"""Attach bounded SEC security-title evidence to identity-recovery events.

Research-only helper. It reads the same effective 2013-2022 SEC artifact used by
the identity diagnostic, but target events remain 2016-2022. The helper only
adds source-observed security titles to the research event artifact. It never
rewrites canonical SEC data, never changes scoring, and rejects 2023+ input.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import exchange_calendars as xcals

from research_market_event_audit import (
    END_YEAR,
    SEALED_YEAR,
    START_YEAR,
    _evaluation_session,
    _qualified_purchase,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(*, sec_path: Path, events_path: Path, summary_path: Path) -> dict[str, Any]:
    events = _load_json(events_path)
    if not isinstance(events, list):
        raise ValueError("identity recovery events must be a JSON list")

    target_keys: set[tuple[str, str]] = set()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("identity recovery event is not an object")
        session = str(event.get("evaluationSession") or "")
        if not session or not START_YEAR <= int(session[:4]) <= END_YEAR:
            raise ValueError("identity target outside frozen 2016-2022 period")
        target_keys.add((str(event.get("issuerCik") or ""), session))

    calendar = xcals.get_calendar("XNYS")
    titles_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    rows_read = 0
    qualified_rows = 0

    with sec_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            knowledge = str(row["timestamps"]["knowledgeAt"])
            year = int(knowledge[:4])
            if year >= SEALED_YEAR:
                raise ValueError("sealed OOS boundary violated by SEC input")
            if not START_YEAR <= year <= END_YEAR:
                continue
            rows_read += 1
            if not _qualified_purchase(row):
                continue
            qualified_rows += 1

            cik = str(row.get("issuer", {}).get("cik") or "")
            session = _evaluation_session(knowledge, calendar)
            key = (cik, session)
            if key not in target_keys:
                continue
            title = str(row.get("security", {}).get("title") or "").strip()
            if title:
                titles_by_key[key].add(title)

    title_counts: Counter[str] = Counter()
    events_with_titles = 0
    events_with_multiple_titles = 0
    for event in events:
        key = (str(event.get("issuerCik") or ""), str(event["evaluationSession"]))
        titles = sorted(titles_by_key.get(key, set()))
        event["securityTitles"] = titles
        if titles:
            events_with_titles += 1
            title_counts.update(titles)
        if len(titles) > 1:
            events_with_multiple_titles += 1

    _write_json(events_path, events)

    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "dataset": "SEC security-title evidence for PIT identity recovery",
        "period": "2016-2022",
        "effectiveSecRowsRead": rows_read,
        "qualifiedPurchaseRowsRead": qualified_rows,
        "identityTargetEvents": len(events),
        "eventsWithSecurityTitles": events_with_titles,
        "eventsWithoutSecurityTitles": len(events) - events_with_titles,
        "eventsWithMultipleSecurityTitles": events_with_multiple_titles,
        "topSecurityTitles": [
            {"securityTitle": title, "issuerSessionEvents": count}
            for title, count in title_counts.most_common(30)
        ],
        "oosOpened": False,
        "productionScoringChanged": False,
        "canonicalSecChanged": False,
        "status": "SEC_IDENTITY_SECURITY_TITLE_EVIDENCE_COMPLETE",
    }
    _write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sec", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    run(sec_path=args.sec, events_path=args.events, summary_path=args.summary)


if __name__ == "__main__":
    main()
