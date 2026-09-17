"""Optimized PIT cluster-trigger evaluator for the Phase-1 B2 research runner.

This module preserves the exact semantics of ``research_phase1_b2`` while replacing
its quadratic-per-anchor cluster search with a transaction-date sliding window.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

import research_phase1_b2 as b2


def _cluster_trigger_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return PIT B2 trigger sessions using a 30-calendar-day sliding window."""

    by_issuer_session: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        by_issuer_session[str(row["issuerCik"])][str(row["evaluationSession"])].append(row)

    events: list[dict[str, Any]] = []
    max_span = timedelta(days=b2.WINDOW_DAYS)
    for issuer_cik, session_rows in by_issuer_session.items():
        known: list[dict[str, Any]] = []
        for session in sorted(session_rows):
            new_rows = session_rows[session]
            known.extend(new_rows)
            new_ids = {int(row["sourceSeq"]) for row in new_rows}
            ordered = sorted(
                known,
                key=lambda row: (
                    str(row["transactionDate"]),
                    int(row["sourceSeq"]),
                ),
            )

            owner_counts: Counter[str] = Counter()
            new_in_window = 0
            left = 0
            best_owners: set[str] = set()
            best_anchor: str | None = None

            for right, row in enumerate(ordered):
                owner = str(row["ownerCik"])
                owner_counts[owner] += 1
                if int(row["sourceSeq"]) in new_ids:
                    new_in_window += 1
                right_date = date.fromisoformat(str(row["transactionDate"]))

                while left <= right:
                    left_row = ordered[left]
                    left_date = date.fromisoformat(str(left_row["transactionDate"]))
                    if right_date - left_date <= max_span:
                        break
                    left_owner = str(left_row["ownerCik"])
                    owner_counts[left_owner] -= 1
                    if owner_counts[left_owner] <= 0:
                        del owner_counts[left_owner]
                    if int(left_row["sourceSeq"]) in new_ids:
                        new_in_window -= 1
                    left += 1

                if new_in_window > 0 and len(owner_counts) > len(best_owners):
                    best_owners = set(owner_counts)
                    best_anchor = right_date.isoformat()

            if len(best_owners) < b2.IMPORTANT_OWNER_COUNT:
                continue
            if not (b2.DEVELOPMENT_START <= session <= b2.DEVELOPMENT_END):
                continue
            tickers = sorted({str(row["ticker"]) for row in new_rows if row.get("ticker")})
            events.append(
                {
                    "issuerCik": issuer_cik,
                    "evaluationSession": session,
                    "knowledgeAtFirst": min(str(row["knowledgeAt"]) for row in new_rows),
                    "knowledgeAtLast": max(str(row["knowledgeAt"]) for row in new_rows),
                    "tickers": tickers,
                    "clusterOwnerCount": len(best_owners),
                    "clusterOwnerIds": sorted(best_owners),
                    "clusterAnchorTransactionDate": best_anchor,
                    "strongCluster": len(best_owners) >= b2.STRONG_OWNER_COUNT,
                }
            )

    events.sort(
        key=lambda row: (
            str(row["evaluationSession"]),
            str(row["knowledgeAtFirst"]),
            str(row["issuerCik"]),
        )
    )
    return events


def main() -> None:
    b2._cluster_trigger_events = _cluster_trigger_events
    b2.main()


if __name__ == "__main__":
    main()
