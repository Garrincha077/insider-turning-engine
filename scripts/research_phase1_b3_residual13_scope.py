"""Freeze B3 residual-13 scope after surviving-unit resolution subtraction."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SOURCE_SCOPE_KEY_SHA256 = (
    "sha256:cd190ed2cfbd8147b5f8c3b3c3f562e4b20093e775b88dfc9a6f0f57dc1167f5"
)
SURVIVING_RESOLUTION_KEY_SHA256 = (
    "sha256:a59cce3f542956da1d04b11ebcf783732ac0513668ef7fff3e4f40fa95a55371"
)
RESIDUAL13_KEY_SHA256 = (
    "sha256:0183d2bb7d158cfa642cb02106eb1937d7e0a327db9e23efb4423188b13c5a18"
)
EXPECTED_IDENTITIES = {
    ("0001622577", "ARWA"),
    ("0001630940", "AAPC"),
    ("0001641398", "WYIG"),
    ("0001680873", "ATACU"),
    ("0001698990", "TPGE"),
    ("0001823882", "NBA.U"),
}


def _load_scope(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("status") != "B3_RESIDUAL24_SCOPE_FROZEN":
        raise ValueError("unexpected residual-24 scope status")
    if p.get("residualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-24 key digest changed")
    if p.get("performanceRead") is not False or p.get("oosOpened") is not False:
        raise ValueError("residual-24 source violates research boundary")
    if p.get("priceFieldsRead") != []:
        raise ValueError("residual-24 source read price fields")
    cols = p["scopeColumns"]
    rows = [dict(zip(cols, values, strict=True)) for values in p["scopeRows"]]
    if len(rows) != 24 or base._key_digest(rows) != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-24 scope content changed")
    return p, rows


def _load_resolution(path: Path) -> list[dict[str, Any]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("status") != "B3_SURVIVING_UNIT_PRIMARY_RESOLUTION_COMPLETE":
        raise ValueError("unexpected surviving-unit resolution status")
    if p.get("resolvedRows") != 11:
        raise ValueError("surviving-unit resolution row count changed")
    if p.get("resolutionKeySha256") != SURVIVING_RESOLUTION_KEY_SHA256:
        raise ValueError("surviving-unit resolution digest changed")
    if p.get("performanceRead") is not False or p.get("oosOpened") is not False:
        raise ValueError("surviving-unit resolution violates research boundary")
    rows = p.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != 11:
        raise ValueError("invalid surviving-unit resolution rows")
    if base._key_digest(rows) != SURVIVING_RESOLUTION_KEY_SHA256:
        raise ValueError("surviving-unit resolution rows changed")
    return rows


def freeze(
    *,
    scope_path: Path,
    surviving_resolution_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    source, source_rows = _load_scope(scope_path)
    resolved = _load_resolution(surviving_resolution_path)

    resolved_keys = {base._row_key(row) for row in resolved}
    source_keys = {base._row_key(row) for row in source_rows}
    if not resolved_keys < source_keys:
        raise ValueError("surviving-unit resolutions are not a strict source subset")

    residual = [
        row for row in source_rows
        if base._row_key(row) not in resolved_keys
    ]
    if len(residual) != 13:
        raise ValueError("surviving-unit subtraction did not produce 13 rows")
    if base._key_digest(residual) != RESIDUAL13_KEY_SHA256:
        raise ValueError("residual-13 key digest mismatch")

    identities = {
        (str(row["issuerCik"]), str(row["ticker"]).upper())
        for row in residual
    }
    if identities != EXPECTED_IDENTITIES:
        raise ValueError("residual-13 identity set changed")

    buckets = Counter(str(row["evidenceBucket"]) for row in residual)
    payload = {
        "schemaVersion": "1.0.0",
        "status": "B3_RESIDUAL13_SCOPE_FROZEN",
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
        "sourceResidual24KeySha256": SOURCE_SCOPE_KEY_SHA256,
        "survivingResolutionKeySha256": SURVIVING_RESOLUTION_KEY_SHA256,
        "sourceRows": 24,
        "subtractedSurvivingRows": 11,
        "residualRows": 13,
        "uniqueIssuerTickerPairs": 6,
        "residualKeySha256": RESIDUAL13_KEY_SHA256,
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
    parser.add_argument("--surviving-resolution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = freeze(
        scope_path=args.scope,
        surviving_resolution_path=args.surviving_resolution,
        output_path=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
