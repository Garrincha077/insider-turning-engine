"""Freeze F2 validation residual-11 scope after SPAC resolutions."""

from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ROWS=19
EXPECTED_RESOLVED_ROWS=8
EXPECTED_RESIDUAL_ROWS=11
EXPECTED_SOURCE_DIGEST="sha256:612f62f79717037ecb858998a03cf5fb6d6ce927f308fd08f535af5eeb99945d"
EXPECTED_RESOLUTION_DIGEST="sha256:f08070c07a6bb411490e8f97b6413c5b498496d4f178067ceab5059db4d159c0"
EXPECTED_RESIDUAL_DIGEST="sha256:46381d68c3ad51f9d6d9d7a934d88d807c599f78712f34d4e210c9f4248e5d55"
KEY_FIELDS=("eventNumber","issuerCik","ticker","evaluationSession","entrySession","horizon","targetExitSession")


def _obj(r: dict[str,Any])->dict[str,Any]:
    return {"eventNumber":int(r["eventNumber"]),"issuerCik":str(r["issuerCik"]),
            "ticker":str(r["ticker"]).upper(),"evaluationSession":str(r["evaluationSession"]),
            "entrySession":str(r["entrySession"]),"horizon":int(r["horizon"]),
            "targetExitSession":str(r["targetExitSession"])}


def _key(r:dict[str,Any])->tuple[str,...]:
    o=_obj(r); return tuple(str(o[k]) for k in KEY_FIELDS)


def _digest(rows:list[dict[str,Any]])->str:
    lines=sorted(json.dumps(_obj(r),sort_keys=True,separators=(",",":")) for r in rows)
    return "sha256:"+hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _boundary(p:dict[str,Any],label:str)->None:
    for k,v in {"researchOnly":True,"performanceRead":False,"priceFieldsRead":[],
                "featureOutcomesRead":False,"validationOpened":False,
                "validationPerformanceOpened":False,"oosOpened":False,
                "productionScoringChanged":False}.items():
        if p.get(k)!=v: raise ValueError(f"{label} boundary mismatch: {k}")


def run(*,source_path:Path,resolution_path:Path,output_path:Path)->dict[str,Any]:
    src=json.loads(source_path.read_text())
    res=json.loads(resolution_path.read_text())
    _boundary(src,"residual-19"); _boundary(res,"SPAC resolution")
    if src.get("status")!="PHASE1_FEATURE_TOURNAMENT_VALIDATION_RESIDUAL19_SCOPE_FROZEN": raise ValueError("source status")
    if src.get("residualRows")!=19 or src.get("scopeKeySha256")!=EXPECTED_SOURCE_DIGEST: raise ValueError("source scope")
    if res.get("status")!="PHASE1_FEATURE_TOURNAMENT_VALIDATION_SPAC_SHARE_EXCHANGE_PRIMARY_RESOLUTION_COMPLETE": raise ValueError("resolution status")
    if res.get("resolvedRows")!=8 or res.get("resolvedKeySha256")!=EXPECTED_RESOLUTION_DIGEST: raise ValueError("resolution scope")
    srows=src.get("rows"); rrows=res.get("resolutionRows")
    if not isinstance(srows,list) or len(srows)!=19: raise ValueError("source rows")
    if not isinstance(rrows,list) or len(rrows)!=8: raise ValueError("resolution rows")
    if _digest(srows)!=EXPECTED_SOURCE_DIGEST or _digest(rrows)!=EXPECTED_RESOLUTION_DIGEST: raise ValueError("key digest changed")
    rkeys={_key(r) for r in rrows}
    residual=[r for r in srows if _key(r) not in rkeys]
    if len(residual)!=11 or _digest(residual)!=EXPECTED_RESIDUAL_DIGEST: raise ValueError("residual-11 changed")
    cats=Counter(str((r.get("evidenceAudit") or {}).get("category") or "") for r in residual)
    if cats!=Counter({"LONG_GAP_NEW_PRIMARY_EVIDENCE_REQUIRED":10,"PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED":1}): raise ValueError("category partition")
    provider=[r for r in residual if str((r.get("evidenceAudit") or {}).get("category") or "")=="PROVIDER_NEW_PRIMARY_EVIDENCE_REQUIRED"]
    if len(provider)!=1 or provider[0]["ticker"]!="CBTX" or provider[0].get("candidateActionTypes")!=["name_changes"]: raise ValueError("provider residual changed")
    residual.sort(key=lambda r:(int(r["eventNumber"]),int(r["horizon"])))
    out={"schemaVersion":"1.0.0","status":"PHASE1_FEATURE_TOURNAMENT_VALIDATION_RESIDUAL11_SCOPE_FROZEN",
         "researchOnly":True,"performanceRead":False,"priceFieldsRead":[],"featureOutcomesRead":False,
         "validationOpened":False,"validationPerformanceOpened":False,"oosOpened":False,"productionScoringChanged":False,
         "sourceResidualRows":19,"subtractedSpacRows":8,"residualRows":11,
         "scopeKeySha256":EXPECTED_RESIDUAL_DIGEST,"categoryCounts":dict(sorted(cats.items())),
         "rows":residual,"resolutionComplete":False}
    output_path.parent.mkdir(parents=True,exist_ok=True); output_path.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    return out


def main()->None:
    p=argparse.ArgumentParser(); p.add_argument("--source",type=Path,required=True); p.add_argument("--resolution",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); r=run(source_path=a.source,resolution_path=a.resolution,output_path=a.output)
    print(json.dumps({k:v for k,v in r.items() if k!="rows"},indent=2,sort_keys=True))
if __name__=="__main__": main()
