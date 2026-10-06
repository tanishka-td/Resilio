"""Train and evaluate a recursive demand forecast against a seven-day average baseline."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder, StandardScaler


CUTOFF_DATES = [
    "2024-11-01",
    "2024-11-08",
    "2024-11-15",
    "2024-11-22",
    "2024-11-29",
    "2024-12-06",
    "2024-12-13",
]
HORIZON_DAYS = 14
TRAIN_END_DATE = "2024-10-31"


def compute_cyclical_calendar(dates: pd.Series) -> pd.DataFrame:
    """Compute continuous cyclical sine/cosine encodings for calendar day-of-year and day-of-week."""
    doy = dates.dt.dayofyear
    dow = dates.dt.dayofweek
    return pd.DataFrame(
        {
            "sin_doy": np.sin(2 * np.pi * doy / 365.25),
            "cos_doy": np.cos(2 * np.pi * doy / 365.25),
            "sin_dow": np.sin(2 * np.pi * dow / 7.0),
            "cos_dow": np.cos(2 * np.pi * dow / 7.0),
        },
        index=dates.index,
    )


def build_training_matrix(
    df: pd.DataFrame, encoder: OneHotEncoder, train_end_date: str = TRAIN_END_DATE
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Build features using rows on or before the requested training end date."""
    train_df = df[df["Date"] <= train_end_date].copy()
    entity_ohe = encoder.transform(train_df[["SKU_ID", "Warehouse_ID"]])
    cal_df = compute_cyclical_calendar(train_df["Date"])
    cal_features = cal_df.to_numpy()

    lag_feature_names = [
        "lag_1",
        "lag_2",
        "lag_3",
        "lag_7",
        "lag_14",
        "roll_mean_7",
        "roll_mean_14",
    ]
    train_df["lag_1"] = train_df.groupby(["SKU_ID", "Warehouse_ID"])["Units_Sold"].shift(1)
    train_df["lag_2"] = train_df.groupby(["SKU_ID", "Warehouse_ID"])["Units_Sold"].shift(2)
    train_df["lag_3"] = train_df.groupby(["SKU_ID", "Warehouse_ID"])["Units_Sold"].shift(3)
    train_df["lag_7"] = train_df.groupby(["SKU_ID", "Warehouse_ID"])["Units_Sold"].shift(7)
    train_df["lag_14"] = train_df.groupby(["SKU_ID", "Warehouse_ID"])["Units_Sold"].shift(14)

    roll7 = (
        train_df.groupby(["SKU_ID", "Warehouse_ID"])["Units_Sold"]
        .rolling(window=7, closed="left")
        .mean()
        .reset_index(level=[0, 1], drop=True)
    )
    roll14 = (
        train_df.groupby(["SKU_ID", "Warehouse_ID"])["Units_Sold"]
        .rolling(window=14, closed="left")
        .mean()
        .reset_index(level=[0, 1], drop=True)
    )
    train_df["roll_mean_7"] = roll7
    train_df["roll_mean_14"] = roll14

    valid_mask = train_df["lag_14"].notna() & train_df["roll_mean_14"].notna()
    valid_df = train_df[valid_mask]

    lag_matrix = valid_df[lag_feature_names].to_numpy()
    cal_matrix = cal_features[valid_mask]
    ent_matrix = entity_ohe[valid_mask]

    X = np.hstack([lag_matrix, cal_matrix, ent_matrix])
    y = valid_df["Units_Sold"].to_numpy(dtype=float)

    return X, y


