"""Generate the FEMM 4.2 cross-tool fixtures (spec docs/superpowers/specs/2026-10-04-m5c-femm-design.md).

Windows only; needs FEMM 4.2 and pyfemm (`.venv\\Scripts\\python -m pip install pyfemm`, not a declared
dependency). Run from the repo root with the test helpers on the path:

    $env:PYTHONPATH="tests"; .venv\\Scripts\\python tools\\femm_fixtures.py krishnan_8_6 --level 2 --workers 7

Each point is drawn from srmcore's own outline with the rotor at the snapped angle and solved at mesh
levels F-1 and F, each in two models: a meshed-gap model (ψ, weighted-stress-tensor torque) and an
air-gap-element model (primary torque). Output: tests/validation/fixtures/femm_<machine>.json.
"""
import argparse
import datetime
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version
from pathlib import Path

import numpy as np

import femm_machines as fm
from srmcore.materials.laws import MU0, library_law
from srmcore.topology.primitives import Line, rotate
from srmcore.topology.radial import build_outline

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "validation" / "fixtures"
WORK = ROOT / "tools" / "femm_work"          # FEMM scratch documents (git-ignored)
MM = 1000.0
KRISHNAN_BORE_MM = 50.3                      # reference size for the iron and slot-air element sizes
CONVERGENCE_LIMIT = 0.005                    # level F-1 → F: ψ relative, torque in fractions of peak
PROBE_LIMIT = 0.001

try:
    import femm
except ImportError:
    femm = None


def level_sizes(p, level: int) -> dict[str, float]:
    """Element sizes in mm; each level halves all of them."""
    f = 2.0 ** -level
    scale = p.bore_radius * MM / KRISHNAN_BORE_MM
    return {"gap": p.air_gap * MM / 3 * f, "iron": 1.5 * scale * f, "slot_air": 3.0 * scale * f}


def _arc(seg, maxseg_len, fn):
    s, e, c = (np.array(fn(q)) * MM for q in (seg.start, seg.end, seg.center))
    r = float(np.hypot(*(s - c)))
    v1, v2 = s - c, e - c
    sweep = math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1 @ v2))
    if sweep < 0:                    # FEMM draws counter-clockwise from the first point
        s, e, sweep = e, s, -sweep
    femm.mi_drawarc(s[0], s[1], e[0], e[1], sweep, min(math.degrees(maxseg_len / r), sweep))


def _seg(seg, maxseg_len, fn):
    if isinstance(seg, Line):
        s, e = (np.array(fn(q)) * MM for q in (seg.start, seg.end))
        femm.mi_drawline(s[0], s[1], e[0], e[1])
    else:
        _arc(seg, maxseg_len, fn)


def _circle(r, maxseg_deg, prop=""):
    femm.mi_drawarc(r, 0, -r, 0, 180, maxseg_deg)
    femm.mi_drawarc(-r, 0, r, 0, 180, maxseg_deg)
    if prop:
        for x, y in ((0, r), (0, -r)):
            femm.mi_selectarcsegment(x, y)
            femm.mi_setarcsegmentprop(maxseg_deg, prop, 0, 0)
            femm.mi_clearselected()


def _label(x, y, mat, size, circuit="<None>", group=0, turns=0):
    femm.mi_addblocklabel(x, y)
    femm.mi_selectlabel(x, y)
    femm.mi_setblockprop(mat, 0, size, circuit, 0, group, turns)
    femm.mi_clearselected()


def _polar(r, a):
    return r * math.cos(a), r * math.sin(a)


