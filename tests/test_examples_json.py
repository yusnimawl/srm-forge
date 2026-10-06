import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from em_validate_8_6 import validation_json  # noqa: E402

from srmcore.maps.checks import Check
from srmcore.maps.validation import KEYS, BudgetRow, EmValidation, UncertaintyBudget


def test_validation_json_is_plain_json_with_nan_as_null():
    one = {k: 1.0 for k in KEYS}
    budget = UncertaintyBudget(one, one, (BudgetRow("mesh", one, "n"),), one)
    v = EmValidation(None, (Check("preset", "pass", math.nan, math.nan, "d"),), budget, "0.4.0",
                     {"stator": "C", "rotor": "C"})
    out = json.loads(json.dumps(validation_json(v, 1.0, 2.0)))
    assert out["checks"][0] == {"name": "preset", "status": "pass", "value": None, "limit": None, "detail": "d"}
    assert out["budget"]["keys"] == list(KEYS) and out["budget"]["rows"][0]["source"] == "mesh"
    assert out["label"] is None and out["map_s"] == 1.0 and out["validate_s"] == 2.0
