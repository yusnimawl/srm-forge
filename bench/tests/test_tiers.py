import json

import pytest

from srmbench import tiers
from srmbench.preflight import Platform
from srmbench.tiers import SUSTAINED_MIN, TIERS, run_tier, scaling_workers


def test_constants():
    assert TIERS == ("quick", "standard", "long")
    assert SUSTAINED_MIN == {"standard": 5, "long": 20}


def test_scaling_workers():
    assert scaling_workers(10, 16, 16, "quick") == [10, 16]
    assert scaling_workers(10, 16, 16, "standard") == [1, 2, 4, 8, 10, 16]
    assert scaling_workers(4, 4, 4, "long") == [1, 2, 4]
    assert scaling_workers(32, 64, 7, "quick") == []
    assert scaling_workers(10, 16, 12, "quick") == [10]
    assert scaling_workers(8, 16, 16, "standard") == [1, 2, 4, 8, 16]
    assert scaling_workers(6, 12, 5, "standard") == [1, 2, 4]


PLATFORM = Platform(system="Linux", machine="x86_64", libc="glibc", glibc=(2, 35), windows_build=None,
                    ram_gb=32.0, available_ram_gb=28.0, free_disk_gb=100.0, logical_cpus=16)


class FakeWorkload:
    """Stands in for every srmbench.workload function the tiers use and records the calls."""

    def __init__(self):
        self.calls: list[tuple] = []

    def design(self, name, preset):
        return (name, preset)

    def static_mesh(self, d):
        self.calls.append(("static_mesh", d))
        full = d[1] == "full"
        return f"static-{d[1]}", {"seconds": 12.3 if full else 4.1, "nodes": 98412 if full else 30000}

    def grid_points(self, d):
        return 1008 if d[1] == "full" else 360

    def single_solves(self, static, d, n):
        self.calls.append(("single_solves", d, n))
        base = 6.0 if d[1] == "full" else 2.0
        return {"samples": [base] * n, "median": base}

    def reference_points(self, static, d):
        return [{"angle": 0.0, "current": 20.0, "psi": 0.3, "torque": 0.0}]

    def check_points(self, got, ref, version, nodes=None):
        self.calls.append(("check_points", nodes))
        return {"status": "pass", "details": []}

    def load_reference(self, name):
        return {"name": name}

    def time_batch(self, static, d, workers):
        self.calls.append(("time_batch", workers))
        return {"workers": workers, "points": 8 * workers, "seconds": 10.0,
                "per_min": 100.0 * workers ** 0.5, "peak_ram_gb": None if workers == 1 else 0.8}

    def map_run(self, d, workers, goldens):
        self.calls.append(("map_run", d, workers, goldens is not None))
        full = d[1] == "full"
        status = "not checked" if goldens is None else "pass"
        return ({"seconds": 900.0 if full else 200.0, "points": 960 if full else 320, "key_numbers": {"la": 0.03},
                 "statuses": {"la_lu": "pass"}, "correctness": {"status": status, "details": []}}, "map-result")

    def extras_run(self, d, result, workers):
        self.calls.append(("extras_run", d, result, workers))
        return {"seconds": 300.0}

    def sustained(self, static, d, workers, minutes):
        self.calls.append(("sustained", workers, minutes))
        return {"batches": [{"t": 1.0, "per_min": 400.0}, {"t": 61.0, "per_min": 380.0}], "throttle_pct": -5.0}


@pytest.fixture
def fake(monkeypatch):
    f = FakeWorkload()
    for name in ("design", "static_mesh", "grid_points", "single_solves", "reference_points", "check_points",
                 "load_reference", "time_batch", "map_run", "extras_run", "sustained"):
        monkeypatch.setattr(tiers.workload, name, getattr(f, name))
    monkeypatch.setattr(tiers, "machine_info", lambda: {"cpu_model": "Fake", "physical_cores": 8, "logical_cpus": 16})
    monkeypatch.setattr(tiers, "package_versions", lambda: {"srmcore": "0.4.0", "numpy": "2.0"})
    monkeypatch.setattr(tiers, "lock_hash", lambda path: "deadbeef0000")
    monkeypatch.setattr(tiers, "_available_gb", lambda: 28.0)
    return f


def test_run_tier_quick_with_fake_workload(fake):
    lines: list[str] = []
    r = run_tier("quick", "test-box", PLATFORM, None, lines.append)
    assert r.status == "complete" and r.tier == "quick" and r.label == "test-box"
    assert r.schema == "srmbench-result" and r.lock_hash == "deadbeef0000"
    assert set(r.steps) == {"mesh", "single_solve", "correctness_points", "batches"}
    assert [b["workers"] for b in r.steps["batches"]] == [8, 16]
    assert r.summary["recommended_workers"] in {8, 16}
    assert r.summary["srmweb_workers"] == r.summary["recommended_workers"]
    assert r.summary["throttle_pct"] is None
    assert r.summary["screening_map_s"]["measured"] is False
    assert r.summary["correctness"]["status"] == "pass"
    assert ("single_solves", ("8_6", "screening"), 5) in fake.calls
    assert ("single_solves", ("8_6", "full"), 3) in fake.calls
    assert ("check_points", 30000) in fake.calls
    assert not any(c[0] in ("map_run", "sustained", "extras_run") for c in fake.calls)
    assert any("mesh 8/6 full: 12.3 s, 98 412 nodes" in line for line in lines)
    assert len(lines) >= 6
    print(json.dumps(r.__dict__, indent=1, sort_keys=True))


