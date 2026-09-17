from scripts.research_phase1_b2 import _cluster_trigger_events


def _row(
    seq: int,
    owner: str,
    tx_date: str,
    evaluation_session: str,
    *,
    issuer: str = "0000000001",
) -> dict[str, object]:
    return {
        "sourceSeq": seq,
        "issuerCik": issuer,
        "ownerCik": owner,
        "transactionDate": tx_date,
        "knowledgeAt": f"{evaluation_session}T15:00:00Z",
        "evaluationSession": evaluation_session,
        "ticker": "TEST",
    }


def test_second_independent_owner_triggers_only_when_public() -> None:
    rows = [
        _row(1, "0000000101", "2019-01-02", "2019-01-04"),
        _row(2, "0000000102", "2019-01-10", "2019-01-14"),
    ]

    events = _cluster_trigger_events(rows)

    assert len(events) == 1
    assert events[0]["evaluationSession"] == "2019-01-14"
    assert events[0]["clusterOwnerCount"] == 2
    assert events[0]["strongCluster"] is False


def test_repeated_purchases_by_same_owner_do_not_form_cluster() -> None:
    rows = [
        _row(1, "0000000101", "2019-01-02", "2019-01-04"),
        _row(2, "0000000101", "2019-01-10", "2019-01-14"),
    ]

    assert _cluster_trigger_events(rows) == []


def test_delayed_older_filing_can_trigger_later_without_backdating() -> None:
    rows = [
        _row(1, "0000000101", "2019-01-20", "2019-01-22"),
        _row(2, "0000000102", "2019-01-05", "2019-01-25"),
    ]

    events = _cluster_trigger_events(rows)

    assert len(events) == 1
    assert events[0]["evaluationSession"] == "2019-01-25"
    assert events[0]["clusterAnchorTransactionDate"] == "2019-01-20"


def test_transactions_more_than_30_days_apart_do_not_cluster() -> None:
    rows = [
        _row(1, "0000000101", "2019-01-01", "2019-01-03"),
        _row(2, "0000000102", "2019-02-01", "2019-02-04"),
    ]

    assert _cluster_trigger_events(rows) == []


def test_three_independent_owners_are_strong_cluster() -> None:
    rows = [
        _row(1, "0000000101", "2019-03-01", "2019-03-04"),
        _row(2, "0000000102", "2019-03-05", "2019-03-07"),
        _row(3, "0000000103", "2019-03-10", "2019-03-12"),
    ]

    events = _cluster_trigger_events(rows)

    assert len(events) == 2
    assert events[0]["clusterOwnerCount"] == 2
    assert events[0]["strongCluster"] is False
    assert events[1]["clusterOwnerCount"] == 3
    assert events[1]["strongCluster"] is True
