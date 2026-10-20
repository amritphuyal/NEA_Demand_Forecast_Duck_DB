# Literature review: what others use for load / import forecasting

Research date 2026-10-26. Verification: **[V]** page read, **[S]** search snippet only (abstract/listing), **[U]** not verifiable. Paywalled IJF papers were not read in full; claims about them come from abstracts and the authors' own blogs.

## 1. Nepal

| Study | Scope | Methods | Best result | Note |
|---|---|---|---|---|
| Kathmandu University, KUSET 2021 [1] [V] | Kathmandu Valley, short-term | time series, regression, ML, LSTM | LSTM, MAPE 1.56% | data size and other models' MAPE not reported |
| IEEE PES Nepal, RESSD-2022 [2] [V] | Kathmandu Valley | MLR vs LSTM | LSTM, MAPE 4.37% | winter (Nov–Feb) demand falls as minimum temperature rises: matches our EDA (Dec–Feb corr −0.24) |
| Pulchowk (IOE) master's thesis 2023 [3] [V] | national peak load | LSTM (32 units, 30-day lookback) vs 30-day weighted moving average | LSTM 2.950% vs **WMA 3.005%** | deep learning beat a moving average by **0.05 points** |
| Neupane, RESSD-2020 [4] [S] | national, long-term | regression, ARIMA, fuzzy | — | paywalled |
| Parajuli et al. 2014 [6] [S] | national energy | log-linear econometric (GDP, population) | — | |
| NEA Load Forecast 2014/15 [7] [U] | national, long-term | GDP-elasticity (~1.2 reported) | — | document host unreachable; figure unverified |
| NPC / IBN [9] [S] | national, long-term | IAEA MAED end-use | — | NPC vice-chair called NEA's forecast "linear" and based on suppressed demand [8] |

No published NEA **daily or monthly** forecasting method was found [U].

## 2. South Asia and hydro systems

- **India, CEA Electric Power Survey:** the partial end-use method (bottom-up plus time series) [11] [S]. The 19th EPS added an econometric projection on GDP, price and weather.
- **India, POSOCO/WRLDC:** day-ahead forecasts by day-of-week variation, about 10% day-ahead error, which drove reserve needs of 800–1000 MW [12] [S]. Forecast error turns directly into reserve and import cost.
- **Nepal's winter deficit:** run-of-river plants produce under 40% of capacity in the dry season, and only Kulekhani (92 MW) stores water [13] [S]. Imports were about a third of national need in 2018 [14] [S]. River discharge is therefore a physical driver of import.
- **Himalayan streamflow:** 7-day forecasts are skillful [15] [S], and persistence is a strong benchmark on snow-fed rivers [16] [S]. Global streamflow products were weak at Nepal run-of-river sites [17] [S]. Treat GloFAS as an index, not plant-level truth.
- No study was found that forecasts run-of-river generation or imports from discharge [U]. Our import-need model (demand − generation from discharge) is therefore our own design. It rests on the physics above and on our EDA (generation ~ discharge corr 0.82).

## 3. Competitions and benchmarks

- **Tao Hong's "vanilla benchmark":** multiple linear regression with a trend, calendar dummies, a cubic temperature polynomial and temperature × calendar interactions [19] [S]. It is the standard reference model in load forecasting.
- **GEFCom2012:** winners beat the benchmark by about 30%. Regression with temperature appears in every winning team. EDF's entry was a GAM (trend + temperature + calendar) [20][21] [S].
- **GEFCom2014 (probabilistic):** 1st a quantile GAM, 2nd semiparametric regression with temperature scenarios, 3rd MLR with temperature scenarios [22] [S].
- **GEFCom2017:** "simple_but_good" used quantile regression. 3rd place used an ensemble of gradient boosting, quantile random forest and neural networks [23] [S].
- **Hong on ARIMA/ETS** [24] [V]:
  - They have rarely been a main part of winning load models; ETS is competitive only very short-term.
  - Competitions supplied actual temperatures, which favours regression.
  - For ex-ante forecasts there is no solid evidence either way.
