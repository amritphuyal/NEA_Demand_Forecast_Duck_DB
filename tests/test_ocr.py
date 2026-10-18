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
