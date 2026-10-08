import json
import time

import numpy as np
import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from srmweb.api import create_app
from srmweb.config import load_settings
from srmweb.jobs import JobRunner

BODY = {"kind": "search",
        "payload": {"requirements": dict(peak_power_w=630.0, peak_torque_nm=2.0,
                                         base_speed_rpm=3000.0, max_speed_rpm=6000.0),
                    "settings": dict(n_candidates=2, shortlist=1, preset="screening"),
                    "grid": [4, 3]}}


@pytest.mark.slow
def test_search_job_end_to_end(tmp_path):
    settings = load_settings({"SRMWEB_DB": str(tmp_path / "e2e.db"),
                              "SRMWEB_CACHE_DIR": str(tmp_path / "cache"),
                              "SRMWEB_WORKERS": "2"})
    with TestClient(create_app(settings, runner_factory=JobRunner)) as client:
        r = client.post("/api/jobs", json=BODY)
        assert r.status_code == 201, r.text
        job_id = r.json()["id"]
        end = time.time() + 1800
        while time.time() < end:
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in {"done", "failed", "cancelled"}:
                break
            time.sleep(1.0)
        assert job["status"] == "done", job
        result = client.get(f"/api/jobs/{job_id}/result").json()

    json.dumps(result, allow_nan=False)
    assert result["sampled"] >= 1
    assert len(result["evaluations"]) == 1
    ok = [e for e in result["evaluations"] if e["status"] == "ok"]
    assert ok, [e["status"] for e in result["evaluations"]]
    # the current grid gains the La current beyond the 3 requested nodes
    assert np.shape(ok[0]["map"]["psi"]) == (4, 4)
    assert "theta_on_el" in ok[0]["envelope"]
