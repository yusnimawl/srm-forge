import dataclasses
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
    env = Envelope(a, a, a, a, a, np.array([0.0, NAN]), a, a, a, None, a, a, a)
    m = MapArrays(a, a, np.zeros((2, 2)), np.full((2, 2), NAN))
    return Evaluation("good", design, "ok", "", 1.0, Winding(10, 1, 1e-6, 5.0, 0.1, 0.2, 0), 1.1, 1.1,
                      1000.0, 2.0, 0.9, True, env, None, map=m,
                      rated_continuous_kw_per_kg=1.0, rated_peak_kw_per_kg=2.0)


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


def _eval_with_waveforms(n=180, n_speeds=2):
    from srmapp.drive.envelope import Waveforms
    ev = _eval(True)
    env = ev.envelope
    z = np.zeros((n_speeds, n))
    wf = Waveforms(np.arange(n) * (2 * math.pi / 6) / n, z, z, z, z, z)
    return dataclasses.replace(ev, envelope=dataclasses.replace(env, waveforms=wf))


def test_evaluation_json_has_waveforms_with_electrical_angles():
    wf = evaluation_json(_eval_with_waveforms())["envelope"]["waveforms"]
    assert wf["theta_el"][0] == pytest.approx(-180.0)
    assert len(wf["theta_el"]) == 180 and all(len(row) == 180 for row in wf["line"])


def test_search_result_json_leaves_out_waveforms():
    req = Requirements(peak_power_w=1000, peak_torque_nm=10, base_speed_rpm=955, max_speed_rpm=2000)
    r = SearchResult(req, 1, {}, 0, (_eval_with_waveforms(),), False)
    env = search_result_json(r)["evaluations"][0]["envelope"]
    assert "waveforms" not in env and "power_factor" in env


def test_evaluation_out_parses_waveforms():
    from srmweb.results import EvaluationOut
    ev = _eval_with_waveforms()
    out = EvaluationOut.model_validate(evaluation_json(ev))
    assert out.envelope.waveforms.theta_el[0] == pytest.approx(-180.0)
    nan_pf = dataclasses.replace(ev.envelope, power_factor=np.array([0.5, NAN]))
    out = EvaluationOut.model_validate(evaluation_json(dataclasses.replace(ev, envelope=nan_pf)))
    assert out.envelope.power_factor[1] is None


def _rec_result(evals=(), **kw):
    req = Requirements(peak_power_w=1000, peak_torque_nm=10, base_speed_rpm=955, max_speed_rpm=2000)
    return SearchResult(req, len(evals), {}, 0, tuple(evals), False, **kw)


def test_search_result_json_recommendation_keys():
    from srmapp.pipeline import PEAK_BAND_NOTE
    r = _rec_result((_eval(True), _eval(False)), limit_rejected={"rotor_stress": 3},
                    dropped_pole_sets={"6/4": "not self-starting"}, stopped="three failures")
    out = search_result_json(r)
    json.dumps(out, allow_nan=False)
    assert out["recommended_ids"] == ["good"] and out["recommendation_id"] == "good"
    assert out["notes"] == [PEAK_BAND_NOTE]
    assert out["limit_rejected"] == {"rotor_stress": 3}
    assert out["dropped_pole_sets"] == {"6/4": "not self-starting"} and out["stopped"] == "three failures"


def test_search_result_json_without_recommendation():
    out = search_result_json(_rec_result((_eval(False),)))
    assert out["recommendation_id"] is None and out["recommended_ids"] == [] and out["notes"] == []
    assert out["limit_rejected"] == {} and out["dropped_pole_sets"] == {} and out["stopped"] == ""


def test_older_stored_results_load():
    from srmweb.results import EvaluationOut, SearchResultOut
    out = search_result_json(_rec_result((_eval(True),)))
    new_ev = ("limits", "nominal_continuous_kw_per_kg", "nominal_peak_kw_per_kg", "nominal_check")
    for e in out["evaluations"]:
        for k in new_ev:
            e.pop(k)
    for k in ("recommended_ids", "recommendation_id", "notes", "stopped", "limit_rejected", "dropped_pole_sets"):
        out.pop(k)
    got = SearchResultOut.model_validate(out)
    assert got.recommendation_id is None and got.recommended_ids == [] and got.evaluations[0].limits == []
    assert EvaluationOut.model_validate(out["evaluations"][0]).nominal_check is None


def test_new_evaluation_fields_nan_become_null():
    from srmapp.limits import Limit
    from srmweb.results import EvaluationOut
    ev = dataclasses.replace(_eval(True), limits=(Limit("rotor", "not_run", NAN, None, "n"),),
                             nominal_continuous_kw_per_kg=NAN, nominal_peak_kw_per_kg=NAN)
    ev = dataclasses.replace(ev, envelope=dataclasses.replace(ev.envelope, torque_single_pulse=np.array([1.0, NAN])))
    body = evaluation_json(ev)
    assert body["envelope"]["torque_single_pulse"] == [1.0, None]
    assert body["limits"][0]["value"] is None and body["nominal_peak_kw_per_kg"] is None
    out = EvaluationOut.model_validate(body)
    dumped = json.loads(out.model_dump_json())
    assert dumped["envelope"]["torque_single_pulse"] == [1.0, None] and dumped["nominal_continuous_kw_per_kg"] is None
