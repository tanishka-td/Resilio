# Dataset Audit Report: Supply Chain Inventory Candidate

- **File:** `supply_chain_dataset1.csv`
- **Rows:** 91,250
- **Columns:** 15
- **Exact duplicate rows:** 0
- **Rows with at least one missing value:** 0

## 1. Executive Summary & Verdict

> [!IMPORTANT]
> **Audit Verdict: Demonstration / Prototype Use Only (With Identified Caveats)**
> 
> This dataset is synthetic and demonstrates basic schema elements, but it exhibits several critical synthetic generation artifacts:
> 1. **Instantaneous Replenishment (0 Lead Time in Practice):** 100.0% (91,000/91,000) of inventory transitions follow the exact formula `Inventory_Level[t] = Inventory_Level[t-1] - Units_Sold[t] + Order_Quantity[t]`. Replenishment orders arrive the exact same day they are ordered, completely ignoring `Supplier_Lead_Time_Days` (which ranges from 2 to 14 days).
> 2. **Zero Stockout Events:** `Stockout_Flag` is constant `0` across all rows. The minimum inventory level observed is `168`, meaning the synthetic inventory buffer was never depleted.
> 3. **Synthetic Circularity / Data Leakage in `Demand_Forecast`:** The `Demand_Forecast` column has an extreme correlation (0.949) with same-day `Units_Sold`, constructed as `Units_Sold + Normal(0, ~3)`. It is not an authentic forward-looking operational forecast and cannot be used as an input feature for predictive modeling.
> 4. **Random Geographic Assignment:** Warehouses do not reside in a single geographic `Region`. Each warehouse's recorded region switches randomly day by day (~25% in East, North, South, West).
> 5. **Truncated Leap Year Calendar:** Contains exactly 365 days (2024-01-01 to 2024-12-30), omitting December 31, 2024.

## 2. Column Overview

| Column | Type | Missing | Unique | Example values |
|---|---|---:|---:|---|
| `Date` | str | 0 | 365 | '2024-01-01', '2024-01-02', '2024-01-03' |
| `SKU_ID` | str | 0 | 50 | 'SKU_1', 'SKU_1', 'SKU_1' |
| `Warehouse_ID` | str | 0 | 5 | 'WH_1', 'WH_1', 'WH_1' |
| `Supplier_ID` | str | 0 | 10 | 'SUP_8', 'SUP_8', 'SUP_8' |
| `Region` | str | 0 | 4 | 'West', 'West', 'North' |
| `Units_Sold` | int64 | 0 | 58 | 10, 17, 35 |
| `Inventory_Level` | int64 | 0 | 781 | 592, 575, 540 |
| `Supplier_Lead_Time_Days` | int64 | 0 | 13 | 14, 14, 14 |
| `Reorder_Point` | int64 | 0 | 142 | 379, 379, 379 |
| `Order_Quantity` | int64 | 0 | 301 | 0, 0, 0 |
| `Unit_Cost` | float64 | 0 | 230 | 13.95, 13.95, 13.95 |
| `Unit_Price` | float64 | 0 | 227 | 20.48, 20.48, 20.48 |
| `Promotion_Flag` | int64 | 0 | 2 | 0, 0, 1 |
| `Stockout_Flag` | int64 | 0 | 1 | 0, 0, 0 |
| `Demand_Forecast` | float64 | 0 | 4,736 | 8.52, 18.63, 39.62 |

## 3. Constant or Single-Value Columns

`Stockout_Flag`

> [!WARNING]
> `Stockout_Flag` is always zero, so it cannot be used to train a stockout classifier on this dataset.

## 4. Date Range & Time Horizon Coverage

- **Column:** `Date`
- **Valid date entries:** 91,250 of 91,250
- **Date range:** `2024-01-01` to `2024-12-30` (365 calendar days span)
- **Unique dates present:** 365
- **Continuity:** Continuous daily records across the span.
- **Note on calendar year:** 2024 was a leap year (366 days). The dataset ends on `2024-12-30`, missing `2024-12-31`.

## 5. Entity Coverage & Hierarchy

- **SKUs:** 50
- **Warehouses:** 5
- **Total SKU-Warehouse series:** 250 (expected 250)
- **Records per series:** Min = 365, Max = 365 (Balanced panel)
- **Suppliers:** 10
- **Supplier assignment:** Fixed per SKU-Warehouse pair (1 unique supplier per pair).

### Warehouse-to-Region Mapping Anomaly
In physical logistics, a warehouse operates within a fixed geographic region. However, in this dataset, records for each warehouse are uniformly distributed across all regions:

| Warehouse_ID   |   East |   North |   South |   West |
|:---------------|-------:|--------:|--------:|-------:|
| WH_1           |   4610 |    4685 |    4497 |   4458 |
| WH_2           |   4550 |    4518 |    4581 |   4601 |
| WH_3           |   4677 |    4583 |    4480 |   4510 |
| WH_4           |   4553 |    4609 |    4607 |   4481 |
| WH_5           |   4544 |    4579 |    4555 |   4572 |

> [!NOTE]
> `Region` varies randomly day to day for every warehouse. It should not be treated as a physical warehouse location in routing or disruption models.

## 6. Demand & Sales Analysis

- **Units Sold Summary:** Mean = 20.05, Std = 9.07, Min = 0, Max = 59
- **Promotion association:** Sales averaged 24.91 units on promotion days and 19.50 units otherwise. This difference does not establish causation.
- **Average sales by weekday:** 19.99 to 20.11 units.
- **Monthly pattern:** Highest average sales were in March (29.9); lowest were in September (10.2). One year does not establish recurring seasonality.

