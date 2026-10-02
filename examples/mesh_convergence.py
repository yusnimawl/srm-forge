"""Mesh-convergence study runner.

usage: python examples/mesh_convergence.py run <design> <k...>     (refinement levels, scale = 2**(-k/2))
       python examples/mesh_convergence.py run-presets <design>    (screening, full and reference)
       python examples/mesh_convergence.py split <design>          (held-out error split of the stock full map)
       python examples/mesh_convergence.py report                  (fit, write docs/m5a-convergence.md and PNGs)
designs: 8_6, 8_6_sharp, 12_8, 24_16
The data directory is docs/m5a-data unless the environment variable M5A_DATA names another; report then writes
the markdown into that directory instead of docs/.
Every run row pins the band divisions to a multiple of B = lcm(Ns, 2 Nr, 12 Nr) so the study angles sit on the
band grid; preset rows use the nearest B-multiple to the stock division (within B/2 of it).

run and run-presets append one JSON line per level to docs/m5a-data/convergence.jsonl. Peak memory is the
process running maximum, so run each level in its own process for clean per-level numbers. split uses the
stock full settings and appends one line to docs/m5a-data/split.jsonl.
"""
import json
import math
import os
import sys
import tempfile
import time
import warnings
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

DATA = Path(os.environ.get("M5A_DATA", ROOT / "docs" / "m5a-data"))
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


def on_pitch_midpoints(angles, tau, pitch, n):
    """n angles on the band pitch, one per chosen grid interval (wrap interval included): the pitch multiple
    nearest the interval mid-point (down on a tie) strictly inside the interval; intervals with no interior
    pitch point are skipped."""
    ang = np.append(angles, angles[0] + tau)
    found = []
    for lo, hi in zip(ang[:-1], ang[1:]):
        k_lo, k_hi = round(lo / pitch), round(hi / pitch)
        if k_hi - k_lo < 2:
            continue
        k = min(max(math.ceil((lo + hi) / 2 / pitch - 0.5 - 1e-9), k_lo + 1), k_hi - 1)
        found.append(k * pitch)
    return _spread(found, n)


def run_split(name, machine, solver):
    """Held-out error of the stock full map split into angle, current and band-noise parts. angle_only is the
    pure angle-interpolation error (points on the band pitch), band is the off-pitch noise; together they
    bound what the held-out torque check of fem_checks sees. current_only uses grid angles (on pitch)."""
    smoke = os.environ.get("M5A_SMOKE") == "1"
    n_samples = 2 if smoke else 8
    n_pitches = 1 if smoke else 4
    design = Design(machine=machine, mesh=MeshSettings(preset="full"))
    i_max = find_i_max(name, machine, solver)
    tau = 2 * math.pi / machine.n_rotor_poles
    t0 = time.perf_counter()
    result = build_map(design, i_max, workers=None, cache_dir=Path(tempfile.gettempdir()) / "m5a-map-cache",
                       **(dict(n_angles=8, n_currents=4) if smoke else {}))
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

    pitch = 2 * math.pi / resolve_mesh_settings(machine, design.mesh).band_divisions
    mid_angles = on_pitch_midpoints(result.angles, tau, pitch, n_samples)
    cur = result.currents[result.currents > 0]
    mid_currents = _spread(list((cur[:-1] + cur[1:]) / 2), 3 if not smoke else 2)

    def near(target):
        return float(result.currents[np.argmin(abs(result.currents - target))])

    grid_currents = sorted({near(LA_CURRENT_FRACTION * i_max), near(i_max / 2), float(result.currents[-1])})
    angle_only = [error(a, i) for a in mid_angles for i in grid_currents]
    current_only = [error(float(a), i) for a in _spread(list(result.angles), n_samples) for i in mid_currents]

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


TARGETS = {"screening": (2.0, 3.0), "full": (0.5, 1.0), "reference": (0.1, 0.2)}  # percent: (psi/W', torque)
PRESETS = tuple(TARGETS)
TORQUE_STATES = ("tau/12_imax", "tau/6_imax")
GROUPS = ("psi", "t_ark", "t_vw", "wc")


def load_records():
    """Last line wins per (design, level); returns {design: {level: record}}."""
    out = {}
    path = DATA / "convergence.jsonl"
    for line in path.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            out.setdefault(rec["design"], {})[rec["level"]] = rec
    return out


def load_splits():
    path = DATA / "split.jsonl"
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                out[rec["design"]] = rec
    return out


def quantity_values(rec):
    """{(group, state): value} for one record."""
    q = {}
    for row in rec["rows"]:
        q["psi", row["state"]] = row["psi"]
        if row["state"] in TORQUE_STATES:
            q["t_ark", row["state"]] = row["t_ark"]
            q["t_vw", row["state"]] = row["t_vw"]
        if row["state"] == "aligned_imax":
            q["wc", row["state"]] = row["wc"]
    return q


