"""Point-in-time clocks shared by daily-close calculations."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

_REGULAR_CLOSE = time(16, 0)


def _sunday_in_month(year: int, month: int, occurrence: int) -> date:
    first = date(year, month, 1)
    days_to_sunday = (6 - first.weekday()) % 7
    return first + timedelta(days=days_to_sunday + 7 * (occurrence - 1))


def _last_sunday_in_month(year: int, month: int) -> date:
    first_next_month = date(year + (month == 12), month % 12 + 1, 1)
    last = first_next_month - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - 6) % 7)


def us_equity_session_close(session: date) -> datetime:
    """Return the US regular-session 16:00 Eastern close as an aware UTC instant.

    This deliberately avoids a host ``tzdata`` dependency.  The engine's SEC
    history starts in 2006, so both the 2006 rule and the current (2007+)
    daylight-saving rule are represented.
    """

    if session.year >= 2007:
        daylight_start = _sunday_in_month(session.year, 3, 2)
        daylight_end = _sunday_in_month(session.year, 11, 1)
    else:
        daylight_start = _sunday_in_month(session.year, 4, 1)
        daylight_end = _last_sunday_in_month(session.year, 10)
    utc_offset_hours = 4 if daylight_start <= session < daylight_end else 5
    return datetime.combine(session, _REGULAR_CLOSE, tzinfo=UTC) + timedelta(hours=utc_offset_hours)


__all__ = ["us_equity_session_close"]