def test_run_tier_quick_empty_schedule_runs_one_batch_at_the_cap(fake, monkeypatch):
    monkeypatch.setattr(tiers, "machine_info", lambda: {"cpu_model": "Fake", "physical_cores": 32, "logical_cpus": 64})
    p = Platform(**{**PLATFORM.__dict__, "logical_cpus": 64})
    r = run_tier("quick", "big-box", p, 7, lambda s: None)
    assert [b["workers"] for b in r.steps["batches"]] == [7]
    assert r.summary["recommended_workers"] == 7


def test_run_tier_physical_cores_none_falls_back_to_logical(fake, monkeypatch):
    monkeypatch.setattr(tiers, "machine_info", lambda: {"cpu_model": "VM", "physical_cores": None, "logical_cpus": 4})
    p = Platform(**{**PLATFORM.__dict__, "logical_cpus": 4})
    r = run_tier("quick", "vm", p, None, lambda s: None)
    assert [b["workers"] for b in r.steps["batches"]] == [4]


def test_run_tier_ram_cap_from_first_batch_with_a_figure(fake, monkeypatch):
    # W=1 has no figure; W=2 reports 10 GB per worker, which with 28 GB available caps workers at 2.
    def batch(static, d, workers):
        fake.calls.append(("time_batch", workers))
        return {"workers": workers, "points": 16, "seconds": 10.0, "per_min": 50.0 * workers,
                "peak_ram_gb": None if workers == 1 else 10.0}

    monkeypatch.setattr(tiers.workload, "time_batch", batch)
    r = run_tier("standard", "tight", PLATFORM, None, lambda s: None)
    assert [b["workers"] for b in r.steps["batches"]] == [1, 2]
    assert r.summary["peak_ram_worker_gb"] == 10.0
    assert r.summary["recommended_workers"] == 2


def test_run_tier_standard(fake):
    r = run_tier("standard", "test-box", PLATFORM, 8, lambda s: None)
    assert [b["workers"] for b in r.steps["batches"]] == [1, 2, 4, 8]
    assert set(r.steps) == {"mesh", "single_solve", "correctness_points", "batches", "screening_map", "sustained"}
    assert r.summary["recommended_workers"] == 8
    assert ("map_run", ("8_6", "screening"), 8, True) in fake.calls
    assert ("sustained", 8, 5) in fake.calls
    assert r.steps["sustained"]["workers"] == 8 and r.steps["sustained"]["minutes"] == 5
    assert r.steps["screening_map"]["workers"] == 8
    assert r.summary["screening_map_s"] == {"value": 200.0, "measured": True}
    assert r.summary["full_map_s"]["measured"] is False
    assert r.summary["throttle_pct"] == -5.0


def test_run_tier_long_caps_full_map_workers_by_ram(fake, monkeypatch):
    monkeypatch.setattr(tiers, "_available_gb", lambda: 10.0)
    r = run_tier("long", "test-box", PLATFORM, None, lambda s: None)
    # peak 0.8 GB x (98412 / 30000) = 2.62 GB per full-map worker, (10 - 1) // 2.62 = 3
    assert r.steps["full_maps"]["8_6"]["workers"] == 3
    assert r.steps["full_maps"]["12_8"]["workers"] == 3
    assert ("map_run", ("8_6", "full"), 3, False) in fake.calls
    assert ("extras_run", ("12_8", "full"), "map-result", 3) in fake.calls
    assert ("sustained", r.summary["recommended_workers"], 20) in fake.calls
    assert r.summary["full_map_s"] == {"value": 900.0, "measured": True}
    assert set(r.summary["projection_error_pct"]) == {"screening", "full"}


def test_run_tier_long_without_ram_figure_keeps_the_recommended_workers(fake, monkeypatch):
    monkeypatch.setattr(tiers.workload, "time_batch", lambda static, d, workers: {
        "workers": workers, "points": 8 * workers, "seconds": 10.0, "per_min": 10.0 * workers, "peak_ram_gb": None})
    r = run_tier("long", "test-box", PLATFORM, 4, lambda s: None)
    assert r.summary["peak_ram_worker_gb"] is None
    assert r.steps["full_maps"]["8_6"]["workers"] == 4


def test_run_tier_keyboard_interrupt_propagates(fake, monkeypatch):
    def boom(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(tiers.workload, "time_batch", boom)
    with pytest.raises(KeyboardInterrupt):
        run_tier("quick", "x", PLATFORM, None, lambda s: None)


def test_run_tier_rejects_unknown_tier(fake):
    with pytest.raises(ValueError):
        run_tier("huge", "x", PLATFORM, None, lambda s: None)
