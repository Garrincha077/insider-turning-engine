"""Build outcome-blind 2021-2022 Monster Winner extension feature matrix."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import research_market_event_audit_v2 as p0
import research_monster_winner_discovery as monster
import research_phase1_feature_tournament_stage_a as stage_a
import research_phase1_feature_tournament_validation_scope as validation_scope

EXTENSION_START = "2021-01-01"
EXTENSION_END = "2022-12-31"
DATA_BOUNDARY = "2022-12-30"
SEALED_YEAR = 2023
HORIZONS = (126, 252)
CANDIDATES = ("F3_DRAWDOWN_252", "F4_DISTANCE_BELOW")


def _market_paths_multi(
    roots: list[Path],
    prefix: str,
    years: range,
) -> list[Path]:
    result: list[Path] = []
    for year in years:
        matches: list[Path] = []
        for root in roots:
            matches.extend(root.rglob(f"{prefix}-{year}.csv"))
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one {prefix}-{year}.csv, got {len(matches)}"
            )
        result.append(matches[0])
    return result


def _load_cutpoints(stage_a_dir: Path) -> dict[str, Any]:
    path = stage_a_dir / "stage-a-cutpoints.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    for feature in ("F3_DRAWDOWN_252", "F4_DISTANCE_TO_BASIS", "DOLLAR_ADV_20"):
        if feature not in payload:
            raise ValueError(f"frozen cutpoint missing: {feature}")
    return payload


def run(
    *,
    sec_effective: Path,
    sec_revisions: Path,
    adjusted_root: Path,
    raw_roots: list[Path],
    stage_a_dir: Path,
    output: Path,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    if (adjusted_root / "2023").exists():
        raise ValueError("sealed 2023 adjusted market mounted")
    if any((root / "2023").exists() for root in raw_roots):
        raise ValueError("sealed 2023 raw market mounted")

    adjusted_paths = stage_a._market_paths(
        adjusted_root,
        "canonical-market",
        range(2016, 2023),
    )
    raw_paths = _market_paths_multi(
        raw_roots,
        "raw-feature-market",
        range(2016, 2023),
    )

    adjusted_db = output / "extension-adjusted.sqlite"
    raw_db = output / "extension-raw.sqlite"
    stage_a._build_market_db(adjusted_paths, adjusted_db)
    stage_a._build_market_db(raw_paths, raw_db)

    try:
        retained = validation_scope._candidate_stream(sec_effective)
        candidates = [
            dict(row)
            for row in retained
            if EXTENSION_START <= str(row["evaluationSession"]) <= EXTENSION_END
        ]
        if not candidates:
            raise ValueError("2021-2022 extension candidate stream is empty")

        issuers = {str(row["issuerCik"]) for row in candidates}
        revisions = stage_a._load_revisions(sec_revisions, issuers)
        calendar = xcals.get_calendar("XNYS")
        sessions = p0._expected_sessions()
        session_index = {day: idx for idx, day in enumerate(sessions)}
        data_boundary_idx = session_index.get(DATA_BOUNDARY)
        if data_boundary_idx is None:
            raise ValueError("2022 data boundary absent from XNYS calendar")

        adjusted_conn = sqlite3.connect(adjusted_db)
        raw_conn = sqlite3.connect(raw_db)
        adjusted_cache: dict[str, list[tuple[Any, ...]]] = {}
        raw_cache: dict[str, list[tuple[Any, ...]]] = {}
        matrix: list[dict[str, Any]] = []
        missing_entry = 0

        try:
            for source in candidates:
                evaluation_idx = int(source["evaluationIndex"])
                entry_idx = evaluation_idx + 1
                if entry_idx >= len(sessions):
                    continue
                entry = sessions[entry_idx]
                if int(entry[:4]) >= SEALED_YEAR:
                    continue

                ticker = str(source["ticker"]).upper()
                entry_row = adjusted_conn.execute(
                    "SELECT date,open,high,low,close,volume,trade_count,terminal "
                    "FROM market WHERE ticker=? AND date=?",
                    (ticker, entry),
                ).fetchone()
                if not stage_a._regular(entry_row):
                    missing_entry += 1
                    continue

                if ticker not in adjusted_cache:
                    adjusted_cache[ticker] = stage_a._regular_market_rows(
                        adjusted_conn, ticker
                    )
                if ticker not in raw_cache:
                    raw_cache[ticker] = stage_a._regular_market_rows(
                        raw_conn, ticker
                    )

                event = {
                    **source,
                    "entrySession": entry,
                    "eventNumber": len(matrix) + 1,
                }
                features = stage_a._event_features(
                    event=event,
                    issuer_rows=revisions.get(str(source["issuerCik"]), []),
                    adjusted_rows=adjusted_cache[ticker],
                    raw_rows=raw_cache[ticker],
                    calendar=calendar,
                )

                for horizon in HORIZONS:
                    target_idx = entry_idx + horizon
                    key = f"targetExitSession{horizon}"
                    mature_key = f"horizon{horizon}MatureAtBoundary"
                    if target_idx < len(sessions):
                        target = sessions[target_idx]
                    else:
                        target = ""
                    features[key] = target
                    features[mature_key] = bool(
                        target
                        and target_idx <= data_boundary_idx
                        and target <= DATA_BOUNDARY
                    )

                matrix.append(features)
        finally:
            adjusted_conn.close()
            raw_conn.close()

        cutpoints = _load_cutpoints(stage_a_dir)
        for row in matrix:
            row["F3_DRAWDOWN_252_GROUP"] = monster._membership(
                row,
                "F3_DRAWDOWN_252",
                cutpoints,
            ) or ""
            row["F4_DISTANCE_BELOW_GROUP"] = monster._membership(
                row,
                "F4_DISTANCE_BELOW",
                cutpoints,
            ) or ""

        counts_by_year = Counter(str(row["evaluationSession"])[:4] for row in matrix)
        mature126_by_year = Counter(
            str(row["evaluationSession"])[:4]
            for row in matrix
            if row["horizon126MatureAtBoundary"]
        )
        mature252_by_year = Counter(
            str(row["evaluationSession"])[:4]
            for row in matrix
            if row["horizon252MatureAtBoundary"]
        )

        fieldnames = list(matrix[0].keys())
        forbidden = ("futurereturn", "mfe", "monsterlabel", "outcome")
        lowered = " ".join(fieldnames).lower()
        if any(token in lowered for token in forbidden):
            raise ValueError("extension matrix contains forbidden outcome field")

        path = output / "monster-extension-feature-matrix-2021-2022.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(matrix)

        summary = {
            "schemaVersion": "1.0.0",
            "status": "MONSTER_MAX_EXISTING_DATA_EXTENSION_FEATURE_SCOPE_FROZEN",
            "researchOnly": True,
            "outcomesRead": False,
            "priceOutcomeFieldsRead": [],
            "monsterLabelsComputed": False,
            "knownSampleOnly": True,
            "oosOpened": False,
            "productionScoringChanged": False,
            "evaluationPeriod": [EXTENSION_START, EXTENSION_END],
            "marketDataBoundary": DATA_BOUNDARY,
            "events": len(matrix),
            "distinctIssuers": len({str(row["issuerCik"]) for row in matrix}),
            "missingExactEntry": missing_entry,
            "eventsByYear": dict(sorted(counts_by_year.items())),
            "mature126ByYear": dict(sorted(mature126_by_year.items())),
            "mature252ByYear": dict(sorted(mature252_by_year.items())),
            "mature126Events": sum(mature126_by_year.values()),
            "mature252Events": sum(mature252_by_year.values()),
            "rightCensored126Events": len(matrix) - sum(mature126_by_year.values()),
            "rightCensored252Events": len(matrix) - sum(mature252_by_year.values()),
            "candidateGroupCounts": {
                candidate: dict(
                    sorted(
                        Counter(
                            str(
                                row[
                                    "F3_DRAWDOWN_252_GROUP"
                                    if candidate == "F3_DRAWDOWN_252"
                                    else "F4_DISTANCE_BELOW_GROUP"
                                ]
                            )
                            for row in matrix
                        ).items()
                    )
                )
                for candidate in CANDIDATES
            },
            "cutpointsSource": "immutable Stage-A 2016-2018 cutpoints",
            "nextGate": (
                "Build performance-blind 126/252 continuity for only mature "
                "2021-2022 extension event-horizon rows, then open outcomes."
            ),
        }
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return summary
    finally:
        adjusted_db.unlink(missing_ok=True)
        raw_db.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sec-effective", type=Path, required=True)
    parser.add_argument("--sec-revisions", type=Path, required=True)
    parser.add_argument("--adjusted-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, action="append", required=True)
    parser.add_argument("--stage-a-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        sec_effective=args.sec_effective,
        sec_revisions=args.sec_revisions,
        adjusted_root=args.adjusted_root,
        raw_roots=args.raw_root,
        stage_a_dir=args.stage_a_dir,
        output=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
