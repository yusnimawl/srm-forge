"""FE sweep of rotor geometries behind the root and bore constants of srmcore.post.rotor_stress (docs/r5-sources.md
section 5). Run from the repository root with PYTHONPATH=src;tests;tests/post:

    python tools/rotor_stress_sweep.py lattice OUT.json       # the derivation lattice, about 15 min on 16 cores
    python tools/rotor_stress_sweep.py fit LATTICE.json       # print the constants
    python tools/rotor_stress_sweep.py heldout SEED OUT.json  # the held-out design list, no FE
    python tools/rotor_stress_sweep.py solve DESIGNS.json OUT.json   # FE of a design list
    python tools/rotor_stress_sweep.py check SWEEP.json ...   # errors of the model against the FE
"""
import argparse
import itertools
import json
import math
import multiprocessing
import os

import numpy as np
from scipy.optimize import least_squares
from scipy.stats import qmc

from conftest import make_8_6
from rotor_elastic_fe import E, NU, OMEGA, RHO, sweep_point
from srmcore.materials.library import load_material
from srmcore.post import rotor_stress as rs
from srmcore.topology.radial import _pole_side

RADIUS = 0.5                  # large, so the absolute web margin of the outline is no limit: stresses scale with R^2
PHASES = {4: 3, 6: 4, 8: 3, 12: 3, 16: 3}
RANGES = (rs._FIT_SHAFT, rs._FIT_ARC, rs._FIT_YOKE, rs._FIT_TAPER, rs._FIT_FILLET)
CENTRE = (0.5, 0.5, 0.5, 0.5, 0.5)
MECH = load_material("10JNEX900").mechanical.model_copy(update={"poisson_ratio": NU, "youngs_modulus": E})


def design(n_poles, u):
    """Design values at the unit coordinates `u` of the box; the fillet coordinate is logarithmic."""
    ratios = [lo + x * (hi - lo) for x, (lo, hi) in zip(u[:4], RANGES)]
    shaft, arc_ratio, yoke_ratio, taper = ratios
    arc = 2 * math.pi / (PHASES[n_poles] * n_poles) * arc_ratio
    yoke = 2 * RADIUS * math.sin(arc / 2) * yoke_ratio
    base = dict(n_rotor_poles=n_poles, n_phases=PHASES[n_poles], rotor_outer_diameter=2 * RADIUS,
                shaft_diameter=2 * RADIUS * shaft, rotor_pole_arc=arc, rotor_yoke_thickness=yoke,
                rotor_pole_taper=math.radians(taper), rotor_fillet_radius=0.0)
    if RADIUS * shaft + yoke >= 0.99 * RADIUS:
        return None
    lo, hi = rs._FIT_FILLET
    d = 2 * rs.pole_half_width(make_8_6(**base), RADIUS * shaft + yoke)
    return {**base, "rotor_fillet_radius": lo * (hi / lo)**u[4] * d}


def usable(values) -> bool:
    """The design builds and reads inside the validity box."""
    if values is None:
        return False
    m = make_8_6(**values)
    try:
        _pole_side(m.rotor_outer_radius, m.rotor_pole_arc, m.rotor_pole_taper, m.rotor_yoke_outer_radius,
                   m.rotor_fillet_radius, False, 2 * math.pi / m.n_rotor_poles)
    except ValueError:
        return False
    return rs._outside_fit(m) is None


def to_boundary(n_poles, u):
    """The usable point nearest `u` on the line from the box centre: `u` itself when usable, else on a joint limit."""
    u, centre = np.array(u, float), np.array(CENTRE)
    if usable(design(n_poles, u)):
        return design(n_poles, u)
    inside, outside = 0.0, 1.0
    if not usable(design(n_poles, centre)):
        return None
    for _ in range(40):
        mid = (inside + outside) / 2
        if usable(design(n_poles, centre + mid * (u - centre))):
            inside = mid
        else:
            outside = mid
    return design(n_poles, centre + inside * (u - centre))


def lattice_designs():
    grid = (np.linspace(0, 1, 5), np.linspace(0, 1, 6), np.linspace(0, 1, 6), (0.0, 0.5, 1.0), np.linspace(0, 1, 7))
    jobs = []
    for n_poles in PHASES:
        for u in itertools.product(*grid):
            values = to_boundary(n_poles, u)
            if values is not None:
                jobs.append(values)
    return jobs


