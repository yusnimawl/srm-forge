"""Mesh-convergence study runner.

usage: python examples/mesh_convergence.py run <design> <k...>     (refinement levels, scale = 2**(-k/2))
       python examples/mesh_convergence.py run-presets <design>    (screening, full and reference)
       python examples/mesh_convergence.py split <design>          (held-out error split of the stock full map)
designs: 8_6, 8_6_sharp, 12_8, 24_16
Every row pins the band divisions to a multiple of B = lcm(Ns, 2 Nr, 12 Nr) so the study angles sit on the
band grid; preset rows use the nearest B-multiple to the stock division (within B/2 of it).

Appends one JSON line per level to docs/m5a-data/convergence.jsonl. Peak memory is the process
running maximum, so run each level in its own process for clean per-level numbers.
"""
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from conftest import make_8_6, make_12_8, make_24_16  # noqa: E402

from srmcore.fields.solution import SolveStatus  # noqa: E402
from srmcore.maps.api import build_map  # noqa: E402
from srmcore.maps.grids import LA_CURRENT_FRACTION  # noqa: E402
from srmcore.maps.point import solve_point  # noqa: E402
from srmcore.maps.results import key_numbers  # noqa: E402
from srmcore.maps.tables import angle_spline  # noqa: E402
from srmcore.mesh import build_machine_mesh, mesh_at_angle  # noqa: E402
from srmcore.mesh.settings import resolve_mesh_settings  # noqa: E402
from srmcore.model.design import Design, MeshSettings  # noqa: E402
from srmcore.physics.build import machine_problem  # noqa: E402
from srmcore.post.quantities import saturation_report  # noqa: E402
from srmcore.solvers.factory import make_solver  # noqa: E402

DATA = ROOT / "docs" / "m5a-data"
DESIGNS = {
    "8_6": lambda: make_8_6(),
    "8_6_sharp": lambda: make_8_6(stator_fillet_radius=0, rotor_fillet_radius=0),
    "12_8": make_12_8,
    "24_16": make_24_16,
}
BASELINE_GB = 0.0
SATURATION_T = 2.0
I_MAX_CAP = 640.0