- **M4:** combinations of methods beat single methods, and pure ML lost to ARIMA/ETS [26] [S].
- **M5:** LightGBM ensembles won, but over about 42,840 series, not one short series [25] [S].
- **Deep learning vs simple models:**
  - Tree models beat deep learning on medium tabular data [27] [S].
  - A linear model (DLinear) beat Transformers on long-horizon benchmarks [28] [S].
  - On very small samples ML overfits and MLR holds up [29] [U].
- **Future weather:** forecasts with actual future temperature beat those without, but the gain shrinks once forecast temperature replaces actuals [30] [S]. Ex-ante evaluation is rarely done [31] [S].

## 4. Medium and long term

- Hyndman & Fan used semiparametric additive models (temperature, calendar, economic drivers), simulated temperature, and bootstrapped residuals for density forecasts of peak demand [32] [S].
- ETS and SARIMA are the standard monthly baselines in *Forecasting: Principles and Practice* [33] [U, background].
- GDP elasticity is the local practice in Nepal [7]. Our EDA measured an elasticity of 2.6 for 2013–2026.

## 5. Uncertainty

- Probabilistic forecasting is the community standard for planning [22][34] [S].
- Conformal prediction works on small data; adaptive versions handle time series, where the exchangeability assumption fails [35][36] [S].
- No NEA document requires prediction intervals [U]. Their value for import planning is our inference: import is bought ahead, so the planner needs a range, not just a point [12].

## 6. What we took from this

| Evidence | Our design choice |
|---|---|
| Nepal thesis: LSTM beats WMA by 0.05 pt [3]; DL loses on small tabular data [27][28] | no LSTM; 30-day WMA added as a baseline (same reference as [3]) |
| Vanilla benchmark, GEFCom winners [19][20][22] | ridge regression with calendar, nonlinear temperature (HDD/CDD), season × temperature, recency |
| Hong: ex-ante vs ex-post [24][30][31] | backtest with climatology (ex-ante) **and** actual weather (ex-post oracle), both reported |
| M4 combinations [26]; FPP ETS [33] | monthly: ETS baseline and an equal-weight combination |
| GEFCom2014+ probabilistic [22][34]; conformal [35][36] | P10/P90 intervals from split conformal on backtest residuals; coverage and pinball loss reported |
| M5 LightGBM [25] vs small data [29] | LightGBM kept only if > 5% better **and** the Diebold–Mariano test is significant |
| No published discharge→import model [U] | import need = demand − generation(discharge), compared with a direct model |

## Sources