def solve(name: str, theta: float, current: float, level: int, age: bool, tag: str) -> dict:
    """One FEMM solve of machine `name` with the rotor at `theta` (rad, counter-clockwise) and phase A
    at `current` (A). `age` selects the air-gap-element model."""
    d = fm.design(name)
    p = d.machine
    out = build_outline(p)
    sz = level_sizes(p, level)
    hg, hi, ha = sz["gap"], sz["iron"], sz["slot_air"]
    rr = p.rotor_outer_radius * MM
    r1, r2 = rr + p.air_gap * MM / 3, rr + 2 * p.air_gap * MM / 3

    femm.newdocument(0)
    femm.mi_probdef(0, "millimeters", "planar", 1e-9, p.stack_length * MM, 30)
    femm.mi_smartmesh(0)
    femm.mi_addmaterial("Air", 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0)
    for mat in fm._iron_materials(d):
        femm.mi_addmaterial(mat, 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0)     # LamFill 1
        for b, h in zip(*fm.bh_table(mat)):
            femm.mi_addbhpoint(mat, float(b), float(h))
    phases = [chr(ord("A") + k) for k in range(p.n_phases)]
    for ph in phases:
        femm.mi_addcircprop(ph, current if ph == "A" else 0.0, 1)
    femm.mi_addboundprop("A0", 0, 0, 0, 0, 0, 0, 0, 0, 0)
    if age:
        femm.mi_addboundprop("AGE", 0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 0)

    ident = lambda q: q  # noqa: E731
    rot = lambda q: rotate(q, theta)  # noqa: E731
    ro = out.stator_outer_radius * MM
    _circle(ro, math.degrees(hi / ro), "A0")
    for seg in out.stator_inner_boundary:
        _seg(seg, hg if seg.tag.endswith("pole_tip") else hi, ident)
    for side in out.coil_sides:
        for seg in side.boundary:
            _seg(seg, hi, ident)
    for seg in out.rotor_outer_boundary:
        _seg(seg, hg if seg.tag.endswith("pole_tip") else hi, rot)
    rs = out.shaft_radius * MM
    _circle(rs, math.degrees(hi / rs))
    mg = math.degrees(hg / rr)
    _circle(r1, mg, "AGE" if age else "")
    _circle(r2, mg, "AGE" if age else "")

    m = p.materials
    half_rotor_pitch = math.pi / p.n_rotor_poles
    _label(*_polar((p.stator_outer_radius - p.stator_yoke_thickness / 2) * MM, 0.0), m.stator, hi)
    _label(*_polar((p.shaft_radius + p.rotor_yoke_thickness / 2) * MM, theta + half_rotor_pitch), m.rotor, hi, group=1)
    _label(0.5 * rs, 0.0, m.shaft, hi, group=1)
    # interpolar rotor air, connected to the inner gap layer
    _label(*_polar((p.rotor_yoke_outer_radius + p.rotor_outer_radius) / 2 * MM, theta + half_rotor_pitch), "Air", ha)
    _label(*_polar((r1 + r2) / 2, 0.1 * half_rotor_pitch), "<No Mesh>" if age else "Air", hg)
    # stator slot air, between the bore and the coils on the slot centre line
    _label(*_polar((p.bore_radius + p.coil_inner_clearance / 2) * MM, math.pi / p.n_stator_poles), "Air", ha)
    for side in out.coil_sides:
        cx, cy = (np.array([s.start for s in side.boundary]) * MM).mean(axis=0)
        _label(cx, cy, "Air", hi, phases[side.phase], 0, side.sign * p.turns_per_pole)

    femm.mi_saveas(str(WORK / f"{tag}.fem"))
    femm.mi_analyze(1)
    femm.mi_loadsolution()
    femm.mo_smooth("off")
    res = {"psi": float(np.real(femm.mo_getcircuitproperties("A")[2])), "nodes": int(femm.mo_numnodes())}
    if age:
        res["torque"] = float(np.real(femm.mo_gapintegral("AGE", 0)))
    else:
        femm.mo_groupselectblock(1)
        res["torque"] = float(np.real(femm.mo_blockintegral(22)))
        femm.mo_clearblock()
    return res


def probe_bh(name: str) -> float:
    """Largest relative deviation of FEMM's H from the srmcore law at element-constant points along the
    phase-A stator pole axis and stator yoke (call right after a meshed-gap solve; air points skipped)."""
    d = fm.design(name)
    p = d.machine
    law = library_law(p.materials.stator)
    worst = 0.0
    radii = np.linspace(p.bore_radius + 0.0005, p.stator_outer_radius - 0.0005, 40) * MM
    for r in radii:
        v = femm.mo_getpointvalues(r, 0.0)
        b = math.hypot(np.real(v[1]), np.real(v[2]))
        h = math.hypot(np.real(v[5]), np.real(v[6]))
        if b < 0.05 or abs(h * MU0 / b - 1) < 0.01:       # air or near-zero field
            continue
        worst = max(worst, abs(h / float(law.h_of_b(np.array([b]))[0]) - 1))
    return worst


_opened = False


