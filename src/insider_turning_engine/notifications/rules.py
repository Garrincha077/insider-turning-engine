"""Versioned v1 alert predicates and publication quality gates."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from .models import AlertCandidate, AlertType, QualityGateResult, Severity

_THRESHOLDS = {
    "parse_success_rate": 0.995,
    "market_data_coverage_rate": 0.90,
    "core_branch_coverage_rate": 0.85,
}


def _get(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        if name in source:
            return source[name]
        camel = name.split("_")[0] + "".join(p.title() for p in name.split("_")[1:])
        if camel in source:
            return source[camel]
        # Scores are often grouped by model in signal snapshots.
        for group in ("scores", "score", "metrics", "signals", "quality"):
            nested = source.get(group)
            if isinstance(nested, Mapping) and name in nested:
                return nested[name]
    else:
        if hasattr(source, name):
            return getattr(source, name)
        camel = name.split("_")[0] + "".join(p.title() for p in name.split("_")[1:])
        if hasattr(source, camel):
            return getattr(source, camel)
    return default


def _number(source: Any, name: str, default: float = 0.0) -> float:
    value = _get(source, name, default)
    if isinstance(value, Mapping):
        value = value.get("slope", value.get("value", default))
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _flags(source: Any) -> set[str]:
    flags = _get(source, "flags", _get(source, "alert_flags", ()))
    if isinstance(flags, Mapping):
        return {str(key) for key, value in flags.items() if value}
    return {str(flag).replace("-", "_").lower() for flag in (flags or ())}


def assess_quality_gates(
    quality: Any = None,
    *,
    stale_benchmark: bool | None = None,
    canonical_valid: bool | None = None,
    scoring_methodology_complete: bool | None = None,
    parse_success_rate: float | None = None,
    market_data_coverage_rate: float | None = None,
    core_branch_coverage_rate: float | None = None,
) -> QualityGateResult:
    """Return fail-closed publication eligibility for alert delivery.

    Every quality clock is required for an alerting decision. Missing evidence
    is fail-closed: it produces a suppressed candidate rather than a plausible
    send. This keeps a partial/degraded run auditable without contacting a
    notification provider.
    """

    def q(name: str, explicit: Any) -> Any:
        return explicit if explicit is not None else _get(quality, name)

    benchmark_state = (
        stale_benchmark
        if stale_benchmark is not None
        else _get(quality, "stale_benchmark", _get(quality, "benchmark_stale"))
    )
    if benchmark_state is None:
        benchmark_fresh = _get(quality, "benchmark_fresh")
        if isinstance(benchmark_fresh, bool):
            benchmark_state = not benchmark_fresh
    canonical = canonical_valid if canonical_valid is not None else _get(quality, "canonical_valid")
    methodology = (
        scoring_methodology_complete
        if scoring_methodology_complete is not None
        else _get(
            quality,
            "scoring_methodology_complete",
            _get(quality, "methodology_complete"),
        )
    )

    reasons: list[str] = []
    checks: dict[str, bool] = {}
    benchmark_available = isinstance(benchmark_state, bool)
    checks["benchmark_available"] = benchmark_available
    if not benchmark_available:
        reasons.append("MISSING_BENCHMARK")
    stale = benchmark_state is True
    checks["stale_benchmark"] = benchmark_available and not stale
    if stale:
        reasons.append("STALE_BENCHMARK")
    checks["canonical_valid"] = canonical is True
    if canonical is None:
        reasons.append("MISSING_CANONICAL_EVIDENCE")
    elif canonical is not True:
        reasons.append("CANONICAL_INVALID")
    checks["scoring_methodology_complete"] = methodology is True
    if methodology is None:
        reasons.append("MISSING_SCORING_METHODOLOGY_EVIDENCE")
    elif methodology is not True:
        reasons.append("SCORING_METHODOLOGY_INCOMPLETE")

    for name, explicit in (
        ("parse_success_rate", parse_success_rate),
        ("market_data_coverage_rate", market_data_coverage_rate),
        ("core_branch_coverage_rate", core_branch_coverage_rate),
    ):
        value = q(name, explicit)
        coherent = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )
        if isinstance(value, Mapping):
            numerator = value.get("numerator")
            denominator = value.get("denominator")
            value = value.get("rate")
            coherent = (
                isinstance(numerator, int)
                and not isinstance(numerator, bool)
                and isinstance(denominator, int)
                and not isinstance(denominator, bool)
                and denominator > 0
                and 0 <= numerator <= denominator
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and abs(float(value) - numerator / denominator) <= 1e-9
            )
        if value is None:
            checks[name] = False
            reasons.append(f"MISSING_{name.upper()}")
            continue
        try:
            numeric = float(value)
            passed = (
                coherent
                and math.isfinite(numeric)
                and 0.0 <= numeric <= 1.0
                and numeric >= _THRESHOLDS[name]
            )
        except (TypeError, ValueError, OverflowError):
            passed = False
        checks[name] = passed
        if not passed:
            reasons.append(f"INSUFFICIENT_{name.upper()}")
    explicit_gate = _get(quality, "quality_gate_passed", _get(quality, "passed"))
    checks["quality_gate_passed"] = explicit_gate is True
    if explicit_gate is None:
        reasons.append("QUALITY_GATE_EVIDENCE_MISSING")
    elif explicit_gate is not True:
        reasons.append("QUALITY_GATE_FAILED")
    return QualityGateResult(not reasons, tuple(reasons), checks)


def _severity(alert_type: AlertType, snapshot: Any) -> Severity:
    value = _get(snapshot, "severity")
    if value is not None:
        return Severity(value)
    return {
        AlertType.MAJOR_INSIDER_BUY: Severity.HIGH,
        AlertType.STEALTH_ACCUMULATION: Severity.WATCH,
        AlertType.TURNING: Severity.HIGH,
    }[alert_type]


def _candidate(
    alert_type: AlertType,
    snapshot: Any,
    *,
    issuer_cik: str,
    trigger_snapshot_id: str,
    reasons: list[str],
    quality: QualityGateResult,
    reason_overrides: Mapping[str, Any] | None,
    now: datetime | None,
) -> AlertCandidate:
    override = (reason_overrides or {}).get(alert_type.value)
    if override is None:
        override = _get(snapshot, "reason_overrides", {})
        override = override.get(alert_type.value) if isinstance(override, Mapping) else None
    if override is not None:
        reasons = [
            str(reason) for reason in (override if not isinstance(override, str) else [override])
        ]
    state = _get(snapshot, "state", _get(snapshot, "current_state"))
    previous_state = _get(snapshot, "previous_state", _get(snapshot, "from_state"))
    delta = _get(snapshot, "absolute_score_delta")
    important_flag = _get(snapshot, "important_flag", False)
    if not isinstance(important_flag, bool):
        raise ValueError("important_flag must be a boolean")
    score = _number(snapshot, "total_score")
    if delta is None and _get(snapshot, "previous_total_score") is not None:
        delta = abs(score - _number(snapshot, "previous_total_score"))
    return AlertCandidate(
        issuer_cik=str(issuer_cik),
        ticker=_get(snapshot, "ticker"),
        alert_type=alert_type,
        trigger_snapshot_id=str(trigger_snapshot_id),
        score=score,
        severity=_severity(alert_type, snapshot),
        important_flag=important_flag,
        reasons=tuple(reasons),
        state=state,
        previous_state=previous_state,
        previous_severity=_get(snapshot, "previous_severity"),
        previous_important_flag=_get(snapshot, "previous_important_flag"),
        absolute_score_delta=float(delta) if delta is not None else None,
        created_at=now or datetime.now(UTC),
        suppression_reasons=() if quality.allowed else quality.reasons,
    )


def evaluate_alert_rules(
    snapshot: Any,
    *,
    issuer_cik: str | None = None,
    trigger_snapshot_id: str | None = None,
    quality: Any = None,
    reason_overrides: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> tuple[AlertCandidate, ...]:
    """Evaluate all three v1 rules, preserving candidates under bad quality.

    Suppressed candidates are retained by the outbox for auditability and are
    marked with ``suppression_reasons``; no channel is contacted for them.
    """

    issuer = issuer_cik or _get(snapshot, "issuer_cik", _get(snapshot, "cik"))
    snap_id = trigger_snapshot_id or _get(
        snapshot, "trigger_snapshot_id", _get(snapshot, "snapshot_id")
    )
    if issuer is None or snap_id is None:
        raise ValueError("issuer_cik and trigger_snapshot_id are required")
    gate = assess_quality_gates(quality if quality is not None else snapshot)
    flags = _flags(snapshot)
    value = _number(snapshot, "transaction_value_usd")
    conviction = _number(snapshot, "conviction_score")
    candidates: list[AlertCandidate] = []

    major_reasons: list[str] = []
    if conviction >= 80 and value >= 250_000:
        major_reasons.append("conviction_score >= 80 and transaction_value_usd >= 250000")
    if value >= 1_000_000:
        major_reasons.append("transaction_value_usd >= 1000000")
    for flag in ("strong_cluster", "first_buy", "largest_buy"):
        if flag in flags:
            major_reasons.append(f"flag: {flag}")
    if major_reasons:
        candidates.append(
            _candidate(
                AlertType.MAJOR_INSIDER_BUY,
                snapshot,
                issuer_cik=str(issuer),
                trigger_snapshot_id=str(snap_id),
                reasons=major_reasons,
                quality=gate,
                reason_overrides=reason_overrides,
                now=now,
            )
        )

    stealth_ok = (
        _number(snapshot, "company_insider_score") >= 70
        and _number(snapshot, "divergence_score") >= 75
        and _number(snapshot, "turn_score") >= 45
        and bool(
            _get(
                snapshot,
                "no_new_52_week_low_20_sessions",
                _get(snapshot, "no_new_52_week_low", False),
            )
        )
        and _number(
            snapshot,
            "ordinary_rs_3m_slope_4w",
            _number(snapshot, "ordinary_rs_3m_slope"),
        )
        > 0
        and _number(
            snapshot,
            "mansfield_market_slope_4w",
            _number(snapshot, "mansfield_market_slope"),
        )
        > 0
    )
    if stealth_ok:
        candidates.append(
            _candidate(
                AlertType.STEALTH_ACCUMULATION,
                snapshot,
                issuer_cik=str(issuer),
                trigger_snapshot_id=str(snap_id),
                reasons=[
                    "company_insider_score >= 70",
                    "divergence_score >= 75",
                    "turn_score >= 45",
                    "no new 52-week low for 20 sessions",
                    "ordinary RS 4-week slope > 0",
                    "Mansfield market 4-week slope > 0",
                ],
                quality=gate,
                reason_overrides=reason_overrides,
                now=now,
            )
        )

    transition = _get(snapshot, "transition_to", _get(snapshot, "to_state"))
    if (
        transition in {"EARLY_TURN", "CONFIRMED_TURN"}
        and _number(snapshot, "total_score") >= 75
        and _number(snapshot, "company_insider_score") >= 65
        and _number(snapshot, "divergence_score") >= 65
    ):
        candidates.append(
            _candidate(
                AlertType.TURNING,
                snapshot,
                issuer_cik=str(issuer),
                trigger_snapshot_id=str(snap_id),
                reasons=[
                    f"transition to {transition}",
                    "total_score >= 75",
                    "company_insider_score >= 65",
                    "divergence_score >= 65",
                ],
                quality=gate,
                reason_overrides=reason_overrides,
                now=now,
            )
        )
    return tuple(candidates)


match_alert_rules = evaluate_alert_rules
evaluate_alerts = evaluate_alert_rules

__all__ = ["assess_quality_gates", "evaluate_alert_rules", "evaluate_alerts", "match_alert_rules"]
