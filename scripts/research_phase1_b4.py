"""Phase-1 B4 development baseline: canonical B1 opportunistic purchase AND B2 cluster.

Research only. B4 is the predeclared intersection benchmark. A B4 event exists only
when an identity-eligible B1 event and an identity-eligible B2 event occur for the
same issuer CIK on the same XNYS evaluation session. The intersection is formed
before the common 20-session issuer-level deduplication rule, so neither component's
standalone deduplication can create or remove a joint event.

Selection is development-only (2016-2020 XNYS evaluation sessions); outcomes use
2016-2022 market data and never read 2023+; production scoring is untouched.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import research_market_event_audit as v1
import research_market_event_audit_v2 as p0
import research_phase1_b0 as b0
import research_phase1_b1 as b1
import research_phase1_b2 as b2
import research_phase1_b2_fast as b2_fast

DEDUP_SESSIONS = 20
PRIMARY_HORIZON = 126


def _intersect_events(
    b1_events: list[dict[str, Any]], b2_events: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Form the exact issuer/evaluation-session B1 ∩ B2 event set."""

    diag: dict[str, int] = defaultdict(int)
    b1_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for event in b1_events:
        key = (str(event["issuerCik"]), str(event["evaluationSession"]))
        if key in b1_by_key:
            raise ValueError(f"duplicate B1 issuer-session event: {key}")
        b1_by_key[key] = event

    b2_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for event in b2_events:
        key = (str(event["issuerCik"]), str(event["evaluationSession"]))
        if key in b2_by_key:
            raise ValueError(f"duplicate B2 issuer-session event: {key}")
        b2_by_key[key] = event

    diag["b1IdentityEligibleEvents"] = len(b1_by_key)
    diag["b2IdentityEligibleEvents"] = len(b2_by_key)
    common_keys = sorted(
        set(b1_by_key) & set(b2_by_key),
        key=lambda key: (key[1], key[0]),
    )
    diag["exactIssuerSessionIntersections"] = len(common_keys)

    combined: list[dict[str, Any]] = []
    for key in common_keys:
        opportunistic = b1_by_key[key]
        cluster = b2_by_key[key]
        b1_ticker = str(opportunistic["ticker"])
        b2_ticker = str(cluster["ticker"])
        if b1_ticker != b2_ticker:
            diag["tickerMismatchAtIntersection"] += 1
            continue

        opportunistic_owners = {
            str(owner) for owner in opportunistic.get("opportunisticOwnerIds", []) if owner
        }
        cluster_owners = {
            str(owner) for owner in cluster.get("clusterOwnerIds", []) if owner
        }
        overlap = sorted(opportunistic_owners & cluster_owners)
        if overlap:
            diag["intersectionWithOwnerOverlap"] += 1
        else:
            diag["intersectionWithoutOwnerOverlap"] += 1

        combined.append(
            {
                "issuerCik": key[0],
                "ticker": b1_ticker,
                "evaluationSession": key[1],
                "knowledgeAtFirst": max(
                    str(opportunistic["knowledgeAtFirst"]),
                    str(cluster["knowledgeAtFirst"]),
                ),
                "b1KnowledgeAtFirst": str(opportunistic["knowledgeAtFirst"]),
                "b2KnowledgeAtFirst": str(cluster["knowledgeAtFirst"]),
                "opportunisticOwnerCount": int(opportunistic["opportunisticOwnerCount"]),
                "opportunisticOwnerIds": sorted(opportunistic_owners),
                "rawOpportunisticPurchaseRows": int(
                    opportunistic["rawOpportunisticPurchaseRows"]
                ),
                "clusterOwnerCount": int(cluster["clusterOwnerCount"]),
                "clusterOwnerIds": sorted(cluster_owners),
                "clusterAnchorTransactionDate": cluster["clusterAnchorTransactionDate"],
                "strongCluster": bool(cluster["strongCluster"]),
                "opportunisticClusterOwnerOverlapCount": len(overlap),
                "opportunisticClusterOwnerOverlapIds": overlap,
            }
        )

    diag["identityConsistentIntersections"] = len(combined)
    return combined, dict(diag)


