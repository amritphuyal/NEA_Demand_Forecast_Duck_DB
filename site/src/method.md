---
toc: true
---

# Method & limits

How the numbers on this site were produced, why these choices were made, and what they can't tell you. The full write-ups, with equations and 37 cited sources, are in the project repository under `docs/models/`.

## Pipeline

1. **Collect** (plain Python, no AI):
   - NEA daily operational reports (PDF)
   - NEA monthly and annual reports (PDF → tables, OCR where tables are images)
   - the NEA homepage widget
   - ERA5 weather, GloFAS river flow and its forecast
   - India customs trade and the CERC power-exchange report
   - World Bank GDP
   - a sourced register of flood-damaged plants
2. **Store** in a DuckLake lakehouse (Parquet + DuckDB). Raw files are kept, every fetch is logged, and the store is time-travel queryable.
3. **Analyse:** seasonality, temperature, river flow, growth, and the agreement between sources (the [Analysis](./analysis) page).
4. **Model:** a rolling-origin backtest, then model selection, then P10–P90 ranges (the [Models](./models) page).
5. **Forecast:** daily 1–30 days and a monthly winter outlook, adjusted for flood losses (the [Forecast](./forecast) page).
6. **Publish:** the lake is exported to Parquet, and this static site queries it in your browser with DuckDB-WASM (the [SQL explorer](./sql)).

## Why these models

- **Simple first, complex only if proven.** In international load-forecasting competitions (GEFCom 2012/2014/2017), regression with temperature and calendar terms appears in every winning entry. Our ridge model is that, adapted to Nepal: two temperature regions, Nepali holidays, river flow.
- **No deep learning.** We have two winters of daily data. A Nepal peak-load study found LSTM beat a 30-day moving average by only 0.05 percentage points. Tree models and even linear models beat deep networks on data this size.
- **Honest testing.**
  - Every forecast is made only from data available at the time.
  - Future weather comes from the long-term average, not the actual weather.
  - The backtest scores **winter** error separately.
  - A Diebold–Mariano test guards against "better by luck".
- **Ranges, not just numbers.** P10–P90 bands come from each model's own recent out-of-sample errors. Their coverage is reported, including where it misses.

## Results in one line each

- **Daily demand:** 2.5% error next day, 5–8% at 30 days (baseline: 3.0% → 12.5%).
- **Daily peak:** 2.4% next day (a Nepal LSTM study: 2.95%).
- **Monthly winter demand:** 3–6.5% error per month, forecast 5–10 months past the last published NEA figure.
- **Winter 2026/27 import:** about 300–350 GWh/month in Jan–Apr after flood losses (about 200 without).

## Limits

- **One test winter for daily models** (Nov 2024 – Jan 2025), because NEA stopped publishing daily reports in January 2025. Treat daily error figures as indicative.
- **The flood adjustment uses estimates:** plant lists from news reports, and a rule-of-thumb dry-season output of 35%. It could be off by ±30%.
- **GloFAS is a global model** (~5 km grid), used as a basin-scale signal, not plant-level truth.
- **Not modelled:** India-side supply limits and prices, and new plant commissioning dates.
- **Plant locations on the map are approximate** (valley level).

## Data credits

- **Nepal Electricity Authority:** reports and website.
- **Open-Meteo** (CC BY 4.0): ERA5 reanalysis (ECMWF) and GloFAS river flow (Copernicus).
- **Other data:** World Bank, India Ministry of Commerce (TradeStat), CERC.
- **Flood damage reporting:** Kathmandu Post, Spotlight Nepal, Mongabay, Al Jazeera.
- **Inspiration:** the NDOR scraping idea came from [nea-data-warehouse](https://github.com/Unknown-333/nea-data-warehouse) by Aayush Paudel.

This is an educational, non-commercial project.
