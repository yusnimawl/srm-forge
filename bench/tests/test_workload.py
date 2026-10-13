import importlib.metadata
import json
from importlib import resources

import numpy as np
import pytest
from srmcore.maps.grids import GRID_SIZES, angle_grid, current_grid
from srmcore.mesh.settings import resolve_mesh_settings

from srmbench import workload
from srmbench.workload import (batch_grid, check_points, design, grid_points, reference_points, static_mesh,
                               time_batch)


def test_check_points_pass_fail_and_version():
    ref = {"srmcore": "0.4.0", "points": [{"angle": 0.0, "current": 20.0, "psi": 0.3, "torque": 0.0}]}
    ok = [{"angle": 0.0, "current": 20.0, "psi": 0.30000002, "torque": 0.000005}]
    assert check_points(ok, ref, "0.4.0")["status"] == "pass"
    bad = check_points([{**ok[0], "psi": 0.301}], ref, "0.4.0")
    assert bad["status"] == "fail" and bad["details"]
    assert check_points(ok, ref, "0.5.0")["status"] == "not checked"


def test_batch_grid_size_and_determinism():
    d = design("8_6", "screening")
    a, i = batch_grid(d, 4)
    assert len(i) == 2 and i[-1] == 20.0 and len(a) <= 8 and np.array_equal(a, batch_grid(d, 4)[0])


def test_grid_points_screening_8_6():
    d = design("8_6", "screening")
    n_a, n_i = GRID_SIZES["screening"]
    divisions = resolve_mesh_settings(d.machine, d.mesh).band_divisions
    want = len(angle_grid(d.machine, divisions, n_a, aligned=0.0)) * len(current_grid(20.0, n_i))
    assert grid_points(d) == want


def test_sustained_throttle_with_fake_batches(monkeypatch):
    rates = iter([100.0, 100.0, 90.0, 80.0, 80.0])
    now = [0.0]

    def fake_batch(static, d, workers):
        now[0] += 60.0
        return {"workers": workers, "points": 8, "seconds": 1.0, "per_min": next(rates), "peak_ram_gb": 0.1}

    monkeypatch.setattr(workload, "time_batch", fake_batch)
    out = workload.sustained(None, None, 2, 5.0, clock=lambda: now[0])
    assert [b["per_min"] for b in out["batches"]] == [100.0, 100.0, 90.0, 80.0, 80.0]
    assert out["throttle_pct"] == pytest.approx(-20.0)


def test_sustained_single_batch_has_no_throttle(monkeypatch):
    now = [0.0]

    def fake_batch(static, d, workers):
        now[0] += 120.0
        return {"workers": workers, "points": 8, "seconds": 1.0, "per_min": 50.0, "peak_ram_gb": 0.1}

    monkeypatch.setattr(workload, "time_batch", fake_batch)
    out = workload.sustained(None, None, 2, 1.0, clock=lambda: now[0])
    assert len(out["batches"]) == 1 and out["throttle_pct"] == 0.0


def test_reference_points_match_stored():
    d = design("8_6", "screening")
    static, info = static_mesh(d)
    assert info["seconds"] > 0 and info["nodes"] > 0
    ref = json.loads(resources.files("srmbench.reference").joinpath("points_8_6.json").read_text())
    assert len(ref["points"]) == 3
    got = reference_points(static, d)
    assert check_points(got, ref, importlib.metadata.version("srmcore"))["status"] == "pass"


def test_single_solves_median():
    d = design("8_6", "screening")
    static, _ = static_mesh(d)
    out = workload.single_solves(static, d, 2)
    assert len(out["samples"]) == 2 and out["median"] > 0


def test_time_batch_runs_two_workers():
    d = design("8_6", "screening")
    static, _ = static_mesh(d)
    r = time_batch(static, d, 2)
    a, i = batch_grid(d, 2)
    assert r["points"] == len(a) * len(i) and r["per_min"] > 0 and r["peak_ram_gb"] > 0.05
