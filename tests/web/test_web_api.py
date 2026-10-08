import threading
import time

import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from conftest import make_8_6

import srmcore
import srmweb
from srmweb.api import create_app
from srmweb.config import Settings
from srmweb.jobs import JobRunner

REQ = dict(peak_power_w=10000.0, peak_torque_nm=31.83, base_speed_rpm=3000.0,
           max_speed_rpm=6000.0)


def _body(**over):
    return {"kind": "search", "payload": {"requirements": REQ, **over}}


def _settings(tmp_path, queue_max=10):
    return Settings("127.0.0.1", 8000, tmp_path / "a.db", tmp_path / "cache", 1,
                    None, queue_max, tmp_path)


@pytest.fixture
def gate():
    ev = threading.Event()
    yield ev
    ev.set()


@pytest.fixture
def make(tmp_path):
    clients = []

    def _make(run_fn=lambda kind, req, rep: {"ok": 1}, **kw):
        app = create_app(_settings(tmp_path, **kw),
                         runner_factory=lambda store, s: JobRunner(store, s, run_fn=run_fn))
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        return c

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


def _wait(client, job_id, statuses, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in statuses:
            return j
        time.sleep(0.01)
    raise AssertionError(j)


def test_health(make):
    assert make().get("/api/health").json() == {
        "version": srmweb.__version__, "srmcore": srmcore.__version__}


def test_submit_and_poll_search(make):
    c = make()
    r = c.post("/api/jobs", json=_body())
    assert r.status_code == 201
    job_id = r.json()["id"]
    _wait(c, job_id, {"done"})
    assert c.get(f"/api/jobs/{job_id}/result").json() == {"ok": 1}
    assert [j["id"] for j in c.get("/api/jobs").json()] == [job_id]


def test_unknown_kind_422(make):
    assert make().post("/api/jobs", json={**_body(), "kind": "bogus"}).status_code == 422


def test_extra_field_422(make):
    assert make().post("/api/jobs", json={**_body(), "extra": 1}).status_code == 422
    assert make().post("/api/jobs", json=_body(bogus=1)).status_code == 422


@pytest.mark.parametrize("settings", [{"n_candidates": 2001}, {"shortlist": 0}])
def test_caps_422(make, settings):
    assert make().post("/api/jobs", json=_body(settings=settings)).status_code == 422


def test_inconsistent_requirements_422(make):
    bad = {**REQ, "peak_torque_nm": 50.0}
    r = make().post("/api/jobs", json={"kind": "search", "payload": {"requirements": bad}})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"][:3] == ["body", "payload", "requirements"]


@pytest.mark.parametrize("name", ["unobtainium", "copper"])
def test_unknown_material_422(make, name):
    assert make().post("/api/jobs", json=_body(settings={"stator": name})).status_code == 422


def test_queue_full_429(make, gate):
    c = make(lambda kind, req, rep: gate.wait(10) and {}, queue_max=1)
    first = c.post("/api/jobs", json=_body()).json()["id"]
    _wait(c, first, {"running"})
    assert c.post("/api/jobs", json=_body()).status_code == 201
    assert c.post("/api/jobs", json=_body()).status_code == 429


def test_resume_creates_new_job(make, tmp_path):
    c = make()
    old = c.post("/api/jobs", json=_body()).json()["id"]
    _wait(c, old, {"done"})
    assert c.post(f"/api/jobs/{old}/resume").status_code == 409
    c.app.state.store.set_status(old, "interrupted")
    r = c.post(f"/api/jobs/{old}/resume")
    assert r.status_code == 201
    new = r.json()["id"]
    assert new != old
    store = c.app.state.store
    assert store.get_job(new)["request"] == store.get_job(old)["request"]


def test_resume_queue_full_429(make, gate):
    c = make(lambda kind, req, rep: gate.wait(10) and {}, queue_max=1)
    first = c.post("/api/jobs", json=_body()).json()["id"]
    _wait(c, first, {"running"})
    c.post("/api/jobs", json=_body())
    c.app.state.store.set_status(first, "failed")
    assert c.post(f"/api/jobs/{first}/resume").status_code == 429


def test_delete_running_409(make, gate):
    c = make(lambda kind, req, rep: gate.wait(10) and {})
    j = c.post("/api/jobs", json=_body()).json()["id"]
    _wait(c, j, {"running"})
    assert c.delete(f"/api/jobs/{j}").status_code == 409


def test_running_job_reports_live_progress(make, gate):
    def fn(kind, req, rep):
        rep.progress(designs_done=3, designs_total=9)
        gate.wait(10)
        return {}

    c = make(fn)
    j = c.post("/api/jobs", json=_body()).json()["id"]
    end = time.time() + 10
    while c.get(f"/api/jobs/{j}").json()["progress"] is None or \
            c.get(f"/api/jobs/{j}").json()["progress"]["designs_done"] != 3:
        assert time.time() < end
        time.sleep(0.01)


def test_cancel_running_202(make, gate):
    def fn(kind, req, rep):
        gate.wait(10)
        return {"cancelled": rep.cancelled()}

    c = make(fn)
    j = c.post("/api/jobs", json=_body()).json()["id"]
    _wait(c, j, {"running"})
    assert c.post(f"/api/jobs/{j}/cancel").status_code == 202
    gate.set()
    _wait(c, j, {"cancelled"})


def test_delete_done_204(make):
    c = make()
    j = c.post("/api/jobs", json=_body()).json()["id"]
    _wait(c, j, {"done"})
    assert c.delete(f"/api/jobs/{j}").status_code == 204
    assert c.get(f"/api/jobs/{j}").status_code == 404


def test_cancel_done_409(make):
    c = make()
    j = c.post("/api/jobs", json=_body()).json()["id"]
    _wait(c, j, {"done"})
    assert c.post(f"/api/jobs/{j}/cancel").status_code == 409


def test_missing_job_404(make):
    c = make()
    for call in (c.get("/api/jobs/x"), c.get("/api/jobs/x/result"),
                 c.post("/api/jobs/x/cancel"), c.post("/api/jobs/x/resume"),
                 c.delete("/api/jobs/x")):
        assert call.status_code == 404


@pytest.mark.parametrize("grid", [[10**6, 10**6], [1, 4], [4, 201]])
def test_grid_out_of_bounds_422(make, grid):
    assert make().post("/api/jobs", json=_body(grid=grid)).status_code == 422


def test_job_out_flags(make, gate):
    c = make(lambda kind, req, rep: gate.wait(10) and {}, queue_max=3)
    j = c.post("/api/jobs", json=_body()).json()["id"]
    _wait(c, j, {"running"})
    out = c.get(f"/api/jobs/{j}").json()
    assert (out["active"], out["resumable"], out["case_id"]) == (True, False, None)
    c.app.state.store.set_status(j, "failed")
    out = c.get(f"/api/jobs/{j}").json()
    assert (out["active"], out["resumable"]) == (False, True)
    assert c.get("/api/jobs").json()[0]["resumable"] is True


def test_list_route_fills_case_id(make):
    c = make()
    store = c.app.state.store
    j = store.create_job("evaluate", {"case_id": "abc"})
    store.set_status(j, "failed")
    (out,) = c.get("/api/jobs").json()
    assert out["case_id"] == "abc" and out["kind"] == "evaluate"


@pytest.mark.parametrize("kind", ["evaluate", "validate"])
def test_case_kinds_not_submittable_here(make, kind):
    inputs = {"requirements": REQ, "design": {"machine": make_8_6().model_dump(mode="json")}}
    r = make().post("/api/jobs", json={"kind": kind, "payload": {"case_id": "c", "inputs": inputs}})
    assert r.status_code == 422
    assert r.json()["detail"] == "submit through /api/cases/{id}/evaluate or /validate"


def test_evaluate_payload_is_validated_first(make):
    r = make().post("/api/jobs", json={"kind": "evaluate", "payload": {"case_id": "c"}})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)


def test_resume_keeps_kind_and_request(make):
    c = make()
    store = c.app.state.store
    old = store.create_job("evaluate", {"case_id": "abc", "inputs": {}})
    store.set_status(old, "failed")
    new = c.post(f"/api/jobs/{old}/resume").json()["id"]
    got = store.get_job(new)
    assert got["kind"] == "evaluate" and got["request"] == store.get_job(old)["request"]
