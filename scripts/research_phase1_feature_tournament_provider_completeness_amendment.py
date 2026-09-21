"""Amend incomplete provider stock-merger semantics before confirmation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_ROWS = 13
EXPECTED_EVENTS = 7
EXPECTED_ACTIONS = 4
EXPECTED_ACTION_IDS = {
    "025514e5-df61-4736-abbd-958aef5d7747",
    "3f1999bc-0671-4ac9-832d-34a273de33b0",
    "5952fed5-9d9e-4228-b719-dab4e78cb1cc",
    "fd86b4fb-0687-4693-bf79-cbdef0e8bb19",
}


def _load_ledger(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {
            "eventNumber",
            "issuerCik",
            "ticker",
            "evaluationSession",
            "entrySession",
            "horizon",
            "targetExitSession",
            "state",
            "successorSymbol",
            "resolutionSource",
            "candidateActionTypes",
            "candidateActionIds",
        }
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Stage-B ledger missing amendment fields")
        rows = [dict(row) for row in reader]
    if len(rows) != 96760:
        raise ValueError("Stage-B ledger row count changed")
    return rows


def _load_evidence(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "contractId": (
            "phase1-feature-tournament-provider-completeness-"
            "primary-evidence-v1"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "finalResolutionContractCreated": False,
        "confirmationOutcomesOpened": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"primary evidence contract mismatch: {key}")
    scope = payload.get("scope")
    if scope != {
        "expectedRows": 13,
        "expectedActions": 4,
        "expectedEvents": 7,
        "evaluationYears": [2019, 2020],
        "discoveryOverlapRows": 0,
    }:
        raise ValueError("primary evidence scope changed")

    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or len(evidence) != EXPECTED_ACTIONS:
        raise ValueError("primary evidence action count changed")

    result: dict[str, dict[str, Any]] = {}
    for item in evidence:
        action_id = str(item["actionId"])
        if action_id in result:
            raise ValueError("duplicate primary evidence action")
        if action_id not in EXPECTED_ACTION_IDS:
            raise ValueError("unexpected provider action in amendment")
        effective = str(item["effectiveDate"])
        if not effective or int(effective[:4]) >= 2023:
            raise ValueError("amendment evidence crosses sealed OOS")
        if item["resolutionDecision"] != "TRANSFORMED_HOLDER_CONSIDERATION":
            raise ValueError("unsupported amendment decision")
        if item["resultState"] != "TRANSFORMED_HOLDER_CONSIDERATION":
            raise ValueError("unsupported amendment result state")
        if not item.get("transformationKind"):
            raise ValueError("amendment transformation kind missing")
        if not item.get("primaryEvidence"):
            raise ValueError("amendment lacks primary evidence")
        result[action_id] = item

    if set(result) != EXPECTED_ACTION_IDS:
        raise ValueError("primary evidence action set changed")
    return result


def _key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(row[field])
        for field in (
            "eventNumber",
            "issuerCik",
            "ticker",
            "evaluationSession",
            "entrySession",
            "horizon",
            "targetExitSession",
        )
    )


def _digest(rows: list[dict[str, Any]]) -> str:
    material = [
        {
            key: row[key]
            for key in (
                "eventNumber",
                "issuerCik",
                "ticker",
                "evaluationSession",
                "entrySession",
                "horizon",
                "targetExitSession",
                "resolutionDecision",
                "transformationKind",
                "successorSymbol",
                "successorSharesPerEntryShare",
                "cashPerEntryShare",
            )
        }
        for row in rows
    ]
    raw = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _resolution(
    row: dict[str, str],
    fact: dict[str, Any],
) -> dict[str, Any]:
    action_id = str(fact["actionId"])
    ids = [
        item
        for item in str(row.get("candidateActionIds") or "").split(";")
        if item
    ]
    if ids != [action_id]:
        raise ValueError("amendment action identity mismatch")
    if row["state"] != "TRANSFORMED_HOLDER_CONSIDERATION":
        raise ValueError("amendment row is not provider-transformed")
    if row["successorSymbol"]:
        raise ValueError("amendment row already has successor semantics")
    if row["resolutionSource"] != "provider":
        raise ValueError("amendment row is not provider-classified")
    action_types = set(
        filter(None, row["candidateActionTypes"].split(";"))
    )
    if not action_types.intersection(
        {"stock_mergers", "stock_and_cash_mergers"}
    ):
        raise ValueError("amendment row is not stock-merger classified")
    if str(row["issuerCik"]) != str(fact["issuerCik"]):
        raise ValueError("amendment issuer mismatch")
    if str(row["ticker"]).upper() != str(fact["ticker"]).upper():
        raise ValueError("amendment ticker mismatch")
    if str(row["evaluationSession"]) <= "2018-12-31":
        raise ValueError("amendment overlaps frozen discovery outcomes")
    if str(row["evaluationSession"]) > "2020-12-31":
        raise ValueError("amendment includes validation event")
    effective = str(fact["effectiveDate"])
    if not str(row["entrySession"]) < effective <= str(
        row["targetExitSession"]
    ):
        raise ValueError("amendment effective date outside event horizon")

    quantity = float(fact["successorSharesPerEntryShare"])
    cash = float(fact["cashPerEntryShare"])
    successor = str(fact.get("successorSymbol") or "").upper()
    if quantity > 0 and not successor:
        raise ValueError("stock amendment lacks successor")
    if quantity == 0 and cash <= 0:
        raise ValueError("cash amendment lacks consideration")

    result = {
        "eventNumber": int(row["eventNumber"]),
        "issuerCik": str(row["issuerCik"]),
        "ticker": str(row["ticker"]).upper(),
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": str(row["entrySession"]),
        "horizon": int(row["horizon"]),
        "targetExitSession": str(row["targetExitSession"]),
        "sourceInitialState": str(row["state"]),
        "sourceResolutionSource": str(row["resolutionSource"]),
        "sourceActionIds": [action_id],
        "effectiveDate": effective,
        "resolutionDecision": str(fact["resolutionDecision"]),
        "transformationKind": str(fact["transformationKind"]),
        "resultState": str(fact["resultState"]),
        "successorSymbol": successor,
        "successorSharesPerEntryShare": quantity,
        "cashPerEntryShare": cash,
        "primaryEvidenceAccessions": [
            str(item["accession"])
            for item in fact["primaryEvidence"]
        ],
        "classificationSource": (
            "PRIMARY_EVIDENCE_PROVIDER_COMPLETENESS_AMENDMENT"
        ),
    }
    if fact.get("holderPolicy"):
        result["holderPolicy"] = str(fact["holderPolicy"])
    return result


def run(
    *,
    ledger_path: Path,
    evidence_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    ledger = _load_ledger(ledger_path)
    evidence = _load_evidence(evidence_path)

    target = []
    for row in ledger:
        ids = [
            item
            for item in str(row.get("candidateActionIds") or "").split(";")
            if item
        ]
        if len(ids) == 1 and ids[0] in evidence:
            target.append(row)

    if len(target) != EXPECTED_ROWS:
        raise ValueError("provider completeness row count changed")
    if len({_key(row) for row in target}) != EXPECTED_ROWS:
        raise ValueError("duplicate provider completeness key")
    if len({row["eventNumber"] for row in target}) != EXPECTED_EVENTS:
        raise ValueError("provider completeness event count changed")

    resolutions = [
        _resolution(row, evidence[row["candidateActionIds"]])
        for row in target
    ]
    resolutions.sort(
        key=lambda row: (row["eventNumber"], row["horizon"])
    )

    action_counts = Counter(
        row["sourceActionIds"][0]
        for row in resolutions
    )
    expected_counts = {
        "025514e5-df61-4736-abbd-958aef5d7747": 5,
        "3f1999bc-0671-4ac9-832d-34a273de33b0": 4,
        "5952fed5-9d9e-4228-b719-dab4e78cb1cc": 3,
        "fd86b4fb-0687-4693-bf79-cbdef0e8bb19": 1,
    }
    if dict(action_counts) != expected_counts:
        raise ValueError("provider completeness action partition changed")

    ticker_counts = Counter(row["ticker"] for row in resolutions)
    if dict(ticker_counts) != {
        "MGYR": 1,
        "PAAC": 3,
        "QES": 4,
        "WSTL": 5,
    }:
        raise ValueError("provider completeness ticker partition changed")

    payload = {
        "schemaVersion": "1.0.0",
        "status": (
            "PHASE1_FEATURE_TOURNAMENT_PROVIDER_COMPLETENESS_"
            "AMENDMENT_COMPLETE"
        ),
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "featureOutcomesRead": False,
        "confirmationOutcomesOpened": False,
        "validationOpened": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceLedgerRows": len(ledger),
        "amendedRows": len(resolutions),
        "amendedEvents": len(
            {row["eventNumber"] for row in resolutions}
        ),
        "amendedActions": len(action_counts),
        "discoveryOverlapRows": sum(
            row["evaluationSession"] <= "2018-12-31"
            for row in resolutions
        ),
        "validationEventRows": sum(
            row["evaluationSession"] >= "2021-01-01"
            for row in resolutions
        ),
        "actionCounts": dict(sorted(action_counts.items())),
        "tickerCounts": dict(sorted(ticker_counts.items())),
        "amendmentKeySha256": _digest(resolutions),
        "resolutionRows": resolutions,
        "finalStageB210ContractMutated": False,
        "overlayRequiredForPerformanceValuation": True,
    }
    if payload["discoveryOverlapRows"] != 0:
        raise ValueError("amendment would alter discovery outcomes")
    if payload["validationEventRows"] != 0:
        raise ValueError("amendment would open validation events")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        ledger_path=args.ledger,
        evidence_path=args.evidence,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key != "resolutionRows"
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
