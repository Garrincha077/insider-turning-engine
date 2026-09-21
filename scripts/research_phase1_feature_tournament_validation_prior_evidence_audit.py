"""Audit frozen prior continuity evidence for 41 validation residual rows."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

EXPECTED_AUDIT_ROWS = 7493
EXPECTED_UNRESOLVED_ROWS = 41

KEY_FIELDS = (
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
)


def _number(value: object, *, default: str = "") -> str:
    if value in (None, ""):
        return default
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def _action_ids(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(sorted(str(item) for item in value if item))
    return tuple(
        sorted(
            item.strip()
            for item in str(value or "").split(";")
            if item.strip()
        )
    )


def _basket(value: object) -> tuple[tuple[str, str, str], ...]:
    if not isinstance(value, list):
        return ()
    rows = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("invalid prior-evidence basket item")
        rows.append(
            (
                str(item.get("symbol") or "").upper(),
                str(item.get("securityClass") or ""),
                _number(
                    item.get(
                        "quantityPerEntryUnit",
                        item.get("quantity"),
                    )
                ),
            )
        )
    return tuple(sorted(rows))


def _fingerprint(row: dict[str, Any]) -> tuple[Any, ...]:
    state = str(row.get("resultState") or "")
    quantity = row.get("shareQuantityFactor")
    if quantity in (None, ""):
        quantity = row.get("successorSharesPerEntryShare")
    if quantity in (None, "") and state in {
        "PRICE_CONTINUOUS_ADJUSTED",
        "SYMBOL_CHANGED_SAME_SECURITY",
    }:
        quantity = 1
    return (
        state,
        str(row.get("successorSymbol") or "").upper(),
        _number(quantity),
        _number(row.get("cashPerEntryShare"), default="0"),
        _basket(row.get("basket")),
    )


def _load_audit(
    csv_path: Path,
    summary_path: Path,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    required = {
        "status": "PHASE1_FEATURE_TOURNAMENT_VALIDATION_CONTINUITY_AUDITED",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "scopeRows": EXPECTED_AUDIT_ROWS,
        "unresolvedRows": EXPECTED_UNRESOLVED_ROWS,
        "providerSemanticsCompletenessChecked": True,
        "performanceStageBlocked": True,
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise ValueError(f"validation audit mismatch: {key}")

    with csv_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = [dict(row) for row in reader]
    if len(rows) != EXPECTED_AUDIT_ROWS:
        raise ValueError("validation audit row count changed")
    unresolved = [
        row
        for row in rows
        if row["state"] == "UNRESOLVED_CONTINUITY"
    ]
    if len(unresolved) != EXPECTED_UNRESOLVED_ROWS:
        raise ValueError("validation unresolved row count changed")
    return summary, unresolved


def _load_b1(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "contractId": "phase1-b1-security-continuity-resolution-v1",
        "researchOnly": True,
        "performanceRead": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"B1 contract mismatch: {key}")
    columns = payload.get("resolutionColumns")
    values = payload.get("resolutions")
    if not isinstance(columns, list) or not isinstance(values, list):
        raise ValueError("invalid B1 compact contract")
    rows = [
        dict(zip(columns, item, strict=True))
        for item in values
    ]
    if len(rows) != 54:
        raise ValueError("B1 continuity row count changed")
    return rows


def _load_contract(
    path: Path,
    *,
    label: str,
    expected_status: str,
    expected_rows: int,
) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "status": expected_status,
        "researchOnly": True,
        "performanceRead": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"{label} contract mismatch: {key}")
    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != expected_rows:
        raise ValueError(f"{label} resolution rows changed")
    return rows


def _load_provider_amendment(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_PROVIDER_COMPLETENESS_"
            "AMENDMENT_COMPLETE"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "amendedRows": 13,
        "validationEventRows": 0,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"provider amendment mismatch: {key}")
    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != 13:
        raise ValueError("provider amendment rows changed")
    return rows


def _prior_rows(
    *,
    b1_path: Path,
    b3_path: Path,
    stage_b_path: Path,
    provider_amendment_path: Path,
) -> list[dict[str, Any]]:
    sources = [
        ("B1", _load_b1(b1_path)),
        (
            "B3",
            _load_contract(
                b3_path,
                label="B3",
                expected_status="B3_FINAL_CONTINUITY_CONTRACT_COMPLETE",
                expected_rows=264,
            ),
        ),
        (
            "STAGE_B",
            _load_contract(
                stage_b_path,
                label="Stage-B",
                expected_status=(
                    "PHASE1_FEATURE_TOURNAMENT_STAGE_B_"
                    "FINAL_CONTINUITY_COMPLETE"
                ),
                expected_rows=210,
            ),
        ),
        (
            "PROVIDER_AMENDMENT",
            _load_provider_amendment(provider_amendment_path),
        ),
    ]
    result = []
    for source, rows in sources:
        for row in rows:
            annotated = dict(row)
            annotated["_source"] = source
            result.append(annotated)
    return result


def _provider_evidence(
    row: dict[str, Any],
    prior: list[dict[str, Any]],
) -> dict[str, Any]:
    ids = _action_ids(row.get("candidateActionIds"))
    if not ids:
        raise ValueError("provider unresolved row lacks action IDs")

    matches = [
        item
        for item in prior
        if str(item.get("issuerCik")) == str(row["issuerCik"])
        and str(item.get("ticker")).upper() == str(row["ticker"]).upper()
        and _action_ids(item.get("sourceActionIds")) == ids
    ]
    if not matches:
        return {
            "category": "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED",
            "actionIds": list(ids),
            "priorMatchCount": 0,
        }

    fingerprints = {_fingerprint(item) for item in matches}
    sources = sorted({str(item["_source"]) for item in matches})
    if len(fingerprints) != 1:
        return {
            "category": "PROVIDER_PRIOR_EVIDENCE_CONFLICT",
            "actionIds": list(ids),
            "priorMatchCount": len(matches),
            "priorSources": sources,
            "economicFingerprints": [
                list(item)
                for item in sorted(fingerprints, key=str)
            ],
        }

    example = matches[0]
    fingerprint = next(iter(fingerprints))
    return {
        "category": "PROVIDER_EXACT_ACTION_PRIOR_CANDIDATE",
        "actionIds": list(ids),
        "priorMatchCount": len(matches),
        "priorSources": sources,
        "economicFingerprint": list(fingerprint),
        "exampleEffectiveDate": str(
            example.get("effectiveDate") or ""
        ),
        "exampleEvidenceClass": str(
            example.get("evidenceClass")
            or example.get("classificationSource")
            or ""
        ),
        "schemaLabels": sorted(
            {
                (
                    str(item.get("resolutionDecision") or ""),
                    str(item.get("transformationKind") or ""),
                )
                for item in matches
            }
        ),
    }


def _long_gap_evidence(
    row: dict[str, Any],
    prior: list[dict[str, Any]],
) -> dict[str, Any]:
    matches = [
        item
        for item in prior
        if str(item.get("issuerCik")) == str(row["issuerCik"])
        and str(item.get("ticker")).upper() == str(row["ticker"]).upper()
        and not _action_ids(item.get("sourceActionIds"))
    ]
    if not matches:
        return {
            "category": "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED",
            "priorMatchCount": 0,
        }

    fingerprints = {_fingerprint(item) for item in matches}
    sources = sorted({str(item["_source"]) for item in matches})
    if len(fingerprints) != 1:
        return {
            "category": "LONG_GAP_PRIOR_SECURITY_CONFLICT",
            "priorMatchCount": len(matches),
            "priorSources": sources,
            "economicFingerprints": [
                list(item)
                for item in sorted(fingerprints, key=str)
            ],
        }

    return {
        "category": "LONG_GAP_PRIOR_SECURITY_CANDIDATE",
        "priorMatchCount": len(matches),
        "priorSources": sources,
        "economicFingerprint": list(next(iter(fingerprints))),
        "effectiveDates": sorted(
            {
                str(item.get("effectiveDate") or "")
                for item in matches
                if item.get("effectiveDate")
            }
        ),
    }


def run(
    *,
    audit_csv: Path,
    audit_summary: Path,
    b1_contract: Path,
    b3_contract: Path,
    stage_b_contract: Path,
    provider_amendment: Path,
    output_path: Path,
) -> dict[str, Any]:
    summary, unresolved = _load_audit(audit_csv, audit_summary)
    prior = _prior_rows(
        b1_path=b1_contract,
        b3_path=b3_contract,
        stage_b_path=stage_b_contract,
        provider_amendment_path=provider_amendment,
    )

    audited = []
    for row in unresolved:
        source = str(row["resolutionSource"])
        if source in {"provider", "provider_incomplete_terms"}:
            evidence = _provider_evidence(row, prior)
        elif source == "long_internal_gap":
            evidence = _long_gap_evidence(row, prior)
        else:
            raise ValueError(f"unexpected validation residual source: {source}")
        audited.append(
            {
                "eventNumber": int(row["eventNumber"]),
                **{
                    field: (
                        int(row[field])
                        if field == "horizon"
                        else str(row[field])
                    )
                    for field in KEY_FIELDS
                },
                "resolutionSource": source,
                "candidateActionIds": list(
                    _action_ids(row.get("candidateActionIds"))
                ),
                "candidateActionTypes": sorted(
                    item
                    for item in str(
                        row.get("candidateActionTypes") or ""
                    ).split(";")
                    if item
                ),
                "maxInternalGapSessions": int(
                    row.get("maxInternalGapSessions") or 0
                ),
                "evidenceAudit": evidence,
            }
        )

    categories = Counter(
        row["evidenceAudit"]["category"]
        for row in audited
    )
    source_counts = Counter(row["resolutionSource"] for row in audited)
    ticker_counts = Counter(
        row["ticker"]
        for row in audited
        if row["evidenceAudit"]["category"].endswith(
            "NEW_PRIMARY_EVIDENCE_REQUIRED"
        )
    )

    if len(audited) != EXPECTED_UNRESOLVED_ROWS:
        raise ValueError("validation evidence audit row count changed")
    if sum(categories.values()) != EXPECTED_UNRESOLVED_ROWS:
        raise ValueError("validation evidence partition is incomplete")

    payload = {
        "schemaVersion": "1.0.0",
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
            "PRIOR_EVIDENCE_AUDIT_COMPLETE"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceValidationScopeKeySha256": summary[
            "sourceScopeKeySha256"
        ],
        "sourceAuditRows": EXPECTED_AUDIT_ROWS,
        "sourceUnresolvedRows": EXPECTED_UNRESOLVED_ROWS,
        "auditedRows": len(audited),
        "resolutionSourceCounts": dict(sorted(source_counts.items())),
        "categoryCounts": dict(sorted(categories.items())),
        "newPrimaryEvidenceTickerCounts": dict(
            sorted(ticker_counts.items())
        ),
        "rows": sorted(
            audited,
            key=lambda item: (
                item["eventNumber"],
                item["horizon"],
            ),
        ),
        "auditOnly": True,
        "resolutionApplied": False,
        "validationPerformanceOpened": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-csv", type=Path, required=True)
    parser.add_argument("--audit-summary", type=Path, required=True)
    parser.add_argument("--b1-contract", type=Path, required=True)
    parser.add_argument("--b3-contract", type=Path, required=True)
    parser.add_argument("--stage-b-contract", type=Path, required=True)
    parser.add_argument("--provider-amendment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = run(
        audit_csv=args.audit_csv,
        audit_summary=args.audit_summary,
        b1_contract=args.b1_contract,
        b3_contract=args.b3_contract,
        stage_b_contract=args.stage_b_contract,
        provider_amendment=args.provider_amendment,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key != "rows"
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
