CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS bronze.ingest_log (
    source VARCHAR, key VARCHAR, url VARCHAR, status VARCHAR, sha256 VARCHAR, fetched_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS silver.nea_daily (
    date DATE, bs_date VARCHAR,
    nea_gen_mwh DOUBLE, nea_sub_gen_mwh DOUBLE, ipp_gen_mwh DOUBLE, import_mwh DOUBLE,
    total_available_mwh DOUBLE, export_mwh DOUBLE, net_met_mwh DOUBLE, interruption_mwh DOUBLE,
    deficit_mwh DOUBLE, requirement_mwh DOUBLE, net_exchange_india_mwh DOUBLE,
    peak_time TIME, peak_gen_mw DOUBLE, peak_import_mw DOUBLE, peak_availability_mw DOUBLE,
    peak_export_mw DOUBLE, peak_met_mw DOUBLE, peak_interruption_mw DOUBLE, peak_deficit_mw DOUBLE,
    peak_demand_mw DOUBLE, peak_net_exchange_india_mw DOUBLE,
    qa_ok BOOLEAN, source VARCHAR, source_url VARCHAR
);

CREATE TABLE IF NOT EXISTS silver.nea_document (
    key VARCHAR, category VARCHAR, title VARCHAR, published DATE,
    pdf_path VARCHAR, md_path VARCHAR, source_url VARCHAR
);

CREATE TABLE IF NOT EXISTS silver.weather_daily (
    date DATE, point VARCHAR, tmax_c DOUBLE, tmin_c DOUBLE, precip_mm DOUBLE
);

CREATE TABLE IF NOT EXISTS silver.river_discharge_daily (
    date DATE, point VARCHAR, discharge_m3s DOUBLE
);

CREATE TABLE IF NOT EXISTS silver.river_level_obs (
    station_id INTEGER, observed_at TIMESTAMP, name VARCHAR, basin VARCHAR, district VARCHAR,
    lat DOUBLE, lon DOUBLE, level_m DOUBLE, warning_level DOUBLE, danger_level DOUBLE, status VARCHAR
);

CREATE TABLE IF NOT EXISTS silver.dim_calendar (
    date DATE, bs_year INTEGER, bs_month INTEGER, bs_day INTEGER, bs_date VARCHAR, dow INTEGER,
    is_saturday BOOLEAN, is_holiday BOOLEAN, holiday_name VARCHAR, season VARCHAR, fiscal_year VARCHAR
);

-- Gold views. IF NOT EXISTS keeps every connect from writing a snapshot: DROP VIEW to change one.
CREATE VIEW IF NOT EXISTS gold.daily_features AS
WITH w AS (
    SELECT date,
           max(tmax_c) FILTER (point = 'kathmandu') AS tmax_ktm,
           max(tmin_c) FILTER (point = 'kathmandu') AS tmin_ktm,
           avg((tmax_c + tmin_c) / 2) FILTER (point <> 'kathmandu') AS tmean_terai,
           avg(precip_mm) AS precip_mm_avg
    FROM silver.weather_daily GROUP BY date),
q AS (SELECT date, sum(discharge_m3s) AS discharge_index, count(*) AS discharge_points
      FROM silver.river_discharge_daily GROUP BY date)
SELECT c.*, n.* EXCLUDE (date, bs_date, source, source_url), w.* EXCLUDE (date), q.* EXCLUDE (date)
FROM silver.dim_calendar c
LEFT JOIN silver.nea_daily n USING (date)
LEFT JOIN w USING (date)
LEFT JOIN q USING (date);

CREATE VIEW IF NOT EXISTS gold.monthly_summary AS
SELECT bs_year, bs_month, min(date) AS start_date, any_value(fiscal_year) AS fiscal_year,
       bool_or(season = 'winter') AS winter,
       count(requirement_mwh) AS days_reported,
       sum(requirement_mwh) AS requirement_mwh, sum(net_met_mwh) AS net_met_mwh,
       sum(nea_gen_mwh + nea_sub_gen_mwh + ipp_gen_mwh) AS domestic_gen_mwh,
       sum(net_exchange_india_mwh) AS net_exchange_india_mwh,
       max(peak_demand_mw) AS peak_demand_mw,
       avg(tmean_terai) AS tmean_terai, avg(discharge_index) AS discharge_index
FROM gold.daily_features
GROUP BY bs_year, bs_month;
