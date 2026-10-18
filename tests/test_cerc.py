from datetime import date

from nea_forecast import cerc

ROWS = [
    ["Table-46(a) : VOLUME AND PRICE OF CROSS BORDER TRADE THROUGH DAY AHEAD MARKET AT IEX, MARCH 2026"],
    ["Sr. No.", "Neighboring Country ", "Volume (MU)", None, None, "Weighted Average Price (₹/kWh)"],
    [None, None, "Sale", "Purchase", "Net", "Sale", "Purchase"],
    ["1", "Nepal", "0", "20.9", "20.9", "-", "2.6395454545454546"],
    ["2", "Bhutan", "0", "391.02", "391.02", "-", "3.2"],
    ["Table-46(b) : VOLUME AND PRICE OF CROSS BORDER TRADE THROUGH REAL TIME MARKET AT IEX, MARCH 2026"],
    [None, None, "Sale", "Purchase", "Net", "Sale", "Purchase"],
    ["1", "Nepal", "40.45", "119.92", "79.47", "3.48", "3.13"],
]


def test_parse_cross_border_nepal():
    got = cerc.parse_rows(ROWS, "u")
    assert got == [
        {"month": date(2026, 3, 1), "market": "DAM", "sale_mu": 0, "purchase_mu": 20.9, "net_mu": 20.9,
         "sale_price": None, "purchase_price": 2.6395454545454546, "source_url": "u"},
        {"month": date(2026, 3, 1), "market": "RTM", "sale_mu": 40.45, "purchase_mu": 119.92, "net_mu": 79.47,
         "sale_price": 3.48, "purchase_price": 3.13, "source_url": "u"},
    ]


def test_xlsx_links():
    html = '<a href="2026/market_monitoring/MMC Report Jan 2026.xlsx">x</a><a href="2026/market_monitoring/a.pdf">p</a>'
    assert cerc.xlsx_links(html) == ["https://www.cercind.gov.in/2026/market_monitoring/MMC%20Report%20Jan%202026.xlsx"]
