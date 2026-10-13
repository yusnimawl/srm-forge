"""The measured steps: each runs the real srmcore engine and returns a plain JSON-able dict."""

import dataclasses
import json
import math
import statistics
import sys
import time
from importlib import metadata, resources

import numpy as np
from srmapp.references import make_8_6, make_12_8
from srmcore.maps import analyse_map, build_map, build_overlap_map
from srmcore.maps.fem_checks import fem_checks
from srmcore.maps.grids import GRID_SIZES, aligned_angle, angle_grid, current_grid
from srmcore.maps.point import solve_point
from srmcore.maps.run import run_map
from srmcore.mesh import build_machine_mesh
from srmcore.mesh.band import snap_angle
from srmcore.mesh.settings import resolve_mesh_settings
from srmcore.model.design import Design, MeshSettings
from srmcore.solvers.factory import make_solver

from .monitor import WorkerRam

I_MAX = {"8_6": 20.0, "12_8": 10.0}
_MAKERS = {"8_6": make_8_6, "12_8": make_12_8}
_I_MAX_BY_POLES = {(8, 6): I_MAX["8_6"], (12, 8): I_MAX["12_8"]}
CHECK_RTOL = 1e-4
CHECK_FLOOR = 0.1
KEY_RTOL = 1e-3
THROTTLE_FRACTION = 0.2


def design(name: str, preset: str) -> Design:
    return Design(machine=_MAKERS[name](), mesh=MeshSettings(preset=preset))


def _i_max(d: Design) -> float:
    return _I_MAX_BY_POLES[(d.machine.n_stator_poles, d.machine.n_rotor_poles)]


def _divisions(d: Design) -> int:
    return resolve_mesh_settings(d.machine, d.mesh).band_divisions


def static_mesh(d: Design):
    t0 = time.perf_counter()
    static = build_machine_mesh(d)
    seconds = time.perf_counter() - t0
    return static, {"seconds": seconds, "nodes": int(len(static.stator.nodes) + len(static.rotor.nodes))}


def single_solves(static, d: Design, n: int) -> dict:
    """n cold solves at the aligned angle, phase A at full current, each with a fresh single-thread solver."""
    angle = aligned_angle(d.machine, "A")
    samples = []
    for _ in range(n):
        solver = make_solver("ngsolve", threads=1)
        t0 = time.perf_counter()
        solve_point(static, d, angle, {"A": _i_max(d)}, solver)
        samples.append(time.perf_counter() - t0)
    return {"samples": samples, "median": statistics.median(samples)}


def reference_points(static, d: Design) -> list[dict]:
    """Phase A flux linkage and Arkkio torque at the aligned, mid and unaligned angles at full current."""
    tau = 2 * math.pi / d.machine.n_rotor_poles
    divisions = _divisions(d)
    i_max = _i_max(d)
    solver = make_solver("ngsolve", threads=1)
    out = []
    for offset in (0.0, tau / 4, tau / 2):
        angle = snap_angle(aligned_angle(d.machine, "A") + offset, divisions)[0]
        p = solve_point(static, d, angle, {"A": i_max}, solver)
        out.append({"angle": float(angle), "current": i_max, "psi": float(p.psi[0]),
                    "torque": float(p.torque_arkkio)})
    return out


def check_points(got: list[dict], ref: dict, srmcore_version: str) -> dict:
    """Compare solved points with the stored reference; values pass within CHECK_RTOL of the reference
    (relative to at least CHECK_FLOOR, so a reference near zero is compared on an absolute scale)."""
    if ref.get("srmcore") != srmcore_version:
        return {"status": "not checked",
                "details": [f"reference is for srmcore {ref.get('srmcore')}, running {srmcore_version}"]}
    want_points = ref["points"]
    if len(got) != len(want_points):
        return {"status": "fail", "details": [f"{len(got)} points, reference has {len(want_points)}"]}
    details = []
    for k, (g, w) in enumerate(zip(got, want_points)):
        for key in ("psi", "torque"):
            if abs(g[key] - w[key]) > CHECK_RTOL * max(abs(w[key]), CHECK_FLOOR):
                details.append(f"point {k} {key}: got {g[key]:.8g}, want {w[key]:.8g}")
    return {"status": "fail" if details else "pass", "details": details}


