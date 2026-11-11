from datetime import date, datetime, timedelta

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from src.target_models import DimDate

def to_date(value) -> date:
    """Given a datetime, return the corresponding date."""
    if isinstance(value, datetime):
        return value.date()
    else:
        return value

def date_key(value) -> int:
    """YYYYMMDD integer from a date or datetime."""
    return int(to_date(value).strftime("%Y%m%d"))

def date_row(d: date) -> dict:
    """Data for the given date in the table dim_date."""
    return {
        "date_key": date_key(d),
        "date": d,
        "year": d.year,
        "quarter": (d.month - 1) // 3 + 1,
        "month": d.month,
        "day_of_month": d.day,
        "day_of_week": d.isoweekday(),
        "is_weekend": 1 if d.isoweekday() >= 6 else 0,
    }

def add_dates(tgt: Session, days) -> int:
    """Insert any missing dates. Returns the number of dates given."""
    rows = [date_row(d) for d in sorted({to_date(x) for x in days if x is not None})]
    for i in range(0, len(rows), 100):
        stmt = insert(DimDate).values(rows[i:i + 100]).on_conflict_do_nothing(
            index_elements=["date_key"])
        tgt.execute(stmt)
    return len(rows)

def date_range(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)

