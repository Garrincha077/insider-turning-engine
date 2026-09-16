"""Research-only Massive point-in-time CIK-to-ticker recovery diagnostic.

This script consumes the bounded 2016-2022 SEC identity-recovery artifact and
queries Massive's point-in-time reference endpoint only for events that remain
unresolved after the SEC-only recovery tiers. It never reads 2023+ target data,
never rewrites canonical SEC rows, and never changes production scoring.

Recovery is conservative. A ticker receives credit when the exact CIK/date
query returns one active U.S. equity ticker, or when multiple returned share
classes can be resolved uniquely from the source-observed SEC security title.
Ambiguous cases remain unresolved.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import httpx

SEALED_YEAR = 2023
ALLOWED_MARKETS = {"stocks", "otc"}
API_URL = "https://api.massive.com/v3/reference/tickers"
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
_CLASS_PATTERNS = (
    re.compile(r"\bCLASS[\s-]*([A-Z])\b", re.IGNORECASE),
    re.compile(r"\bCL[\s-]*([A-Z])\b", re.IGNORECASE),
    re.compile(r"\bCL([A-Z])\b", re.IGNORECASE),
)
_TICKER_CLASS_SUFFIX = re.compile(r"[.-]([A-Z])$")


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


def _class_tokens(text: object) -> set[str]:
    value = str(text or "")
    return {match.upper() for pattern in _CLASS_PATTERNS for match in pattern.findall(value)}


def _candidate_class_tokens(candidate: dict[str, Any]) -> set[str]:
    tokens = _class_tokens(candidate.get("name"))
    ticker = str(candidate.get("ticker") or "").strip().upper()
    suffix = _TICKER_CLASS_SUFFIX.search(ticker)
    if suffix:
        tokens.add(suffix.group(1))
    return tokens


def _event_class_token(event: dict[str, Any]) -> str | None:
    tokens: set[str] = set()
    for title in event.get("securityTitles") or []:
        tokens.update(_class_tokens(title))
    return next(iter(tokens)) if len(tokens) == 1 else None


def _resolve_candidates(
    event: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> tuple[str | None, str, str | None]:
    if len(candidates) == 1:
        return str(candidates[0]["ticker"]), "RECOVERABLE_MASSIVE_PIT_UNIQUE", None
    if not candidates:
        return None, "NO_MASSIVE_PIT_ACTIVE_US_EQUITY", None

    class_token = _event_class_token(event)
    if class_token is None:
        return None, "AMBIGUOUS_MASSIVE_PIT_MULTIPLE", None

    matches = [
        candidate
        for candidate in candidates
        if class_token in _candidate_class_tokens(candidate)
    ]
    if len(matches) == 1:
        return (
            str(matches[0]["ticker"]),
            "RECOVERABLE_MASSIVE_PIT_SEC_CLASS_UNIQUE",
            class_token,
        )
    return None, "AMBIGUOUS_MASSIVE_PIT_MULTIPLE", class_token


def _round_robin_query_order(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prioritize distinct issuers before repeated dates for the same CIK."""
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

    query_order = _round_robin_query_order(unresolved)

    cache: dict[str, Any] = {}
    if cache_path and cache_path.exists():
        loaded_cache = _load_json(cache_path)
        if not isinstance(loaded_cache, dict):
            raise ValueError("Massive cache must be a JSON object")
        cache = loaded_cache

    event_by_key = {_event_key(event): event for event in unresolved}
    for key, evidence in cache.items():
        event = event_by_key.get(key)
        if event is None or not isinstance(evidence, dict):
            continue
        candidates = list(evidence.get("candidates") or [])
        recovered, status, class_token = _resolve_candidates(event, candidates)
        evidence["status"] = status
        evidence["recoveredTicker"] = recovered
        evidence["secClassToken"] = class_token
        evidence["resolutionMethod"] = (
            "SEC_SECURITY_TITLE_CLASS"
            if status == "RECOVERABLE_MASSIVE_PIT_SEC_CLASS_UNIQUE"
            else "EXACT_CIK_DATE_UNIQUE"
            if status == "RECOVERABLE_MASSIVE_PIT_UNIQUE"
            else None
        )

    limiter = RateLimiter(requests_per_minute)
    network_queries = 0
    http_requests = 0

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for event in query_order:
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
            recovered, status, class_token = _resolve_candidates(event, candidates)

            cache[key] = {
                "issuerCik": cik,
                "evaluationSession": date,
                "status": status,
                "recoveredTicker": recovered,
                "candidateCount": len(candidates),
                "candidates": candidates,
                "securityTitles": list(event.get("securityTitles") or []),
                "secClassToken": class_token,
                "resolutionMethod": (
                    "SEC_SECURITY_TITLE_CLASS"
                    if status == "RECOVERABLE_MASSIVE_PIT_SEC_CLASS_UNIQUE"
                    else "EXACT_CIK_DATE_UNIQUE"
                    if status == "RECOVERABLE_MASSIVE_PIT_UNIQUE"
                    else None
                ),
                "source": "Massive /v3/reference/tickers cik+date active=true",
            }

    cache_output = output / "massive-query-cache.json"
    _write_json(cache_output, cache)

    result_rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    recovered_tickers: Counter[str] = Counter()
    resolution_methods: Counter[str] = Counter()
    recovered_events = 0
    queried_events = 0

    for event in unresolved:
        key = _event_key(event)
        evidence = cache.get(key)
        if evidence is None:
            status = "NOT_QUERIED_YET"
            recovered = None
            candidates: list[dict[str, Any]] = []
            class_token = _event_class_token(event)
            resolution_method = None
        else:
            queried_events += 1
            status = str(evidence["status"])
            recovered = evidence.get("recoveredTicker")
            candidates = list(evidence.get("candidates") or [])
            class_token = evidence.get("secClassToken")
            resolution_method = evidence.get("resolutionMethod")
            if recovered:
                recovered_events += 1
                recovered_tickers[str(recovered)] += 1
            if resolution_method:
                resolution_methods[str(resolution_method)] += 1
        status_counts[status] += 1
        result_rows.append(
            {
                "issuerCik": event["issuerCik"],
                "evaluationSession": event["evaluationSession"],
                "identityProblem": event["identityProblem"],
                "secRecoveryStatus": event["recoveryStatus"],
                "securityTitles": list(event.get("securityTitles") or []),
                "secClassToken": class_token,
                "massiveRecoveryStatus": status,
                "massiveRecoveredTicker": recovered,
                "resolutionMethod": resolution_method,
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
        "schemaVersion": "1.1.0",
        "dataset": "Massive PIT historical identity recovery diagnostic",
        "period": "2016-2022",
        "sourceEndpoint": "/v3/reference/tickers?cik=<CIK>&date=<evaluationSession>&active=true",
        "sourcePolicy": (
            "Recovery credit requires either exactly one active U.S. equity ticker for the "
            "exact issuer CIK and evaluation-session date, or exactly one candidate whose "
            "explicit share-class token matches the source-observed SEC security title. "
            "Ambiguous cases remain unresolved."
        ),
        "querySamplingPolicy": (
            "Round-robin by issuer CIK: one unresolved issuer-session per CIK before "
            "second dates for the same issuer."
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
        "resolutionMethodCounts": dict(sorted(resolution_methods.items())),
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
