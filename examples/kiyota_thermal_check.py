"""R5e gate V4: our thermal network on the Kiyota 18/12 Fig. 8 hold (140.7 A RMS for about 14 s, coil end measured from
51.1 degC; K. Kiyota, T. Kakishima, A. Chiba, IEEE Trans. Ind. Electron. 61(10), 2014, pp. 5714 to 5716) against the
measured rise of the coil-end sensor, 39.5 +- 0.4 K read off the trace (the paper prints 41 K).

Ours is the peak over 0 to 20 s of the hottest end-winding lump over the start temperature (the rating's hot spot,
coil sides included, is reported beside it and not judged). Nominal = every cooling row at its nominal; rated =
`frozenset(ROWS)`. The phase resistance is the winding alone, 92.5 mOhm: the measured 97.8 mOhm includes 5.3 mOhm of coil
connections and terminal wiring (2014 pp. 5714 to 5715; Eq. (1) gives 4.9 mOhm for the same 1.68 m, so 92.9 mOhm
for the winding is the other reading). The resistance input row runs 92.5 to 97.8 mOhm; 94.9 mOhm is the
inference if the 0.78 m of connections sits at the coil end. The mean-turn value of the tool is 92.6 mOhm.

Band (plan calls 8 and 9): low = nominal + the sum of the negative input-row changes - numerical error, high = rated +
the sum of the positive row changes + numerical error; numerical error = |full - reference| + |dt - dt/2| on full.
Pass when low - 0.4 <= target <= high + 0.4, for 39.5 K and, on its own line, for 41 K. r = (target - nominal) /
nominal. Rows (each one change from nominal, on full): resistance, iron M, cold-iron start, mechanical loss at the
end caps, housing 4 and 16 mm, stator arc, rotor arc and rotor yoke +-0.3 mm, ambient 40 degC. The rise at 10 s and
14 s is printed beside the trace values (22.7 and 35.5 K, information only: the sensor lags).

Run from the repo root:
  PYTHONPATH=src:tests python -u examples/kiyota_thermal_check.py [--presets screening full reference] [--dt 0.05]
      [--no-dt-check] [--no-rows] [--json PATH]
"""
import argparse
import json
import math
import resource
import time
import srmapp
import srmcore
from pathlib import Path

import numpy as np

import kiyota_18_12 as k18
import kiyota_thermal as kt
from srmapp.cooling import ROWS

R_NOMINAL = 92.5e-3             # ohm at 20 degC, winding alone (92.5 to 92.9 mOhm, see the docstring)
R_TERMINAL = 97.8e-3            # measured at the terminals
R_END_INFERENCE = 94.9e-3       # if the 0.78 m of connections sits at the coil end (inference)
SPLIT = "5.3 mOhm of 97.8 (coil connections 0.78 m and terminal wiring, 1.68 m in all, 2014 pp. 5714-5715); Eq. (1) gives 4.9 mOhm"
TRACE = {"rise_10s_k": 22.7, "rise_14s_k": 35.5}
D_MM = 0.3e-3
# closed-form adiabatic copper heating (finding 1): library copper, DC resistance, no heat flow
CU = {"density_kg_m3": 8890.0, "specific_heat_j_kg_k": 385.2, "rho_20c_ohm_m": 1.7241e-8, "alpha_1_k": 0.00393}
R_BORE = k18.ROTOR_R + k18.AIR_GAP
ROWS_DEF = {      # name -> list of (label, kwargs of rig / run / build)
    "resistance": [("97.8 mOhm", {"resistance": R_TERMINAL}), ("94.9 mOhm (inference)", {"resistance": R_END_INFERENCE})],
    "iron M 0.6 kW": [("0.6 kW", {"iron_w": kt.M_IRON_LOW_W})],
    "cold-iron start": [("cold iron", {"start": "cold_iron"})],
    "mechanical at end caps": [("friction", {"mech": "friction"})],
    "housing": [("4 mm", {"housing": 4e-3}), ("16 mm", {"housing": 16e-3})],
    "stator pole arc": [(f"{s * 0.3:+.1f} mm", {"geo": {"stator_arc": k18.STATOR_ARC + s * D_MM / R_BORE}}) for s in (-1, 1)],
    "rotor pole arc": [(f"{s * 0.3:+.1f} mm", {"geo": {"rotor_arc": k18.ROTOR_ARC + s * D_MM / k18.ROTOR_R}}) for s in (-1, 1)],
    "rotor yoke": [(f"{s * 0.3:+.1f} mm", {"geo": {"rotor_yoke": k18.ROTOR_YOKE + s * D_MM}}) for s in (-1, 1)],
    "ambient 40 degC": [("40 degC", {"ambient": 40.0})],
}


