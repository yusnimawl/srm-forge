"""Mesh-convergence study runner.

usage: python examples/mesh_convergence.py run <design> <k...>     (refinement levels, scale = 2**(-k/2))
       python examples/mesh_convergence.py run-presets <design>    (screening, full and reference)
designs: 8_6, 8_6_sharp, 12_8, 24_16
Every row pins the band divisions to a multiple of B = lcm(Ns, 2 Nr, 12 Nr) so the study angles sit on the
band grid; preset rows use the nearest B-multiple to the stock division (within B/2 of it).

Appends one JSON line per level to docs/m5a-data/convergence.jsonl. Peak memory is the process
running maximum, so run each level in its own process for clean per-level numbers.
"""
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from conftest import make_8_6, make_12_8, make_24_16  # noqa: E402

from srmcore.fields.solution import SolveStatus  # noqa: E402
from srmcore.maps.grids import LA_CURRENT_FRACTION  # noqa: E402
from srmcore.maps.point import solve_point  # noqa: E402
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


def main(argv):
    if len(argv) < 2 or argv[1] not in DESIGNS or argv[0] not in ("run", "run-presets") \
            or (argv[0] == "run" and len(argv) < 3):
        raise SystemExit(__doc__)
    mode, name = argv[0], argv[1]
    machine = DESIGNS[name]()
    global BASELINE_GB
    BASELINE_GB = peak_gb()
    solver = make_solver("ngsolve")
    if mode == "run":
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
