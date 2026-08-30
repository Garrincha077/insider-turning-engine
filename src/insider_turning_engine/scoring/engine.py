"""Rules-based score v1 implementation.

The engine consumes already point-in-time feature values.  It refuses missing
or non-finite required components so a broken upstream feature cannot quietly
become a plausible score.  The only nullable v1 input is ``fundamental`` in the
total score; it is excluded and the remaining weights are renormalized.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "config" / "scoring.v1.yaml"


class ScoreValidationError(ValueError):
    """Raised when score inputs violate the frozen v1 contract."""


@dataclass(frozen=True)
class ScoreResult:
    name: str
    score: float
    components: Mapping[str, float | None]
    confidence: float
    score_version: str
    reason_codes: tuple[str, ...]
    score_config_hash: str = ""
    score_lineage: str = ""


def _number(name: str, value: Any) -> float:
    if isinstance(value, bool) or value is None:
        raise ScoreValidationError(f"{name} is required")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ScoreValidationError(f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise ScoreValidationError(f"{name} must be finite")
    if number < 0 or number > 100:
        raise ScoreValidationError(f"{name} must be within 0..100")
    return number


class ScoreEngine:
    """Load frozen YAML weights and produce transparent component scores."""

    def __init__(self, config_path: str | Path = DEFAULT_CONFIG) -> None:
        self.config_path = Path(config_path)
        config_bytes = self.config_path.read_bytes()
        with self.config_path.open("r", encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
        if not isinstance(raw, Mapping) or not isinstance(raw.get("models"), Mapping):
            raise ScoreValidationError("scoring config must contain models")
        self._config = raw
        self.score_version = str(raw.get("version", "unknown"))
        if self.score_version != "scoring.v1":
            raise ScoreValidationError("scoring config version must be scoring.v1")
        self.score_config_hash = "sha256:" + hashlib.sha256(config_bytes).hexdigest()
        try:
            lineage_path = self.config_path.resolve().relative_to(
                Path(__file__).resolve().parents[3]
            )
        except ValueError:
            lineage_path = Path(self.config_path.name)
        self.score_lineage = f"{lineage_path.as_posix()}@{self.score_config_hash}"
        self._validate_weights()

    def _validate_weights(self) -> None:
        models = self._config["models"]
        for name, model in models.items():
            if not isinstance(model, Mapping) or not isinstance(model.get("weights"), Mapping):
                raise ScoreValidationError(f"model {name} is missing weights")
            total = sum(float(value) for value in model["weights"].values())
            if not math.isclose(total, 1.0, abs_tol=1e-9):
                raise ScoreValidationError(f"model {name} weights sum to {total}")

    def score(self, name: str, components: Mapping[str, float | None]) -> ScoreResult:
        models = self._config["models"]
        if name not in models:
            raise ScoreValidationError(f"unknown score model: {name}")
        weights: Mapping[str, Any] = models[name]["weights"]
        unknown = set(components).difference(weights)
        if unknown:
            raise ScoreValidationError(f"unknown {name} components: {sorted(unknown)}")

        values: dict[str, float | None] = {}
        active_weight = 0.0
        weighted = 0.0
        for component, raw_weight in weights.items():
            value = components.get(component)
            if value is None and name == "total" and component == "fundamental":
                values[component] = None
                continue
            numeric = _number(component, value)
            weight = float(raw_weight)
            values[component] = numeric
            weighted += numeric * weight
            active_weight += weight
        if active_weight <= 0:
            raise ScoreValidationError(f"{name} has no active components")
        result = weighted / active_weight
        ranked = sorted(
            ((key, value) for key, value in values.items() if value is not None),
            key=lambda item: (-item[1], item[0]),
        )
        reasons = tuple(
            f"{key.upper()}_{'STRONG' if value >= 65 else 'WEAK'}" for key, value in ranked
        )
        return ScoreResult(
            name=name,
            score=round(result, 6),
            components=values,
            confidence=round(len(ranked) / len(weights), 6),
            score_version=self.score_version,
            reason_codes=reasons,
            score_config_hash=self.score_config_hash,
            score_lineage=self.score_lineage,
        )

    def market_pulse(self, **components: float) -> ScoreResult:
        return self.score("market_pulse", components)

    def company_insider(self, **components: float) -> ScoreResult:
        return self.score("company_insider", components)

    def divergence(self, **components: float) -> ScoreResult:
        return self.score("divergence", components)

    def turn(self, **components: float) -> ScoreResult:
        return self.score("turn", components)

    def total(self, **components: float | None) -> ScoreResult:
        components.setdefault("fundamental", None)
        return self.score("total", components)


__all__ = ["DEFAULT_CONFIG", "ScoreEngine", "ScoreResult", "ScoreValidationError"]
