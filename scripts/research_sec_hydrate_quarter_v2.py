"""Fallback-aware entrypoint for the research quarter runner."""

from __future__ import annotations

from typing import Any

import research_sec_hydrate_quarter as quarter
from research_sec_hydrate_with_fallback import hydrate


def validate_shard(summary: dict[str, Any], expected_total: int) -> None:
    """Accept audited fallback discovery while preserving daily-index statistics."""
    selected = int(summary["selectedOriginalBuyFilings"])
    discovered = int(summary.get("discoveredFilings", summary["matchedInDailyIndex"]))
    if selected <= 0:
        raise ValueError("empty hydration shard")
    if int(summary["eligibleOriginalBuyFilingsInQuarter"]) != expected_total:
        raise ValueError("shard eligible-quarter count disagrees with candidate universe")
    if discovered != selected:
        raise ValueError("daily-index plus audited archive fallback discovery is incomplete")
    if int(summary["hydratedAndParsedFilings"]) != selected:
        raise ValueError("hydration/parser coverage is incomplete")
    if int(summary["failureCount"]) != 0:
        raise ValueError("shard contains failures")
    if summary.get("allCanonicalKnowledgeEqualAccepted") is not True:
        raise ValueError("historical PIT clock gate failed")
    if summary.get("oosOpened") is not False:
        raise ValueError("OOS boundary was opened unexpectedly")
    if summary.get("signalReady") is not False:
        raise ValueError("research hydration must never mark signalReady")


if __name__ == "__main__":
    quarter.hydrate = hydrate
    quarter._validate_shard = validate_shard
    quarter.main()
