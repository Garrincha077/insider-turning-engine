"""Apply the frozen performance-blind Phase-1 B1 continuity-resolution overlay."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SEALED_YEAR = 2023
LONG_GAP_SESSIONS = 10
HORIZONS = {21, 63, 126, 252}
COHORT_YEARS = {2016, 2017, 2018, 2019, 2020}
KEY_FIELDS = (
    "eventNumber",
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
)
FORBIDDEN_PREFIXES = ("raw_", "excess_", "mae_", "realized_")
FORBIDDEN_NAMES = {"open", "high", "low", "close", "ohlc", "adj_close", "adjusted_close"}


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _assert_safe_fields(fields: Iterable[str], source: str) -> None:
    bad = []
    for field in fields:
        name = str(field).strip().lower()
        if name in FORBIDDEN_NAMES or name.startswith(FORBIDDEN_PREFIXES):
            bad.append(str(field))
    if bad:
        raise ValueError(f"{source} contains forbidden performance/price fields: {sorted(bad)}")


def _assert_safe_json(value: Any) -> None:
    if isinstance(value, dict):
        _assert_safe_fields(value, "resolution contract")
        for nested in value.values():
            _assert_safe_json(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_safe_json(nested)


def _year(value: str, field: str) -> int:
    text = str(value)
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        raise ValueError(f"invalid ISO date for {field}")
    return int(text[:4])


def _assert_unsealed(value: str, field: str) -> None:
    if _year(value, field) >= SEALED_YEAR:
        raise ValueError(f"sealed OOS boundary violated by {field}")


def _row_key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row[field]) for field in KEY_FIELDS)


def _key_object(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventNumber": int(row["eventNumber"]),
        "issuerCik": str(row["issuerCik"]),
        "ticker": str(row["ticker"]),
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": str(row["entrySession"]),
        "horizon": int(row["horizon"]),
        "targetExitSession": str(row["targetExitSession"]),
    }


def _key_digest(rows: Iterable[dict[str, Any]]) -> str:
    lines = sorted(
        json.dumps(_key_object(row), sort_keys=True, separators=(",", ":")) for row in rows
    )
    return _sha256_bytes("\n".join(lines).encode())


def _normalize_resolutions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    values = payload.get("resolutions")
    if not isinstance(values, list) or not values:
        raise ValueError("resolution contract has no resolutions")
    columns = payload.get("resolutionColumns")
    if columns is None:
        if not all(isinstance(row, dict) for row in values):
            raise ValueError("resolution rows must be objects")
        return values
    if not isinstance(columns, list) or not all(isinstance(value, str) for value in columns):
        raise ValueError("invalid compact resolution column contract")
    rows = []
    for values_row in values:
        if not isinstance(values_row, list) or len(values_row) != len(columns):
            raise ValueError("compact resolution row does not match resolutionColumns")
        row = dict(zip(columns, values_row, strict=True))
        row["expectedSourceState"] = "UNRESOLVED_CONTINUITY"
        rows.append(row)
    return rows


def _load_contract(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode())
    _assert_safe_json(payload)
    if payload.get("researchOnly") is not True:
        raise ValueError("resolution contract must be researchOnly=true")
    if payload.get("oosOpened") is not False:
        raise ValueError("resolution contract opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError("resolution contract changed production scoring")
    if payload.get("performanceRead") is not False:
        raise ValueError("resolution contract is not performance-blind")

    scope = payload.get("frozenScope")
    if not isinstance(scope, dict):
        raise ValueError("resolution contract missing frozenScope")
    if scope.get("developmentCohortYears") != [2016, 2017, 2018, 2019, 2020]:
        raise ValueError("development cohort changed from 2016-2020")
    if scope.get("outcomeEnd") != "2022-12-31" or scope.get("sealedYear") != SEALED_YEAR:
        raise ValueError("frozen outcome/OOS boundary changed")
    if scope.get("horizons") != [21, 63, 126, 252] or scope.get("primaryHorizon") != 126:
        raise ValueError("frozen horizon contract changed")
    if scope.get("longGapThresholdXnysSessions") != LONG_GAP_SESSIONS:
        raise ValueError("long-gap threshold changed from frozen 10 XNYS sessions")
    if scope.get("autoExpansionAllowed") is not False:
        raise ValueError("frozen scope must prohibit automatic expansion")

    rows = _normalize_resolutions(payload)
    payload["resolutions"] = rows
    if len(rows) != int(scope.get("expectedSourceUnresolvedRows", -1)):
        raise ValueError("resolution contract row count does not match frozen scope")
    if len({_row_key(row) for row in rows}) != len(rows):
        raise ValueError("duplicate event-horizon key in resolution contract")

    for row in rows:
        if int(row["horizon"]) not in HORIZONS:
            raise ValueError("resolution contains non-frozen horizon")
        for field in ("evaluationSession", "entrySession", "targetExitSession", "effectiveDate"):
            _assert_unsealed(str(row[field]), f"contract.{field}")
        if _year(str(row["evaluationSession"]), "evaluationSession") not in COHORT_YEARS:
            raise ValueError("resolution row falls outside frozen development cohort")
        entry = str(row["entrySession"])
        effective = str(row["effectiveDate"])
        target = str(row["targetExitSession"])
        if not (entry < effective <= target):
            raise ValueError(
                "resolution effective date must satisfy entry < effective <= target exit"
            )
        if row.get("expectedSourceState") != "UNRESOLVED_CONTINUITY":
            raise ValueError("resolution may only target frozen unresolved rows")

        decision = row.get("resolutionDecision")
        if decision == "SAME_SECURITY_CONTINUITY":
            if row.get("resultState") != "PRICE_CONTINUOUS_ADJUSTED":
                raise ValueError("same-security continuity must resolve to price continuity")
            if str(row.get("shareQuantityFactor")) not in {"1", "1.0"}:
                raise ValueError("same-security continuity must preserve holder quantity")
            if row.get("expectedSourceResolutionSource") != "long_internal_gap":
                raise ValueError("same-security resolution must target frozen long-gap source")
            gap = row.get("maxInternalGapSessions")
            if gap in (None, ""):
                gap = (row.get("frozenGap") or {}).get("maxInternalGapSessions")
            if int(gap) < LONG_GAP_SESSIONS:
                raise ValueError(
                    "same-security resolution no longer satisfies frozen gap threshold"
                )
        elif decision == "TRANSFORMED_HOLDER_CONSIDERATION":
            if row.get("resultState") != "TRANSFORMED_HOLDER_CONSIDERATION":
                raise ValueError("holder transformation must preserve transformed state")
            if not str(row.get("successorSymbol") or ""):
                raise ValueError("holder transformation missing successor symbol")
            if float(row.get("shareQuantityFactor")) <= 0:
                raise ValueError("shareQuantityFactor must be positive")
        else:
            raise ValueError("unsupported frozen resolution decision")

    if _key_digest(rows) != scope.get("unresolvedRowKeySha256"):
        raise ValueError("frozen unresolved-row key digest mismatch")
    return payload, _sha256_bytes(raw)


def _load_source_ledger(
    path: Path, *, expected_sha256: str
) -> tuple[list[dict[str, str]], list[str]]:
    raw = path.read_bytes()
    if _sha256_bytes(raw) != expected_sha256:
        raise ValueError("source continuity ledger SHA-256 differs from frozen contract")
    reader = csv.DictReader(io.StringIO(raw.decode()))
    fields = list(reader.fieldnames or [])
    _assert_safe_fields(fields, "source continuity ledger")
    required = set(KEY_FIELDS) | {
        "state",
        "successorSymbol",
        "resolutionSource",
        "candidateActionIds",
        "maxInternalGapSessions",
        "longInternalGapCandidate",
    }
    if not required.issubset(fields):
        raise ValueError("source continuity ledger missing required continuity fields")

    rows = []
    for raw_row in reader:
        row = {field: str(raw_row.get(field) or "").strip() for field in fields}
        for field in ("evaluationSession", "entrySession", "targetExitSession"):
            _assert_unsealed(row[field], f"ledger.{field}")
        if _year(row["evaluationSession"], "evaluationSession") not in COHORT_YEARS:
            raise ValueError("source row falls outside frozen development cohort")
        if int(row["horizon"]) not in HORIZONS:
            raise ValueError("source ledger contains non-frozen horizon")
        rows.append(row)
    if not rows:
        raise ValueError("source continuity ledger is empty")
    return rows, fields


def _assert_exact_frozen_scope(
    source_rows: list[dict[str, str]], contract: dict[str, Any]
) -> tuple[list[dict[str, str]], dict[tuple[str, ...], dict[str, Any]]]:
    unresolved = [row for row in source_rows if row["state"] == "UNRESOLVED_CONTINUITY"]
    resolutions = contract["resolutions"]
    expected = int(contract["frozenScope"]["expectedSourceUnresolvedRows"])
    if len(unresolved) != expected:
        raise ValueError("source unresolved count differs from frozen scope")
    contract_by_key = {_row_key(row): row for row in resolutions}
    source_keys = {_row_key(row) for row in unresolved}
    if len(source_keys) != len(unresolved):
        raise ValueError("source ledger contains duplicate unresolved event-horizon keys")
    if source_keys != set(contract_by_key):
        raise ValueError("frozen unresolved scope changed; exact key set mismatch")
    if _key_digest(unresolved) != contract["frozenScope"]["unresolvedRowKeySha256"]:
        raise ValueError("source unresolved-row key digest differs from frozen contract")
    return unresolved, contract_by_key


def _validate_source(row: dict[str, str], resolution: dict[str, Any]) -> None:
    if row["state"] != resolution["expectedSourceState"]:
        raise ValueError("source state differs from frozen resolution expectation")
    if row["resolutionSource"] != resolution["expectedSourceResolutionSource"]:
        raise ValueError("source resolution provenance differs from frozen contract")
    expected_ids = sorted(str(value) for value in resolution.get("sourceActionIds", []))
    if expected_ids:
        actual_ids = sorted(value for value in row["candidateActionIds"].split(";") if value)
        if actual_ids != expected_ids:
            raise ValueError("source corporate-action ids differ from frozen contract")
    gap = resolution.get("maxInternalGapSessions")
    if gap in (None, ""):
        gap = (resolution.get("frozenGap") or {}).get("maxInternalGapSessions")
    if gap not in (None, ""):
        if row["longInternalGapCandidate"].lower() != "true":
            raise ValueError("frozen gap resolution no longer targets a long-gap row")
        if int(row["maxInternalGapSessions"]) != int(gap):
            raise ValueError("source gap length differs from frozen diagnostic")


def run(*, ledger_path: Path, contract_path: Path, output_dir: Path) -> dict[str, Any]:
    contract, contract_sha = _load_contract(contract_path)
    source_sha = str(contract["source"]["continuityLedgerCsvSha256"])
    source_rows, fields = _load_source_ledger(ledger_path, expected_sha256=source_sha)
    unresolved, contract_by_key = _assert_exact_frozen_scope(source_rows, contract)
    for row in unresolved:
        _validate_source(row, contract_by_key[_row_key(row)])

    output_rows = []
    overlay_rows = []
    for source in source_rows:
        row: dict[str, Any] = dict(source)
        row.update(
            originalState=source["state"],
            originalResolutionSource=source["resolutionSource"],
            resolutionDecision="",
            resolutionEffectiveDate="",
            transformationKind="",
            shareQuantityFactor="",
            resolutionContractId="",
            frozenResolutionApplied=False,
        )
        resolution = contract_by_key.get(_row_key(source))
        if resolution is not None:
            if source["state"] != "UNRESOLVED_CONTINUITY":
                raise ValueError("frozen overlay attempted to rewrite an ordinary continuity row")
            row.update(
                state=resolution["resultState"],
                successorSymbol=resolution["successorSymbol"],
                resolutionSource="frozen_resolution_contract",
                resolutionDecision=resolution["resolutionDecision"],
                resolutionEffectiveDate=resolution["effectiveDate"],
                transformationKind=resolution.get("transformationKind", ""),
                shareQuantityFactor=str(resolution["shareQuantityFactor"]),
                resolutionContractId=contract["contractId"],
                frozenResolutionApplied=True,
            )
            overlay_rows.append(
                {
                    **_key_object(resolution),
                    "effectiveDate": resolution["effectiveDate"],
                    "resolutionDecision": resolution["resolutionDecision"],
                    "resultState": resolution["resultState"],
                    "successorSymbol": resolution["successorSymbol"],
                    "transformationKind": resolution.get("transformationKind", ""),
                    "shareQuantityFactor": str(resolution["shareQuantityFactor"]),
                    "resolutionContractId": contract["contractId"],
                }
            )
        output_rows.append(row)

    states = Counter(row["state"] for row in output_rows)
    if len(overlay_rows) != len(contract["resolutions"]):
        raise ValueError("not every frozen contract row was applied exactly once")
    if states.get("UNRESOLVED_CONTINUITY", 0):
        raise ValueError("UNRESOLVED_CONTINUITY must be zero after frozen overlay")
    decisions = Counter(row["resolutionDecision"] for row in overlay_rows)
    scope = contract["frozenScope"]
    if decisions["SAME_SECURITY_CONTINUITY"] != scope["expectedSameSecurityRows"]:
        raise ValueError("same-security resolution count differs from frozen scope")
    if decisions["TRANSFORMED_HOLDER_CONSIDERATION"] != scope["expectedTransformedHolderRows"]:
        raise ValueError("holder-transformation count differs from frozen scope")

    output_dir.mkdir(parents=True, exist_ok=True)
    extra = [
        "originalState",
        "originalResolutionSource",
        "resolutionDecision",
        "resolutionEffectiveDate",
        "transformationKind",
        "shareQuantityFactor",
        "resolutionContractId",
        "frozenResolutionApplied",
    ]
    with (output_dir / "resolved-continuity-ledger.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields + extra)
        writer.writeheader()
        writer.writerows(output_rows)
    with (output_dir / "resolution-overlay.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(overlay_rows[0]))
        writer.writeheader()
        writer.writerows(overlay_rows)

    summary = {
        "schemaVersion": 1,
        "status": "PHASE1_SECURITY_CONTINUITY_RESOLUTION_COMPLETE",
        "contractId": contract["contractId"],
        "contractSha256": contract_sha,
        "sourceLedgerRunId": contract["source"]["continuityLedgerRunId"],
        "sourceLedgerArtifact": contract["source"]["continuityLedgerArtifact"],
        "sourceLedgerArtifactDigest": contract["source"]["continuityLedgerArtifactDigest"],
        "sourceLedgerCsvSha256": source_sha,
        "sourceLedgerUntouched": True,
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "performanceRead": False,
        "performanceFieldsRead": [],
        "priceFieldsRead": [],
        "developmentCohortYears": scope["developmentCohortYears"],
        "outcomeEnd": scope["outcomeEnd"],
        "sealedYear": SEALED_YEAR,
        "horizons": scope["horizons"],
        "primaryHorizon": scope["primaryHorizon"],
        "gapThresholdSessions": LONG_GAP_SESSIONS,
        "sourceEventHorizonRows": len(source_rows),
        "sourceUnresolvedEventHorizonRows": len(unresolved),
        "resolutionContractRows": len(contract["resolutions"]),
        "resolvedByContractRows": len(overlay_rows),
        "sameSecurityRows": decisions["SAME_SECURITY_CONTINUITY"],
        "transformedHolderRows": decisions["TRANSFORMED_HOLDER_CONSIDERATION"],
        "continuityStates": dict(sorted(states.items())),
        "unresolvedEventHorizonRows": 0,
        "performanceStageBlocked": False,
        "frozenScopeExpanded": False,
        "unresolvedRowKeySha256": scope["unresolvedRowKeySha256"],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                ledger_path=args.ledger,
                contract_path=args.contract,
                output_dir=args.output_dir,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
