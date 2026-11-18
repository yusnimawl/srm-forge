"""R3 iron-loss check against Kiyota, Kakishima and Chiba 2014 (10JNEX900 18/12; Table III points and the Fig. 16
iron-and-other losses at 13 900 r/min; docs/superpowers/plans/2026-11-18-kiyota-iron-check.md).

The map is the 2D design at 20 turns plus the analytic end winding (image factor 1.5), phase A, I_max 300 A. Per point
two strokes, both `min_copper_stroke` at 650 V: the measured torque, and the torque target at which the stroke's RMS
current equals the measured RMS current (the 2D model gives more torque per ampere than the 3D machine); the second
needs a measured RMS, so the Fig. 16 points have the first only. "Iron and other" in the measurement holds stray
losses, so the ratio over-states the iron error.

Run from the repo root:
  PYTHONPATH=src:tests python -u examples/kiyota_losses_check.py [--preset screening|full|reference] [--workers N]
      [--cache-dir DIR] [--points a b c f1 ... f7] [--stator-yoke M] [--json PATH]
"""
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

import kiyota_18_12 as k18
from srmapp.drive.envelope import min_copper_stroke
from srmapp.losses import iron_uncertainty, phase_current_samples, stroke_losses
from srmcore.maps import build_map
from srmcore.maps.end_winding import end_winding_inductance, with_end_winding
from srmcore.maps.stroke import DEFAULT_STROKE_ANGLES, stroke_angles
from srmcore.maps.tables import angle_spline
from srmcore.mesh import build_machine_mesh

IMAGE_FACTOR = 1.5
I_MAX = 300.0
COPPER_ALPHA, T_COIL_C = 0.00393, 75.0
R_PHASE = k18.R_PHASE_20C * (1 + COPPER_ALPHA * (T_COIL_C - 20.0))
MEASURED_L = (1.2e-3, 9.1e-3)                       # unaligned, aligned at 10 A (2014 Table II)
FIG16_RPM = 13900.0
FIG16_KW = (14.68, 17.22, 21.94, 22.36, 30.03, 59.06, 99.46)
FIG16_IRON_W = (823, 944, 1123, 1260, 1564, 3348, 6989)
# name: (rpm, measured torque N·m, measured peak A, measured RMS A, measured iron and other W)
POINTS = {
    "a": (2768.0, 209.0, 240.0, 137.0, 700.0),
    "b": (8700.0, 113.0, 205.0, 130.0, 4400.0),
    "c": (7500.0, 36.0, 76.0, 35.4, 600.0),
}
for n, (kw, w) in enumerate(zip(FIG16_KW, FIG16_IRON_W), 1):
    POINTS[f"f{n}"] = (FIG16_RPM, 1000 * kw / (FIG16_RPM * 2 * math.pi / 60), None, None, float(w))
BISECT_ITER, RMS_TOL = 14, 0.005


def inductances(result, machine, current=10.0):
    """Unaligned and aligned secant inductance (H) at `current` from the angle spline and linear interpolation in
    the grid currents."""
    tau = 2 * math.pi / machine.n_rotor_poles
    e = result.circuits.index(result.excited)
    psi = [angle_spline(result.angles, result.psi[:, k, e], tau)([0.0, tau / 2]) for k in range(len(result.currents))]
    psi = np.array(psi)
    return tuple(float(np.interp(current, result.currents, psi[:, c])) / current for c in (1, 0))


def match_rms(result, machine, rpm, torque, rms):
    """The stroke whose RMS current equals `rms` by bisection of the torque target (None when none reaches it)."""
    def stroke(t):
        return min_copper_stroke(result, machine, k18.BUS_V, R_PHASE, rpm, t)

    lo, hi, best = 0.0, 1.5 * torque, None
    for _ in range(BISECT_ITER):
        mid = 0.5 * (lo + hi) if lo > 0 else 0.5 * hi
        s = stroke(mid)
        if s is None:
            hi = mid
            continue
        best = s
        if abs(s.i_rms - rms) <= RMS_TOL * rms:
            break
        lo, hi = (mid, hi) if s.i_rms < rms else (lo, mid)
    return best


def losses(trace, static, d, angles, tau, rpm, iron_meas, solver, workers, cache_dir, fractions):
    phase = phase_current_samples(trace.current, angles, tau, d.machine.n_phases)
    with k18.waivers():
        sl = stroke_losses(static, d, angles, phase, rpm, solver=solver, workers=workers, cache_dir=cache_dir,
                           cut_process="unspecified", fractions=fractions)
    lo, hi = sl.cut_edge_rel
    return dict(torque_model=trace.torque_avg, computed_peak=float(trace.current.max()), computed_rms=trace.i_rms,
                model_iron_w=sl.iron_w, cut_edge_low_w=sl.iron_w * (1 + lo), cut_edge_high_w=sl.iron_w * (1 + hi),
                iron_uncertainty_pct=100 * iron_uncertainty(list(sl.sides)), valid=trace.valid,
                ratio_measured_over_model=iron_meas / sl.iron_w)


