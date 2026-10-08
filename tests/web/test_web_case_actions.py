import io
import math
import threading
import time

import numpy as np
import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from scipy.io import loadmat
from fastapi.testclient import TestClient

from conftest import make_8_6
from srmapp.case import CaseInputs
from srmapp.requirements import Requirements
from srmcore.model.design import Design, MeshSettings
from srmweb import api
from srmweb.api import create_app
from srmweb.config import Settings
from srmweb.jobs import JobRunner
from web_support import REQ, evaluation, search_body, store_search

SMALL = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)


def _inputs(preset="screening", **machine) -> dict:
    design = Design(machine=make_8_6(**machine), mesh=MeshSettings(preset=preset))
    return CaseInputs(requirements=Requirements(**SMALL), design=design).model_dump(mode="json")


def _wait(client, job_id, statuses, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.01)
    raise AssertionError(job)


@pytest.fixture
def gate():
    ev = threading.Event()
    yield ev
    ev.set()


@pytest.fixture
def make(tmp_path, gate):
    """A client whose jobs wait for `gate` and then fail, so they never touch a case's result."""
    clients = []

    def fail(kind, req, rep):
        gate.wait(10)
        raise RuntimeError("test job")

    def _make(queue_max=10):
        s = Settings("127.0.0.1", 8000, tmp_path / "a.db", tmp_path / "cache", 1, None, queue_max,
                     tmp_path / "nostatic")
        c = TestClient(create_app(s, runner_factory=lambda store, st: JobRunner(store, st, run_fn=fail)))
        c.__enter__()
        clients.append(c)
        return c

    yield _make
    gate.set()
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make):
    return make()


def _draft(client, inputs=None, **kw):
    case = client.post("/api/cases", json={"origin": "reference", "name": "8/6", "requirements": SMALL, **kw}).json()
    if inputs is not None:
        client.patch(f"/api/cases/{case['id']}", json={"inputs": inputs})
    return case["id"]


def _evaluated(client, preset="screening"):
    job_id = store_search(client, evaluation("c0"))
    case = client.post("/api/cases", json={"origin": "candidate", "job_id": job_id, "candidate_id": "c0"}).json()
    if preset != "screening":
        client.app.state.store.update_case(case["id"], inputs=_inputs(preset))
    return case["id"]


def _validate(client, inputs):
    r = client.post("/api/validate", json={"inputs": inputs})
    assert r.status_code == 200, r.text
    return r.json()


def test_validate_valid_design(client):
    assert _validate(client, _inputs()) == {"errors": [], "warnings": []}


def test_validate_extra_key_and_non_object(client):
    errors = _validate(client, _inputs() | {"bogus": 1})["errors"]
    assert [e["loc"] for e in errors] == [["bogus"]]
    assert _validate(client, "text")["errors"][0]["loc"] == []
    nested = _inputs()
    nested["design"]["machine"]["stack_length"] = -1
    assert _validate(client, nested)["errors"][0]["loc"] == ["design", "machine", "stack_length"]


def test_validate_geometry_rules(client):
    out = _validate(client, _inputs(stator_pole_arc=math.radians(40)))
    assert [e["loc"] for e in out["errors"]] == [["design", "machine", "rotor_pole_arc"]]
    assert out["errors"][0]["msg"].startswith("[pole_arc_sum] ")
    assert [w["loc"] for w in out["warnings"]] == [["design", "machine", "stator_pole_arc"]]


def test_validate_fixed_winding(client):
    out = _validate(client, _inputs() | {"winding": {"turns": 10, "paths": 3}})
    assert [e["loc"] for e in out["errors"]] == [["winding", "paths"]]
    assert _validate(client, _inputs() | {"winding": {"turns": 10}})["errors"] == []


def test_validate_stage1_reason_is_a_warning(client):
    heavy = _inputs()
    heavy["requirements"]["max_mass_kg"] = 0.01
    out = _validate(client, heavy)
    assert out["errors"] == [] and [w["loc"] for w in out["warnings"]] == [[]]
    assert out["warnings"][0]["msg"].startswith("stage 1: ")


