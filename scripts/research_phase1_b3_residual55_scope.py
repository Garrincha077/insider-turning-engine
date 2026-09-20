"""Freeze B3 residual-55 scope after second SPAC-unit resolution."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SOURCE_SCOPE_KEY_SHA256 = (
    "sha256:ed13976872da6522da2973a450a1f1c39e22cc19e2ffcc8367b9cc1a1b016b50"
)
RESOLUTION_KEY_SHA256 = (
    "sha256:fae1020ef5d77cd93b885da6bc4e5c8b4a83ec1ded373f9ccc2148bf90add999"
)
RESIDUAL55_KEY_SHA256 = (
    "sha256:378820b3ab1a31441aa5b6a3e0faa54c51961e08aa5747d502a5638000e5a6dc"
)
REMOVED_IDENTITIES = {
    ("0001719893", "MTECU"),
    ("0001768910", "GRCYU"),
    ("0001777393", "SBE.U"),
    ("0001785424", "FSRVU"),
}


def _load_scope(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("status") != "B3_RESIDUAL63_SCOPE_FROZEN":
        raise ValueError("unexpected residual-63 status")
    if p.get("residualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-63 key digest changed")
    if p.get("performanceRead") is not False or p.get("oosOpened") is not False:
        raise ValueError("residual-63 boundary violated")
    if p.get("priceFieldsRead") != [] or p.get("productionScoringChanged") is not False:
        raise ValueError("residual-63 price/production boundary violated")
    cols = p["scopeColumns"]
    rows = [dict(zip(cols, values, strict=True)) for values in p["scopeRows"]]
    if len(rows) != 63 or base._key_digest(rows) != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-63 scope content changed")
    return p, rows


def _load_resolution(path: Path) -> list[dict[str, Any]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("status") != "B3_SPAC_UNIT2_PRIMARY_RESOLUTION_COMPLETE":
        raise ValueError("unexpected second SPAC-unit resolution status")
    if p.get("resolvedRows") != 8 or p.get("resolutionKeySha256") != RESOLUTION_KEY_SHA256:
        raise ValueError("second SPAC-unit resolution contract changed")
    if p.get("performanceRead") is not False or p.get("oosOpened") is not False:
        raise ValueError("second SPAC-unit resolution boundary violated")
    rows = p.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != 8:
        raise ValueError("invalid second SPAC-unit resolution rows")
    if base._key_digest(rows) != RESOLUTION_KEY_SHA256:
        raise ValueError("second SPAC-unit resolution rows changed")
    return rows


def freeze(scope_path: Path, resolution_path: Path, output_path: Path) -> dict[str, Any]:
    source, rows = _load_scope(scope_path)
    resolved = _load_resolution(resolution_path)
    resolved_keys = {base._row_key(row) for row in resolved}
    source_keys = {base._row_key(row) for row in rows}
    if not resolved_keys < source_keys:
        raise ValueError("resolved rows are not a strict source subset")

    residual = [row for row in rows if base._row_key(row) not in resolved_keys]
    if len(residual) != 55 or base._key_digest(residual) != RESIDUAL55_KEY_SHA256:
        raise ValueError("residual-55 scope mismatch")
    if any((str(r["issuerCik"]), str(r["ticker"])) in REMOVED_IDENTITIES for r in residual):
        raise ValueError("resolved SPAC-unit identity remained")

    pairs = sorted({(str(r["issuerCik"]), str(r["ticker"])) for r in residual})
    if len(pairs) != 23:
        raise ValueError("unexpected residual-55 issuer/ticker count")
    buckets = Counter(str(r["evidenceBucket"]) for r in residual)

    payload = {
        "schemaVersion": "1.0.0",
        "status": "B3_RESIDUAL55_SCOPE_FROZEN",
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
        "sourceRows": 63,
        "subtractedSpacRows": 8,
        "residualRows": 55,
        "uniqueIssuerTickerPairs": 23,
        "sourceResidual63KeySha256": SOURCE_SCOPE_KEY_SHA256,
        "spacResolutionKeySha256": RESOLUTION_KEY_SHA256,
        "residualKeySha256": RESIDUAL55_KEY_SHA256,
        "evidenceBucketCounts": dict(sorted(buckets.items())),
        "scopeColumns": source["scopeColumns"],
        "scopeRows": [[r[c] for c in source["scopeColumns"]] for r in residual],
        "issuerTickerPairs": [{"issuerCik": cik, "ticker": ticker} for cik, ticker in pairs],
        "autoExpansionAllowed": False,
        "finalResolutionContractCreated": False,
        "correctedPerformanceOpened": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", type=Path, required=True)
    ap.add_argument("--resolution", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    print(json.dumps(freeze(a.scope, a.resolution, a.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
