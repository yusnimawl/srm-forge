"""R5 gate V2: our 2-D thermal solver on the Faiz 2009 8/6 stator (tests/faiz_8_6.py) against their 2-D results
(Fig. 10 with the Fig. 8 inside air, the Fig. 9 constant-air curve, Table VI), under the pass rule
|ours - fig| <= fig error + mesh error + time-step error at every point, ours = coil max.

Cases: frame "printed" (5 mm aluminium shell, an inference) and "table_v" (R1, C1 of Table V, an inference). Each runs
0 to 120 min, backward Euler, once with the Fig. 8 inside air (linear between readings, 20 degC at 0, the last 10
readings' slope past 119 min; the solver is rebuilt each step with the air at the step end) and once with constant
20 degC inside air. Mesh error = |full - reference|, time-step error = |dt - dt/2| on full; the nominal run is full at
dt (or, when full is not run, the last preset given, and the missing error terms count as 0, flagged in the JSON).
Input rows on the nominal mesh: frame 5 / 15 / 25 mm (printed), liner and wedge +-1 px (table_v).

Run from the repo root:
  PYTHONPATH=src:tests python -u examples/faiz_thermal_check.py [--presets screening full reference] [--dt 15]
      [--no-dt-check] [--json PATH]
"""
import argparse
import json
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np

import faiz_8_6 as F
from srmcore.thermal.model import Temperatures
from srmcore.thermal.solve import ThermalSolver

READINGS = Path("docs/validation/r5_v0_readings.json")
T_END_MIN = 120
TABLE_VI = {"A": 50.7, "B": 51.7, "C": 52.6}     # Table VI, p. 2932, equivalent conductivity; time not printed
TABLE_VI_MIN = 120                                # inferred: Fig. 10 at 119 min lies between B and C
TABLE_VI_PAIRS = (("max", "C"), ("mean", "B"), ("min", "A"))   # by rank: C (far) hottest, A (near the iron) coolest
SHOW_MIN = (1, 5, 10, 30, 60, 119, 120)
ROW_MIN = (30, 60, 119)
FRAME_ROWS_MM = (5.0, 15.0, 25.0)                 # their Fig. 12(f) range


def fig8_air(readings: dict):
    pts = np.array([[0.0, F.AMBIENT_C]] + [p[:2] for p in readings["faiz_fig8"]["points"]])
    slope = float(np.polyfit(pts[-10:, 0], pts[-10:, 1], 1)[0])
    t_last, a_last = pts[-1]

    def air(minute: float) -> float:
        if minute <= t_last:
            return float(np.interp(minute, pts[:, 0], pts[:, 1]))
        return float(a_last + slope * (minute - t_last))
    return air, {"last_reading_min": float(t_last), "extrapolation_slope_k_per_min": slope,
                 "extrapolation": "last 10 readings' least-squares slope from the last reading"}


def coil_sets(case: F.FaizCase):
    d = case.domain
    nodes = np.unique(np.concatenate([d.triangles[e] for e in d.coil_elements.values()]))
    w = case.part == "winding"
    return nodes, d.triangles[w], case.area[w]


def run(case: F.FaizCase, frame: str, air, dt: float, frame_t: float = F.FRAME_T) -> dict:
    """Per minute 0..120: coil max, area mean, min and the frame lump."""
    if 60.0 % dt:
        raise ValueError("dt must divide 60 s")
    t0 = time.time()
    p0, load = F.problem(case, F.AMBIENT_C, frame, frame_t), F.load(case)
    nodes, tri, area = coil_sets(case)
    t = Temperatures(np.full(len(case.domain.nodes), F.AMBIENT_C), {"frame": F.AMBIENT_C})
    out = {k: [F.AMBIENT_C] for k in ("max", "mean", "min", "frame")}
    per_min, solver, solver_air = round(60.0 / dt), None, None
    for k in range(1, T_END_MIN * per_min + 1):
        a = air(k * dt / 60.0)
        if a != solver_air:
            solver, solver_air = ThermalSolver(F.with_air(p0, a)), a
        t = solver.transient(t, lambda _: load, dt, 1).final
        if k % per_min == 0:
            f = t.field
            out["max"].append(float(f[nodes].max()))
            out["mean"].append(float((f[tri].mean(axis=1) * area).sum() / area.sum()))
            out["min"].append(float(f[nodes].min()))
            out["frame"].append(float(t.lumps["frame"]))
    out["wall_s"] = time.time() - t0
    return out


def steady_max(case: F.FaizCase, frame: str, frame_t: float = F.FRAME_T) -> float:
    s = ThermalSolver(F.problem(case, F.AMBIENT_C, frame, frame_t))
    nodes, _, _ = coil_sets(case)
    return float(s.steady(lambda _: F.load(case)).field[nodes].max())


