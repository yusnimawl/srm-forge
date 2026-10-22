"""srmweb HIL routes on the fake rig: loopback rule, session lifecycle, live parameters, capture and comparison,
the flash job and its exclusion with the session, and the cache."""

import json
import threading
import time

import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sil_fixtures import analytic_motor

from srmsil.hil.fake import FakeRig
from srmweb.api import create_app
from srmweb.config import Settings
from srmweb.hil import HilManager
from srmweb.jobs import JobRunner
from web_support import analytic_evaluation, store_search

SCENARIO = {"speed_rpm": 1000.0, "duration": 0.02, "command_value": 1.0, "bus_voltage": 48.0}
OPEN = {"controller": "hysteresis", "scenario": SCENARIO, "modes": {}}


def _settings(tmp_path, host="127.0.0.1", token=None):
    return Settings(host, 8000, tmp_path / "a.db", tmp_path / "cache", 1, token, 10, tmp_path / "nostatic")


@pytest.fixture
def rig(tmp_path):
    """Keyword arguments of the next FakeRig the app opens."""
    return {"cache_dir": tmp_path / "rig"}


def _client(tmp_path, rig, host="127.0.0.1", token=None):
    return TestClient(create_app(_settings(tmp_path, host, token), runner_factory=lambda store, st: JobRunner(store, st),
                                 hil_transports=lambda: FakeRig(analytic_motor(), **rig)))


@pytest.fixture
def client(tmp_path, rig):
    with _client(tmp_path, rig) as c:
        yield c


def _case(client):
    job_id = store_search(client, analytic_evaluation("c1"))
    return client.post("/api/cases", json={"origin": "candidate", "job_id": job_id, "candidate_id": "c1"}).json()["id"]


def _open(client, cid, body=OPEN):
    return client.post("/api/hil/session", json={"case_id": cid, **body})


def _wait(client, job_id):
    end = time.time() + 60
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError(job)


ROUTES = [("post", "/api/cases/{cid}/hil/flash", OPEN), ("post", "/api/hil/session", None),
          ("delete", "/api/hil/session", None), ("get", "/api/hil/session/events", None),
          ("post", "/api/hil/session/param", {"name": "band", "value": 1.0}),
          ("post", "/api/hil/session/command", {"mode": "torque", "value": 1.0}),
          ("post", "/api/hil/session/start", None), ("post", "/api/hil/session/stop", None),
          ("post", "/api/hil/session/capture", {"n_steps": 1000}),
          ("get", "/api/hil/captures/abc?n_px=500", None), ("get", "/api/hil/captures/abc/compare", None)]


def test_every_route_refused_off_loopback(tmp_path, rig):
    with _client(tmp_path, rig, "0.0.0.0", "t0k") as c:
        c.post("/api/login", json={"token": "t0k"})
        cid = _case(c)
        for method, path, body in ROUTES:
            if path == "/api/hil/session" and method == "post":
                body = {"case_id": cid, **OPEN}
            kw = {"json": body} if body is not None else {}
            r = c.request(method.upper(), path.format(cid=cid), **kw)
            assert r.status_code == 403, (method, path, r.text)
            assert "loopback" in r.json()["detail"]


def test_manager_refuses_off_loopback(tmp_path):
    m = HilManager(_settings(tmp_path, "0.0.0.0", "t"), lambda: FakeRig(analytic_motor()), lambda: False)
    for call in (m.close, m.start, m.stop, lambda: m.param("band", 1.0), lambda: m.capture(100),
                 lambda: m.compare("0" * 32, lambda *a: analytic_motor())):
        with pytest.raises(HTTPException) as e:
            call()
        assert e.value.status_code == 403


def test_open_close_and_second_open(client):
    cid = _case(client)
    r = _open(client, cid)
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["case_id"] == cid and s["controller"] == "hysteresis" and not s["running"]
    assert s["modes"] == {"current_sense": "ad7606", "position": "encoder", "dac": "mcp4922x2"}
    assert s["emulator_hash"] == s["controller_hash"] == 0x5EED0001
    again = _open(client, cid)
    assert again.status_code == 409 and "open" in again.json()["detail"]
    assert client.delete("/api/hil/session").status_code == 204
    assert client.post("/api/hil/session/start").status_code == 409
    assert _open(client, cid).status_code == 201


