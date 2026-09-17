import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
_intersect_events = importlib.import_module("research_phase1_b4")._intersect_events


def _b1(
    issuer: str,
    session: str,
    *,
    ticker: str = "TEST",
    owners: tuple[str, ...] = ("0000000101",),
) -> dict[str, object]:
    return {
        "issuerCik": issuer,
        "evaluationSession": session,
        "knowledgeAtFirst": f"{session}T14:00:00Z",
        "ticker": ticker,
        "opportunisticOwnerCount": len(owners),
        "opportunisticOwnerIds": list(owners),
        "rawOpportunisticPurchaseRows": len(owners),
    }


def _b2(
    issuer: str,
    session: str,
    *,
    ticker: str = "TEST",
    owners: tuple[str, ...] = ("0000000101", "0000000102"),
) -> dict[str, object]:
    return {
        "issuerCik": issuer,
        "evaluationSession": session,
        "knowledgeAtFirst": f"{session}T15:00:00Z",
        "ticker": ticker,
        "clusterOwnerCount": len(owners),
        "clusterOwnerIds": list(owners),
        "clusterAnchorTransactionDate": session,
        "strongCluster": len(owners) >= 3,
    }


def test_b4_requires_exact_issuer_and_evaluation_session() -> None:
    joint, diag = _intersect_events(
        [_b1("0000000001", "2019-01-10")],
        [
            _b2("0000000001", "2019-01-11"),
            _b2("0000000002", "2019-01-10"),
        ],
    )

    assert joint == []
    assert diag["exactIssuerSessionIntersections"] == 0


def test_b4_combines_same_session_signals_without_future_confirmation() -> None:
    joint, diag = _intersect_events(
        [_b1("0000000001", "2019-02-12")],
        [_b2("0000000001", "2019-02-12")],
    )

    assert len(joint) == 1
    assert joint[0]["evaluationSession"] == "2019-02-12"
    assert joint[0]["knowledgeAtFirst"] == "2019-02-12T15:00:00Z"
    assert joint[0]["opportunisticClusterOwnerOverlapCount"] == 1
    assert diag["intersectionWithOwnerOverlap"] == 1


def test_b4_reports_but_does_not_require_owner_overlap() -> None:
    joint, diag = _intersect_events(
        [_b1("0000000001", "2019-03-14", owners=("0000000199",))],
        [_b2("0000000001", "2019-03-14")],
    )

    assert len(joint) == 1
    assert joint[0]["opportunisticClusterOwnerOverlapCount"] == 0
    assert diag["intersectionWithoutOwnerOverlap"] == 1


def test_b4_rejects_ticker_disagreement_at_same_issuer_session() -> None:
    joint, diag = _intersect_events(
        [_b1("0000000001", "2019-04-10", ticker="AAA")],
        [_b2("0000000001", "2019-04-10", ticker="BBB")],
    )

    assert joint == []
    assert diag["exactIssuerSessionIntersections"] == 1
    assert diag["tickerMismatchAtIntersection"] == 1


def test_b4_output_order_is_session_then_issuer() -> None:
    b1_events = [
        _b1("0000000002", "2019-05-15"),
        _b1("0000000001", "2019-05-15"),
        _b1("0000000003", "2019-05-14"),
    ]
    b2_events = [
        _b2("0000000001", "2019-05-15"),
        _b2("0000000003", "2019-05-14"),
        _b2("0000000002", "2019-05-15"),
    ]

    joint, _ = _intersect_events(b1_events, b2_events)

    assert [(row["evaluationSession"], row["issuerCik"]) for row in joint] == [
        ("2019-05-14", "0000000003"),
        ("2019-05-15", "0000000001"),
        ("2019-05-15", "0000000002"),
    ]


def test_b4_duplicate_component_event_fails_closed() -> None:
    event = _b1("0000000001", "2019-06-10")

    try:
        _intersect_events([event, dict(event)], [_b2("0000000001", "2019-06-10")])
    except ValueError as exc:
        assert "duplicate B1 issuer-session event" in str(exc)
    else:
        raise AssertionError("duplicate component event must fail closed")
