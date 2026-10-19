import time
from pathlib import Path

import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from srmweb.api import create_app
from srmweb.config import Settings
from srmweb.jobs import JobRunner
from web_support import analytic_evaluation, store_search, unpack

CRASH = str(Path(__file__).parents[1] / "sil" / "controllers" / "crash")
SHORT = {"duration": 0.005}


def _client(tmp_path, host="127.0.0.1", token=None):
    s = Settings(host, 8000, tmp_path / "a.db", tmp_path / "cache", 1, token, 10, tmp_path / "nostatic")
    return TestClient(create_app(s, runner_factory=lambda store, st: JobRunner(store, st)))


@pytest.fixture
def client(tmp_path):
    with _client(tmp_path) as c:
        yield c


def _case(client, evaluated=True):
    job_id = store_search(client, analytic_evaluation("c1"))
    cid = client.post("/api/cases", json={"origin": "candidate", "job_id": job_id, "candidate_id": "c1"}).json()["id"]
    if not evaluated:
        with client.app.state.store._db() as con:
            con.execute("UPDATE cases SET stale = 1 WHERE id = ?", (cid,))
    return cid


def _wait(client, job_id):
    end = time.time() + 120
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError(job)


def _control(client, cid, controller="hysteresis", scenario=SHORT):
    return client.post(f"/api/cases/{cid}/control", json={"controller": controller, "scenario": scenario})


def test_control_reference_runs(client):
    cid = _case(client)
    r = _control(client, cid)
    assert r.status_code == 201, r.text
    job = _wait(client, r.json()["job_id"])
    assert job["status"] == "done", job
    blob = client.get(f"/api/jobs/{job['id']}/control?n_px=500")
    assert blob.status_code == 200
    header, _, arrays = unpack(blob.content)
    assert 0 < len(arrays["y.i.0"]) <= 1000 and len(arrays["t.i.0"]) == len(arrays["y.i.0"])
    assert header["meta"]["n_phases"] == 4 and "mean_torque" in header["meta"]["summary"]


def test_control_needs_evaluated_case(client):
    assert _control(client, _case(client, evaluated=False)).status_code == 409


def test_custom_folder_refused_off_loopback(tmp_path):
    with _client(tmp_path, "0.0.0.0", "t0k") as c:
        c.post("/api/login", json={"token": "t0k"})
        assert _control(c, _case(c), CRASH).status_code == 403


def test_custom_folder_invalid(client):
    cid = _case(client)
    assert _control(client, cid, str(Path(CRASH).parent / "missing")).status_code == 422
    assert _control(client, cid, str(Path(CRASH) / "crash.c")).status_code == 422


def test_scenario_too_long(client):
    assert _control(client, _case(client), scenario={"duration": 1000.0, "dt": 1e-6}).status_code == 422


def test_crashing_controller_fails_job(client):
    job = _wait(client, _control(client, _case(client), CRASH).json()["job_id"])
    assert job["status"] == "failed" and "crashed" in job["error"]
    assert client.get("/api/health").status_code == 200


def test_header_download(client):
    r = client.get(f"/api/cases/{_case(client)}/control/header")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert "#define SRM_N_PHASES 4" in r.text


def test_target_check_route(client):
    cid = _case(client)
    r = client.post("/api/control/target-check", json={"controller": "hysteresis", "case_id": cid})
    assert r.status_code == 200 and r.json()["ok"], r.text
    assert client.post("/api/control/target-check", json={"controller": CRASH, "case_id": cid}).status_code == 200


def test_controllers_list(client):
    r = client.get("/api/control/controllers").json()
    assert {c["name"] for c in r} == {"hysteresis", "pwm_current", "tsf"}
    hyst = next(c for c in r if c["name"] == "hysteresis")
    assert {"name": "band", "unit": "A", "default": "0.05 * SRM_I_MAX_A"} in hyst["params"]


def test_cache_counts_and_clears_sil_files(client):
    job = _wait(client, _control(client, _case(client)).json()["job_id"])
    assert job["status"] == "done"
    assert client.get("/api/settings/cache").json()["files"] >= 2   # the run and the compiled library
    assert client.delete("/api/settings/cache").status_code == 204
    assert client.get("/api/settings/cache").json()["files"] == 0
    assert client.get(f"/api/jobs/{job['id']}/control").status_code == 410


def test_resume_custom_refused_off_loopback(tmp_path):
    with _client(tmp_path, "0.0.0.0", "t0k") as c:
        c.post("/api/login", json={"token": "t0k"})
        cid = _case(c)
        req = {"case_id": cid, "motor": {"angles": [0.0], "currents": [1.0], "psi": [[0.0]], "torque": [[0.0]],
               "resistance": 0.5, "n_phases": 4, "n_rotor_poles": 6, "bus_voltage": 100.0},
               "controller": CRASH, "scenario": {}}
        store = c.app.state.store
        job_id = store.create_job("control", req)
        store.set_status(job_id, "interrupted")
        assert c.post(f"/api/jobs/{job_id}/resume").status_code == 403


def test_runner_refuses_custom_off_loopback(tmp_path):
    from srmweb.jobs import JobContext, Reporter, run_control_job
    from srmweb.schemas import ControlRequest
    s = Settings("0.0.0.0", 8000, tmp_path / "a.db", tmp_path / "cache", 1, "t", 10, tmp_path / "nostatic")
    req = ControlRequest.model_validate({"case_id": "x", "motor": {
        "angles": [0.0], "currents": [1.0], "psi": [[0.0]], "torque": [[0.0]], "resistance": 0.5,
        "n_phases": 4, "n_rotor_poles": 6, "bus_voltage": 100.0}, "controller": CRASH, "scenario": {}})
    with pytest.raises(ValueError, match="loopback"):
        run_control_job(req, None, JobContext(s, None))
    assert not (tmp_path / "cache").exists()


def test_custom_folder_must_be_absolute(client):
    assert _control(client, _case(client), "controllers/crash").status_code == 422


def test_target_check_refused_off_loopback(tmp_path):
    with _client(tmp_path, "0.0.0.0", "t0k") as c:
        c.post("/api/login", json={"token": "t0k"})
        r = c.post("/api/control/target-check", json={"controller": CRASH, "case_id": _case(c)})
        assert r.status_code == 403
