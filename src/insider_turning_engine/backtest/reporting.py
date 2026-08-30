"""Deterministic backtest reporting and formal validation gates.

The backtest engine owns event scheduling and outcome construction.  This
module is deliberately a read-only projection over those contracts: it does
not re-score signals, search weights, or expose sealed OOS data to a tuner.
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Any

from .models import (
    BacktestCaveat,
    BacktestEvent,
    BacktestPeriod,
    BacktestResult,
    BacktestSignal,
    EventGroup,
    ForwardReturn,
    OOSReport,
    PeriodResults,
)

_REPORT_HORIZONS: tuple[int, ...] = (63, 126, 252)
_BENCHMARK_ALIASES: dict[str, str] = {
    "simple_ps": "simple_ps",
    "simple p/s": "simple_ps",
    "simple_ratio": "simple_ps",
    "unique_buyer_ratio": "unique_buyer_ratio",
    "unique buyer ratio": "unique_buyer_ratio",
    "largest_buys": "largest_buys",
    "largest buys": "largest_buys",
    "cluster_buys": "cluster_buys",
    "cluster buys": "cluster_buys",
    "cluster_buy": "cluster_buys",
    "full_engine": "full_engine",
    "full engine": "full_engine",
    "top_decile": "full_engine",
}
_SIMPLE_BENCHMARKS = ("simple_ps", "unique_buyer_ratio", "largest_buys", "cluster_buys")
BacktestSignalLike = BacktestSignal


class ReportingError(ValueError):
    """Raised when a reporting input cannot be interpreted safely."""


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    """A reproducible percentile bootstrap interval for a sample median."""

    estimate: float | None
    lower: float | None
    upper: float | None
    confidence: float
    iterations: int
    seed: int

    @property
    def lower_ci(self) -> float | None:
        """Alias useful to tabular/report consumers."""

        return self.lower

    @property
    def upper_ci(self) -> float | None:
        return self.upper


@dataclass(frozen=True, slots=True)
class MetricSummary:
    """Return and risk metrics for one event group at one horizon."""

    horizon_sessions: int
    event_count: int
    observed_count: int
    attrited_count: int
    median_stock_return: float | None
    median_spy_excess_return: float | None
    mean_spy_excess_return: float | None
    win_rate: float | None
    downside_tail: float | None
    median_mae: float | None

    @property
    def attrition_rate(self) -> float:
        return self.attrited_count / self.event_count if self.event_count else 0.0

    @property
    def downside_tail_10pct(self) -> float | None:
        return self.downside_tail


@dataclass(frozen=True, slots=True)
class BenchmarkComparison:
    """Metrics for one benchmark selection rule."""

    name: str
    display_name: str
    event_count: int
    attrited_count: int
    metrics: Mapping[int, MetricSummary]
    events: tuple[BacktestEvent, ...] = ()

    def metric(self, horizon: int | str = 126) -> MetricSummary:
        """Get one horizon, accepting ``3M``, ``6M`` and ``12M`` labels."""

        if isinstance(horizon, str):
            labels = {"3M": 63, "6M": 126, "12M": 252, "1M": 21}
            horizon = labels[horizon.upper()] if horizon.upper() in labels else int(horizon)
        try:
            return self.metrics[int(horizon)]
        except KeyError as exc:
            raise ReportingError(f"horizon {horizon} is not available") from exc


@dataclass(frozen=True, slots=True)
class GateAssessment:
    """Formal PASS/INCONCLUSIVE/FAIL outcome for the sealed OOS study."""

    status: str
    point_estimate: float | None
    interval: BootstrapInterval
    best_simple_benchmark: str | None
    sealed_oos_events: int
    minimum_events: int
    reason: str
    observed_eligible_oos_outcomes: int = 0

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


@dataclass(frozen=True, slots=True)
class ValidationEvidence:
    """Independent evidence required before an OOS performance claim.

    ``None`` means the evidence was not supplied and deliberately yields an
    inconclusive gate.  ``False`` or a below-threshold rate is an explicit
    failed control and yields ``FAIL``.  This separation makes a missing
    attestation impossible to turn into a green result.
    """

    parse_success_rate: float | None = None
    market_coverage: float | None = None
    core_branch_coverage: float | None = None
    canonical_valid: bool | None = None
    schema_valid: bool | None = None
    hash_valid: bool | None = None
    temporal_valid: bool | None = None
    benchmark_fresh: bool | None = None

    @property
    def market_coverage_rate(self) -> float | None:
        """Compatibility spelling for evidence exporters."""

        return self.market_coverage


@dataclass(frozen=True, slots=True)
class DataQualityDisclosure:
    """Explicit basis and data-completeness counts carried by every report."""

    adjustment_basis_counts: Mapping[str, int]
    survivorship_attrition_count: int
    ticker_identity_missing_count: int
    sector_missing_count: int
    missing_return_count: int
    missing_intermediate_bar_count: int


@dataclass(frozen=True, slots=True)
class AttritionSummary:
    """Reason-level missing/delisted outcome accounting for a report."""

    total_events: int
    attrited_events: int
    observed_events: int
    reason_counts: Mapping[str, int]
    missing_or_delisted_events: int

    @property
    def attrition_rate(self) -> float:
        return self.attrited_events / self.total_events if self.total_events else 0.0


@dataclass(frozen=True, slots=True)
class RegimeSummary:
    """A tabular slice, grouped by period, sector, or signal type."""

    dimension: str
    value: str
    event_count: int
    metrics: Mapping[int, MetricSummary]


@dataclass(frozen=True, slots=True)
class SensitivityScenario:
    """Read-only score sensitivity result; production weights remain frozen."""

    name: str
    event_count: int
    selected_count: int
    median_score: float | None
    score_min: float | None
    score_max: float | None
    score_version: str
    weights_changed: bool
    notes: str


@dataclass(frozen=True, slots=True)
class BacktestReport:
    """Answer-first report assembled from one period of a backtest."""

    period: BacktestPeriod
    benchmark_table: tuple[BenchmarkComparison, ...]
    regime_table: tuple[RegimeSummary, ...]
    attrition: AttritionSummary
    caveats: tuple[BacktestCaveat, ...]
    gate: GateAssessment | None
    sensitivity: tuple[SensitivityScenario, ...]
    data_quality: DataQualityDisclosure

    @property
    def benchmarks(self) -> tuple[BenchmarkComparison, ...]:
        return self.benchmark_table


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ReportingError("cannot calculate a quantile for an empty sample")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _finite_values(values: Iterable[float | None]) -> tuple[float, ...]:
    result: list[float] = []
    for value in values:
        if value is not None and math.isfinite(float(value)):
            result.append(float(value))
    return tuple(result)


def bootstrap_median_ci(
    values: Iterable[float | None],
    *,
    confidence: float = 0.95,
    iterations: int = 2_000,
    seed: int = 0,
) -> BootstrapInterval:
    """Return a deterministic percentile bootstrap CI for a sample median.

    A local ``Random`` instance makes output independent of process-global
    random state.  Missing values are omitted, never imputed as zero.
    """

    sample = _finite_values(values)
    if not 0.0 < confidence < 1.0:
        raise ReportingError("confidence must be between 0 and 1")
    if iterations <= 0:
        raise ReportingError("iterations must be positive")
    if not sample:
        return BootstrapInterval(None, None, None, confidence, iterations, seed)
    estimate = float(median(sample))
    if len(sample) == 1:
        return BootstrapInterval(estimate, estimate, estimate, confidence, iterations, seed)
    rng = random.Random(seed)
    medians = [float(median(rng.choices(sample, k=len(sample)))) for _ in range(iterations)]
    alpha = (1.0 - confidence) / 2.0
    return BootstrapInterval(
        estimate,
        _quantile(medians, alpha),
        _quantile(medians, 1.0 - alpha),
        confidence,
        iterations,
        seed,
    )


def bootstrap_median_difference_ci(
    first: Iterable[float | None],
    second: Iterable[float | None],
    *,
    confidence: float = 0.95,
    iterations: int = 2_000,
    seed: int = 0,
) -> BootstrapInterval:
    """Bootstrap ``median(first) - median(second)`` independently and deterministically."""

    first_values = _finite_values(first)
    second_values = _finite_values(second)
    if not first_values or not second_values:
        return BootstrapInterval(None, None, None, confidence, iterations, seed)
    if not 0.0 < confidence < 1.0:
        raise ReportingError("confidence must be between 0 and 1")
    if iterations <= 0:
        raise ReportingError("iterations must be positive")
    estimate = float(median(first_values) - median(second_values))
    rng = random.Random(seed)
    differences = [
        float(median(rng.choices(first_values, k=len(first_values))))
        - float(median(rng.choices(second_values, k=len(second_values))))
        for _ in range(iterations)
    ]
    alpha = (1.0 - confidence) / 2.0
    return BootstrapInterval(
        estimate,
        _quantile(differences, alpha),
        _quantile(differences, 1.0 - alpha),
        confidence,
        iterations,
        seed,
    )


def _outcome(event: BacktestEvent, horizon: int) -> ForwardReturn | None:
    return event.forward_returns.get(horizon)


def _event_reasons(event: BacktestEvent) -> set[str]:
    reasons = set(event.attrition_reasons)
    for result in event.forward_returns.values():
        if result.attrition_reason is not None:
            reasons.add(result.attrition_reason)
        reasons.update(result.quality_reasons)
    return reasons


def _eligible_outcome(event: BacktestEvent, horizon: int) -> float | None:
    """Return a fully observed excess outcome, otherwise ``None``.

    A missing intermediate stock bar invalidates the MAE path and therefore is
    not eligible for the formal 6M gate even if its endpoint happens to exist.
    """

    result = _outcome(event, horizon)
    if (
        result is None
        or result.spy_excess_return is None
        or result.attrition_reason is not None
        or result.quality_reasons
    ):
        return None
    return float(result.spy_excess_return)


def summarize_events(events: Iterable[BacktestEvent], horizon: int) -> MetricSummary:
    """Compute 3M/6M/12M return, win-rate, downside-tail, and MAE metrics."""

    rows = tuple(events)
    excess: list[float] = []
    stock: list[float] = []
    maes: list[float] = []
    attrited = 0
    for event in rows:
        result = _outcome(event, horizon)
        excess_return = _eligible_outcome(event, horizon)
        if result is None or excess_return is None:
            attrited += 1
            continue
        excess.append(excess_return)
        if result.stock_return is not None:
            stock.append(float(result.stock_return))
        if result.max_adverse_excursion is not None:
            maes.append(float(result.max_adverse_excursion))
    return MetricSummary(
        horizon_sessions=horizon,
        event_count=len(rows),
        observed_count=len(excess),
        attrited_count=attrited,
        median_stock_return=float(median(stock)) if stock else None,
        median_spy_excess_return=float(median(excess)) if excess else None,
        mean_spy_excess_return=sum(excess) / len(excess) if excess else None,
        win_rate=sum(value > 0 for value in excess) / len(excess) if excess else None,
        downside_tail=_quantile(excess, 0.10) if excess else None,
        median_mae=float(median(maes)) if maes else None,
    )


def summarize_group(
    group: EventGroup, *, horizons: Sequence[int] = _REPORT_HORIZONS
) -> BenchmarkComparison:
    """Summarize one event group into a benchmark-comparison row."""

    metrics = {int(horizon): summarize_events(group.events, int(horizon)) for horizon in horizons}
    attrited = sum(1 for event in group.events if event.is_attrited)
    return BenchmarkComparison(
        name=group.name,
        display_name=_display_name(group.name),
        event_count=len(group.events),
        attrited_count=attrited,
        metrics=metrics,
        events=group.events,
    )


def _display_name(name: str) -> str:
    return {
        "simple_ps": "Simple P/S",
        "unique_buyer_ratio": "Unique Buyer Ratio",
        "largest_buys": "Largest Buys",
        "cluster_buys": "Cluster Buys",
        "full_engine": "Full Engine",
    }.get(name, name.replace("_", " ").title())


def _canonical_benchmark_name(name: str) -> str:
    normalized = name.strip().lower().replace("-", "_")
    return _BENCHMARK_ALIASES.get(normalized, normalized)


def _period_results(
    source: BacktestResult | OOSReport | PeriodResults, period: BacktestPeriod
) -> PeriodResults:
    if isinstance(source, PeriodResults):
        return source
    if isinstance(source, OOSReport):
        return source.results
    if period is BacktestPeriod.DEVELOPMENT:
        return source.development
    if period is BacktestPeriod.VALIDATION:
        return source.validation
    # This is the only permitted read of sealed OOS in this module.
    return source.sealed_oos.final_report().results


def _groups_for(
    results: PeriodResults,
    benchmark_groups: Mapping[str, EventGroup | Iterable[BacktestEvent]] | None,
) -> dict[str, EventGroup]:
    groups: dict[str, EventGroup] = {}
    if benchmark_groups:
        for raw_name, raw_group in benchmark_groups.items():
            name = _canonical_benchmark_name(raw_name)
            events = raw_group.events if isinstance(raw_group, EventGroup) else tuple(raw_group)
            groups[name] = EventGroup(name, results.period, tuple(events))
    # The engine always supplies these canonical groups.  Aliased simple
    # benchmarks default to the all-event comparator when no dedicated group
    # was provided, preserving a complete, honest table.
    groups.setdefault(
        "full_engine", EventGroup("full_engine", results.period, results.top_decile.events)
    )
    for name in _SIMPLE_BENCHMARKS:
        groups.setdefault(name, EventGroup(name, results.period, results.simple_benchmark.events))
    return groups


def compare_benchmarks(
    source: BacktestResult | OOSReport | PeriodResults,
    *,
    period: BacktestPeriod = BacktestPeriod.OOS,
    benchmark_groups: Mapping[str, EventGroup | Iterable[BacktestEvent]] | None = None,
    horizons: Sequence[int] = _REPORT_HORIZONS,
) -> tuple[BenchmarkComparison, ...]:
    """Build the simple P/S, buyer-ratio, largest-buy, cluster, and full-engine table."""

    results = _period_results(source, period)
    groups = _groups_for(results, benchmark_groups)
    ordered = [*(_SIMPLE_BENCHMARKS), "full_engine"]
    ordered.extend(name for name in sorted(groups) if name not in ordered)
    return tuple(summarize_group(groups[name], horizons=horizons) for name in ordered)


def summarize_attrition(events: Iterable[BacktestEvent]) -> AttritionSummary:
    """Account for missing and delisted outcomes without zero imputation."""

    rows = tuple(events)
    reasons: Counter[str] = Counter()
    attrited = 0
    missing_delisted_events = 0
    for event in rows:
        event_reasons = _event_reasons(event)
        if event_reasons:
            attrited += 1
            reasons.update(event_reasons)
            if any(reason.startswith(("MISSING_", "DELISTED_")) for reason in event_reasons):
                missing_delisted_events += 1
    return AttritionSummary(
        total_events=len(rows),
        attrited_events=attrited,
        observed_events=len(rows) - attrited,
        reason_counts=dict(sorted(reasons.items())),
        missing_or_delisted_events=missing_delisted_events,
    )


def evaluate_formal_gate(
    comparisons: Sequence[BenchmarkComparison],
    *,
    sealed_oos_events: int,
    validation_evidence: ValidationEvidence | Mapping[str, Any] | None = None,
    minimum_events: int = 200,
    confidence: float = 0.95,
    iterations: int = 2_000,
    seed: int = 0,
) -> GateAssessment:
    """Apply the frozen formal gate to the full engine versus simple benchmarks.

    PASS requires a positive lower CI, 200 observed/eligible 6M outcomes in
    both compared selections, and all mandatory validation evidence.  The
    retained OOS-event count is audit context only; attrited outcomes never
    satisfy the formal sample-size threshold.
    """

    evidence_status, evidence_reason = _validation_evidence_status(validation_evidence)
    by_name = {_canonical_benchmark_name(row.name): row for row in comparisons}
    full = by_name.get("full_engine")
    simple = [by_name[name] for name in _SIMPLE_BENCHMARKS if name in by_name]
    if full is None or not simple:
        empty = BootstrapInterval(None, None, None, confidence, iterations, seed)
        return GateAssessment(
            "INCONCLUSIVE",
            None,
            empty,
            None,
            sealed_oos_events,
            minimum_events,
            "full-engine and simple benchmark results are required",
            0,
        )
    try:
        full_metric = full.metric(126)
        candidates = [row for row in simple if row.metric(126).median_spy_excess_return is not None]
    except ReportingError:
        empty = BootstrapInterval(None, None, None, confidence, iterations, seed)
        return GateAssessment(
            "INCONCLUSIVE",
            None,
            empty,
            None,
            sealed_oos_events,
            minimum_events,
            "6M outcomes are required for the formal gate",
            0,
        )
    if full_metric.median_spy_excess_return is None or not candidates:
        empty = BootstrapInterval(None, None, None, confidence, iterations, seed)
        return GateAssessment(
            "INCONCLUSIVE",
            None,
            empty,
            None,
            sealed_oos_events,
            minimum_events,
            "insufficient observed 6M outcomes for a comparison",
            0,
        )
    best = max(
        candidates,
        key=lambda row: float(row.metric(126).median_spy_excess_return or -math.inf),
    )
    full_values = [
        _eligible_outcome(event, 126) for event in _events_for_comparison(full, comparisons)
    ]
    best_values = [
        _eligible_outcome(event, 126) for event in _events_for_comparison(best, comparisons)
    ]
    full_observed = _finite_values(full_values)
    best_observed = _finite_values(best_values)
    eligible_outcomes = min(len(full_observed), len(best_observed))
    interval = bootstrap_median_difference_ci(
        full_observed, best_observed, confidence=confidence, iterations=iterations, seed=seed
    )
    point = interval.estimate
    if evidence_status == "FAIL":
        status = "FAIL"
        reason = evidence_reason
    elif point is None:
        status = "INCONCLUSIVE"
        reason = "insufficient observed eligible 6M outcomes for a comparison"
    elif point <= 0:
        status = "FAIL"
        reason = "full engine does not beat the best simple benchmark at 6M"
    elif evidence_status == "INCONCLUSIVE":
        status = "INCONCLUSIVE"
        reason = evidence_reason
    elif interval.lower is None or interval.lower <= 0 or eligible_outcomes < minimum_events:
        status = "INCONCLUSIVE"
        reason = "positive 6M point estimate is not formally validated: " + (
            "confidence interval includes zero"
            if interval.lower is None or interval.lower <= 0
            else f"fewer than {minimum_events} observed eligible 6M OOS outcomes"
        )
    else:
        status = "PASS"
        reason = "full engine beats the best simple benchmark at 6M with a positive lower CI"
    return GateAssessment(
        status,
        point,
        interval,
        best.name,
        sealed_oos_events,
        minimum_events,
        reason,
        eligible_outcomes,
    )


def _validation_evidence_status(
    raw: ValidationEvidence | Mapping[str, Any] | None,
) -> tuple[str, str]:
    """Classify validation evidence without allowing unknown values to pass."""

    if raw is None:
        return "INCONCLUSIVE", "required validation evidence is missing"
    evidence = _coerce_validation_evidence(raw)
    rates = {
        "parse success": (evidence.parse_success_rate, 0.995),
        "market coverage": (evidence.market_coverage, 0.90),
        "core branch coverage": (evidence.core_branch_coverage, 0.85),
    }
    booleans = {
        "canonical input": evidence.canonical_valid,
        "schema": evidence.schema_valid,
        "hash": evidence.hash_valid,
        "temporal": evidence.temporal_valid,
        "benchmark freshness": evidence.benchmark_fresh,
    }
    missing = [name for name, (value, _threshold) in rates.items() if value is None]
    missing.extend(name for name, value in booleans.items() if value is None)
    if missing:
        return "INCONCLUSIVE", "required validation evidence is missing: " + ", ".join(missing)
    failed: list[str] = []
    for name, (value, threshold) in rates.items():
        assert value is not None
        if not math.isfinite(float(value)) or float(value) < threshold:
            failed.append(f"{name} below {threshold:.3f}")
    failed.extend(name for name, value in booleans.items() if value is False)
    if failed:
        return "FAIL", "validation evidence failed: " + ", ".join(failed)
    return "PASS", "validation evidence passed"


def _coerce_validation_evidence(
    raw: ValidationEvidence | Mapping[str, Any],
) -> ValidationEvidence:
    if isinstance(raw, ValidationEvidence):
        return raw
    return ValidationEvidence(
        parse_success_rate=_optional_float(raw.get("parse_success_rate", raw.get("parse_success"))),
        market_coverage=_optional_float(
            raw.get("market_coverage", raw.get("market_coverage_rate"))
        ),
        core_branch_coverage=_optional_float(
            raw.get("core_branch_coverage", raw.get("core_coverage"))
        ),
        canonical_valid=_optional_bool(raw.get("canonical_valid")),
        schema_valid=_optional_bool(raw.get("schema_valid")),
        hash_valid=_optional_bool(raw.get("hash_valid")),
        temporal_valid=_optional_bool(raw.get("temporal_valid")),
        benchmark_fresh=_optional_bool(raw.get("benchmark_fresh")),
    )


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _optional_bool(value: Any) -> bool | None:
    return None if value is None else bool(value)


def _events_for_comparison(
    comparison: BenchmarkComparison, comparisons: Sequence[BenchmarkComparison]
) -> tuple[BacktestEvent, ...]:
    return comparison.events


def _regime_table(
    events: Iterable[BacktestEvent], horizons: Sequence[int]
) -> tuple[RegimeSummary, ...]:
    rows = tuple(events)
    grouped: dict[tuple[str, str], list[BacktestEvent]] = defaultdict(list)
    for event in rows:
        grouped[("period", event.period.value)].append(event)
        grouped[("sector", event.signal.sector or "UNKNOWN")].append(event)
        grouped[("signal_type", event.signal.signal_type)].append(event)
    return tuple(
        RegimeSummary(
            dimension,
            value,
            len(group),
            {int(h): summarize_events(group, int(h)) for h in horizons},
        )
        for (dimension, value), group in sorted(grouped.items())
    )


def _data_quality_disclosure(events: Iterable[BacktestEvent]) -> DataQualityDisclosure:
    rows = tuple(events)
    adjustment_basis: Counter[str] = Counter(event.adjustment_basis or "UNKNOWN" for event in rows)
    reasons = Counter(reason for event in rows for reason in _event_reasons(event))
    return DataQualityDisclosure(
        adjustment_basis_counts=dict(sorted(adjustment_basis.items())),
        survivorship_attrition_count=sum(
            1
            for event in rows
            if any(reason.startswith("DELISTED_") for reason in _event_reasons(event))
        ),
        ticker_identity_missing_count=sum(1 for event in rows if event.signal.issuer_cik is None),
        sector_missing_count=sum(1 for event in rows if not event.signal.sector),
        missing_return_count=sum(
            count
            for reason, count in reasons.items()
            if reason.startswith(("MISSING_RETURN_", "DELISTED_RETURN_"))
        ),
        missing_intermediate_bar_count=sum(
            count
            for reason, count in reasons.items()
            if reason.startswith("MISSING_INTERMEDIATE_BAR_")
        ),
    )


def _quality_caveats(disclosure: DataQualityDisclosure) -> tuple[BacktestCaveat, ...]:
    basis = (
        ", ".join(f"{name}={count}" for name, count in disclosure.adjustment_basis_counts.items())
        or "none=0"
    )
    return (
        BacktestCaveat("ADJUSTMENT_BASIS_COUNTS", f"Adjustment basis counts: {basis}."),
        BacktestCaveat(
            "SURVIVORSHIP_COUNT",
            f"Delisted/survivorship attrition count: {disclosure.survivorship_attrition_count}.",
        ),
        BacktestCaveat(
            "TICKER_IDENTITY_COUNT",
            "Events without supplied issuer CIK identity: "
            f"{disclosure.ticker_identity_missing_count}.",
        ),
        BacktestCaveat(
            "SECTOR_MISSING_COUNT",
            f"Events without point-in-time sector metadata: {disclosure.sector_missing_count}.",
        ),
        BacktestCaveat(
            "MISSING_RETURN_COUNT",
            f"Missing or delisted forward-return outcomes: {disclosure.missing_return_count}.",
        ),
    )


def score_sensitivity_report(
    scenarios: Mapping[str, Sequence[BacktestSignalLike] | Mapping[str, Any] | float],
    *,
    score_version: str = "scoring.v1",
) -> tuple[SensitivityScenario, ...]:
    """Evaluate supplied score scenarios while preserving scoring.v1 weights.

    Scenarios may provide ``scores``/``signals``/``events`` and an optional
    ``threshold``.  This is a diagnostic ranking report, not a re-weighting
    API; every row explicitly reports ``weights_changed=False``.
    """

    output: list[SensitivityScenario] = []
    for name, raw in scenarios.items():
        scores: list[float] = []
        threshold: float | None = None
        if isinstance(raw, Mapping):
            threshold_raw = raw.get("threshold")
            threshold = float(threshold_raw) if threshold_raw is not None else None
            values = raw.get("scores", raw.get("signals", raw.get("events", ())))
        else:
            values = raw if not isinstance(raw, (int, float)) else (raw,)
        if isinstance(values, (int, float)):
            values = (values,)
        for value in values or ():
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                scores.append(float(value))
            elif hasattr(value, "signal"):
                score = value.signal.score
                if score is not None and math.isfinite(float(score)):
                    scores.append(float(score))
            elif hasattr(value, "score"):
                score = value.score
                if math.isfinite(float(score)):
                    scores.append(float(score))
        selected = (
            sum(score >= threshold for score in scores) if threshold is not None else len(scores)
        )
        output.append(
            SensitivityScenario(
                str(name),
                len(scores),
                selected,
                float(median(scores)) if scores else None,
                min(scores) if scores else None,
                max(scores) if scores else None,
                score_version,
                False,
                "frozen scoring.v1 weights; ranking/threshold sensitivity only",
            )
        )
    return tuple(output)


def build_backtest_report(
    source: BacktestResult | OOSReport | PeriodResults,
    *,
    period: BacktestPeriod = BacktestPeriod.OOS,
    benchmark_groups: Mapping[str, EventGroup | Iterable[BacktestEvent]] | None = None,
    sensitivity_scenarios: Mapping[str, Sequence[BacktestSignalLike] | Mapping[str, Any] | float]
    | None = None,
    validation_evidence: ValidationEvidence | Mapping[str, Any] | None = None,
    bootstrap_iterations: int = 2_000,
    bootstrap_seed: int = 0,
) -> BacktestReport:
    """Build a complete benchmark, regime, attrition, caveat, and gate report."""

    results = _period_results(source, period)
    # Materialize custom iterables once: report assembly calls the table and
    # gate paths independently, and a generator must not disappear on the
    # second pass.
    materialized_groups = None
    if benchmark_groups is not None:
        materialized_groups = {
            name: (group.events if isinstance(group, EventGroup) else tuple(group))
            for name, group in benchmark_groups.items()
        }
    comparisons = list(
        compare_benchmarks(source, period=period, benchmark_groups=materialized_groups)
    )
    sealed_count = len(results.simple_benchmark.events)
    gate = (
        evaluate_formal_gate(
            comparisons,
            sealed_oos_events=sealed_count,
            validation_evidence=validation_evidence,
            iterations=bootstrap_iterations,
            seed=bootstrap_seed,
        )
        if period is BacktestPeriod.OOS
        else None
    )
    attrition = summarize_attrition(results.simple_benchmark.events)
    data_quality = _data_quality_disclosure(results.simple_benchmark.events)
    if isinstance(source, OOSReport):
        caveats = list(source.caveats)
    elif isinstance(source, BacktestResult):
        caveats = list(
            source.sealed_oos.final_report().caveats
            if period is BacktestPeriod.OOS
            else source.caveats
        )
    else:
        caveats = []
    caveats.extend(
        (
            BacktestCaveat(
                "SURVIVORSHIP_BIAS",
                "A bar universe that omits delisted issuers can overstate historical returns.",
            ),
            BacktestCaveat(
                "MISSING_DELISTED_ATTRITION",
                "Missing or delisted outcomes are excluded from return metrics, "
                "never imputed as zero.",
            ),
        )
    )
    caveats.extend(_quality_caveats(data_quality))
    deduped = tuple({c.code: c for c in caveats}.values())
    return BacktestReport(
        period,
        tuple(comparisons),
        _regime_table(results.simple_benchmark.events, _REPORT_HORIZONS),
        attrition,
        deduped,
        gate,
        score_sensitivity_report(sensitivity_scenarios or {}),
        data_quality,
    )


# Friendly aliases used by downstream report/export callers.
make_backtest_report = build_backtest_report
formal_gate = evaluate_formal_gate
bootstrap_ci = bootstrap_median_ci
sensitivity_report = score_sensitivity_report


__all__ = [
    "AttritionSummary",
    "BacktestReport",
    "BenchmarkComparison",
    "BootstrapInterval",
    "DataQualityDisclosure",
    "GateAssessment",
    "MetricSummary",
    "RegimeSummary",
    "ReportingError",
    "SensitivityScenario",
    "ValidationEvidence",
    "BacktestSignalLike",
    "bootstrap_ci",
    "bootstrap_median_ci",
    "bootstrap_median_difference_ci",
    "build_backtest_report",
    "compare_benchmarks",
    "evaluate_formal_gate",
    "formal_gate",
    "make_backtest_report",
    "score_sensitivity_report",
    "sensitivity_report",
    "summarize_attrition",
    "summarize_events",
    "summarize_group",
]
