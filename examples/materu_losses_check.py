"""R3 loss check against Materu's measured core and copper loss on the 6/4 (dissertation 1989, Tables 4 and 5;
docs/r3-sources.md section 4) and a region-share cross-check on the 8/6 against Yan et al. 2020.

Materu's points are single-pulse strokes at 180 V d.c. with fixed advance and conduction angles, a hysteresis current
limit at the measured peak current, and the measured speed. The angles are taken as mechanical, the advance as
measured before the onset of pole overlap (aligned - (stator arc + rotor arc)/2). The 6/4 is the Krishnan machine
(tests/krishnan_6_4.py, 2D plus the analytic end winding at image factor 1.5) with the M19 loss fit standing in for
Materu's "E140" steel, so the iron error includes that material gap. Copper loss is 3 R I_rms^2 from the computed
current beside the same formula on the measured rms current.

Run from the repo root (hours at `reference`):
  $env:PYTHONPATH="tests"; python -u examples\\materu_losses_check.py [--preset screening|full|reference]
      [--rows 4:0 5:2 ...] [--workers N] [--cache-dir DIR] [--skip-yan] [--json PATH]
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

import krishnan_6_4 as k64
from materials.m19_loss_fixture import m19_loss_data
from srmapp.drive.envelope import _simulate, _stroke_waveforms, _tables, envelope, min_copper_stroke
from srmapp.losses import _uncertainty, phase_current_samples, stroke_losses
from srmcore.maps import build_map
from srmcore.maps.end_winding import end_winding_inductance, with_end_winding
from srmcore.maps.stroke import DEFAULT_STROKE_ANGLES, stroke_angles
from srmcore.materials.library import load_material
from srmcore.materials.loss import fit_loss
from srmcore.mesh import build_machine_mesh

BUS_V, R_PHASE = 180.0, 3.4
IMAGE_FACTOR = 1.5
I_MAX = 6.0                      # above the largest measured peak current, 5.66 A
N_THETA = 721                    # table angles over one rotor pole pitch (0.125 deg)
FLAT = dict(advance=0.0, conduction=18.05)
PEAKY = dict(advance=11.95, conduction=25.27)
# per row: (peak A, rms A, iron W, copper W, rpm)
MATERU = {
    4: (FLAT, [(1.07, 0.446, 5.6, 2.0, 955), (1.54, 0.629, 9.6, 4.0, 729), (1.83, 0.768, 10.4, 6.0, 615),
               (2.13, 0.888, 10.5, 8.0, 550), (2.54, 1.051, 10.70, 11.3, 486)]),
    5: (PEAKY, [(2.67, 0.870, 20.6, 7.7, 2324), (3.28, 1.067, 11.3, 11.6, 1806), (4.04, 1.356, 7.3, 18.8, 1458),
                (4.94, 1.712, 15.5, 29.9, 1150), (5.66, 2.000, 22.9, 40.8, 1004)]),
}
M5D_FLUX_DEFICIT = {"La at 1 A": -0.020, "La at 10 A": -0.114, "torque at 1 A": -0.109, "torque at 10 A": -0.169}
YAN_SHARES = {"stator yoke": 52.9, "stator teeth": 23.9, "rotor": 23.2}
YAN_RPM, YAN_BUS_V, YAN_R, YAN_I_MAX = 3000.0, 300.0, 0.3, 20.0


def stroke_for_angles(result, machine, rpm, advance_deg, conduction_deg, i_limit):
    """(phase current over one pitch on the table angles, computed peak A, rms A, valid) of the single pulse that
    starts `advance_deg` before the onset of pole overlap and lasts `conduction_deg`, with the hysteresis limit
    `i_limit`. `valid` is False when the flux has not died away before the next turn-on."""
    period = 2 * math.pi / machine.n_rotor_poles
    onset = math.degrees(period - 0.5 * (machine.stator_pole_arc + machine.rotor_pole_arc))
    n = N_THETA - 1
    on = round((onset - advance_deg) / math.degrees(period) * n)
    off = on + round(conduction_deg / math.degrees(period) * n)
    t = _tables(result, period, i_limit, N_THETA)
    omega = rpm * 2 * math.pi / 60
    args = (t, omega, BUS_V, R_PHASE)
    _, _, i2, valid = _simulate(*args, np.array([on]), np.array([off]))
    cur = _stroke_waveforms(*args, on, off)[0]
    return cur, float(cur.max()), math.sqrt(i2[0] / period), bool(valid[0])


def _corrected_map(design, i_max, solver, workers, cache_dir):
    result = build_map(design, i_max, solver=solver, workers=workers, cache_dir=cache_dir)
    return with_end_winding(result, end_winding_inductance(design.machine, image_factor=IMAGE_FACTOR))


def materu_rows(preset="reference", rows=None, workers=None, cache_dir=None, solver="ngsolve", log=print):
    d = k64.design(preset=preset)
    machine = d.machine
    tau = 2 * math.pi / machine.n_rotor_poles
    material = load_material("M19")
    model = fit_loss(m19_loss_data(), density=material.density, thickness=material.thickness)
    with k64.waivers():
        result = _corrected_map(d, I_MAX, solver, workers, cache_dir)
        static = build_machine_mesh(d)
    angles = stroke_angles(static, tau, DEFAULT_STROKE_ANGLES)
    out = []
    for table, (angle_set, points) in MATERU.items():
        for index, (peak, rms, iron, copper, rpm) in enumerate(points):
            if rows is not None and (table, index) not in rows:
                continue
            cur, c_peak, c_rms, valid = stroke_for_angles(result, machine, rpm, angle_set["advance"],
                                                          angle_set["conduction"], peak)
            phase = phase_current_samples(cur, angles, tau, machine.n_phases)
            with k64.waivers():
                sl = stroke_losses(static, d, angles, phase, rpm, solver=solver, workers=workers,
                                   cache_dir=cache_dir, model=model)
            row = dict(table=table, index=index, rpm=rpm, measured_peak=peak, measured_rms=rms,
                       computed_peak=c_peak, computed_rms=c_rms, valid=valid,
                       measured_iron_w=iron, computed_iron_w=sl.iron_w,
                       error_pct=100 * (sl.iron_w - iron) / iron,
                       iron_uncertainty_pct=100 * _uncertainty(list(sl.sides)),
                       measured_copper_w=copper, copper_from_measured_rms_w=3 * R_PHASE * rms**2,
                       computed_copper_w=3 * R_PHASE * c_rms**2,
                       regions={k: v.hysteresis + v.classical + v.excess for k, v in sl.iron.items()})
            out.append(row)
            log(f"T{table}.{index + 1}: {rpm:.0f} rpm, iron {sl.iron_w:.2f} W vs {iron} W ({row['error_pct']:+.0f} %)")
    return out


def yan_shares(preset="reference", workers=None, cache_dir=None, solver="ngsolve"):
    """Region shares (%) of the iron loss of the repo's 8/6 (10JNEX900) on the stroke of half the envelope torque at
    one speed, in Yan's grouping."""
    from conftest import make_8_6
    from srmcore.model.design import Design, MeshSettings, RegionMaterials
    iron = RegionMaterials(stator="10JNEX900", rotor="10JNEX900")
    d = Design(machine=make_8_6(materials=iron, lamination_thickness=1.0e-4), mesh=MeshSettings(preset=preset))
    machine = d.machine
    tau = 2 * math.pi / machine.n_rotor_poles
    result = _corrected_map(d, YAN_I_MAX, solver, workers, cache_dir)
    env = envelope(result, machine, YAN_BUS_V, YAN_R, [YAN_RPM])
    trace = min_copper_stroke(result, machine, YAN_BUS_V, YAN_R, YAN_RPM, 0.5 * float(env.torque[0]))
    if trace is None:
        raise RuntimeError("no stroke reaches half the envelope torque")
    static = build_machine_mesh(d)
    angles = stroke_angles(static, tau, DEFAULT_STROKE_ANGLES)
    phase = phase_current_samples(trace.current, angles, tau, machine.n_phases)
    sl = stroke_losses(static, d, angles, phase, YAN_RPM, solver=solver, workers=workers, cache_dir=cache_dir)
    w = {k: v.hysteresis + v.classical + v.excess for k, v in sl.iron.items()}
    total = sum(w.values())
    shares = {"stator yoke": w["stator_yoke"], "stator teeth": w["stator_pole"],
              "rotor": w["rotor_pole"] + w["rotor_yoke"]}
    return dict(rpm=YAN_RPM, torque_nm=trace.torque_avg, iron_w=total,
                shares_pct={k: 100 * v / total for k, v in shares.items()})


