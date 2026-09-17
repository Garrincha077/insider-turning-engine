"""Apply the frozen performance-blind Phase-1 B1 continuity-resolution overlay.

This stage reads only the already-frozen continuity ledger and a machine-readable
resolution contract. It does not read event performance fields, OHLC, realized
returns, or 2023+ OOS data. The source ledger is never modified in place.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

SEALED_YEAR = 2023
LONG_GAP_SESSIONS = 10
KEY_FIELDS = (
    "eventNumber",
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
)
DATE_FIELDS = ("evaluationSession", "entrySession", "targetExitSession")
FORBIDDEN_FIELD_PREFIXES = ("raw_", "excess_", "mae_", "realized_")
FORBIDDEN_FIELD_NAMES = {
    "open",
    "high",
    "low",
    "close",
    "ohlc",
    "adj_close",
    "adjusted_close",
}
ALLOWED_HORIZONS = {21, 63, 126, 252}
ALLOWED_DECISIONS = {
    "SAME_SECURITY_CONTINUITY",
    "TRANSFORMED_HOLDER_CONSIDERATION",
}
ALLOWED_TRANSFORMATIONS = {
    "STOCK_DIVIDEND_QUANTITY",
    "STOCK_ACQUISITION",
    "PASSIVE_HOLDER_STOCK_MERGER",
}


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _assert_allowed_field_names(fieldnames: Iterable[str], *, source: str) -> None:
    forbidden: list[str] = []
    for field in fieldnames:
        normalized = str(field).strip().lower()
        if normalized in FORBIDDEN_FIELD_NAMES or normalized.startswith(FORBIDDEN_FIELD_PREFIXES):
            forbidden.append(str(field))
    if forbidden:
        raise ValueError(
            f"{source} contains forbidden performance/price fields: {sorted(forbidden)}"
        )


def _assert_allowed_json_keys(value: Any, *, source: str) -> None:
    if isinstance(value, dict):
        _assert_allowed_field_names(value.keys(), source=source)
        for nested in value.values():
            _assert_allowed_json_keys(nested, source=source)
    elif isinstance(value, list):
        for nested in value:
            _assert_allowed_json_keys(nested, source=source)


def _year(value: str, *, field: str) -> int:
    text = str(value).strip()
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        raise ValueError(f"invalid ISO date for {field}: {text!r}")
    try:
        return int(text[:4])
    except ValueError as exc:
        raise ValueError(f"invalid ISO date for {field}: {text!r}") from exc


def _assert_unsealed_date(value: str, *, field: str) -> None:
    if _year(value, field=field) >= SEALED_YEAR:
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
    encoded = sorted(
        json.dumps(_key_object(row), sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    return _sha256_bytes("\n".join(encoded).encode("utf-8"))


def _load_contract(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    _assert_allowed_json_keys(payload, source="resolution contract")

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
    if int(scope.get("sealedYear", -1)) != SEALED_YEAR:
        raise ValueError("sealed year is not frozen at 2023")
    if int(scope.get("longGapThresholdXnysSessions", -1)) != LONG_GAP_SESSIONS:
        raise ValueError("long-gap threshold changed from frozen 10 XNYS sessions")
    if scope.get("autoExpansionAllowed") is not False:
        raise ValueError("frozen scope must prohibit automatic expansion")
    if scope.get("horizons") != [21, 63, 126, 252]:
        raise ValueError("frozen horizon set changed")
    if int(scope.get("primaryHorizon", -1)) != 126:
        raise ValueError("primary horizon changed from 126 sessions")
    if str(scope.get("outcomeEnd")) != "2022-12-31":
        raise ValueError("outcome boundary changed from 2022-12-31")

    cohort_years = {int(year) for year in scope.get("developmentCohortYears", [])}
    if cohort_years != {2016, 2017, 2018, 2019, 2020}:
        raise ValueError("development cohort changed from 2016-2020")

    resolutions = payload.get("resolutions")
    if not isinstance(resolutions, list) or not resolutions:
        raise ValueError("resolution contract has no resolutions")
    expected_rows = int(scope.get("expectedSourceUnresolvedRows", -1))
    if len(resolutions) != expected_rows:
        raise ValueError("resolution contract row count does not match frozen scope")

    seen: set[tuple[str, ...]] = set()
    for resolution in resolutions:
        if not isinstance(resolution, dict):
            raise ValueError("resolution entry must be an object")
        key = _row_key(resolution)
        if key in seen:
            raise ValueError("duplicate event-horizon key in resolution contract")
        seen.add(key)

        if int(resolution["horizon"]) not in ALLOWED_HORIZONS:
            raise ValueError("resolution contains non-frozen horizon")
        for field in ("evaluationSession", "entrySession", "targetExitSession", "effectiveDate"):
            _assert_unsealed_date(str(resolution[field]), field=f"contract.{field}")
        evaluation_year = _year(
            str(resolution["evaluationSession"]), field="evaluationSession"
        )
        if evaluation_year not in cohort_years:
            raise ValueError("resolution row falls outside frozen development cohort")
        entry = str(resolution["entrySession"])
        effective = str(resolution["effectiveDate"])
        target = str(resolution["targetExitSession"])
        if not (entry < effective <= target):
            raise ValueError(
                "resolution effective date must satisfy entry < effective <= target exit"
            )
        if str(resolution.get("expectedSourceState")) != "UNRESOLVED_CONTINUITY":
            raise ValueError("resolution may only target frozen unresolved rows")

        decision = str(resolution.get("resolutionDecision"))
        if decision not in ALLOWED_DECISIONS:
            raise ValueError("unsupported frozen resolution decision")
        result_state = str(resolution.get("resultState"))
        factor_text = str(resolution.get("shareQuantityFactor") or "")
        try:
            factor = Decimal(factor_text)
        except InvalidOperation as exc:
            raise ValueError("invalid shareQuantityFactor") from exc
        if factor <= 0:
            raise ValueError("shareQuantityFactor must be positive")

        if decision == "SAME_SECURITY_CONTINUITY":
            if result_state != "PRICE_CONTINUOUS_ADJUSTED":
                raise ValueError("same-security continuity must resolve to price continuity")
            if factor != Decimal("1"):
                raise ValueError("same-security continuity must preserve holder quantity")
            if str(resolution.get("expectedSourceResolutionSource")) != "long_internal_gap":
                raise ValueError("same-security resolution is not tied to frozen long-gap source")
            frozen_gap = resolution.get("frozenGap")
            if not isinstance(frozen_gap, dict):
                raise ValueError("same-security resolution missing frozen gap evidence")
            if int(frozen_gap.get("maxInternalGapSessions", -1)) < LONG_GAP_SESSIONS:
                raise ValueError(
                    "same-security resolution no longer satisfies frozen gap threshold"
                )
            if str(resolution["effectiveDate"]) != str(frozen_gap.get("nextObservedSession")):
                raise ValueError(
                    "same-security effective date must equal frozen post-gap resumption"
                )
        else:
            if result_state != "TRANSFORMED_HOLDER_CONSIDERATION":
                raise ValueError("holder transformation must preserve transformed state")
            kind = str(resolution.get("transformationKind") or "")
            if kind not in ALLOWED_TRANSFORMATIONS:
                raise ValueError("unsupported holder transformation kind")
            if not str(resolution.get("successorSymbol") or ""):
                raise ValueError("holder transformation missing successor symbol")

    expected_key_digest = str(scope.get("unresolvedRowKeySha256") or "")
    actual_key_digest = _key_digest(resolutions)
    if actual_key_digest != expected_key_digest:
        raise ValueError("frozen unresolved-row key digest mismatch")
    return payload, _sha256_bytes(raw)


def _load_source_ledger(
    path: Path, *, expected_sha256: str
) -> tuple[list[dict[str, str]], list[str]]:
    raw = path.read_bytes()
    actual_sha256 = _sha256_bytes(raw)
    if actual_sha256 != expected_sha256:
        raise ValueError("source continuity ledger SHA-256 differs from frozen contract")

    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    fieldnames = list(reader.fieldnames or [])
    _assert_allowed_field_names(fieldnames, source="source continuity ledger")
    required = set(KEY_FIELDS) | {
        "state",
        "successorSymbol",
        "resolutionSource",
        "candidateActionIds",
        "maxInternalGapSessions",
        "longInternalGapCandidate",
    }
    if not required.issubset(fieldnames):
        raise ValueError("source continuity ledger missing required continuity fields")

    rows: list[dict[str, str]] = []
    for raw_row in reader:
        row = {name: str(raw_row.get(name) or "").strip() for name in fieldnames}
        for field in DATE_FIELDS:
            _assert_unsealed_date(row[field], field=f"ledger.{field}")
        horizon = int(row["horizon"])
        if horizon not in ALLOWED_HORIZONS:
            raise ValueError("source ledger contains non-frozen horizon")
        rows.append(row)
    if not rows:
        raise ValueError("source continuity ledger is empty")
    return rows, fieldnames


def _assert_exact_frozen_scope(
    source_rows: list[dict[str, str]], contract: dict[str, Any]
) -> tuple[list[dict[str, str]], dict[tuple[str, ...], dict[str, Any]]]:
    unresolved = [row for row in source_rows if row["state"] == "UNRESOLVED_CONTINUITY"]
    resolutions = list(contract["resolutions"])
    expected_rows = int(contract["frozenScope"]["expectedSourceUnresolvedRows"])
    if len(unresolved) != expected_rows:
        raise ValueError("source unresolved count differs from frozen scope")

    unresolved_keys = [_row_key(row) for row in unresolved]
    if len(unresolved_keys) != len(set(unresolved_keys)):
        raise ValueError("source ledger contains duplicate unresolved event-horizon keys")
    contract_by_key = {_row_key(row): row for row in resolutions}
    source_key_set = set(unresolved_keys)
    contract_key_set = set(contract_by_key)
    if source_key_set != contract_key_set:
        missing = len(source_key_set - contract_key_set)
        extra = len(contract_key_set - source_key_set)
        raise ValueError(
            "frozen unresolved scope changed; "
            f"missing_contract_rows={missing} extra_contract_rows={extra}"
        )
    if _key_digest(unresolved) != contract["frozenScope"]["unresolvedRowKeySha256"]:
        raise ValueError("source unresolved-row key digest differs from frozen contract")
    return unresolved, contract_by_key


def _validate_resolution_against_source(
    source: dict[str, str], resolution: dict[str, Any]
) -> None:
    if source["state"] != str(resolution["expectedSourceState"]):
        raise ValueError("source state differs from frozen resolution expectation")
    if source["resolutionSource"] != str(resolution["expectedSourceResolutionSource"]):
        raise ValueError("source resolution provenance differs from frozen contract")

    expected_action_ids = sorted(str(value) for value in resolution.get("sourceActionIds", []))
    if expected_action_ids:
        actual_action_ids = sorted(
            value for value in source["candidateActionIds"].split(";") if value
        )
        if actual_action_ids != expected_action_ids:
            raise ValueError("source corporate-action ids differ from frozen contract")

    frozen_gap = resolution.get("frozenGap")
    if isinstance(frozen_gap, dict):
        if source["longInternalGapCandidate"].lower() != "true":
            raise ValueError("frozen gap resolution no longer targets a long-gap row")
        if int(source["maxInternalGapSessions"]) != int(frozen_gap["maxInternalGapSessions"]):
            raise ValueError("source gap length differs from frozen diagnostic")


def run(*, ledger_path: Path, contract_path: Path, output_dir: Path) -> dict[str, Any]:
    contract, contract_sha256 = _load_contract(contract_path)
    source_sha256 = str(contract["source"]["continuityLedgerCsvSha256"])
    source_rows, source_fieldnames = _load_source_ledger(
        ledger_path, expected_sha256=source_sha256
    )
    unresolved, contract_by_key = _assert_exact_frozen_scope(source_rows, contract)

    for source in unresolved:
        _validate_resolution_against_source(source, contract_by_key[_row_key(source)])

    output_rows: list[dict[str, Any]] = []
    overlay_rows: list[dict[str, Any]] = []
    resolved_count = 0
    for source in source_rows:
        row: dict[str, Any] = deepcopy(source)
        row["originalState"] = source["state"]
        row["originalResolutionSource"] = source["resolutionSource"]
        row["resolutionDecision"] = ""
        row["resolutionEffectiveDate"] = ""
        row["transformationKind"] = ""
        row["shareQuantityFactor"] = ""
        row["resolutionContractId"] = ""
        row["frozenResolutionApplied"] = False

        resolution = contract_by_key.get(_row_key(source))
        if resolution is not None:
            if source["state"] != "UNRESOLVED_CONTINUITY":
                raise ValueError("frozen overlay attempted to rewrite an ordinary continuity row")
            effective = str(resolution["effectiveDate"])
            if not (source["entrySession"] < effective <= source["targetExitSession"]):
                raise ValueError("resolution effective date is outside the source event horizon")
            row["state"] = str(resolution["resultState"])
            row["successorSymbol"] = str(resolution.get("successorSymbol") or "")
            row["resolutionSource"] = "frozen_resolution_contract"
            row["resolutionDecision"] = str(resolution["resolutionDecision"])
            row["resolutionEffectiveDate"] = effective
            row["transformationKind"] = str(resolution.get("transformationKind") or "")
            row["shareQuantityFactor"] = str(resolution["shareQuantityFactor"])
            row["resolutionContractId"] = str(contract["contractId"])
            row["frozenResolutionApplied"] = True
            resolved_count += 1
            overlay_rows.append(
                {
                    **_key_object(resolution),
                    "effectiveDate": effective,
                    "resolutionDecision": row["resolutionDecision"],
                    "resultState": row["state"],
                    "successorSymbol": row["successorSymbol"],
                    "transformationKind": row["transformationKind"],
                    "shareQuantityFactor": row["shareQuantityFactor"],
                    "resolutionContractId": row["resolutionContractId"],
                }
            )
        output_rows.append(row)

    states = Counter(str(row["state"]) for row in output_rows)
    remaining_unresolved = states.get("UNRESOLVED_CONTINUITY", 0)
    if resolved_count != len(contract["resolutions"]):
        raise ValueError("not every frozen contract row was applied exactly once")
    if remaining_unresolved != 0:
        raise ValueError("UNRESOLVED_CONTINUITY must be zero after frozen overlay")

    decision_counts = Counter(str(row["resolutionDecision"]) for row in overlay_rows)
    scope = contract["frozenScope"]
    if decision_counts.get("SAME_SECURITY_CONTINUITY", 0) != int(
        scope["expectedSameSecurityRows"]
    ):
        raise ValueError("same-security resolution count differs from frozen scope")
    if decision_counts.get("TRANSFORMED_HOLDER_CONSIDERATION", 0) != int(
        scope["expectedTransformedHolderRows"]
    ):
        raise ValueError("holder-transformation count differs from frozen scope")

    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_path = output_dir / "resolved-continuity-ledger.csv"
    output_fieldnames = list(source_fieldnames) + [
        "originalState",
        "originalResolutionSource",
        "resolutionDecision",
        "resolutionEffectiveDate",
        "transformationKind",
        "shareQuantityFactor",
        "resolutionContractId",
        "frozenResolutionApplied",
    ]
    with resolved_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=output_fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    overlay_path = output_dir / "resolution-overlay.csv"
    overlay_fieldnames = list(overlay_rows[0]) if overlay_rows else []
    with overlay_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=overlay_fieldnames)
        writer.writeheader()
        writer.writerows(overlay_rows)

    summary: dict[str, Any] = {
        "schemaVersion": 1,
        "status": "PHASE1_SECURITY_CONTINUITY_RESOLUTION_COMPLETE",
        "contractId": contract["contractId"],
        "contractSha256": contract_sha256,
        "sourceLedgerRunId": int(contract["source"]["continuityLedgerRunId"]),
        "sourceLedgerArtifact": contract["source"]["continuityLedgerArtifact"],
        "sourceLedgerArtifactDigest": contract["source"]["continuityLedgerArtifactDigest"],
        "sourceLedgerCsvSha256": source_sha256,
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
        "resolvedByContractRows": resolved_count,
        "sameSecurityRows": decision_counts.get("SAME_SECURITY_CONTINUITY", 0),
        "transformedHolderRows": decision_counts.get(
            "TRANSFORMED_HOLDER_CONSIDERATION", 0
        ),
        "continuityStates": dict(sorted(states.items())),
        "unresolvedEventHorizonRows": remaining_unresolved,
        "performanceStageBlocked": remaining_unresolved > 0,
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
    summary = run(
        ledger_path=args.ledger,
        contract_path=args.contract,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
