"""Research-only Massive transaction-date identity fallback diagnostic.

This layer is deliberately separate from evaluation-session tradability. It is
used only when the existing Massive exact evaluation-session query found no
active U.S. equity for a bounded 2016-2022 identity event. Source-observed SEC
transaction dates (2013-2022 warm-up/development/validation only) may then be
queried point-in-time to recover historical security identity.

A historical identity recovery never counts as an evaluation-session market
entry. Canonical SEC rows, production scoring, and sealed 2023+ OOS remain
unchanged.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import httpx
from research_massive_identity_recovery import (
    RateLimiter,
    _candidate_rows,
    _event_key,
    _is_still_unresolved,
    _load_json,
    _query_cik_date,
    _resolve_candidates,
    _write_json,
)

SEALED_YEAR = 2023
WARMUP_START_YEAR = 2013
EVALUATION_NO_TICKER = "NO_MASSIVE_PIT_ACTIVE_US_EQUITY"


def _date_key(cik: str, transaction_date: str) -> str:
    return f"{cik}|{transaction_date}"


def _eligible_events(
    identity_events: list[dict[str, Any]],
    evaluation_cache: dict[str, Any],
) -> list[dict[str, Any]]:
    eligible: list[dict[str, Any]] = []
    for event in identity_events:
        if not _is_still_unresolved(event):
            continue
        key = _event_key(event)
        evaluation = evaluation_cache.get(key)
        if not isinstance(evaluation, dict) or evaluation.get("status") != EVALUATION_NO_TICKER:
            continue
        dates = sorted({str(value) for value in event.get("transactionDates") or [] if value})
        if not dates:
            continue
        evaluation_session = str(event["evaluationSession"])
        for transaction_date in dates:
            year = int(transaction_date[:4])
            if not WARMUP_START_YEAR <= year < SEALED_YEAR:
                raise ValueError("transaction-date evidence outside frozen 2013-2022 period")
            if transaction_date > evaluation_session:
                raise ValueError("SEC transaction date occurs after evaluation session")
        copy = dict(event)
        copy["transactionDates"] = dates
        eligible.append(copy)
    eligible.sort(key=lambda row: (str(row["issuerCik"]), str(row["evaluationSession"])))
    return eligible


def _round_robin_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_cik: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_cik[str(event["issuerCik"])].append(event)
    for rows in by_cik.values():
        rows.sort(key=lambda row: str(row["evaluationSession"]))

    ordered: list[dict[str, Any]] = []
    depth = 0
    while True:
        added = False
        for cik in sorted(by_cik):
            rows = by_cik[cik]
            if depth < len(rows):
                ordered.append(rows[depth])
                added = True
        if not added:
            return ordered
        depth += 1


def _date_resolution(
    event: dict[str, Any],
    evidence: dict[str, Any],
) -> tuple[str | None, str]:
    candidates = list(evidence.get("candidates") or [])
    recovered, status, _ = _resolve_candidates(event, candidates)
    if status == "RECOVERABLE_MASSIVE_PIT_UNIQUE":
        return recovered, "RECOVERABLE_TRANSACTION_DATE_UNIQUE"
    if status == "RECOVERABLE_MASSIVE_PIT_SEC_CLASS_UNIQUE":
        return recovered, "RECOVERABLE_TRANSACTION_DATE_SEC_CLASS_UNIQUE"
    if status == "AMBIGUOUS_MASSIVE_PIT_MULTIPLE":
        return None, "AMBIGUOUS_TRANSACTION_DATE_MULTIPLE"
    return None, "NO_MASSIVE_TRANSACTION_DATE_ACTIVE_US_EQUITY"


def _event_resolution(
    event: dict[str, Any],
    date_cache: dict[str, Any],
) -> tuple[str | None, str, list[dict[str, Any]]]:
    cik = str(event["issuerCik"])
    per_date: list[dict[str, Any]] = []
    recovered_tickers: set[str] = set()
    unresolved_statuses: set[str] = set()

    for transaction_date in event["transactionDates"]:
        evidence = date_cache.get(_date_key(cik, transaction_date))
        if not isinstance(evidence, dict):
            return None, "TRANSACTION_DATE_EVIDENCE_PARTIAL", per_date
        recovered, status = _date_resolution(event, evidence)
        per_date.append(
            {
                "transactionDate": transaction_date,
                "status": status,
                "recoveredTicker": recovered,
                "candidates": list(evidence.get("candidates") or []),
            }
        )
        if recovered:
            recovered_tickers.add(str(recovered))
        else:
            unresolved_statuses.add(status)

    if unresolved_statuses:
        if "AMBIGUOUS_TRANSACTION_DATE_MULTIPLE" in unresolved_statuses:
            return None, "HISTORICAL_IDENTITY_AMBIGUOUS", per_date
        return None, "HISTORICAL_IDENTITY_NOT_FOUND_ON_ALL_TRANSACTION_DATES", per_date
    if len(recovered_tickers) == 1:
        return next(iter(recovered_tickers)), "RECOVERABLE_HISTORICAL_IDENTITY_CONSISTENT", per_date
    if len(recovered_tickers) > 1:
        return None, "HISTORICAL_IDENTITY_TICKER_CONFLICT", per_date
    return None, "HISTORICAL_IDENTITY_NOT_FOUND", per_date


def run(
    *,
    identity_events_path: Path,
    identity_summary_path: Path,
    evaluation_cache_path: Path,
    output: Path,
    api_key: str,
    requests_per_minute: float,
    max_queries: int,
    cache_path: Path | None = None,
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("Massive API key is required")
    if max_queries <= 0:
        raise ValueError("max_queries must be positive")

    identity_events = _load_json(identity_events_path)
    identity_summary = _load_json(identity_summary_path)
    evaluation_cache = _load_json(evaluation_cache_path)
    if not isinstance(identity_events, list):
        raise ValueError("identity events must be a JSON list")
    if not isinstance(identity_summary, dict) or identity_summary.get("period") != "2016-2022":
        raise ValueError("identity summary must be bounded to 2016-2022")
    if identity_summary.get("oosOpened") is not False:
        raise ValueError("sealed OOS boundary is not intact")
    if not isinstance(evaluation_cache, dict):
        raise ValueError("evaluation Massive cache must be a JSON object")

    events = _eligible_events(identity_events, evaluation_cache)
    query_order = _round_robin_events(events)

    date_cache: dict[str, Any] = {}
    if cache_path and cache_path.exists():
        loaded = _load_json(cache_path)
        if not isinstance(loaded, dict):
            raise ValueError("transaction-date Massive cache must be a JSON object")
        date_cache = loaded

    limiter = RateLimiter(requests_per_minute)
    network_queries = 0
    http_requests = 0
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for event in query_order:
            cik = str(event["issuerCik"])
            for transaction_date in event["transactionDates"]:
                key = _date_key(cik, transaction_date)
                if key in date_cache:
                    continue
                if network_queries >= max_queries:
                    break
                rows, used_requests = _query_cik_date(
                    client,
                    api_key=api_key,
                    cik=cik,
                    date=transaction_date,
                    limiter=limiter,
                )
                candidates = _candidate_rows(rows, cik)
                date_cache[key] = {
                    "issuerCik": cik,
                    "transactionDate": transaction_date,
                    "candidateCount": len(candidates),
                    "candidates": candidates,
                    "source": "Massive /v3/reference/tickers cik+transactionDate active=true",
                }
                network_queries += 1
                http_requests += used_requests
            if network_queries >= max_queries:
                break

    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "massive-transaction-date-query-cache.json", date_cache)

    status_counts: Counter[str] = Counter()
    recovered_tickers: Counter[str] = Counter()
    rows_out: list[dict[str, Any]] = []
    completed_events = 0
    recovered_events = 0
    for event in events:
        recovered, status, per_date = _event_resolution(event, date_cache)
        if status != "TRANSACTION_DATE_EVIDENCE_PARTIAL":
            completed_events += 1
        if recovered:
            recovered_events += 1
            recovered_tickers[recovered] += 1
        status_counts[status] += 1
        rows_out.append(
            {
                "issuerCik": event["issuerCik"],
                "evaluationSession": event["evaluationSession"],
                "evaluationSessionMassiveStatus": EVALUATION_NO_TICKER,
                "securityTitles": list(event.get("securityTitles") or []),
                "transactionDates": list(event["transactionDates"]),
                "historicalIdentityStatus": status,
                "historicalRecoveredTicker": recovered,
                "transactionDateEvidence": per_date,
                "evaluationSessionTradabilityChanged": False,
            }
        )

    _write_json(output / "massive-transaction-date-recovery-events.json", rows_out)

    qualified = int(identity_summary["qualifiedIssuerSessionEvents"])
    sec_remaining = int(identity_summary["remainingAfterStrictPlus365PlusEvaluationClose"])
    evaluation_recovered_events = sum(
        1
        for event in identity_events
        if _is_still_unresolved(event)
        and isinstance(evaluation_cache.get(_event_key(event)), dict)
        and evaluation_cache[_event_key(event)].get("recoveredTicker")
    )
    provisional_remaining = sec_remaining - evaluation_recovered_events - recovered_events
    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "dataset": "Massive PIT transaction-date historical identity fallback diagnostic",
        "period": "2016-2022 target events; 2013-2022 transaction-date evidence",
        "eligibleNoEvaluationTickerEvents": len(events),
        "eventsWithCompleteTransactionDateEvidence": completed_events,
        "evaluationSessionRecoveredEventsInInputCache": evaluation_recovered_events,
        "historicalIdentityRecoveredEvents": recovered_events,
        "historicalIdentityRecoveryRateAmongCompleted": (
            recovered_events / completed_events if completed_events else 0.0
        ),
        "statusCounts": dict(sorted(status_counts.items())),
        "networkQueriesThisRun": network_queries,
        "httpRequestsThisRun": http_requests,
        "cachedUniqueCikTransactionDates": len(date_cache),
        "requestsPerMinuteConfigured": requests_per_minute,
        "provisionalIdentityProblemEventsAfterEvaluationAndHistoricalEvidence": (
            provisional_remaining
        ),
        "provisionalIdentityMissingRateAfterEvaluationAndHistoricalEvidence": (
            provisional_remaining / qualified if qualified else 0.0
        ),
        "topHistoricalRecoveredTickers": [
            {"ticker": ticker, "issuerSessionEvents": count}
            for ticker, count in recovered_tickers.most_common(30)
        ],
        "identityEvidenceOnly": True,
        "countsTowardMarketEntryCoverage": False,
        "evaluationSessionTradabilityChanged": False,
        "completeForCurrentlyCachedNoEvaluationTickerEvents": completed_events == len(events),
        "oosOpened": False,
        "productionScoringChanged": False,
        "canonicalSecChanged": False,
        "status": "MASSIVE_TRANSACTION_DATE_IDENTITY_FALLBACK_DIAGNOSTIC",
    }
    _write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity-events", type=Path, required=True)
    parser.add_argument("--identity-summary", type=Path, required=True)
    parser.add_argument("--evaluation-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--requests-per-minute", type=float, default=5.0)
    parser.add_argument("--max-queries", type=int, default=20)
    args = parser.parse_args()

    run(
        identity_events_path=args.identity_events,
        identity_summary_path=args.identity_summary,
        evaluation_cache_path=args.evaluation_cache,
        output=args.output,
        api_key=os.environ.get("MASSIVE_API_KEY", "").strip(),
        requests_per_minute=args.requests_per_minute,
        max_queries=args.max_queries,
        cache_path=args.cache,
    )


if __name__ == "__main__":
    main()