def batch_grid(d: Design, workers: int) -> tuple[np.ndarray, np.ndarray]:
    i_max = _i_max(d)
    angles = angle_grid(d.machine, _divisions(d), 2 * workers, aligned=0.0)
    return angles, np.array([i_max / 2, i_max])


def time_batch(static, d: Design, workers: int) -> dict:
    """One small cold map (about two angles per worker) through the process pool, with the workers' peak RAM."""
    angles, currents = batch_grid(d, workers)
    with WorkerRam(workers) as ram:
        t0 = time.perf_counter()
        run_map(static, d, angles, currents, solver_name="ngsolve", workers=workers)
        seconds = time.perf_counter() - t0
    points = len(angles) * len(currents)
    return {"workers": workers, "points": points, "seconds": seconds, "per_min": points / seconds * 60,
            "peak_ram_gb": ram.peak_gb}


def grid_points(d: Design) -> int:
    n_a, n_i = GRID_SIZES[d.mesh.preset]
    return len(angle_grid(d.machine, _divisions(d), n_a, aligned=0.0)) * len(current_grid(_i_max(d), n_i))


def _correctness(key_numbers: dict, statuses: dict, goldens: dict | None) -> dict:
    if goldens is None:
        return {"status": "not checked", "details": []}
    details = []
    for name, want in goldens["key_numbers"].items():
        got = key_numbers[name]
        if abs(got - want) > KEY_RTOL * abs(want) + 1e-12:
            details.append(f"{name}: got {got:.8g}, want {want:.8g}")
    for name, want in goldens["statuses"].items():
        if statuses.get(name) != want:
            details.append(f"check {name}: got {statuses.get(name)}, want {want}")
    return {"status": "fail" if details else "pass", "details": details}


def map_run(d: Design, workers: int, goldens: dict | None):
    """Build and analyse the design's map. Returns (summary dict, MapResult); the result feeds `extras_run`."""
    t0 = time.perf_counter()
    result = build_map(d, _i_max(d), workers=workers)
    report = analyse_map(result, d)
    seconds = time.perf_counter() - t0
    key_numbers = {k: float(v) for k, v in dataclasses.asdict(report.key_numbers).items()}
    statuses = {c.name: c.status for c in report.checks}
    summary = {"seconds": seconds, "points": int(result.status.size), "key_numbers": key_numbers,
               "statuses": statuses, "correctness": _correctness(key_numbers, statuses, goldens)}
    return summary, result


def extras_run(d: Design, result, workers: int) -> dict:
    t0 = time.perf_counter()
    build_overlap_map(d, _i_max(d), workers=workers)
    fem_checks(d, result, workers=workers)
    return {"seconds": time.perf_counter() - t0}


def sustained(static, d: Design, workers: int, minutes: float, clock=time.monotonic) -> dict:
    """Repeat `time_batch` for `minutes`; throttle is the change in rate from the first to the last 20 % of
    the batches, in percent (negative when the machine slowed down)."""
    start = clock()
    batches = []
    while True:
        r = time_batch(static, d, workers)
        batches.append({"t": clock() - start, "per_min": r["per_min"]})
        if clock() - start >= minutes * 60:
            break
    if len(batches) < 2:
        return {"batches": batches, "throttle_pct": 0.0}
    k = max(1, round(THROTTLE_FRACTION * len(batches)))
    first = statistics.fmean(b["per_min"] for b in batches[:k])
    last = statistics.fmean(b["per_min"] for b in batches[-k:])
    return {"batches": batches, "throttle_pct": (last / first - 1) * 100}


def load_reference(name: str) -> dict:
    return json.loads(resources.files("srmbench.reference").joinpath(name).read_text(encoding="utf-8"))


def make_reference() -> None:
    d = design("8_6", "screening")
    static, _ = static_mesh(d)
    data = {"srmcore": metadata.version("srmcore"), "points": reference_points(static, d)}
    path = resources.files("srmbench.reference").joinpath("points_8_6.json")
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    if sys.argv[1:] == ["make-reference"]:
        make_reference()
    else:
        sys.exit("usage: python -m srmbench.workload make-reference")