def _init_worker():
    global _opened
    WORK.mkdir(parents=True, exist_ok=True)
    femm.openfemm(1)
    femm.smartmesh(0)
    _opened = True


def solve_point(args) -> dict:
    name, k, theta, current, level = args
    tag = f"{name}_{os.getpid()}_{k}"
    out = {}
    for lv, key in ((level - 1, "_prev"), (level, "")):
        mg = solve(name, theta, current, lv, False, tag)
        ag = solve(name, theta, current, lv, True, tag)
        out["psi" + key], out["torque_wst" + key] = mg["psi"], mg["torque"]
        out["torque_age" + key], out["psi_age" + key], out["nodes" + key] = ag["torque"], ag["psi"], mg["nodes"]
    return out


def _probe(name: str, level: int) -> float:
    d = fm.design(name)
    i_max = fm.currents(d.machine)[-1]
    solve(name, 0.0, i_max, level, False, f"{name}_probe")
    return probe_bh(name)


def convergence_failures(points: list[dict]) -> list[str]:
    """Points whose level F-1 → F change exceeds CONVERGENCE_LIMIT (ψ relative, torque of peak)."""
    peak: dict[float, float] = {}
    for q in points:
        peak[q["current"]] = max(peak.get(q["current"], 0.0), abs(q["torque_age"]))
    bad = []
    for q in points:
        dpsi = abs(q["psi"] - q["psi_prev"]) / abs(q["psi"])
        dt = abs(q["torque_age"] - q["torque_age_prev"]) / peak[q["current"]]
        if dpsi > CONVERGENCE_LIMIT or dt > CONVERGENCE_LIMIT:
            bad.append(f"angle {q['angle']:.5f} i {q['current']}: dpsi {dpsi:.4%}, dT {dt:.4%} of peak")
    return bad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("machine", choices=list(fm.MACHINES))
    ap.add_argument("--level", type=int, default=2, help="finest mesh level F (>= 1); F-1 is solved too")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    ap.add_argument("--only", type=int, default=0, help="solve only the first K points (smoke test)")
    a = ap.parse_args()
    if femm is None:
        sys.exit("pyfemm is missing: .venv\\Scripts\\python -m pip install pyfemm (Windows, FEMM 4.2)")
    if a.level < 1:
        sys.exit("--level must be >= 1 (the convergence estimate needs level F-1)")
    name = a.machine
    d = fm.design(name)
    pts = fm.points(d)[: a.only or None]
    jobs = [(name, k, th, i, a.level) for k, (th, i) in enumerate(pts)]
    with ProcessPoolExecutor(a.workers, initializer=_init_worker) as pool:
        probe = pool.submit(_probe, name, a.level).result()
        print(f"B-H probe: max relative deviation {probe:.4%}", flush=True)
        if probe > PROBE_LIMIT:
            sys.exit(f"B-H probe deviation {probe:.4%} above {PROBE_LIMIT:.2%}")
        results = []
        for (th, i), r in zip(pts, pool.map(solve_point, jobs)):
            q = {"angle": th, "current": i, "tolerance": fm.tolerance(d, th, i), **r}
            print(f"{math.degrees(th):7.3f} deg {i:7.2f} A  psi {q['psi']:.6f}  T_age {q['torque_age']:+.5f}  "
                  f"T_wst {q['torque_wst']:+.5f}  nodes {q['nodes']}", flush=True)
            results.append(q)
    bad = [] if a.only else convergence_failures(results)
    if bad:
        sys.exit("FEMM not converged at level %d:\n  %s" % (a.level, "\n  ".join(bad)))
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    fixture = {
        "provenance": {
            "machine": name, "design_json": d.model_dump_json(), "design_sha256": fm.design_sha256(d),
            "bh_sha256": fm.bh_sha256(d), "assumed": fm.ASSUMED[name],
            "srmcore_version": version("srmcore"), "pyfemm_version": version("pyfemm"),
            "femm": "FEMM 4.2 (C:\\femm42)", "level": a.level,
            "sizes_mm": level_sizes(d.machine, a.level), "bh_probe_max_rel_dev": probe,
            "date": datetime.date.today().isoformat(), "git_commit": commit,
        },
        "points": results,
    }
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / (f"femm_{name}_partial.json" if a.only else f"femm_{name}.json")
    path.write_text(json.dumps(fixture, indent=1) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
