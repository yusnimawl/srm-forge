"""srmweb HIL routes on the fake rig: loopback rule, session lifecycle, live parameters, capture and comparison,
the flash job and its exclusion with the session, and the cache."""

import json
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sil_fixtures import analytic_motor

from srmsil import run as sil_run
from srmsil.hil import HilError
from srmsil.hil.build import firmware_hash
from srmsil.hil.config import HilModes
from srmsil.hil.fake import FakeRig
from srmsil.hil.proto import CAPTURE_RING
from srmsil.scenario import Scenario
from srmsil.tables import motor_data_from_json
from srmweb.api import create_app
from srmweb.config import Settings
from srmweb.hil import HilManager
from srmweb.jobs import JobRunner
from web_support import analytic_evaluation, store_search

SCENARIO = {"speed_rpm": 1000.0, "duration": 0.02, "command_value": 1.0, "bus_voltage": 48.0}
CAPTURE_STEPS = 4200      # 25 ms: its second half spans 5 strokes of the analytic 8/6 at 1000 rpm
OPEN = {"controller": "hysteresis", "scenario": SCENARIO, "modes": {}}


def _settings(tmp_path, host="127.0.0.1", token=None):
    return Settings(host, 8000, tmp_path / "a.db", tmp_path / "cache", 1, token, 10, tmp_path / "nostatic")


@pytest.fixture
def rig(tmp_path):
    """Keyword arguments of the next FakeRig the app opens."""
    return {"cache_dir": tmp_path / "rig"}


def _client(tmp_path, rig, host="127.0.0.1", token=None):
    """The app on the fake rig; `client.rig` is the keyword dict of the next FakeRig it opens."""
    c = TestClient(create_app(_settings(tmp_path, host, token), runner_factory=lambda store, st: JobRunner(store, st),
                              hil_transports=lambda: FakeRig(analytic_motor(), **rig)))
    c.rig = rig
    return c


@pytest.fixture
def client(tmp_path, rig):
    with _client(tmp_path, rig) as c:
        yield c


def _build(client, cid, controller="hysteresis"):
    """The firmware hash of the case's build of `controller` for SCENARIO, from the sources as they are now."""
    motor = motor_data_from_json(client.app.state.store.case_result(cid, "evaluate"), SCENARIO["bus_voltage"])
    return firmware_hash(controller, motor, Scenario(**SCENARIO), HilModes())


def _flashed(client, cid, controller="hysteresis", firmware_hash=None):
    """A finished Build & Flash job of the case and controller, as run_hil_flash_job stores it (by default of the
    current sources); the fake rig's boards then run that build."""
    h = _build(client, cid, controller) if firmware_hash is None else firmware_hash
    store = client.app.state.store
    job_id = store.create_job("hil_flash", {"case_id": cid})
    store.put_result(job_id, {"case_id": cid, "controller": controller, "modes": {}, "firmware_hash": h,
                              "log": ""}, kind="hil_flash")
    store.set_status(job_id, "done")
    if firmware_hash is None:
        client.rig.update(emulator_hash=h, controller_hash=h)
    return h


def _case(client, flashed=True):
    """An evaluated case; with `flashed` the boards of the fake rig run its hysteresis build."""
    job_id = store_search(client, analytic_evaluation("c1"))
    cid = client.post("/api/cases", json={"origin": "candidate", "job_id": job_id, "candidate_id": "c1"}).json()["id"]
    if flashed:
        _flashed(client, cid)
    return cid


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
          ("get", "/api/jobs/abc/hil-flash", None), ("get", "/api/hil/captures/abc?n_px=500", None), ("get", "/api/hil/captures/abc/compare", None)]


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
    m = HilManager(_settings(tmp_path, "0.0.0.0", "t"), lambda: FakeRig(analytic_motor()), lambda: False,
                   lambda case_id, controller: 0)
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
    h = _build(client, cid)
    assert s["case_id"] == cid and s["controller"] == "hysteresis" and not s["running"]
    assert s["modes"] == {"current_sense": "ad7606", "position": "encoder", "dac": "mcp4922x2"}
    assert s["emulator_hash"] == s["controller_hash"] == h
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
    r = client.post("/api/hil/session/capture", json={"n_steps": CAPTURE_STEPS})
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
    assert out["ripple_window_hil"] > 0 and out["ripple_window_sil"] > 0
    from web_support import unpack
    header, _, arrays = unpack(client.get(f"/api/hil/captures/{cap['capture_id']}?n_px=500").content)
    assert header["meta"]["compared"] and header["meta"]["hil"]["valid"]
    assert "y.i.0" in arrays and "y.sil.i.0" in arrays
    assert arrays["t.sil.i.0"][0] >= arrays["t.i.0"][0] - 1e-9


