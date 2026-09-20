"""Generate performance-blind B3 continuity resolution candidates.

This is NOT the final resolution overlay. It proposes only deterministic rows
supported by (a) direct frozen provider action terms or (b) an already frozen
B1 performance-blind resolution for the same issuer/security evidence.
Residual rows remain explicitly unresolved for separate primary-source review.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import research_phase1_security_continuity_resolution as base

B1_CONTRACT_SHA256 = (
    "sha256:88325d71dd9da1f18bdc2c2695933860e087addd586def8b4271ed768d121430"
)


def _scope_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    columns = payload["unresolvedColumns"]
    rows = [
        dict(zip(columns, values, strict=True))
        for values in payload["unresolvedRows"]
    ]
    if base._key_digest(rows) != payload["frozenScope"]["unresolvedRowKeySha256"]:
        raise ValueError("B3 unresolved key digest mismatch")
    return rows


def _actions(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("performanceRead") is not False:
        raise ValueError("corporate-action source is not performance-blind")
    if payload.get("oosOpened") is not False:
        raise ValueError("corporate-action source opened OOS")
    return {
        str(action["id"]): action
        for action in payload.get("actions", [])
    }


def _b1_rows(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    import hashlib

    actual = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual != B1_CONTRACT_SHA256:
        raise ValueError("B1 continuity contract hash changed")
    payload = json.loads(raw)
    columns = payload["resolutionColumns"]
    return [
        dict(zip(columns, values, strict=True))
        for values in payload["resolutions"]
    ]


def _provider_candidate(
    row: dict[str, Any],
    actions: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    ids = [value for value in str(row["candidateActionIds"]).split(";") if value]
    selected = [actions[value] for value in ids if value in actions]
    if len(selected) != len(ids):
        return None, "PROVIDER_ACTION_ID_MISSING"

    buckets = sorted(str(action.get("bucket") or "") for action in selected)

    # Stock dividends carry an explicit per-share quantity factor.
    if len(selected) == 1 and buckets == ["stock_dividends"]:
        action = selected[0]
        rate = float(action.get("rate") or 0)
        if rate <= 0:
            return None, "STOCK_DIVIDEND_RATE_INVALID"
        effective = str(action.get("actionDate") or "")
        if not str(row["entrySession"]) < effective <= str(row["targetExitSession"]):
            return None, "PROVIDER_ACTION_OUTSIDE_HORIZON"
        ticker = str(row["ticker"])
        return {
            **base._key_object(row),
            "evidenceClass": "DIRECT_PROVIDER_TERMS",
            "expectedSourceResolutionSource": "provider",
            "effectiveDate": effective,
            "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
            "transformationKind": "STOCK_DIVIDEND_QUANTITY",
            "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
            "successorSymbol": ticker,
            "successorSharesPerEntryShare": rate,
            "cashPerEntryShare": 0.0,
            "sourceActionIds": ids,
        }, "RESOLVED_PROVIDER_STOCK_DIVIDEND"

    # Alpaca may report a mixed acquisition as paired stock + cash merger rows.
    if buckets == ["cash_mergers", "stock_mergers"] and len(selected) == 2:
        stock = next(action for action in selected if action["bucket"] == "stock_mergers")
        cash = next(action for action in selected if action["bucket"] == "cash_mergers")
        if str(stock.get("actionDate")) != str(cash.get("actionDate")):
            return None, "MIXED_MERGER_DATES_DIFFER"
        acquiree_rate = float(stock.get("acquiree_rate") or 0)
        acquirer_rate = float(stock.get("acquirer_rate") or 0)
        cash_rate = float(cash.get("rate") or 0)
        successor = str(stock.get("acquirer_symbol") or "").upper()
        effective = str(stock.get("actionDate") or "")
        if (
            acquiree_rate <= 0
            or acquirer_rate < 0
            or cash_rate < 0
            or not successor
        ):
            return None, "MIXED_MERGER_TERMS_INCOMPLETE"
        if not str(row["entrySession"]) < effective <= str(row["targetExitSession"]):
            return None, "PROVIDER_ACTION_OUTSIDE_HORIZON"
        return {
            **base._key_object(row),
            "evidenceClass": "DIRECT_PROVIDER_TERMS",
            "expectedSourceResolutionSource": "provider",
            "effectiveDate": effective,
            "resolutionDecision": "TRANSFORMED_HOLDER_CONSIDERATION",
            "transformationKind": "STOCK_AND_CASH_MERGER",
            "resultState": "TRANSFORMED_HOLDER_CONSIDERATION",
            "successorSymbol": successor,
            "successorSharesPerEntryShare": acquirer_rate / acquiree_rate,
            "cashPerEntryShare": cash_rate / acquiree_rate,
            "sourceActionIds": ids,
        }, "RESOLVED_PROVIDER_MIXED_MERGER"

    # WPF -> ALIT has an explicit same-CUSIP name change plus a 1:1 stock row.
    if buckets == ["name_changes", "stock_mergers"] and len(selected) == 2:
        name = next(action for action in selected if action["bucket"] == "name_changes")
        stock = next(action for action in selected if action["bucket"] == "stock_mergers")
        same_cusip = (
            str(name.get("old_cusip") or "")
            and str(name.get("old_cusip")) == str(name.get("new_cusip"))
            and str(name.get("new_cusip")) == str(stock.get("acquirer_cusip") or "")
        )
        acquiree_rate = float(stock.get("acquiree_rate") or 0)
        acquirer_rate = float(stock.get("acquirer_rate") or 0)
        successor = str(name.get("new_symbol") or "").upper()
        effective = str(name.get("actionDate") or "")
        if (
            same_cusip
            and acquiree_rate > 0
            and acquirer_rate / acquiree_rate == 1.0
            and successor
            and str(row["entrySession"]) < effective <= str(row["targetExitSession"])
        ):
            return {
                **base._key_object(row),
                "evidenceClass": "DIRECT_PROVIDER_SAME_CUSIP",
                "expectedSourceResolutionSource": "provider",
                "effectiveDate": effective,
                "resolutionDecision": "SYMBOL_CHANGED_SAME_SECURITY",
                "transformationKind": "SAME_SECURITY_SYMBOL_CHANGE",
                "resultState": "SYMBOL_CHANGED_SAME_SECURITY",
                "successorSymbol": successor,
                "successorSharesPerEntryShare": 1.0,
                "cashPerEntryShare": 0.0,
                "sourceActionIds": ids,
            }, "RESOLVED_PROVIDER_SAME_CUSIP"

    return None, "PROVIDER_AMBIGUOUS_REQUIRES_PRIMARY_EVIDENCE"


def _b1_candidate(
    row: dict[str, Any],
    b1_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    issuer = str(row["issuerCik"])
    ticker = str(row["ticker"])
    entry = str(row["entrySession"])
    target = str(row["targetExitSession"])
    gap = str(row.get("maxInternalGapSessions") or "")

    same_pair = [
        source
        for source in b1_rows
        if str(source["issuerCik"]) == issuer and str(source["ticker"]) == ticker
    ]
    candidates: list[dict[str, Any]] = []
    for source in same_pair:
        effective = str(source["effectiveDate"])
        if not entry < effective <= target:
            continue
        decision = str(source["resolutionDecision"])
        if decision == "SAME_SECURITY_CONTINUITY":
            if str(source.get("maxInternalGapSessions") or "") != gap:
                continue
            candidates.append(source)
        elif decision == "TRANSFORMED_HOLDER_CONSIDERATION":
            candidates.append(source)

    # Deduplicate equivalent evidence terms. Multiple B1 event rows may certify
    # the same underlying continuity fact.
    unique: dict[tuple[str, ...], dict[str, Any]] = {}
    for source in candidates:
        signature = (
            str(source["effectiveDate"]),
            str(source["resolutionDecision"]),
            str(source["transformationKind"]),
            str(source["resultState"]),
            str(source["successorSymbol"]),
            str(source["shareQuantityFactor"]),
            json.dumps(source.get("sourceActionIds") or [], sort_keys=True),
        )
        unique[signature] = source

    if len(unique) != 1:
        return None, (
            "NO_MATCHING_PRIOR_B1_EVIDENCE"
            if not unique
            else "AMBIGUOUS_PRIOR_B1_EVIDENCE"
        )

    source = next(iter(unique.values()))
    decision = str(source["resolutionDecision"])
    quantity = float(source["shareQuantityFactor"])
    return {
        **base._key_object(row),
        "evidenceClass": "PRIOR_FROZEN_B1_CONTINUITY_EVIDENCE",
        "expectedSourceResolutionSource": str(row["resolutionSource"]),
        "effectiveDate": str(source["effectiveDate"]),
        "resolutionDecision": decision,
        "transformationKind": str(source["transformationKind"]),
        "resultState": str(source["resultState"]),
        "successorSymbol": str(source["successorSymbol"]),
        "successorSharesPerEntryShare": quantity,
        "cashPerEntryShare": 0.0,
        "sourceActionIds": source.get("sourceActionIds") or [],
        "priorB1ContractSha256": B1_CONTRACT_SHA256,
    }, "RESOLVED_BY_PRIOR_B1_EVIDENCE"


def generate(
    *,
    scope_path: Path,
    corporate_actions_path: Path,
    b1_contract_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    if scope.get("status") != "B3_UNRESOLVED_CONTINUITY_SCOPE_FROZEN":
        raise ValueError("B3 unresolved scope is not frozen")
    if scope.get("performanceRead") is not False or scope.get("oosOpened") is not False:
        raise ValueError("B3 unresolved scope violates research boundaries")

    rows = _scope_rows(scope)
    actions = _actions(corporate_actions_path)
    b1_rows = _b1_rows(b1_contract_path)

    candidates: list[dict[str, Any]] = []
    residual: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    evidence_classes: Counter[str] = Counter()

    for row in rows:
        candidate: dict[str, Any] | None = None
        reason = ""

        if row["resolutionSource"] == "provider":
            candidate, reason = _provider_candidate(row, actions)

        if candidate is None:
            prior, prior_reason = _b1_candidate(row, b1_rows)
            if prior is not None:
                candidate = prior
                reason = prior_reason
            elif not reason:
                reason = prior_reason

        if candidate is None:
            residual.append(
                {
                    **base._key_object(row),
                    "resolutionSource": row["resolutionSource"],
                    "candidateActionTypes": row["candidateActionTypes"],
                    "candidateActionIds": row["candidateActionIds"],
                    "maxInternalGapSessions": row["maxInternalGapSessions"],
                    "residualReason": reason,
                }
            )
            reasons[reason] += 1
        else:
            candidates.append(candidate)
            evidence_classes[str(candidate["evidenceClass"])] += 1
            reasons[reason] += 1

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "B3_CONTINUITY_RESOLUTION_CANDIDATES_COMPLETE",
        "researchOnly": True,
        "performanceRead": False,
        "priceFieldsRead": [],
        "oosOpened": False,
        "productionScoringChanged": False,
        "sourceUnresolvedRows": len(rows),
        "candidateResolutionRows": len(candidates),
        "residualUnresolvedRows": len(residual),
        "candidateEvidenceClasses": dict(sorted(evidence_classes.items())),
        "reasonCounts": dict(sorted(reasons.items())),
        "frozenScopeKeySha256": scope["frozenScope"]["unresolvedRowKeySha256"],
        "candidateRows": candidates,
        "residualRows": residual,
        "finalResolutionContractCreated": False,
        "correctedPerformanceOpened": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--corporate-actions", type=Path, required=True)
    parser.add_argument("--b1-contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            generate(
                scope_path=args.scope,
                corporate_actions_path=args.corporate_actions,
                b1_contract_path=args.b1_contract,
                output_path=args.output,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
