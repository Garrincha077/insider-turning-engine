"""Resolve eight F2 validation SPAC share-exchange rows from frozen SEC evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ROWS = 19
EXPECTED_TARGET_ROWS = 8
EXPECTED_REMAINING_ROWS = 11
EXPECTED_SOURCE_DIGEST = (
    "sha256:612f62f79717037ecb858998a03cf5fb6d6ce927f308fd08f535af5eeb99945d"
)
EXPECTED_TARGET_DIGEST = (
    "sha256:f08070c07a6bb411490e8f97b6413c5b498496d4f178067ceab5059db4d159c0"
)
KEY_FIELDS = (
    "eventNumber","issuerCik","ticker","evaluationSession",
    "entrySession","horizon","targetExitSession",
)


def _key_object(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventNumber": int(row["eventNumber"]),
        "issuerCik": str(row["issuerCik"]),
        "ticker": str(row["ticker"]).upper(),
        "evaluationSession": str(row["evaluationSession"]),
        "entrySession": str(row["entrySession"]),
        "horizon": int(row["horizon"]),
        "targetExitSession": str(row["targetExitSession"]),
    }


def _digest(rows: list[dict[str, Any]]) -> str:
    lines=sorted(json.dumps(_key_object(r),sort_keys=True,separators=(",",":")) for r in rows)
    return "sha256:"+hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _number(value: object) -> Decimal:
    try:
        n=Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"invalid numeric value: {value}") from None
    if not n.is_finite():
        raise ValueError("non-finite numeric value")
    return n


def _fmt(n: Decimal) -> str:
    return "0" if n==0 else format(n.normalize(),"f")


def _load_scope(path: Path) -> list[dict[str, Any]]:
    p=json.loads(path.read_text(encoding="utf-8"))
    required={
        "status":"PHASE1_FEATURE_TOURNAMENT_VALIDATION_RESIDUAL19_SCOPE_FROZEN",
        "researchOnly":True,"performanceRead":False,"priceFieldsRead":[],
        "featureOutcomesRead":False,"validationOpened":False,
        "validationPerformanceOpened":False,"oosOpened":False,
        "productionScoringChanged":False,"residualRows":EXPECTED_SOURCE_ROWS,
        "scopeKeySha256":EXPECTED_SOURCE_DIGEST,
    }
    for k,v in required.items():
        if p.get(k)!=v: raise ValueError(f"residual-19 mismatch: {k}")
    rows=p.get("rows")
    if not isinstance(rows,list) or len(rows)!=EXPECTED_SOURCE_ROWS:
        raise ValueError("residual-19 rows changed")
    if _digest(rows)!=EXPECTED_SOURCE_DIGEST:
        raise ValueError("residual-19 semantic keys changed")
    return [dict(r) for r in rows]


def _load_evidence(path: Path) -> dict[frozenset[str], dict[str, Any]]:
    p=json.loads(path.read_text(encoding="utf-8"))
    required={
        "contractId":"phase1-feature-tournament-validation-spac-share-exchange-primary-evidence-v1",
        "researchOnly":True,"performanceRead":False,"priceFieldsRead":[],
        "featureOutcomesRead":False,"validationOpened":False,
        "validationPerformanceOpened":False,"oosOpened":False,
        "productionScoringChanged":False,
        "sourceResidualAssetDigest":"sha256:2b2ebcf18d1ab74594141cbbaec00f911f4db4c01e529d34f000a8b24ddfcf67",
        "expectedRows":EXPECTED_TARGET_ROWS,"expectedIdentities":6,
        "expectedKeySha256":EXPECTED_TARGET_DIGEST,
        "resolutionApplied":False,
    }
    for key, expected in required.items():
        if p.get(key) != expected:
            raise ValueError(f"SPAC evidence mismatch: {key}")
    rows=p.get("evidence")
    if not isinstance(rows,list) or len(rows)!=6:
        raise ValueError("SPAC evidence identity count changed")
    out={}
    for r in rows:
        ids=frozenset(str(x) for x in r.get("actionIds") or [])
        if len(ids)!=2 or ids in out:
            raise ValueError("invalid/duplicate SPAC action set")
        if not r.get("primaryEvidence"):
            raise ValueError("SPAC primary evidence missing")
        out[ids]=dict(r)
    return out


def _resolution(row: dict[str, Any], fact: dict[str, Any]) -> dict[str, Any]:
    ids=frozenset(str(x) for x in row.get("candidateActionIds") or [])
    if ids!=frozenset(str(x) for x in fact["actionIds"]):
        raise ValueError("SPAC action set changed")
    action_types = sorted(str(x) for x in row.get("candidateActionTypes") or [])
    if action_types != ["name_changes", "stock_mergers"]:
        raise ValueError("SPAC source action types changed")
    if str(row.get("resolutionSource") or "")!="provider":
        raise ValueError("SPAC source classification changed")
    category = str((row.get("evidenceAudit") or {}).get("category") or "")
    if category != "PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED":
        raise ValueError("SPAC evidence category changed")
    same_issuer = str(row["issuerCik"]) == str(fact["issuerCik"])
    same_ticker = str(row["ticker"]).upper() == str(fact["ticker"]).upper()
    if not same_issuer or not same_ticker:
        raise ValueError("SPAC identity changed")

    effective=str(fact["effectiveDate"])
    if not str(row["entrySession"]) < effective <= str(row["targetExitSession"]):
        raise ValueError("SPAC effective date outside event horizon")
    if fact["resolutionDecision"]!="TRANSFORMED_HOLDER_CONSIDERATION":
        raise ValueError("SPAC decision changed")
    if fact["transformationKind"]!="PRIMARY_SEC_SPAC_STOCK_EXCHANGE":
        raise ValueError("SPAC transformation kind changed")
    if fact["resultState"]!="TRANSFORMED_HOLDER_CONSIDERATION":
        raise ValueError("SPAC result state changed")

    successor=str(fact["successorSymbol"]).upper()
    qty=_number(fact["successorSharesPerEntryShare"])
    cash=_number(fact["cashPerEntryShare"])
    if not successor or qty!=Decimal("1") or cash!=0:
        raise ValueError("SPAC holder economics changed")

    return {
        **_key_object(row),
        "expectedSourceResolutionSource":"provider",
        "effectiveDate":effective,
        "resolutionDecision":"TRANSFORMED_HOLDER_CONSIDERATION",
        "transformationKind":"PRIMARY_SEC_SPAC_STOCK_EXCHANGE",
        "resultState":"TRANSFORMED_HOLDER_CONSIDERATION",
        "successorSymbol":successor,
        "successorSharesPerEntryShare":_fmt(qty),
        "cashPerEntryShare":"0",
        "sourceActionIds":sorted(ids),
        "basket":[],
        "classificationSource":"VALIDATION_PRIMARY_SPAC_SHARE_EXCHANGE_TERMS",
        "evidenceClass":"PRIMARY_SEC_SPAC_COMMON_SHARE_EXCHANGE_1_TO_1",
        "primaryEvidenceAccessions":[str(x["accession"]) for x in fact["primaryEvidence"]],
    }


def run(*, scope_path: Path, evidence_path: Path, output_path: Path) -> dict[str, Any]:
    scope=_load_scope(scope_path)
    evidence=_load_evidence(evidence_path)
    targets=[
        r for r in scope
        if sorted(str(x) for x in r.get("candidateActionTypes") or [])
        == ["name_changes", "stock_mergers"]
    ]
    if len(targets)!=EXPECTED_TARGET_ROWS: raise ValueError("SPAC target count changed")
    if _digest(targets)!=EXPECTED_TARGET_DIGEST: raise ValueError("SPAC target digest changed")

    resolutions=[]
    for row in targets:
        ids=frozenset(str(x) for x in row.get("candidateActionIds") or [])
        fact=evidence.get(ids)
        if fact is None: raise ValueError("SPAC action set lacks frozen evidence")
        resolutions.append(_resolution(row,fact))
    resolutions.sort(key=lambda r:(int(r["eventNumber"]),int(r["horizon"])))
    if _digest(resolutions)!=EXPECTED_TARGET_DIGEST: raise ValueError("resolved SPAC keys changed")

    result={
        "schemaVersion":"1.0.0",
        "status":"PHASE1_FEATURE_TOURNAMENT_VALIDATION_SPAC_SHARE_EXCHANGE_PRIMARY_RESOLUTION_COMPLETE",
        "researchOnly":True,"performanceRead":False,"priceFieldsRead":[],
        "featureOutcomesRead":False,"validationOpened":False,
        "validationPerformanceOpened":False,"oosOpened":False,
        "productionScoringChanged":False,
        "sourceResidualRows":EXPECTED_SOURCE_ROWS,
        "resolvedRows":len(resolutions),
        "remainingUnresolvedRows":EXPECTED_REMAINING_ROWS,
        "resolvedKeySha256":EXPECTED_TARGET_DIGEST,
        "resolutionRows":resolutions,
        "resolutionApplied":True,"resolutionComplete":False,
    }
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return result


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--scope",type=Path,required=True)
    parser.add_argument("--evidence",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=run(scope_path=args.scope,evidence_path=args.evidence,output_path=args.output)
    print(json.dumps({k:v for k,v in result.items() if k!="resolutionRows"},indent=2,sort_keys=True))


if __name__=="__main__":
    main()