def peak_gb():
    if sys.platform == "win32":
        import ctypes
        import ctypes.wintypes as wt

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD)] + [
                (n, ctypes.c_size_t) for n in (
                    "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

        c = PMC()
        c.cb = ctypes.sizeof(c)
        k32 = ctypes.WinDLL("kernel32")
        k32.GetCurrentProcess.restype = wt.HANDLE
        k32.K32GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
        k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
        return c.PeakWorkingSetSize / 1e9
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1e9 if sys.platform == "darwin" else peak / 1e6


def find_i_max(name, machine, solver):
    """I_max for a design: 20 A for the 8/6 variants, else doubled from 5 A until the stator poles reach 2 T."""
    if name.startswith("8_6"):
        return 20.0
    DATA.mkdir(parents=True, exist_ok=True)
    cache = DATA / "i_max.json"
    known = json.loads(cache.read_text()) if cache.exists() else {}
    if name in known:
        return known[name]
    design = Design(machine=machine, mesh=MeshSettings(preset="screening"))
    static = build_machine_mesh(design)
    amps = 5.0
    while True:
        point = solve_point(static, design, 0.0, {"A": amps}, solver, keep_field=True)
        if point.status is SolveStatus.NONCONVERGED:
            raise SystemExit(f"i_max search {name}: solve did not converge at {amps} A")
        problem = machine_problem(mesh_at_angle(static, 0.0), design, {"A": amps})
        peak = saturation_report(problem, point.field, machine)["stator_poles"].peak
        print(f"i_max search {name}: {amps} A -> {peak:.3f} T", flush=True)
        if peak >= SATURATION_T:
            break
        if amps >= I_MAX_CAP:
            raise SystemExit(f"{name}: stator poles below {SATURATION_T} T at {amps} A")
        amps *= 2.0
    known[name] = amps
    cache.write_text(json.dumps(known, indent=1))
    return amps


def run_level(name, machine, solver, level, scale, settings):
    design = Design(machine=machine, mesh=settings)
    i_max = find_i_max(name, machine, solver)
    i_la = LA_CURRENT_FRACTION * i_max
    tau = 2 * math.pi / machine.n_rotor_poles
    states = [("aligned", 0.0, True), ("tau/12", tau / 12, True), ("tau/6", tau / 6, True),
              ("tau/2", tau / 2, False)]
    t0 = time.perf_counter()
    static = build_machine_mesh(design)
    mesh_s = time.perf_counter() - t0
    rows, nodes, elements = [], 0, 0
    for label, angle, with_i_max in states:
        for tag, amps in ((("imax", i_max),) if with_i_max else ()) + (("ila", i_la),):
            t = time.perf_counter()
            r = solve_point(static, design, angle, {"A": amps}, solver, keep_field=True)
            nodes, elements = len(r.field.a), len(r.field.b)
            rows.append(dict(state=f"{label}_{tag}", angle=r.angle, i=amps, psi=float(r.psi[0]),
                             t_ark=r.torque_arkkio, t_vw=r.torque_virtual_work, wc=r.coenergy,
                             status=r.status.value, it=r.iterations, s=time.perf_counter() - t))
            print(name, level, rows[-1]["state"], f"psi={rows[-1]['psi']:.5f}", rows[-1]["status"], flush=True)
    rec = dict(design=name, level=level, scale=scale,
               divisions=resolve_mesh_settings(machine, settings).band_divisions, nodes=nodes,
               elements=elements, mesh_s=mesh_s, baseline_gb=BASELINE_GB, peak_gb=peak_gb(), i_max=i_max, rows=rows)
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / "convergence.jsonl").open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(name, level, "nodes", nodes, "elements", elements, "mesh_s", round(mesh_s, 1),
          "peak_gb", round(rec["peak_gb"], 2), flush=True)


def pinned_settings(machine, preset, scale=1.0):
    """Settings whose band divisions are the nearest multiple of B to the resolved default."""
    d = resolve_mesh_settings(machine, MeshSettings(preset=preset, scale=scale)).band_divisions
    base = math.lcm(machine.n_stator_poles, 2 * machine.n_rotor_poles, 12 * machine.n_rotor_poles)
    return MeshSettings(preset=preset, scale=scale, airgap_circumferential_divisions=base * max(1, round(d / base)))


def _spread(items, n):
    """n items evenly chosen from a list, first and last included."""
    idx = sorted({round(k) for k in np.linspace(0, len(items) - 1, min(n, len(items)))})
    return [items[k] for k in idx]


def run_split(name, machine, solver):
    """Held-out error of the stock full map split into angle, current and band-noise parts."""
    smoke = os.environ.get("M5A_SMOKE") == "1"
    n_samples = 2 if smoke else 8
    n_pitches = 1 if smoke else 4
    design = Design(machine=machine, mesh=MeshSettings(preset="full"))
    i_max = find_i_max(name, machine, solver)
    tau = 2 * math.pi / machine.n_rotor_poles
    t0 = time.perf_counter()
    result = build_map(design, i_max, workers=None, **(dict(n_angles=8, n_currents=4) if smoke else {}))
    map_s = time.perf_counter() - t0
    print(name, "map built", result.psi.shape[:2], round(map_s, 1), "s", flush=True)
    key = key_numbers(result, machine)
    e = result.circuits.index(result.excited)
    psi_spl = angle_spline(result.angles, result.psi[..., e], tau)
    t_spl = angle_spline(result.angles, result.torque_arkkio, tau)
    static = build_machine_mesh(design)

    def error(angle, amps):
        r = solve_point(static, design, angle, {result.excited: amps}, solver)
        if r.status is SolveStatus.NONCONVERGED:
            raise SystemExit(f"{name}: held-out solve did not converge at {angle} rad, {amps} A")
        psi_i = float(PchipInterpolator(result.currents, psi_spl(angle))(amps))
        t_i = float(PchipInterpolator(result.currents, t_spl(angle))(amps))
        print(name, f"split angle={math.degrees(angle):.3f}deg i={amps:.3f}", flush=True)
        return dict(angle=float(angle), i=float(amps), err_psi=abs(float(r.psi[e]) - psi_i) / key.psi_max,
                    err_t=abs(r.torque_arkkio - t_i) / key.peak_torque)

    ang = np.append(result.angles, result.angles[0] + tau)
    mid_angles = _spread(list((ang[:-1] + ang[1:]) / 2), n_samples)
    cur = result.currents[result.currents > 0]
    mid_currents = _spread(list((cur[:-1] + cur[1:]) / 2), 3 if not smoke else 2)
    near = lambda target: float(result.currents[np.argmin(abs(result.currents - target))])
    grid_currents = sorted({near(LA_CURRENT_FRACTION * i_max), near(i_max / 2), float(result.currents[-1])})
    angle_only = [error(a, i) for a in mid_angles for i in grid_currents]
    current_only = [error(float(a), i) for a in _spread(list(result.angles), n_samples) for i in mid_currents]

    pitch = 2 * math.pi / resolve_mesh_settings(machine, design.mesh).band_divisions
    start = float(result.angles[np.argmin(abs(result.angles - tau / 6))])
    angles = [start + j * pitch / 8 for j in range(8 * n_pitches + 1)]
    torque = []
    for a in angles:
        r = solve_point(static, design, a, {result.excited: float(result.currents[-1])}, solver)
        if r.status is SolveStatus.NONCONVERGED:
            raise SystemExit(f"{name}: band-noise solve did not converge at {a} rad")
        torque.append(r.torque_arkkio)
    print(name, "band sweep done", flush=True)
    x, t = (np.array(angles) - start) / pitch, np.array(torque)
    on = np.arange(len(angles)) % 8 == 0
    fit = np.polyfit(x[on], t[on], min(3, int(on.sum()) - 1))
    rms = float(np.sqrt(np.mean((t[~on] - np.polyval(fit, x[~on])) ** 2)) / key.peak_torque)
    rec = dict(design=name, i_max=i_max, peak_torque=key.peak_torque, psi_max=key.psi_max,
               n_angles=len(result.angles), n_currents=len(result.currents), map_s=map_s,
               angle_only=angle_only, current_only=current_only,
               band=dict(pitch=pitch, angles=angles, torque=torque, rms_residual=rms))
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / "split.jsonl").open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(name, "split: max err_psi", max(r["err_psi"] for r in angle_only + current_only),
          "max err_t", max(r["err_t"] for r in angle_only + current_only), "band rms", rms, flush=True)


def main(argv):
    if len(argv) < 2 or argv[1] not in DESIGNS or argv[0] not in ("run", "run-presets", "split") \
            or (argv[0] == "run" and len(argv) < 3):
        raise SystemExit(__doc__)
    mode, name = argv[0], argv[1]
    machine = DESIGNS[name]()
    global BASELINE_GB
    BASELINE_GB = peak_gb()
    solver = make_solver("ngsolve")
    if mode == "split":
        run_split(name, machine, solver)
    elif mode == "run":
        for k in argv[2:]:
            k = float(k)
            scale = 2.0 ** (-k / 2)
            run_level(name, machine, solver, int(k) if k == int(k) else k, scale,
                      pinned_settings(machine, "screening", scale))
    else:
        for preset in ("screening", "full", "reference"):
            run_level(name, machine, solver, preset, 1.0, pinned_settings(machine, preset))


if __name__ == "__main__":
    main(sys.argv[1:])
