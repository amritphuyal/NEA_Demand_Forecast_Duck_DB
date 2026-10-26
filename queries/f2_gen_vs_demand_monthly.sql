-- Finding 2: the same grid makes far more than it needs in the monsoon and far less in late winter.
-- Source: NEA Daily Operational Reports (NDOR), 608 days that pass the energy-balance check (qa_ok), Apr 2023 - Jan 2025.
-- Domestic generation = NEA + NEA subsidiaries + independent power producers. Demand = NDOR "Energy Requirement".
-- Per-day averages, so months with missing report days still compare fairly.
SELECT date_trunc('month', date)::DATE                                                  AS month,
       count(*)                                                                         AS days,
       round(avg(requirement_mwh) / 1000, 1)                                            AS demand_gwh_per_day,
       round(avg(nea_gen_mwh + nea_sub_gen_mwh + ipp_gen_mwh) / 1000, 1)                AS domestic_gen_gwh_per_day,
       round(avg(import_mwh) / 1000, 1)                                                 AS import_gwh_per_day,
       round(avg(export_mwh) / 1000, 1)                                                 AS export_gwh_per_day,
       round(100 * sum(nea_gen_mwh + nea_sub_gen_mwh + ipp_gen_mwh) / sum(requirement_mwh)) AS domestic_gen_pct_of_demand
FROM gold.daily_features
WHERE qa_ok
GROUP BY 1
ORDER BY 1;
