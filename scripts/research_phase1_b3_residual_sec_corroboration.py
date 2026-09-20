"""Performance-blind bounded SEC corroboration for residual B3 continuity rows.

Consumes only the frozen residual continuity set, frozen long-gap diagnostics,
the bounded 2016-2022 original P/S PIT corpus, and bounded corporate-action
metadata. It records nearest same-issuer PIT ticker observations around each
continuity pivot. It does NOT classify or mutate continuity states.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

SEALED_YEAR = 2023


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_residual(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "B3_CONTINUITY_RESOLUTION_CANDIDATES_COMPLETE":
        raise ValueError("unexpected B3 candidate source status")
    if payload.get("performanceRead") is not False:
        raise ValueError("candidate source is not performance-blind")
    if payload.get("oosOpened") is not False:
        raise ValueError("candidate source opened OOS")
    rows = payload.get("residualRows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("no residual B3 continuity rows")
    if len(rows) != int(payload["residualUnresolvedRows"]):
        raise ValueError("residual row count mismatch")
    for row in rows:
        for field in ("evaluationSession", "entrySession", "targetExitSession"):
            if int(str(row[field])[:4]) >= SEALED_YEAR:
                raise ValueError("sealed OOS boundary violated by residual row")
    return rows


def _row_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(row["eventNumber"]),
        str(row["issuerCik"]),
        str(row["ticker"]),
        str(row["evaluationSession"]),
        str(row["entrySession"]),
        str(row["horizon"]),
        str(row["targetExitSession"]),
    )


def _load_gaps(path: Path) -> dict[tuple[str, ...], dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    result: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = (
            str(row["eventNumber"]),
            str(row["issuerCik"]),
            str(row["ticker"]),
            str(row.get("evaluationSession") or ""),
            str(row["entrySession"]),
            str(row["horizon"]),
            str(row["targetExitSession"]),
        )
        result[key] = row
    return result


def _load_actions(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("performanceRead") is not False:
        raise ValueError("corporate actions are not performance-blind")
    if payload.get("oosOpened") is not False:
        raise ValueError("corporate actions opened OOS")
    return {str(row["id"]): row for row in payload.get("actions", [])}


def _observations(
    pit_root: Path,
    wanted_issuers: set[str],
) -> dict[str, list[dict[str, str]]]:
    by_issuer: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for path in sorted(pit_root.rglob("canonical-research.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                row = json.loads(line)
                issuer = row.get("issuer") or {}
                cik = str(issuer.get("cik") or "")
                if cik not in wanted_issuers:
                    continue
                timestamps = row.get("timestamps") or {}
                knowledge = str(timestamps.get("knowledgeAt") or "")
                accepted = str(timestamps.get("acceptedAt") or knowledge)
                if not knowledge or int(knowledge[:4]) >= SEALED_YEAR:
                    raise ValueError("sealed or missing PIT knowledge timestamp")
                if accepted != knowledge:
                    raise ValueError("PIT clock differs from accepted timestamp")
                source = row.get("source") or {}
                accession = str(source.get("accessionNumber") or "")
                if not accession:
                    raise ValueError("PIT observation missing accession")
                ticker = str(issuer.get("ticker") or "").strip().upper()
                observation = {
                    "issuerCik": cik,
                    "ticker": ticker,
                    "knowledgeAt": knowledge,
                    "accession": accession,
                }
                prior = by_issuer[cik].get(accession)
                if prior is not None and prior != observation:
                    raise ValueError("conflicting PIT identity within one accession")
                by_issuer[cik][accession] = observation

    output: dict[str, list[dict[str, str]]] = {}
    for cik, values in by_issuer.items():
        output[cik] = sorted(
            values.values(),
            key=lambda row: (row["knowledgeAt"], row["accession"]),
        )
    return output


def _nearest(
    observations: list[dict[str, str]],
    pivot: str,
) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    pivot_dt = _dt(pivot + "T23:59:59+00:00") if len(pivot) == 10 else _dt(pivot)
    before = None
    after = None
    for row in observations:
        when = _dt(row["knowledgeAt"])
        if when <= pivot_dt:
            before = row
        elif after is None:
            after = row
            break
    return before, after


def _pivot(
    row: dict[str, Any],
    gaps: dict[tuple[str, ...], dict[str, str]],
    actions: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    if str(row["resolutionSource"]) == "long_internal_gap":
        full = _row_key(row)
        gap = gaps.get(full)
        if gap is None:
            short = (
                full[0],
                full[1],
                full[2],
                "",
                full[4],
                full[5],
                full[6],
            )
            gap = gaps.get(short)
        if gap is None:
            raise ValueError("residual long-gap row absent from frozen gap diagnostics")
        return str(gap["firstMissingSession"]), "FROZEN_LONG_GAP_START"

    ids = [
        value
        for value in str(row.get("candidateActionIds") or "").split(";")
        if value
    ]
    dates = sorted(
        {
            str(actions[action_id].get("actionDate") or "")
            for action_id in ids
            if action_id in actions and actions[action_id].get("actionDate")
        }
    )
    if not dates:
        raise ValueError("provider residual has no bounded action date")
    return dates[0], "FROZEN_PROVIDER_ACTION_DATE"


def run(
    *,
    residual_path: Path,
    gaps_path: Path,
    corporate_actions_path: Path,
    pit_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    residual = _load_residual(residual_path)
    gaps = _load_gaps(gaps_path)
    actions = _load_actions(corporate_actions_path)
    wanted = {str(row["issuerCik"]) for row in residual}
    observations = _observations(pit_root, wanted)

    evidence: list[dict[str, Any]] = []
    statuses: Counter[str] = Counter()
    issuers_with_evidence: set[str] = set()

    for row in residual:
        pivot, pivot_kind = _pivot(row, gaps, actions)
        before, after = _nearest(observations.get(str(row["issuerCik"]), []), pivot)
        expected = str(row["ticker"]).upper()

        if before is None and after is None:
            status = "NO_BOUNDED_PS_PIT_OBSERVATION"
        elif before is None:
            status = (
                "AFTER_ONLY_EXPECTED_TICKER"
                if after and after["ticker"] == expected
                else "AFTER_ONLY_DIFFERENT_TICKER"
            )
        elif after is None:
            status = (
                "BEFORE_ONLY_EXPECTED_TICKER"
                if before["ticker"] == expected
                else "BEFORE_ONLY_DIFFERENT_TICKER"
            )
        else:
            before_match = before["ticker"] == expected
            after_match = after["ticker"] == expected
            if before_match and after_match:
                status = "EXPECTED_TICKER_BOTH_SIDES"
            elif before_match and not after_match:
                status = "TICKER_CHANGED_AFTER_PIVOT"
            elif not before_match and after_match:
                status = "EXPECTED_TICKER_ONLY_AFTER"
            elif before["ticker"] == after["ticker"]:
                status = "SAME_DIFFERENT_TICKER_BOTH_SIDES"
            else:
                status = "DIFFERENT_TICKERS_ACROSS_PIVOT"

        statuses[status] += 1
        if before or after:
            issuers_with_evidence.add(str(row["issuerCik"]))
        evidence.append(
            {
                **row,
                "pivotDate": pivot,
                "pivotKind": pivot_kind,
                "corroborationStatus": status,
                "beforeObservation": before,
                "afterObservation": after,
                "continuityStateChanged": False,
                "finalResolutionAllowedFromThisStage": False,
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "b3-residual-sec-corroboration.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_RESIDUAL_SEC_CORROBORATION_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "marketDataRead": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "residualRows": len(residual),
        "residualIssuers": len(wanted),
        "issuersWithAnyBoundedPsPitEvidence": len(issuers_with_evidence),
        "statusCounts": dict(sorted(statuses.items())),
        "continuityStatesChanged": 0,
        "finalResolutionContractCreated": False,
        "correctedPerformanceOpened": False,
        "interpretation": (
            "Bounded P/S PIT observations are corroborative identity evidence only. "
            "They do not by themselves prove holder continuity across bankruptcy, "
            "recapitalization or security replacement."
        ),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--residual", type=Path, required=True)
    parser.add_argument("--gaps", type=Path, required=True)
    parser.add_argument("--corporate-actions", type=Path, required=True)
    parser.add_argument("--pit-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                residual_path=args.residual,
                gaps_path=args.gaps,
                corporate_actions_path=args.corporate_actions,
                pit_root=args.pit_root,
                output_dir=args.output_dir,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