### Demand Forecast Column Integrity
- **Correlation (`Demand_Forecast` vs `Units_Sold`):** 0.9493
- **Error (`Demand_Forecast` - `Units_Sold`):** Mean = 0.027, Std = 2.987, Min = -13.00, Max = 14.08
- **Finding:** `Demand_Forecast` behaves as same-day actual sales perturbed by Gaussian noise ~ $\mathcal{N}(0, 3)$. It must **not** be used as a predictor variable in time-series models due to target leakage.

## 7. Inventory Plausibility & Balance Verification

### Stock Balance Equation
We tested the standard conservation of inventory balance:
$$\text{Inventory}_t = \text{Inventory}_{t-1} - \text{Units Sold}_t + \text{Order Received}_t$$

- **Tested Transitions:** 91,000
- **Exact Matches:** 91,000 (100.00%)
- **Mismatches:** 0

### Reorder Policy Trigger Mechanism
- **Trigger Rule Tested:** `Inventory[t-1] <= Reorder_Point`
- **Total Times Threshold Met:** 5,027
- **Threshold events followed by an order:** 5,027 (100.0%)
- **Orders placed above the threshold:** 0 (0.0%)
- **Recorded order sizes:** 200 to 499 units (mean 349.8).

### Supplier Lead Time Decoupling
- In the dataset, `Supplier_Lead_Time_Days` ranges from 2 to 14 days (Mean = 8.0 days).
- **Critical Finding:** Orders placed on day $t$ enter available inventory on day $t$ without delay. The synthetic data generator recorded lead times as metadata, but executed replenishment with **zero latency**.

## 8. Pricing & Margins Summary

- **Unit Cost:** Min = $5.02, Mean = $12.20, Max = $19.76
- **Unit Price:** Min = $6.95, Mean = $18.26, Max = $35.10
- **Gross Margin %:** Min = 16.7%, Mean = 32.4%, Max = 44.4% (No negative margin rows)
- Pricing and cost values are fixed per SKU-Warehouse pair across the entire year.

## 9. Numeric Column Distributions

|                         |   count |    mean |     std |    min |    25% |    50% |    75% |    max |
|:------------------------|--------:|--------:|--------:|-------:|-------:|-------:|-------:|-------:|
| Units_Sold              |   91250 |  20.055 |   9.069 |   0    |  13    |  20    |  27    |  59    |
| Inventory_Level         |   91250 | 471.522 | 133.488 | 168    | 370    | 461    | 564    | 990    |
| Supplier_Lead_Time_Days |   91250 |   7.984 |   3.908 |   2    |   4    |   8    |  11    |  14    |
| Reorder_Point           |   91250 | 300.068 |  54.88  | 201    | 252    | 300    | 346    | 398    |
| Order_Quantity          |   91250 |  19.272 |  82.341 |   0    |   0    |   0    |   0    | 499    |
| Unit_Cost               |   91250 |  12.203 |   4.575 |   5.02 |   8.18 |  11.99 |  16.32 |  19.76 |
| Unit_Price              |   91250 |  18.262 |   7.121 |   6.95 |  12    |  18.18 |  23.39 |  35.1  |
| Promotion_Flag          |   91250 |   0.102 |   0.302 |   0    |   0    |   0    |   0    |   1    |
| Stockout_Flag           |   91250 |   0     |   0     |   0    |   0    |   0    |   0    |   0    |
| Demand_Forecast         |   91250 |  20.082 |   9.504 |   0    |  12.95 |  19.95 |  26.93 |  61.42 |

## Review before using this data

This report is an initial structural check, not proof that the data is accurate. Confirm what each field means, whether each row represents a day/item/location, whether inventory values are opening or closing stock, and whether sales can be lower than true demand during stockouts. Check that related rows form sensible inventory balances.


## 10. Implications & Recommendations for Resilio

In accordance with project guidance (`AGENTS.md` and `README.md`):

### What This Dataset Can Support
- **Demand Forecasting Prototyping:** `Units_Sold` has observed variation within this synthetic year and can be used to compare simple chronological forecasts.
- **UI & Dashboard Wireframing:** Provides structured multi-entity hierarchy (50 SKUs, 5 Warehouses, 10 Suppliers) suitable for designing tables, inventory cards, and scenario dropdowns.

### What This Dataset Cannot Support As-Is
- **Real-World Evidence:** The publisher states this is synthetic, and our audit confirms synthetic artifacts (0 lead time, uniform random reorder quantities, random warehouse regions). Results must never be presented as empirical supply-chain evidence.
- **Disruption Analysis on Historical Inventory:** Because historical stock never dropped below 168 and replenishment was instantaneous, historical stockout metrics cannot validate disaster or lead-time disruption models.
- **Using `Demand_Forecast` as an ML Feature:** Due to synthetic target leakage, this column must be excluded from feature pipelines.

### Recommended Architecture for Resilio
1. **Use Demand for Forecasting:** Train forecasting models on past `Units_Sold` and carefully chosen calendar features. Promotion data is excluded from the current Phase 2 model.
2. **Simulate Inventory Dynamically:** Do not trust the synthetic CSV `Inventory_Level`; calculate forward inventory with explicit rules and selected lead-time or supply scenarios, and label any shortages as simulated outcomes.
3. **Clearly Label Assumptions:** Document that the raw Kaggle dataset is demonstration data, with inventory simulation powered by Resilio's internal logic.
