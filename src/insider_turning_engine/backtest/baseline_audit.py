"""Reproduce a pinned development baseline with explicit costs and attrition.

This is not a new filter, model tournament, calendar portfolio, or OOS gate.
Missing paths, liquidity and PIT feature joins remain explicit research blockers.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import fmean, median
from typing import Any

DEFAULT_CONTRACT = Path("research/predictive-baseline-audit.v1.json")


def text_sha256(payload: bytes) -> str:
    """Normalize only tracked text line endings, not downloaded source bytes."""
    return hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest()


def net_return(gross_return: float, cost_bps_per_leg: float) -> float:
    """Entry premium and exit haircut, including proportional cost on profits."""
    if not math.isfinite(gross_return) or gross_return < -1:
        raise ValueError("Return must be finite and cannot lose more than invested capital")
    if not math.isfinite(cost_bps_per_leg) or not 0 <= cost_bps_per_leg < 10_000:
        raise ValueError("Cost must be finite and between 0 and 10000 bps per leg")
    cost = cost_bps_per_leg / 10_000
    return (1 + gross_return) * (1 - cost) / (1 + cost) - 1


def _summary(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "observed": len(values),
        "mean": fmean(values) if values else None,
        "median": median(values) if values else None,
        "winRate": sum(value > 0 for value in values) / len(values) if values else None,
        # Discrete lower decile; avoid interpolation pretending to add observations.
        "lowerDecile": ordered[math.floor((len(ordered) - 1) * .1)] if values else None,
    }


def _number(row: dict[str, str], field: str) -> float:
    try:
        value = float(row[field])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Missing numeric outcome: {field}") from exc
    if not math.isfinite(value):
        raise ValueError(f"Non-finite outcome: {field}")
    return value


def audit_baseline(
    csv_path: Path, summary_path: Path, *, contract_path: Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    """Verify exact frozen inputs before reading any numeric research outcome."""
    contract_bytes = contract_path.read_bytes()
    contract = json.loads(contract_bytes)
    if (
        contract["studyId"] != "predictive-baseline-audit.v1"
        or contract["formationStart"] != "2016-01-01"
        or contract["formationEnd"] != "2020-12-31"
        or contract["outcomeEnd"] != "2022-12-31"
        or contract["horizons"] != [21, 63, 126, 252]
        or contract["primaryHorizon"] != 126
        or contract["costBpsPerLeg"] != [0, 10, 25, 50]
    ):
        raise ValueError("This audit cannot change its population, dates, horizons or cost grid")
    payloads = (csv_path.read_bytes(), summary_path.read_bytes())
    hashes = tuple(hashlib.sha256(payload).hexdigest() for payload in payloads)
    if hashes != (contract["sourceCsvSha256"], contract["sourceSummarySha256"]):
        raise ValueError("Frozen development input checksum mismatch")
    source = json.loads(payloads[1])
    if (
        source.get("researchOnly") is not True
        or source.get("oosOpened") is not False
        or source.get("productionScoringChanged") is not False
        or source.get("outcomeMarketBoundary") != "2016-2022 only"
    ):
        raise ValueError("Source is not the bounded research-only development cohort")

    rows: dict[int, list[dict[str, str]]] = defaultdict(list)
    events: dict[str, tuple[str, str, str, str]] = {}
    seen: set[tuple[str, int]] = set()
    for row in csv.DictReader(io.StringIO(payloads[0].decode("utf-8"))):
        formation = date.fromisoformat(row["evaluationSession"])
        entry = date.fromisoformat(row["entrySession"])
        target = date.fromisoformat(row["targetExitSession"])
        if not date(2016, 1, 1) <= formation <= date(2020, 12, 31):
            raise ValueError("Non-development formation or sealed evaluation attempted")
        if not formation < entry < target <= date(2022, 12, 31):
            raise ValueError("Invalid execution order or outcome beyond development boundary")
        if row["effectiveDate"] and date.fromisoformat(row["effectiveDate"]) > date(2022, 12, 31):
            raise ValueError("Corporate action exceeds the permitted outcome boundary")
        horizon = int(row["horizon"])
        key = (row["eventNumber"], horizon)
        if horizon not in contract["horizons"] or key in seen:
            raise ValueError("Duplicate or unsupported event/horizon")
        seen.add(key)
        identity = (row["issuerCik"], row["ticker"], row["evaluationSession"], row["entrySession"])
        if not identity[0] or not key[0] or events.setdefault(key[0], identity) != identity:
            raise ValueError("Missing or inconsistent economic-event identity")
        _number(row, "entryOpen")
        if float(row["entryOpen"]) <= 0:
            raise ValueError("Invalid entry price")
        if row["valuationStatus"] == "VALUED":
            gross, spy = _number(row, "correctedRaw"), _number(row, "spyReturn")
            net_return(gross, 0)
            net_return(spy, 0)
            if row["missingReason"] or not math.isclose(
                gross - spy, _number(row, "correctedExcess"), abs_tol=1e-12, rel_tol=1e-10,
            ):
                raise ValueError("Valued row has inconsistent excess or missing outcome")
        elif row["valuationStatus"] in {
            "MISSING_EXACT_TERMINAL_HOLDER_BAR", "MISSING_DISCONTINUOUS_NO_COMPLETE_VALUATION",
            "MISSING_EXACT_SPY_EXIT_BAR",
        }:
            if row["correctedRaw"] or row["correctedExcess"] or not row["missingReason"]:
                raise ValueError("Missing outcome was imputed or has no reason")
        else:
            raise ValueError("Unknown outcome valuation status")
        rows[horizon].append(row)
    if len(events) != contract["expectedEvents"] or any(
        len(rows[horizon]) != len(events) for horizon in contract["horizons"]
    ):
        raise ValueError("Frozen event inventory changed or horizon rows are missing")

    horizons: dict[str, Any] = {}
    for horizon in contract["horizons"]:
        cohort = rows[horizon]
        valued = [row for row in cohort if row["valuationStatus"] == "VALUED"]
        missing = [row for row in cohort if row["valuationStatus"] != "VALUED"]
        gross_excess = [_number(row, "correctedExcess") for row in valued]
        frozen = source["horizons"][str(horizon)]["B1ContinuityCorrected"]
        if len(valued) != frozen["maturedOutcomeCount"] or any(
            not math.isclose(actual, frozen[field], abs_tol=1e-12, rel_tol=1e-10)
            for actual, field in [
                (fmean(gross_excess), "spyExcessMean"),
                (median(gross_excess), "spyExcessMedian"),
            ]
        ):
            raise ValueError("Frozen baseline result does not reproduce")
        costs = []
        for bps in contract["costBpsPerLeg"]:
            net = [net_return(_number(row, "correctedRaw"), bps) for row in valued]
            excess = [value - _number(row, "spyReturn")
                      for value, row in zip(net, valued, strict=True)]
            matched = [value - net_return(_number(row, "spyReturn"), bps)
                       for value, row in zip(net, valued, strict=True)]
            years = {
                str(year): _summary([value for value, row in zip(excess, valued, strict=True)
                                    if row["evaluationSession"].startswith(str(year))])
                for year in range(2016, 2021)
            }
            # Stress assumption, NOT a delisting estimate: every unavailable
            # stock outcome loses all capital. Unknown SPY also remains unknown.
            stress = excess + [-1 - _number(row, "spyReturn") for row in missing
                               if row["spyReturn"]]
            cut = math.floor(len(excess) * .01)
            no_top = sorted(excess)[:-cut] if cut else excess
            costs.append({
                "costBpsPerLeg": bps, "netStock": _summary(net),
                "netExcessVsGrossSpy": _summary(excess),
                "netExcessVsEquallyCostedSpy": _summary(matched), "byFormationYear": years,
                "topOnePercentRemoved": _summary(no_top),
                "missingStockZeroRecoveryStress": _summary(stress),
                "stressUnknownSpy": sum(not row["spyReturn"] for row in missing),
            })
        horizons[str(horizon)] = {
            "events": len(cohort), "observed": len(valued), "missing": len(missing),
            "coverage": len(valued) / len(cohort),
            "missingReasons": dict(sorted(
                Counter(row["valuationStatus"] for row in missing).items())),
            "continuityStates": dict(sorted(
                Counter(row["continuityState"] for row in cohort).items())),
            "costScenarios": costs, "mae": None,
        }
    return {
        "schemaVersion": "1.0.0", "studyId": contract["studyId"],
        "status": "DEVELOPMENT_BASELINE_REPRODUCED_NOT_VALIDATED",
        "sourceRunId": contract["sourceRunId"],
        "lineage": {"contractSha256": text_sha256(contract_bytes),
                    "csvSha256": hashes[0], "summarySha256": hashes[1],
                    "implementationSha256": text_sha256(Path(__file__).read_bytes()),
                    "trackedTextHashNormalization": "CRLF_TO_LF_ONLY"},
        "formation": [contract["formationStart"], contract["formationEnd"]],
        "outcomeEnd": contract["outcomeEnd"], "economicEvents": len(events),
        "primaryHorizon": 126, "horizons": horizons,
        "limitations": [
            "B1_ONLY_NOT_COMPONENT_ABLATIONS_OR_FULL_ENGINE",
            "ACCEPTANCE_FEATURE_AND_ENTRY_CLOCKS_NOT_RECONSTRUCTED_BY_THIS_AUDIT",
            "SOURCE_ENTRY_COHORT_DOES_NOT_COUNT_ALL_ORIGINALLY_UNPRICEABLE_SIGNALS",
            "LIQUIDITY_AND_CAPACITY_NOT_VERIFIED",
            "COST_GRID_IS_A_SENSITIVITY_ASSUMPTION_NOT_REALIZED_EXECUTION",
            "RETURN_ADJUSTMENT_AND_DIVIDEND_TREATMENT_INHERITED_NOT_REAUDITED",
            "CORRECTED_MAE_PATHS_NOT_AVAILABLE",
            "MISSING_OUTCOMES_ARE_NOT_AUTOMATICALLY_DELISTINGS",
            "NO_INDEPENDENCE_ASSUMPTION_OR_SIGNIFICANCE_CLAIM",
            "ALL_RESULTS_PREVIOUSLY_VIEWED_DEVELOPMENT_ONLY",
        ],
        "priorGate": "BLOCK_HAC_AND_OOS", "oosOpened": False,
        "fullEngineValidated": False, "productionScoringChanged": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_baseline(args.csv, args.summary, contract_path=args.contract)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8", newline="\n")
    print(f"{result['status']}: {result['economicEvents']} economic events; no OOS opened")


if __name__ == "__main__":
    main()
