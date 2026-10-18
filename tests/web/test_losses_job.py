import json
import time

import numpy as np
import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

import srmapp
from srmapp import losses as lossmod
from srmapp.case import CaseInputs
from srmapp.losses import LossResult, OperatingLoss, RegionLoss
from srmweb import jobs
from srmweb.api import create_app
from srmweb.config import Settings
from srmweb.jobs import JobContext, JobRunner, Reporter
from srmweb.quick import QuickLane
from srmweb.schemas import LossesRequest
from srmweb.serialize import evaluation_json, to_json
from srmweb.store import Store
from web_support import REQ, evaluation, store_search

NAN = float("nan")


def _result(key="abc"):
    iron = {"stator_pole": RegionLoss(1.0, 0.5, 0.25)}
    reached = OperatingLoss(1000.0, 5.0, True, 500.0, 20.0, None, iron, 1.75, 0.9, 0.12, False,
                            0.1, 0.5, 10.0, key)
    missed = OperatingLoss(2000.0, 9.0, False, NAN, NAN, None, {}, NAN, NAN, NAN, False, NAN, NAN, NAN, "")
    return LossResult((reached, missed), (1000.0, 2000.0), (0.5, 1.0), 120.0, 60, 0.02, srmapp.__version__, ("note",))


@pytest.fixture
def calls(monkeypatch):
    calls = []

    def efficiency_map(inputs, evaluation, *, n_speeds, n_torques, workers, cache_dir, progress, cancel, **kw):
        calls.append((n_speeds, n_torques, evaluation.winding.turns, evaluation.j_limit))
        for step in ("strokes", "fields", "losses"):
            progress(step, 1, 2)
            progress(step, 2, 2)
        return _result()

    monkeypatch.setattr(jobs, "efficiency_map", efficiency_map)
    monkeypatch.setattr("srmweb.api.check_loss_data", lambda design: None)
    return calls


@pytest.fixture
def client(tmp_path):
    s = Settings("127.0.0.1", 8000, tmp_path / "a.db", tmp_path / "cache", 1, None, 10, tmp_path / "nostatic")
    with TestClient(create_app(s, runner_factory=lambda store, st: JobRunner(
            store, st, quick=QuickLane(spawn=False)))) as c:
        yield c


def _case(client):
    job_id = store_search(client, evaluation("c1"))
    return client.post("/api/cases", json={"origin": "candidate", "job_id": job_id,
                                           "candidate_id": "c1"}).json()["id"]


def _wait(client, job_id):
    end = time.time() + 10
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if not job["active"]:
            return job
        time.sleep(0.02)
    raise AssertionError(job)


def test_losses_job_steps(tmp_path, monkeypatch):
    store = Store(tmp_path / "a.db")
    ev = evaluation("c1")
    inputs = CaseInputs(requirements=REQ, design=ev.design)
    case = store.create_case(origin="reference", inputs=inputs.model_dump(mode="json"), label="x", stale=False)
    with store._db() as con:
        con.execute("INSERT INTO results (job_id, case_id, kind, body) VALUES (NULL, ?, 'evaluate', ?)",
                    (case, json.dumps(evaluation_json(ev))))
    reporter = Reporter(store, "j", "losses")
    seen = [reporter.snapshot()[1]["step"]]

    def efficiency_map(inputs, evaluation, *, progress, **kw):
        for step in ("strokes", "fields", "losses"):
            progress(step, 1, 2)
            seen.append(reporter.snapshot()[1]["step"])
        return _result()

    monkeypatch.setattr(jobs, "efficiency_map", efficiency_map)
    settings = Settings("127.0.0.1", 8000, tmp_path / "a.db", tmp_path, 1, None, 1, tmp_path)
    out = jobs.run_losses_job(LossesRequest(case_id=case, inputs=inputs), reporter, JobContext(settings, QuickLane(spawn=False)))
    assert seen == ["queued", "strokes", "fields", "losses"]
    assert reporter.snapshot()[1]["steps"] == ["queued", "strokes", "fields", "losses", "saved"]
    assert out["points"][1]["power_w"] is None and out["srmapp_version"] == srmapp.__version__


def test_losses_route_end_to_end(client, calls):
    case = _case(client)
    r = client.post(f"/api/cases/{case}/losses", json={"n_speeds": 3, "n_torques": 2})
    assert r.status_code == 201, r.text
    job = _wait(client, r.json()["job_id"])
    assert job["status"] == "done" and job["progress"]["step"] == "saved" and job["lane"] == "main"
    assert calls == [(3, 2, 10, calls[0][3])]
    out = client.get(f"/api/cases/{case}/losses")
    assert out.status_code == 200
    body = out.json()
    assert body["points"][1]["power_w"] is None and body["points"][0]["iron"]["stator_pole"]["excess"] == 0.25
    assert body["winding_temperature_c"] == 120.0 and body["notes"] == ["note"]


