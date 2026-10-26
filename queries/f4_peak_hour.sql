-- Finding 4: national peak demand always falls in the evening.
-- Source: NDOR "Peak Time" field, 608 qa_ok days, Apr 2023 - Jan 2025.
SELECT hour(peak_time) AS peak_hour, count(*) AS days
FROM silver.nea_daily
WHERE qa_ok
GROUP BY 1
ORDER BY 1;