def adiabatic_rise_k() -> float:
    """Closed form: du/dt = a rho20 J^2 u / (d c), u = 1 + a (T - 20), J from the 9 strands of one turn."""
    j2_int = float(np.trapezoid(kt._I ** 2, kt._T)) / kt.TURN_AREA ** 2
    a = CU["alpha_1_k"]
    u0 = 1 + a * (kt.START_C - 20.0)
    return u0 * (math.exp(a * CU["rho_20c_ohm_m"] * j2_int / (CU["density_kg_m3"] * CU["specific_heat_j_kg_k"])) - 1) / a


def simulate(case, dt, rows=frozenset(), resistance=R_NOMINAL, iron_w=kt.M_IRON_W, mech="windage", housing=8e-3,
             ambient=kt.AMBIENT_C, start="uniform"):
    r = kt.rig(case, resistance, rows, iron_w, mech, housing, ambient)
    return kt.run(r, dt, start=start, ambient=ambient)


def summary(res: kt.Result, dt: float) -> dict:
    s = max(1, round(0.25 / dt))
    return {"end_peak_k": res.end_peak_k, "hot_peak_k": res.hot_peak_k, "hot_peak_where": res.hot_peak_where,
            "rise_10s_k": res.rise_10s_k, "rise_14s_k": res.rise_14s_k, "wall_s": res.wall_s,
            "trace_s": [float(x) for x in res.times_s[::s]],
            "trace_end_rise_k": [float(x - kt.START_C) for x in res.end_c[::s]]}


