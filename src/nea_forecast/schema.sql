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
