# Run and deploy the website

Live site:
- **https://nea-winter-outlook.pages.dev**
- **https://nea-demand.amritphuyal.com.np** (custom domain)

How the pieces fit together: [architecture.md](architecture.md). What each page shows: [site.md](site.md).

## Commands

Run from the repository root.

| I want to… | Command |
|---|---|
| refresh the data the site shows | `uv run nea export` |
| work on the site, live reload | `cd site && npm run dev` → http://127.0.0.1:3000 |
| check the production build locally | `cd site && npm run build && npm run preview` → http://127.0.0.1:8788 |
| publish to Cloudflare | `cd site && npm run deploy` |
| fetch new data, forecast and publish (the daily routine) | `uv run nea ingest all && uv run nea forecast && (cd site && npm run deploy)` |

- `npm run deploy` exports the lake (`nea export`), builds, then uploads `site/dist/` as the **production** deployment, so both URLs update within seconds.
- `npm run preview` serves `dist/` the way Cloudflare does (clean URLs like `/map`). Stop it with `Ctrl+C`.
- First time on a new machine: `cd site && npm install`.
- `site/src/data/` (the Parquet snapshot) is not in git; it is rebuilt by `uv run nea export`, so run `uv run nea export` before `npm run dev` / `npm run build` (`npm run deploy` does it for you). Local databases, caches and logs (`*.sqlite`, `.wrangler/`, `.observablehq/cache/`, `*.log`) are ignored for the same reason: they change every run.

## Daily schedule (cron + Cronitor)

The daily routine runs on its own at **15:00 Nepal time** from the laptop's user crontab (`crontab -l` to see it, `crontab -e` to change it):

```cron
PATH=/home/fm-pc-lt-314/.local/bin:/usr/local/bin:/usr/bin:/bin
DISPLAY=:0
WAYLAND_DISPLAY=wayland-0
XDG_RUNTIME_DIR=/run/user/1000
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

0 15 * * * cronitor exec nea-daily-deploy "cd /home/fm-pc-lt-314/All_Repo/NEA_Demand_Forecast_Duck_DB && uv run nea ingest all && uv run nea forecast && cd site && npm run deploy" >> /home/fm-pc-lt-314/nea-deploy.log 2>&1
```

- **Why the variables at the top:** cron starts with an almost empty environment. `PATH` lets it find `uv`, `npm` and `cronitor`; the display variables let the NDOR fetcher open its headed Chrome on the desktop session.
- **Each step needs the previous one:** if ingest fails, forecast and deploy do not run, and the site keeps the last good data.
- **Output** goes to `~/nea-deploy.log`.
- **Needs:** laptop on and the user logged in to the desktop at 15:00. A missed run is not caught up later; the next one is the following day.

**Cronitor** tracks every run. `cronitor exec nea-daily-deploy …` reports start, finish, exit code and output to the monitor `nea-daily-deploy` (schedule `0 15 * * *`, timezone `Asia/Kathmandu`, 10 min grace). It alerts when a run fails, or when no run starts by 15:10. The CLI's API key is in `/etc/cronitor/cronitor.json`; history is on the Cronitor dashboard.

Run it by hand (real ingest and deploy, also reported to Cronitor):

```bash
cronitor exec nea-daily-deploy "cd ~/All_Repo/NEA_Demand_Forecast_Duck_DB && uv run nea ingest all && uv run nea forecast && cd site && npm run deploy"
```

To change the time, edit the cron line **and** the monitor's schedule in Cronitor, or Cronitor will report runs as late or missing.

## First publish (2026-10-26): the steps actually followed

1. **Install the site's tools:** `cd site && npm install`.
2. **Log in to Cloudflare:** `npx wrangler@4.152.0 login`. The browser opened; clicked **Allow** for the personal Cloudflare account (the one that already hosts `portfolio-amrit`).
3. **Create the Pages project:** `npm run project`. Result: "Successfully created the 'nea-winter-outlook' project".
4. **Opened https://nea-winter-outlook.pages.dev and got Error 522.** That is normal: the project existed but nothing had been uploaded yet.
5. **First upload:** `uv run nea export && cd site && npm run deploy`.
   - 91 files uploaded in about 4 s.
   - Preview link: `https://04494876.nea-winter-outlook.pages.dev`.
   - Production URL now served the site: `/`, `/sql` and the data files returned 200.
6. **The dashboard's Workers & Pages list showed only `portfolio-amrit`.** The list was stale; `npx wrangler@4.152.0 pages project list` showed both projects in the same account. Fix: click ↻ on the list or reload the page.
7. **Custom domain** (Cloudflare dashboard):
   1. Open **Workers & Pages** → **nea-winter-outlook** → **Custom domains**.
   2. Click **Set up a custom domain** and enter `nea-demand.amritphuyal.com.np`.
   3. Click **Continue**, then **Activate domain**.
   4. Wait for the status **Active**.

   `amritphuyal.com.np` already uses Cloudflare DNS, so Cloudflare added the `CNAME nea-demand → nea-winter-outlook.pages.dev` record and the HTTPS certificate itself.

**Why a hyphen:** the subdomain is `nea-demand`, not `nea_demand`, because certificate authorities refuse underscores in host names.

**Why `--branch production`:** the project's production branch is named `production` (step 3), and the deploy script always uploads to it. Without that flag, wrangler uses the git branch (`master`), Cloudflare treats the upload as a preview, and the custom domain does not change.

## When something goes wrong

| Symptom | Fix |
|---|---|
| `npm run deploy` says not logged in / authentication error | `cd site && npx wrangler@4.152.0 login` |
| "Project not found" | `cd site && npm run project` (once) |
| Error 522 on pages.dev | nothing deployed yet: `npm run deploy` |
| Project missing from the dashboard | reload the list; check with `npx wrangler@4.152.0 pages project list` |
| Custom domain stuck on *Pending* for more than 30 min | Cloudflare → `amritphuyal.com.np` → **DNS**: delete any old `nea-demand` record, then add the domain again from the Pages screen |
| Site shows old numbers | run `uv run nea export` before deploying; hard-reload the browser (`Ctrl+Shift+R`) |
| Cronitor alert: run missing | laptop was off, asleep or logged out at 15:00; run the routine by hand |
| Cronitor alert: run failed | read the end of `~/nea-deploy.log` (or the run output in Cronitor) for the step that failed |
| A chart or SQL query says it can't load DuckDB | DuckDB-WASM comes from cdn.jsdelivr.net; check that the network or browser isn't blocking it |
