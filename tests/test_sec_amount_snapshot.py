"""Amount-only derivatives stay factual without changing P/S aggregates or history."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from pydantic import ValidationError
from test_dashboard_export import _data
from test_research_snapshot import POINT, _build, _record

from insider_turning_engine.domain.models import CanonicalTransaction
from insider_turning_engine.domain.research import ResearchSnapshot
from insider_turning_engine.export.dashboard import (
    DashboardExportError,
    export_dashboard,
    validate_dashboard_directory,
)
from insider_turning_engine.ingestion.sec.parser import parse_sec_xml

FIXTURES = Path(__file__).parent / "fixtures"
AMOUNT_ACCESSION = "0001234567-26-000004"


def _filing(name: str, accession: str, *, known_at: datetime) -> list[CanonicalTransaction]:
    parsed = parse_sec_xml((FIXTURES / name).read_text().encode(), {
        "accession_number": accession,
        "source_url": "https://www.sec.gov/Archives/edgar/data/test.xml",
        "accepted_at": POINT - timedelta(days=3),
        "observed_at": known_at, "recorded_at": known_at,
        "run_id": "run_repair_amount_fixture_001",
    })
    assert not parsed.quarantines
    return parsed.records


def _amount(*, known_at: datetime = POINT - timedelta(days=1)) -> CanonicalTransaction:
    return _filing("form4_derivative_amount.xml", AMOUNT_ACCESSION, known_at=known_at)[0]


def _market_rows() -> list[CanonicalTransaction]:
    sale = _filing("form4_non_derivative.xml", "0001234567-26-000003",
                   known_at=POINT - timedelta(days=3))[1]
    return [_record(), _record(accession="0001234567-26-000002", owner="0001999102"), sale]


def _export(snapshot: ResearchSnapshot, root: Path) -> dict[str, Any]:
    data = _data()
    data["generatedAt"] = POINT.isoformat()
    data["researchSnapshot"] = snapshot.model_dump(by_alias=True, mode="json")
    export_dashboard(data, root, run_id="run_research_fixture_001", as_of=POINT)
    validate_dashboard_directory(root, require_settings=True)
    return json.loads((root / "research-v2.json").read_text())


def test_amount_derivative_exports_as_research_21_with_null_quantity(tmp_path: Path) -> None:
    amount = _amount()
    assert amount.schema_version == "1.1.0"
    snapshot = _build([*_market_rows(), amount])
    exported = _export(snapshot, tmp_path / "public")
    assert exported["schemaVersion"] == "2.1.0"
    event = next(row for row in exported["economicTransactions"]
                 if row["accession"] == AMOUNT_ACCESSION)
    assert event["table"] == "DERIVATIVE" and event["code"] == "M"
    assert event["shares"] is None and event["value"] == 35000 and event["price"] == 0
    assert event["side"] == "OTHER"
    assert event["qualified"] is False and event["aggregateEligible"] is False
    assert event["knownAt"] == amount.timestamps.knowledge_at.isoformat().replace("+00:00", "Z")
    assert ResearchSnapshot.model_validate(exported).model_dump(mode="json", by_alias=True) \
        == exported
    schema = json.loads((Path(__file__).parents[1] / "schemas/research-snapshot.v2.schema.json")
                        .read_text())
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()) \
        .validate(exported)


def test_amount_derivative_does_not_change_purchase_sale_basis_cluster_or_scores() -> None:
    market = _market_rows()
    before = _build(market)
    after = _build([*market, _amount()])
    assert before.schema_version == "2.0.0" and after.schema_version == "2.1.0"
    assert before.companies == after.companies
    assert before.research_scores == after.research_scores
    assert before.clusters == after.clusters and len(after.clusters) == 1
    assert after.clusters[0].purchase_value == 2000
    assert all(window.purchase_count == 2 and window.purchase_value == 2000
               and window.weighted_basis == 10 for window in after.companies[0].basis)
    market_events = [event for event in after.economic_transactions
                     if event.table == "NON_DERIVATIVE"]
    assert market_events == before.economic_transactions
    assert {event.code for event in market_events} == {"P", "S"}
    assert after.coverage.eligible_companies == before.coverage.eligible_companies


def test_later_recovered_amount_cannot_rewrite_earlier_snapshot_bytes(tmp_path: Path) -> None:
    market = _market_rows()
    repaired_at = POINT + timedelta(seconds=1)
    recovered = _amount(known_at=repaired_at)
    assert recovered.timestamps.accepted_at < POINT
    assert recovered.transaction.transaction_date < POINT.date()
    assert recovered.timestamps.knowledge_at == recovered.timestamps.recorded_at == repaired_at
    before = _build(market)
    after = _build([*market, recovered])
    assert after.schema_version == "2.0.0"
    assert before.model_dump_json(by_alias=True).encode() == after.model_dump_json(by_alias=True) \
        .encode()
    root = tmp_path / "public"
    _export(before, root)
    original_files = {path.name: path.read_bytes() for path in root.iterdir()}
    _export(after, root)
    assert original_files == {path.name: path.read_bytes() for path in root.iterdir()}


@pytest.mark.parametrize("mutation", [
    "legacy_version", "non_derivative", "qualified", "aggregate_eligible", "missing_value",
])
def test_invalid_null_quantity_snapshot_cannot_validate_or_publish(
    tmp_path: Path, mutation: str,
) -> None:
    payload = _build([*_market_rows(), _amount()]).model_dump(mode="json", by_alias=True)
    event = next(row for row in payload["economicTransactions"]
                 if row["accession"] == AMOUNT_ACCESSION)
    if mutation == "legacy_version":
        payload["schemaVersion"] = "2.0.0"
    elif mutation == "non_derivative":
        event["table"] = "NON_DERIVATIVE"
    elif mutation == "qualified":
        event["qualified"] = True
    elif mutation == "aggregate_eligible":
        event["aggregateEligible"] = True
    else:
        event["value"] = None
    with pytest.raises(ValidationError):
        ResearchSnapshot.model_validate(payload)
    data = _data()
    data["generatedAt"] = POINT.isoformat()
    data["researchSnapshot"] = payload
    with pytest.raises(DashboardExportError):
        export_dashboard(data, tmp_path / "invalid", run_id="run_research_fixture_001", as_of=POINT)
