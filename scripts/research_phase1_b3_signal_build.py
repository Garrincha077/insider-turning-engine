"""Build performance-blind B3 company-net-buying raw signal candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def _money(row: dict[str, Any]) -> Decimal:
    tx = row["transaction"]
    return Decimal(str(tx["shares"])) * Decimal(str(tx["pricePerShare"]))


def build(*, revisions_path: Path, definition_path: Path, output: Path) -> dict[str, Any]:
    definition = json.loads(definition_path.read_text())
    if definition.get("b3DefinitionFrozen") is not True:
        raise ValueError("B3 definition must be frozen before signal build")
    if definition.get("developmentPerformanceComputed") is not False:
        raise ValueError("definition artifact unexpectedly contains performance")

    rows = _read_jsonl(revisions_path)
    by_issuer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rr = row.get("researchReconciliation") or {}
        if rr.get("b3QualifiedSide") not in {"BUY", "SALE"}:
            continue
        event_at = rr.get("economicEventAt")
        if event_at is None:
            continue
        if int(event_at[:4]) >= 2023:
            raise ValueError("sealed OOS boundary violated")
        by_issuer[str(row["issuer"]["cik"])].append(row)

    window = int(definition["primaryWindowCalendarDays"])
    start = datetime(2016, 1, 1, tzinfo=UTC)
    end = datetime(2021, 1, 1, tzinfo=UTC)
    candidates: list[dict[str, Any]] = []

    for issuer, issuer_rows in sorted(by_issuer.items()):
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
                if prior is None or _dt(prior["lifecycle"]["validFrom"]) < valid_from:
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
            candidates.append(
                {
                    "signalId": "b3_" + hashlib.sha256(material.encode()).hexdigest()[:24],
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
            )

    output.mkdir(parents=True, exist_ok=True)
    with (output / "b3-raw-signal-candidates.jsonl").open("w", encoding="utf-8") as stream:
        for row in candidates:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    by_year: dict[str, int] = defaultdict(int)
    issuers: set[str] = set()
    for row in candidates:
        by_year[row["knowledgeBoundaryAt"][:4]] += 1
        issuers.add(row["issuerCik"])
    summary = {
        "schemaVersion": "1.0.0",
        "dataset": "B3 company-net-buying raw development signal candidates",
        "developmentPeriod": "2016-2020",
        "rawCandidateCount": len(candidates),
        "distinctIssuers": len(issuers),
        "candidateCountByYear": dict(sorted(by_year.items())),
        "definitionId": definition["definitionId"],
        "primaryWindowCalendarDays": window,
        "marketDataJoined": False,
        "returnsRead": False,
        "developmentPerformanceComputed": False,
        "validationPerformanceComputed": False,
        "oosOpened": False,
        "productionScoringChanged": False,
        "nextGate": "map raw candidates to exact XNYS evaluation/entry sessions and apply 20-session issuer dedup before development outcomes",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revisions", type=Path, required=True)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(
        revisions_path=args.revisions,
        definition_path=args.definition,
        output=args.output,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
