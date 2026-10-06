"""Forecast demand and compare normal, disruption, and response scenarios."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from forecast_demand import build_training_matrix, compute_cyclical_calendar


NUMERIC_FEATURE_COUNT = 11


def train_latest_model(frame: pd.DataFrame) -> tuple[Ridge, OneHotEncoder, StandardScaler, pd.Timestamp]:
    """Fit the Phase 2 model through the last date available in the CSV."""
    series = frame.sort_values(["SKU_ID", "Warehouse_ID", "Date"]).reset_index(drop=True)
    last_date = pd.Timestamp(series["Date"].max())
    encoder = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    encoder.fit(series[["SKU_ID", "Warehouse_ID"]])
    features, target = build_training_matrix(
        series, encoder, train_end_date=last_date.strftime("%Y-%m-%d")
    )
    scaler = StandardScaler()
    features[:, :NUMERIC_FEATURE_COUNT] = scaler.fit_transform(features[:, :NUMERIC_FEATURE_COUNT])
    model = Ridge(alpha=1.0)
    model.fit(features, target)
    return model, encoder, scaler, last_date


def forecast_selected_series(
    frame: pd.DataFrame,
    sku: str,
    warehouse: str,
    model: Ridge,
    encoder: OneHotEncoder,
    scaler: StandardScaler,
    last_date: pd.Timestamp,
    horizon: int,
) -> list[dict[str, float | str]]:
    """Create recursive forecasts without using any future actual sales."""
    selected = frame[(frame["SKU_ID"] == sku) & (frame["Warehouse_ID"] == warehouse)]
    selected = selected.sort_values("Date")
    if selected.empty:
        raise ValueError(f"Unknown SKU/warehouse pair: {sku} at {warehouse}.")
    if selected["Date"].max() != last_date:
        raise ValueError("The selected series does not include the dataset's latest date.")
    history = selected["Units_Sold"].astype(float).tolist()
    if len(history) < 14:
        raise ValueError("At least 14 days of sales history are required.")

    entity = encoder.transform(pd.DataFrame([{"SKU_ID": sku, "Warehouse_ID": warehouse}]))
    output = []
    for step in range(1, horizon + 1):
        target_date = last_date + pd.Timedelta(days=step)
        lags = [history[-1], history[-2], history[-3], history[-7], history[-14]]
        numeric = np.array(lags + [float(np.mean(history[-7:])), float(np.mean(history[-14:]))])
        calendar = compute_cyclical_calendar(pd.Series([target_date])).to_numpy()[0]
        row = np.hstack([numeric, calendar, entity[0]]).reshape(1, -1)
        row[:, :NUMERIC_FEATURE_COUNT] = scaler.transform(row[:, :NUMERIC_FEATURE_COUNT])
        predicted = max(0.0, float(model.predict(row)[0]))
        history.append(predicted)
        output.append({"date": target_date.strftime("%Y-%m-%d"), "forecast_units": predicted})
    return output


def simulate(
    forecast: list[dict[str, float | str]],
    *,
    opening_stock: float,
    order_units: float,
    lead_time_days: int,
    demand_multiplier: float = 1.0,
    delivery_delay_days: int = 0,
    shipment_loss_fraction: float = 0.0,
    extra_stock_units: float = 0.0,
    expedite_days: int = 0,
) -> dict:
    """Roll inventory forward one day at a time and return its daily trace."""
    adjusted_delay = max(0, delivery_delay_days - expedite_days)
    arrival_day = lead_time_days + adjusted_delay
    delivered_units = order_units * (1.0 - shipment_loss_fraction)
    stock = opening_stock + extra_stock_units
    shortage_days = 0
    unmet_units_total = 0.0
    first_shortage_date = None
    rows = []

    for day, item in enumerate(forecast, start=1):
        received = delivered_units if day == arrival_day else 0.0
        available = stock + received
        demand = float(item["forecast_units"]) * demand_multiplier
        unmet = max(0.0, demand - available)
        stock = max(0.0, available - demand)
        if unmet > 0:
            shortage_days += 1
            unmet_units_total += unmet
            if first_shortage_date is None:
                first_shortage_date = str(item["date"])
        rows.append({
            "date": item["date"],
            "forecast_demand_units": demand,
            "received_units": received,
            "ending_stock_units": stock,
            "unmet_demand_units": unmet,
        })

    return {
        "summary": {
            "shortage_days": shortage_days,
            "unmet_demand_units": unmet_units_total,
            "ending_stock_units": stock,
            "first_shortage_date": first_shortage_date,
            "arrival_date": (str(forecast[arrival_day - 1]["date"]) if arrival_day <= len(forecast) else None),
            "received_units": delivered_units if arrival_day <= len(forecast) else 0.0,
        },
        "daily": rows,
    }


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if not np.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("Enter a finite number that is zero or greater.")
    return parsed


def nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("Enter a whole number that is zero or greater.")
    return parsed


def create_scenario_result(
    frame: pd.DataFrame,
    sku: str,
    warehouse: str,
    opening_stock: float,
    order_units: float,
    demand_multiplier: float = 1.0,
    delay_days: int = 0,
    shipment_loss: float = 0.0,
    extra_stock: float = 0.0,
    expedite_days: int = 0,
    model_context: tuple[Ridge, OneHotEncoder, StandardScaler, pd.Timestamp] | None = None,
) -> dict:
    """Build forecast, normal, disruption, and response results for a SKU pair."""
    if not 0 <= shipment_loss <= 1:
        raise ValueError("Shipment loss must be between 0 and 1.")
    if any(not np.isfinite(v) or v < 0 for v in (opening_stock, order_units, demand_multiplier, extra_stock)):
        raise ValueError("Stock, order, and multiplier values must be finite and nonnegative.")
    if delay_days < 0 or expedite_days < 0:
        raise ValueError("Delay and expedite days must be whole numbers that are zero or greater.")

    selected = frame[(frame["SKU_ID"] == sku) & (frame["Warehouse_ID"] == warehouse)]
    if selected.empty:
        raise ValueError(f"Unknown SKU/warehouse pair: {sku} at {warehouse}.")
    lead_values = pd.to_numeric(selected["Supplier_Lead_Time_Days"], errors="coerce").dropna().unique()
    if len(lead_values) != 1 or int(lead_values[0]) < 1:
        raise ValueError("The selected pair must have one consistent, positive supplier lead time.")
    lead_time = int(lead_values[0])
    horizon = max(14, lead_time + delay_days)
    if horizon > 60:
        raise ValueError("The resulting forecast horizon exceeds the 60-day safety limit.")

    model, encoder, scaler, last_date = model_context or train_latest_model(frame)
    forecast = forecast_selected_series(frame, sku, warehouse, model, encoder, scaler, last_date, horizon)
    common = {"opening_stock": opening_stock, "order_units": order_units, "lead_time_days": lead_time}
    normal = simulate(forecast, **common)
    disruption = simulate(
        forecast, **common, demand_multiplier=demand_multiplier,
        delivery_delay_days=delay_days, shipment_loss_fraction=shipment_loss,
    )
    response = simulate(
        forecast, **common, demand_multiplier=demand_multiplier,
        delivery_delay_days=delay_days, shipment_loss_fraction=shipment_loss,
        extra_stock_units=extra_stock, expedite_days=expedite_days,
    )
    return {
        "notice": "Demonstration using a synthetic dataset. Scenarios are user-selected what-if assumptions, not predictions.",
        "selection": {"sku_id": sku, "warehouse_id": warehouse},
        "forecast": {
            "model": "Ridge regression, recursively projected",
            "trained_through": last_date.strftime("%Y-%m-%d"),
            "target": "Units_Sold (recorded sales used as a demand proxy)",
            "promotions_included": False,
            "daily": forecast,
        },
        "inputs": {
            "starting_stock_units": opening_stock,
            "planned_order_units": order_units,
            "listed_lead_time_days": lead_time,
            "disruption_demand_multiplier": demand_multiplier,
            "disruption_delivery_delay_days": delay_days,
            "disruption_shipment_loss_fraction": shipment_loss,
            "response_extra_stock_units": extra_stock,
            "response_expedite_days": expedite_days,
            "inventory_values_source": "User-entered assumptions; historical inventory and orders are not used.",
        },
        "comparisons": {
            "normal_conditions": normal,
            "selected_disruption": disruption,
            "disruption_with_response": response,
        },
        "limitations": [
            "The CSV is synthetic and cannot establish real-world performance.",
            "The CSV's historical inventory and order quantities are excluded because its recorded replenishment is instantaneous.",
            "Costs are not compared because holding and shortage costs are missing from the data.",
            "The model does not predict disruptions; all disruption settings are selected by the user.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare a normal inventory outlook, a disruption, and a user-selected response."
    )
    parser.add_argument("--csv", type=Path, default=Path("Data/raw/supply_chain_dataset1.csv"))
    parser.add_argument("--sku", required=True, help="SKU_ID from the CSV")
    parser.add_argument("--warehouse", required=True, help="Warehouse_ID from the CSV")
    parser.add_argument("--opening-stock", type=nonnegative_float, required=True,
                        help="Starting units, entered by the user (not taken from historical inventory)")
    parser.add_argument("--order-units", type=nonnegative_float, required=True,
                        help="Units in one planned order arriving after the listed lead time")
    parser.add_argument("--demand-multiplier", type=nonnegative_float, default=1.0,
                        help="Disruption demand multiplier; 1.2 means 20%% higher forecast demand")
    parser.add_argument("--delay-days", type=nonnegative_int, default=0,
                        help="Additional delivery delay for the disruption scenario")
    parser.add_argument("--shipment-loss", type=float, default=0.0,
                        help="Fraction of the planned shipment lost, from 0 through 1")
    parser.add_argument("--extra-stock", type=nonnegative_float, default=0.0,
                        help="Extra stock prepared before the disruption")
    parser.add_argument("--expedite-days", type=nonnegative_int, default=0,
                        help="Days removed from the disruption delay in the response scenario")
    parser.add_argument("--output", type=Path, default=Path("outputs/resilience_scenarios.json"))
    args = parser.parse_args()

    if not args.csv.is_file():
        parser.error(f"CSV file not found: {args.csv}")
    if not 0 <= args.shipment_loss <= 1:
        parser.error("--shipment-loss must be between 0 and 1.")
    frame = pd.read_csv(args.csv, low_memory=False)
    required = {"Date", "SKU_ID", "Warehouse_ID", "Units_Sold", "Supplier_Lead_Time_Days"}
    missing = required - set(frame.columns)
    if missing:
        parser.error(f"Missing required columns: {', '.join(sorted(missing))}")
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    if frame["Date"].isna().any():
        parser.error("The CSV contains dates that could not be read.")
    try:
        result = create_scenario_result(
            frame, args.sku, args.warehouse, args.opening_stock, args.order_units,
            args.demand_multiplier, args.delay_days, args.shipment_loss,
            args.extra_stock, args.expedite_days,
        )
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Scenario comparison written to: {args.output}")
    print(f"Normal: {result['comparisons']['normal_conditions']['summary']}")
    print(f"Disruption: {result['comparisons']['selected_disruption']['summary']}")
    print(f"With response: {result['comparisons']['disruption_with_response']['summary']}")


if __name__ == "__main__":
    main()