def test_losses_absent_is_404(client):
    assert client.get(f"/api/cases/{_case(client)}/losses").status_code == 404


def test_losses_refused_without_loss_data(client):
    case = _case(client)
    r = client.post(f"/api/cases/{case}/losses", json={})
    assert r.status_code == 422 and "M19" in json.dumps(r.json())
    assert [j["kind"] for j in client.get("/api/jobs").json()] == ["search"]


def test_losses_needs_evaluated_case(client, calls):
    draft = client.post("/api/cases", json={"origin": "reference", "name": "8/6", "requirements": REQ}).json()["id"]
    assert client.post(f"/api/cases/{draft}/losses", json={}).status_code == 409
    assert client.post("/api/cases/nope/losses", json={}).status_code == 404


def test_old_evaluation_loads(client):
    job_id = store_search(client, evaluation("c1"))
    store = client.app.state.store
    body = store.get_result(job_id)
    assert body["evaluations"][0]["srmapp_version"] == srmapp.__version__
    del body["evaluations"][0]["srmapp_version"]
    with store._db() as con:
        con.execute("UPDATE results SET body = ? WHERE job_id = ?", (json.dumps(body), job_id))
    case = client.post("/api/cases", json={"origin": "candidate", "job_id": job_id, "candidate_id": "c1"}).json()
    assert case["evaluation"]["srmapp_version"] is None


def _store_losses(client, case, result):
    client.app.state.store.put_result(None, to_json(result), kind="losses", case_id=case)


def test_cache_clear_counts_strokes(client, tmp_path):
    case = _case(client)
    _store_losses(client, case, _result("abc"))
    strokes = tmp_path / "cache" / "strokes"
    strokes.mkdir(parents=True)
    (strokes / "abc.npz").write_bytes(b"123")
    (strokes / "abc.1.tmp.npz").write_bytes(b"9999")
    assert client.get("/api/settings/cache").json()["files"] == 1
    assert client.get("/api/settings/cache").json()["bytes"] == 3
    assert client.delete("/api/settings/cache").status_code == 204
    assert not (strokes / "abc.npz").exists()
    assert client.get(f"/api/cases/{case}/losses/b", params={"point": 0, "x": 0.03, "y": 0.0}).status_code == 410


def test_b_route(client, tmp_path, monkeypatch):
    case = _case(client)
    _store_losses(client, case, _result("abc"))
    (tmp_path / "cache" / "strokes").mkdir(parents=True)
    (tmp_path / "cache" / "strokes" / "abc.npz").write_bytes(b"x")
    seen = []

    def b_waveform(design, key, n_angles, rpm, x, y, *, cache_dir):
        seen.append((key, n_angles, rpm, x, y))
        return dict(t=np.array([0.0, 1e-3]), b_r=np.array([0.5, NAN]), b_t=np.array([0.0, 0.1]),
                    region="stator_pole", side="stator")

    monkeypatch.setattr(lossmod, "b_waveform", b_waveform)
    r = client.get(f"/api/cases/{case}/losses/b", params={"point": 0, "x": 0.03, "y": 0.01})
    assert r.status_code == 200, r.text
    assert r.json() == dict(t=[0.0, 1e-3], b_r=[0.5, None], b_t=[0.0, 0.1], region="stator_pole", side="stator")
    assert seen == [("abc", 60, 1000.0, 0.03, 0.01)]
    assert client.get(f"/api/cases/{case}/losses/b", params={"point": 1, "x": 0, "y": 0}).status_code == 404
    assert client.get(f"/api/cases/{case}/losses/b", params={"point": 7, "x": 0, "y": 0}).status_code == 404


def test_locate_prefers_containment_then_nearest_centroid():
    tri = np.array([[[0, 0], [10, 0], [0, 10]], [[4, 4], [5, 4], [4, 5]]], dtype=float)
    assert lossmod.locate(tri, np.array([1.0, 1.0])) == (0, True)
    assert lossmod.locate(tri, np.array([4.1, 4.1]))[1]            # inside both
    assert lossmod.locate(tri, np.array([20.0, 20.0])) == (1, False)   # outside both: nearest centroid


def test_losses_estimate(client):
    case = _case(client)
    e = client.get(f"/api/cases/{case}/losses/estimate").json()
    assert e["solves"] == 6 * 5 * 60 and e["basis"] == "budget"
    assert e["seconds"] == pytest.approx(e["solves"] * 228.0 / (40 * 8))
    client.app.state.store.add_map_time("screening", 160.0)
    e = client.get(f"/api/cases/{case}/losses/estimate", params={"n_speeds": 2, "n_torques": 2}).json()
    assert e["basis"] == "history" and e["seconds"] == pytest.approx(2 * 2 * 60 * 160.0 / 320)