def _comparison(
    horizons: dict[str, dict[str, Any]], summary_path: Path | None
) -> dict[str, Any]:
    if summary_path is None or not summary_path.exists():
        return {}
    reference = json.loads(summary_path.read_text(encoding="utf-8"))
    comparison: dict[str, Any] = {}
    for horizon in v1.HORIZONS:
        key = str(horizon)
        base = reference["horizons"][key]
        current = horizons[key]
        comparison[key] = {
            "spyExcessMeanDelta": current["spyExcessMean"] - base["spyExcessMean"],
            "spyExcessMedianDelta": current["spyExcessMedian"] - base["spyExcessMedian"],
            "spyExcessWinRateDelta": current["spyExcessWinRate"] - base["spyExcessWinRate"],
            "maturedOutcomeCountRatio": (
                current["maturedOutcomeCount"] / base["maturedOutcomeCount"]
                if base["maturedOutcomeCount"]
                else None
            ),
        }
    return comparison


def run(
    *,
    sec_path: Path,
    cmp_history_root: Path,
    market_root: Path,
    p0_summary: Path,
    output: Path,
    b0_summary: Path | None = None,
    b1_summary: Path | None = None,
    b2_summary: Path | None = None,
) -> dict[str, Any]:
    p0_data = json.loads(p0_summary.read_text(encoding="utf-8"))
    tier = str(p0_data["dataQualityGate"]["tier"])
    if tier == "FAIL_BELOW_EXPLORATORY":
        raise ValueError("P0 exact-calendar data-quality gate is below Tier C")
    if p0_data.get("oosOpened") is not False:
        raise ValueError("P0 artifact violates sealed OOS boundary")

    output.mkdir(parents=True, exist_ok=True)
    history, history_diag = b1._load_cmp_history(cmp_history_root)
    labels, classifier_diag = b1._annual_classifications(history)
    b1_events, b1_diag = b1._load_b1_events(sec_path, labels)

    purchase_rows, b2_purchase_diag = b2._normalize_purchase_rows(sec_path)
    cluster_events = b2_fast._cluster_trigger_events(purchase_rows)
    b2_events, b2_identity_diag = b2._identity_eligible(cluster_events)

    joint_events, intersection_diag = _intersect_events(b1_events, b2_events)
    sessions = p0._expected_sessions()
    retained, dedup_suppressed = b1._deduplicate(joint_events, sessions)
    if b1.DEDUP_SESSIONS != DEDUP_SESSIONS or b2.DEDUP_SESSIONS != DEDUP_SESSIONS:
        raise ValueError("B4 dedup contract diverges from B1/B2")

    event_rows, attrition = b2._outcomes(
        retained=retained,
        market_files=v1._market_files(market_root),
        sessions=sessions,
        output=output,
    )
    metadata = {
        (str(event["issuerCik"]), str(event["evaluationSession"])): event
        for event in retained
    }
    enriched_rows: list[dict[str, Any]] = []
    for row in event_rows:
        key = (str(row["issuerCik"]), str(row["evaluationSession"]))
        source = metadata[key]
        enriched_rows.append(
            {
                **row,
                "b1KnowledgeAtFirst": source["b1KnowledgeAtFirst"],
                "b2KnowledgeAtFirst": source["b2KnowledgeAtFirst"],
                "opportunisticOwnerCount": source["opportunisticOwnerCount"],
                "rawOpportunisticPurchaseRows": source["rawOpportunisticPurchaseRows"],
                "opportunisticClusterOwnerOverlapCount": source[
                    "opportunisticClusterOwnerOverlapCount"
                ],
            }
        )

    fieldnames = [
        "issuerCik",
        "ticker",
        "knowledgeAtFirst",
        "b1KnowledgeAtFirst",
        "b2KnowledgeAtFirst",
        "evaluationSession",
        "entrySession",
        "entryOpen",
        "opportunisticOwnerCount",
        "rawOpportunisticPurchaseRows",
        "clusterOwnerCount",
        "strongCluster",
        "clusterAnchorTransactionDate",
        "opportunisticClusterOwnerOverlapCount",
    ]
    for horizon in v1.HORIZONS:
        fieldnames.extend(
            [
                f"exit_{horizon}",
                f"raw_{horizon}",
                f"excess_{horizon}",
                f"mae_{horizon}",
                f"reason_{horizon}",
            ]
        )
    with (output / "events.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)

    horizons = {
        str(horizon): b0._aggregate(enriched_rows, horizon) for horizon in v1.HORIZONS
    }
    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "benchmark": "B4_CMP_OPPORTUNISTIC_AND_INDEPENDENT_OWNER_CLUSTER",
        "status": "PHASE1_B4_DEVELOPMENT_DESCRIPTIVE_COMPLETE",
        "period": "2016-2020 XNYS evaluation-session cohort",
        "outcomeMarketBoundary": "2016-2022 only",
        "p0DataQualityTier": tier,
        "definition": {
            "intersectionKey": "issuer CIK + exact XNYS evaluation session",
            "b1": "canonical CMP trader-level opportunistic qualified purchase",
            "b2": "independent-owner qualified-purchase cluster within 30 calendar days",
            "intersectionTiming": "form intersection before common issuer-level deduplication",
            "futureConfirmationAllowed": False,
            "ownerOverlapRequired": False,
            "ownerOverlapReported": True,
        },
        "eventUnit": "issuer CIK + joint-signal XNYS evaluation session",
        "dedupSessions": DEDUP_SESSIONS,
        "dedupKey": "issuer CIK",
        "executionClock": "joint PIT evaluation session close -> exact next XNYS session open",
        "horizonsSessions": list(v1.HORIZONS),
        "primaryHorizonSessions": PRIMARY_HORIZON,
        "history": history_diag,
        "classifier": classifier_diag,
        "b1SelectionDiagnostics": b1_diag,
        "b2PurchaseDiagnostics": b2_purchase_diag,
        "b2IdentityDiagnostics": b2_identity_diag,
        "intersectionDiagnostics": intersection_diag,
        "selection": {
            "jointEventsBeforeDedup": len(joint_events),
            "dedupSuppressed": dedup_suppressed,
            "retainedAfterDedup": len(retained),
            "exactEntryMatched": len(enriched_rows),
            "entryAttrition": attrition,
            "distinctIssuersWithEntry": len({row["issuerCik"] for row in enriched_rows}),
        },
        "horizons": horizons,
        "comparisonVsB0": _comparison(horizons, b0_summary),
        "comparisonVsB1": _comparison(horizons, b1_summary),
        "comparisonVsB2": _comparison(horizons, b2_summary),
        "interpretation": (
            "Development descriptive intersection only. B4 tests incremental corroboration of "
            "canonical opportunistic timing and independent-owner cluster evidence; it is not "
            "authorized as a production score or default winner. 2023+ remains sealed."
        ),
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "canonicalReady": False,
        "signalReady": False,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sec", type=Path, required=True)
    parser.add_argument("--cmp-history-root", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--p0-summary", type=Path, required=True)
    parser.add_argument("--b0-summary", type=Path)
    parser.add_argument("--b1-summary", type=Path)
    parser.add_argument("--b2-summary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(
        sec_path=args.sec,
        cmp_history_root=args.cmp_history_root,
        market_root=args.market_root,
        p0_summary=args.p0_summary,
        b0_summary=args.b0_summary,
        b1_summary=args.b1_summary,
        b2_summary=args.b2_summary,
        output=args.output,
    )


if __name__ == "__main__":
    main()
