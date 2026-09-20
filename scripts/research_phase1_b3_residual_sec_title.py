"""Accession-pinned SEC security-title corroboration for residual B3 continuity."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _norm(value: object) -> str:
    return " ".join(str(value or "").upper().split())


def audit(
    *,
    corroboration_path: Path,
    pit_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    source = json.loads(corroboration_path.read_text(encoding="utf-8"))
    wanted: set[str] = set()
    for row in source:
        for side in ("beforeObservation", "afterObservation"):
            observation = row.get(side)
            if observation and observation.get("accession"):
                wanted.add(str(observation["accession"]))

    titles: dict[str, set[str]] = defaultdict(set)
    underlying: dict[str, set[str]] = defaultdict(set)
    for path in sorted(pit_root.rglob("canonical-research.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                row = json.loads(line)
                accession = str((row.get("source") or {}).get("accessionNumber") or "")
                if accession not in wanted:
                    continue
                knowledge = str((row.get("timestamps") or {}).get("knowledgeAt") or "")
                if not knowledge or int(knowledge[:4]) >= 2023:
                    raise ValueError("sealed OOS boundary violated")
                security = row.get("security") or {}
                title = _norm(security.get("title"))
                under = _norm(security.get("underlyingTitle"))
                if title:
                    titles[accession].add(title)
                if under:
                    underlying[accession].add(under)

    output: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in source:
        before = row.get("beforeObservation")
        after = row.get("afterObservation")
        bacc = str((before or {}).get("accession") or "")
        aacc = str((after or {}).get("accession") or "")
        bt = sorted(titles.get(bacc, set()))
        at = sorted(titles.get(aacc, set()))
        bu = sorted(underlying.get(bacc, set()))
        au = sorted(underlying.get(aacc, set()))

        if not bacc or not aacc:
            status = "ONE_SIDED_ACCESSION_ONLY"
        elif not bt or not at:
            status = "TITLE_EVIDENCE_MISSING"
        elif bt == at:
            status = "TITLE_SET_EXACT_MATCH"
        elif set(bt) & set(at):
            status = "TITLE_SET_OVERLAP"
        else:
            status = "TITLE_SET_CHANGED"

        counts[status] += 1
        output.append(
            {
                **row,
                "beforeSecurityTitles": bt,
                "afterSecurityTitles": at,
                "beforeUnderlyingTitles": bu,
                "afterUnderlyingTitles": au,
                "securityTitleStatus": status,
                "continuityStateChanged": False,
                "finalResolutionAllowedFromThisStage": False,
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "b3-residual-sec-title-corroboration.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {
        "schemaVersion": "1.0.0",
        "status": "B3_RESIDUAL_SEC_TITLE_CORROBORATION_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceRows": len(source),
        "targetAccessions": len(wanted),
        "accessionsWithTitleEvidence": len(titles),
        "statusCounts": dict(sorted(counts.items())),
        "continuityStatesChanged": 0,
        "finalResolutionContractCreated": False,
        "correctedPerformanceOpened": False,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corroboration", type=Path, required=True)
    parser.add_argument("--pit-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(
        corroboration_path=args.corroboration,
        pit_root=args.pit_root,
        output_dir=args.output_dir,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
