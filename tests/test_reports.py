from nea_forecast import reports

ROW_TABLE = """
###### **Capacity Balance in MW of FY 2082/83**

||~~Shrawan~~|<br>~~Bhadra~~|<br>~~Ashwin~~|<br>~~Kartik~~|<br>~~Mangshir~~|<br>~~Poush~~|<br>~~Magh~~|<br>~~Falgun~~|<br>~~Chaitra~~|<br>~~Baishakh~~|<br>~~Jestha~~|<br>~~Ashadh~~|<br>~~Average ~~|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|~~IMPORT~~|~~22~~|~~0~~|~~0~~|~~0~~|~~0~~|~~162~~|~~295~~|~~419~~|~~332~~|~~169~~|~~241~~|~~51~~|~~141~~|
|MONTHLY<br>~~NATIONAL~~<br>PEAK DEMAND|~~2323~~|~~2294~~|~~2418~~|~~1939~~|~~2183~~|~~2374~~|~~2256~~|~~2117~~|~~2266~~|~~2353~~|~~2387~~|~~2479~~|~~2282~~|
"""

COL_TABLE = """
**MONTHLY ENERGY GENERATION FY 2082/83 (MWh)**

|Month|Kaligandaki 'A'|Kulekhani I|
|---|---|---|
|Shrawan|1,000.5|200|
|Bhadra|1,100|0|
|Total|2,100.5|200|
"""

LDC = """
|**1**|**Annual System Peak Demand**|**3226 MW**|**2083-03-22**|
|2|Annual System Energy Demand|19077.95 GWh||
"""


def test_fy_from_key():
    assert reports.fy_from_key("annual-report-20252026") == "2082/83"
    assert reports.fy_from_key("annual-report-202122") == "2078/79"
    assert reports.fy_from_key("annual-report-2023") == "2079/80"  # published 2023 -> FY 2022/23
    assert reports.fy_from_key("yearly-summary-207980") == "2079/80"


def test_row_oriented_month_table():
    rows = reports.month_tables(ROW_TABLE, "k", "2082/83")
    peak = {r["bs_month"]: r["value"] for r in rows if "PEAK DEMAND" in r["series"]}
    assert peak[4] == 2323 and peak[3] == 2479 and len(peak) == 12  # Shrawan=4 .. Ashadh=3, Average dropped
    imp = [r for r in rows if r["series"] == "IMPORT"]
    assert {r["bs_month"]: r["value"] for r in imp}[10] == 295  # Magh
    assert rows[0]["title"] == "Capacity Balance in MW of FY 2082/83"


def test_column_oriented_month_table():
    rows = reports.month_tables(COL_TABLE, "k", "2082/83")
    kul = {r["bs_month"]: r["value"] for r in rows if r["series"] == "Kulekhani I"}
    assert kul == {4: 200, 5: 0}  # Total row dropped
    assert any(r["series"] == "Kaligandaki 'A'" and r["value"] == 1000.5 for r in rows)


def test_ldc_summary():
    got = reports.ldc_summary(LDC, "k", "2082/83")
    assert {(r["metric"], r["value"], r["unit"]) for r in got} == {
        ("annual system peak demand", 3226, "MW"), ("annual system energy demand", 19077.95, "GWh")}
    assert next(r for r in got if r["unit"] == "MW")["date_bs"] == "2083-03-22"


def test_gold_monthly_balance(tmp_path):
    from nea_forecast.lake import connect, upsert
    con = connect(tmp_path)
    upsert(con, "silver.report_monthly", reports.month_tables(ROW_TABLE, "k", "2082/83"),
           ("doc_key", "table_no", "series", "bs_month"))
    got = con.execute("select unit, national_demand, import from gold.report_monthly_balance "
                      "where fy='2082/83' and bs_month=10").fetchone()
    assert got == ("MW", 2256, 295)