def _capture(client, n_steps=CAPTURE_STEPS):
    r = client.post("/api/hil/session/capture", json={"n_steps": n_steps})
    assert r.status_code == 201, r.text
    return r.json()


def _compare(client, cap):
    r = client.get(f"/api/hil/captures/{cap['capture_id']}/compare")
    assert r.status_code == 200, r.text
    return r.json()


def test_late_fixed_capture_matches_from_settle_before(client):
    """A fixed-speed capture more than 1 s after Start: the matched SIL starts SETTLE_S before it."""
    _open(client, _case(client))
    client.post("/api/hil/session/start")
    time.sleep(1.3)
    cap = _capture(client)
    assert cap["valid"], cap["reason"]
    out = _compare(client, cap)
    assert out["passed"], out
    from web_support import unpack
    _, _, arrays = unpack(client.get(f"/api/hil/captures/{cap['capture_id']}?n_px=500").content)
    t_hil, t_sil = arrays["t.i.0"], arrays["t.sil.i.0"]
    assert t_hil[0] > 1.3 and t_sil[0] >= t_hil[0] - 1e-6 and t_sil[-1] <= t_hil[-1] + 1e-6


def test_capture_after_restart_matches(client):
    """Stop and Start again: the boards restart from the scenario's initial state and the change made in the first
    run is part of the scenario of the second."""
    _open(client, _case(client))
    client.post("/api/hil/session/start")
    assert client.post("/api/hil/session/param", json={"name": "band", "value": 0.6}).json() == {"status": 0}
    client.post("/api/hil/session/stop")
    client.post("/api/hil/session/start")
    out = _compare(client, _capture(client))
    assert out["passed"], out


def test_fixed_change_within_settle_refused(client):
    _open(client, _case(client))
    client.post("/api/hil/session/start")
    time.sleep(0.3)
    client.post("/api/hil/session/command", json={"mode": "torque", "value": 1.2})
    out = _compare(client, _capture(client))
    assert not out["passed"] and out["reason"] == "parameters or command changed within 0.2 s before the capture"
    assert out["d_torque_pct"] is None


def test_fixed_change_long_before_capture_matches(client):
    _open(client, _case(client))
    client.post("/api/hil/session/start")
    client.post("/api/hil/session/command", json={"mode": "torque", "value": 1.2})
    time.sleep(0.4)
    out = _compare(client, _capture(client))
    assert out["passed"], out


def test_dynamic_change_while_running_refused(client):
    scn = {**SCENARIO, "mode": "dynamic", "speed_rpm": 200.0, "inertia": 2e-3}
    _open(client, _case(client), {**OPEN, "scenario": scn})
    client.post("/api/hil/session/start")
    client.post("/api/hil/session/command", json={"mode": "torque", "value": 1.2})
    out = _compare(client, _capture(client))
    assert not out["passed"] and "changed while running" in out["reason"]


def test_capture_before_start_409(client):
    _open(client, _case(client))
    r = client.post("/api/hil/session/capture", json={"n_steps": 1000})
    assert r.status_code == 409 and r.json()["detail"] == "start the run before capturing"


def test_failed_sil_run_is_a_reason_not_500(client, monkeypatch):
    _open(client, _case(client))
    client.post("/api/hil/session/start")
    cap = _capture(client)

    def broken(*a, **k):
        raise ValueError("controller library missing")

    monkeypatch.setattr("srmweb.hil.sil_run.run", broken)
    out = _compare(client, cap)
    assert not out["passed"] and out["reason"] == "the matched SIL run failed: controller library missing"


def test_concurrent_compares_run_one_sil_and_block_cache_clear(client, monkeypatch):
    import threading
    import srmsil.run as sil_run_module
    _open(client, _case(client))
    client.post("/api/hil/session/start")
    cap = _capture(client)
    client.delete("/api/hil/session")
    real, release, calls = sil_run_module.run, threading.Event(), []

    def slow(*a, **k):
        calls.append(1)
        release.wait(30)
        return real(*a, **k)

    monkeypatch.setattr("srmweb.hil.sil_run.run", slow)
    hil, results = client.app.state.hil, []
    motor = lambda case_id, bus: analytic_motor()     # noqa: E731
    threads = [threading.Thread(target=lambda: results.append(hil.compare(cap["capture_id"], motor)))
               for _ in range(2)]
    for th in threads:
        th.start()
    end = time.time() + 10
    while not calls and time.time() < end:
        time.sleep(0.01)
    r = client.delete("/api/settings/cache")
    assert r.status_code == 409 and "comparison" in r.json()["detail"]
    release.set()
    for th in threads:
        th.join(60)
    assert len(calls) == 1 and len(results) == 2 and all(c.passed for c in results), results
    assert not hil.comparing()
    assert client.delete("/api/settings/cache").status_code == 204


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
    out = client.get(f"/api/jobs/{job['id']}/hil-flash")
    assert out.status_code == 200, out.text
    assert out.json() == {"case_id": cid, "controller": "hysteresis", "firmware_hash": 0x1234,
                          "modes": {"current_sense": "ad7606", "position": "encoder", "dac": "mcp4922x2"},
                          "log": result["log"]}


