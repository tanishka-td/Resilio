"""Small local JSON API for Resilio's demand forecast and scenario simulator."""

from __future__ import annotations

import argparse
import json
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import pandas as pd

from simulate_resilience import (
    create_scenario_result,
    forecast_selected_series,
    train_latest_model,
)


MAX_REQUEST_BYTES = 64 * 1024
ALLOWED_BROWSER_ORIGINS = {
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:5501",
    "http://127.0.0.1:5501",
}


class ResilioService:
    def __init__(self, csv_path: Path) -> None:
        if not csv_path.is_file():
            raise FileNotFoundError(f"Dataset not found: {csv_path}")
        self.frame = pd.read_csv(csv_path, low_memory=False)
        required = {"Date", "SKU_ID", "Warehouse_ID", "Units_Sold", "Supplier_Lead_Time_Days"}
        missing = required - set(self.frame.columns)
        if missing:
            raise ValueError(f"Dataset is missing required columns: {', '.join(sorted(missing))}")
        self.frame["Date"] = pd.to_datetime(self.frame["Date"], errors="coerce")
        if self.frame["Date"].isna().any():
            raise ValueError("Dataset contains dates that could not be read.")
        self.model_context = train_latest_model(self.frame)
        self.last_date = self.model_context[3]

    def items(self) -> list[dict[str, Any]]:
        pairs = self.frame[["SKU_ID", "Warehouse_ID", "Supplier_Lead_Time_Days"]].drop_duplicates()
        return [
            {
                "sku_id": row.SKU_ID,
                "warehouse_id": row.Warehouse_ID,
                "lead_time_days": int(row.Supplier_Lead_Time_Days),
            }
            for row in pairs.sort_values(["SKU_ID", "Warehouse_ID"]).itertuples(index=False)
        ]

    def overview(self) -> dict[str, Any]:
        monthly = self.frame.assign(month=self.frame["Date"].dt.to_period("M")).groupby("month")["Units_Sold"].sum()
        warehouses = self.frame.groupby("Warehouse_ID")["Units_Sold"].sum().sort_values(ascending=False)
        skus = self.frame.groupby("SKU_ID")["Units_Sold"].sum().sort_values(ascending=False).head(8)
        dated = self.frame.assign(month=self.frame["Date"].dt.to_period("M"))
        warehouse_monthly = dated.pivot_table(
            index="Warehouse_ID", columns="month", values="Units_Sold", aggfunc="sum", fill_value=0
        ).reindex(index=warehouses.index, columns=monthly.index, fill_value=0)
        sku_warehouse = self.frame.pivot_table(
            index="SKU_ID", columns="Warehouse_ID", values="Units_Sold", aggfunc="sum", fill_value=0
        ).reindex(index=skus.index, columns=warehouses.index, fill_value=0)
        promotion_sales = self.frame.groupby("Promotion_Flag")["Units_Sold"].mean() if "Promotion_Flag" in self.frame else pd.Series(dtype=float)
        promotion_comparison = None
        if 0 in promotion_sales.index and 1 in promotion_sales.index:
            promotion_comparison = {
                "regular_average": float(promotion_sales.loc[0]),
                "promotion_average": float(promotion_sales.loc[1]),
                "note": "Association in synthetic data; this does not show that promotions caused the difference.",
            }
        return {
            "data_label": "Synthetic demonstration data",
            "rows": int(len(self.frame)),
            "sku_count": int(self.frame["SKU_ID"].nunique()),
            "warehouse_count": int(self.frame["Warehouse_ID"].nunique()),
            "supplier_count": int(self.frame["Supplier_ID"].nunique()) if "Supplier_ID" in self.frame else None,
            "date_start": self.frame["Date"].min().strftime("%Y-%m-%d"),
            "date_end": self.frame["Date"].max().strftime("%Y-%m-%d"),
            "recorded_units_sold": float(self.frame["Units_Sold"].sum()),
            "mean_daily_units_sold": float(self.frame["Units_Sold"].mean()),
            "monthly_sales": [
                {"month": period.strftime("%b %Y"), "units": float(value)}
                for period, value in monthly.items()
            ],
            "warehouse_sales": [
                {"warehouse_id": str(name), "units": float(value)}
                for name, value in warehouses.items()
            ],
            "warehouse_monthly": {
                "months": [period.strftime("%b %Y") for period in monthly.index],
                "rows": [
                    {"warehouse_id": str(name), "units": [float(value) for value in warehouse_monthly.loc[name].tolist()]}
                    for name in warehouse_monthly.index
                ],
            },
            "top_skus": [
                {"sku_id": str(name), "units": float(value)}
                for name, value in skus.items()
            ],
            "sku_warehouse": {
                "warehouses": [str(name) for name in warehouses.index],
                "rows": [
                    {"sku_id": str(name), "units": [float(value) for value in sku_warehouse.loc[name].tolist()]}
                    for name in sku_warehouse.index
                ],
            },
            "promotion_comparison": promotion_comparison,
            "inventory_note": "Recorded inventory and order quantities are synthetic and do not reflect the listed delivery delays.",
        }

    def history(self, sku: str, warehouse: str) -> dict[str, Any]:
        selected = self.frame[(self.frame["SKU_ID"] == sku) & (self.frame["Warehouse_ID"] == warehouse)]
        if selected.empty:
            raise ValueError(f"Unknown SKU/warehouse pair: {sku} at {warehouse}.")
        columns = ["Date", "Units_Sold"]
        if "Inventory_Level" in selected:
            columns.append("Inventory_Level")
        if "Promotion_Flag" in selected:
            columns.append("Promotion_Flag")
        records = []
        for row in selected.sort_values("Date")[columns].itertuples(index=False, name=None):
            values = dict(zip(columns, row))
            item = {"date": values["Date"].strftime("%Y-%m-%d"), "units_sold": float(values["Units_Sold"])}
            if "Inventory_Level" in columns:
                item["recorded_inventory"] = float(values["Inventory_Level"])
            if "Promotion_Flag" in columns:
                item["promotion_flag"] = int(values["Promotion_Flag"])
            records.append(item)
        return {
            "sku_id": sku,
            "warehouse_id": warehouse,
            "history": records,
            "inventory_note": "Recorded inventory is shown only as a dataset value; its historical replenishment timing is inconsistent.",
        }

    def forecast(self, sku: str, warehouse: str, horizon: int = 14) -> dict[str, Any]:
        if not 1 <= horizon <= 14:
            raise ValueError("Forecast horizon must be between 1 and 14 days.")
        model, encoder, scaler, last_date = self.model_context
        forecast_rows = forecast_selected_series(
            self.frame, sku, warehouse, model, encoder, scaler, last_date, horizon
        )
        lead_time = self.items()
        selected = next((item for item in lead_time if item["sku_id"] == sku and item["warehouse_id"] == warehouse), None)
        if selected is None:
            raise ValueError(f"Unknown SKU/warehouse pair: {sku} at {warehouse}.")
        return {
            "sku_id": sku,
            "warehouse_id": warehouse,
            "trained_through": last_date.strftime("%Y-%m-%d"),
            "lead_time_days": selected["lead_time_days"],
            "forecast": forecast_rows,
            "model": "Recursive Ridge Regression",
            "target": "Recorded sales used as a proxy for demand",
            "promotions_included": False,
        }

    def simulate(self, body: dict[str, Any]) -> dict[str, Any]:
        required = ("sku_id", "warehouse_id", "opening_stock", "order_units")
        missing = [key for key in required if key not in body]
        if missing:
            raise ValueError(f"Required fields missing: {', '.join(missing)}")

        def number(key: str, default: float | None = None) -> float:
            value = body.get(key, default)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{key} must be a finite, nonnegative number.")
            return float(value)

        def whole_days(key: str) -> int:
            value = body.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{key} must be a whole number that is zero or greater.")
            return value

        sku = body["sku_id"]
        warehouse = body["warehouse_id"]
        if not isinstance(sku, str) or not isinstance(warehouse, str):
            raise ValueError("sku_id and warehouse_id must be text values.")
        loss = number("shipment_loss_fraction", 0.0)
        if loss > 1:
            raise ValueError("shipment_loss_fraction must be between 0 and 1.")

        return create_scenario_result(
            self.frame,
            sku,
            warehouse,
            number("opening_stock"),
            number("order_units"),
            number("demand_multiplier", 1.0),
            whole_days("delay_days"),
            loss,
            number("extra_stock_units", 0.0),
            whole_days("expedite_days"),
            model_context=self.model_context,
        )


