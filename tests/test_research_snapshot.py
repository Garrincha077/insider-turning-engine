import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from insider_turning_engine.domain.research import DayEvidence, ResearchSnapshot
from insider_turning_engine.export.dashboard import (
    DashboardExportError,
    export_dashboard,
    validate_dashboard_directory,
)
from insider_turning_engine.export.settings import attach_settings
from insider_turning_engine.ingestion.sec.parser import parse_sec_xml
from insider_turning_engine.pipeline.research_snapshot import build_research_snapshot

POINT = datetime(2026, 8, 31, 21, tzinfo=UTC)


def _record(*, accession="0001234567-26-000001", owner="0001999101", amendment=False):
    xml = (Path(__file__).parent / "fixtures/form4_non_derivative.xml").read_text()
    xml = xml.replace("0001999101", owner)
    if amendment:
        xml = xml.replace("<documentType>4</documentType>", "<documentType>4/A</documentType>")
    return parse_sec_xml(xml.encode(), {
        "accession_number": accession, "source_url": "https://www.sec.gov/Archives/test.xml",
        "accepted_at": POINT - timedelta(days=3), "observed_at": POINT - timedelta(days=3),
        "run_id": "run_research_fixture_001",
    }).records[0]


def _build(rows, **kwargs):
    return build_research_snapshot(rows, as_of=POINT, run_id="run_research_fixture_001",
        identities={row.issuer.cik: {"ticker": "ACME"} for row in rows}, **kwargs)


def test_joint_owners_one_event_one_amount_and_replay_identical():
    first, joint = _record(), _record(owner="0001999102")
    snapshot = _build([first, joint])
    replay = _build([joint, first, first, joint])
    assert snapshot.model_dump_json(by_alias=True) == replay.model_dump_json(by_alias=True)
    assert len(snapshot.economic_transactions) == 1
    assert snapshot.economic_transactions[0].value == 1000
    assert len(snapshot.economic_transactions[0].owners) == 2
    assert snapshot.companies[0].basis[0].purchase_value == 1000
    assert snapshot.clusters == []
    assert snapshot.research_scores[0].total is None
    assert snapshot.research_scores[0].state == "UNKNOWN"


def test_same_facts_different_filings_not_merged_and_cluster_members_real():
    first = _record()
    independent = _record(accession="0001234567-26-000002", owner="0001999102")
    snapshot = _build([first, independent])
    assert len(snapshot.economic_transactions) == 2
    assert snapshot.companies[0].basis[0].purchase_value == 2000
    assert len(snapshot.clusters) == 1
    assert snapshot.clusters[0].owner_ciks == ["0001999101", "0001999102"]
    assert snapshot.clusters[0].purchase_value == 2000
    assert snapshot.clusters[0].event_ids == sorted(
        row.event_id for row in snapshot.economic_transactions)


def test_no_cluster_for_multiple_rows_or_filings_by_same_joint_owners():
    rows = [_record(accession=accession, owner=owner)
            for accession in ["0001234567-26-000001", "0001234567-26-000002"]
            for owner in ["0001999101", "0001999102"]]
    assert _build(rows).clusters == []


def test_unresolved_amendment_blocks_issuer_not_unrelated_facts():
    original = _record()
    amendment = _record(accession="0001234567-26-000002", amendment=True)
    other = _record(accession="0001234567-26-000003")
    other.issuer.cik = "0001999002"
    snapshot = _build([original, amendment, other])
    assert snapshot.coverage.unresolved_amendment_issuers == [original.issuer.cik]
    affected = next(row for row in snapshot.companies if row.issuer_cik == original.issuer.cik)
    assert affected.insider_status == "UNRESOLVED_AMENDMENT"
    assert affected.basis[0].purchase_count is None
    assert affected.basis[0].weighted_basis is None
    assert sum(row.aggregate_eligible for row in snapshot.economic_transactions) == 1
    assert any(row.processing == "UNRESOLVED_AMENDMENT"
               for row in snapshot.economic_transactions)


def test_future_or_after_close_observations_do_not_change_snapshot():
    original = _record()
    future = _record(accession="0001234567-26-000002", owner="0001999102")
    future.timestamps.knowledge_at = POINT + timedelta(seconds=1)
    future.issuer.name = "Future name must not leak"
    assert _build([original]).model_dump_json() == _build([original, future]).model_dump_json()
    future.timestamps.knowledge_at = POINT - timedelta(days=1)
    future.transaction.transaction_date = POINT.date() + timedelta(days=1)
    assert _build([original]).model_dump_json() == _build([original, future]).model_dump_json()


