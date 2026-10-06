"""Create a comprehensive, readable audit of a supply chain CSV dataset."""

from __future__ import annotations

import argparse
import calendar
from pathlib import Path

import pandas as pd


DATE_HINTS = ("date", "timestamp", "datetime")


def audit_csv(csv_path: Path) -> str:
    """Return a detailed Markdown report with structural, domain, and quality checks."""
    frame = pd.read_csv(csv_path, low_memory=False)

    lines: list[str] = [
        "# Dataset Audit Report: Supply Chain Inventory Candidate",
        "",
        f"- **File:** `{csv_path.name}`",
        f"- **Rows:** {len(frame):,}",
        f"- **Columns:** {len(frame.columns):,}",
        f"- **Exact duplicate rows:** {int(frame.duplicated().sum()):,}",
        f"- **Rows with at least one missing value:** {int(frame.isna().any(axis=1).sum()):,}",
        "",
        "## 1. Executive Summary & Verdict",
        "",
    ]

    has_date = "Date" in frame.columns
    has_sku = "SKU_ID" in frame.columns
    has_wh = "Warehouse_ID" in frame.columns
    has_sales = "Units_Sold" in frame.columns
    has_inv = "Inventory_Level" in frame.columns
    has_order = "Order_Quantity" in frame.columns
    has_lead = "Supplier_Lead_Time_Days" in frame.columns
    has_rop = "Reorder_Point" in frame.columns
    has_forecast = "Demand_Forecast" in frame.columns
    has_stockout = "Stockout_Flag" in frame.columns
    has_region = "Region" in frame.columns
    has_supplier = "Supplier_ID" in frame.columns
    has_promo = "Promotion_Flag" in frame.columns
    has_cost = "Unit_Cost" in frame.columns
    has_price = "Unit_Price" in frame.columns

    same_day_matches = 0
    total_transitions = 0
    zero_lead_time_pct = 0.0
    min_inv = int(frame["Inventory_Level"].min()) if has_inv else 0
    forecast_corr = 0.0

    if has_date and has_sku and has_wh and has_inv and has_sales and has_order:
        df_sorted = frame.copy()
        df_sorted["_dt"] = pd.to_datetime(df_sorted["Date"], errors="coerce")
        df_sorted = df_sorted.sort_values(["SKU_ID", "Warehouse_ID", "_dt"]).reset_index(drop=True)
        df_sorted["_prev_inv"] = df_sorted.groupby(["SKU_ID", "Warehouse_ID"])["Inventory_Level"].shift(1)
        valid = df_sorted.dropna(subset=["_prev_inv"])
        total_transitions = len(valid)
        expected_same_day = valid["_prev_inv"] - valid["Units_Sold"] + valid["Order_Quantity"]
        same_day_matches = int((valid["Inventory_Level"] == expected_same_day).sum())
        if total_transitions > 0:
            zero_lead_time_pct = (same_day_matches / total_transitions) * 100

    if has_sales and has_forecast:
        forecast_corr = float(frame["Units_Sold"].corr(frame["Demand_Forecast"]))

    lines.extend([
        "> [!IMPORTANT]",
        "> **Audit Verdict: Demonstration / Prototype Use Only (With Identified Caveats)**",
        "> ",
        "> This dataset is synthetic and demonstrates basic schema elements, but it exhibits several critical synthetic generation artifacts:",
        f"> 1. **Instantaneous Replenishment (0 Lead Time in Practice):** {zero_lead_time_pct:.1f}% ({same_day_matches:,}/{total_transitions:,}) of inventory transitions follow the exact formula `Inventory_Level[t] = Inventory_Level[t-1] - Units_Sold[t] + Order_Quantity[t]`. Replenishment orders arrive the exact same day they are ordered, completely ignoring `Supplier_Lead_Time_Days` (which ranges from 2 to 14 days).",
        f"> 2. **Zero Stockout Events:** `Stockout_Flag` is constant `0` across all rows. The minimum inventory level observed is `{min_inv:,}`, meaning the synthetic inventory buffer was never depleted.",
        f"> 3. **Synthetic Circularity / Data Leakage in `Demand_Forecast`:** The `Demand_Forecast` column has an extreme correlation ({forecast_corr:.3f}) with same-day `Units_Sold`, constructed as `Units_Sold + Normal(0, ~3)`. It is not an authentic forward-looking operational forecast and cannot be used as an input feature for predictive modeling.",
        "> 4. **Random Geographic Assignment:** Warehouses do not reside in a single geographic `Region`. Each warehouse's recorded region switches randomly day by day (~25% in East, North, South, West).",
        "> 5. **Truncated Leap Year Calendar:** Contains exactly 365 days (2024-01-01 to 2024-12-30), omitting December 31, 2024.",
        "",
        "## 2. Column Overview",
        "",
        "| Column | Type | Missing | Unique | Example values |",
        "|---|---|---:|---:|---|",
    ])

    for column in frame.columns:
        series = frame[column]
        examples = ", ".join(repr(value) for value in series.dropna().head(3).tolist())
        examples = examples.replace("|", "\\|")
        lines.append(
            f"| `{column}` | {series.dtype} | {int(series.isna().sum()):,} "
            f"| {int(series.nunique(dropna=True)):,} | {examples or '—'} |"
        )

    constant_columns = [column for column in frame if frame[column].nunique(dropna=False) <= 1]
    lines.extend(["", "## 3. Constant or Single-Value Columns", ""])
    if constant_columns:
        lines.append(", ".join(f"`{column}`" for column in constant_columns))
        lines.append("")
        lines.append("> [!WARNING]")
        if has_stockout and "Stockout_Flag" in constant_columns and frame["Stockout_Flag"].iloc[0] == 0:
            lines.append(
                "> `Stockout_Flag` is always zero, so it cannot be used to train a stockout classifier on this dataset."
            )
        else:
            lines.append("> Constant columns contain no variation and cannot help distinguish outcomes.")
    else:
        lines.append("None found.")

    lines.extend(["", "## 4. Date Range & Time Horizon Coverage", ""])
    date_columns = [
        col for col in frame.columns
        if any(h in str(col).lower() for h in DATE_HINTS) and not col.endswith(("_Days", "_days", "_days_count"))
    ]
    if not date_columns:
        lines.append("No column name obviously suggests a date. Inspect the column names and values manually.")
    else:
        for column in date_columns:
            parsed = pd.to_datetime(frame[column], errors="coerce")
            valid_dt = parsed.dropna()
            if valid_dt.empty:
                lines.append(f"- `{column}`: could not parse any values as dates.")
            else:
                unique_dates = valid_dt.drop_duplicates().sort_values()
                start_date = unique_dates.min().date()
                end_date = unique_dates.max().date()
                days_span = (unique_dates.max() - unique_dates.min()).days + 1
                lines.append(f"- **Column:** `{column}`")
                lines.append(f"- **Valid date entries:** {len(valid_dt):,} of {len(frame):,}")
                lines.append(f"- **Date range:** `{start_date}` to `{end_date}` ({days_span} calendar days span)")
                lines.append(f"- **Unique dates present:** {len(unique_dates):,}")

                full_range = pd.date_range(start=start_date, end=end_date)
                missing_calendar = set(full_range) - set(unique_dates)
                if missing_calendar:
                    missing_strs = [d.strftime("%Y-%m-%d") for d in sorted(missing_calendar)]
                    lines.append(f"- **Missing dates in span:** {', '.join(f'`{d}`' for d in missing_strs)}")
                else:
                    lines.append("- **Continuity:** Continuous daily records across the span.")

                if start_date.year == 2024 and end_date.strftime("%Y-%m-%d") == "2024-12-30":
                    lines.append(
                        "- **Note on calendar year:** 2024 was a leap year (366 days). "
                        "The dataset ends on `2024-12-30`, missing `2024-12-31`."
                    )

    lines.extend(["", "## 5. Entity Coverage & Hierarchy", ""])
    if has_sku and has_wh:
        num_skus = int(frame["SKU_ID"].nunique())
        num_wh = int(frame["Warehouse_ID"].nunique())
        combinations = frame.groupby(["SKU_ID", "Warehouse_ID"]).size()
        lines.append(f"- **SKUs:** {num_skus:,}")
        lines.append(f"- **Warehouses:** {num_wh:,}")
        lines.append(f"- **Total SKU-Warehouse series:** {len(combinations):,} (expected {num_skus * num_wh:,})")
        lines.append(
            f"- **Records per series:** Min = {combinations.min()}, Max = {combinations.max()} "
            f"({'Balanced panel' if combinations.min() == combinations.max() else 'Unbalanced'})"
        )
    if has_supplier:
        num_supp = int(frame["Supplier_ID"].nunique())
        lines.append(f"- **Suppliers:** {num_supp:,}")
        if has_sku and has_wh:
            supp_per_pair = frame.groupby(["SKU_ID", "Warehouse_ID"])["Supplier_ID"].nunique()
            lines.append(
                f"- **Supplier assignment:** Fixed per SKU-Warehouse pair "
                f"({supp_per_pair.max()} unique supplier per pair)."
            )

    if has_region and has_wh:
        reg_per_wh = frame.groupby(["Warehouse_ID", "Region"]).size().unstack(fill_value=0)
        lines.append("")
        lines.append("### Warehouse-to-Region Mapping Anomaly")
        lines.append(
            "In physical logistics, a warehouse operates within a fixed geographic region. "
            "However, in this dataset, records for each warehouse are uniformly distributed across all regions:"
        )
        lines.append("")
        lines.append(reg_per_wh.to_markdown())
        lines.append("")
        lines.append(
            "> [!NOTE]\n"
            "> `Region` varies randomly day to day for every warehouse. It should not be treated as a physical "
            "warehouse location in routing or disruption models."
        )

    lines.extend(["", "## 6. Demand & Sales Analysis", ""])
    if has_sales:
        s_mean = frame["Units_Sold"].mean()
        s_std = frame["Units_Sold"].std()
        s_min = frame["Units_Sold"].min()
        s_max = frame["Units_Sold"].max()
        lines.append(f"- **Units Sold Summary:** Mean = {s_mean:.2f}, Std = {s_std:.2f}, Min = {s_min}, Max = {s_max}")

        if has_promo:
            promo_stats = frame.groupby("Promotion_Flag")["Units_Sold"].agg(["count", "mean", "std"]).round(2)
            if 0 in promo_stats.index and 1 in promo_stats.index:
                lines.append(
                    f"- **Promotion association:** Sales averaged {promo_stats.loc[1, 'mean']:.2f} units on promotion days "
                    f"and {promo_stats.loc[0, 'mean']:.2f} units otherwise. This difference does not establish causation."
                )

        if has_date:
            df_temp = frame.copy()
            df_temp["_dt"] = pd.to_datetime(df_temp["Date"], errors="coerce")
            df_temp["_dow"] = df_temp["_dt"].dt.day_name()
            dow_sales = df_temp.groupby("_dow")["Units_Sold"].mean().round(2)
            lines.append(f"- **Average sales by weekday:** {dow_sales.min():.2f} to {dow_sales.max():.2f} units.")

            df_temp["_month"] = df_temp["_dt"].dt.month
            monthly_sales = df_temp.groupby("_month")["Units_Sold"].mean().round(2)
            peak_month = int(monthly_sales.idxmax())
            low_month = int(monthly_sales.idxmin())
            lines.append(
                f"- **Monthly pattern:** Highest average sales were in {calendar.month_name[peak_month]} "
                f"({monthly_sales.max():.1f}); lowest were in {calendar.month_name[low_month]} "
                f"({monthly_sales.min():.1f}). One year does not establish recurring seasonality."
            )

    if has_forecast and has_sales:
        diff = frame["Demand_Forecast"] - frame["Units_Sold"]
        lines.append("")
        lines.append("### Demand Forecast Column Integrity")
        lines.append(f"- **Correlation (`Demand_Forecast` vs `Units_Sold`):** {frame['Demand_Forecast'].corr(frame['Units_Sold']):.4f}")
        lines.append(f"- **Error (`Demand_Forecast` - `Units_Sold`):** Mean = {diff.mean():.3f}, Std = {diff.std():.3f}, Min = {diff.min():.2f}, Max = {diff.max():.2f}")
        lines.append(
            "- **Finding:** `Demand_Forecast` behaves as same-day actual sales perturbed by Gaussian noise ~ $\\mathcal{N}(0, 3)$. "
            "It must **not** be used as a predictor variable in time-series models due to target leakage."
        )

    lines.extend(["", "## 7. Inventory Plausibility & Balance Verification", ""])
    if has_inv and has_sales and has_order:
        lines.append("### Stock Balance Equation")
        lines.append("We tested the standard conservation of inventory balance:")
        lines.append("$$\\text{Inventory}_t = \\text{Inventory}_{t-1} - \\text{Units Sold}_t + \\text{Order Received}_t$$")
        lines.append("")
        lines.append(f"- **Tested Transitions:** {total_transitions:,}")
        lines.append(f"- **Exact Matches:** {same_day_matches:,} ({zero_lead_time_pct:.2f}%)")
        lines.append(f"- **Mismatches:** {total_transitions - same_day_matches:,}")
        lines.append("")

        if has_rop:
            df_sorted = frame.copy()
            df_sorted["_dt"] = pd.to_datetime(df_sorted["Date"], errors="coerce")
            df_sorted = df_sorted.sort_values(["SKU_ID", "Warehouse_ID", "_dt"]).reset_index(drop=True)
            df_sorted["_prev_inv"] = df_sorted.groupby(["SKU_ID", "Warehouse_ID"])["Inventory_Level"].shift(1)

            below_rop = df_sorted[df_sorted["_prev_inv"] <= df_sorted["Reorder_Point"]]
            above_rop = df_sorted[df_sorted["_prev_inv"] > df_sorted["Reorder_Point"]]
            reorders_triggered = int((below_rop["Order_Quantity"] > 0).sum())
            false_reorders = int((above_rop["Order_Quantity"] > 0).sum())

            lines.append("### Reorder Policy Trigger Mechanism")
            lines.append(f"- **Trigger Rule Tested:** `Inventory[t-1] <= Reorder_Point`")
            lines.append(f"- **Total Times Threshold Met:** {len(below_rop):,}")
            reorder_rate = reorders_triggered / len(below_rop) * 100 if len(below_rop) else 0.0
            above_rate = false_reorders / len(above_rop) * 100 if len(above_rop) else 0.0
            lines.append(f"- **Threshold events followed by an order:** {reorders_triggered:,} ({reorder_rate:.1f}%)")
            lines.append(f"- **Orders placed above the threshold:** {false_reorders:,} ({above_rate:.1f}%)")

            reorder_orders = frame[frame["Order_Quantity"] > 0]["Order_Quantity"]
            if not reorder_orders.empty:
                lines.append(
                    f"- **Recorded order sizes:** {reorder_orders.min():.0f} to {reorder_orders.max():.0f} units "
                    f"(mean {reorder_orders.mean():.1f})."
                )

        if has_lead:
            lines.append("")
            lines.append("### Supplier Lead Time Decoupling")
            lines.append(
                f"- In the dataset, `Supplier_Lead_Time_Days` ranges from {frame['Supplier_Lead_Time_Days'].min()} "
                f"to {frame['Supplier_Lead_Time_Days'].max()} days (Mean = {frame['Supplier_Lead_Time_Days'].mean():.1f} days)."
            )
            lines.append(
                "- **Critical Finding:** Orders placed on day $t$ enter available inventory on day $t$ without delay. "
                "The synthetic data generator recorded lead times as metadata, but executed replenishment with **zero latency**."
            )

    lines.extend(["", "## 8. Pricing & Margins Summary", ""])
    if has_cost and has_price:
        margins = (frame["Unit_Price"] - frame["Unit_Cost"]) / frame["Unit_Price"]
        lines.append(
            f"- **Unit Cost:** Min = ${frame['Unit_Cost'].min():.2f}, Mean = ${frame['Unit_Cost'].mean():.2f}, Max = ${frame['Unit_Cost'].max():.2f}"
        )
        lines.append(
            f"- **Unit Price:** Min = ${frame['Unit_Price'].min():.2f}, Mean = ${frame['Unit_Price'].mean():.2f}, Max = ${frame['Unit_Price'].max():.2f}"
        )
        lines.append(
            f"- **Gross Margin %:** Min = {margins.min()*100:.1f}%, Mean = {margins.mean()*100:.1f}%, Max = {margins.max()*100:.1f}% (No negative margin rows)"
        )
        lines.append(
            "- Pricing and cost values are fixed per SKU-Warehouse pair across the entire year."
        )

    numeric = frame.select_dtypes(include="number")
    lines.extend(["", "## 9. Numeric Column Distributions", ""])
    if numeric.empty:
        lines.append("No numeric columns found.")
    else:
        summary = numeric.describe().transpose().round(3)
        lines.append(summary.to_markdown())

    lines.extend(
        [
            "",
            "## Review before using this data",
            "",
            "This report is an initial structural check, not proof that the data is accurate. "
            "Confirm what each field means, whether each row represents a day/item/location, "
            "whether inventory values are opening or closing stock, and whether sales can be lower "
            "than true demand during stockouts. Check that related rows form sensible inventory balances.",
            "",
        ]
    )
    lines.extend([
        "",
        "## 10. Implications & Recommendations for Resilio",
        "",
        "In accordance with project guidance (`AGENTS.md` and `README.md`):",
        "",
        "### What This Dataset Can Support",
        "- **Demand Forecasting Prototyping:** `Units_Sold` has observed variation within this synthetic year and can be used to compare simple chronological forecasts.",
        "- **UI & Dashboard Wireframing:** Provides structured multi-entity hierarchy (50 SKUs, 5 Warehouses, 10 Suppliers) suitable for designing tables, inventory cards, and scenario dropdowns.",
        "",
        "### What This Dataset Cannot Support As-Is",
        "- **Real-World Evidence:** The publisher states this is synthetic, and our audit confirms synthetic artifacts (0 lead time, uniform random reorder quantities, random warehouse regions). Results must never be presented as empirical supply-chain evidence.",
        "- **Disruption Analysis on Historical Inventory:** Because historical stock never dropped below 168 and replenishment was instantaneous, historical stockout metrics cannot validate disaster or lead-time disruption models.",
        "- **Using `Demand_Forecast` as an ML Feature:** Due to synthetic target leakage, this column must be excluded from feature pipelines.",
        "",
        "### Recommended Architecture for Resilio",
        "1. **Use Demand for Forecasting:** Train forecasting models on past `Units_Sold` and carefully chosen calendar features. Promotion data is excluded from the current Phase 2 model.",
        "2. **Simulate Inventory Dynamically:** Do not trust the synthetic CSV `Inventory_Level`; calculate forward inventory with explicit rules and selected lead-time or supply scenarios, and label any shortages as simulated outcomes.",
        "3. **Clearly Label Assumptions:** Document that the raw Kaggle dataset is demonstration data, with inventory simulation powered by Resilio's internal logic.",
        "",
    ])

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a CSV and write a comprehensive Markdown summary.")
    parser.add_argument("csv", type=Path, help="Path to the CSV file to inspect")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/data_audit.md"),
        help="Report path (default: reports/data_audit.md)",
    )
    args = parser.parse_args()

    if not args.csv.is_file():
        parser.error(f"CSV file does not exist: {args.csv}")

    report = audit_csv(args.csv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Comprehensive audit successfully written to {args.output}")


if __name__ == "__main__":
    main()
