"""Publication of validated SEC facts is separate from predictive permission."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from insider_turning_engine.domain.research import ResearchSnapshot

from .dashboard import (
    dashboard_experimental_publication_policy,
    dashboard_publication_policy,
    validate_dashboard_directory,
)


def validate_publication(directory: Path) -> str:
    """Validate every file/hash/run before allowing factual or legacy publication.

    Partial market coverage and unvalidated scores cannot hide valid SEC facts.
    This does NOT authorize digest delivery or predictive alerts.
    """
    manifest = validate_dashboard_directory(directory, require_settings=True)
    if any(row["path"] == "research-v2.json" for row in manifest["files"]):
        research = ResearchSnapshot.model_validate_json(
            (directory / "research-v2.json").read_bytes())
        if (manifest["quality"]["canonicalValid"] is not True
                or not research.economic_transactions
                or research.readiness.dashboard.status == "BLOCKED"
                or research.readiness.predictive.status != "BLOCKED"):
            raise ValueError("factual research publication blocked")
        return "DAILY_RESEARCH: partial facts disclosed; predictive alerts disabled"
    if dashboard_publication_policy(manifest)[0]:
        return "LEGACY_VALIDATED"
    if dashboard_experimental_publication_policy(manifest) == (True, False):
        return "LEGACY_EXPERIMENTAL: predictive alerts disabled"
    raise ValueError("dashboard publication policy blocked")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({"publication": validate_publication(args.directory), "alertsAllowed": False}))


if __name__ == "__main__":
    main()
