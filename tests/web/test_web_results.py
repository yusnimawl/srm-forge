import json

import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from srmweb.serialize import evaluation_json
from web_support import evaluation, make_client, store_search


@pytest.fixture
def client(tmp_path):
    with make_client(tmp_path) as c:
        yield c


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
