-- Finding 1: Nepal exports more every year, but still imports every winter.
-- Source: NEA annual reports, monthly energy balance tables (GWh), read by `nea ingest docs reports ocr`
--         into gold.report_monthly_balance. bs_month is Baishakh = 1 ... Chaitra = 12; the fiscal year starts in Shrawan (4).
-- Poush to Chaitra (bs_month 9-12) is about mid-December to mid-April.
-- Only complete fiscal years (12 months): FY 2078/79 lacks Falgun in the parsed table, so it is left out.
SELECT fy,
       count(*)                                                 AS months,
       round(sum(export))                                       AS export_gwh_year,
       round(sum(import) FILTER (WHERE bs_month IN (9, 10, 11, 12))) AS import_gwh_poush_chaitra,
       round(sum(import))                                       AS import_gwh_year,
       round(sum(national_demand))                              AS demand_gwh_year
FROM gold.report_monthly_balance
WHERE unit = 'GWh'
GROUP BY fy
HAVING count(*) = 12
ORDER BY fy;
