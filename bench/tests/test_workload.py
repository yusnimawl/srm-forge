import importlib.metadata
import json
from importlib import resources

import numpy as np
import pytest
from srmcore.maps.grids import GRID_SIZES, angle_grid, current_grid
from srmcore.mesh.settings import resolve_mesh_settings

from srmbench import workload
from srmbench.workload import batch_grid, check_points, design, grid_points, reference_points, static_mesh, time_batch


REF = {"srmcore": "0.4.0", "nodes": 100, "points": [
    {"angle": 0.0, "current": 20.0, "psi": 0.3, "torque": 0.001},
    {"angle": 0.2, "current": 20.0, "psi": 0.2, "torque": -12.0},
]}


def _got(**changes):
    pts = [dict(p) for p in REF["points"]]
    for k, v in changes.items():
        idx, key = k.split("_", 1)
        pts[int(idx)][key] = v
    return pts


def test_check_points_pass_within_tolerance():
    got = _got(**{"0_psi": 0.3002, "0_torque": 0.001 + 0.011})   # torque off by 0.011 < 1e-3 * 12
    assert check_points(got, REF, "0.4.0", nodes=100) == {"status": "pass", "details": []}


def test_check_points_fail_cases():
    assert check_points(_got(**{"0_psi": 0.3004}), REF, "0.4.0")["status"] == "fail"
    assert check_points(_got(**{"0_torque": 0.001 + 0.02}), REF, "0.4.0")["status"] == "fail"
    bad_angle = check_points(_got(**{"1_angle": 0.2001}), REF, "0.4.0")
    assert bad_angle["status"] == "fail" and "angle" in bad_angle["details"][0]
    assert check_points(_got()[:1], REF, "0.4.0")["status"] == "fail"


def test_check_points_version_and_node_count():
    assert check_points(_got(), REF, "0.5.0")["status"] == "not checked"
    other_mesh = check_points(_got(), REF, "0.4.0", nodes=101)
    assert other_mesh["status"] == "pass" and other_mesh["details"] == ["mesh differs: 101 nodes vs 100"]


def test_batch_grid_same_mix_for_every_worker_count():
    d = design("8_6", "screening")
    base, i = batch_grid(d, 1)
    assert len(base) == 4 and len(i) == 2 and i[-1] == 20.0
    for w in (2, 4, 8):
        a, _ = batch_grid(d, w)
        assert len(a) == 4 * w and np.array_equal(a, np.tile(base, w))


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


@pytest.fixture(scope="module")
def built():
    d = design("8_6", "screening")
    static, info = static_mesh(d)
    return d, static, info


def test_reference_points_match_stored(built):
    d, static, info = built
    assert info["seconds"] > 0 and info["nodes"] > 0
    ref = json.loads(resources.files("srmbench.reference").joinpath("points_8_6.json").read_text())
    assert len(ref["points"]) == 3 and ref["nodes"] == info["nodes"]
    got = reference_points(static, d)
    result = check_points(got, ref, importlib.metadata.version("srmcore"), nodes=info["nodes"])
    assert result == {"status": "pass", "details": []}


def test_single_solves_median(built):
    d, static, _ = built
    out = workload.single_solves(static, d, 2)
    assert len(out["samples"]) == 2 and out["median"] > 0


def test_time_batch_one_worker_has_no_ram_figure(monkeypatch):
    calls = []
    monkeypatch.setattr(workload, "run_map", lambda *a, **k: calls.append((a, k)))
    r = time_batch(None, design("8_6", "screening"), 1)
    assert len(calls) == 1 and r["peak_ram_gb"] is None and r["points"] == 8


def test_time_batch_runs_two_workers(built):
    d, static, _ = built
    r = time_batch(static, d, 2)
    a, i = batch_grid(d, 2)
    assert r["points"] == len(a) * len(i) == 16 and r["per_min"] > 0 and r["peak_ram_gb"] > 0.05
