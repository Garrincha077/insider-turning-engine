"""Persistable v1 company state machine with promotion gates and hysteresis."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class CompanyState(StrEnum):
    FALLING = "FALLING"
    INSIDER_ACCUMULATION = "INSIDER_ACCUMULATION"
    BASE_FORMING = "BASE_FORMING"
    EARLY_TURN = "EARLY_TURN"
    CONFIRMED_TURN = "CONFIRMED_TURN"


ORDER = tuple(CompanyState)


@dataclass(frozen=True)
class StateEvaluation:
    previous_state: CompanyState
    state: CompanyState
    transitioned: bool
    failed_evaluations: int
    reason_codes: tuple[str, ...]
    state_version: str = "state.v1"


def _finite(facts: Mapping[str, Any], key: str) -> float | None:
    value = facts.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _true(facts: Mapping[str, Any], key: str) -> bool:
    return facts.get(key) is True


class StateMachine:
    """Evaluate one daily observation without ever skipping a state."""

    version = "state.v1"

    @staticmethod
    def _falling(facts: Mapping[str, Any]) -> bool:
        """Configured baseline: negative 3M return while below the 50D MA."""

        return_3m = _finite(facts, "return_3m")
        close = _finite(facts, "close")
        ma50 = _finite(facts, "ma50")
        if return_3m is None or close is None or ma50 is None:
            return False
        return return_3m < 0 and close < ma50

    @staticmethod
    def _accumulation(facts: Mapping[str, Any]) -> bool:
        drawdown = _finite(facts, "drawdown_from_52_week_high")
        insider = _finite(facts, "company_insider_score")
        age = _finite(facts, "qualified_buy_age_days")
        return (
            drawdown is not None
            and drawdown <= -0.20
            and insider is not None
            and insider >= 65
            and age is not None
            and age <= 30
        )

    @staticmethod
    def _base(facts: Mapping[str, Any]) -> bool:
        evidence = sum(
            _true(facts, key)
            for key in ("volatility_contraction", "volume_dryup", "ma20_flattening")
        )
        return _true(facts, "no_new_52_week_low_20_sessions") and evidence >= 2

    @staticmethod
    def _early(facts: Mapping[str, Any]) -> bool:
        turn = _finite(facts, "turn_score")
        slope = _finite(facts, "mansfield_market_slope_4w")
        return (
            turn is not None
            and turn >= 60
            and _true(facts, "ordinary_rs_improving_4w")
            and slope is not None
            and slope > 0
        )

    @staticmethod
    def _confirmed(facts: Mapping[str, Any]) -> bool:
        days = _finite(facts, "close_above_ma50_days_last10")
        mansfield = _finite(facts, "mansfield_market")
        confirmation = (mansfield is not None and mansfield >= 0) or _true(
            facts, "cost_basis_reclaim"
        )
        return days is not None and days >= 5 and confirmation

    def _qualifies(self, state: CompanyState, facts: Mapping[str, Any]) -> bool:
        if state is CompanyState.FALLING:
            return self._falling(facts)
        if state is CompanyState.INSIDER_ACCUMULATION:
            return self._accumulation(facts)
        if state is CompanyState.BASE_FORMING:
            return self._base(facts)
        if state is CompanyState.EARLY_TURN:
            return self._early(facts)
        return self._confirmed(facts)

    def evaluate(
        self,
        previous_state: CompanyState | str,
        facts: Mapping[str, Any],
        *,
        consecutive_failed_evaluations: int = 0,
    ) -> StateEvaluation:
        previous = CompanyState(previous_state)
        if _true(facts, "new_52_week_low"):
            return StateEvaluation(
                previous,
                CompanyState.FALLING,
                previous is not CompanyState.FALLING,
                0,
                ("NEW_52W_LOW_RESET",),
            )

        # A fully supplied baseline that fails the locked FALLING predicate
        # must not be promoted.  If a legacy caller omits the baseline facts,
        # let the promotion gates operate on the supplied evidence and avoid
        # inventing a market state from missing data.
        baseline_present = any(key in facts for key in ("return_3m", "close", "ma50"))
        if previous is CompanyState.FALLING and baseline_present and not self._falling(facts):
            return StateEvaluation(
                previous,
                previous,
                False,
                consecutive_failed_evaluations,
                ("FALLING_PREDICATE_NOT_MET", "NO_TRACKED_STATE_PROMOTION"),
            )

        current_index = ORDER.index(previous)
        if current_index < len(ORDER) - 1:
            next_state = ORDER[current_index + 1]
            promoters = {
                CompanyState.INSIDER_ACCUMULATION: self._accumulation,
                CompanyState.BASE_FORMING: self._base,
                CompanyState.EARLY_TURN: self._early,
                CompanyState.CONFIRMED_TURN: self._confirmed,
            }
            if promoters[next_state](facts):
                return StateEvaluation(
                    previous,
                    next_state,
                    True,
                    0,
                    (f"PROMOTED_TO_{next_state.value}",),
                )

        if self._qualifies(previous, facts):
            return StateEvaluation(previous, previous, False, 0, ("STATE_HELD",))

        failures = consecutive_failed_evaluations + 1
        if failures < 2:
            return StateEvaluation(previous, previous, False, failures, ("DOWNGRADE_PENDING",))
        downgraded = ORDER[max(0, current_index - 1)]
        return StateEvaluation(
            previous,
            downgraded,
            downgraded is not previous,
            0,
            (f"DOWNGRADED_TO_{downgraded.value}",),
        )


__all__ = ["CompanyState", "ORDER", "StateEvaluation", "StateMachine"]