def test_flash_job_failure_carries_log(client, monkeypatch):
    from srmsil.hil.build import BuildResult
    monkeypatch.setattr("srmweb.jobs.build_and_flash",
                        lambda *a, upload=True, **k: BuildResult(False, "error: undefined ctrl_isr", 0))
    cid = _case(client)
    job = _wait(client, client.post(f"/api/cases/{cid}/hil/flash", json=OPEN).json()["job_id"])
    assert job["status"] == "failed" and "undefined ctrl_isr" in job["error"]
    assert client.get(f"/api/jobs/{job['id']}/hil-flash").status_code == 404
    assert client.get("/api/jobs/nope/hil-flash").status_code == 404


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


BUILD = "runs another build"


def test_open_refuses_boards_without_this_flash(client, rig):
    """The session opens only when both boards run the newest Build & Flash of the case and controller."""
    cid = _case(client, flashed=False)
    r = _open(client, cid)
    assert r.status_code == 409 and r.json()["detail"].startswith(f"the controller board {BUILD}")
    _flashed(client, cid, controller="tsf")                      # another controller's build
    assert BUILD in _open(client, cid).json()["detail"]
    rig.update(emulator_hash=_build(client, cid), controller_hash=_build(client, cid))
    _flashed(client, cid, firmware_hash=0x1234)                  # this controller, but not what the boards run
    r = _open(client, cid)
    assert r.status_code == 409 and "controller board" in r.json()["detail"]
    _flashed(client, cid)
    assert _open(client, cid).status_code == 201
    client.delete("/api/hil/session")
    other = _case(client, flashed=False)                         # flashed for another case only
    assert BUILD in _open(client, other).json()["detail"]
    rig["emulator_hash"] = 0x1234
    r = _open(client, cid)
    assert r.status_code == 409 and r.json()["detail"].startswith(f"the emulator board {BUILD}")
    assert not client.app.state.hil.is_open()


def test_open_refuses_controller_sources_changed_since_the_flash(client, tmp_path):
    """A custom controller folder edited after its Build & Flash: the boards still run the flashed build, so the
    session (whose matched SIL compiles the folder as it is now) is refused."""
    import shutil
    folder = tmp_path / "ctrl"
    shutil.copytree(Path(__file__).parents[1] / "sil" / "controllers" / "open_loop", folder)
    cid = _case(client, flashed=False)
    _flashed(client, cid, controller=str(folder))
    body = {**OPEN, "controller": str(folder)}
    assert _open(client, cid, body).status_code == 201
    client.delete("/api/hil/session")
    src = next(folder.glob("*.c"))
    src.write_text(src.read_text() + "\n/* edited after the flash */\n")
    r = _open(client, cid, body)
    assert r.status_code == 409
    assert r.json()["detail"].startswith("the controller sources changed since the last Build & Flash")
    assert not client.app.state.hil.is_open()


def test_events_stream_reports_a_lost_board_link(client, monkeypatch):
    _open(client, _case(client))
    client.post("/api/hil/session/start")

    def lost():
        raise HilError("serial port closed")

    monkeypatch.setattr(client.app.state.hil._session, "live", lost)
    got = []
    with client.stream("GET", "/api/hil/session/events") as r:
        name = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                got.append((name, json.loads(line[6:])))
    assert got == [("link_lost", {"error": "serial port closed"})]


def test_capture_longer_than_the_ring_is_422(client):
    _open(client, _case(client))
    client.post("/api/hil/session/start")
    r = client.post("/api/hil/session/capture", json={"n_steps": CAPTURE_RING + 1})
    assert r.status_code == 422
    assert client.post("/api/hil/session/capture", json={"n_steps": CAPTURE_RING}).status_code == 201


def test_sil_file_without_start_time_is_rerun_not_500(client):
    _open(client, _case(client))
    client.post("/api/hil/session/start")
    cap = _capture(client)
    path = client.app.state.hil.capture_file(cap["capture_id"])
    assert _compare(client, cap)["passed"]
    sil_file = path.with_name(f"{cap['capture_id']}.sil.npz")
    sil = sil_run.load(sil_file)
    sil_run.save(replace(sil, hil=None), sil_file)               # a file from before the HIL block existed
    assert _compare(client, cap)["passed"]                         # run again and saved with its start time
    assert sil_run.load(sil_file).hil["t0"] >= 0
    sil_run.save(replace(sil_run.load(sil_file), hil={}), sil_file)
    assert client.get(f"/api/hil/captures/{cap['capture_id']}?n_px=500").status_code == 200
