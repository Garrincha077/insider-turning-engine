"""Attach PIT historical ticker identity to frozen B3 pre-outcome events.

Performance-blind. Each event is re-derived from the authoritative reconciled
P/S revision state at its public knowledge boundary. Economic totals must match
the frozen signal exactly before ticker evidence is accepted.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

PLACEHOLDERS = frozenset({"NA", "NONE"})
WINDOW_DAYS = 30
SEALED_YEAR = 2023


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def _money(row: dict[str, Any]) -> Decimal:
    tx = row["transaction"]
    return Decimal(str(tx["shares"])) * Decimal(str(tx["pricePerShare"]))


def _events(path: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in rows:
        if int(str(row["evaluationSession"])[:4]) >= SEALED_YEAR:
            raise ValueError("sealed OOS boundary violated by B3 event")
    return rows


def _iter_target_issuer_groups(
    path: Path,
    targets: set[str],
):
    seen: set[str] = set()
    current: str | None = None
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            issuer = str(row["issuer"]["cik"])

            if current is None:
                current = issuer
                seen.add(issuer)
            elif issuer != current:
                if issuer in seen:
                    raise ValueError("reconciliation input is not issuer-contiguous")
                if current in targets:
                    yield current, rows
                current = issuer
                rows = []
                seen.add(issuer)

            if issuer in targets:
                rows.append(row)

    if current is not None and current in targets:
        yield current, rows


def _state_at(
    issuer_rows: list[dict[str, Any]],
    moment: datetime,
) -> tuple[Decimal, Decimal, set[str], int]:
    active_by_key: dict[str, dict[str, Any]] = {}
    ticker_evidence: set[str] = set()
    active_rows = 0

    for row in issuer_rows:
        rr = row.get("researchReconciliation") or {}
        side = rr.get("b3QualifiedSide")
        if side not in {"BUY", "SALE"}:
            continue

        event_at_raw = rr.get("economicEventAt")
        if event_at_raw is None:
            continue
        event_at = _dt(str(event_at_raw))
        valid_from = _dt(str(row["lifecycle"]["validFrom"]))
        valid_to = (
            _dt(str(row["lifecycle"]["validTo"]))
            if row["lifecycle"].get("validTo")
            else None
        )

        if not (
            valid_from <= moment
            and (valid_to is None or moment < valid_to)
            and event_at <= moment
            and event_at > moment - timedelta(days=WINDOW_DAYS)
        ):
            continue

        active_rows += 1
        ticker_raw = (row.get("issuer") or {}).get("ticker")
        if ticker_raw:
            ticker_evidence.add(str(ticker_raw).strip().upper())

        key = str(rr["companyEconomicKey"])
        prior = active_by_key.get(key)
        if prior is None or _dt(str(prior["lifecycle"]["validFrom"])) < valid_from:
            active_by_key[key] = row

    buy = Decimal("0")
    sale = Decimal("0")
    for row in active_by_key.values():
        if row["researchReconciliation"]["b3QualifiedSide"] == "BUY":
            buy += _money(row)
        else:
            sale += _money(row)

    return buy, sale, ticker_evidence, active_rows


def attach_identity(
    *,
    events_path: Path,
    event_summary_path: Path,
    revisions_path: Path,
    definition_path: Path,
    output: Path,
) -> dict[str, Any]:
    event_summary = json.loads(event_summary_path.read_text(encoding="utf-8"))
    definition = json.loads(definition_path.read_text(encoding="utf-8"))

    if event_summary.get("status") != "B3_EVENT_CONSTRUCTION_PREOUTCOME_PASS":
        raise ValueError("source event construction has not passed")
    for flag in (
        "marketDataJoined",
        "returnsRead",
        "developmentPerformanceComputed",
        "validationPerformanceComputed",
        "oosOpened",
        "productionScoringChanged",
    ):
        if event_summary.get(flag) is not False:
            raise ValueError(f"source event artifact violates pre-outcome flag {flag}")

    if definition.get("status") != "PREDECLARED_BEFORE_B3_DEVELOPMENT_OUTCOMES":
        raise ValueError("B3 identity definition is not predeclared")
    if int(definition["windowCalendarDays"]) != WINDOW_DAYS:
        raise ValueError("B3 identity lineage window changed from frozen 30 days")

    events = _events(events_path)
    if len(events) != int(event_summary["retainedEventCount"]):
        raise ValueError("event count differs from frozen event-construction summary")

    by_issuer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_issuer[str(event["issuerCik"])].append(event)

    provisional: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    processed_issuers: set[str] = set()

    for issuer, issuer_rows in _iter_target_issuer_groups(
        revisions_path,
        set(by_issuer),
    ):
        processed_issuers.add(issuer)
        for event in by_issuer[issuer]:
            moment = _dt(str(event["knowledgeBoundaryAt"]))
            buy, sale, tickers, evidence_rows = _state_at(issuer_rows, moment)

            expected_buy = Decimal(str(event["buyDollars"]))
            expected_sale = Decimal(str(event["saleDollars"]))
            if buy != expected_buy or sale != expected_sale:
                raise ValueError(
                    "B3 frozen signal lineage mismatch for "
                    f"{event['signalId']}: expected buy/sale "
                    f"{expected_buy}/{expected_sale}, reconstructed {buy}/{sale}"
                )

            real = sorted(ticker for ticker in tickers if ticker not in PLACEHOLDERS)
            placeholders = sorted(ticker for ticker in tickers if ticker in PLACEHOLDERS)

            base = {
                **event,
                "identityEvidenceActiveRows": evidence_rows,
                "identityTickerEvidence": sorted(tickers),
                "identityPlaceholderEvidence": placeholders,
                "identityDefinitionId": definition["definitionId"],
            }

            if not real:
                quarantine.append({**base, "identityStatus": "MISSING_REAL_TICKER"})
                continue
            if len(real) != 1:
                quarantine.append(
                    {
                        **base,
                        "identityStatus": "MULTIPLE_REAL_TICKERS",
                        "realTickerCandidates": real,
                    }
                )
                continue

            provisional.append(
                {
                    **base,
                    "ticker": real[0],
                    "identityStatus": "SINGLE_PIT_TICKER",
                }
            )

    missing_issuers = sorted(set(by_issuer) - processed_issuers)
    if missing_issuers:
        raise ValueError(
            "frozen B3 events missing from authoritative reconciliation: "
            + ",".join(missing_issuers[:10])
        )

    collision_map: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in provisional:
        collision_map[(str(row["ticker"]), str(row["evaluationSession"]))].add(
            str(row["issuerCik"])
        )
    collision_keys = {
        key for key, issuers in collision_map.items() if len(issuers) > 1
    }

    eligible: list[dict[str, Any]] = []
    for row in provisional:
        key = (str(row["ticker"]), str(row["evaluationSession"]))
        if key in collision_keys:
            quarantine.append(
                {
                    **row,
                    "identityStatus": "TICKER_SESSION_CIK_COLLISION",
                    "collisionIssuerCiks": sorted(collision_map[key]),
                }
            )
        else:
            eligible.append(row)

    eligible.sort(
        key=lambda row: (
            str(row["evaluationSession"]),
            str(row["knowledgeBoundaryAt"]),
            str(row["issuerCik"]),
            str(row["signalId"]),
        )
    )
    quarantine.sort(
        key=lambda row: (
            str(row["evaluationSession"]),
            str(row["issuerCik"]),
            str(row["signalId"]),
        )
    )

    output.mkdir(parents=True, exist_ok=True)
    with (output / "b3-development-identity-events.jsonl").open(
        "w", encoding="utf-8"
    ) as stream:
        for row in eligible:
            stream.write(json.dumps(row, sort_keys=True) + "\n")

    with (output / "b3-development-identity-quarantine.jsonl").open(
        "w", encoding="utf-8"
    ) as stream:
        for row in quarantine:
            stream.write(json.dumps(row, sort_keys=True) + "\n")

    status_counts: dict[str, int] = defaultdict(int)
    for row in quarantine:
        status_counts[str(row["identityStatus"])] += 1

    eligible_by_year: dict[str, int] = defaultdict(int)
    for row in eligible:
        eligible_by_year[str(row["evaluationSession"])[:4]] += 1

    total = len(events)
    summary: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_PIT_IDENTITY_ATTACHMENT_PASS",
        "definitionId": definition["definitionId"],
        "sourceEventCount": total,
        "identityEligibleEvents": len(eligible),
        "identityQuarantineEvents": len(quarantine),
        "identityCoverage": len(eligible) / total if total else 0.0,
        "distinctEligibleIssuers": len({str(row["issuerCik"]) for row in eligible}),
        "tickerSessionCollisionKeys": len(collision_keys),
        "quarantineStatusCounts": dict(sorted(status_counts.items())),
        "eligibleByEvaluationYear": dict(sorted(eligible_by_year.items())),
        "signalStateLineageVerified": True,
        "currentTickerFallbackUsed": False,
        "fuzzyIdentityMatchingUsed": False,
        "marketPricesRead": False,
        "returnsRead": False,
        "developmentPerformanceComputed": False,
        "validationPerformanceComputed": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "nextGate": (
            "join identity-eligible B3 events to bounded 2016-2022 exact-session "
            "market data and compute development outcomes without opening 2023+"
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--event-summary", type=Path, required=True)
    parser.add_argument("--revisions", type=Path, required=True)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    print(
        json.dumps(
            attach_identity(
                events_path=args.events,
                event_summary_path=args.event_summary,
                revisions_path=args.revisions,
                definition_path=args.definition,
                output=args.output,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