def test_open_needs_evaluated_case(client):
    assert client.post("/api/hil/session", json={"case_id": "nope", **OPEN}).status_code == 404


def test_mode_mismatch_409(client, rig):
    cid = _case(client)
    rig["mode_mismatch"] = True
    r = _open(client, cid)
    assert r.status_code == 409 and "board modes differ" in r.json()["detail"]
    rig["mode_mismatch"] = False
    assert _open(client, cid).status_code == 201


def test_scenario_rule_409(client):
    r = _open(client, _case(client), {**OPEN, "scenario": {**SCENARIO, "adc": {"noise": 1.0}}})
    assert r.status_code == 409 and "does not emulate adc.noise" in r.json()["detail"]
    r = _open(client, _case(client), {**OPEN, "scenario": {**SCENARIO, "isr_hz": 10000.0}})
    assert r.status_code == 409 and "k odd" in r.json()["detail"]


def test_param_status_messages(client):
    _open(client, _case(client))
    assert client.post("/api/hil/session/param", json={"name": "band", "value": 0.5}).json() == {"status": 0}
    assert client.post("/api/hil/session/param", json={"name": "nope", "value": 1.0}).json() == {
        "status": -1, "message": "unknown parameter"}
    assert client.post("/api/hil/session/start").json()["running"]
    r = client.post("/api/hil/session/param", json={"name": "resolver_pole_pairs", "value": 2.0})
    assert r.status_code == 200
    assert r.json() == {"status": -2, "message": "not changeable while running"}
    assert client.post("/api/hil/session/command", json={"mode": "torque", "value": 1.0}).status_code == 200
    assert not client.post("/api/hil/session/stop").json()["running"]


