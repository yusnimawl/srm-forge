"""Which steps each tier runs, in order, and the result they produce.

`steps` layout (JSON-able, every raw sample kept):
  mesh                {"screening" | "full": {seconds, nodes, points}}        8/6 meshes; points = grid size
  single_solve        {"screening" | "full": {samples, median}}
  correctness_points  {points, correctness}
  batches             [time_batch result, ...] in ascending worker count
  screening_map       map_run summary + workers                               standard, long
  sustained           workload.sustained result + workers, minutes            standard, long
  full_maps           {"8_6" | "12_8": {map, extras, workers}}                long
"""

from __future__ import annotations

import platform as _platform
from collections.abc import Callable

import psutil

from . import BENCH_DIR, BENCH_VERSION, workload
from .preflight import Platform, apply_cgroup, cgroup_memory, max_workers
from .projections import choose_workers, summary
from .result import SCHEMA, Result, now_iso
from .sysinfo import lock_hash, machine_info, package_versions

TIERS = ("quick", "standard", "long")
SUSTAINED_MIN = {"standard": 5, "long": 20}
SINGLE_SOLVES = {"screening": 5, "full": 3}


def scaling_workers(physical: int, logical: int, cap: int, tier: str) -> list[int]:
    """Worker counts to time: quick the physical and logical counts, the others also 1, 2, 4, 8, ...; all within cap."""
    counts = {physical, logical}
    if tier != "quick":
        w = 1
        while w <= cap:
            counts.add(w)
            w *= 2
    return sorted(w for w in counts if 1 <= w <= cap)


def _available_gb() -> float:
    available = float(psutil.virtual_memory().available)
    if _platform.system() == "Linux":
        _, available = apply_cgroup(float("inf"), available, cgroup_memory())
    return available / 1e9


def _seconds(x: float) -> str:
    return f"{x:.1f} s"


def run_tier(tier: str, label: str, platform: Platform, worker_cap: int | None, log: Callable[[str], None]) -> Result:
    """Run the tier's steps and return the result (the caller writes it). KeyboardInterrupt propagates."""
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; tiers: {', '.join(TIERS)}")
    started = now_iso()
    logical = platform.logical_cpus
    info = machine_info()
    physical = min(info.get("physical_cores") or logical, logical)
    versions = package_versions()
    log(f"machine: {info.get('cpu_model')}, {physical} cores, {logical} threads, {platform.ram_gb:.1f} GB RAM")

    steps: dict = {}
    d_scr, d_full = workload.design("8_6", "screening"), workload.design("8_6", "full")
    static_scr, mesh_scr = workload.static_mesh(d_scr)
    static_full, mesh_full = workload.static_mesh(d_full)
    steps["mesh"] = {
        "screening": {**mesh_scr, "points": workload.grid_points(d_scr)},
        "full": {**mesh_full, "points": workload.grid_points(d_full)},
    }
    for name, m in (("screening", mesh_scr), ("full", mesh_full)):
        nodes = f"{m['nodes']:,}".replace(",", " ")
        log(f"mesh 8/6 {name}: {_seconds(m['seconds'])}, {nodes} nodes")

    steps["single_solve"] = {}
    for name, d, static in (("screening", d_scr, static_scr), ("full", d_full, static_full)):
        steps["single_solve"][name] = workload.single_solves(static, d, SINGLE_SOLVES[name])
        s = steps["single_solve"][name]
        log(f"single solve 8/6 {name}: median {_seconds(s['median'])} of {len(s['samples'])}")
    del static_full, static

    points = workload.reference_points(static_scr, d_scr)
    correctness = workload.check_points(points, workload.load_reference("points_8_6.json"),
                                        versions.get("srmcore") or "unknown", nodes=mesh_scr["nodes"])
    steps["correctness_points"] = {"points": points, "correctness": correctness}
    log(f"correctness points: {correctness['status']}" + "".join(f"; {x}" for x in correctness["details"]))

    cap = max_workers(logical, _available_gb(), None, worker_cap)
    schedule = scaling_workers(physical, logical, cap, tier) or [cap]
    steps["batches"] = []
    ram_known = False
    for w in schedule:
        if w > cap:
            break
        b = workload.time_batch(static_scr, d_scr, w)
        steps["batches"].append(b)
        ram = "" if b["peak_ram_gb"] is None else f", {b['peak_ram_gb']:.2f} GB per worker"
        log(f"batch {w} workers: {b['per_min']:.1f} solves/min{ram}")
        if not ram_known and b["peak_ram_gb"] is not None:
            ram_known = True
            cap = max_workers(logical, _available_gb(), b["peak_ram_gb"], worker_cap)

    recommended = choose_workers(steps["batches"], tier)
    peaks = [b["peak_ram_gb"] for b in steps["batches"] if b["peak_ram_gb"] is not None]
    peak = max(peaks) if peaks else None
    run_workers = min(recommended, max_workers(logical, _available_gb(), peak, worker_cap))

    if tier in SUSTAINED_MIN:
        goldens = workload.load_reference("goldens_8_6.json")
        run, result = workload.map_run(d_scr, run_workers, goldens)
        steps["screening_map"] = {**run, "workers": run_workers}
        log(f"screening map 8/6: {_seconds(run['seconds'])} at {run_workers} workers, correctness {run['correctness']['status']}")
        del result
        minutes = SUSTAINED_MIN[tier]
        log(f"sustained load: {minutes} min at {run_workers} workers")
        sus = workload.sustained(static_scr, d_scr, run_workers, minutes)
        steps["sustained"] = {**sus, "workers": run_workers, "minutes": minutes}
        log(f"sustained: throttle {sus['throttle_pct']:+.1f} %")

    if tier == "long":
        node_ratio = mesh_full["nodes"] / mesh_scr["nodes"]
        full_peak = None if peak is None else peak * node_ratio
        full_workers = min(recommended, max_workers(logical, _available_gb(), full_peak, worker_cap))
        steps["full_maps"] = {}
        for name in ("8_6", "12_8"):
            d = workload.design(name, "full")
            run, result = workload.map_run(d, full_workers, None)
            log(f"full map {name.replace('_', '/')}: {_seconds(run['seconds'])} at {full_workers} workers")
            extras = workload.extras_run(d, result, full_workers)
            log(f"full extras {name.replace('_', '/')}: {_seconds(extras['seconds'])}")
            steps["full_maps"][name] = {"map": run, "extras": extras, "workers": full_workers}
            del result

    result_summary = summary(steps, tier)
    log(f"recommended workers: {result_summary['recommended_workers']}, {result_summary['throughput_per_min']:.1f} solves/min")
    return Result(
        schema=SCHEMA, bench_version=BENCH_VERSION, tier=tier, label=label, started=started, finished=now_iso(),
        status="complete", machine=info, versions=versions, lock_hash=lock_hash(BENCH_DIR / "requirements.lock"),
        steps=steps, summary=result_summary, warnings=[],
    )