def fit_series(h, q):
    """Fit q = qinf + C h^p; h ordered coarse to fine. Returns dict(qinf, p, rms, flag, bound)."""
    from scipy.optimize import OptimizeWarning, curve_fit

    h, q = np.asarray(h, float), np.asarray(q, float)
    bound = 3 * abs(q[-1] - q[-2]) if len(q) > 1 else float("nan")
    d = np.diff(q)
    d[np.abs(d) <= 1e-12 * np.max(np.abs(q))] = 0.0
    res = dict(qinf=float(q[-1]), p=float("nan"), rms=float("nan"), flag="", bound=bound)
    if not d.any():
        res["bound"] = 0.0
        return res
    monotone = bool(np.all(d > 0) or np.all(d < 0))
    if len(h) < 4:
        res["flag"] = "insufficient levels"
        return res
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", OptimizeWarning)
            popt, _ = curve_fit(lambda x, qi, c, p: qi + c * x ** p, h, q, p0=(q[-1], q[0] - q[-1], 1.5),
                                maxfev=20000)
    except RuntimeError:
        res["flag"] = "fit failed"
        return res
    res.update(p=float(popt[2]), rms=float(np.sqrt(np.mean((popt[0] + popt[1] * h ** popt[2] - q) ** 2))))
    flags = []
    if not 0.5 <= popt[2] <= 3:
        flags.append("p out of range")
    if not monotone:
        flags.append("non-monotone")
    res["flag"] = ", ".join(flags)
    if not flags:
        res["qinf"] = float(popt[0])
    return res


def analyse_design(recs):
    """Fits and errors (fractions) for one design. errors[(group, state)] = {level_or_preset: error}."""
    levels = sorted((k for k in recs if not isinstance(k, str)), key=lambda k: recs[k]["scale"], reverse=True)
    finest = recs[levels[-1]] if levels else None
    vals = {k: quantity_values(r) for k, r in recs.items()}
    peak = max((abs(vals[levels[-1]][g, s]) for g in ("t_ark",) for s in TORQUE_STATES
                if (g, s) in vals[levels[-1]]), default=float("nan")) if levels else float("nan")
    out = {}
    for key in vals[levels[-1]] if levels else {}:
        lv = [k for k in levels if key in vals[k]]
        h = [recs[k]["scale"] for k in lv]
        f = fit_series(h, [vals[k][key] for k in lv]) if len(lv) > 1 else None
        if f is None:
            continue
        flagged = bool(f["flag"])
        norm = peak if key[0] in ("t_ark", "t_vw") else abs(f["qinf"])
        err = {k: (abs(vals[k][key] - f["qinf"]) + (f["bound"] if flagged else 0.0)) / norm
               for k in recs if key in vals[k]}
        out[key] = dict(fit=f, err=err, norm=norm)
    return dict(levels=levels, finest=finest, peak=peak, q=out, vals=vals)


def worst(analysis, keys, who):
    """Worst error over the quantities in keys for level/preset `who` (nan if none)."""
    e = [v["err"][who] for k, v in analysis["q"].items() if k[0] in keys and who in v["err"]]
    return nanmax(e)


def nanmax(values):
    v = [x for x in values if x == x]
    return max(v) if v else float("nan")


def plots(name, recs, analysis):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    levels = analysis["levels"]
    nodes = [recs[k]["nodes"] for k in levels]
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for g in GROUPS:
        ax.loglog(nodes, [max(worst(analysis, (g,), k), 1e-16) for k in levels], "o-", label=g)
        for p in PRESETS:
            if p in recs:
                ax.loglog([recs[p]["nodes"]], [max(worst(analysis, (g,), p), 1e-16)], "x", color="gray")
    ax.set(xlabel="nodes", ylabel="worst |error| (fraction)", title=f"{name}: error vs nodes (x = presets)")
    ax.legend()
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(DATA / f"convergence_{name}.png", dpi=120)
    plt.close(fig)
    return levels


def gap_plot(all_analyses, all_recs):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 4.5))
    for name, an in all_analyses.items():
        recs = all_recs[name]
        keys = [(g, s) for g in ("t_ark",) for s in TORQUE_STATES]
        xs, ys = [], []
        for k in an["levels"] + [p for p in PRESETS if p in recs]:
            gaps = [abs(an["vals"][k][("t_ark", s)] - an["vals"][k][("t_vw", s)]) / an["peak"]
                    for _, s in keys if ("t_ark", s) in an["vals"][k]]
            if gaps:
                xs.append(recs[k]["nodes"])
                ys.append(max(max(gaps), 1e-16))
        order = np.argsort(xs)
        ax.loglog(np.array(xs)[order], np.array(ys)[order], "o-", label=name)
    ax.set(xlabel="nodes", ylabel="|T_ark - T_vw| / peak", title="Arkkio vs virtual-work gap")
    ax.legend()
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(DATA / "convergence_torque_gap.png", dpi=120)
    plt.close(fig)


def pct(x):
    return "n/a" if x != x else f"{100 * x:.4g}"


def report_path():
    return DATA / "m5a-convergence.md" if "M5A_DATA" in os.environ else ROOT / "docs" / "m5a-convergence.md"


