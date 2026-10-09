# Resilio

### Ready for what shifts.

[Open the live demo](https://resilio-peha.onrender.com)

Resilio is a small interactive project about supply chains and the choices people make when plans change. It brings demand signals, a short forecast, and inventory what-ifs into one visual dashboard.

## Explore

- Browse sales patterns across items and warehouses.
- See a 14-day demand projection for a selected item and location.
- Change demand, delivery delay, or shipment loss.
- Compare the disruption with a response, such as preparing extra stock or expediting delivery.

## Run it on your computer

You’ll need Python 3.10 or newer.

```powershell
python -m pip install -r requirements.txt
python scripts/resilio_api.py
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000). The demo data is included, so there’s no separate download step.

## How it’s built

The dashboard uses HTML, CSS, and JavaScript. Python serves the site and API, prepares the data with Pandas and NumPy, and uses scikit-learn for the Ridge regression forecast and supporting preprocessing.

## A note about the results

This is a learning demo, not a live supply-chain planning system. Recorded sales are used as a demand proxy. Starting stock and planned order size are entered by the user; disruption scenarios are chosen what-ifs, not predictions. The project does not calculate financial costs.

## What’s next

I’d like to add a guided way for people to explore their own data, including CSV, Excel, database, or manual input. That feature isn’t built yet.

Questions, ideas, and kind bug reports are welcome.
