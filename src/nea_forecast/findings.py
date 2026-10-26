"""Headline findings: every SQL file in queries/ -> assets/findings.json (file -> rows), plus 3 charts at
1920x1080 for the README and the video. The numbers quoted anywhere outside the repo come from findings.json."""
import json
import textwrap
from decimal import Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # files only, no display
import matplotlib.dates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from nea_forecast.eda import _rows  # noqa: E402

QUERIES, OUT = Path("queries"), Path("assets")
INK, RIVER, IMPORT, MUTED = "#15202b", "#12828a", "#c8102e", "#8a99a6"
plt.rcParams.update({"font.size": 22, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": MUTED,
                     "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK, "text.color": INK})


def _figure(title: str, subtitle: str, source: str, left: float = 0.08):
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100)  # exactly 1920x1080, no tight bbox
    fig.text(0.05, 0.95, textwrap.fill(title, 58), fontsize=38, fontweight="bold", va="top", linespacing=1.15)
    fig.text(0.05, 0.80, textwrap.fill(subtitle, 110), fontsize=23, color="#4a5866", va="top")
    fig.text(0.05, 0.025, source, fontsize=17, color="#6b7a88")
    return fig, fig.add_axes((left, 0.13, 0.96 - left, 0.6))


def _save(fig, out: Path, name: str) -> str:
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.png", dpi=100, facecolor="white")
    plt.close(fig)
    return str(out / f"{name}.png")


def export_vs_winter_import(rows: list[dict], out: Path) -> str:
    fig, ax = _figure("Nepal's exports nearly tripled in three years. It still imports every winter.",
                      "GWh per Nepali fiscal year. Export: whole year. Import: Poush to Chaitra (mid-December to mid-April).",
                      "Source: Nepal Electricity Authority annual reports, monthly energy balance tables. Query: queries/f1_export_vs_winter_import.sql")
    x = range(len(rows))
    for off, key, color, label in ((-0.2, "export_gwh_year", RIVER, "Exported to India (year)"),
                                   (0.2, "import_gwh_poush_chaitra", IMPORT, "Imported from India (Poush to Chaitra)")):
        bars = ax.bar([i + off for i in x], [r[key] for r in rows], width=0.38, color=color, label=label)
        ax.bar_label(bars, labels=[f"{r[key]:,.0f}" for r in rows], padding=6, fontsize=24, fontweight="bold", color=color)
    ax.set_xticks(list(x), [f"FY {r['fy']}" for r in rows], fontsize=26)
    ax.set_ylabel("GWh")
    ax.legend(frameon=False, fontsize=24, loc="upper left")
    ax.grid(axis="y", color="#e3e8ec")
    ax.set_axisbelow(True)
    return _save(fig, out, "1_export_vs_winter_import")


def gen_vs_demand(rows: list[dict], out: Path) -> str:
    lo = min(rows, key=lambda r: r["domestic_gen_pct_of_demand"] if r["days"] >= 26 else 999)
    hi = max(rows, key=lambda r: r["domestic_gen_pct_of_demand"] if r["days"] >= 26 and r["month"].month == 7 else -1)
    fig, ax = _figure(f"Same grid, six months apart: plants met {lo['domestic_gen_pct_of_demand']:.0f}% of demand in "
                      f"{lo['month']:%b %Y} and {hi['domestic_gen_pct_of_demand']:.0f}% in {hi['month']:%b %Y}",
                      "Average GWh per day, by month. Gap above demand is exported. Gap below is imported or not supplied.",
                      "Source: Nepal Electricity Authority Daily Operational Reports, 608 checked days, Apr 2023 to Jan 2025. "
                      "Query: queries/f2_gen_vs_demand_monthly.sql")
    m = [r["month"] for r in rows]
    gen, dem = [r["domestic_gen_gwh_per_day"] for r in rows], [r["demand_gwh_per_day"] for r in rows]
    ax.fill_between(m, gen, dem, where=[g >= d for g, d in zip(gen, dem)], interpolate=True, color=RIVER, alpha=0.18)
    ax.fill_between(m, gen, dem, where=[g < d for g, d in zip(gen, dem)], interpolate=True, color=IMPORT, alpha=0.18)
    ax.plot(m, dem, color=INK, lw=4, label="Demand")
    ax.plot(m, gen, color=RIVER, lw=4, label="Domestic generation")
    for r, dy in ((lo, -6), (hi, 4)):
        ax.annotate(f"{r['domestic_gen_pct_of_demand']:.0f}% of demand", (r["month"], r["domestic_gen_gwh_per_day"]),
                    xytext=(0, dy * 10), textcoords="offset points", ha="center", fontsize=24, fontweight="bold",
                    color=IMPORT if r is lo else RIVER, arrowprops={"arrowstyle": "-", "color": MUTED})
    ax.set_ylabel("GWh per day")
    ax.set_ylim(0, max(gen + dem) * 1.15)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %Y"))
    ax.legend(frameon=False, fontsize=24, loc="upper left")
    ax.grid(axis="y", color="#e3e8ec")
    return _save(fig, out, "2_gen_vs_demand_monthly")


def evening_peak(rows: list[dict], hours: list[dict], out: Path) -> str:
    w = next(r for r in rows if r["season"] == "winter")
    h0, h1 = min(r["peak_hour"] for r in hours), max(r["peak_hour"] for r in hours) + 1
    fig, ax = _figure("Winter evenings: about 1 MW in 8 comes from India, and 1 in 10 is not supplied",
                      f"Average national peak demand in MW. The peak fell between {h0 - 12} and {h1 - 12} pm on all "
                      f"{sum(r['days'] for r in hours)} days.",
                      "Source: Nepal Electricity Authority Daily Operational Reports, peak-time table, Apr 2023 to Jan 2025. "
                      "Query: queries/f3_evening_peak_by_season.sql", left=0.17)
    labels = ["Winter\nNov to Apr" if r["season"] == "winter" else "Summer\nMay to Oct" for r in rows]
    left = [0] * len(rows)
    for key, color, name in (("domestic_mw", RIVER, "Nepal's own plants"), ("import_mw", IMPORT, "Imported from India"),
                             ("not_supplied_mw", MUTED, "Not supplied")):
        vals = [r[key] for r in rows]
        bars = ax.barh(labels, vals, left=left, color=color, height=0.55, label=name)
        if key == "domestic_mw":
            ax.bar_label(bars, labels=[f"{v:,.0f} MW" for v in vals], label_type="center", fontsize=24, fontweight="bold", color="white")
        left = [a + b for a, b in zip(left, vals)]
    for i, r in enumerate(rows):  # the two thin segments are named beside the bar, same way for both seasons
        ax.text(left[i] + 30, i, f"{r['import_mw']:,.0f} MW imported ({r['import_pct_of_peak']:.0f}%)\n"
                f"{r['not_supplied_mw']:,.0f} MW not supplied ({r['not_supplied_pct_of_peak']:.0f}%)",
                va="center", fontsize=23, linespacing=1.4)
    ax.invert_yaxis()
    ax.tick_params(axis="y", labelsize=28)
    ax.set_xlabel("MW at the national evening peak")
    ax.set_xlim(0, max(left) * 1.42)
    ax.legend(frameon=False, fontsize=22, loc="center left", bbox_to_anchor=(0.0, 0.5), ncol=3)  # sits in the gap between the bars
    assert abs(w["domestic_mw"] + w["import_mw"] + w["not_supplied_mw"] - w["peak_demand_mw"]) <= 2  # parts add up
    return _save(fig, out, "3_winter_evening_peak")


def run(con, out: Path = OUT, queries: Path = QUERIES) -> dict:
    num = lambda v: float(v) if isinstance(v, Decimal) else v  # DECIMAL results -> float for charts and JSON
    res = {p.stem: {"sql": p.as_posix(), "rows": [{k: num(v) for k, v in r.items()} for r in _rows(con, p.read_text())]}
           for p in sorted(queries.glob("*.sql"))}
    for k, v in res.items():
        print(f"✔ {k}: {len(v['rows'])} rows", flush=True)
    r = {k.split("_")[0]: v["rows"] for k, v in res.items()}
    charts = [export_vs_winter_import(r["f1"], out), gen_vs_demand(r["f2"], out), evening_peak(r["f3"], r["f4"], out)]
    for c in charts:
        print(f"✔ chart: {c}", flush=True)
    (out / "findings.json").write_text(json.dumps(res, indent=2, default=str) + "\n")
    print(f"✔ wrote {out / 'findings.json'}", flush=True)
    return res
