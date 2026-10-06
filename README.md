# Resilio

Resilio is a personal project exploring how inventory data, demand forecasts, and disruption scenarios can help explain supply risk and compare possible responses.

## Current progress

Phase 1 (dataset audit) is complete. It documented synthetic artifacts including instantaneous replenishment in the recorded stock, a constant zero stockout flag, and leakage in the publisher's forecast column.

Phase 2 (demand forecasting) is complete for the prototype. A global Ridge Regression model predicts recorded sales (`Units_Sold`, used as a demand proxy) recursively, and its chronological evaluation compares it with a 7-day-average baseline.

Phases 3 and 4 (inventory simulation and response comparison) are implemented as a command-line backend. It forecasts one selected SKU–warehouse pair, rolls inventory forward, and compares normal conditions, a user-selected disruption, and a user-entered response. The local JSON API provides item choices, dataset summaries, historical series, forecasts, and scenario comparisons. The simulator does not use the dataset's unreliable historical inventory or order quantities. Starting stock and planned order size are required inputs because the dataset does not provide trustworthy values for those simulation inputs.

The simulator does not calculate financial costs: holding costs and shortage penalties are absent from the dataset. Its scenarios are demonstrations based on explicit user assumptions, not historical evidence or predictions of disruptions.

## Run the project

1. Download the CSV from Kaggle and place it under `Data/raw/`.
2. Install dependencies in your Python environment:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Run the dataset audit script:

   ```powershell
   python scripts/audit_dataset.py Data/raw/supply_chain_dataset1.csv
   ```
   Review `reports/data_audit.md`.

4. Run the Phase 2 demand forecasting and recursive evaluation script:

   ```powershell
   python scripts/forecast_demand.py Data/raw/supply_chain_dataset1.csv
   ```
   Review `reports/forecast_evaluation.md`.

5. Run the Phase 3–4 scenario simulator for a SKU and warehouse in the CSV. Supply the starting stock and planned order size; the CSV does not provide reliable values for these inputs:

   ```powershell
   python scripts/simulate_resilience.py --sku YOUR_SKU --warehouse YOUR_WAREHOUSE --opening-stock YOUR_STARTING_STOCK --order-units YOUR_ORDER_SIZE
   ```

   Replace the placeholders with the SKU, warehouse, starting stock, and planned order size you want to explore. Optional disruption and response settings are listed by `--help`. The script writes a forecast, daily inventory traces, and summaries for the normal, disruption, and response cases to `outputs/resilience_scenarios.json`.

6. Start the local API:

   ```powershell
   python scripts/resilio_api.py
   ```

   It listens on `http://127.0.0.1:8000` by default and provides `GET /api/health`, `/api/items`, `/api/overview`, `/api/history`, `/api/forecast`, and `POST /api/simulate`. The simulation request requires `sku_id`, `warehouse_id`, `opening_stock`, and `order_units`; optional fields are `demand_multiplier`, `delay_days`, `shipment_loss_fraction`, `extra_stock_units`, and `expedite_days`. It only listens on the local computer by default.

7. In a second terminal, serve the website from the project root:

   ```powershell
   python -m http.server 5500 --bind 127.0.0.1
   ```

   Open `http://127.0.0.1:5500/frontend/`. Keep both local servers running. The page includes visual dataset summaries, historical charts, the demand forecast, and a scenario comparison. Enter starting stock and planned order size yourself before running a scenario.

Do not commit downloaded raw data. The `.gitignore` excludes files in `Data/raw/` and all `*.csv` files.

## Planned direction

- Python for data analysis and machine learning.
- HTML, CSS, and JavaScript for the website.
- Demand forecasting and analytics feed a transparent inventory simulator for user-selected disruption scenarios.
- Scenario outputs are “what if” estimates, not predictions that a disruption will occur.
- The website uses HTML, CSS, and JavaScript. The owner approved the frontend phase; its single-page dashboard is in `frontend/`.

The plan can change if the dataset audit finds missing, inconsistent, or unusable fields.
