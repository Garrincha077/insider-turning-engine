"""Freeze the final 10-row F2 validation long-gap residual."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ROWS = 11
EXPECTED_RESOLVED_ROWS = 1
EXPECTED_RESIDUAL_ROWS = 10
EXPECTED_SOURCE_DIGEST = (
    "sha256:46381d68c3ad51f9d6d9d7a934d88d807c599f78712f34d4e210c9f4248e5d55"
)
EXPECTED_RESOLUTION_DIGEST = (
    "sha256:a8705b17cd9f57eab966148e2ecaef12126e7010698ee812090b26151bed0e75"
)
EXPECTED_RESIDUAL_DIGEST = (
    "sha256:bba1bd1512a8ab6b8009e477689e189c2bd5ebf3033801f50753b023d5d6a426"
)
EXPECTED_TICKERS = {
    "ROCGU",
    "APMIU",
    "GRCY",
    "MCAGU",
    "NETC.U",
    "KACLU",
    "UPTD",
    "JAGX",
    "ACON",
    "NVVE",
}
KEY_FIELDS = (
    "eventNumber",
    "issuerCik",
    "ticker",
    "evaluationSession",
    "entrySession",
    "horizon",
    "targetExitSession",
)


def _obj(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventNumber": int(r["eventNumber"]),
        "issuerCik": str(r["issuerCik"]),
        "ticker": str(r["ticker"]).upper(),
        "evaluationSession": str(r["evaluationSession"]),
        "entrySession": str(r["entrySession"]),
        "horizon": int(r["horizon"]),
        "targetExitSession": str(r["targetExitSession"]),
    }


def _key(r: dict[str, Any]) -> tuple[str, ...]:
    o = _obj(r)
    return tuple(str(o[k]) for k in KEY_FIELDS)


def _digest(rows: list[dict[str, Any]]) -> str:
    lines = sorted(
        json.dumps(_obj(r), sort_keys=True, separators=(",", ":")) for r in rows
    )
    return "sha256:" + hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _boundary(p: dict[str, Any], label: str) -> None:
    required = {
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
    }
    for k, v in required.items():
        if p.get(k) != v:
            raise ValueError(f"{label} boundary mismatch: {k}")


def run(
    *,
    source_path: Path,
    resolution_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    resolution = json.loads(resolution_path.read_text(encoding="utf-8"))
    _boundary(source, "residual-11")
    _boundary(resolution, "CBTX resolution")

    if source.get("status") != (
        "PHASE1_FEATURE_TOURNAMENT_VALIDATION_RESIDUAL11_SCOPE_FROZEN"
    ):
        raise ValueError("residual-11 status changed")
    if (
        source.get("residualRows") != EXPECTED_SOURCE_ROWS
        or source.get("scopeKeySha256") != EXPECTED_SOURCE_DIGEST
    ):
        raise ValueError("residual-11 scope changed")
    if resolution.get("status") != (
        "PHASE1_FEATURE_TOURNAMENT_VALIDATION_"
        "CBTX_SYMBOL_CHANGE_RESOLUTION_COMPLETE"
    ):
        raise ValueError("CBTX resolution status changed")
    if (
        resolution.get("resolvedRows") != EXPECTED_RESOLVED_ROWS
        or resolution.get("resolvedKeySha256") != EXPECTED_RESOLUTION_DIGEST
    ):
        raise ValueError("CBTX resolution key changed")

    source_rows = source.get("rows")
    resolution_rows = resolution.get("resolutionRows")
    if not isinstance(source_rows, list) or len(source_rows) != EXPECTED_SOURCE_ROWS:
        raise ValueError("residual-11 rows changed")
    if (
        not isinstance(resolution_rows, list)
        or len(resolution_rows) != EXPECTED_RESOLVED_ROWS
    ):
        raise ValueError("CBTX resolution rows changed")
    if (
        _digest(source_rows) != EXPECTED_SOURCE_DIGEST
        or _digest(resolution_rows) != EXPECTED_RESOLUTION_DIGEST
    ):
        raise ValueError("input semantic keys changed")

    resolved = {_key(r) for r in resolution_rows}
    residual = [r for r in source_rows if _key(r) not in resolved]
    if (
        len(residual) != EXPECTED_RESIDUAL_ROWS
        or _digest(residual) != EXPECTED_RESIDUAL_DIGEST
    ):
        raise ValueError("residual-10 changed")
    if {str(r["ticker"]).upper() for r in residual} != EXPECTED_TICKERS:
        raise ValueError("residual-10 ticker set changed")

    for row in residual:
        category = str((row.get("evidenceAudit") or {}).get("category") or "")
        if category != "LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED":
            raise ValueError("residual-10 contains non-long-gap row")
        if row.get("candidateActionIds") or row.get("candidateActionTypes"):
            raise ValueError("residual-10 unexpectedly contains provider action")

    residual.sort(key=lambda r: int(r["eventNumber"]))
    out = {
        "schemaVersion": "1.0.0",
        "status": "PHASE1_FEATURE_TOURNAMENT_VALIDATION_RESIDUAL10_LONG_GAP_SCOPE_FROZEN",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "validationPerformanceOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceResidualRows": EXPECTED_SOURCE_ROWS,
        "subtractedCbtxRows": EXPECTED_RESOLVED_ROWS,
        "residualRows": EXPECTED_RESIDUAL_ROWS,
        "scopeKeySha256": EXPECTED_RESIDUAL_DIGEST,
        "tickers": sorted(EXPECTED_TICKERS),
        "rows": residual,
        "resolutionComplete": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--resolution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        source_path=args.source,
        resolution_path=args.resolution,
        output_path=args.output,
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "rows"},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