def report():
    recs_all = load_records()
    splits = load_splits()
    out = report_path()
    names = [n for n in DESIGNS if n in recs_all]
    analyses = {n: analyse_design(recs_all[n]) for n in names if any(not isinstance(k, str) for k in recs_all[n])}
    md = ["# M5a mesh convergence study", "",
          "Generated by `examples/mesh_convergence.py report`. Errors are percent.", "",
          "## Method", "",
          "Per design and quantity the k-level series (h = scale) is fitted with q = qinf + C h^p by least squares "
          "(`scipy.optimize.curve_fit`). psi and W' errors are relative to |qinf|; torque errors are relative to the "
          "design's peak torque at I_max (largest |T_ark| of the finest level at tau/12 and tau/6). Torque is fitted "
          "at I_max only. A quantity is flagged when p is outside [0.5, 3], the series is not monotone, the fit "
          "fails, or fewer than 4 levels exist. For a flagged quantity qinf = q_finest, the GCI-style bound is "
          "U = 3 x |q_finest - q_second| (normalised like the errors), and the error of every row (each level "
          "including the finest, and each preset) is |q - q_finest| / norm + U. A series whose successive "
          "differences are all below 1e-12 of its magnitude counts as converged (qinf = q_finest, U = 0, not "
          "flagged). A quantity present at only one level is dropped. Each design/level appears once (the last "
          "run wins).", ""]

    def link(file):
        return os.path.relpath(DATA / file, out.parent).replace("\\", "/")

    for name in names:
        recs = recs_all[name]
        an = analyses.get(name)
        md += [f"## Design {name}", "", f"I_max = {recs[next(iter(recs))]['i_max']:g} A", ""]
        md += ["| level | scale | nodes | elements | band divisions | mesh s | peak GB |", "|---|---|---|---|---|---|---|"]
        order = (an["levels"] if an else []) + [p for p in PRESETS if p in recs]
        for k in order:
            r = recs[k]
            md.append(f"| {k} | {r['scale']:.4g} | {r['nodes']} | {r['elements']} | {r['divisions']} | "
                      f"{r['mesh_s']:.1f} | {r['peak_gb']:.2f} |")
        md.append("")
        if not an:
            continue
        md += [f"Peak torque at I_max: {an['peak']:.6g} N m", ""]
        cols = an["levels"] + [p for p in PRESETS if p in recs]
        md += ["| quantity | state | p | qinf | fit rms | flag | " + " | ".join(str(k) for k in cols) + " |",
               "|" + "---|" * (6 + len(cols))]
        for (g, s), v in an["q"].items():
            f = v["fit"]
            md.append(f"| {g} | {s} | {f['p']:.3f} | {f['qinf']:.6g} | {f['rms']:.3g} | {f['flag'] or '-'} | " +
                      " | ".join(pct(v["err"].get(k, float("nan"))) for k in cols) + " |")
        md.append("")
        plots(name, recs, an)
        md += [f"![{name}]({link(f'convergence_{name}.png')})", ""]
    if analyses:
        gap_plot(analyses, {n: recs_all[n] for n in analyses})
        md += [f"![gap]({link('convergence_torque_gap.png')})", ""]
        md += ["## Summary against targets", "",
               "Worst error over all designs and quantities. Target columns are the spec section 5 values; "
               "pass is against the target, margin against target/2.", "",
               "| preset | psi/W' worst | target | pass | margin | torque worst | target | pass | margin |",
               "|---|---|---|---|---|---|---|---|---|"]
        for p in PRESETS:
            have = [a for n, a in analyses.items() if p in recs_all[n]]
            w = [nanmax(worst(a, g, p) for a in have) for g in (("psi", "wc"), ("t_ark", "t_vw"))]
            cells = []
            for val, tgt in zip(w, TARGETS[p]):
                v = 100 * val
                cells += [pct(val), f"{tgt:g}", "n/a" if v != v else "pass" if v <= tgt else "FAIL",
                          "n/a" if v != v else "pass" if v <= tgt / 2 else "FAIL"]
            md.append(f"| {p} | " + " | ".join(cells) + " |")
        md += ["", "| level | psi/W' worst | torque worst |", "|---|---|---|"]
        ks = sorted({k for a in analyses.values() for k in a["levels"]}, key=float)
        for k in ks:
            ws = [a for a in analyses.values() if k in a["levels"]]
            md.append(f"| {k} | " + " | ".join(pct(nanmax(worst(a, g, k) for a in ws)) for g in
                                                (("psi", "wc"), ("t_ark", "t_vw"))) + " |")
        md.append("")
    if splits:
        md += ["## Grid-error split (full preset)", "",
               "| design | angle-only psi | angle-only torque | current-only psi | current-only torque | band rms |",
               "|---|---|---|---|---|---|"]
        for n, s in splits.items():
            md.append(f"| {n} | {pct(max(r['err_psi'] for r in s['angle_only']))} | "
                      f"{pct(max(r['err_t'] for r in s['angle_only']))} | "
                      f"{pct(max(r['err_psi'] for r in s['current_only']))} | "
                      f"{pct(max(r['err_t'] for r in s['current_only']))} | {pct(s['band']['rms_residual'])} |")
        md.append("")
    out.write_text("\n".join(md), encoding="utf-8")
    print("wrote", out)


def main(argv):
    if argv[:1] == ["report"]:
        report()
        return
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
