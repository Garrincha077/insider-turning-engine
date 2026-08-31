from __future__ import annotations

import json
from pathlib import Path

import pytest

from insider_turning_engine.backtest.models import EvaluationStage
from insider_turning_engine.backtest.reporting import (
    ReportingError,
    build_backtest_report,
    evaluate_formal_gate,
)
from insider_turning_engine.domain.scoring_lock import (
    DEFAULT_LOCK,
    ScoringLockError,
    ScoringLockStatus,
    load_scoring_lock,
)


def _lock_copy(tmp_path: Path) -> tuple[dict[str, object], Path]:
    raw = json.loads(DEFAULT_LOCK.read_text(encoding="utf-8"))
    destination = tmp_path / "scoring.v1.lock.json"
    return raw, destination


def _write(destination: Path, raw: dict[str, object]) -> Path:
    destination.write_text(json.dumps(raw), encoding="utf-8")
    return destination


def test_checked_in_lock_is_candidate_complete_and_exact() -> None:
    lock = load_scoring_lock()

    assert lock.status is ScoringLockStatus.CANDIDATE
    assert lock.component_contract_complete is True
    assert lock.methodology_complete is False
    assert lock.frozen_at_iso is None
    assert tuple(item.path for item in lock.methodology_files) == tuple(
        sorted(item.path for item in lock.methodology_files)
    )


def test_candidate_lock_has_no_frozen_at_and_never_claims_completion(tmp_path: Path) -> None:
    raw, destination = _lock_copy(tmp_path)
    raw["status"] = "CANDIDATE"
    raw.pop("frozenAt", None)

    lock = load_scoring_lock(lock_path=_write(destination, raw))

    assert lock.status is ScoringLockStatus.CANDIDATE
    assert lock.frozen_at is None
    assert lock.methodology_complete is False


@pytest.mark.parametrize(
    ("status", "frozen_at", "message"),
    [
        ("FROZEN", None, "requires frozenAt"),
        ("CANDIDATE", "2026-08-30T22:35:09Z", "must not include frozenAt"),
        ("FROZEN", "2026-08-30T22:35:09+00:00", "canonical UTC timestamp"),
    ],
)
def test_frozen_at_contract_is_status_bound(
    tmp_path: Path, status: str, frozen_at: str | None, message: str
) -> None:
    raw, destination = _lock_copy(tmp_path)
    raw["status"] = status
    if frozen_at is None:
        raw.pop("frozenAt", None)
    else:
        raw["frozenAt"] = frozen_at

    with pytest.raises(ScoringLockError, match=message):
        load_scoring_lock(lock_path=_write(destination, raw))


def test_methodology_source_hash_and_order_are_exact(tmp_path: Path) -> None:
    raw, destination = _lock_copy(tmp_path)
    files = raw["methodologyFiles"]
    assert isinstance(files, list)
    first = files[0]
    assert isinstance(first, dict)
    first["sha256"] = "sha256:" + "0" * 64

    with pytest.raises(ScoringLockError, match="hash does not match source bytes"):
        load_scoring_lock(lock_path=_write(destination, raw))

    raw, destination = _lock_copy(tmp_path)
    files = raw["methodologyFiles"]
    assert isinstance(files, list)
    raw["methodologyFiles"] = list(reversed(files))
    with pytest.raises(ScoringLockError, match="path-sorted"):
        load_scoring_lock(lock_path=_write(destination, raw))


def test_sealed_gate_rejects_candidate_lock_without_oos_inputs(tmp_path: Path) -> None:
    raw, destination = _lock_copy(tmp_path)
    raw["status"] = "CANDIDATE"
    raw.pop("frozenAt", None)

    gate = evaluate_formal_gate(
        (),
        sealed_oos_events=0,
        validation_evidence={"scoring_methodology_complete": True},
        evaluation_stage=EvaluationStage.SEALED_OOS,
        scoring_lock_path=_write(destination, raw),
    )

    assert gate.status == "FAIL"
    assert "FROZEN, complete methodology lock" in gate.reason


def test_sealed_gate_rejects_an_inexact_lock_without_oos_inputs(tmp_path: Path) -> None:
    raw, destination = _lock_copy(tmp_path)
    files = raw["methodologyFiles"]
    assert isinstance(files, list)
    first = files[0]
    assert isinstance(first, dict)
    first["sha256"] = "sha256:" + "0" * 64

    gate = evaluate_formal_gate(
        (),
        sealed_oos_events=0,
        evaluation_stage=EvaluationStage.SEALED_OOS,
        scoring_lock_path=_write(destination, raw),
    )

    assert gate.status == "FAIL"
    assert "exact frozen methodology lock" in gate.reason


def test_oos_report_fails_before_reading_a_candidate_lock_source(tmp_path: Path) -> None:
    raw, destination = _lock_copy(tmp_path)
    raw["status"] = "CANDIDATE"
    raw.pop("frozenAt", None)

    with pytest.raises(ReportingError, match="FROZEN, complete methodology lock"):
        build_backtest_report(object(), scoring_lock_path=_write(destination, raw))


def test_dev_validation_does_not_need_to_open_or_validate_a_sealed_lock() -> None:
    gate = evaluate_formal_gate(
        (),
        sealed_oos_events=0,
        evaluation_stage=EvaluationStage.DEV_VALIDATION,
        scoring_lock_path="not-used-in-dev-validation.json",
    )

    assert gate.status == "INCONCLUSIVE"
    assert gate.reason == "full-engine and simple benchmark results are required"
