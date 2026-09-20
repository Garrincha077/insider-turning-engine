"""Freeze B3 residual-43 scope after multi-class resolution subtraction."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SOURCE_SCOPE_KEY_SHA256 = (
    "sha256:378820b3ab1a31441aa5b6a3e0faa54c51961e08aa5747d502a5638000e5a6dc"
)
RESOLUTION_KEY_SHA256 = (
    "sha256:d9103eb5d9b5e04e18f955f4f6361ba39932ad285dff823a1046f72b613c2e91"
)
RESIDUAL43_KEY_SHA256 = (
    "sha256:be82164c63ed8c8528017ff3201d5172e818655e5c7a8fa48bd7576c7cb02cd6"
)
REMOVED_IDENTITIES = {
    ("0001635193", "GGO"),
    ("0001471824", "TAGS"),
    ("0001647088", "EAGL"),
    ("0001697152", "FMCIU"),
}


def _load_scope(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("status") != "B3_RESIDUAL55_SCOPE_FROZEN":
        raise ValueError("unexpected residual-55 status")
    if p.get("residualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-55 key digest changed")
    if p.get("performanceRead") is not False or p.get("oosOpened") is not False:
        raise ValueError("residual-55 boundary violated")
    if p.get("priceFieldsRead") != [] or p.get("productionScoringChanged") is not False:
        raise ValueError("residual-55 price/production boundary violated")
    cols = p["scopeColumns"]
    rows = [dict(zip(cols, values, strict=True)) for values in p["scopeRows"]]
    if len(rows) != 55 or base._key_digest(rows) != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-55 scope content changed")
    return p, rows


def _load_resolution(path: Path) -> list[dict[str, Any]]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("status") != "B3_MULTICLASS_REORG_PRIMARY_RESOLUTION_COMPLETE":
        raise ValueError("unexpected multi-class resolution status")
    if p.get("resolvedRows") != 12 or p.get("resolutionKeySha256") != RESOLUTION_KEY_SHA256:
        raise ValueError("multi-class resolution contract changed")
    if p.get("performanceRead") is not False or p.get("oosOpened") is not False:
        raise ValueError("multi-class resolution boundary violated")
    rows = p.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != 12:
        raise ValueError("invalid multi-class resolution rows")
    if base._key_digest(rows) != RESOLUTION_KEY_SHA256:
        raise ValueError("multi-class resolution rows changed")
    return rows


def freeze(scope_path: Path, resolution_path: Path, output_path: Path) -> dict[str, Any]:
    source, rows = _load_scope(scope_path)
    resolved = _load_resolution(resolution_path)
    resolved_keys = {base._row_key(row) for row in resolved}
    source_keys = {base._row_key(row) for row in rows}
    if not resolved_keys < source_keys:
        raise ValueError("resolved rows are not a strict source subset")

    residual = [row for row in rows if base._row_key(row) not in resolved_keys]
    if len(residual) != 43 or base._key_digest(residual) != RESIDUAL43_KEY_SHA256:
        raise ValueError("residual-43 scope mismatch")
    if any((str(r["issuerCik"]), str(r["ticker"])) in REMOVED_IDENTITIES for r in residual):
        raise ValueError("resolved identity remained in residual-43 scope")

    pairs = sorted({(str(r["issuerCik"]), str(r["ticker"])) for r in residual})
    if len(pairs) != 19:
        raise ValueError("unexpected residual-43 issuer/ticker count")
    buckets = Counter(str(r["evidenceBucket"]) for r in residual)

    payload = {
        "schemaVersion": "1.0.0",
        "status": "B3_RESIDUAL43_SCOPE_FROZEN",
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
        "sourceRows": 55,
        "subtractedResolutionRows": 12,
        "residualRows": 43,
        "uniqueIssuerTickerPairs": 19,
        "sourceResidual55KeySha256": SOURCE_SCOPE_KEY_SHA256,
        "resolutionKeySha256": RESOLUTION_KEY_SHA256,
        "residualKeySha256": RESIDUAL43_KEY_SHA256,
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
