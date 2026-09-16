"""Export bounded unresolved issuer-session market events for coverage research.

This research-only diagnostic reuses the frozen issuer-session audit helpers. It
never reads 2023+ data, never changes production scoring, and emits the SEC CIK,
historical SEC ticker, evaluation session, and explicit market-miss reason needed
for targeted provider supplementation.
"""

from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from research_market_event_audit import (
    END_YEAR,
    SEALED_YEAR,
    START_YEAR,
    _build_market_db,
    _load_events,
    _market_files,
    _regular_sessions,
)


def export_unresolved(*, sec_path: Path, market_root: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    events_by_ticker, sec_diag = _load_events(sec_path)
    files = _market_files(market_root)
    db_path = output / "market-unresolved.sqlite"
    if db_path.exists():
        db_path.unlink()
    market_diag = _build_market_db(files, db_path)

    unresolved: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    ticker_counts: Counter[str] = Counter()

    conn = sqlite3.connect(db_path)
    try:
        for ticker, events in sorted(events_by_ticker.items()):
            rows = conn.execute(
                "SELECT date,open,high,low,close,volume,trade_count,terminal "
                "FROM market WHERE ticker=? ORDER BY date",
                (ticker,),
            ).fetchall()
            regular_dates, _ = _regular_sessions(rows)

            for event in events:
                if bool(event["identityAmbiguous"]):
                    continue

                evaluation_session = str(event["evaluationSession"])
                if int(evaluation_session[:4]) >= SEALED_YEAR:
                    raise ValueError("sealed OOS boundary violated by unresolved event")

                reason: str | None = None
                if not regular_dates:
                    reason = "noRegularMarketHistory"
                else:
                    entry_index = bisect.bisect_right(regular_dates, evaluation_session)
                    if entry_index >= len(regular_dates):
                        reason = "noNextRegularSession"

                if reason is None:
                    continue

                record = {
                    "issuerCik": str(event["issuerCik"]),
                    "ticker": ticker,
                    "evaluationSession": evaluation_session,
                    "knowledgeAtFirst": str(event["knowledgeAtFirst"]),
                    "knowledgeAtLast": str(event["knowledgeAtLast"]),
                    "knowledgeYear": int(event["knowledgeYear"]),
                    "rawQualifiedRows": int(event["rawQualifiedRows"]),
                    "reason": reason,
                }
                unresolved.append(record)
                reason_counts[reason] += 1
                ticker_counts[ticker] += 1
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)

    unresolved.sort(
        key=lambda row: (
            -ticker_counts[str(row["ticker"])],
            str(row["ticker"]),
            str(row["evaluationSession"]),
            str(row["issuerCik"]),
        )
    )
    (output / "unresolved-market-events.json").write_text(
        json.dumps(unresolved, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    top_tickers = [
        {"ticker": ticker, "unresolvedIssuerSessions": count}
        for ticker, count in ticker_counts.most_common(100)
    ]
    (output / "top-unresolved-tickers.json").write_text(
        json.dumps(top_tickers, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    unique_ciks = {str(row["issuerCik"]) for row in unresolved if row["issuerCik"]}
    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "dataset": "Unresolved issuer-session market identities",
        "period": f"{START_YEAR}-{END_YEAR}",
        "qualifiedIssuerSessionEvents": int(sec_diag["qualifiedIssuerSessionEvents"]),
        "unresolvedIssuerSessionEvents": len(unresolved),
        "unresolvedUniqueTickers": len(ticker_counts),
        "unresolvedUniqueIssuerCiks": len(unique_ciks),
        "reasons": dict(sorted(reason_counts.items())),
        "topUnresolvedTickers": top_tickers[:20],
        "marketRowsRead": int(market_diag["marketRowsRead"]),
        "identityPolicyInheritedFromAudit": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "status": "MARKET_UNRESOLVED_IDENTITY_EXPORT_COMPLETE",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sec", type=Path, required=True)
    parser.add_argument("--market-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export_unresolved(sec_path=args.sec, market_root=args.market_root, output=args.output)


if __name__ == "__main__":
    main()
