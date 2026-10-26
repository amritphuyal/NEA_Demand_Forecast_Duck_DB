-- Finding 5 (check the definition before quoting): energy recorded as "Interruption" in NDOR, by season.
-- Source: NDOR daily energy table, 608 qa_ok days, Apr 2023 - Jan 2025.
SELECT season,
       count(*)                                  AS days,
       round(avg(interruption_mwh) / 1000, 2)    AS interruption_gwh_per_day,
       round(sum(interruption_mwh) / 1000)       AS interruption_gwh_total
FROM gold.daily_features
WHERE qa_ok
GROUP BY season
ORDER BY season DESC;