def main():
    args = sys.argv[1:]

    def opt(name, default=None, cast=str):
        if name in args:
            i = args.index(name)
            v = cast(args[i + 1])
            del args[i:i + 2]
            return v
        return default

    preset = opt("--preset", "reference")
    workers = opt("--workers", None, int)
    cache_dir = opt("--cache-dir")
    json_path = opt("--json")
    skip_yan = "--skip-yan" in args
    if skip_yan:
        args.remove("--skip-yan")
    rows = None
    if "--rows" in args:
        i = args.index("--rows")
        rows = {tuple(map(int, a.split(":"))) for a in args[i + 1:]}
    out = dict(preset=preset, rows=materu_rows(preset, rows, workers, cache_dir))
    print(f"\nMaterial stand-in: M19 fit (grade C) for Materu's E140; the iron error includes that gap. Preset {preset}.")
    print("M5d 2D flux deficit after end winding (small at 1-6 A, large at 10 A+): "
          + ", ".join(f"{k} {100 * v:+.1f} %" for k, v in M5D_FLUX_DEFICIT.items()))
    print("\n| Row | rpm | peak meas/comp (A) | rms meas/comp (A) | iron meas (W) | iron comp (W) | error | +/- | "
          "Cu meas (W) | Cu from meas rms (W) | Cu comp (W) | valid |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in out["rows"]:
        print(f"| T{r['table']}.{r['index'] + 1} | {r['rpm']:.0f} | {r['measured_peak']:.2f} / {r['computed_peak']:.2f} | "
              f"{r['measured_rms']:.3f} / {r['computed_rms']:.3f} | {r['measured_iron_w']:.1f} | "
              f"{r['computed_iron_w']:.2f} | {r['error_pct']:+.0f} % | {r['iron_uncertainty_pct']:.0f} % | "
              f"{r['measured_copper_w']:.1f} | {r['copper_from_measured_rms_w']:.1f} | "
              f"{r['computed_copper_w']:.1f} | {r['valid']} |")
    if not skip_yan:
        y = yan_shares(preset, workers, cache_dir)
        out["yan"] = y
        print(f"\nRegion shares of the iron loss, 8/6 10JNEX900 at {y['rpm']:.0f} rpm, {y['torque_nm']:.2f} N·m "
              f"({y['iron_w']:.1f} W); qualitative only (different machine and material):")
        print("| Region | This 8/6 (%) | Yan et al. 2020 (%) |\n|---|---|---|")
        for k, v in y["shares_pct"].items():
            print(f"| {k} | {v:.1f} | {YAN_SHARES[k]} |")
    if json_path:
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    main()
