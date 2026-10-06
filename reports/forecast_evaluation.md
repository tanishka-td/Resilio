# Phase 2 Demand Forecasting: Model Evaluation Report

- **Phase:** Phase 2 (Demand Forecasting)
- **Prediction target:** `Units_Sold` (recorded sales used as a proxy for demand)
- **Training period:** 2024-01-01 to 2024-10-31
- **Forecast length:** Up to 14 days, generated recursively
- **Forecast origins:** 7 dates in November and December 2024
- **Series per origin:** 250 SKU–warehouse pairs
- **Evaluation windows:** 1,750 overlapping pair/origin windows

## Results in brief

Ridge was compared with a simple rule that repeats the previous 7-day average each day. Results below describe this synthetic dataset and test period only.

- **Tomorrow's sales (MAE):** Ridge 4.13 units; baseline 4.50 units (+8.3% lower error for Ridge).
- **14-day total demand (MAE):** Ridge 16.27 units; baseline 32.73 units (+50.3% lower error for Ridge).
- **At each pair's listed supplier wait (MAE):** Ridge 11.70 units; baseline 19.09 units (+38.7% lower error for Ridge).

## What the model uses

- One global Ridge model is trained across the 50 SKUs and 5 warehouses.
- Inputs are past sales (lags and rolling averages), cyclic calendar values, and SKU/warehouse identifiers.
- Numeric inputs are standardized using training-period statistics; one-hot SKU and warehouse indicators are left unchanged.
- Predictions are clipped at zero. Fractional expected units are kept during calculations and rounded only for display.
- `Demand_Forecast`, `Inventory_Level`, `Order_Quantity`, `Stockout_Flag`, `Region`, and `Promotion_Flag` are not model inputs.
- Because promotions are not inputs, the forecast does not adjust for promotion days.
- Calendar cycles describe patterns in this one synthetic year; they do not establish repeatable yearly seasonality.

## How the test works

The model is trained on January 1 through October 31. At each listed forecast origin, only sales through that date are used as history. Later daily predictions are fed back as model inputs; actual sales within the forecast window are not used to make predictions.
The forecast origins are 7 days apart while each forecast lasts 14 days, so windows overlap. These scores describe repeated forecasts from different dates, not independent experiments.

## Daily error by forecast distance

| Days ahead | Ridge MAE | Baseline MAE | Ridge RMSE | Baseline RMSE | MAE improvement |
|---:|---:|---:|---:|---:|---:|
| 1 | 4.13 | 4.50 | 5.21 | 5.66 | +8.3% |
| 2 | 4.22 | 4.52 | 5.31 | 5.66 | +6.6% |
| 3 | 4.22 | 4.52 | 5.32 | 5.72 | +6.6% |
| 4 | 4.23 | 4.56 | 5.33 | 5.76 | +7.1% |
| 5 | 4.06 | 4.34 | 5.07 | 5.46 | +6.3% |
| 6 | 4.33 | 4.72 | 5.41 | 5.92 | +8.3% |
| 7 | 4.10 | 4.58 | 5.28 | 5.85 | +10.5% |
| 8 | 4.19 | 4.61 | 5.29 | 5.82 | +9.2% |
| 9 | 4.16 | 4.67 | 5.26 | 5.91 | +10.9% |
| 10 | 4.24 | 4.74 | 5.37 | 6.05 | +10.5% |
| 11 | 4.25 | 4.78 | 5.34 | 6.08 | +11.1% |
| 12 | 4.08 | 4.60 | 5.13 | 5.83 | +11.3% |
| 13 | 4.28 | 4.92 | 5.39 | 6.24 | +13.1% |
| 14 | 4.15 | 4.98 | 5.35 | 6.31 | +16.6% |

## Total-demand error by delivery window

Each forecast total is compared with actual sales over the same number of days. The final row uses the supplier lead time listed for each SKU–warehouse pair.

| Window | Ridge MAE | Baseline MAE | MAE improvement | Ridge RMSE | Baseline RMSE | Ridge bias | Baseline bias |
|:---|---:|---:|---:|---:|---:|---:|---:|
| 2 days | 5.83 | 6.82 | +14.5% | 7.42 | 8.52 | -0.38 | -1.32 |
| 7 days | 11.36 | 16.84 | +32.6% | 14.33 | 20.98 | -0.85 | -6.56 |
| 14 days | 16.27 | 32.73 | +50.3% | 20.69 | 40.59 | -1.74 | -20.44 |
| Each SKU–warehouse lead time | 11.70 | 19.09 | +38.7% | 15.35 | 25.71 | -0.77 | -9.24 |

## Limits to keep in mind

1. The data is synthetic. These results are not evidence of real-world forecast accuracy.
2. The model predicts recorded sales as a proxy for demand, not independently measured customer demand.
3. Recursive forecasts can carry earlier errors forward, though measured MAE does not have to rise at every step.
4. Promotions are not modelled. Actual sales may differ on promotion days.
5. The data contains one year only, so recurring annual patterns cannot be confirmed.
6. The simulator must state its own inventory and disruption assumptions; this forecast does not predict disruptions.
