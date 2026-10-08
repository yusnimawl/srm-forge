import time

import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from srmcore.maps.grids import GRID_SIZES
from srmweb.api import create_app
from srmweb.config import load_settings
from srmweb.jobs import JobRunner

REQ = dict(peak_power_w=630.0, peak_torque_nm=2.0, base_speed_rpm=3000.0, max_speed_rpm=6000.0)


@pytest.mark.slow
def test_case_evaluate_end_to_end(tmp_path, monkeypatch):
    settings = load_settings({"SRMWEB_DB": str(tmp_path / "e2e.db"),
                              "SRMWEB_CACHE_DIR": str(tmp_path / "cache"),
                              "SRMWEB_WORKERS": "2"})
    with TestClient(create_app(settings, runner_factory=JobRunner)) as client:
        case = client.post("/api/cases", json={"origin": "reference", "name": "8/6", "requirements": REQ,
                                               "preset": "screening"})
        assert case.status_code == 201, case.text
        case = case.json()
        cid = case["id"]
        assert case["stale"] is True

        inputs = case["inputs"] | {"winding": {"turns": 60, "paths": 1}}
        r = client.patch(f"/api/cases/{cid}", json={"inputs": inputs})
        assert r.status_code == 200, r.text

        r = client.post(f"/api/cases/{cid}/evaluate", json={"grid": [4, 3]})
        assert r.status_code == 201, r.text
        job_id = r.json()["job_id"]
        end = time.time() + 1800
        while time.time() < end:
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in {"done", "failed", "cancelled"}:
                break
            time.sleep(1.0)
        assert job["status"] == "done", job

        done = client.get(f"/api/cases/{cid}").json()
        assert done["stale"] is False
        ev = done["evaluation"]
        assert ev["status"] == "ok", ev["error"]
        assert ev["winding"]["turns"] == 60 and ev["winding"]["paths"] == 1
        k2 = ev["curves"]["k2"]
        assert k2 and all(0.0 < k < 1.0 for k in k2)

        store = client.app.state.store
        (map_s,), (scan_s,) = store.recent_map_times("screening"), store.recent_scan_times("fixed")
        # the estimate looks up the preset's default grid: the test-only grid the job used is a miss...
        miss = client.get(f"/api/cases/{cid}/estimate").json()
        assert miss["new_map"] is True and miss["basis"] == "history"
        assert miss["seconds"] == pytest.approx(map_s + scan_s)
        # ...until the lookup is pointed at it
        monkeypatch.setitem(GRID_SIZES, "screening", (4, 3))
        est = client.get(f"/api/cases/{cid}/estimate")
        assert est.status_code == 200, est.text
        assert est.json() == {"new_map": False, "seconds": pytest.approx(scan_s), "basis": "history"}