def test_events_stream_live_stats(client):
    _open(client, _case(client))
    client.post("/api/hil/session/start")
    # TestClient delivers the body only once the stream ends, so close the session after a second of live windows
    threading.Timer(1.0, client.app.state.hil.close).start()
    got = []
    with client.stream("GET", "/api/hil/session/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        name = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                got.append((name, json.loads(line[6:])))
    assert got[-1] == ("end", {})
    live = [d for n, d in got if n == "live"]
    assert 5 <= len(live) <= 40                       # sent on change, polled at 20 Hz
    last = live[-1]
    assert last["session"]["running"]
    assert last["emu"]["latency_us"] == 8.0 and last["ctrl"]["isr_mean_us"] == 3.0
    assert client.get("/api/hil/session/events").status_code == 409


def test_capture_then_compare_passes(client):
    _open(client, _case(client))
    client.post("/api/hil/session/start")
    r = client.post("/api/hil/session/capture", json={"n_steps": 2000})
    assert r.status_code == 201, r.text
    cap = r.json()
    assert cap["valid"], cap["reason"]
    blob = client.get(f"/api/hil/captures/{cap['capture_id']}?n_px=500")
    assert blob.status_code == 200
    c = client.get(f"/api/hil/captures/{cap['capture_id']}/compare")
    assert c.status_code == 200, c.text
    out = c.json()
    assert out["passed"], out
    assert out["clock_measured"] and out["clock_ratio"] == pytest.approx(1.0)
    from web_support import unpack
    header, _, arrays = unpack(client.get(f"/api/hil/captures/{cap['capture_id']}?n_px=500").content)
    assert header["meta"]["compared"] and header["meta"]["hil"]["valid"]
    assert "y.i.0" in arrays and "y.sil.i.0" in arrays
    assert arrays["t.sil.i.0"][0] >= arrays["t.i.0"][0] - 1e-9


def test_capture_gap_does_not_pass(client, rig):
    rig["drop_after"] = 3
    _open(client, _case(client))
    client.post("/api/hil/session/start")
    cap = client.post("/api/hil/session/capture", json={"n_steps": 2000}).json()
    assert not cap["valid"] and "sequence gap" in cap["reason"]
    out = client.get(f"/api/hil/captures/{cap['capture_id']}/compare").json()
    assert not out["passed"] and "sequence gap" in out["reason"]


def test_unknown_capture_404(client):
    assert client.get("/api/hil/captures/0123abcd").status_code == 404
    assert client.get("/api/hil/captures/0123abcd/compare").status_code == 404
    assert client.get("/api/hil/captures/..%2Fx").status_code in (404, 422)


def test_cache_counts_and_clears_captures(client):
    _open(client, _case(client))
    client.post("/api/hil/session/start")
    cap = client.post("/api/hil/session/capture", json={"n_steps": 1000}).json()
    assert client.get("/api/settings/cache").json()["files"] >= 2   # the capture's npz and json
    r = client.delete("/api/settings/cache")
    assert r.status_code == 409 and "HIL session" in r.json()["detail"]
    client.delete("/api/hil/session")
    assert client.delete("/api/settings/cache").status_code == 204
    assert client.get("/api/settings/cache").json()["files"] == 0
    assert client.get(f"/api/hil/captures/{cap['capture_id']}").status_code == 404


def test_flash_and_session_exclude_each_other(client):
    cid = _case(client)
    _open(client, cid)
    r = client.post(f"/api/cases/{cid}/hil/flash", json=OPEN)
    assert r.status_code == 409 and "session" in r.json()["detail"]
    client.delete("/api/hil/session")
    store = client.app.state.store
    store.create_job("hil_flash", {"case_id": cid})      # queued, never picked up by this runner
    r = _open(client, cid)
    assert r.status_code == 409 and "Flash" in r.json()["detail"]


def test_flash_job_steps(client, monkeypatch):
    from srmsil.hil.build import BuildResult
    calls = []

    def fake_build(controller, m, scenario, modes, *, cache_dir, upload=True, log=None):
        calls.append(upload)
        return BuildResult(True, f"log upload={upload}", 0x1234)

    monkeypatch.setattr("srmweb.jobs.build_and_flash", fake_build)
    cid = _case(client)
    r = client.post(f"/api/cases/{cid}/hil/flash", json=OPEN)
    assert r.status_code == 201, r.text
    job = _wait(client, r.json()["job_id"])
    assert job["status"] == "done", job
    assert job["kind"] == "hil_flash" and job["lane"] == "main"
    assert job["progress"]["steps"] == ["queued", "build", "flash", "saved"] and job["progress"]["step"] == "saved"
    assert calls == [False, True]
    result = client.app.state.store.get_result(job["id"])
    assert result["firmware_hash"] == 0x1234 and "upload=True" in result["log"]


def test_flash_job_failure_carries_log(client, monkeypatch):
    from srmsil.hil.build import BuildResult
    monkeypatch.setattr("srmweb.jobs.build_and_flash",
                        lambda *a, upload=True, **k: BuildResult(False, "error: undefined ctrl_isr", 0))
    cid = _case(client)
    job = _wait(client, client.post(f"/api/cases/{cid}/hil/flash", json=OPEN).json()["job_id"])
    assert job["status"] == "failed" and "undefined ctrl_isr" in job["error"]


def test_flash_isr_rule_422(client):
    cid = _case(client)
    r = client.post(f"/api/cases/{cid}/hil/flash", json={**OPEN, "scenario": {**SCENARIO, "isr_hz": 10000.0}})
    assert r.status_code == 422


def test_flash_job_refused_off_loopback(tmp_path):
    from srmweb.hil import HIL_REFUSED
    from srmweb.jobs import JobContext, run_hil_flash_job
    from srmweb.schemas import HilFlashRequest
    m = analytic_motor()
    req = HilFlashRequest.model_validate({"case_id": "x", "motor": {
        "angles": m.angles.tolist(), "currents": m.currents.tolist(), "psi": m.psi.tolist(),
        "torque": m.torque.tolist(), "resistance": 0.5, "n_phases": 4, "n_rotor_poles": 6, "bus_voltage": 48.0},
        "controller": "hysteresis", "scenario": {}, "modes": {}})
    with pytest.raises(ValueError, match=HIL_REFUSED):
        run_hil_flash_job(req, None, JobContext(_settings(tmp_path, "0.0.0.0", "t"), None))
