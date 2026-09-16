"""Compatibility entry point for the fixed research amendment reconciler."""

from research_sec_reconcile_amendments_v2 import main, reconcile

__all__ = ["main", "reconcile"]

if __name__ == "__main__":
    main()
