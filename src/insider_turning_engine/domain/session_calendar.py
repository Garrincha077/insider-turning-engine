"""XNYS calendar for operational freshness; never guess with calendar-day age."""

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import Any

import exchange_calendars as xcals  # type: ignore[import-untyped]

CALENDAR_VERSION = "exchange-calendars-4.13.2:XNYS"


@lru_cache(maxsize=4)
def _calendar(year: int) -> Any:
    return xcals.get_calendar("XNYS", start=f"{year - 2}-01-01", end=f"{year + 1}-12-31")


def latest_closed_session(as_of: datetime) -> date:
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    point = as_of.astimezone(UTC)
    calendar = _calendar(point.year)
    candidates = calendar.sessions_in_range(point.date() - timedelta(days=15), point.date())
    for session in reversed(candidates):
        if calendar.session_close(session).to_pydatetime() <= point:
            return session.date()  # type: ignore[no-any-return]
    raise ValueError("calendar contains no recent closed session")


def session_close(day: date) -> datetime:
    return _calendar(day.year).session_close(day).to_pydatetime()  # type: ignore[no-any-return]


def session_lag(day: date | None, *, as_of: datetime) -> int | None:
    latest = latest_closed_session(as_of)
    if day is None or day.year < latest.year - 2:
        return None
    calendar = _calendar(latest.year)
    if day > latest or not calendar.is_session(day):
        return None
    return max(0, len(calendar.sessions_in_range(day, latest)) - 1)