def test_evaluate_submits_the_cases_inputs(client):
    case_id = _draft(client)
    r = client.post(f"/api/cases/{case_id}/evaluate", json={"grid": [5, 4]})
    assert r.status_code == 201, r.text
    request = client.app.state.store.get_job(r.json()["job_id"])["request"]
    assert request["case_id"] == case_id and request["grid"] == [5, 4]
    assert request["inputs"] == CaseInputs.model_validate(client.get(f"/api/cases/{case_id}").json()["inputs"]
                                                          ).model_dump(mode="json")


def test_evaluate_without_body(client):
    r = client.post(f"/api/cases/{_draft(client)}/evaluate")
    assert r.status_code == 201
    assert client.app.state.store.get_job(r.json()["job_id"])["request"]["grid"] is None


@pytest.mark.parametrize("grid", [[1, 4], [4, 201]])
def test_evaluate_grid_bounds(client, grid):
    assert client.post(f"/api/cases/{_draft(client)}/evaluate", json={"grid": grid}).status_code == 422


def test_evaluate_refuses_evaluated_case(client):
    assert client.post(f"/api/cases/{_evaluated(client)}/evaluate").status_code == 409


def test_evaluate_draft_with_errors_422(client):
    case_id = _draft(client, {"design": {"machine": {}}})
    r = client.post(f"/api/cases/{case_id}/evaluate")
    assert r.status_code == 422 and r.json()["errors"][0]["loc"][:1] == ["requirements"]
    assert client.get(f"/api/cases/{case_id}").json()["jobs"] == []


def test_evaluate_unknown_case_404(client):
    assert client.post("/api/cases/nope/evaluate").status_code == 404


def test_evaluate_full_queue_429(make):
    c = make(queue_max=0)
    assert c.post(f"/api/cases/{_draft(c)}/evaluate").status_code == 429


def test_edits_and_evaluate_refused_while_a_job_is_active(client):
    case_id = _draft(client)
    assert client.post(f"/api/cases/{case_id}/evaluate").status_code == 201
    r = client.post(f"/api/cases/{case_id}/evaluate")
    assert r.status_code == 409 and "still running" in r.json()["detail"]
    r = client.patch(f"/api/cases/{case_id}", json={"inputs": _inputs()})
    assert r.status_code == 409 and "still running" in r.json()["detail"]
    assert client.patch(f"/api/cases/{case_id}", json={"label": "ok"}).status_code == 200


def test_validate_refuses_stale_or_screening(client):
    assert client.post(f"/api/cases/{_draft(client)}/validate").json()["detail"] == "evaluate this case first"
    r = client.post(f"/api/cases/{_evaluated(client)}/validate")
    assert r.status_code == 409 and r.json()["detail"] == "EM validation needs a full map"
    assert client.post("/api/cases/nope/validate").status_code == 404


def test_validate_submits_for_a_full_evaluated_case(client):
    case_id = _evaluated(client, "full")
    r = client.post(f"/api/cases/{case_id}/validate")
    assert r.status_code == 201, r.text
    job = client.app.state.store.get_job(r.json()["job_id"])
    assert job["kind"] == "validate" and job["request"]["case_id"] == case_id
    assert job["request"]["inputs"]["design"]["mesh"]["preset"] == "full"
    assert client.post(f"/api/cases/{case_id}/validate").status_code == 409   # one at a time


def test_running_validate_cannot_be_cancelled_but_queued_one_can(client):
    first = client.post(f"/api/cases/{_evaluated(client, 'full')}/validate").json()["job_id"]
    second = client.post(f"/api/cases/{_evaluated(client, 'full')}/validate").json()["job_id"]
    _wait(client, first, {"running"})
    r = client.post(f"/api/jobs/{first}/cancel")
    assert r.status_code == 409 and r.json()["detail"] == "EM validation cannot be cancelled once started"
    assert client.post(f"/api/jobs/{second}/cancel").status_code == 202
    assert client.get(f"/api/jobs/{second}").json()["status"] == "cancelled"


def test_estimate_without_history_uses_the_budget(client):
    pytest.importorskip("ngsolve")
    case_id = _draft(client, _inputs("full"))
    assert client.get(f"/api/cases/{case_id}/estimate").json() == {"new_map": True, "seconds": 1560.0, "basis": "budget"}
    case_id = _draft(client, _inputs("screening"))
    assert client.get(f"/api/cases/{case_id}/estimate").json()["seconds"] == 228.0


