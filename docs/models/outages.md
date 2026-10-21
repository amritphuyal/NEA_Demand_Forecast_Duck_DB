# Flood damage and outage adjustment

**Role:** add capacity loss that history has never seen to the import forecast. On **26 August 2026**, floods on the Bhotekoshi and Trishuli rivers destroyed or cut off about 480 MW (around 10% of national capacity) [1–3]. Every model learned from years without such a loss, so on its own it would under-forecast this winter's import.

## The register: `outages.json` → `silver.plant_outage`

A hand-kept, sourced list (`nea ingest outages`):

| Plant | MW | Status | Source |
|---|---|---|---|
| Rasuwagadhi | 111 | destroyed | [1][2] |
| Upper Trishuli 3A | 60 | destroyed | [1] |
| Trishuli | 24 | destroyed | [1][2] |
| Chilime | 22 | destroyed / buried | [1][2] |
| Langtang Khola | 20 | destroyed | [1][2] |
| Devighat | 14.1 | destroyed | [1][3] |
| Mailung Khola | 5 | destroyed | [1] |
| Solar plant, Nuwakot | 25 | destroyed | [1][3] |
| Plants cut off by destroyed lines/substations (incl. Sanjen) | ~230 | offline, return date unknown | [1] (Ghising: 230–235 MW) |
| Kulekhani I–III reservoir | (106 MW plant) | storage shortfall ≈ 22 GWh of winter energy | [4] |

Sources disagree on totals: 405–481 MW operating capacity knocked out (NEA 430, Energy Ministry 431.1, Ghising ~450 or 250 destroyed + 230 offline) [1–3]. The register follows Ghising's split because it separates destroyed from reconnectable capacity. Under-construction projects (Upper Trishuli 1 216 MW, Upper Trishuli 3B 37 MW, Langtang Bhote Koshi 120 MW, …) are listed by the sources but not in the register: they produced nothing before the flood, so they change nothing this winter.

## How the adjustment works

For each forecast month $m$:

$$\text{lost}_m = \sum_{\text{plants out in } m} \text{MW} \times f_{\text{kind}} \times 24 \times \text{days}_m \;+\; \text{reservoir shortfall}/4 \;\text{(Jan–Apr)}$$

- $f$ = dry-season output factor: run-of-river 0.35 (they produce under 40% of capacity in the dry season [5]), solar 0.18.
- **Kulekhani.** The reservoir was at 1,522.46 m on 12 Sep 2026, against a 1,527 m safe maximum, and falling 2–10 cm/day from round-the-clock running [4]. At about 3.1 GWh per metre (144.7 GWh/yr over ~46 m usable depth), being ~7 m short ≈ **22 GWh** less peak energy, spread over Jan–Apr.
- **Months with an export surplus absorb the loss first.** Adjusted import = base + max(0, lost − the same month's export last year). November usually exports about 490 GWh, so the loss only cuts exports; from January, every lost GWh becomes import.
- **Range:**
  - `yhat` and P90 assume everything in the register stays out all winter.
  - P10 assumes only **destroyed** plants stay out, with the cut-off 230 MW reconnected.

The result is stored as model `combo+outage` next to the unadjusted `combo` in `ml.forecasts`.

## Daily forecasts don't need it

Daily models use recent days as inputs (lags). Once the widget collects post-flood days, the lower generation level is already in the data. Adding the outage again would count it twice.

## Result (live run 2026-10-26)

| Month | Lost generation (all / destroyed only) | Usual export | Import base → adjusted (GWh) |
|---|---|---|---|
| Nov 2026 | 126 / 68 | 487 | 0 → 0 |
| Dec 2026 | 130 / 70 | 123 | 46 → 53 |
| Jan 2027 | 135 / 70 | 0 | 196 → **332** |
| Feb 2027 | 123 / 63 | 0 | 228 → **351** |
| Mar 2027 | 135 / 70 | 6 | 194 → **323** |
| Apr 2027 | 131 / 68 | 22 | 193 → **301** |

Jan–Apr import rises by about 60%, to 300–350 GWh/month: the level of winter 2023/24 (peak 340 GWh). India approved up to 654 MW for 18 h/day until 31 Dec 2026, about 355 GWh/month, with a review in December for January onward [6]. The adjusted forecast fits within that ceiling.

## Limits and upkeep

- The plant list and the 0.35 factor are estimates from news and a rule of thumb, not NEA plant data. The real loss could be ±30%.
- When NEA reports a plant or line restored, set its `expected_return` in `outages.json`, then run `nea ingest outages && nea forecast`.
- Under-construction delays (Upper Trishuli 1, etc.) raise import in **later** winters. Add them to the register once their commissioning dates are known.

## Sources

1. Spotlight Nepal, "Bhotekoshi flood: blow to hydropower sector", 2026-09-07: https://www.spotlightnepal.com/2026/09/07/bhotekoshi-flood-blow-hydropower-sector/
2. Kathmandu Post, "Flood damage to Nepal's hydropower sector could run into billions", 2026-08-30: https://kathmandupost.com/national/2026/08/30/flood-damage-to-nepal-s-hydropower-sector-could-run-into-billions
3. Mongabay, "Nepal's flood disaster puts its hydropower-first strategy, exports to the test", 2026-09: https://news.mongabay.com/2026/09/nepals-flood-disaster-puts-its-hydropower-first-strategy-exports-to-the-test/
4. Kathmandu Post, "Bhotekoshi floods push Kulekhani into continuous power generation", 2026-09-12: https://kathmandupost.com/national/2026/09/12/bhotekoshi-floods-push-kulekhani-into-continuous-power-generation
5. Kathmandu Post, "Power shortage continues as generation slumps", 2023-05-04: https://kathmandupost.com/national/2023/05/04/power-shortage-continues-as-generation-slumps
6. Al Jazeera, "India to supply Nepal electricity after floods wrecked hydropower projects", 2026-09-14: https://www.aljazeera.com/amp/news/2026/9/14/india-to-supply-nepal-electricity-after-floods-wrecked-hydropower-projects
