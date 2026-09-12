from datetime import UTC, date, datetime

import pytest

from insider_turning_engine.domain.session_calendar import (
    latest_closed_session,
    session_close,
    session_lag,
)


def test_holiday_weekend_and_daily_before_close():
    # Labor Day Monday is not a missing trading session.
    monday = datetime(2026, 9, 7, 21, tzinfo=UTC)
    assert latest_closed_session(monday) == date(2026, 9, 4)
    assert session_lag(date(2026, 9, 4), as_of=monday) == 0
    assert latest_closed_session(datetime(2026, 9, 8, 19, 59, tzinfo=UTC)) == date(2026, 9, 4)
    assert latest_closed_session(datetime(2026, 9, 8, 20, tzinfo=UTC)) == date(2026, 9, 8)


def test_early_close_and_dst_are_from_calendar():
    friday = date(2026, 11, 27)
    assert session_close(friday) == datetime(2026, 11, 27, 18, tzinfo=UTC)
    assert latest_closed_session(datetime(2026, 11, 27, 18, tzinfo=UTC)) == friday
    assert session_close(date(2026, 7, 1)).hour == 20
    assert session_close(date(2026, 12, 1)).hour == 21


def test_invalid_or_future_bars_not_fresh():
    point = datetime(2026, 9, 8, 21, tzinfo=UTC)
    assert session_lag(date(2026, 9, 4), as_of=point) == 1
    assert session_lag(date(2026, 9, 7), as_of=point) is None
    assert session_lag(date(2026, 9, 9), as_of=point) is None
    assert session_lag(None, as_of=point) is None
    with pytest.raises(ValueError, match="timezone"):
        latest_closed_session(datetime(2026, 9, 8))