def run_recursive_evaluation(
    df: pd.DataFrame, model: Ridge, encoder: OneHotEncoder, scaler: StandardScaler
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate recursive forecasts from historical cutoff dates."""
    series_groups = {
        (sku, wh): sub_df.sort_values("Date").reset_index(drop=True)
        for (sku, wh), sub_df in df.groupby(["SKU_ID", "Warehouse_ID"])
    }

    series_keys = sorted(series_groups.keys())
    entity_df = pd.DataFrame(series_keys, columns=["SKU_ID", "Warehouse_ID"])
    ent_matrix = encoder.transform(entity_df)

    daily_results = []
    cumulative_results = []

    for cutoff_str in CUTOFF_DATES:
        cutoff_dt = pd.to_datetime(cutoff_str)
        target_dates = pd.date_range(cutoff_dt + pd.Timedelta(days=1), periods=HORIZON_DAYS)

        buffers = []
        baselines = []
        actuals_matrix = []
        valid_indices = []

        for idx, key in enumerate(series_keys):
            sub_df = series_groups[key]
            hist = sub_df[sub_df["Date"] <= cutoff_dt]
            actual_window = sub_df[sub_df["Date"].isin(target_dates)].sort_values("Date")
            if len(hist) >= 14 and len(actual_window) == HORIZON_DAYS:
                buffers.append(hist["Units_Sold"].tolist())
                baselines.append(float(hist["Units_Sold"].iloc[-7:].mean()))
                actuals_matrix.append(actual_window["Units_Sold"].to_numpy(dtype=float))
                valid_indices.append(idx)

        n_series = len(valid_indices)
        if n_series == 0:
            continue

        ent_sub = ent_matrix[valid_indices]
        preds_matrix = np.zeros((n_series, HORIZON_DAYS), dtype=float)

        for h in range(1, HORIZON_DAYS + 1):
            tgt_date = target_dates[h - 1]
            doy = tgt_date.dayofyear
            dow = tgt_date.dayofweek

            lags_1 = np.array([buf[-1] for buf in buffers])
            lags_2 = np.array([buf[-2] for buf in buffers])
            lags_3 = np.array([buf[-3] for buf in buffers])
            lags_7 = np.array([buf[-7] for buf in buffers])
            lags_14 = np.array([buf[-14] for buf in buffers])
            rolls_7 = np.array([np.mean(buf[-7:]) for buf in buffers])
            rolls_14 = np.array([np.mean(buf[-14:]) for buf in buffers])

            cal_block = np.tile(
                np.array([
                    np.sin(2 * np.pi * doy / 365.25),
                    np.cos(2 * np.pi * doy / 365.25),
                    np.sin(2 * np.pi * dow / 7.0),
                    np.cos(2 * np.pi * dow / 7.0),
                ]),
                (n_series, 1),
            )

            X_step = np.hstack([
                np.column_stack([lags_1, lags_2, lags_3, lags_7, lags_14, rolls_7, rolls_14]),
                cal_block,
                ent_sub,
            ])

            X_step[:, :11] = scaler.transform(X_step[:, :11])

            pred_step = np.clip(model.predict(X_step), 0.0, None)
            preds_matrix[:, h - 1] = pred_step

            for i, p in enumerate(pred_step):
                buffers[i].append(float(p))

            for i, idx in enumerate(valid_indices):
                sku, wh = series_keys[idx]
                daily_results.append({
                    "cutoff_date": cutoff_str,
                    "sku_id": sku,
                    "warehouse_id": wh,
                    "step": h,
                    "target_date": tgt_date.strftime("%Y-%m-%d"),
                    "actual": float(actuals_matrix[i][h - 1]),
                    "ridge_pred": float(pred_step[i]),
                    "baseline_pred": float(baselines[i]),
                })

        for i, idx in enumerate(valid_indices):
            sku, wh = series_keys[idx]
            series_df = series_groups[(sku, wh)]
            lead_time = pd.to_numeric(series_df["Supplier_Lead_Time_Days"], errors="coerce").dropna()
            if lead_time.empty or lead_time.nunique() != 1:
                raise ValueError(f"Supplier lead time must be present and constant for {sku} at {wh}.")
            lead_days = int(round(float(lead_time.iloc[0])))
            if not 1 <= lead_days <= HORIZON_DAYS:
                raise ValueError(f"Supplier lead time for {sku} at {wh} must be between 1 and {HORIZON_DAYS} days.")

            row = {
                "cutoff_date": cutoff_str,
                "sku_id": sku,
                "warehouse_id": wh,
                "lead_time_days": lead_days,
            }
            for horizon in (2, 7, 14):
                row[f"actual_{horizon}"] = float(np.sum(actuals_matrix[i][:horizon]))
                row[f"ridge_{horizon}"] = float(np.sum(preds_matrix[i, :horizon]))
                row[f"baseline_{horizon}"] = float(baselines[i] * horizon)
            row["actual_lead"] = float(np.sum(actuals_matrix[i][:lead_days]))
            row["ridge_lead"] = float(np.sum(preds_matrix[i, :lead_days]))
            row["baseline_lead"] = float(baselines[i] * lead_days)
            cumulative_results.append(row)
    return pd.DataFrame(daily_results), pd.DataFrame(cumulative_results)


def build_evaluation_report(
    daily_df: pd.DataFrame, cum_df: pd.DataFrame
) -> str:
    """Generate a beginner-friendly report from matching forecast/actual windows."""
    d1 = daily_df[daily_df["step"] == 1]
    d1_ridge_mae = float(np.mean(np.abs(d1["ridge_pred"] - d1["actual"])))
    d1_baseline_mae = float(np.mean(np.abs(d1["baseline_pred"] - d1["actual"])))
    d1_improvement = ((d1_baseline_mae - d1_ridge_mae) / d1_baseline_mae * 100) if d1_baseline_mae else 0.0

    horizons = {
        "2 days": ("ridge_2", "baseline_2", "actual_2"),
        "7 days": ("ridge_7", "baseline_7", "actual_7"),
        "14 days": ("ridge_14", "baseline_14", "actual_14"),
        "Each SKU–warehouse lead time": ("ridge_lead", "baseline_lead", "actual_lead"),
    }
    metrics = {}
    for label, (ridge_col, baseline_col, actual_col) in horizons.items():
        actual = cum_df[actual_col]
        ridge_error = cum_df[ridge_col] - actual
        baseline_error = cum_df[baseline_col] - actual
        ridge_mae = float(np.mean(np.abs(ridge_error)))
        baseline_mae = float(np.mean(np.abs(baseline_error)))
        metrics[label] = {
            "ridge_mae": ridge_mae,
            "baseline_mae": baseline_mae,
            "improvement": ((baseline_mae - ridge_mae) / baseline_mae * 100) if baseline_mae else 0.0,
            "ridge_rmse": float(np.sqrt(np.mean(ridge_error ** 2))),
            "baseline_rmse": float(np.sqrt(np.mean(baseline_error ** 2))),
            "ridge_bias": float(np.mean(ridge_error)),
            "baseline_bias": float(np.mean(baseline_error)),
        }

    metric_14 = metrics["14 days"]
    metric_lead = metrics["Each SKU–warehouse lead time"]
    lines = [
        "# Phase 2 Demand Forecasting: Model Evaluation Report", "",
        "- **Phase:** Phase 2 (Demand Forecasting)",
        "- **Prediction target:** `Units_Sold` (recorded sales used as a proxy for demand)",
        "- **Training period:** 2024-01-01 to 2024-10-31",
        "- **Forecast length:** Up to 14 days, generated recursively",
        "- **Forecast origins:** 7 dates in November and December 2024",
        f"- **Series per origin:** {cum_df['sku_id'].nunique() * cum_df['warehouse_id'].nunique():,} SKU–warehouse pairs",
        f"- **Evaluation windows:** {len(cum_df):,} overlapping pair/origin windows", "",
        "## Results in brief", "",
        "Ridge was compared with a simple rule that repeats the previous 7-day average each day. Results below describe this synthetic dataset and test period only.",
        "",
        f"- **Tomorrow's sales (MAE):** Ridge {d1_ridge_mae:.2f} units; baseline {d1_baseline_mae:.2f} units ({d1_improvement:+.1f}% lower error for Ridge).",
        f"- **14-day total demand (MAE):** Ridge {metric_14['ridge_mae']:.2f} units; baseline {metric_14['baseline_mae']:.2f} units ({metric_14['improvement']:+.1f}% lower error for Ridge).",
        f"- **At each pair's listed supplier wait (MAE):** Ridge {metric_lead['ridge_mae']:.2f} units; baseline {metric_lead['baseline_mae']:.2f} units ({metric_lead['improvement']:+.1f}% lower error for Ridge).", "",
        "## What the model uses", "",
        "- One global Ridge model is trained across the 50 SKUs and 5 warehouses.",
        "- Inputs are past sales (lags and rolling averages), cyclic calendar values, and SKU/warehouse identifiers.",
        "- Numeric inputs are standardized using training-period statistics; one-hot SKU and warehouse indicators are left unchanged.",
        "- Predictions are clipped at zero. Fractional expected units are kept during calculations and rounded only for display.",
        "- `Demand_Forecast`, `Inventory_Level`, `Order_Quantity`, `Stockout_Flag`, `Region`, and `Promotion_Flag` are not model inputs.",
        "- Because promotions are not inputs, the forecast does not adjust for promotion days.",
        "- Calendar cycles describe patterns in this one synthetic year; they do not establish repeatable yearly seasonality.", "",
        "## How the test works", "",
        "The model is trained on January 1 through October 31. At each listed forecast origin, only sales through that date are used as history. Later daily predictions are fed back as model inputs; actual sales within the forecast window are not used to make predictions.",
        "The forecast origins are 7 days apart while each forecast lasts 14 days, so windows overlap. These scores describe repeated forecasts from different dates, not independent experiments.", "",
        "## Daily error by forecast distance", "",
        "| Days ahead | Ridge MAE | Baseline MAE | Ridge RMSE | Baseline RMSE | MAE improvement |",
        "|---:|---:|---:|---:|---:|---:|",
    ]

    for step in range(1, HORIZON_DAYS + 1):
        step_df = daily_df[daily_df["step"] == step]
        ridge_error = step_df["ridge_pred"] - step_df["actual"]
        baseline_error = step_df["baseline_pred"] - step_df["actual"]
        ridge_mae = float(np.mean(np.abs(ridge_error)))
        baseline_mae = float(np.mean(np.abs(baseline_error)))
        ridge_rmse = float(np.sqrt(np.mean(ridge_error ** 2)))
        baseline_rmse = float(np.sqrt(np.mean(baseline_error ** 2)))
        improvement = ((baseline_mae - ridge_mae) / baseline_mae * 100) if baseline_mae else 0.0
        lines.append(f"| {step} | {ridge_mae:.2f} | {baseline_mae:.2f} | {ridge_rmse:.2f} | {baseline_rmse:.2f} | {improvement:+.1f}% |")

    lines.extend([
        "", "## Total-demand error by delivery window", "",
        "Each forecast total is compared with actual sales over the same number of days. The final row uses the supplier lead time listed for each SKU–warehouse pair.", "",
        "| Window | Ridge MAE | Baseline MAE | MAE improvement | Ridge RMSE | Baseline RMSE | Ridge bias | Baseline bias |",
        "|:---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for label, result in metrics.items():
        lines.append(
            f"| {label} | {result['ridge_mae']:.2f} | {result['baseline_mae']:.2f} | "
            f"{result['improvement']:+.1f}% | {result['ridge_rmse']:.2f} | "
            f"{result['baseline_rmse']:.2f} | {result['ridge_bias']:+.2f} | {result['baseline_bias']:+.2f} |"
        )

    lines.extend([
        "", "## Limits to keep in mind", "",
        "1. The data is synthetic. These results are not evidence of real-world forecast accuracy.",
        "2. The model predicts recorded sales as a proxy for demand, not independently measured customer demand.",
        "3. Recursive forecasts can carry earlier errors forward, though measured MAE does not have to rise at every step.",
        "4. Promotions are not modelled. Actual sales may differ on promotion days.",
        "5. The data contains one year only, so recurring annual patterns cannot be confirmed.",
        "6. The simulator must state its own inventory and disruption assumptions; this forecast does not predict disruptions.", "",
    ])
    return "\n".join(lines)

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2: Demand Forecasting with Ridge Regression.")
    parser.add_argument(
        "csv",
        type=Path,
        nargs="?",
        default=Path("Data/raw/supply_chain_dataset1.csv"),
        help="Path to the supply chain CSV (default: Data/raw/supply_chain_dataset1.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/forecast_evaluation.md"),
        help="Report path (default: reports/forecast_evaluation.md)",
    )
    args = parser.parse_args()

    if not args.csv.is_file():
        parser.error(f"Input CSV file not found: {args.csv}")

    print(f"Loading dataset from: {args.csv}")
    df = pd.read_csv(args.csv, low_memory=False)

    required_cols = {"Date", "SKU_ID", "Warehouse_ID", "Units_Sold", "Supplier_Lead_Time_Days"}
    missing = required_cols - set(df.columns)
    if missing:
        parser.error(f"Missing required columns in dataset: {missing}")

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values(["SKU_ID", "Warehouse_ID", "Date"]).reset_index(drop=True)

    print("Fitting OneHotEncoder on SKU_ID and Warehouse_ID...")
    encoder = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    encoder.fit(df[["SKU_ID", "Warehouse_ID"]])

    print(f"Building training matrix for dates through {TRAIN_END_DATE}...")
    X_train, y_train = build_training_matrix(df, encoder)
    print(f"Training set: {X_train.shape[0]:,} samples across {X_train.shape[1]} features.")

    print("Standardizing numeric features using training data only...")
    scaler = StandardScaler()
    X_train[:, :11] = scaler.fit_transform(X_train[:, :11])

    print("Fitting global Ridge Regression model (alpha=1.0)...")
    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)

    print("Executing 14-day recursive multi-step evaluation across test cutoff dates...")
    daily_df, cum_df = run_recursive_evaluation(df, model, encoder, scaler)
    print(f"Evaluation completed: {len(daily_df):,} daily step predictions and {len(cum_df):,} cumulative windows.")

    print(f"Generating evaluation report to: {args.output}")
    report_md = build_evaluation_report(daily_df, cum_df)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report_md, encoding="utf-8")
    print(f"Successfully generated Phase 2 evaluation report: {args.output}")


if __name__ == "__main__":
    main()
