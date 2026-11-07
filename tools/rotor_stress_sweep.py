"""FE sweep of rotor geometries behind the root-stress correlation of srmcore.post.rotor_stress (docs/r5-sources.md
section 5). Run from the repository root with PYTHONPATH=src;tests;tests/post:

    python tools/rotor_stress_sweep.py run SEED N_PER_POLE_COUNT OUT.json [--poles 4 6 8 16]
    python tools/rotor_stress_sweep.py fit DERIVED.json    # print the constants
    python tools/rotor_stress_sweep.py check SWEEP.json ...   # errors of the model against the FE
"""
import argparse
import json
import math
import multiprocessing
import os

import numpy as np
from scipy.optimize import least_squares
from scipy.stats import qmc

from conftest import make_8_6
from rotor_elastic_fe import rotor_sector_fe
from srmcore.materials.library import load_material
from srmcore.post import rotor_stress as rs

RHO, E, NU, OMEGA = 7490.0, 200e9, 0.33, 2 * math.pi * 200
RADIUS = 0.05
PHASES = {4: 3, 6: 4, 8: 3, 10: 3, 12: 3, 16: 3}
SHAFT = (0.25, 0.45)          # shaft diameter / rotor diameter
ARC = (1.0, 1.7)              # rotor pole arc / Lawrenson limit 2 pi / (m Nr)
YOKE = (0.5, 1.15)            # yoke thickness / tip chord
TAPER = (-5.0, 10.0)          # degrees
FILLET = (0.01, 0.3)          # fillet radius / pole width at the root, log-uniform
LEVELS = (20, 40, 80)         # fillet radius / element size


def machine_at(n_poles, u):
    limit = 2 * math.pi / (PHASES[n_poles] * n_poles)
    arc = limit * (ARC[0] + u[1] * (ARC[1] - ARC[0]))
    shaft = 2 * RADIUS * (SHAFT[0] + u[0] * (SHAFT[1] - SHAFT[0]))
    yoke = 2 * RADIUS * math.sin(arc / 2) * (YOKE[0] + u[2] * (YOKE[1] - YOKE[0]))
    taper = math.radians(TAPER[0] + u[3] * (TAPER[1] - TAPER[0]))
    base = dict(n_rotor_poles=n_poles, n_phases=PHASES[n_poles], rotor_outer_diameter=2 * RADIUS, shaft_diameter=shaft, rotor_pole_arc=arc,
                rotor_yoke_thickness=yoke, rotor_pole_taper=taper, rotor_fillet_radius=0.0)
    d = 2 * rs.pole_half_width(make_8_6(**base), shaft / 2 + yoke)
    ratio = FILLET[0] * (FILLET[1] / FILLET[0])**u[4]
    return {**base, "rotor_fillet_radius": ratio * d}


def evaluate(values):
    machine = make_8_6(**values)
    b = machine.rotor_yoke_outer_radius
    try:
        levels = [rotor_sector_fe(machine, RHO, E, NU, OMEGA, n) for n in LEVELS]
        pole = rotor_sector_fe(machine, RHO, E, NU, OMEGA, LEVELS[1], body=lambda x: 1.0 * (np.hypot(*x) > b))
        yoke = rotor_sector_fe(machine, RHO, E, NU, OMEGA, LEVELS[1], body=lambda x: 1.0 * (np.hypot(*x) <= b))
    except ValueError as exc:
        return {"params": values, "skipped": str(exc)}
    fe = levels[-1]
    i = int(np.argmax(np.abs(fe.fillet_stress)))
    return {
        "params": values,
        "bore": [s.bore_peak for s in levels], "root": [s.root_peak for s in levels],
        "tip": [s.tip_displacement for s in levels], "peak": fe.peak, "peak_xy": fe.peak_xy,
        "root_position": float(fe.fillet_position[i]),
        "bore_ends": [float(fe.bore_stress[0]), float(fe.bore_stress[-1])],
        "rim_ends": [float(fe.rim_stress[0]), float(fe.rim_stress[-1])],
        "pole_root": pole.root_peak, "yoke_root": yoke.root_peak, "pole_bore": pole.bore_peak, "yoke_bore": yoke.bore_peak,
    }


def fit(path, target=1.045):
    """Near-minimax fit (fourth power of the log error) of the two constant sets against `target` x FE, so the errors
    centre on the high side of the pass rule. Designs outside the validity box take no part."""
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
        return np.log(np.maximum(model, 1.0) / (target * root))**2

    def bore_error(c):
        rs._BORE_RIM_RELIEF, rs._BORE_BEND_GAIN = c
        return np.log(np.array([analytic_bore(m) for m in machines]) / (target * bore))**2

    for name, error, start in (("root", root_error, (0.8, 0.5, 0.27, 0.19)), ("bore", bore_error, (0.05, 1.9))):
        result = least_squares(error, start, diff_step=1e-3)
        print(name, len(machines), "designs", np.round(result.x, 4), "worst log error", np.sqrt(result.fun.max()))


def analytic_bore(machine):
    return rs.rotor_stress(machine, RHO, load_material("10JNEX900").mechanical.model_copy(update={"poisson_ratio": NU}),
                           OMEGA * 60 / (2 * math.pi) / rs.OVERSPEED).bore_stress


def check(path):
    with open(path) as f:
        rows = [row for row in json.load(f) if "skipped" not in row]
    mech = load_material("10JNEX900").mechanical.model_copy(update={"poisson_ratio": NU, "youngs_modulus": E})
    rpm = OMEGA * 60 / (2 * math.pi)
    errors, out = [], 0
    for row in rows:
        machine = make_8_6(**row["params"])
        st = rs.rotor_stress(machine, RHO, mech, rpm / rs.OVERSPEED)
        if st.status != "ok":
            out += 1
            continue
        fe_root, fe_bore, fe_tip = row["root"][-1], row["bore"][-1], row["tip"][-1]
        tip = rs.gap_closure(machine, RHO, mech, None, None, rpm, 20.0, 20.0).centrifugal
        errors.append((st.root_stress / fe_root - 1, st.bore_stress / fe_bore - 1, tip / fe_tip - 1,
                       max(st.root_stress, st.bore_stress) / max(fe_root, fe_bore) - 1,
                       abs(row["root"][-1] / row["root"][-2] - 1), abs(row["bore"][-1] / row["bore"][-2] - 1)))
    e = 100 * np.array(errors)
    print(f"{path}: {len(e)} designs in the box, {out} outside")
    for i, name in enumerate(("root", "bore", "tip", "peak", "root conv", "bore conv")):
        print(f"  {name:10s} min {e[:, i].min():7.2f} % max {e[:, i].max():7.2f} %")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("seed", type=int)
    run.add_argument("n", type=int)
    run.add_argument("out")
    run.add_argument("--poles", type=int, nargs="+", default=[4, 6, 8, 16])
    sub.add_parser("fit").add_argument("derived")
    sub.add_parser("check").add_argument("sweeps", nargs="+")
    args = parser.parse_args()
    if args.command == "check":
        for path in args.sweeps:
            check(path)
        return
    if args.command == "fit":
        fit(args.derived)
        return
    jobs = []
    for n_poles in args.poles:
        sampler = qmc.LatinHypercube(d=5, seed=args.seed * 100 + n_poles)
        jobs += [machine_at(n_poles, u) for u in sampler.random(args.n)]
    os.environ.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    with multiprocessing.get_context("spawn").Pool(14) as pool:
        rows = pool.map(evaluate, jobs, chunksize=4)
    with open(args.out, "w") as f:
        json.dump(rows, f, indent=0)


if __name__ == "__main__":
    main()
