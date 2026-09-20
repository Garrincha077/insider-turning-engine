"""Aggregate every frozen B3 continuity classification into one final contract."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

EXPECTED_SOURCE_ROWS = 264
EXPECTED_BASE_ROWS = 173
EXPECTED_LATER_ROWS = 91

SOURCE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": "provider",
        "release": "research-phase1-b3-provider-primary-resolution-v1",
        "asset": "b3-provider-primary-resolution.json",
        "assetSha256": "sha256:4f37195c3fda7a2db119f7391c8dbad4571d928aca80b78bc6e5630cdc48dfc1",
        "status": "B3_PROVIDER_PRIMARY_RESOLUTION_COMPLETE",
        "countField": "resolvedProviderRows",
        "count": 4,
    },
    {
        "name": "spac_unit_1",
        "release": "research-phase1-b3-spac-unit-primary-resolution-v1",
        "asset": "b3-spac-unit-primary-resolution.json",
        "assetSha256": "sha256:0a6e5f9b271508959f3628babc86965254fe715720790958fd5883202e612065",
        "status": "B3_SPAC_UNIT_PRIMARY_RESOLUTION_COMPLETE",
        "countField": "resolvedRows",
        "count": 4,
    },
    {
        "name": "one_sided",
        "release": "research-phase1-b3-one-sided-primary-resolution-v1",
        "asset": "b3-one-sided-primary-resolution.json",
        "assetSha256": "sha256:2b4e30dcac2d032e9f27495f72e67ed1cb70fc14d11ed58abe8d4e2a73d5c45b",
        "status": "B3_ONE_SIDED_PRIMARY_RESOLUTION_COMPLETE",
        "countField": "resolvedRows",
        "count": 20,
    },
    {
        "name": "spac_unit_2",
        "release": "research-phase1-b3-spac-unit2-primary-resolution-v1",
        "asset": "b3-spac-unit2-primary-resolution.json",
        "assetSha256": "sha256:1a4e0b9fb67ce72a80d49b39ec827b3ad2ca8e5ce53ca36bcdf44470bf2ecb04",
        "status": "B3_SPAC_UNIT2_PRIMARY_RESOLUTION_COMPLETE",
        "countField": "resolvedRows",
        "count": 8,
    },
    {
        "name": "multiclass_reorg",
        "release": "research-phase1-b3-multiclass-reorg-primary-resolution-v1",
        "asset": "b3-multiclass-reorg-primary-resolution.json",
        "assetSha256": "sha256:a844ea830b9503a045b55a490c30b9e3cd77456974b741a696f16617caf75969",
        "status": "B3_MULTICLASS_REORG_PRIMARY_RESOLUTION_COMPLETE",
        "countField": "resolvedRows",
        "count": 12,
    },
    {
        "name": "ordinary_common",
        "release": "research-phase1-b3-common-security-primary-resolution-v1",
        "asset": "b3-common-security-primary-resolution.json",
        "assetSha256": "sha256:fec6e91a78c665686d5a00baa1baef9a9c6493c4bf53841e8b39bc0e20cc2ac4",
        "status": "B3_COMMON_SECURITY_PRIMARY_RESOLUTION_COMPLETE",
        "countField": "resolvedRows",
        "count": 19,
    },
    {
        "name": "surviving_unit",
        "release": "research-phase1-b3-surviving-unit-primary-resolution-v1",
        "asset": "b3-surviving-unit-primary-resolution.json",
        "assetSha256": "sha256:65ce412c1bee4abdb0e47851f13afa9c8cfa2abd33190c8ac401da29c5c5c8f9",
        "status": "B3_SURVIVING_UNIT_PRIMARY_RESOLUTION_COMPLETE",
        "countField": "resolvedRows",
        "count": 11,
    },
    {
        "name": "final_residual13",
        "release": "research-phase1-b3-final-residual13-resolution-v1",
        "asset": "b3-final-residual13-resolution.json",
        "assetSha256": "sha256:6ac4dc4adee77e32747ad4e536fec3036c99c23bb664f3ccf5be2b4ab5b4981e",
        "status": "B3_FINAL_RESIDUAL13_PRIMARY_RESOLUTION_COMPLETE",
        "countField": "resolvedRows",
        "count": 13,
    },
)

MULTISOURCE_RELEASE = "research-phase1-b3-residual-multisource-v1"
MULTISOURCE_ASSET = "b3-residual-multisource-synthesis.json"
MULTISOURCE_ASSET_SHA256 = (
    "sha256:b88512259b21b31b1defa63328cba4f2e56ba32f6fbf071452ff32251777f56a"
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("source payload must be a JSON object")
    return payload


def _assert_research_boundary(payload: dict[str, Any], label: str) -> None:
    if payload.get("researchOnly") is not True:
        raise ValueError(f"{label} is not research-only")
    if payload.get("performanceRead") is not False:
        raise ValueError(f"{label} read performance")
    if payload.get("priceFieldsRead") != []:
        raise ValueError(f"{label} read price fields")
    if payload.get("oosOpened") is not False:
        raise ValueError(f"{label} opened OOS")
    if payload.get("productionScoringChanged") is not False:
        raise ValueError(f"{label} changed production scoring")
    if payload.get("correctedPerformanceOpened") is not False:
        raise ValueError(f"{label} opened corrected performance")


def _annotate(
    row: dict[str, Any],
    *,
    source_name: str,
    source_release: str,
) -> dict[str, Any]:
    out = dict(row)
    out["classificationSource"] = source_name
    out["classificationSourceRelease"] = source_release
    return out


def _load_multisource(path: Path) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    payload = _load_json(path)
    if payload.get("status") != "B3_RESIDUAL_MULTISOURCE_SYNTHESIS_COMPLETE":
        raise ValueError("unexpected multisource status")
    _assert_research_boundary(payload, "multisource")
    if int(payload.get("sourceUnresolvedRows", -1)) != EXPECTED_SOURCE_ROWS:
        raise ValueError("multisource source count changed")
    if int(payload.get("combinedCandidateRows", -1)) != EXPECTED_BASE_ROWS:
        raise ValueError("multisource base candidate count changed")
    if int(payload.get("residualUnresolvedRows", -1)) != EXPECTED_LATER_ROWS:
        raise ValueError("multisource residual count changed")

    base_rows = payload.get("combinedCandidateRowsData")
    residual_rows = payload.get("residualRows")
    if not isinstance(base_rows, list) or len(base_rows) != EXPECTED_BASE_ROWS:
        raise ValueError("invalid multisource base rows")
    if not isinstance(residual_rows, list) or len(residual_rows) != EXPECTED_LATER_ROWS:
        raise ValueError("invalid multisource residual rows")
    if base._key_digest(base_rows) != payload.get("combinedCandidateKeySha256"):
        raise ValueError("multisource base key digest changed")
    if base._key_digest(residual_rows) != payload.get("residualKeySha256"):
        raise ValueError("multisource residual key digest changed")

    base_keys = {base._row_key(row) for row in base_rows}
    residual_keys = {base._row_key(row) for row in residual_rows}
    if len(base_keys) != EXPECTED_BASE_ROWS:
        raise ValueError("duplicate key in multisource base rows")
    if len(residual_keys) != EXPECTED_LATER_ROWS:
        raise ValueError("duplicate key in multisource residual rows")
    if base_keys & residual_keys:
        raise ValueError("multisource base and residual scopes overlap")
    if len(base_keys | residual_keys) != EXPECTED_SOURCE_ROWS:
        raise ValueError("multisource partition does not cover 264 rows")
    if base._key_digest([*base_rows, *residual_rows]) != payload.get(
        "frozenScopeKeySha256"
    ):
        raise ValueError("multisource partition differs from frozen 264-row scope")
    return payload, base_rows, residual_rows


def _load_later(
    path: Path,
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    payload = _load_json(path)
    if payload.get("status") != spec["status"]:
        raise ValueError(f"unexpected status for {spec['name']}")
    _assert_research_boundary(payload, str(spec["name"]))
    if int(payload.get(str(spec["countField"]), -1)) != int(spec["count"]):
        raise ValueError(f"row count changed for {spec['name']}")
    rows = payload.get("resolutionRows")
    if not isinstance(rows, list) or len(rows) != int(spec["count"]):
        raise ValueError(f"invalid resolution rows for {spec['name']}")
    digest = base._key_digest(rows)
    if digest != payload.get("resolutionKeySha256"):
        raise ValueError(f"resolution key digest changed for {spec['name']}")
    if len({base._row_key(row) for row in rows}) != len(rows):
        raise ValueError(f"duplicate resolution key in {spec['name']}")
    return rows


def _validate_final_rows(rows: list[dict[str, Any]]) -> Counter[str]:
    if len(rows) != EXPECTED_SOURCE_ROWS:
        raise ValueError("final contract does not contain 264 rows")
    if len({base._row_key(row) for row in rows}) != EXPECTED_SOURCE_ROWS:
        raise ValueError("final contract contains duplicate keys")

    decisions: Counter[str] = Counter()
    multi_component_rows = 0
    for row in rows:
        decision = str(row.get("resolutionDecision") or "")
        result_state = str(row.get("resultState") or "")
        if not decision or not result_state:
            raise ValueError("final resolution row lacks decision/state")
        decisions[decision] += 1
        if decision == "TRANSFORMED_MULTI_COMPONENT_CONSIDERATION":
            multi_component_rows += 1
            basket = row.get("basket")
            if not isinstance(basket, list) or len(basket) != 2:
                raise ValueError("multi-component resolution lost its basket")
            symbols = {str(item.get("symbol") or "").upper() for item in basket}
            if symbols != {"MIMO", "MIMO WS"}:
                raise ValueError("NBA.U basket symbols changed")
    if multi_component_rows != 1:
        raise ValueError("final contract must preserve exactly one multi-component row")
    return decisions


def aggregate(
    *,
    multisource_path: Path,
    later_paths: list[Path],
    output_path: Path,
) -> dict[str, Any]:
    if len(later_paths) != len(SOURCE_SPECS):
        raise ValueError("wrong number of later-resolution inputs")

    multisource, base_rows, residual_rows = _load_multisource(multisource_path)
    residual_keys = {base._row_key(row) for row in residual_rows}

    later_rows: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = [
        {
            "name": "multisource_base",
            "release": MULTISOURCE_RELEASE,
            "asset": MULTISOURCE_ASSET,
            "assetSha256": MULTISOURCE_ASSET_SHA256,
            "rows": EXPECTED_BASE_ROWS,
            "keySha256": multisource["combinedCandidateKeySha256"],
        }
    ]

    for path, spec in zip(later_paths, SOURCE_SPECS, strict=True):
        rows = _load_later(path, spec)
        later_rows.extend(
            _annotate(
                row,
                source_name=str(spec["name"]),
                source_release=str(spec["release"]),
            )
            for row in rows
        )
        provenance.append(
            {
                "name": spec["name"],
                "release": spec["release"],
                "asset": spec["asset"],
                "assetSha256": spec["assetSha256"],
                "rows": spec["count"],
                "keySha256": base._key_digest(rows),
            }
        )

    if len(later_rows) != EXPECTED_LATER_ROWS:
        raise ValueError("later-resolution rows do not sum to 91")
    later_keys = {base._row_key(row) for row in later_rows}
    if len(later_keys) != EXPECTED_LATER_ROWS:
        raise ValueError("later-resolution releases contain duplicate keys")
    if later_keys != residual_keys:
        raise ValueError("later-resolution keys differ from frozen residual-91 scope")

    annotated_base = [
        _annotate(
            row,
            source_name="multisource_base",
            source_release=MULTISOURCE_RELEASE,
        )
        for row in base_rows
    ]
    final_rows = [*annotated_base, *later_rows]
    final_key_digest = base._key_digest(final_rows)
    if final_key_digest != multisource["frozenScopeKeySha256"]:
        raise ValueError("final 264-row union differs from frozen source scope")

    decisions = _validate_final_rows(final_rows)
    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_FINAL_CONTINUITY_CONTRACT_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": EXPECTED_SOURCE_ROWS,
        "classifiedRows": EXPECTED_SOURCE_ROWS,
        "unresolvedRows": 0,
        "classifiedKeySha256": final_key_digest,
        "frozenScopeKeySha256": multisource["frozenScopeKeySha256"],
        "resolutionDecisionCounts": dict(sorted(decisions.items())),
        "sourceProvenance": provenance,
        "resolutionRows": final_rows,
        "finalResolutionContractCreated": True,
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
    parser.add_argument("--multisource", type=Path, required=True)
    parser.add_argument(
        "--later",
        type=Path,
        action="append",
        required=True,
        help="Supply exactly eight later-resolution JSONs in frozen source order.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(
        multisource_path=args.multisource,
        later_paths=args.later,
        output_path=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
