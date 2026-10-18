from nea_forecast import ocr

FY_MONTHS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]


def boxes(lines):
    """Fake OCR output: one box per token, y jitters a little like real OCR."""
    out = []
    for i, line in enumerate(lines):
        for j, tok in enumerate(line.split()):
            out.append((j * 50.0, i * 30.0 + (3 if j % 2 else 0), 20.0, tok))
    return out


MW = boxes([
    "Capacity Balance MW of FY 2080/81",
    "2400.00 2500.00 INTERRUPTION",  # chart axis noise: < 12 numbers
    "IPP 1114 1181 1211 1201 858 652 509 493 543 603 995 1398 897",
    "SUBSIDIARY 536 539 538 471 450 511 345 385 481 477 519 538 483",
    "PROR 417 394 434 425 425 415 321 390 374 390 390 415 399",
    "IMPORT 27 56 21 0 0 22 472 353 141 281 55 0 119",
    "STORAGE 51 67 97 17 97 100 92 19 82 99 101 65 74",
    "INTERRUPTION 10 0 50 0 150 120 280 250 300 220 350 50 148",
    "NATIONAL 1872 1881 1893 1568 1682 1820 2019 1889 1920 2070 2212 1777 1884",
    "EXPORT 283 356 459 545 298 0 0 0 0 0 197 689 236",
    "SYSTEM PEAK 2155 2237 2352 2113 1980 1820 2019 1889 1920 2070 2409 2466 2119",
])


def test_rows_rebuilt_despite_y_jitter():
    rows = ocr.rows(MW)
    assert ["IPP", "1114", "1181"] == rows[2][:3] and len(rows[2]) == 14


def test_balance_parsed_and_validated():
    series, ok = ocr.balance(ocr.rows(MW), "MW")
    assert series["MONTHLY NATIONAL PEAK DEMAND"][10] == 2212  # Jestha (index 10 in FY order)
    assert series["EXPORT"][0] == 283 and series["MONTHLY SYSTEM PEAK DEMAND"][11] == 2466
    assert ok == [True] * 12  # sources == national + export every month


def test_bad_month_rejected():
    bad = [b if b[3] != "1872" else (b[0], b[1], b[2], "1972") for b in MW]  # misread digit
    _, ok = ocr.balance(ocr.rows(bad), "MW")
    assert ok[0] is False and all(ok[1:])


def test_records_keep_only_valid_months():
    series, ok = ocr.balance(ocr.rows(MW), "MW")
    ok[0] = False
    recs = ocr.records(series, ok, "annual-report-20232024", "2080/81", 187, "Capacity Balance (MW)")
    assert {r["bs_month"] for r in recs} == set(FY_MONTHS[1:])
    assert all(r["table_no"] == 10187 for r in recs)


GWH_UNLABELED = boxes([
    "IPP 831.31 785.85 864.78 798.99 629.19 481.92 455.70 428.61 398.00 472.00 966.43 1103.39 684.68",
    "NEA SUBSIDIARY 538.00 538.00 538.00 538.00 535.20 351.00 179.90 201.70 155.00 191.00 434.00 538.00 394.82",
    "NEAROR&PROR 421.11 421.55 428.37 422.74 428.21 408.99 379.83 390.47 272.84 289.43 433.02 428.86 393.79",
    "IMPORT 76.70 72.80 70.20 14.30 39.10 239.69 515.70 470.00 665.00 562.00 57.00 51.00 236.12",
    "STORAGE 101.20 99.20 60.00 0.00 97.00 98.40 94.70 26.30 98.90 100.00 75.30 49.60 75.05",
    "INTERRUPTION 0.00 90.00 0.00 0.00 0.00 260.00 170.00 180.00 225.00 325.00 100.00 0.00 112.50",
    "1968.33 2007.40 1961.35 1774.03 1728.81 1839.99 1795.83 1697.08 1815.05 1938.68 2065.65 2171.15 1896.94",
    "EXPORT 267.80 200.00 241.00 408.00 199.00 0.00 0.00 0.00 0.00 0.00 195.00 300.00 150.90",
    "1754.081814.65 1756.87 1464.63 1594.71 1839.99 1795.831697.081815.05 1938.68 1986.39 1947.80 1783.81",
])


def test_unlabeled_rows_named_by_arithmetic_and_merged_numbers_split():
    series, ok = ocr.balance(ocr.rows(GWH_UNLABELED), "MW")
    assert max(series["MONTHLY SYSTEM PEAK DEMAND"]) == 2171.15  # == sum of sources
    assert series["MONTHLY NATIONAL PEAK DEMAND"][:2] == [1754.08, 1814.65]  # split "1754.081814.65"
    assert max(series["MONTHLY NATIONAL PEAK DEMAND"]) == 1986.39
    assert sum(ok) == 12


def test_bare_nea_label_is_subsidiary():
    b = [x if x[3] != "SUBSIDIARY" else (x[0], x[1], x[2], "NEA") for x in MW]
    series, ok = ocr.balance(ocr.rows(b), "MW")
    assert series["NEA SUBSIDIARY"][0] == 536 and all(ok)


def test_label_glued_to_first_number():
    b = boxes(["NEAROR&PROR290.92 304.66 241.96 257.00 250.94 201.20 160.28 141.62 141.77 172.23 270.43 272.24 2705.23"])
    series, _ = ocr.balance(ocr.rows(b), "GWh")
    assert series["NEA ROR & PROR"][0] == 290.92 and len(series["NEA ROR & PROR"]) == 12