def test_estimate_uses_recent_map_times(client):
    pytest.importorskip("ngsolve")
    store = client.app.state.store
    store.add_map_time("full", 100.0)
    store.add_map_time("full", 200.0)
    store.add_map_time("screening", 5.0)
    out = client.get(f"/api/cases/{_draft(client, _inputs('full'))}/estimate").json()
    assert out == {"new_map": True, "seconds": 150.0, "basis": "history"}


def test_estimate_of_a_cached_map(client, monkeypatch):
    seen = []
    monkeypatch.setattr(api, "map_cache_hit", lambda inputs, cache_dir: seen.append(cache_dir) or True)
    out = client.get(f"/api/cases/{_draft(client, _inputs())}/estimate").json()
    assert out == {"new_map": False, "seconds": None, "basis": None}
    assert seen == [client.app.state.settings.cache_dir]


def test_estimate_of_invalid_inputs_422(client):
    r = client.get(f"/api/cases/{_draft(client, {'design': {}})}/estimate")
    assert r.status_code == 422 and r.json()["errors"]
    bad = _inputs() | {"winding": {"turns": 10, "paths": 3}}
    r = client.get(f"/api/cases/{_draft(client, bad)}/estimate")
    assert [e["loc"] for e in r.json()["errors"]] == [["winding", "paths"]]
    assert client.get("/api/cases/nope/estimate").status_code == 404


def test_map_mat_round_trip(client):
    case_id = _evaluated(client)
    r = client.get(f"/api/cases/{case_id}/map.mat")
    assert r.status_code == 200 and r.headers["content-type"] == "application/octet-stream"
    assert "attachment" in r.headers["content-disposition"] and ".mat" in r.headers["content-disposition"]
    mat = loadmat(io.BytesIO(r.content))
    stored = client.get(f"/api/cases/{case_id}").json()["evaluation"]["map"]
    assert mat["psi"].shape == np.shape(stored["psi"])
    np.testing.assert_allclose(mat["angles"].ravel(), stored["angles"])
    np.testing.assert_allclose(mat["currents"].ravel(), stored["currents"])
    assert np.isnan(mat["torque"]).all()                 # the fixture's torque is NaN, stored as null
    assert mat["turns"].item() == 10 and mat["paths"].item() == 1


def test_map_mat_needs_an_evaluation(client):
    assert client.get(f"/api/cases/{_draft(client)}/map.mat").status_code == 404
    assert client.get("/api/cases/nope/map.mat").status_code == 404


def test_cancelled_search_result_is_still_served(client):
    store = client.app.state.store
    job_id = store.create_job("search", {"requirements": REQ})
    store.put_result(job_id, search_body(evaluation("c0")) | {"cancelled": True}, kind="search")
    store.set_status(job_id, "cancelled")
    r = client.get(f"/api/jobs/{job_id}/result")
    assert r.status_code == 200 and r.json()["cancelled"] is True


@pytest.mark.parametrize("name, message", [("nosuch", "unknown material 'nosuch'"), ("copper", "not a soft-magnetic")])
def test_bad_material_is_an_error_not_a_500(client, name, message):
    inputs = _inputs()
    inputs["design"]["machine"]["materials"]["stator"] = name
    out = _validate(client, inputs)
    assert [e["loc"] for e in out["errors"]] == [["design", "machine", "materials", "stator"]]
    assert message in out["errors"][0]["msg"]
    case_id = _draft(client, inputs)
    r = client.post(f"/api/cases/{case_id}/evaluate")
    assert r.status_code == 422 and r.json()["errors"][0]["loc"][-2:] == ["materials", "stator"]
    assert client.get(f"/api/cases/{case_id}/estimate").status_code == 422


def test_unexpected_map_request_failure_is_an_error(client, monkeypatch):
    def boom(inputs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(api, "map_request", boom)
    out = _validate(client, _inputs())
    assert out["errors"] == [{"loc": [], "msg": "RuntimeError: kaboom"}]
