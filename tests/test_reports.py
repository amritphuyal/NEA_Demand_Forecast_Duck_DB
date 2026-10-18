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


MONTHS_HDR = "||Shrawan|Bhadra|Ashwin|Kartik|Mangshir|Poush|Magh|Falgun|Chaitra|Baishakh|Jestha|Ashadh|"
BALANCED = "\n".join([MONTHS_HDR, "|---" * 13 + "|",
                      "|IPP|" + "|".join(["1000"] * 12) + "|", "|IMPORT|" + "|".join(["300"] * 12) + "|",
                      "|EXPORT|" + "|".join(["100"] * 12) + "|",
                      "|MONTHLY NATIONAL PEAK DEMAND|" + "|".join(["1200"] * 11 + ["1500"]) + "|"])  # Ashadh broken


def test_gold_monthly_balance_keeps_only_balanced_months(tmp_path):
    from nea_forecast.lake import connect, upsert
    con = connect(tmp_path)
    upsert(con, "silver.report_monthly", reports.month_tables(BALANCED, "k", "2082/83"),
           ("doc_key", "table_no", "series", "bs_month"))
    got = dict(con.execute("select bs_month, national_demand from gold.report_monthly_balance").fetchall())
    assert len(got) == 11 and 3 not in got and got[10] == 1200  # Ashadh (3) fails 1000+300 = 1200+100


CHART = """<!-- Start of picture text -->
 3,000  2,500  - 2026* 2,803 3,826 10,825 1,171 18,624 2,479 3,226<br>2,479<br>2026*<br>2025 2,953 2,400 8,606 1,681 15,641 2,409 2,901<br>2,409
<!-- End of picture text -->
<!-- Start of picture text -->
 2,000 | 2022*  2021  2,804   148   3,093   2,806   8,851   1,482 |  1,482 | 2019  2548 ,  2190 ,  2813 , 551  7, 320  1, | 1,320
<!-- End of picture text -->"""


def test_energy_peak_history_validates_rows():
    got = {r["year"]: r for r in reports.energy_peak_history(CHART, "k")}
    assert set(got) == {2026, 2025, 2021}  # garbled 2019 row fails the sum check -> dropped
    assert got[2026]["fy"] == "2082/83" and got[2026]["import_gwh"] == 1171
    assert (got[2026]["national_peak_mw"], got[2026]["system_peak_mw"]) == (2479, 3226)
    assert got[2021]["total_gwh"] == 8851 and got[2021]["national_peak_mw"] == 1482 and got[2021]["system_peak_mw"] is None


def test_ldc_summary_2023_wording():
    md = "|Annual System  Peak Demand (11 July 2023)|2,171.15 MW|\n|Annual  National Peak Demand (01 June 2023)|1986.39|"
    got = {r["metric"]: (r["value"], r["unit"]) for r in reports.ldc_summary(md, "k", "2079/80")}
    assert got == {"annual system peak demand": (2171.15, "MW"), "annual national peak demand": (1986.39, "MW")}


def test_gold_annual_history_newest_report_wins(tmp_path):
    from nea_forecast.lake import connect, upsert
    con = connect(tmp_path)
    old = reports.energy_peak_history(CHART, "annual-report-202122")
    new = [{**r, "doc_key": "annual-report-20252026", "import_gwh": 9.0} for r in old if r["year"] == 2025]
    upsert(con, "silver.report_energy_history", old + new, ("doc_key", "year"))
    rows = dict(con.execute("select year, import_gwh from gold.annual_history").fetchall())
    assert rows[2025] == 9.0 and rows[2026] == 1171


def test_gold_prefers_ocr_table(tmp_path):
    from nea_forecast.lake import connect, upsert
    con = connect(tmp_path)
    text = reports.month_tables(BALANCED, "k", "2082/83")
    ocr_rows = [{**r, "table_no": 10174, "value": r["value"] * 2} for r in text]  # still balanced
    upsert(con, "silver.report_monthly", text + ocr_rows, ("doc_key", "table_no", "series", "bs_month"))
    assert con.execute("select national_demand, method from gold.report_monthly_balance where bs_month=10"
                       ).fetchone() == (2400, "ocr")
