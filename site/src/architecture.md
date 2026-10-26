---
toc: true
---

# How it works

How the data gets from the internet to a forecast and onto this page. Everything heavy runs on one laptop in Nepal. This site is static files: your browser downloads a small Parquet snapshot and runs SQL on it, so every chart is a query you can repeat in the [SQL explorer](./sql).

## 1. The whole system

```mermaid
flowchart TB
  subgraph S["1 · Sources"]
    direction LR
    nea["NEA website<br>daily / monthly / annual PDFs<br>homepage widget"]
    om["Open-Meteo<br>ERA5 weather<br>GloFAS river flow + forecast"]
    trade["India TradeStat · CERC<br>World Bank"]
    reg["outages.json<br>flood register, hand-kept"]
  end
  subgraph I["2 · Ingest: nea ingest all"]
    direction LR
    fetch["fetch.py<br>httpx, polite, retries<br>headless Chrome for NEA bot check"]
    parse["parsers<br>pdfplumber · RapidOCR · JSON"]
  end
  subgraph L["3 · DuckLake lakehouse (laptop)"]
    direction LR
    raw[("data/raw/<br>original files, never overwritten")]
    bronze[("bronze.ingest_log<br>what ran, status")]
    silver[("silver.*<br>clean tables")]
    gold[("gold.*<br>joined views")]
    ml[("ml.*<br>backtest metrics, forecasts")]
  end
  subgraph A["4 · Analyse and model"]
    direction LR
    eda["nea eda<br>→ docs/eda/"]
    model["nea model<br>backtest + model selection"]
    fc["nea forecast<br>live outlook"]
  end
  subgraph W["5 · Website"]
    direction LR
    exp["nea export<br>→ site/src/data/*.parquet"]
    build["Observable Framework<br>npm run build"]
    cf["Cloudflare Pages<br>static files"]
    br["visitor's browser<br>DuckDB-WASM · Plot · Leaflet"]
  end
  nea & om & trade --> fetch --> parse
  reg --> parse
  fetch --> raw
  parse --> silver
  parse --> bronze
  silver --> gold
  gold --> eda & model & fc
  model --> ml
  fc --> ml
  model -.->|selection.json| fc
  ml --> exp
  gold --> exp
  exp --> build --> cf --> br
```

- **Laptop does everything heavy.** It sits in Nepal because some government sites block foreign IPs.
- **The website has no server.** The browser downloads the Parquet snapshot and runs SQL on it with DuckDB-WASM. Every chart is one of those queries.

## 2. What runs when

```mermaid
flowchart TB
  cron(["cron on the laptop"])
  cron -->|daily 15:00| ing["nea ingest all<br>14 sources in order, only new data"]
  ing --> fc["nea forecast<br>writes run live-YYYYmmdd"]
  fc --> pub["npm run deploy<br>nea export, build, upload"]
  cron -->|Sunday 17:00| mt["nea maintain<br>flush inlined rows, merge small files,<br>expire snapshots > 30 days"]
  you(["you, by hand"])
  you -->|each May, or when models change| mdl["nea model<br>re-test and re-select models"]
  ing & fc & mt & mdl & pub --> logs[("data/logs/TIME-COMMAND.log<br>▶ start · ✔ done · ✖ FAILED per step")]
```

A failing step is logged and skipped; the other steps still run. The exact cron lines are in the repository's `docs/flow.md`.

## 3. One ingest step, in detail

```mermaid
sequenceDiagram
  participant C as nea ingest
  participant L as bronze.ingest_log
  participant W as source website
  participant R as data/raw
  participant S as silver table
  C->>L: which keys are already done?
  C->>W: fetch only new or failed keys
  W-->>C: PDF / JSON / HTML
  C->>R: save the original file
  C->>C: parse + quality check
  C->>S: upsert (delete + insert, one transaction)
  C->>L: log ok, or parse_error (retried next run)
```

`ok` is written only after the table write commits, so a crash mid-run is simply redone next time.

## 4. How a forecast is generated

```mermaid
flowchart TB
  subgraph T["nea model (testing)"]
    direction LR
    bt["rolling-origin backtest from 2024-05<br>baselines · ridge · LightGBM"]
    sel["winter MAE + Diebold–Mariano test<br>→ simplest model within 5% of the best"]
    bt --> sel
  end
  subgraph F["nea forecast (live)"]
    direction LR
    feat["features<br>trend, month, weekday, holidays,<br>heating / cooling degree-days,<br>river-flow anomaly"]
    m["selected models<br>daily: ridge / naive<br>monthly: combo of growth-naive, OLS, ETS"]
    iv["P10–P90 range<br>from recent out-of-sample errors"]
    imp["import need =<br>demand − domestic generation"]
    adj["+ flood losses<br>(combo+outage)"]
    feat --> m --> iv --> imp --> adj
  end
  gold[("gold.*")] --> bt
  gold --> feat
  clim["2010–2022 weather averages"] --> feat
  glo[("GloFAS river forecast")] --> feat
  sel -->|selection.json| m
  out[("silver.plant_outage")] --> adj
  adj --> mlf[("ml.forecasts")]
```

Model details and why each was chosen: the [Models](./models) and [Method & limits](./method) pages, and `docs/models/` in the repository.
