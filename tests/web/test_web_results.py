import json

import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import dataclasses

from srmapp.curves import MapCurves
from srmapp.drive.envelope import Envelope
from srmapp.evaluate import Evaluation, MapArrays
from srmapp.sizing.winding import Winding
from srmapp.turns import ScanPoint
from srmcore.maps.checks import Check
from srmcore.maps.results import KeyNumbers
from srmcore.maps.validation import BudgetRow, EmValidation, UncertaintyBudget
from srmweb import results
from srmweb.serialize import evaluation_json
from web_support import evaluation, make_client, store_search


@pytest.fixture
def client(tmp_path):
    with make_client(tmp_path) as c:
        yield c


@pytest.mark.parametrize("engine, out", [
    (Evaluation, results.EvaluationOut), (Winding, results.WindingOut), (KeyNumbers, results.KeyNumbersOut),
    (Envelope, results.EnvelopeOut), (MapArrays, results.MapArraysOut), (MapCurves, results.MapCurvesOut),
    (ScanPoint, results.ScanPointOut), (EmValidation, results.ValidationOut), (Check, results.CheckOut),
    (UncertaintyBudget, results.BudgetOut), (BudgetRow, results.BudgetRowOut)])
def test_response_models_keep_every_engine_field(engine, out):
    """A field added to an engine result must be added to its response model, which drops unknown keys."""
    missing = {f.name for f in dataclasses.fields(engine)} - out.model_fields.keys()
    assert not missing, f"{out.__name__} lacks {sorted(missing)}"


def test_curves_reach_the_evaluation_json():
    out = evaluation_json(evaluation("c0"))
    json.dumps(out, allow_nan=False)
    assert out["curves"]["la_lu"] == [None, 1.0] and out["curves"]["inductance"] == [[1.0, 1.0]] * 2
    assert evaluation_json(evaluation("c1", ok=False))["curves"] is None


def test_search_result_route_keeps_nan_as_null(client):
    job_id = store_search(client, evaluation("c0"), evaluation("c1", ok=False))
    r = client.get(f"/api/jobs/{job_id}/result")
    assert r.status_code == 200
    body = r.json()
    ok, bad = body["evaluations"]
    assert body["pareto_ids"] == ["c0"] and body["dropped"] == {"x": 1}
    assert ok["envelope"]["theta_off"] == [0.0, None] and ok["map"]["torque"] == [[None, None]] * 2
    assert ok["j_rms"] is None and ok["curves"]["la_lu"] == [None, 1.0]
    assert ok["winding"]["turns"] == 10 and ok["design"]["machine"]["n_stator_poles"] == 8
    assert bad["status"] == "MapFailed" and bad["torque_ratio"] is None and bad["envelope"] is None


def test_result_route_serves_search_jobs_only(client):
    store = client.app.state.store
    job_id = store.create_job("evaluate", {"case_id": "x"})
    store.put_result(job_id, {"cancelled": True}, kind="evaluate")
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 404


def _rated_evaluation():
    from srmapp.cooling import CoolingSetup
    from srmapp.thermal import Rating, SpeedRating
    from srmcore.post.rotor_stress import RotorStress
    from srmcore.thermal.solve import HotSpot

    def sr(rpm, k):
        return SpeedRating(rpm, 5.0, 3.0 * k, 4.0 * k, HotSpot(140.0, "coil_A1+"), HotSpot(150.0, "end_winding"),
                           90.0, 95.0, 80.0, 85.0, 7, 60)

    stress = RotorStress("ok", "", 7200.0, 1e8, 2e8, 1.5, "pole_root", "von_mises", 5e8, 2.4, 9000.0)
    rating = Rating((sr(3000.0, 1.0), sr(6000.0, 1.0)), (sr(3000.0, 0.8), sr(6000.0, 0.8)), (), 155.0, "F",
                    CoolingSetup(), stress, {}, 1.0, 12, ("a note",), "0.7.0")
    return dataclasses.replace(evaluation("c0"), rating=rating, rated_continuous_kw_per_kg=0.7, srmcore_version="0.7.0")


def test_rating_summary_reaches_the_evaluation_json():
    out = results.EvaluationOut.model_validate(evaluation_json(_rated_evaluation()))
    json.dumps(out.model_dump(), allow_nan=False)
    r = out.rating
    assert r.limit_c == 155.0 and r.insulation_class == "F" and r.notes == ["a note"]
    assert r.stress_status == "ok" and r.stress_safety_factor == 2.4
    assert [s.rpm for s in r.speeds] == [3000.0, 6000.0]
    s = r.speeds[0]
    assert (s.nominal_continuous_nm, s.rated_continuous_nm, s.rated_peak_nm) == pytest.approx((3.0, 2.4, 3.2))
    assert (s.hot_spot_c, s.hot_spot_at) == (140.0, "coil_A1+")
    assert out.rated_continuous_kw_per_kg == 0.7 and out.srmcore_version == "0.7.0"


def test_unrated_and_older_evaluations_have_no_rating():
    assert evaluation_json(evaluation("c0"))["rating"] is None
    old = evaluation_json(evaluation("c0"))
    for k in ("rating", "rated_continuous_kw_per_kg", "rated_peak_kw_per_kg", "srmcore_version"):
        old.pop(k)
    out = results.EvaluationOut.model_validate(old)
    assert out.rating is None and out.srmcore_version is None