def run(preset="full", points=None, workers=None, cache_dir=None, solver="ngsolve", stator_yoke=k18.STATOR_YOKE,
        log=print):
    d = k18.design(preset=preset, stator_yoke=stator_yoke)
    m = d.machine
    tau = 2 * math.pi / m.n_rotor_poles
    with k18.waivers():
        raw = build_map(d, I_MAX, solver=solver, workers=workers, cache_dir=cache_dir)
        static = build_machine_mesh(d)
    l_end = end_winding_inductance(m, image_factor=IMAGE_FACTOR)
    result = with_end_winding(raw, l_end)
    lu, la = inductances(result, m)
    inductance = dict(l_end=l_end, unaligned=lu, aligned=la, measured_unaligned=MEASURED_L[0],
                      measured_aligned=MEASURED_L[1])
    log(f"L at 10 A (2D + end winding {1e3 * l_end:.2f} mH): unaligned {1e3 * lu:.2f} mH vs {1e3 * MEASURED_L[0]:.1f}, "
        f"aligned {1e3 * la:.2f} mH vs {1e3 * MEASURED_L[1]:.1f}")
    angles = stroke_angles(static, tau, DEFAULT_STROKE_ANGLES)
    fractions, out = {}, []
    for name, (rpm, torque, peak, rms, iron) in POINTS.items():
        if points and name not in points:
            continue
        row = dict(name=name, rpm=rpm, f_elec_hz=rpm / 60 * m.n_rotor_poles, torque_target=torque,
                   measured_peak=peak, measured_rms=rms, measured_iron_w=iron)
        for variant in ("torque", "current"):
            if variant == "torque":
                trace = min_copper_stroke(result, m, k18.BUS_V, R_PHASE, rpm, torque)
            else:
                trace = None if rms is None else match_rms(result, m, rpm, torque, rms)
            row[variant] = None if trace is None else losses(trace, static, d, angles, tau, rpm, iron, solver,
                                                             workers, cache_dir, fractions)
            c = row[variant]
            if c:
                log(f"{name} [{variant}]: {rpm:.0f} rpm, T {c['torque_model']:.1f} N·m, iron {c['model_iron_w']:.0f} W "
                    f"vs {iron:.0f} W (x{c['ratio_measured_over_model']:.2f}), peak {c['computed_peak']:.0f} A, "
                    f"rms {c['computed_rms']:.1f} A")
            else:
                log(f"{name} [{variant}]: none" + (" (no measured RMS)" if variant == "current" and rms is None else ""))
        out.append(row)
    return dict(preset=preset, stator_yoke=stator_yoke, r_phase=R_PHASE, inductance=inductance, points=out)


def main():
    args = sys.argv[1:]

    def opt(name, default=None, cast=str):
        if name in args:
            i = args.index(name)
            v = cast(args[i + 1])
            del args[i:i + 2]
            return v
        return default

    preset = opt("--preset", "full")
    workers = opt("--workers", None, int)
    cache_dir = opt("--cache-dir") or str(Path(tempfile.gettempdir()) / "srm-kiyota-cache")
    json_path = opt("--json")
    yoke = opt("--stator-yoke", k18.STATOR_YOKE, float)
    points = None
    if "--points" in args:
        points = set(args[args.index("--points") + 1:])
    out = run(preset, points, workers, cache_dir, stator_yoke=yoke)
    print(f"\nKiyota 18/12, preset {preset}, stator yoke {1e3 * yoke:.1f} mm, R {1e3 * R_PHASE:.1f} mohm at 75 C.")
    print("| Point | rpm | f_e (Hz) | T target (N·m) | Variant | peak meas/comp (A) | rms meas/comp (A) | "
          "iron meas (W) | iron model (W) | cut-edge range (W) | +/- | meas/model |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in out["points"]:
        for v in ("torque", "current"):
            c = r[v]
            if c is None:
                continue
            mp = "-" if r["measured_peak"] is None else f"{r['measured_peak']:.0f}"
            mr = "-" if r["measured_rms"] is None else f"{r['measured_rms']:.1f}"
            print(f"| {r['name']} | {r['rpm']:.0f} | {r['f_elec_hz']:.0f} | {r['torque_target']:.1f} | {v} | "
                  f"{mp} / {c['computed_peak']:.0f} | {mr} / {c['computed_rms']:.1f} | {r['measured_iron_w']:.0f} | "
                  f"{c['model_iron_w']:.0f} | {c['cut_edge_low_w']:.0f} to {c['cut_edge_high_w']:.0f} | "
                  f"{c['iron_uncertainty_pct']:.0f} % | {c['ratio_measured_over_model']:.2f} |")
    if json_path:
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    main()
