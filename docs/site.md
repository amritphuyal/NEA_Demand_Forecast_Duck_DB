# Website (Phase 4)

A static site for competition evaluators and enthusiasts: the story, the evidence, a map, and a SQL console. It is hosted free on Cloudflare Pages.

- **Run and deploy commands, and the first-publish record:** [deploy.md](deploy.md).
- **Architecture diagrams:** [architecture.md](architecture.md).

## How it works

```
DuckLake lake ──nea export──► site/src/data/*.parquet + manifest.json (0.7 MB snapshot)
                                   │  Observable Framework (npm run build)
                                   ▼
                              site/dist/ (static HTML/JS, ~51 MB, mostly Mermaid chunks loaded only on How it works) ──wrangler──► Cloudflare Pages
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
| How it works | the architecture diagrams from `docs/architecture.md` (Mermaid; edit both copies) |
| Map | weather points, river points (basin outlets + plant sites), flood-damaged plants (approx. locations); click for latest values; history + GloFAS forecast per point |
| Data | snapshot contents, coverage timeline, daily energy balance, the four monthly import sources, annual history |
| Analysis | seasonality, calendar effects, temperature, river flow vs generation/import, growth and GDP elasticity |
| Models | ladder and selection rule, winter error by horizon, shipped models, weather-knowledge test, backtest vs actual, monthly hold-out |
| Forecast | live winter table, GloFAS river-flow forecast vs normal, flood register with sources, daily forecasts when available |
| SQL explorer | examples, free SQL, result table, quick chart, table list |
| Method & limits | pipeline, why these models, results, limits, credits |

## Commands

See [deploy.md](deploy.md).

## Free-tier fit

- **Cloudflare Pages free:** 500 builds/month, unlimited static requests, ≤ 20,000 files and ≤ 25 MiB per file. The site has about 150 files; the largest self-hosted file is under 5 MB.
- **Map tiles:** OpenStreetMap standard tiles, with attribution, which suits low traffic. For heavy traffic, switch the tile URL to a provider with a free key.

## Custom domain

`nea-demand.amritphuyal.com.np`, set up from the Pages dashboard: see [deploy.md](deploy.md#first-publish-2026-10-26-the-steps-actually-followed).
