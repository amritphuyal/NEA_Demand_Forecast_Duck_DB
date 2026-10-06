"""Calendar dimension: AD + Bikram Sambat dates, Nepal holidays, season, NEA fiscal year."""
from datetime import date, timedelta
from pathlib import Path

import holidays
import nepali_datetime

from nea_forecast.lake import upsert

START = date(2010, 1, 1)
WINTER_MONTHS = {11, 12, 1, 2, 3, 4}  # dry season: low river flow, imports from India


def build_calendar(start: date, end: date) -> list[dict]:
    hol = holidays.country_holidays("NP", years=range(start.year, end.year + 1))
    rows, d = [], start
    while d <= end:
        b = nepali_datetime.date.from_datetime_date(d)
        fy = b.year if b.month >= 4 else b.year - 1  # fiscal year starts 1 Shrawan (BS month 4)
        rows.append({"date": d, "bs_year": b.year, "bs_month": b.month, "bs_day": b.day,
                     "bs_date": f"{b.year}-{b.month:02d}-{b.day:02d}", "dow": d.isoweekday(),
                     "is_saturday": d.weekday() == 5, "is_holiday": d in hol, "holiday_name": hol.get(d),
                     "season": "winter" if d.month in WINTER_MONTHS else "summer",
                     "fiscal_year": f"{fy}/{(fy + 1) % 100:02d}"})
        d += timedelta(days=1)
    return rows


def ingest(con, root: Path = Path("data")) -> int:
    return upsert(con, "silver.dim_calendar", build_calendar(START, date.today() + timedelta(days=400)), ("date",))
