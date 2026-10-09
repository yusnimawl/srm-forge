import json
import math
import time

import numpy as np
import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("ngsolve")

from fastapi.testclient import TestClient

from srmapp.sizing.generator import REFERENCE_TURNS
from srmweb.api import create_app
from srmweb.config import Settings
from srmweb.jobs import JobRunner
from srmweb.quick import QuickLane
from web_support import evaluation, store_search, unpack


def _seed(client) -> str:
    """An evaluated 8/6 screening case with no map: only its winding and key numbers are stored."""
    store = client.app.state.store
    job_id = store_search(client, evaluation("c1"))
    cid = client.post("/api/cases", json={"origin": "candidate", "job_id": job_id, "candidate_id": "c1"}).json()["id"]
    body = store.get_result(job_id)["evaluations"][0]
    body["winding"].update(turns=REFERENCE_TURNS, paths=1, current=10.0)
    body["key"].update(i_max=20.0, aligned_angle=0.0, unaligned_angle=math.pi / 6)
    with store._db() as con:
        con.execute("UPDATE results SET body = ? WHERE case_id = ? AND kind = 'evaluate'", (json.dumps(body), cid))
        con.execute("UPDATE cases SET stale = 0 WHERE id = ?", (cid,))
    return cid


@pytest.mark.slow
def test_field_snapshot_and_animation_end_to_end(tmp_path):
    s = Settings("127.0.0.1", 8000, tmp_path / "a.db", tmp_path / "cache", 1, None, 10, tmp_path / "nostatic")
    with TestClient(create_app(s, runner_factory=lambda store, st: JobRunner(store, st, quick=QuickLane()))) as client:
        cid = _seed(client)
        r = client.get(f"/api/cases/{cid}/field/mesh")
        assert r.status_code == 200, r.text
        mesh_header, _, mesh = unpack(r.content)
        n_static = len(mesh["triangles"])

        r = client.post(f"/api/cases/{cid}/field", json={"angle": 0.0, "current_a": 10.0})
        assert r.status_code == 200, r.text
        header, _, arrays = unpack(r.content)
        assert header["meta"]["psi"] > 0 and header["meta"]["status"] == "OK"
        assert len(arrays["band"]) + n_static == len(arrays["b"])

        r = client.post(f"/api/cases/{cid}/animate", json={"current_a": 10.0, "frames": 12})
        assert r.status_code == 201, r.text
        job_id = r.json()["job_id"]
        end = time.time() + 1800
        while time.time() < end:
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in {"done", "failed", "cancelled"}:
                break
            time.sleep(1.0)
        assert job["status"] == "done", job
        torque = np.array(client.app.state.store.get_result(job_id)["torque"])
        assert len(torque) == 12 and abs(torque[-1]) < 0.05 * np.abs(torque).max()
        r = client.get(f"/api/jobs/{job_id}/frames")
        assert r.status_code == 200 and len(unpack(r.content)[0]["meta"]["angles"]) == 12
