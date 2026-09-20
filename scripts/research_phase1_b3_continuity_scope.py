"""Freeze the exact B3 unresolved security-continuity scope.

Reads only continuity identity/provenance fields from the persisted ledger.
Performance and OHLC fields are enumerated and rejected from the extracted
scope. The output is an immutable input for later performance-blind resolution.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as resolution

EXPECTED_UNRESOLVED = 264
EXPECTED_LONG_GAP = 200
EXPECTED_PROVIDER = 64

SAFE_FIELDS = (
    *resolution.KEY_FIELDS,
    "state",
    "resolutionSource",
    "candidateActionTypes",
    "candidateActionIds",
    "maxInternalGapSessions",
    "longInternalGapCandidate",
    "successorSymbol",
)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(
    *,
    ledger_path: Path,
    ledger_summary_path: Path,
    output_path: Path,
    source_release: str,
    source_asset: str,
    source_asset_digest: str,
) -> dict[str, Any]:
    summary = json.loads(ledger_summary_path.read_text(encoding="utf-8"))
    if summary.get("status") != "PHASE1_SECURITY_CONTINUITY_LEDGER_COMPLETE":
        raise ValueError("unexpected B3 continuity ledger status")
    if summary.get("performanceRead") is not False:
        raise ValueError("source ledger was not performance-blind")
    if summary.get("oosOpened") is not False:
        raise ValueError("source ledger opened OOS")
    if summary.get("productionScoringChanged") is not False:
        raise ValueError("source ledger changed production scoring")
    if summary.get("gapThresholdSessions") != 10:
        raise ValueError("source long-gap threshold changed")
    if summary.get("unresolvedEventHorizonRows") != EXPECTED_UNRESOLVED:
        raise ValueError("unexpected unresolved count")

    unresolved: list[dict[str, str]] = []
    with ledger_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        if not set(SAFE_FIELDS).issubset(fields):
            raise ValueError("source ledger missing frozen scope fields")
        for raw in reader:
            if raw.get("state") != "UNRESOLVED_CONTINUITY":
                continue
            row = {field: str(raw.get(field) or "").strip() for field in SAFE_FIELDS}
            for field in ("evaluationSession", "entrySession", "targetExitSession"):
                if int(row[field][:4]) >= resolution.SEALED_YEAR:
                    raise ValueError("sealed OOS boundary violated")
            unresolved.append(row)

    if len(unresolved) != EXPECTED_UNRESOLVED:
        raise ValueError("CSV unresolved count differs from summary")
    if len({resolution._row_key(row) for row in unresolved}) != len(unresolved):
        raise ValueError("duplicate unresolved event-horizon key")

    sources = Counter(row["resolutionSource"] for row in unresolved)
    if sources != Counter({"long_internal_gap": EXPECTED_LONG_GAP, "provider": EXPECTED_PROVIDER}):
        raise ValueError("unexpected unresolved provenance mix")

    unresolved.sort(key=resolution._row_key)
    columns = list(SAFE_FIELDS)
    compact = [[row[column] for column in columns] for row in unresolved]

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_UNRESOLVED_CONTINUITY_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "source": {
            "release": source_release,
            "asset": source_asset,
            "assetDigest": source_asset_digest,
            "continuityLedgerCsvSha256": _sha256(ledger_path),
            "continuityLedgerSummarySha256": _sha256(ledger_summary_path),
        },
        "frozenScope": {
            "developmentCohortYears": [2016, 2017, 2018, 2019, 2020],
            "outcomeEnd": "2022-12-31",
            "sealedYear": 2023,
            "horizons": [21, 63, 126, 252],
            "primaryHorizon": 126,
            "longGapThresholdXnysSessions": 10,
            "expectedSourceUnresolvedRows": len(unresolved),
            "longInternalGapRows": sources["long_internal_gap"],
            "providerRows": sources["provider"],
            "uniqueEvents": len({row["eventNumber"] for row in unresolved}),
            "uniqueIssuers": len({row["issuerCik"] for row in unresolved}),
            "uniqueTickers": len({row["ticker"] for row in unresolved}),
            "unresolvedRowKeySha256": resolution._key_digest(unresolved),
            "autoExpansionAllowed": False,
        },
        "unresolvedColumns": columns,
        "unresolvedRows": compact,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--ledger-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-release", required=True)
    parser.add_argument("--source-asset", required=True)
    parser.add_argument("--source-asset-digest", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            freeze(
                ledger_path=args.ledger,
                ledger_summary_path=args.ledger_summary,
                output_path=args.output,
                source_release=args.source_release,
                source_asset=args.source_asset,
                source_asset_digest=args.source_asset_digest,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