class ResilioRequestHandler(BaseHTTPRequestHandler):
    server_version = "ResilioLocal/1.0"

    @property
    def service(self) -> ResilioService:
        return cast(ResilioHTTPServer, self.server).service

    def _send_json(self, status: int, value: Any) -> None:
        payload = json.dumps(value, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin")
        if origin in ALLOWED_BROWSER_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        origin = self.headers.get("Origin")
        self.send_response(204)
        if origin in ALLOWED_BROWSER_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        request = urlparse(self.path)
        path = request.path
        params = parse_qs(request.query)
        try:
            if path == "/api/health":
                self._send_json(200, {
                    "status": "ready",
                    "data_through": self.service.last_date.strftime("%Y-%m-%d"),
                    "notice": "Synthetic demonstration data; disruption scenarios are user-selected assumptions.",
                })
            elif path == "/api/items":
                self._send_json(200, {"items": self.service.items()})
            elif path == "/api/overview":
                self._send_json(200, self.service.overview())
            elif path == "/api/history":
                sku = params.get("sku_id", [""])[0]
                warehouse = params.get("warehouse_id", [""])[0]
                if not sku or not warehouse:
                    raise ValueError("sku_id and warehouse_id are required.")
                self._send_json(200, self.service.history(sku, warehouse))
            elif path == "/api/forecast":
                sku = params.get("sku_id", [""])[0]
                warehouse = params.get("warehouse_id", [""])[0]
                if not sku or not warehouse:
                    raise ValueError("sku_id and warehouse_id are required.")
                horizon = int(params.get("horizon", ["14"])[0])
                self._send_json(200, self.service.forecast(sku, warehouse, horizon))
            else:
                self._send_json(404, {"error": "Endpoint not found."})
        except (TypeError, ValueError) as error:
            self._send_json(400, {"error": str(error)})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/simulate":
            self._send_json(404, {"error": "Endpoint not found."})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length < 1 or content_length > MAX_REQUEST_BYTES:
                raise ValueError("Request body must be between 1 byte and 64 KB.")
            body = json.loads(self.rfile.read(content_length))
            if not isinstance(body, dict):
                raise ValueError("Request body must be a JSON object.")
            self._send_json(200, self.service.simulate(body))
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
        except Exception:
            self._send_json(500, {"error": "The simulation could not be completed."})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


class ResilioHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], service: ResilioService) -> None:
        super().__init__(address, ResilioRequestHandler)
        self.service = service


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Resilio's local forecast and scenario API.")
    parser.add_argument("--csv", type=Path, default=Path("Data/raw/supply_chain_dataset1.csv"))
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    service = ResilioService(args.csv)
    server = ResilioHTTPServer(("127.0.0.1", args.port), service)
    print(f"Resilio API ready at http://127.0.0.1:{args.port}")
    print(f"Dataset and model use sales through {service.last_date:%Y-%m-%d}.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping Resilio API.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