def heldout_designs(seed):
    """Every corner of the box, moved along the line to the centre onto a joint limit where it is outside them; the
    corners of the taper 0 plane; random rays from the centre to the boundary; random interior points."""
    labelled = []
    for n_poles in PHASES:
        rng = np.random.default_rng(seed * 100 + n_poles)
        for u in itertools.product((0.0, 1.0), repeat=5):
            labelled.append(("corner", to_boundary(n_poles, u)))
        for u in itertools.product((0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.5,), (0.0, 1.0)):
            labelled.append(("corner_taper0", to_boundary(n_poles, u)))
        for _ in range(60):
            direction = rng.normal(size=5)
            u = np.array(CENTRE) + direction * (0.5 / np.abs(direction).max())
            labelled.append(("boundary", to_boundary(n_poles, u)))
        for axis, end in itertools.product(range(5), (0.0, 1.0)):
            for _ in range(6):
                u = rng.random(5)
                u[axis] = end
                labelled.append(("face", to_boundary(n_poles, u)))
        for u in qmc.LatinHypercube(d=5, seed=seed * 100 + n_poles).random(200):
            values = design(n_poles, u)
            if usable(values):
                labelled.append(("interior", values))
    return [{"kind": kind, "params": values} for kind, values in labelled if values is not None]


def solve(jobs, out):
    os.environ.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    with multiprocessing.get_context("spawn").Pool(15) as pool:
        rows = pool.map(sweep_point, jobs, chunksize=8)
    with open(out, "w") as f:
        json.dump(rows, f, separators=(",", ":"))


def fit(path, target=1.05):
    """Near-minimax fit (eighth power of the log error) of the two constant sets against `target` x FE. Only designs
    inside the validity box take part."""
    with open(path) as f:
        rows = [row for row in json.load(f) if "skipped" not in row]
    machines = [make_8_6(**row["params"]) for row in rows]
    keep = [i for i, m in enumerate(machines) if rs._outside_fit(m) is None]
    machines = [machines[i] for i in keep]
    root = np.array([rows[i]["root"][-1] for i in keep])
    bore = np.array([rows[i]["bore"][-1] for i in keep])

    def root_error(c):
        rs._STEM_GAIN, rs._STEM_YOKE_SHARE, rs._STEM_PITCH_POWER, rs._SHOULDER_HEIGHT = c
        model = np.array([rs._root_peak(m, RHO, OMEGA, NU) for m in machines])
        return np.log(np.maximum(model, 1.0) / (target * root))**4

    def bore_error(c):
        rs._BORE_RIM_RELIEF, rs._BORE_BEND_GAIN = c
        return np.log(np.array([analytic_bore(m) for m in machines]) / (target * bore))**4

    for name, error, start in (("root", root_error, (rs._STEM_GAIN, rs._STEM_YOKE_SHARE, rs._STEM_PITCH_POWER,
                                                     rs._SHOULDER_HEIGHT)),
                               ("bore", bore_error, (rs._BORE_RIM_RELIEF, rs._BORE_BEND_GAIN))):
        result = least_squares(error, start, diff_step=1e-3)
        print(name, len(machines), "designs", np.round(result.x, 4), "worst log error", result.fun.max()**0.25)


def analytic_bore(machine):
    return rs.rotor_stress(machine, RHO, MECH, OMEGA * 60 / (2 * math.pi) / rs.OVERSPEED).bore_stress


def check(path):
    with open(path) as f:
        rows = [row for row in json.load(f) if "skipped" not in row]
    rpm = OMEGA * 60 / (2 * math.pi)
    errors, out = [], 0
    for row in rows:
        machine = make_8_6(**row["params"])
        st = rs.rotor_stress(machine, RHO, MECH, rpm / rs.OVERSPEED)
        if st.status != "ok":
            out += 1
            continue
        fe_root, fe_bore, fe_tip = row["root"][-1], row["bore"][-1], row["tip"][-1]
        tip = rs.gap_closure(machine, RHO, MECH, None, None, rpm, 20.0, 20.0).centrifugal
        errors.append((st.root_stress / fe_root - 1, st.bore_stress / fe_bore - 1, tip / fe_tip - 1,
                       max(st.root_stress, st.bore_stress) / row["peak"] - 1,
                       abs(row["root"][-1] / row["root"][-2] - 1), abs(row["bore"][-1] / row["bore"][-2] - 1)))
    e = 100 * np.array(errors)
    print(f"{path}: {len(e)} designs in the box, {out} outside")
    for i, name in enumerate(("root", "bore", "tip", "peak", "root conv", "bore conv")):
        print(f"  {name:10s} min {e[:, i].min():7.2f} % max {e[:, i].max():7.2f} %")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("lattice").add_argument("out")
    sub.add_parser("fit").add_argument("path")
    held = sub.add_parser("heldout")
    held.add_argument("seed", type=int)
    held.add_argument("out")
    solving = sub.add_parser("solve")
    solving.add_argument("designs")
    solving.add_argument("out")
    sub.add_parser("check").add_argument("sweeps", nargs="+")
    args = parser.parse_args()
    if args.command == "lattice":
        solve(lattice_designs(), args.out)
    elif args.command == "fit":
        fit(args.path)
    elif args.command == "heldout":
        with open(args.out, "w") as f:
            json.dump(heldout_designs(args.seed), f, indent=0)
    elif args.command == "solve":
        with open(args.designs) as f:
            items = json.load(f)
        solve([item["params"] for item in items], args.out)
    else:
        for path in args.sweeps:
            check(path)


if __name__ == "__main__":
    main()
