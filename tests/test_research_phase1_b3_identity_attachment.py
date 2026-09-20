from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
mod = importlib.import_module("research_phase1_b3_identity_attachment")


def _definition() -> dict[str, object]:
    return {
        "definitionId": "B3_PIT_IDENTITY_TEST",
        "status": "PREDECLARED_BEFORE_B3_DEVELOPMENT_OUTCOMES",
        "windowCalendarDays": 30,
    }


def _event(
    signal: str,
    issuer: str,
    ticker_buy: str,
    buy: str = "100",
    sale: str = "0",
) -> dict[str, object]:
    return {
        "signalId": signal,
        "issuerCik": issuer,
        "knowledgeBoundaryAt": "2019-01-10T18:00:00+00:00",
        "evaluationSession": "2019-01-10",
        "entrySession": "2019-01-11",
        "buyDollars": buy,
        "saleDollars": sale,
        "definitionId": "B3_COMPANY_NET_BUYING_V1",
        "_tickerHint": ticker_buy,
    }


def _revision(
    issuer: str,
    ticker: str | None,
    key: str,
    side: str,
    shares: str,
    price: str,
) -> dict[str, object]:
    return {
        "issuer": {"cik": issuer, "ticker": ticker},
        "transaction": {"shares": shares, "pricePerShare": price},
        "lifecycle": {
            "validFrom": "2019-01-10T17:00:00+00:00",
            "validTo": None,
        },
        "researchReconciliation": {
            "b3QualifiedSide": side,
            "economicEventAt": "2019-01-10T17:00:00+00:00",
            "companyEconomicKey": key,
        },
    }


def _run(
    tmp_path: Path,
    events: list[dict[str, object]],
    revisions: list[dict[str, object]],
) -> dict[str, object]:
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        "".join(json.dumps(row) + "\n" for row in events),
        encoding="utf-8",
    )
    event_summary = tmp_path / "event-summary.json"
    event_summary.write_text(
        json.dumps(
            {
                "status": "B3_EVENT_CONSTRUCTION_PREOUTCOME_PASS",
                "retainedEventCount": len(events),
                "marketDataJoined": False,
                "returnsRead": False,
                "developmentPerformanceComputed": False,
                "validationPerformanceComputed": False,
                "oosOpened": False,
                "productionScoringChanged": False,
            }
        ),
        encoding="utf-8",
    )
    revisions_path = tmp_path / "revisions.jsonl"
    revisions_path.write_text(
        "".join(json.dumps(row) + "\n" for row in revisions),
        encoding="utf-8",
    )
    definition = tmp_path / "definition.json"
    definition.write_text(json.dumps(_definition()), encoding="utf-8")
    return mod.attach_identity(
        events_path=events_path,
        event_summary_path=event_summary,
        revisions_path=revisions_path,
        definition_path=definition,
        output=tmp_path / "out",
    )


def test_single_pit_ticker_and_exact_signal_lineage(tmp_path: Path) -> None:
    events = [_event("s1", "0000000001", "AAA")]
    revisions = [
        _revision("0000000001", "AAA", "k1", "BUY", "20", "5"),
    ]

    summary = _run(tmp_path, events, revisions)

    assert summary["identityEligibleEvents"] == 1
    assert summary["identityQuarantineEvents"] == 0
    row = json.loads(
        (tmp_path / "out/b3-development-identity-events.jsonl")
        .read_text(encoding="utf-8")
        .strip()
    )
    assert row["ticker"] == "AAA"
    assert row["identityStatus"] == "SINGLE_PIT_TICKER"


def test_missing_ticker_is_explicit_attrition(tmp_path: Path) -> None:
    events = [_event("s1", "0000000001", "")]
    revisions = [
        _revision("0000000001", None, "k1", "BUY", "20", "5"),
    ]

    summary = _run(tmp_path, events, revisions)

    assert summary["identityEligibleEvents"] == 0
    assert summary["quarantineStatusCounts"]["MISSING_REAL_TICKER"] == 1
    assert summary["currentTickerFallbackUsed"] is False


def test_ticker_session_collision_quarantines_both_issuers(tmp_path: Path) -> None:
    events = [
        _event("s1", "0000000001", "AAA"),
        _event("s2", "0000000002", "AAA"),
    ]
    revisions = [
        _revision("0000000001", "AAA", "k1", "BUY", "20", "5"),
        _revision("0000000002", "AAA", "k2", "BUY", "20", "5"),
    ]

    summary = _run(tmp_path, events, revisions)

    assert summary["identityEligibleEvents"] == 0
    assert summary["tickerSessionCollisionKeys"] == 1
    assert summary["quarantineStatusCounts"]["TICKER_SESSION_CIK_COLLISION"] == 2


def test_signal_lineage_mismatch_fails_closed(tmp_path: Path) -> None:
    events = [_event("s1", "0000000001", "AAA", buy="101")]
    revisions = [
        _revision("0000000001", "AAA", "k1", "BUY", "20", "5"),
    ]

    try:
        _run(tmp_path, events, revisions)
    except ValueError as exc:
        assert "lineage mismatch" in str(exc)
    else:
        raise AssertionError("signal-state mismatch must fail closed")
