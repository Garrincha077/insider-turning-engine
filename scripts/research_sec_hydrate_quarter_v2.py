"""Fallback-aware entrypoint for the research quarter runner."""

from __future__ import annotations

import research_sec_hydrate_quarter as quarter
from research_sec_hydrate_with_fallback import hydrate


if __name__ == "__main__":
    quarter.hydrate = hydrate
    quarter.main()
