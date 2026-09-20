"""Freeze B3 residual-87 scope after exact provider-row subtraction."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

SOURCE_SCOPE_KEY_SHA256 = (
    "sha256:46eeaa05a83960c1ef9537dd88972351b8c984c996ccddffa23f7da8d294ab58"
)
PROVIDER_RESOLUTION_KEY_SHA256 = (
    "sha256:8db525671fcc4381ca8b5e906f132df28fe64f5d6c7d5000699b48730cfc5f2c"
)
RESIDUAL87_KEY_SHA256 = (
    "sha256:c28829aa56204db04633546d91b06b938d06f897cd022d2c8147f488415d2742"
)


def _load_scope(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "B3_RESIDUAL91_SCOPE_FROZEN":
        raise ValueError("unexpected residual-91 scope status")
    if payload.get("residualKeySha256") != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-91 key digest changed")
    if payload.get("performanceRead") is not False or payload.get("oosOpened") is not False:
        raise ValueError("residual-91 source violates research boundaries")
    columns = payload["scopeColumns"]
    rows = [dict(zip(columns, values, strict=True)) for values in payload["scopeRows"]]
    if len(rows) != 91 or base._key_digest(rows) != SOURCE_SCOPE_KEY_SHA256:
        raise ValueError("residual-91 scope content changed")
    return payload, rows


def _load_resolutions(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "B3_PROVIDER_PRIMARY_RESOLUTION_COMPLETE":
        raise ValueError("unexpected provider resolution status")
    if int(payload.get("resolvedProviderRows", -1)) != 4:
        raise ValueError("provider resolution row count changed")
    if payload.get("resolutionKeySha256") != PROVIDER_RESOLUTION_KEY_SHA256:
        raise ValueError("provider resolution key digest changed")
    if payload.get("performanceRead") is not False or payload.get("oosOpened") is not False:
        raise ValueError("provider resolution violates research boundaries")
    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != 4:
        raise ValueError("invalid provider resolution rows")
    if base._key_digest(rows) != PROVIDER_RESOLUTION_KEY_SHA256:
        raise ValueError("provider resolution content changed")
    return rows


def freeze(
    *,
    scope_path: Path,
    provider_resolution_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    scope_payload, scope_rows = _load_scope(scope_path)
    provider_rows = _load_resolutions(provider_resolution_path)

    provider_keys = {base._row_key(row) for row in provider_rows}
    source_keys = {base._row_key(row) for row in scope_rows}
    if not provider_keys < source_keys:
        raise ValueError("provider resolutions are not a strict subset of residual-91 scope")

    residual = [
        row for row in scope_rows
        if base._row_key(row) not in provider_keys
    ]
    if len(residual) != 87:
        raise ValueError("provider subtraction did not produce 87 rows")
    if base._key_digest(residual) != RESIDUAL87_KEY_SHA256:
        raise ValueError("residual-87 key digest mismatch")
    if any(row["resolutionSource"] != "long_internal_gap" for row in residual):
        raise ValueError("provider row remained in residual-87 scope")
    if any(
        row["residualReason"] != "NO_MATCHING_PRIOR_B1_EVIDENCE"
        for row in residual
    ):
        raise ValueError("unexpected residual-87 reason")

    pairs = sorted({(str(row["issuerCik"]), str(row["ticker"])) for row in residual})
    if len(pairs) != 33:
        raise ValueError("unexpected residual-87 issuer/ticker identity count")

    buckets = Counter(str(row["evidenceBucket"]) for row in residual)

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_RESIDUAL87_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "developmentCohortYears": scope_payload["developmentCohortYears"],
        "outcomeEnd": scope_payload["outcomeEnd"],
        "sealedYear": scope_payload["sealedYear"],
        "horizons": scope_payload["horizons"],
        "primaryHorizon": scope_payload["primaryHorizon"],
        "sourceResidual91KeySha256": SOURCE_SCOPE_KEY_SHA256,
        "providerResolutionKeySha256": PROVIDER_RESOLUTION_KEY_SHA256,
        "sourceRows": 91,
        "subtractedProviderRows": 4,
        "residualRows": 87,
        "uniqueIssuerTickerPairs": 33,
        "residualKeySha256": RESIDUAL87_KEY_SHA256,
        "evidenceBucketCounts": dict(sorted(buckets.items())),
        "scopeColumns": scope_payload["scopeColumns"],
        "scopeRows": [
            [row[column] for column in scope_payload["scopeColumns"]]
            for row in residual
        ],
        "issuerTickerPairs": [
            {"issuerCik": cik, "ticker": ticker}
            for cik, ticker in pairs
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
    parser.add_argument("--provider-resolution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(freeze(
        scope_path=args.scope,
        provider_resolution_path=args.provider_resolution,
        output_path=args.output,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
