-- Finding 3: at the evening peak in winter, about 1 MW in 8 comes from India and about 1 in 10 is not supplied.
-- Source: NDOR peak table (MW at the time of national peak demand), 608 qa_ok days, Apr 2023 - Jan 2025.
-- Season: winter = November to April (Gregorian), summer = May to October.
-- Domestic supply at peak = peak generation - peak export. Not supplied = NDOR "Interruption" + "Deficit" at peak.
SELECT season,
       count(*)                                                                    AS days,
       round(avg(peak_demand_mw))                                                  AS peak_demand_mw,
       round(avg(peak_gen_mw - peak_export_mw))                                    AS domestic_mw,
       round(avg(peak_import_mw))                                                  AS import_mw,
       round(avg(peak_interruption_mw + peak_deficit_mw))                          AS not_supplied_mw,
       round(100 * avg(peak_import_mw / peak_demand_mw), 1)                        AS import_pct_of_peak,
       round(100 * avg((peak_interruption_mw + peak_deficit_mw) / peak_demand_mw), 1) AS not_supplied_pct_of_peak
FROM gold.daily_features
WHERE qa_ok AND peak_demand_mw > 0
GROUP BY season
ORDER BY season DESC;
