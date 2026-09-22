from __future__ import annotations
import importlib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
m=importlib.import_module("research_phase1_feature_tournament_validation_residual11_scope")
def test_constants():
    assert m.EXPECTED_SOURCE_ROWS==19
    assert m.EXPECTED_RESOLVED_ROWS==8
    assert m.EXPECTED_RESIDUAL_ROWS==11
    assert m.EXPECTED_RESIDUAL_DIGEST.startswith("sha256:")
