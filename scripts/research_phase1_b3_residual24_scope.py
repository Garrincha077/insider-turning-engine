"""Freeze B3 residual-24 scope after ordinary-common resolution subtraction."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SOURCE_SCOPE_KEY_SHA256 = (
    "sha256:be82164c63ed8c8528017ff3201d5172e818655e5c7a8fa48bd7576c7cb02cd6"
)
COMMON_RESOLUTION_KEY_SHA256 = (
    "sha256:a99206160529fc915c30b9859307e1cd603f7f4fab5d24278519af18919bc430"
)
RESIDUAL24_KEY_SHA256 = (
    "sha256:cd190ed2cfbd8147b5f8c3b3c3f562e4b20093e775b88dfc9a6f0f57dc1167f5"
)
EXPECTED_IDENTITIES = {
    ("0001622577", "ARWA"),
    ("0001630940", "AAPC"),
    ("0001641398", "WYIG"),
    ("0001680873", "ATACU"),
    ("0001698990", "TPGE"),
    ("0001719489", "GIG.U"),
    ("0001726146", "TWLVU"),
    ("0001742927", "TZACU"),
    ("0001743858", "LOACU"),
    ("0001773086", "ZGYHU"),
    ("0001781162", "SRACU"),
    ("0001823882", "NBA.U"),
}


def _load_scope(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("status") != "B3_RESIDUAL43_SCOPE_FROZEN":
        raise ValueError("unexpected residual-43 scope status")
    if p.get("residualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-43 key digest changed")
    if p.get("performanceRead") is not False or p.get("oosOpened") is not False:
        raise ValueError("residual-43 source violates performance/OOS boundary")
    if p.get("priceFieldsRead") != []:
        raise ValueError("residual-43 source read price fields")
    cols = p["scopeColumns"]
    rows = [dict(zip(cols, values, strict=True)) for values in p["scopeRows"]]
    if len(rows) != 43 or base._key_digest(rows) != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-43 scope content changed")
    return p, rows


def _load_resolution(path: Path) -> list[dict[str, Any]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("status") != "B3_COMMON_SECURITY_PRIMARY_RESOLUTION_COMPLETE":
        raise ValueError("unexpected ordinary-common resolution status")
    if p.get("resolvedRows") != 19:
        raise ValueError("ordinary-common resolution row count changed")
    if p.get("resolutionKeySha256") != COMMON_RESOLUTION_KEY_SHA256:
        raise ValueError("ordinary-common resolution digest changed")
    if p.get("performanceRead") is not False or p.get("oosOpened") is not False:
        raise ValueError("ordinary-common resolution violates research boundary")
    rows = p.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != 19:
        raise ValueError("invalid ordinary-common resolution rows")
    if base._key_digest(rows) != COMMON_RESOLUTION_KEY_SHA256:
        raise ValueError("ordinary-common resolution rows changed")
    return rows


def freeze(
    *,
    scope_path: Path,
    common_resolution_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    source, source_rows = _load_scope(scope_path)
    resolved = _load_resolution(common_resolution_path)

    resolved_keys = {base._row_key(row) for row in resolved}
    source_keys = {base._row_key(row) for row in source_rows}
    if not resolved_keys < source_keys:
        raise ValueError("ordinary-common resolution is not a strict source subset")

    residual = [
        row for row in source_rows
        if base._row_key(row) not in resolved_keys
    ]
    if len(residual) != 24:
        raise ValueError("ordinary-common subtraction did not produce 24 rows")
    if base._key_digest(residual) != RESIDUAL24_KEY_SHA256:
        raise ValueError("residual-24 key digest mismatch")

    identities = {
        (str(row["issuerCik"]), str(row["ticker"]).upper())
        for row in residual
    }
    if identities != EXPECTED_IDENTITIES:
        raise ValueError("residual-24 identity set changed")

    buckets = Counter(str(row["evidenceBucket"]) for row in residual)

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_RESIDUAL24_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "developmentCohortYears": source["developmentCohortYears"],
        "outcomeEnd": source["outcomeEnd"],
        "sealedYear": source["sealedYear"],
        "horizons": source["horizons"],
        "primaryHorizon": source["primaryHorizon"],
        "sourceResidual43KeySha256": SOURCE_SCOPE_KEY_SHA256,
        "commonResolutionKeySha256": COMMON_RESOLUTION_KEY_SHA256,
        "sourceRows": 43,
        "subtractedCommonRows": 19,
        "residualRows": 24,
        "uniqueIssuerTickerPairs": 12,
        "residualKeySha256": RESIDUAL24_KEY_SHA256,
        "evidenceBucketCounts": dict(sorted(buckets.items())),
        "scopeColumns": source["scopeColumns"],
        "scopeRows": [
            [row[column] for column in source["scopeColumns"]]
            for row in residual
        ],
        "issuerTickerPairs": [
            {"issuerCik": cik, "ticker": ticker}
            for cik, ticker in sorted(identities)
        ],
        "autoExpansionAllowed": False,
        "finalResolutionContractCreated": False,
        "correctedPerformanceOpened": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--common-resolution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            freeze(
                scope_path=args.scope,
                common_resolution_path=args.common_resolution,
                output_path=args.output,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
