"""Audit Monster max-existing-data extension continuity without outcomes."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import research_phase1_security_continuity_ledger as continuity
import research_phase1_security_gap_diagnostics as gaps

SEALED_YEAR = 2023
GAP_THRESHOLD = 10
HORIZONS = (126, 252)


def _load_feature_scope(
    csv_path: Path,
    summary_path: Path,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    summary=json.loads(summary_path.read_text(encoding="utf-8"))
    required={
        "status":"MONSTER_MAX_EXISTING_DATA_EXTENSION_FEATURE_SCOPE_FROZEN",
        "outcomesRead":False,
        "priceOutcomeFieldsRead":[],
        "monsterLabelsComputed":False,
        "knownSampleOnly":True,
        "oosOpened":False,
        "productionScoringChanged":False,
        "evaluationPeriod":["2021-01-01","2022-12-31"],
        "marketDataBoundary":"2022-12-30",
    }
    for key,expected in required.items():
        if summary.get(key)!=expected:
            raise ValueError(f"extension feature scope mismatch: {key}")
    with csv_path.open(encoding="utf-8",newline="") as stream:
        rows=[dict(r) for r in csv.DictReader(stream)]
    if len(rows)!=int(summary["events"]):
        raise ValueError("extension feature row count changed")
    return summary,rows


def _load_actions(path: Path) -> list[dict[str, Any]]:
    payload=json.loads(path.read_text(encoding="utf-8"))
    if payload.get("performanceRead") is not False:
        raise ValueError("corporate actions are not performance-blind")
    if payload.get("oosOpened") is not False:
        raise ValueError("corporate actions opened OOS")
    rows=payload.get("actions")
    if not isinstance(rows,list):
        raise ValueError("corporate action inventory missing actions")
    return rows


def _provider_terms_complete(candidate_rows: list[dict[str, Any]]) -> bool:
    if len(candidate_rows)!=1:
        return False
    action=candidate_rows[0]
    bucket=str(action.get("bucket") or "")
    try:
        if bucket=="cash_mergers":
            return float(action["rate"])>=0
        if bucket=="stock_mergers":
            return (
                float(action["acquiree_rate"])>0
                and float(action["acquirer_rate"])>0
                and bool(str(action.get("acquirer_symbol") or "").strip())
            )
        if bucket=="stock_and_cash_mergers":
            return (
                float(action["acquiree_rate"])>0
                and float(action["acquirer_rate"])>0
                and float(action["cash_rate"])>=0
                and bool(str(action.get("acquirer_symbol") or "").strip())
            )
        if bucket=="redemptions":
            return float(action["rate"])>=0
    except (KeyError,TypeError,ValueError):
        return False
    return False


def _mature_rows(rows: list[dict[str,str]]) -> list[dict[str,Any]]:
    out=[]
    for source in rows:
        for horizon in HORIZONS:
            mature=str(source.get(f"horizon{horizon}MatureAtBoundary") or "").lower()=="true"
            if not mature:
                continue
            target=str(source.get(f"targetExitSession{horizon}") or "")
            if not target or target>"2022-12-30":
                raise ValueError("mature extension row crossed data boundary")
            out.append({
                "eventNumber":int(source["eventNumber"]),
                "issuerCik":str(source["issuerCik"]),
                "ticker":str(source["ticker"]).upper(),
                "evaluationSession":str(source["evaluationSession"]),
                "entrySession":str(source["entrySession"]),
                "horizon":horizon,
                "targetExitSession":target,
                "F3_DRAWDOWN_252_GROUP":str(source.get("F3_DRAWDOWN_252_GROUP") or ""),
                "F4_DISTANCE_BELOW_GROUP":str(source.get("F4_DISTANCE_BELOW_GROUP") or ""),
            })
    return out


def run(
    *,
    feature_csv: Path,
    feature_summary: Path,
    corporate_actions: Path,
    market_root: Path,
    output: Path,
) -> dict[str,Any]:
    output.mkdir(parents=True,exist_ok=True)
    summary,feature_rows=_load_feature_scope(feature_csv,feature_summary)
    scope=_mature_rows(feature_rows)
    actions=_load_actions(corporate_actions)
    indexed=continuity._index_actions(actions)

    calendar=xcals.get_calendar("XNYS")
    sessions=[
        str(value.date())
        for value in calendar.sessions_in_range("2016-01-01","2022-12-30")
    ]
    session_index={day:i for i,day in enumerate(sessions)}
    wanted={str(r["ticker"]).upper() for r in scope}
    observed=gaps._regular_observed_indices(
        market_root,
        wanted,
        session_index,
    )

    audit=[]
    for raw in scope:
        ticker=str(raw["ticker"]).upper()
        entry=str(raw["entrySession"])
        target=str(raw["targetExitSession"])
        entry_idx=session_index.get(entry)
        target_idx=session_index.get(target)
        if entry_idx is None or target_idx is None:
            raise ValueError("extension row outside frozen XNYS calendar")

        candidates,adjusted=continuity._candidate_actions(
            indexed.get(ticker,[]),
            entry,
            target,
        )
        state,successor=continuity._provider_state(candidates)
        source="provider"
        if (
            state=="TRANSFORMED_HOLDER_CONSIDERATION"
            and not _provider_terms_complete(candidates)
        ):
            state="UNRESOLVED_CONTINUITY"
            successor=None
            source="provider_incomplete_terms"

        gap=continuity._max_internal_gap(
            observed.get(ticker,[]),
            entry_idx,
            target_idx,
        )
        long_gap=gap>=GAP_THRESHOLD
        if long_gap and state=="PRICE_CONTINUOUS_ADJUSTED":
            state="UNRESOLVED_CONTINUITY"
            source="long_internal_gap"

        audit.append({
            **raw,
            "state":state,
            "successorSymbol":successor or "",
            "resolutionSource":source,
            "candidateActionTypes":";".join(sorted({
                str(a.get("bucket") or "")
                for a in candidates if a.get("bucket")
            })),
            "candidateActionIds":";".join(
                str(a.get("id") or "") for a in candidates
            ),
            "adjustedActionTypes":";".join(sorted({
                str(a.get("bucket") or "")
                for a in adjusted if a.get("bucket")
            })),
            "maxInternalGapSessions":gap,
            "longInternalGapCandidate":long_gap,
        })

    state_counts=Counter(r["state"] for r in audit)
    source_counts=Counter(r["resolutionSource"] for r in audit)
    horizon_counts=Counter(str(r["horizon"]) for r in audit)
    unresolved=[r for r in audit if r["state"]=="UNRESOLVED_CONTINUITY"]
    unresolved_by_horizon=Counter(str(r["horizon"]) for r in unresolved)

    path=output/"monster-extension-continuity-audit.csv"
    with path.open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(audit[0]))
        writer.writeheader()
        writer.writerows(audit)

    result={
        "schemaVersion":"1.0.0",
        "status":"MONSTER_MAX_EXISTING_DATA_EXTENSION_CONTINUITY_AUDITED",
        "researchOnly":True,
        "performanceRead":False,
        "priceFieldsRead":[],
        "featureOutcomesRead":False,
        "knownSampleOnly":True,
        "oosOpened":False,
        "productionScoringChanged":False,
        "sourceFeatureEvents":int(summary["events"]),
        "matureHorizonRows":len(audit),
        "horizonRowCounts":dict(sorted(horizon_counts.items())),
        "continuityStateCounts":dict(sorted(state_counts.items())),
        "resolutionSourceCounts":dict(sorted(source_counts.items())),
        "longGapRows":sum(bool(r["longInternalGapCandidate"]) for r in audit),
        "unresolvedRows":len(unresolved),
        "unresolvedByHorizon":dict(sorted(unresolved_by_horizon.items())),
        "providerSemanticsCompletenessChecked":True,
        "performanceStageBlocked":len(unresolved)>0,
        "nextGate":(
            "Reuse frozen prior evidence where semantic keys/actions match; "
            "leave any genuinely new unresolved 252-session rows fail-closed "
            "until primary evidence is frozen."
        ),
    }
    (output/"summary.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)+"\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--feature-csv",type=Path,required=True)
    parser.add_argument("--feature-summary",type=Path,required=True)
    parser.add_argument("--corporate-actions",type=Path,required=True)
    parser.add_argument("--market-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(
        feature_csv=args.feature_csv,
        feature_summary=args.feature_summary,
        corporate_actions=args.corporate_actions,
        market_root=args.market_root,
        output=args.output,
    ),indent=2,sort_keys=True))


if __name__=="__main__":
    main()