def test_partial_window_not_claimed_complete_or_zero():
    record = _record()
    record.transaction.transaction_date = POINT.date() - timedelta(days=45)
    snapshot = _build([record])
    assert snapshot.companies[0].basis[0].coverage == "PARTIAL"
    assert snapshot.companies[0].basis[0].purchase_value is None
    assert snapshot.companies[0].basis[1].purchase_count == 1
    assert snapshot.companies[0].basis[1].coverage == "PARTIAL"
    assert snapshot.readiness.digest.status == "BLOCKED"


def test_complete_sec_evidence_and_missing_day():
    days = [date(2026, 6, 1), date(2026, 8, 31)]
    evidence = [DayEvidence(day=day, discovered_filings=1, stored_filings=1,
                            parse_rows=1, quarantined_rows=0, failures=0, complete=True)
                for day in days]
    assert _build([_record()], expected_sec_days=days,
                  day_evidence=evidence).companies[0].basis[1].coverage \
        == "OBSERVED_COMPLETE_SEC_WINDOW"
    assert _build([_record()], expected_sec_days=days,
                  day_evidence=evidence[:1]).companies[0].basis[1].coverage == "PARTIAL"
    with pytest.raises(ValueError, match="completeness"):
        DayEvidence(day=days[0], discovered_filings=2, stored_filings=1,
                    parse_rows=1, quarantined_rows=0, failures=0, complete=True)


def test_conflicting_economic_row_fails_closed():
    first, conflicting = _record(), _record(owner="0001999102")
    conflicting.transaction.shares *= 2
    with pytest.raises(ValueError, match="conflicting economic"):
        _build([first, conflicting])


def test_contract_rejects_mixed_run_and_orphan_event_owner():
    snapshot = _build([_record()])
    data = snapshot.model_dump(by_alias=True, mode="json")
    data["researchScores"][0]["runId"] = "run_another_day"
    with pytest.raises(ValueError, match="mixed score lineage"):
        ResearchSnapshot.model_validate(data)
    data = snapshot.model_dump(by_alias=True, mode="json")
    data["reportingOwners"] = []
    with pytest.raises(ValueError, match="broken event"):
        ResearchSnapshot.model_validate(data)


def test_schema_and_model_do_not_drift():
    schema = json.loads((Path(__file__).parents[1] / "schemas"
                         / "research-snapshot.v2.schema.json").read_text())
    assert schema == ResearchSnapshot.model_json_schema(by_alias=True)


def test_unresolved_identity_and_noncommon_security_keep_facts_not_aggregates():
    row = _record()
    snapshot = build_research_snapshot([row], as_of=POINT, run_id="run_fixture_0001",
                                       identities={})
    assert len(snapshot.economic_transactions) == 1
    assert not snapshot.economic_transactions[0].aggregate_eligible
    assert snapshot.companies[0].basis[0].coverage == "BLOCKED"
    row.security.title = "Warrants to purchase Common Stock"
    assert not _build([row]).economic_transactions[0].aggregate_eligible


def test_partial_filing_quarantine_blocks_only_evidenced_issuer():
    row = _record()
    other = _record(accession="0001234567-26-000009")
    other.issuer.cik = "0001999002"
    snapshot = _build([row, other], quarantined_issuers=frozenset([row.issuer.cik]))
    assert snapshot.companies[0].insider_status == "SOURCE_QUARANTINE"
    assert snapshot.companies[0].basis[0].coverage == "BLOCKED"
    assert sum(event.aggregate_eligible for event in snapshot.economic_transactions) == 1


def test_atomic_export_replay_hashes_lineage_and_settings_preservation(tmp_path):
    from test_dashboard_export import _data

    data = _data()
    data["generatedAt"] = POINT.isoformat()
    data["researchSnapshot"] = _build([_record()]).model_dump(by_alias=True, mode="json")
    root = tmp_path / "public"
    export_dashboard(data, root, run_id="run_research_fixture_001", as_of=POINT)
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    export_dashboard(data, root, run_id="run_research_fixture_001", as_of=POINT)
    assert before == {path.name: path.read_bytes() for path in root.iterdir()}
    bad = dict(data)
    bad["researchSnapshot"] = {**data["researchSnapshot"], "runId": "run_bad_lineage"}
    with pytest.raises(DashboardExportError):
        export_dashboard(bad, root, run_id="run_research_fixture_001", as_of=POINT)
    assert before == {path.name: path.read_bytes() for path in root.iterdir()}
    settings = tmp_path / "settings.json"
    settings.write_bytes((root / "settings-status.json").read_bytes())
    attach_settings(root, settings)
    assert (root / "research-v2.json").read_bytes() == before["research-v2.json"]
    validate_dashboard_directory(root, require_settings=True)
    (root / "research-v2.json").write_text("{}")
    with pytest.raises(DashboardExportError, match="size mismatch|hash mismatch"):
        validate_dashboard_directory(root)
