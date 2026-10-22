# Website (Phase 4)

A static site for competition evaluators and enthusiasts: the story, the evidence, a map, and a SQL console. It is hosted free on Cloudflare Pages.

## How it works

```
DuckLake lake ──nea export──► site/src/data/*.parquet + manifest.json (0.7 MB snapshot)
                                   │  Observable Framework (npm run build)
                                   ▼
                              site/dist/ (static HTML/JS, 7.4 MB) ──wrangler──► Cloudflare Pages
                                   │  in the visitor's browser
                                   ▼
                              DuckDB-WASM runs SQL on the Parquet files → Observable Plot charts, Leaflet map, SQL explorer
```

- **One source of truth.** Every chart is a SQL query on the exported Parquet snapshot of the lake. Nothing is copied by hand into JSON, and the narrative text quotes numbers produced by `nea model` / `nea forecast`.
- **DuckDB-WASM is loaded from jsDelivr** (pinned `@duckdb/duckdb-wasm@1.29.0`). Its `.wasm` files are 35–40 MB, over Cloudflare's 25 MiB per-file limit, so the site can't host them itself. Framework's built-in `sql` blocks would bundle them, so the site uses a small client instead (`site/src/components/db.js`).
- **Read-only by construction.** Queries run in the browser on static files; there is no server, no database connection and no secrets.

## Pages

| Page | Shows |
|---|---|
| Overview (`index.md`) | the answer first: winter import outlook (models only vs with flood losses), key numbers, four-point story |
| Map | weather points, river points (basin outlets + plant sites), flood-damaged plants (approx. locations); click for latest values; history + GloFAS forecast per point |
| Data | snapshot contents, coverage timeline, daily energy balance, the four monthly import sources, annual history |
| Analysis | seasonality, calendar effects, temperature, river flow vs generation/import, growth and GDP elasticity |
| Models | ladder and selection rule, winter error by horizon, shipped models, weather-knowledge test, backtest vs actual, monthly hold-out |
| Forecast | live winter table, GloFAS river-flow forecast vs normal, flood register with sources, daily forecasts when available |
| SQL explorer | examples, free SQL, result table, quick chart, table list |
| Method & limits | pipeline, why these models, results, limits, credits |

## Commands

```bash
uv run nea export          # lake -> site/src/data (run after `nea forecast` / `nea model`)
cd site
npm install                # once
npm run dev                # live preview at http://127.0.0.1:3000
npm run build              # -> site/dist
npx wrangler@4.152.0 login # once: authorise your Cloudflare account in the browser
npm run deploy             # build + upload to Cloudflare Pages project "nea-winter-outlook"
```

Daily refresh: `nea ingest all && nea forecast && nea export`, then `cd site && npm run deploy`. Builds happen on the laptop because the lake lives there. The exported Parquet files are committed, so the site can also be rebuilt from git alone.

## Free-tier fit

- **Cloudflare Pages free:** 500 builds/month, unlimited static requests, ≤ 20,000 files and ≤ 25 MiB per file. The site has about 45 files; the largest self-hosted file is 5 MB.
- **Map tiles:** OpenStreetMap standard tiles, with attribution, which suits low traffic. For heavy traffic, switch the tile URL to a provider with a free key.
