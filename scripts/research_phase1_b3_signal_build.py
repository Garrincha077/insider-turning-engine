"""Build performance-blind B3 company-net-buying raw signal candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any


def _iter_issuer_groups(
    path: Path,
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Stream issuer-contiguous reconciliation rows without loading the file."""

    seen: set[str] = set()
    current_issuer: str | None = None
    current_rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue

            row = json.loads(line)
            issuer = str(row["issuer"]["cik"])

            if current_issuer is None:
                current_issuer = issuer
                seen.add(issuer)
            elif issuer != current_issuer:
                if issuer in seen:
                    raise ValueError("reconciliation input is not issuer-contiguous")
                if current_rows:
                    yield current_issuer, current_rows
                current_issuer = issuer
                current_rows = []
                seen.add(issuer)

            rr = row.get("researchReconciliation") or {}
            if rr.get("b3QualifiedSide") not in {"BUY", "SALE"}:
                continue

            event_at = rr.get("economicEventAt")
            if event_at is None:
                continue
            if int(str(event_at)[:4]) >= 2023:
                raise ValueError("sealed OOS boundary violated")

            current_rows.append(row)

    if current_issuer is not None and current_rows:
        yield current_issuer, current_rows


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def _money(row: dict[str, Any]) -> Decimal:
    tx = row["transaction"]
    return Decimal(str(tx["shares"])) * Decimal(str(tx["pricePerShare"]))


def build(
    *,
    revisions_path: Path,
    definition_path: Path,
    output: Path,
) -> dict[str, Any]:
    definition = json.loads(definition_path.read_text(encoding="utf-8"))
    if definition.get("b3DefinitionFrozen") is not True:
        raise ValueError("B3 definition must be frozen before signal build")
    if definition.get("developmentPerformanceComputed") is not False:
        raise ValueError("definition artifact unexpectedly contains performance")

    window = int(definition["primaryWindowCalendarDays"])
    start = datetime(2016, 1, 1, tzinfo=UTC)
    end = datetime(2021, 1, 1, tzinfo=UTC)

    output.mkdir(parents=True, exist_ok=True)
    candidate_path = output / "b3-raw-signal-candidates.jsonl"

    candidate_count = 0
    by_year: dict[str, int] = defaultdict(int)
    candidate_issuers: set[str] = set()

    with candidate_path.open("w", encoding="utf-8") as stream:
        for issuer, issuer_rows in _iter_issuer_groups(revisions_path):
            boundaries: set[datetime] = set()
            for row in issuer_rows:
                valid_from = _dt(row["lifecycle"]["validFrom"])
                valid_to = (
                    _dt(row["lifecycle"]["validTo"])
                    if row["lifecycle"].get("validTo")
                    else None
                )
                event_at = _dt(row["researchReconciliation"]["economicEventAt"])
                boundaries.add(valid_from)
                if valid_to is not None:
                    boundaries.add(valid_to)
                boundaries.add(event_at + timedelta(days=window))

            prior_signature: tuple[Any, ...] | None = None

            for moment in sorted(t for t in boundaries if start <= t < end):
                active_by_key: dict[str, dict[str, Any]] = {}

                for row in issuer_rows:
                    valid_from = _dt(row["lifecycle"]["validFrom"])
                    valid_to = (
                        _dt(row["lifecycle"]["validTo"])
                        if row["lifecycle"].get("validTo")
                        else None
                    )
                    event_at = _dt(row["researchReconciliation"]["economicEventAt"])

                    if not (
                        valid_from <= moment
                        and (valid_to is None or moment < valid_to)
                        and event_at <= moment
                        and event_at > moment - timedelta(days=window)
                    ):
                        continue

                    key = str(row["researchReconciliation"]["companyEconomicKey"])
                    prior = active_by_key.get(key)
                    if (
                        prior is None
                        or _dt(prior["lifecycle"]["validFrom"]) < valid_from
                    ):
                        active_by_key[key] = row

                buy = Decimal("0")
                sale = Decimal("0")

                for row in active_by_key.values():
                    side = row["researchReconciliation"]["b3QualifiedSide"]
                    if side == "BUY":
                        buy += _money(row)
                    else:
                        sale += _money(row)

                gross = buy + sale
                net = buy - sale
                intensity = (net / gross) if gross > 0 else Decimal("0")
                signature = (
                    str(buy),
                    str(sale),
                    tuple(sorted(active_by_key)),
                )

                if signature == prior_signature:
                    continue
                prior_signature = signature

                if buy <= 0 or net <= 0:
                    continue

                material = f"{issuer}|{moment.isoformat()}|{buy}|{sale}|{window}"
                candidate = {
                    "signalId": "b3_"
                    + hashlib.sha256(material.encode()).hexdigest()[:24],
                    "issuerCik": issuer,
                    "knowledgeBoundaryAt": moment.isoformat(),
                    "primaryWindowCalendarDays": window,
                    "buyDollars": format(buy, "f"),
                    "saleDollars": format(sale, "f"),
                    "netDollars": format(net, "f"),
                    "grossDollars": format(gross, "f"),
                    "netBuyingIntensity": format(intensity, "f"),
                    "activeEconomicRows": len(active_by_key),
                    "definitionId": definition["definitionId"],
                    "requiresDownstreamXnys20SessionIssuerDedup": True,
                }
                stream.write(json.dumps(candidate, sort_keys=True) + "\n")
                candidate_count += 1
                by_year[candidate["knowledgeBoundaryAt"][:4]] += 1
                candidate_issuers.add(issuer)

    summary = {
        "schemaVersion": "1.0.0",
        "dataset": "B3 company-net-buying raw development signal candidates",
        "developmentPeriod": "2016-2020",
        "rawCandidateCount": candidate_count,
        "distinctIssuers": len(candidate_issuers),
        "candidateCountByYear": dict(sorted(by_year.items())),
        "definitionId": definition["definitionId"],
        "primaryWindowCalendarDays": window,
        "marketDataJoined": False,
        "returnsRead": False,
        "developmentPerformanceComputed": False,
        "validationPerformanceComputed": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "nextGate": (
            "map raw candidates to exact XNYS evaluation/entry sessions and apply "
            "20-session issuer dedup before development outcomes"
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revisions", type=Path, required=True)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    print(
        json.dumps(
            build(
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
