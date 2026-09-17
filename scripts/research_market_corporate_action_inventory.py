"""Performance-blind Alpaca corporate-action inventory for persisted research events.

The inventory reads only event identity/date columns, requests corporate actions
bounded to 2016-2022, and never inspects raw/excess/MAE performance fields.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

API_URL = "https://data.alpaca.markets/v1/corporate-actions"
START = "2016-01-01"
END = "2022-12-31"
SEALED_YEAR = 2023
BATCH_SIZE = 50
MAX_ATTEMPTS = 6

# Frozen by the Phase-1 security-continuity correction gate before corrected
# performance is recomputed. New provider types must not silently expand scope.
FROZEN_TYPES = (
    "reverse_split",
    "forward_split",
    "unit_split",
    "cash_dividend",
    "stock_dividend",
    "spin_off",
    "cash_merger",
    "stock_merger",
    "stock_and_cash_merger",
    "redemption",
    "name_change",
    "worthless_removal",
    "rights_distribution",
)
FROZEN_BUCKETS = (
    "reverse_splits",
    "forward_splits",
    "unit_splits",
    "cash_dividends",
    "stock_dividends",
    "spin_offs",
    "cash_mergers",
    "stock_mergers",
    "stock_and_cash_mergers",
    "redemptions",
    "name_changes",
    "worthless_removals",
    "rights_distributions",
)


def _event_tickers(path: Path) -> list[str]:
    tickers: set[str] = set()
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"ticker", "entrySession", "evaluationSession"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("event file missing required identity/date fields")
        for row in reader:
            for field in ("evaluationSession", "entrySession"):
                text = str(row.get(field) or "").strip()
                if text and int(text[:4]) >= SEALED_YEAR:
                    raise ValueError("sealed OOS boundary violated by event metadata")
            ticker = str(row.get("ticker") or "").strip().upper()
            if ticker:
                tickers.add(ticker)
    if not tickers:
        raise ValueError("no event tickers found")
    return sorted(tickers)


def _batches(items: list[str], size: int = BATCH_SIZE) -> Iterator[list[str]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _request_page(
    client: httpx.Client,
    headers: dict[str, str],
    params: dict[str, str | int],
) -> dict[str, Any]:
    delay = 1.0
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.get(API_URL, headers=headers, params=params)
            if response.status_code == 429:
                retry_after = response.headers.get("retry-after")
                pause = float(retry_after) if retry_after else delay
                time.sleep(max(0.5, min(pause, 30.0)))
                delay = min(delay * 2, 30.0)
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("corporate-action response is not an object")
            return payload
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt == MAX_ATTEMPTS:
                break
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
    raise RuntimeError(f"corporate-action request failed: {last_error}")


def _date_value(row: dict[str, Any]) -> str | None:
    for field in ("effective_date", "process_date", "ex_date"):
        value = str(row.get(field) or "").strip()
        if value:
            return value[:10]
    return None


def _normalize(bucket: str, row: dict[str, Any]) -> dict[str, Any]:
    action_date = _date_value(row)
    if action_date and int(action_date[:4]) >= SEALED_YEAR:
        raise ValueError("sealed OOS boundary violated by corporate action")
    keep = {
        key: value
        for key, value in row.items()
        if key
        in {
            "id",
            "corporate_action_type",
            "symbol",
            "cusip",
            "old_symbol",
            "old_cusip",
            "new_symbol",
            "new_cusip",
            "source_symbol",
            "source_cusip",
            "source_rate",
            "acquirer_symbol",
            "acquirer_cusip",
            "acquirer_rate",
            "acquiree_symbol",
            "acquiree_cusip",
            "acquiree_rate",
            "cash_rate",
            "rate",
            "new_rate",
            "old_rate",
            "process_date",
            "effective_date",
            "ex_date",
            "record_date",
            "payable_date",
        }
    }
    return {"bucket": bucket, "actionDate": action_date, **keep}


def _page_actions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Read Alpaca's top-level CA arrays without expanding the frozen type set."""
    normalized: list[dict[str, Any]] = []
    for bucket in FROZEN_BUCKETS:
        rows = payload.get(bucket) or []
        if not isinstance(rows, list):
            raise ValueError(f"corporate-action bucket {bucket} is not a list")
        for raw in rows:
            if not isinstance(raw, dict):
                raise ValueError(f"corporate-action bucket {bucket} contains a non-object")
            normalized.append(_normalize(bucket, raw))
    return normalized


def run(*, events_path: Path, output_dir: Path) -> dict[str, Any]:
    api_key = os.environ.get("ALPACA_API_KEY_ID", "").strip()
    api_secret = os.environ.get("ALPACA_API_SECRET_KEY", "").strip()
    if not api_key or not api_secret:
        raise ValueError("Alpaca credentials are required")

    tickers = _event_tickers(events_path)
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
        "Accept": "application/json",
        "User-Agent": "InsiderTurningEngine-Research/1.0",
    }
    by_id: dict[str, dict[str, Any]] = {}
    pages = 0

    with httpx.Client(timeout=60.0, follow_redirects=False) as client:
        for batch in _batches(tickers):
            page_token: str | None = None
            while True:
                params: dict[str, str | int] = {
                    "symbols": ",".join(batch),
                    "types": ",".join(FROZEN_TYPES),
                    "start": START,
                    "end": END,
                    "limit": 1000,
                    "sort": "asc",
                }
                if page_token:
                    params["page_token"] = page_token
                payload = _request_page(client, headers, params)
                pages += 1
                for normalized in _page_actions(payload):
                    action_id = str(normalized.get("id") or "").strip()
                    if not action_id:
                        raise ValueError("corporate action missing id")
                    by_id[action_id] = normalized
                token = payload.get("next_page_token")
                page_token = str(token) if token else None
                if not page_token:
                    break

    actions = sorted(
        by_id.values(),
        key=lambda row: (
            str(row.get("actionDate") or ""),
            str(row.get("bucket") or ""),
            str(row.get("id") or ""),
        ),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory = {
        "schemaVersion": 1,
        "period": [START, END],
        "performanceRead": False,
        "researchOnly": True,
        "oosOpened": False,
        "productionScoringChanged": False,
        "frozenTypes": list(FROZEN_TYPES),
        "eventTickerCount": len(tickers),
        "requestPages": pages,
        "actionCount": len(actions),
        "actions": actions,
    }
    (output_dir / "corporate-actions.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {key: value for key, value in inventory.items() if key != "actions"}
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(events_path=args.events, output_dir=args.output_dir), indent=2))


if __name__ == "__main__":
    main()
