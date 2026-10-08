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
