"""Read-only, aggregate root-cause evidence for a validated daily SEC research snapshot.

This never changes market data, scoring, state, identity evidence, publishability,
cursors, alerts or dashboard output. It is a separate operations artifact.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

# Mutually exclusive *primary* score blockers. STALE_DATA_HOLD is an overlay:
# it never replaces a durable reason for missing the actual score.
BLOCKERS = (
    "UNRESOLVED_IDENTITY",
    "UNRESOLVED_AMENDMENT",
    "JOINT_OWNER_SCORE_NOT_RECOMPUTED",
    "SOURCE_QUARANTINE",
    "INSUFFICIENT_COMPONENT_DATA",
)


class CoverageEvidenceError(ValueError):
    """Source reports disagree or do not permit an unambiguous diagnosis."""


def summarize(research: dict[str, Any], daily: dict[str, Any],
              identities: dict[str, Any], market: dict[str, Any],
              quarantine: dict[str, Any]) -> dict[str, Any]:
    run_id = research.get("runId")
    if not isinstance(run_id, str) or not run_id or run_id != daily.get("runId"):
        raise CoverageEvidenceError("research/daily report runId mismatch")
    if quarantine.get("runId") != run_id or identities.get("runId") != run_id:
        raise CoverageEvidenceError("SEC/identity diagnostic runId mismatch")

    scores = research["researchScores"]
    companies = research["companies"]
    coverage = research["coverage"]
    states = daily["states"]
    if (not isinstance(scores, list) or not isinstance(companies, list)
            or not isinstance(states, dict) or len(scores) != len(companies)):
        raise CoverageEvidenceError("research score/company/state shape mismatch")
    company_ciks = [item["issuerCik"] for item in companies]
    score_ciks = [item["issuerCik"] for item in scores]
    if len(set(score_ciks)) != len(scores) or set(score_ciks) != set(company_ciks):
        raise CoverageEvidenceError("score issuer grain differs from company issuer grain")

    blocked: Counter[str] = Counter()
    score_reason_tags: Counter[str] = Counter()
    missing_features: Counter[str] = Counter()
    without_state_reasons = 0
    complete = 0
    missing_component_issuers = 0
    stale_overlay = 0
    for score in scores:
        reasons = set(score["reasons"])
        score_reason_tags.update(reasons)
        stale_overlay += "STALE_DATA_HOLD" in reasons
        categories = [key for key in BLOCKERS if key in reasons]
        if score["total"] is not None:
            if categories:
                raise CoverageEvidenceError("completed score contains missing-score blocker")
            complete += 1
            continue
        if len(categories) != 1:
            raise CoverageEvidenceError("unscored issuer lacks a unique primary blocker")
        key = categories[0]
        blocked[key] += 1
        if key != "INSUFFICIENT_COMPONENT_DATA":
            continue
        missing_component_issuers += 1
        state = states.get(score["issuerCik"], {})
        tags = [reason for reason in (state.get("reason_codes") or [])
                if isinstance(reason, str) and reason.startswith("MISSING_")]
        missing_features.update(set(tags))
        if not tags:
            without_state_reasons += 1
    if complete != coverage["completeScores"] or sum(blocked.values()) + complete != len(scores):
        raise CoverageEvidenceError("complete-score coverage does not reconcile")

    expected = coverage["expectedSecDays"]
    days = coverage["days"]
    missing = coverage["missingSecDays"]
    if (len(set(expected)) != len(expected) or len(set(missing)) != len(missing)
            or len({x["day"] for x in days}) != len(days)
            or set(expected) - {x["day"] for x in days} != set(missing)
            or any(x["day"] not in set(expected) for x in days)):
        raise CoverageEvidenceError("SEC day inventory and missing-day evidence mismatch")
    incomplete = [d for d in days if not d["complete"]]
    quarantined = sum(d["quarantinedRows"] for d in days)
    unfilled_filings = sum(d["discoveredFilings"] - d["storedFilings"] for d in days)
    source_failures = sum(d["failures"] for d in days)
    if not all(isinstance(x, int) and x >= 0 for x in
               (quarantined, unfilled_filings, source_failures)):
        raise CoverageEvidenceError("negative or invalid SEC counts")
    if any(bool(d["complete"]) != (
            d["quarantinedRows"] == 0 and d["failures"] == 0
            and d["storedFilings"] == d["discoveredFilings"]) for d in days):
        raise CoverageEvidenceError("SEC day complete flag inconsistent with counts")

    cause_days = quarantine["days"]
    if not isinstance(cause_days, dict):
        raise CoverageEvidenceError("invalid SEC quarantine diagnostics")
    if set(cause_days) - {d["day"] for d in days}:
        raise CoverageEvidenceError("quarantine diagnostics contain unknown days")
    by_day = []
    all_codes: Counter[str] = Counter()
    for day in days:
        codes = cause_days.get(day["day"], {})
        if (not isinstance(codes, dict) or any(
                not isinstance(key, str) or type(value) is not int or value <= 0
                for key, value in codes.items())):
            raise CoverageEvidenceError("malformed quarantine reason counts")
        if sum(codes.values()) != day["quarantinedRows"]:
            raise CoverageEvidenceError("SEC quarantine cause count differs from day evidence")
        all_codes.update(codes)
        if not day["complete"]:
            by_day.append({
                "day": day["day"],
                "quarantinedRows": day["quarantinedRows"],
                "checkpointFailures": day["failures"],
                "missingFilings": day["discoveredFilings"] - day["storedFilings"],
                "causeCodes": dict(sorted(codes.items())),
            })

    requested, resolved = identities["requestedIssuerCount"], identities["resolvedIssuerCount"]
    unresolved = identities["unresolved"]
    if (type(requested) is not int or type(resolved) is not int
            or not isinstance(unresolved, list)
            or resolved + len(unresolved) != requested):
        raise CoverageEvidenceError("current SEC identity inventory does not reconcile")
    identity_reasons: Counter[str] = Counter()
    for item in unresolved:
        identity_reasons.update(set(item.get("reasons", [])))

    if (type(market["requested"]) is not int or type(market["available"]) is not int
            or market["available"] < 0 or market["available"] > market["requested"]
            or not isinstance(market.get("failures"), dict)):
        raise CoverageEvidenceError("market availability totals invalid")

    return {
        "schemaVersion": "research-coverage-diagnostic-v1",
        "runId": run_id,
        "asOf": research["asOf"],
        "scope": "READ_ONLY_AGGREGATE_OPERATIONS_NOT_A_SCORING_GATE",
        "outputFreshnessVerified": False,
        "scoring": {
            "issuerCount": len(scores),
            "completeScores": complete,
            "completeRate": round(complete / len(scores), 6) if scores else None,
            "blockedByPrimaryReason": {code: blocked[code] for code in BLOCKERS},
            "staleHoldOverlayCount": stale_overlay,
            "insufficientComponentIssuers": missing_component_issuers,
            "missingComponentTagCountsOverlapping": dict(sorted(missing_features.items())),
            "missingComponentWithoutSpecificStateTag": without_state_reasons,
            "scoreReasonTagsOverlapping": dict(sorted(score_reason_tags.items())),
        },
        "sec": {
            "expectedDays": len(expected), "checkpointDays": len(days),
            "missingDays": sorted(missing),
            "incompleteCheckpointDays": len(incomplete),
            "quarantinedRows": quarantined,
            "missingFilings": unfilled_filings,
            "sourceFailures": source_failures,
            "quarantineCauseTotals": dict(sorted(all_codes.items())),
            "incompleteDayDetails": by_day,
        },
        "identity": {
            "requestedCurrentIssuerIds": requested,
            "resolvedCurrentIssuerIds": resolved,
            "unresolvedCurrentIssuerIds": len(unresolved),
            "unresolvedReasonTagsOverlapping": dict(sorted(identity_reasons.items())),
            "scopeNote": "Current identity-lookup CIKs are not the same universe as scored issuer CIKs.",
        },
        "market": {
            "requestedSymbols": market["requested"],
            "availableSymbols": market["available"],
            "sourceFailureCount": len(market["failures"]),
            "requiredCacheSession": market.get("requiredCacheSession"),
        },
        "readiness": research["readiness"],
        "limitations": [
            "Score blockers are not all source failures; a missing component may be genuinely inapplicable.",
            "A complete SEC-day checkpoint requires zero parser quarantines, not only all filings present.",
            "All per-source and score gates remain unchanged. No signal, ranking, methodology or alert changes.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("research", "daily-report", "identity-manifest", "market-status",
                "sec-quarantine-reasons", "output"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    paths = (args.research, args.daily_report, args.identity_manifest,
             args.market_status, args.sec_quarantine_reasons)
    result = summarize(*(json.loads(path.read_text(encoding="utf-8")) for path in paths))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "diagnosis": "READY",
        "runId": result["runId"],
        "scored": result["scoring"]["completeScores"],
        "issuers": result["scoring"]["issuerCount"],
        "secQuarantines": result["sec"]["quarantinedRows"],
        "sourceReadiness": result["readiness"]["dashboard"]["status"],
        "alertPolicyChanged": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
