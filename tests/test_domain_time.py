from datetime import UTC, date, datetime

from insider_turning_engine.domain.time import us_equity_session_close


def test_us_equity_session_close_tracks_supported_dst_rules() -> None:
    assert us_equity_session_close(date(2026, 1, 2)) == datetime(2026, 1, 2, 21, tzinfo=UTC)
    assert us_equity_session_close(date(2026, 8, 25)) == datetime(2026, 8, 25, 20, tzinfo=UTC)
    # SEC history starts in 2006, before the current US DST calendar began.
    assert us_equity_session_close(date(2006, 3, 20)) == datetime(2006, 3, 20, 21, tzinfo=UTC)
    assert us_equity_session_close(date(2006, 4, 3)) == datetime(2006, 4, 3, 20, tzinfo=UTC)
