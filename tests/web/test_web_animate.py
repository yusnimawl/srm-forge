import math
import time

import numpy as np
import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from srmapp import field as fieldmod
from srmapp.field import FieldFrame
from srmapp.sizing.generator import REFERENCE_TURNS
from srmweb.api import create_app
from srmweb.config import Settings
from srmweb.jobs import JobRunner
from srmweb.quick import QuickLane
from test_web_field_routes import _case
from test_web_frames import unpack

K = 40 / (2 * REFERENCE_TURNS)


@pytest.fixture
def client(tmp_path):
    s = Settings("127.0.0.1", 8000, tmp_path / "a.db", tmp_path / "cache", 1, None, 10, tmp_path / "nostatic")
    with TestClient(create_app(s, runner_factory=lambda store, st: JobRunner(
            store, st, quick=QuickLane(spawn=False)))) as c:
        yield c


def _frame(angle, coil):
    return FieldFrame(angle, coil, np.array([[0, 1, 2]]), np.ones(2, dtype=np.float32),
                      np.ones(3, dtype=np.float32), 0.5, 1.5, "converged", {"stator_pole": 1.0})


@pytest.fixture
def fake(monkeypatch):
    calls = []

    def frame(design, angle, coil_current, *, solver="ngsolve", cache_dir=None):
        calls.append((angle, coil_current, cache_dir))
        return _frame(angle, coil_current)

    monkeypatch.setattr(fieldmod, "field_frame", frame)
    monkeypatch.setattr(fieldmod, "cached_frame", lambda design, angle, coil, **kw: _frame(angle, coil))
    return calls


def _wait(client, job_id, statuses=("done", "failed", "cancelled")):
    end = time.time() + 10
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.01)
    raise AssertionError(job)


def _animate(client, cid, frames=12, current=3.0):
    r = client.post(f"/api/cases/{cid}/animate", json={"current_a": current, "frames": frames})
    assert r.status_code == 201, r.text
    return r.json()["job_id"]


def test_animate_runs_every_frame(client, fake):
    cid = _case(client)
    job = _wait(client, _animate(client, cid))
    assert job["status"] == "done" and job["progress"]["points_total"] == 12
    result = client.app.state.store.get_result(job["id"])
    assert len(result["angles"]) == 12 and len(fake) == 12
    assert result["angles"][0] == pytest.approx(math.pi / 6) and result["angles"][-1] == pytest.approx(math.pi / 3)
    assert result["psi"] == pytest.approx([0.5 * K] * 12) and result["probes"]["stator_pole"] == [1.0] * 12
    assert fake[0][1] == pytest.approx(3.0 * K) and fake[0][2] is not None


def test_frames_route_packs_every_frame(client, fake):
    job = _wait(client, _animate(client, _case(client)))
    r = client.get(f"/api/jobs/{job['id']}/frames")
    assert r.status_code == 200 and r.headers["content-type"] == "application/octet-stream"
    header, _, arrays = unpack(r.content)
    assert header["meta"]["case_id"] and len(header["meta"]["angles"]) == 12
    assert set(arrays) == {f"{p}.{n}" for p in ("band", "b", "a") for n in range(12)}


def test_frames_gone_after_cache_clear(client, fake, monkeypatch):
    job = _wait(client, _animate(client, _case(client)))
    assert client.get(f"/api/jobs/{job['id']}/frames").status_code == 200
    monkeypatch.setattr(fieldmod, "cached_frame", lambda *a, **k: None)
    assert client.delete("/api/settings/cache").status_code == 204
    r = client.get(f"/api/jobs/{job['id']}/frames")
    assert r.status_code == 410 and "animate again" in r.json()["detail"]


def test_frames_404_for_other_jobs(client, fake):
    assert client.get("/api/jobs/nope/frames").status_code == 404
    other = client.app.state.store.create_job("search", {})
    client.app.state.store.put_result(other, {}, kind="search")
    assert client.get(f"/api/jobs/{other}/frames").status_code == 404


def test_bad_requests(client, fake):
    cid = _case(client)
    assert client.post(f"/api/cases/{cid}/animate", json={"current_a": 3, "frames": 8}).status_code == 422
    assert client.post(f"/api/cases/{cid}/animate", json={"current_a": 25}).status_code == 422
    assert client.post(f"/api/cases/{_case(client, stale=True)}/animate",
                       json={"current_a": 3}).status_code == 409


def test_cancel_and_resume(client, monkeypatch):
    import threading
    gate, started = threading.Event(), threading.Event()
    seen = []

    def frame(design, angle, coil_current, *, solver="ngsolve", cache_dir=None):
        seen.append(angle)
        started.set()
        gate.wait(5)
        return _frame(angle, coil_current)

    monkeypatch.setattr(fieldmod, "field_frame", frame)
    cid = _case(client)
    job_id = _animate(client, cid)
    assert started.wait(5)
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 202
    gate.set()
    job = _wait(client, job_id)
    assert job["status"] == "cancelled" and len(seen) == 1
    assert client.get(f"/api/jobs/{job_id}/frames").status_code == 404
    again = client.post(f"/api/jobs/{job_id}/resume")
    assert again.status_code == 201
    assert _wait(client, again.json()["id"])["status"] == "done"