def verdict(target: float, nominal: float, low: float, high: float) -> dict:
    tol = kt.TARGET_K[1]
    return {"target_k": target, "pass": bool(low - tol <= target <= high + tol), "r": (target - nominal) / nominal}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--presets", nargs="+", default=["screening", "full", "reference"])
    ap.add_argument("--dt", type=float, default=0.05)
    ap.add_argument("--no-dt-check", action="store_true")
    ap.add_argument("--no-rows", action="store_true")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    ad = adiabatic_rise_k()
    print(f"closed-form adiabatic copper rise {ad:.2f} K; resistance {R_NOMINAL * 1e3:.1f} mOhm nominal "
          f"(winding alone), {R_TERMINAL * 1e3:.1f} mOhm at the terminals; split: {SPLIT}")
    out, nominal = {}, {}
    for preset in a.presets:
        t0 = time.perf_counter()
        case = kt.build(preset)
        entry = {"nodes": len(case.domain.nodes), "mesh_wall_s": time.perf_counter() - t0}
        for name, rows in (("nominal", frozenset()), ("rated", frozenset(ROWS))):
            res = simulate(case, a.dt, rows)
            entry[name] = summary(res, a.dt)
            if preset == "full" and not a.no_dt_check:
                entry[name + "_half_dt"] = summary(simulate(case, a.dt / 2, rows), a.dt / 2)
            print(f"{preset:10s} {name:8s} end {res.end_peak_k:6.2f} K  hot {res.hot_peak_k:7.2f} K ({res.hot_peak_where})  "
                  f"10 s {res.rise_10s_k:5.2f} (trace {TRACE['rise_10s_k']})  14 s {res.rise_14s_k:5.2f} "
                  f"(trace {TRACE['rise_14s_k']})  {res.wall_s:.0f} s", flush=True)
        out[preset] = entry
    base = "full" if "full" in out else a.presets[-1]
    flags = []
    err = {}
    for name in ("nominal", "rated"):
        mesh = abs(out["full"][name]["end_peak_k"] - out["reference"][name]["end_peak_k"]) if {"full", "reference"} <= out.keys() else 0.0
        step = abs(out["full"][name]["end_peak_k"] - out["full"][name + "_half_dt"]["end_peak_k"]) if "full" in out and not a.no_dt_check else 0.0
        err[name] = {"mesh_k": mesh, "dt_k": step, "total_k": mesh + step}
    if not {"full", "reference"} <= out.keys():
        flags.append("mesh error not available (full and reference not both run): counted as 0")
    if a.no_dt_check or "full" not in out:
        flags.append("time-step error not available: counted as 0")
    if base != "full":
        flags.append(f"nominal and rated taken from {base}, not full")
    nom, rat = out[base]["nominal"]["end_peak_k"], out[base]["rated"]["end_peak_k"]
    rows_out = {}
    if not a.no_rows and "full" in out:
        full = kt.build("full")
        nom_hot = out["full"]["nominal"]["hot_peak_k"]
        for rname, variants in ROWS_DEF.items():
            vs = []
            for label, kw in variants:
                kw = dict(kw)
                case = kt.build("full", **kw.pop("geo")) if "geo" in kw else full
                res = simulate(case, a.dt, **kw)
                vs.append({"label": label, "end_peak_k": res.end_peak_k, "hot_peak_k": res.hot_peak_k,
                           "d_end_k": res.end_peak_k - out["full"]["nominal"]["end_peak_k"], "d_hot_k": res.hot_peak_k - nom_hot})
                print(f"row {rname:24s} {label:22s} end {res.end_peak_k:6.2f} ({vs[-1]['d_end_k']:+.2f})  "
                      f"hot {res.hot_peak_k:7.2f} ({vs[-1]['d_hot_k']:+.2f})", flush=True)
            d = [v["d_end_k"] for v in vs]
            rows_out[rname] = {"variants": vs, "low_k": min(0.0, *d), "high_k": max(0.0, *d)}
    neg = sum(r["low_k"] for r in rows_out.values())
    pos = sum(r["high_k"] for r in rows_out.values())
    rows_run = bool(rows_out)
    if not rows_run:
        flags.append("input rows not run: counted as 0")
    low, high = nom + neg - err["nominal"]["total_k"], rat + pos + err["rated"]["total_k"]
    verdicts = {"trace_39.5": verdict(kt.TARGET_K[0], nom, low, high), "printed_41": verdict(kt.PRINTED_K, nom, low, high)}
    print(f"band {low:.2f} to {high:.2f} K (nominal {nom:.2f}, rated {rat:.2f}, rows {neg:+.2f} / {pos:+.2f}, "
          f"numerical {err['nominal']['total_k']:.2f} / {err['rated']['total_k']:.2f})")
    for k, v in verdicts.items():
        print(f"{k}: target {v['target_k']} K  {'PASS' if v['pass'] else 'FAIL'}  r = {v['r']:+.3f}")
    for f in flags:
        print("note:", f)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps({
            "inputs": {
                "current": "docs/validation/r5_v0_readings.json kiyota_fig8.rms_current_a, linear between readings, 0 after the last",
                "start_c": kt.START_C, "ambient_c": kt.AMBIENT_C + 0.0, "ambient_note": "25 degC assumed, not printed (call 5)",
                "resistance_ohm_20c": {"nominal": R_NOMINAL, "terminal": R_TERMINAL, "end_inference": R_END_INFERENCE,
                                       "mean_turn_tool": 92.6e-3, "printed_split": SPLIT,
                                       "note": "nominal = winding alone (controller ruling); the terminal value is a row"},
                "iron_w": {"nominal_M": kt.M_IRON_W, "low_M": kt.M_IRON_LOW_W, "source": "Table III (b) and (c), iron and other",
                           "route": "nominal = M / k_iron_hi(1500 Hz), rated = M, uniform over the stator iron (call 1)"},
                "compared_quantity": "end-lump peak: maximum over 0 to 20 s of the hottest end-winding lump minus the start temperature; the sensor is on the coil end (2014 p. 5716); the rating hot spot is reported beside it, not judged (call 2)",
                "target_source": "39.5 +- 0.4 K, the trace reading (docs/r5-sources.md 9.2; the figure's own arrow spans 39.7 K); the printed 41 K has its own verdict (call 3)",
                "start_state": "uniform 51.1 degC at every node and free lump; row: copper nodes and end lumps at 51.1, the rest at the ambient (call 4)",
                "iron_capacity_j_m3_k": "438 J/(kg K) x 7490 kg/m3 from the 10JNEX900 library record (owner, 2026-11-27)",
                "mechanical_w": {"value": kt.MECH_W, "source": "Fig. 7 at 7493 r/min", "route": "windage in the rotor iron; rated x 1.2; row: friction at the end caps"},
                "em_torque_row": "no effect: the current is imposed, not found from a torque (call 7)",
                "housing_row_mm": [4, 16], "housing_note": "Kiyota housing not described; 8 mm default placeholder, range assumed",
                "geometry_row_mm": 0.3, "geometry_source": "Fig. 7 readings, about +-0.3 mm (docs/r5-sources.md 9.2)",
                "target_k": list(kt.TARGET_K), "printed_k": kt.PRINTED_K, "trace_k": TRACE, "dt_s": a.dt, "t_end_s": 20.0},
            "adiabatic_copper_rise_k": ad, "adiabatic_inputs": CU, "presets": out, "numerical_error": err, "rows": rows_out,
            "band": {"low_k": low, "high_k": high, "neg_rows_k": neg, "pos_rows_k": pos, "base_preset": base},
            "verdicts": verdicts, "flags": flags, "input_rows_run": rows_run,
            "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            "hot_spot_beside_end_lump": {p: {k: (e[k]["hot_peak_k"], e[k]["hot_peak_where"], e[k]["end_peak_k"]) for k in ("nominal", "rated")} for p, e in out.items()},
            "srmcore_version": srmcore.__version__, "srmapp_version": srmapp.__version__}, indent=1))


if __name__ == "__main__":
    main()
