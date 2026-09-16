"""Research-only Massive point-in-time CIK-to-ticker recovery diagnostic.

This script consumes the bounded 2016-2022 SEC identity-recovery artifact and
queries Massive's point-in-time reference endpoint only for events that remain
unresolved after the SEC-only recovery tiers. It never reads 2023+ target data,
never rewrites canonical SEC rows, and never changes production scoring.

A Massive recovery is intentionally conservative: for the issuer CIK and exact
evaluation-session date, the point-in-time endpoint must return exactly one
active U.S. equity ticker across the stocks/OTC markets. Multiple candidates are
kept as ambiguous evidence and receive no recovery credit.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

SEALED_YEAR = 2023
ALLOWED_MARKETS = {"stocks", "otc"}
API_URL = "https://api.massive.com/v3/reference/tickers"
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


def _normalize_cik(value: object) -> str:
    raw = str(value or "").strip()
    if not raw.isdigit():
        return raw
    return str(int(raw))


def _event_key(event: dict[str, Any]) -> str:
    return f"{event['issuerCik']}|{event['evaluationSession']}"


def _is_still_unresolved(event: dict[str, Any]) -> bool:
    return not event.get("recoveredTicker") and not event.get("evaluationCloseRecoveredTicker")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class RateLimiter:
    def __init__(self, requests_per_minute: float) -> None:
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        self.interval = 60.0 / requests_per_minute
        self.last_request_at: float | None = None

    def wait(self) -> None:
        if self.last_request_at is not None:
            elapsed = time.monotonic() - self.last_request_at
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
        self.last_request_at = time.monotonic()


def _request_json(
    client: httpx.Client,
    *,
    url: str,
    api_key: str,
    limiter: RateLimiter,
    params: dict[str, object] | None = None,
    max_attempts: int = 8,
) -> tuple[dict[str, Any], int]:
    attempts = 0
    request_count = 0
    while True:
        attempts += 1
        limiter.wait()
        request_count += 1
        response = client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if response.status_code < 400:
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Massive response is not a JSON object")
            return payload, request_count

        if response.status_code not in TRANSIENT_STATUS_CODES or attempts >= max_attempts:
            raise RuntimeError(
                f"Massive request failed with HTTP {response.status_code}: {response.text[:300]}"
            )

        retry_after = response.headers.get("Retry-After")
        try:
            delay = float(retry_after) if retry_after else min(60.0, 2.0**attempts)
        except ValueError:
            delay = min(60.0, 2.0**attempts)
        time.sleep(max(1.0, delay))


def _query_cik_date(
    client: httpx.Client,
    *,
    api_key: str,
    cik: str,
    date: str,
    limiter: RateLimiter,
) -> tuple[list[dict[str, Any]], int]:
    params: dict[str, object] | None = {
        "cik": cik,
        "date": date,
        "active": "true",
        "order": "asc",
        "limit": 1000,
        "sort": "ticker",
    }
    url = API_URL
    rows: list[dict[str, Any]] = []
    request_count = 0

    while url:
        payload, used = _request_json(
            client,
            url=url,
            api_key=api_key,
            limiter=limiter,
            params=params,
        )
        request_count += used
        raw_results = payload.get("results") or []
        if not isinstance(raw_results, list):
            raise RuntimeError("Massive results field is not a list")
        rows.extend(row for row in raw_results if isinstance(row, dict))
        next_url = payload.get("next_url")
        url = str(next_url) if next_url else ""
        params = None

    return rows, request_count


def _candidate_rows(rows: list[dict[str, Any]], cik: str) -> list[dict[str, Any]]:
    normalized_cik = _normalize_cik(cik)
    candidates: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        if _normalize_cik(row.get("cik")) != normalized_cik:
            continue
        if str(row.get("locale") or "").lower() != "us":
            continue
        if str(row.get("market") or "").lower() not in ALLOWED_MARKETS:
            continue
        if row.get("active") is not True:
            continue
        candidates[ticker] = {
            "ticker": ticker,
            "name": row.get("name"),
            "market": row.get("market"),
            "type": row.get("type"),
            "primaryExchange": row.get("primary_exchange"),
            "compositeFigi": row.get("composite_figi"),
            "shareClassFigi": row.get("share_class_figi"),
        }
    return [candidates[ticker] for ticker in sorted(candidates)]


def run(
    *,
    identity_events_path: Path,
    identity_summary_path: Path,
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

    output.mkdir(parents=True, exist_ok=True)
    identity_events = _load_json(identity_events_path)
    identity_summary = _load_json(identity_summary_path)
    if not isinstance(identity_events, list) or not isinstance(identity_summary, dict):
        raise ValueError("unexpected identity artifact shape")
    if identity_summary.get("period") != "2016-2022":
        raise ValueError("identity summary must be bounded to 2016-2022")
    if identity_summary.get("oosOpened") is not False:
        raise ValueError("sealed OOS boundary is not intact")

    unresolved = [event for event in identity_events if _is_still_unresolved(event)]
    unresolved.sort(key=lambda row: (str(row["issuerCik"]), str(row["evaluationSession"])))
    for event in unresolved:
        year = int(str(event["evaluationSession"])[:4])
        if year >= SEALED_YEAR:
            raise ValueError("sealed OOS boundary violated by identity event")

    cache: dict[str, Any] = {}
    if cache_path and cache_path.exists():
        loaded_cache = _load_json(cache_path)
        if not isinstance(loaded_cache, dict):
            raise ValueError("Massive cache must be a JSON object")
        cache = loaded_cache

    limiter = RateLimiter(requests_per_minute)
    network_queries = 0
    http_requests = 0

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for event in unresolved:
            key = _event_key(event)
            if key in cache:
                continue
            if network_queries >= max_queries:
                break

            cik = str(event["issuerCik"])
            date = str(event["evaluationSession"])
            rows, used_requests = _query_cik_date(
                client,
                api_key=api_key,
                cik=cik,
                date=date,
                limiter=limiter,
            )
            http_requests += used_requests
            network_queries += 1
            candidates = _candidate_rows(rows, cik)
            recovered = candidates[0]["ticker"] if len(candidates) == 1 else None
            if recovered:
                status = "RECOVERABLE_MASSIVE_PIT_UNIQUE"
            elif candidates:
                status = "AMBIGUOUS_MASSIVE_PIT_MULTIPLE"
            else:
                status = "NO_MASSIVE_PIT_ACTIVE_US_EQUITY"

            cache[key] = {
                "issuerCik": cik,
                "evaluationSession": date,
                "status": status,
                "recoveredTicker": recovered,
                "candidateCount": len(candidates),
                "candidates": candidates,
                "source": "Massive /v3/reference/tickers cik+date active=true",
            }

    cache_output = output / "massive-query-cache.json"
    _write_json(cache_output, cache)

    result_rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    recovered_tickers: Counter[str] = Counter()
    recovered_events = 0
    queried_events = 0

    for event in unresolved:
        key = _event_key(event)
        evidence = cache.get(key)
        if evidence is None:
            status = "NOT_QUERIED_YET"
            recovered = None
            candidates: list[dict[str, Any]] = []
        else:
            queried_events += 1
            status = str(evidence["status"])
            recovered = evidence.get("recoveredTicker")
            candidates = list(evidence.get("candidates") or [])
            if recovered:
                recovered_events += 1
                recovered_tickers[str(recovered)] += 1
        status_counts[status] += 1
        result_rows.append(
            {
                "issuerCik": event["issuerCik"],
                "evaluationSession": event["evaluationSession"],
                "identityProblem": event["identityProblem"],
                "secRecoveryStatus": event["recoveryStatus"],
                "massiveRecoveryStatus": status,
                "massiveRecoveredTicker": recovered,
                "massiveCandidates": candidates,
            }
        )

    _write_json(output / "massive-identity-recovery-events.json", result_rows)

    total_problem_events = int(identity_summary["identityProblemEvents"])
    qualified_events = int(identity_summary["qualifiedIssuerSessionEvents"])
    max_missing = int(identity_summary["onePctGateMaxMissingEventsApprox"])
    unresolved_after_sec = len(unresolved)
    remaining = unresolved_after_sec - recovered_events
    complete = queried_events == unresolved_after_sec

    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "dataset": "Massive PIT historical identity recovery diagnostic",
        "period": "2016-2022",
        "sourceEndpoint": "/v3/reference/tickers?cik=<CIK>&date=<evaluationSession>&active=true",
        "sourcePolicy": (
            "Recovery credit requires exactly one active U.S. equity ticker for the exact "
            "issuer CIK and evaluation-session date. Multiple candidates remain ambiguous."
        ),
        "qualifiedIssuerSessionEvents": qualified_events,
        "identityProblemEvents": total_problem_events,
        "unresolvedAfterSecRecoveryTiers": unresolved_after_sec,
        "queriedUnresolvedEvents": queried_events,
        "unqueriedUnresolvedEvents": unresolved_after_sec - queried_events,
        "massivePitRecoveredEvents": recovered_events,
        "remainingIdentityProblemEvents": remaining,
        "identityMissingRateAfterMassive": (
            remaining / qualified_events if qualified_events else 0.0
        ),
        "onePctGateMaxMissingEventsApprox": max_missing,
        "wouldCombinedSecPlusMassiveMeetOnePctIdentityGate": complete and remaining <= max_missing,
        "statusCounts": dict(sorted(status_counts.items())),
        "topMassiveRecoveredTickers": [
            {"ticker": ticker, "issuerSessionEvents": count}
            for ticker, count in recovered_tickers.most_common(30)
        ],
        "networkQueriesThisRun": network_queries,
        "httpRequestsThisRun": http_requests,
        "requestsPerMinuteConfigured": requests_per_minute,
        "complete": complete,
        "status": (
            "MASSIVE_PIT_IDENTITY_RECOVERY_COMPLETE"
            if complete
            else "MASSIVE_PIT_IDENTITY_RECOVERY_PARTIAL"
        ),
        "oosOpened": False,
        "productionScoringChanged": False,
        "canonicalSecChanged": False,
    }
    _write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity-events", type=Path, required=True)
    parser.add_argument("--identity-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--requests-per-minute", type=float, default=5.0)
    parser.add_argument("--max-queries", type=int, default=250)
    args = parser.parse_args()

    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    run(
        identity_events_path=args.identity_events,
        identity_summary_path=args.identity_summary,
        output=args.output,
        api_key=api_key,
        requests_per_minute=args.requests_per_minute,
        max_queries=args.max_queries,
        cache_path=args.cache,
    )


if __name__ == "__main__":
    main()
