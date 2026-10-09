import json

import numpy as np
import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from srmapp import field as fieldmod
from srmapp.field import FieldFrame, FieldMesh, RegionInfo
from srmapp.sizing.generator import REFERENCE_TURNS
from srmweb.api import create_app
from srmweb.config import Settings
from srmweb.jobs import JobRunner
from srmweb.quick import LaneTimeout, QuickLane
from test_web_frames import unpack
from web_support import evaluation, store_search


@pytest.fixture
def client(tmp_path):
    s = Settings("127.0.0.1", 8000, tmp_path / "a.db", tmp_path / "cache", 1, None, 10, tmp_path / "nostatic")
    return TestClient(create_app(s, runner_factory=lambda store, st: JobRunner(
        store, st, run_fn=lambda k, r, p, ctx: {}, quick=QuickLane(spawn=False))))


def _case(client, stale=False, status="ok"):
    """An evaluated case with winding turns 40, paths 2, current 10 A and key.i_max 12 A."""
    store = client.app.state.store
    job_id = store_search(client, evaluation("c1"))
    case_id = client.post("/api/cases", json={"origin": "candidate", "job_id": job_id,
                                              "candidate_id": "c1"}).json()["id"]
    body = store.get_result(job_id)["evaluations"][0]
    body["winding"].update(turns=40, paths=2, current=10.0)
    body["key"]["i_max"] = 12.0
    body["status"] = status
    with store._db() as con:
        con.execute("UPDATE results SET body = ? WHERE case_id = ? AND kind = 'evaluate'",
                    (json.dumps(body), case_id))
        con.execute("UPDATE cases SET stale = ? WHERE id = ?", (int(stale), case_id))
    return case_id


@pytest.fixture
def calls(monkeypatch):
    calls = []

    def mesh(design, *, solver="ngsolve", cache_dir=None):
        calls.append(("mesh", design))
        regions = (RegionInfo("iron", "stator_iron", "stator", None, None),)
        z = np.array([0], dtype=np.int64)
        return FieldMesh(np.zeros((3, 2)), 2, np.array([[0, 1, 2]]), np.array([0]), regions, 1.8,
                         {"stator_pole": z, "stator_yoke": z, "rotor_pole": z})

    def frame(design, angle, coil_current, *, solver="ngsolve", cache_dir=None):
        calls.append(("frame", design, angle, coil_current))
        return FieldFrame(angle, coil_current, np.array([[0, 1, 2]]), np.ones(2, dtype=np.float32),
                          np.ones(3, dtype=np.float32), 0.5, 1.5, "converged", {"stator_pole": 1.0})

    monkeypatch.setattr(fieldmod, "field_mesh", mesh)
    monkeypatch.setattr(fieldmod, "field_frame", frame)
    return calls


def test_snapshot_scales_current_and_flux(client, calls):
    cid = _case(client)
    r = client.post(f"/api/cases/{cid}/field", json={"angle": 0.3, "current_a": 3.0})
    assert r.status_code == 200 and r.headers["content-type"] == "application/octet-stream"
    k = 40 / (2 * REFERENCE_TURNS)
    _, design, angle, coil = calls[-1]
    assert design.machine.turns_per_pole == REFERENCE_TURNS
    assert angle == 0.3 and coil == pytest.approx(3.0 * k)
    header, _, arrays = unpack(r.content)
    assert header["meta"]["psi"] == pytest.approx(0.5 * k) and header["meta"]["torque"] == 1.5
    assert set(arrays) == {"band", "b", "a"}


def test_mesh_route(client, calls):
    cid = _case(client)
    r = client.get(f"/api/cases/{cid}/field/mesh")
    assert r.status_code == 200 and r.headers["content-type"] == "application/octet-stream"
    header, _, arrays = unpack(r.content)
    meta = header["meta"]
    assert meta["winding_current"] == 10.0 and meta["i_max"] == 12.0 and meta["n_stator_nodes"] == 2
    assert meta["regions"][0]["name"] == "iron" and "probe.rotor_pole" in arrays


def test_unevaluated_cases_give_409(client, calls):
    stale = _case(client, stale=True)
    assert client.post(f"/api/cases/{stale}/field", json={"angle": 0.1, "current_a": 1}).status_code == 409
    failed = _case(client, status="MapFailed")
    assert client.get(f"/api/cases/{failed}/field/mesh").status_code == 409


def test_limits(client, calls):
    cid = _case(client)
    assert client.post(f"/api/cases/{cid}/field", json={"angle": 0.1, "current_a": 25}).status_code == 422
    assert client.post(f"/api/cases/{cid}/field", json={"angle": 7.0, "current_a": 3}).status_code == 422


def test_timeout_and_errors(client, calls, monkeypatch):
    cid = _case(client)

    def raiser(exc):
        def f(*a, **k):
            raise exc
        return f

    monkeypatch.setattr(fieldmod, "field_frame", raiser(LaneTimeout("t")))
    r = client.post(f"/api/cases/{cid}/field", json={"angle": 0.1, "current_a": 3})
    assert r.status_code == 504 and "120 s" in r.json()["detail"]
    monkeypatch.setattr(fieldmod, "field_frame", raiser(RuntimeError("x")))
    r = client.post(f"/api/cases/{cid}/field", json={"angle": 0.1, "current_a": 3})
    assert r.status_code == 500 and "RuntimeError: x" in r.json()["detail"]