def verdict(ours: list, points: list, mesh_err, dt_err) -> dict:
    rows = []
    for t_min, fig, err in points:
        m = int(round(t_min))
        allow = err + (mesh_err[m] if mesh_err else 0.0) + (dt_err[m] if dt_err else 0.0)
        diff = ours[m] - fig
        rows.append({"t_min": t_min, "fig": fig, "fig_err": err, "ours": ours[m], "diff": diff, "allow": allow,
                     "excess": abs(diff) - allow, "pass": abs(diff) <= allow})
    from_min = None
    for r in reversed(rows):
        if not r["pass"]:
            break
        from_min = r["t_min"]
    worst = max(rows, key=lambda r: r["excess"])
    return {"points": rows, "n_pass": sum(r["pass"] for r in rows), "n": len(rows), "all_pass": all(r["pass"] for r in rows),
            "passes_from_min": from_min, "worst_excess": worst["excess"], "worst_at_min": worst["t_min"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--presets", nargs="+", default=["screening", "full", "reference"])
    ap.add_argument("--dt", type=float, default=15.0)
    ap.add_argument("--no-dt-check", action="store_true")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    readings = json.loads(READINGS.read_text())
    fig8, fig8_info = fig8_air(readings)
    airs = {"fig8": fig8, "constant": lambda _: F.AMBIENT_C}
    nominal = "full" if "full" in args.presets else args.presets[-1]
    half = None if args.no_dt_check else args.dt / 2

    runs, cases, mesh_wall = {}, {}, {}
    for preset in args.presets:
        t0 = time.time()
        cases[preset] = F.build(preset)
        mesh_wall[preset] = time.time() - t0
        print(f"{preset}: mesh {len(cases[preset].domain.nodes)} nodes, {mesh_wall[preset]:.0f} s", flush=True)
        for dt in (args.dt, half) if preset == nominal and half else (args.dt,):
            for frame in F.FRAMES:
                for air_name, air in airs.items():
                    key = f"{preset}/{frame}/{air_name}/dt{dt:g}"
                    runs[key] = run(cases[preset], frame, air, dt)
                    print(f"  {key}: {runs[key]['wall_s']:.0f} s", flush=True)

    targets = {"fig10": ("fig8", readings["faiz_fig10"]["points"]),
               "fig9_constant": ("constant", readings["faiz_fig9"]["constant"]["points"])}
    errors, verdicts, table_vi = {}, {}, {}
    for frame in F.FRAMES:
        for air_name in airs:
            nom = runs[f"{nominal}/{frame}/{air_name}/dt{args.dt:g}"]["max"]
            ref = runs.get(f"reference/{frame}/{air_name}/dt{args.dt:g}")
            fine = runs.get(f"{nominal}/{frame}/{air_name}/dt{half:g}") if half else None
            errors[f"{frame}/{air_name}"] = {
                "mesh": [abs(a - b) for a, b in zip(nom, ref["max"])] if ref and nominal != "reference" else None,
                "time_step": [abs(a - b) for a, b in zip(nom, fine["max"])] if fine else None}
        for target, (air_name, points) in targets.items():
            e = errors[f"{frame}/{air_name}"]
            verdicts[f"{frame}/{target}"] = verdict(runs[f"{nominal}/{frame}/{air_name}/dt{args.dt:g}"]["max"], points,
                                                    e["mesh"], e["time_step"])
        r = runs[f"{nominal}/{frame}/fig8/dt{args.dt:g}"]
        ours = {"max": r["max"][TABLE_VI_MIN], "mean": r["mean"][TABLE_VI_MIN], "min": r["min"][TABLE_VI_MIN]}
        table_vi[frame] = {"ours": ours, "diff": {f"{q}-{p}": ours[q] - TABLE_VI[p] for q, p in TABLE_VI_PAIRS}}

    f10 = {int(p[0]): p[1] for p in readings["faiz_fig10"]["points"]}
    f9 = {int(p[0]): p[1] for p in readings["faiz_fig9"]["constant"]["points"]}
    for frame in F.FRAMES:
        v, c = runs[f"{nominal}/{frame}/fig8/dt{args.dt:g}"], runs[f"{nominal}/{frame}/constant/dt{args.dt:g}"]
        print(f"\n{frame} ({nominal}, dt {args.dt:g} s): min | fig8 air max/mean/min/frame | Fig. 10 | "
              f"constant air max | Fig. 9 constant")
        for m in SHOW_MIN:
            print(f"  {m:4d} | {v['max'][m]:.2f}/{v['mean'][m]:.2f}/{v['min'][m]:.2f}/{v['frame'][m]:.2f} | "
                  f"{f10.get(m, float('nan')):.2f} | {c['max'][m]:.2f} | {f9.get(m, float('nan')):.2f}")
        for target in targets:
            vd = verdicts[f"{frame}/{target}"]
            print(f"  {target}: {vd['n_pass']}/{vd['n']} pass, every point passes from {vd['passes_from_min']} min, "
                  f"worst excess {vd['worst_excess']:+.2f} K at {vd['worst_at_min']:g} min")
        tv = table_vi[frame]["ours"]
        print(f"  Table VI at {TABLE_VI_MIN} min (time inferred): ours max/mean/min {tv['max']:.2f}/{tv['mean']:.2f}/"
              f"{tv['min']:.2f}; theirs A {TABLE_VI['A']} B {TABLE_VI['B']} C {TABLE_VI['C']}")

    # input rows on the nominal mesh: change of coil max at ROW_MIN (Fig. 8 air) and at the constant-air steady state
    def row(case, frame, frame_t=F.FRAME_T):
        r = run(case, frame, fig8, args.dt, frame_t)
        return {**{f"{m}_min": r["max"][m] for m in ROW_MIN}, "steady_constant": steady_max(case, frame, frame_t),
                "wall_s": r["wall_s"]}

    def delta(r, base):
        return {**r, "change": {k: r[k] - base[k] for k in r if k not in ("wall_s",)}}

    base = {fr: {**{f"{m}_min": runs[f"{nominal}/{fr}/fig8/dt{args.dt:g}"]["max"][m] for m in ROW_MIN},
                 "steady_constant": steady_max(cases[nominal], fr)} for fr in F.FRAMES}
    inputs_rows = {}
    for mm in FRAME_ROWS_MM:
        r = base["printed"] if mm * 1e-3 == F.FRAME_T else row(cases[nominal], "printed", mm * 1e-3)
        inputs_rows[f"frame_{mm:g}mm"] = delta(r, base["printed"])
    px = readings["faiz_fig11"]["one_px_mm"] * 1e-3
    for name, kw in (("liner", "liner"), ("wedge", "wedge")):
        nominal_t = F.LINER_T if name == "liner" else F.WEDGE_T
        for sign in (-1, 1):
            case = F.build(nominal, **{kw: nominal_t + sign * px})
            inputs_rows[f"{name}_{'+' if sign > 0 else '-'}1px"] = delta(row(case, "table_v"), base["table_v"])
    print(f"\ninput rows ({nominal}): change of coil max at " + ", ".join(f"{m} min" for m in ROW_MIN)
          + ", constant-air steady")
    print(f"  nominal steady constant air: printed {base['printed']['steady_constant']:.2f}, "
          f"table_v {base['table_v']['steady_constant']:.2f}")
    for name, r in inputs_rows.items():
        print(f"  {name:<12} " + "  ".join(f"{v:+.2f}" for v in r["change"].values()))

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({
            "srmcore": version("srmcore"), "presets": args.presets, "nominal_preset": nominal, "dt_s": args.dt,
            "dt_half_s": half, "missing_error_terms": [n for n, ok in (("mesh", "reference" in args.presets
                                                                         and nominal != "reference"),
                                                                        ("time_step", half is not None)) if not ok],
            "inputs": {
                "readings": str(READINGS), "fig8_air": fig8_info,
                "fig9_constant_dropped": readings["faiz_fig9"]["constant"].get("dropped", []),
                "table_vi": {**TABLE_VI, "source": "Table VI, p. 2932", "compared_at_min": TABLE_VI_MIN,
                             "pairs": "ours max-C, mean-B, min-A, by rank (an inference)",
                             "time": "inferred (not printed): Fig. 10 at 119 min lies between B and C"},
                "case": "tests/faiz_8_6.py (sources in its docstring and docs/r5-sources.md section 9.1)",
                "frame_t_m": F.FRAME_T, "frame_t_source": "Fig. 12, an inference",
                "table_v_r1_c1": [F.TABLE_V_R1, F.TABLE_V_C1], "table_v_source": "Table V, p. 2931, read as the frame "
                "(an inference)", "liner_t_m": F.LINER_T, "wedge_t_m": F.WEDGE_T, "one_px_m": px,
                "compared_metric": "coil max (Fig. 10 does not say which temperature it is; mean reported beside)"},
            "mesh_wall_s": mesh_wall, "runs": runs, "errors": errors, "verdicts": verdicts, "table_vi": table_vi, "input_rows": inputs_rows,
            "nominal_steady_constant": {fr: base[fr]["steady_constant"] for fr in F.FRAMES}}, indent=1))


if __name__ == "__main__":
    main()
