"""Date range utilities for half-open intervals [start, end_exclusive)."""

from datetime import date, datetime, time, timedelta


def day_range(d: date | datetime | str) -> tuple[datetime, datetime]:
    """Return half-open [start_inclusive, end_exclusive) bounds for a single calendar day.

    start: midnight of d (00:00:00.000000)
    end_exclusive: midnight of d + 1 day (00:00:00.000000)
    """
    if isinstance(d, str):
        d = date.fromisoformat(d)
    elif isinstance(d, datetime):
        d = d.date()
    start = datetime.combine(d, time.min)
    end_exclusive = datetime.combine(d + timedelta(days=1), time.min)
    return start, end_exclusive


def range_for(
    d_from: date | datetime | str | None,
    d_to: date | datetime | str | None,
) -> tuple[datetime | None, datetime | None]:
    """Return half-open [start_inclusive, end_exclusive) datetime bounds for a date range.

    If d_from is provided:
      - str: parses ISO date and combines with time.min
      - datetime: kept as-is
      - date: combines with time.min

    If d_to is provided:
      - str: parses ISO date, adds 1 day, and combines with time.min
      - date (and not datetime): adds 1 day and combines with time.min (making the full day inclusive under < end)
      - datetime:
          if time is 23:59:59 or time.max (legacy UI filter artifact):
              advances to start of next day (d_to.date() + 1 day at time.min)
          otherwise:
              kept as-is (e.g. caller passed an explicit timestamp like now or already-computed exclusive bound)
    """
    start_dt = None
    if d_from is not None:
        if isinstance(d_from, datetime):
            start_dt = d_from
        elif isinstance(d_from, date):
            start_dt = datetime.combine(d_from, time.min)
        elif isinstance(d_from, str):
            start_dt = datetime.combine(date.fromisoformat(d_from), time.min)

    end_dt = None
    if d_to is not None:
        if isinstance(d_to, datetime):
            if d_to.time() in (time(23, 59, 59), time.max):
                end_dt = datetime.combine(d_to.date() + timedelta(days=1), time.min)
            else:
                end_dt = d_to
        elif isinstance(d_to, date):
            end_dt = datetime.combine(d_to + timedelta(days=1), time.min)
        elif isinstance(d_to, str):
            end_dt = datetime.combine(date.fromisoformat(d_to) + timedelta(days=1), time.min)

    return start_dt, end_dt
