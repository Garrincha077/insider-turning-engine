"""Adjudicate the frozen POPE B1/B3 continuity conflict from primary evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

EXPECTED_CONFLICT_STATUS = (
    "PHASE1_FEATURE_TOURNAMENT_POPE_PRIOR_CONTINUITY_CONFLICT_FROZEN"
)
EXPECTED_EVIDENCE_CONTRACT = (
    "phase1-feature-tournament-pope-primary-evidence-v1"
)
EXPECTED_CONFLICT_ASSET_SHA256 = (
    "sha256:4a510d67a691e8b74ab268c4610ec83356fef3544a2c56d1160610cba8f8bd1d"
)
EXPECTED_RESIDUAL_SCOPE_SHA256 = (
    "sha256:bba0f3fd8c46c04e0ccd27a6b6a2a6ac0f8fcf074d89fee7239d5477f0574e01"
)


def _assert_boundary(payload: dict[str, Any], *, label: str) -> None:
    required = {
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"{label} boundary mismatch: {key}")


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _prior_match(
    row: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    matches = [
        item
        for item in row.get("priorMatches", [])
        if item.get("source") == source
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one {source} prior match")
    return matches[0]


def run(
    *,
    conflict_path: Path,
    evidence_path: Path,
    output_path: Path,
    verify_frozen_asset: bool = True,
) -> dict[str, Any]:
    if verify_frozen_asset and _sha(conflict_path) != EXPECTED_CONFLICT_ASSET_SHA256:
        raise ValueError("POPE conflict diagnostic asset digest changed")

    conflict = json.loads(conflict_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    _assert_boundary(conflict, label="conflict")
    _assert_boundary(evidence, label="evidence")

    if conflict.get("status") != EXPECTED_CONFLICT_STATUS:
        raise ValueError("unexpected POPE conflict status")
    if conflict.get("conflictRows") != 1:
        raise ValueError("POPE conflict row count changed")
    if conflict.get("adjudicated") is not False:
        raise ValueError("POPE conflict was already adjudicated")

    # Diagnostic v1 accidentally serialized the shell token "$SOURCE_DIGEST"
    # instead of expanding it. Its whole-file release digest is immutable and
    # verified above, so provenance is repaired here with the independently
    # frozen residual-scope asset digest rather than trusting that bad field.
    row = conflict.get("row")
    subject = evidence.get("subject")
    if not isinstance(row, dict) or not isinstance(subject, dict):
        raise ValueError("malformed POPE conflict/evidence subject")

    if evidence.get("contractId") != EXPECTED_EVIDENCE_CONTRACT:
        raise ValueError("unexpected POPE primary-evidence contract")

    exact_pairs = {
        "issuerCik": "issuerCik",
        "ticker": "historicalTicker",
        "evaluationSession": "evaluationSession",
        "entrySession": "entrySession",
        "horizon": "horizon",
        "targetExitSession": "targetExitSession",
    }
    for conflict_key, evidence_key in exact_pairs.items():
        if str(row.get(conflict_key)) != str(subject.get(evidence_key)):
            raise ValueError(
                f"POPE primary evidence does not match {conflict_key}"
            )

    if int(row.get("currentEventNumber")) != 16553:
        raise ValueError("POPE current event number changed")
    if row.get("matchStatus") != "PRIOR_ECONOMIC_CONFLICT":
        raise ValueError("POPE row is no longer a prior-economic conflict")
    if sorted(row.get("priorSources") or []) != ["B1", "B3"]:
        raise ValueError("POPE conflict prior-source set changed")

    b1 = _prior_match(row, "B1")
    b3 = _prior_match(row, "B3")
    b1_fp = b1["economicFingerprint"]
    b3_fp = b3["economicFingerprint"]

    if str(b1_fp.get("successorSymbol")) != "RYN":
        raise ValueError("unexpected B1 POPE successor")
    if _decimal(b1_fp.get("quantityFactor")) != Decimal("3.929"):
        raise ValueError("unexpected B1 POPE quantity")
    if _decimal(b1_fp.get("cashPerEntryShare")) != Decimal("0"):
        raise ValueError("unexpected B1 POPE cash term")

    if str(b3_fp.get("successorSymbol")) != "RYN":
        raise ValueError("unexpected B3 POPE successor")
    if _decimal(b3_fp.get("quantityFactor")) != Decimal("3.929"):
        raise ValueError("unexpected B3 POPE quantity")
    if _decimal(b3_fp.get("cashPerEntryShare")) != Decimal("125"):
        raise ValueError("unexpected B3 POPE cash term")

    adjudication = evidence.get("conflictAdjudication", {})
    if adjudication.get("b1EconomicSemantics") != (
        "SUPPORTED_BY_PRIMARY_SOURCE"
    ):
        raise ValueError("primary evidence does not support B1 economics")
    if adjudication.get("b3EconomicSemantics") != (
        "REJECTED_FOR_THIS_PASSIVE_HOLDER_POLICY"
    ):
        raise ValueError("primary evidence did not reject B3 economics")

    policy = evidence.get("passiveHolderPolicy", {})
    if policy.get("policy") != "NO_VALID_ELECTION_DEFAULT":
        raise ValueError("unexpected POPE passive-holder policy")
    result = policy.get("result")
    if not isinstance(result, dict):
        raise ValueError("missing POPE authoritative result")

    expected_result = {
        "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind": "PASSIVE_HOLDER_STOCK_MERGER",
        "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol": "RYN",
        "successorSharesPerEntryShare": 3.929,
        "cashPerEntryShare": 0,
    }
    if result != expected_result:
        raise ValueError("POPE authoritative passive-holder terms changed")

    primary = evidence.get("primarySource", {})
    if primary.get("form") != "8-K":
        raise ValueError("POPE primary source must be the closing 8-K")
    if primary.get("accession") != "0000052827-20-000138":
        raise ValueError("unexpected POPE primary-source accession")
    expected_url = (
        "https://www.sec.gov/Archives/edgar/data/52827/"
        "000005282720000138/ryn-20200507.htm"
    )
    if primary.get("document") != expected_url:
        raise ValueError("unexpected POPE primary-source document")

    resolution = {
        "eventNumber": int(row["currentEventNumber"]),
        "issuerCik": str(row["issuerCik"]),
        "ticker": str(row["ticker"]),
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": str(row["entrySession"]),
        "horizon": int(row["horizon"]),
        "targetExitSession": str(row["targetExitSession"]),
        "expectedSourceResolutionSource": str(
            row["currentResolutionSource"]
        ),
        "effectiveDate": str(subject["effectiveDate"]),
        **result,
        "successorIssuerCik": "0000052827",
        "evidenceClass": "PRIMARY_SEC_CLOSING_ELECTION_RESULTS",
        "evidenceContractId": str(evidence["contractId"]),
        "primarySourceAccession": str(primary["accession"]),
        "primarySourceDocument": str(primary["document"]),
        "adjudication": "B1_PASSIVE_HOLDER_ECONOMICS_CONFIRMED",
    }

    payload = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_POPE_CONFLICT_ADJUDICATED",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualScopeSha256": EXPECTED_RESIDUAL_SCOPE_SHA256,
        "sourceConflictAssetSha256": EXPECTED_CONFLICT_ASSET_SHA256,
        "sourceConflictRowSha256": str(conflict["conflictRowSha256"]),
        "safePriorEvidenceRows": 175,
        "conflictRows": 1,
        "adjudicatedRows": 1,
        "remainingPOPEConflictRows": 0,
        "remainingPrimaryEvidenceRows": 34,
        "resolution": resolution,
        "adjudicated": True,
        "resolutionCompleteForPOPE": True,
        "featureDiscoveryOutcomesOpened": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conflict", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = run(
        conflict_path=args.conflict,
        evidence_path=args.evidence,
        output_path=args.output,
    )
    compact = {
        key: value
        for key, value in result.items()
        if key != "resolution"
    }
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