1. KUSET 2021, Kathmandu Valley STLF: https://journals.ku.edu.np/kuset/article/view/97
2. IEEE PES Nepal, Kathmandu Valley multivariate: https://r10.ieee.org/nepal-pes/impact-analysis-of-short-term-electrical-demand-factors-using-multivariate-forecasting-approach-a-case-of-kathmandu-valley
3. Pulchowk thesis 2023 (peak load LSTM): https://elibrary.tucl.edu.np/items/b1a89a9a-4229-4858-a791-94ed7025aab7/full
4. RESSD-2020 optimal demand forecasting: https://r10.ieee.org/nepal-pes/ressd-2020-conference-publication/towards-sustainable-social-development-optimal-demand-forecasting
5. Timilsina, ARIMA on NEA consumption: https://tribhuvan.academia.edu/ArunTimilsina
6. Parajuli et al., econometric projection: https://agris.fao.org/search/ar/records/65dfef550f3e94b9e5ddbd33
7. NEA Load Forecast 2014/15 (unreachable): https://cms.nea.org.np/admin/assets/uploads/supportive_docs/LoadForecast2014_15.pdf
8. ShareSansar, NEA demand forecast to be reviewed: https://www.sharesansar.com/index.php/newsdetail/neas-energy-demand-forecast-will-be-reviewed-says-npc-vice-chair
9. Himalayan Times, demand 8,000 MW in 15 years: https://thehimalayantimes.com/ampArticle/150837
10. NEA association presentation 2025: https://neanepal.org.np/storage/news/2025/02/association-presentation_1739529705.pdf
11. CEA 20th Electric Power Survey: https://cea.nic.in/wp-content/uploads/notification/2023/02/Volume_I_Report_of_20th_Electric_Power_Survey.pdf
12. POSOCO, load forecasting and system operation: https://posoco.in/wp-content/uploads/2020/08/WRLDC-TP-005-APPLICATION-OF-LOAD-FORECASTING-TECHNIQUES-TO-INDIAN-POWER-SYSTEM-AND-CASE-STUDY-FOR-WESTERN-REGION-2002.pdf
13. Kathmandu Post 2023, generation slumps: https://kathmandupost.com/national/2023/05/04/power-shortage-continues-as-generation-slumps
14. Kathmandu Post 2018, imports up in winter: https://kathmandupost.com/money/2018/01/11/power-imports-up-20pc-as-winter-takes-its-toll
15. Hybrid RF/HBV streamflow, Beas and Sunkoshi: https://amrita.edu/?p=491748
16. Himalayan streamflow forecast benchmarking: https://impact.ornl.gov/en/publications/benchmarking-real-time-streamflow-forecast-skill-in-the-himalayan/
17. UBC thesis, global streamflow forecasts for Nepal run-of-river: https://open.library.ubc.ca/collections/24/items/1.0412874
18. TERI Bhutan hydropower forecasting pilot: https://teriin.org/project/development-hydropower-forecasting-system-framework-and-implementation-pilot-project
19. Vanilla benchmark described: https://arxiv.org/pdf/2501.10637 ; https://arxiv.org/pdf/2305.05575
20. GEFCom2012 overview: https://ideas.repec.org/a/eee/intfor/v30y2014i2p357-363.html
21. Nedellec, Cugliari, Goude (EDF GAM): https://people.bath.ac.uk/man54/SAMBa/ITTs/ITT2/EDF/ELFandbackcastingNedellecetal2014.pdf
22. Hong et al. 2016, GEFCom2014: https://ideas.repec.org/a/eee/intfor/v32y2016i3p896-913.html
23. GEFCom2017 winners: https://blog.drhongtao.com/2017/08/winning-teams-for-global-energy-forecasting-competition-2017.html
24. Hong, temperature-based vs time series models: https://blog.drhongtao.com/2018/12/temperature-based-models-vs-time-series-models.html
25. M5 accuracy results: https://pure.unic.ac.cy/en/publications/m5-accuracy-competition-results-findings-and-conclusions/
26. M4 summary (Uber): https://www.uber.com/blog/m4-forecasting-competition
27. Grinsztajn et al. 2022, trees vs deep learning on tabular data: https://arxiv.org/abs/2207.08815
28. Zeng et al. 2022, are Transformers effective: https://arxiv.org/pdf/2205.13504
29. Luu & Huynh 2026, small-data case study (no URL retrieved) [U]
30. Energy 2023, future temperature in load forecasting: https://iris.unitn.it/handle/11572/401109
31. Y. Li dissertation, ex-ante load forecasting: https://ninercommons.charlotte.edu/record/2203/files/Li_uncc_0694D_13259.pdf
32. Hyndman & Fan, long-term peak density forecasting: https://ideas.repec.org/p/msh/ebswps/2008-6.html
33. Hyndman & Athanasopoulos, FPP3: https://otexts.com/fpp3/
34. Hong & Fan 2016, probabilistic load forecasting review: https://ideas.repec.org/a/eee/intfor/v32y2016i3p914-938.html
35. UiT thesis, conformal prediction on load: https://munin.uit.no/bitstream/handle/10037/21914/thesis.pdf
36. Zaffran et al. 2022, adaptive conformal for time series: https://proceedings.mlr.press/v162/zaffran22a.html
37. Wang, Liu, Hong 2016, recency effect: https://ideas.repec.org/a/eee/intfor/v32y2016i3p585-597.html
