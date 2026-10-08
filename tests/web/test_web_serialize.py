import json
import math

import numpy as np
import pytest
from conftest import make_8_6
from srmapp.drive.envelope import Envelope
from srmapp.evaluate import Evaluation, MapArrays
from srmapp.pipeline import SearchResult
from srmapp.requirements import Requirements
from srmapp.sizing.winding import Winding
from srmapp.wire import RoundWire
from srmcore.model.design import Design, MeshSettings
from srmweb.serialize import electrical_deg_from_unaligned, evaluation_json, search_result_json, to_json

NAN = float("nan")


def test_nan_and_inf_become_null():
    assert to_json({"a": NAN, "b": np.array([1.0, np.inf])}) == {"a": None, "b": [1.0, None]}


def test_numpy_scalars_and_tuples():
    out = to_json({"i": np.int64(3), "b": np.bool_(True), "t": (1, NAN)})
    assert out == {"i": 3, "b": True, "t": [1, None]}
    assert type(out["i"]) is int and type(out["b"]) is bool


def test_dataclass_and_model_nest():
    w = Winding(10, 1, 1e-6, 5.0, 0.1, 0.2, 0)
    req = Requirements(peak_power_w=1000, peak_torque_nm=10, base_speed_rpm=955, max_speed_rpm=2000,
                       wires=(RoundWire(diameter=1e-3, outer_diameter=1.1e-3),), phase_current_a=20)
    out = to_json({"w": w, "req": req})
    assert out["w"]["turns"] == 10 and out["req"]["wires"][0]["diameter"] == 1e-3
    json.dumps(out, allow_nan=False)


@pytest.mark.parametrize("nr,theta_deg,el", [(6, 30, 0), (6, 45, 90), (6, 60, 180), (6, 15, -90),
                                             (4, 45, 0), (4, 90, 180), (8, 22.5, 0)])
def test_electrical_angle(nr, theta_deg, el):
    assert electrical_deg_from_unaligned(math.radians(theta_deg), nr) == pytest.approx(el)


def _eval(ok):
    design = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
    if not ok:
        return Evaluation("bad", design, "MapFailed", "boom", 1.0, None, NAN, NAN, NAN, NAN, NAN, False,
                          None, None)
    a = np.array([0.1, 0.2])
    env = Envelope(a, a, a, a, a, np.array([0.0, NAN]), a, a, a)
    m = MapArrays(a, a, np.zeros((2, 2)), np.full((2, 2), NAN))
    return Evaluation("good", design, "ok", "", 1.0, Winding(10, 1, 1e-6, 5.0, 0.1, 0.2, 0), 1.1, 1.1,
                      1000.0, 2.0, 0.9, True, env, None, map=m)


def test_search_result_json_is_strict():
    req = Requirements(peak_power_w=1000, peak_torque_nm=10, base_speed_rpm=955, max_speed_rpm=2000)
    r = SearchResult(req, 2, {"x": 1}, 0, (_eval(True), _eval(False)), False)
    out = search_result_json(r)
    json.dumps(out, allow_nan=False)
    assert out["pareto_ids"] == ["good"] and len(out["evaluations"]) == 2
    env = out["evaluations"][0]["envelope"]
    assert len(env["theta_on_el"]) == 2 and len(env["efficiency"]) == 2
    assert env["theta_off_el"][1] is None
    assert out["evaluations"][1]["envelope"] is None
