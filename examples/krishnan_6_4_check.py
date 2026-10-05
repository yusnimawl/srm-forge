"""Krishnan/Materu 6/4: srmcore 2D and 2D + end winding against the measured La, Lu and stroke-averaged
torque, with the uncertainty budget. The output is the source of docs/m5d-krishnan-results.md.

Run from the repo root:  $env:PYTHONPATH="tests"; .venv\\Scripts\\python -u examples\\krishnan_6_4_check.py
"""
import numpy as np

import krishnan_6_4 as k64
from srmcore.maps.end_winding import coil_geometry
from srmcore.solvers.factory import make_solver

UNITS = {"La": ("mH", 1e3), "Lu": ("mH", 1e3), "T_avg": ("N·m", 1.0)}
MEASUREMENT = {"La": None, "Lu": k64.LU_MEASUREMENT_SCATTER, "T_avg": None}   # relative; None = not stated


def main():
    p = k64.machine()
    g = coil_geometry(p)
    print(f"machine: clearance {p.coil_inner_clearance * 1e3:.2f} mm, coil {g.area * 1e6:.0f} mm² "
          f"(build {g.build * 1e3:.1f} x depth {g.depth * 1e3:.1f} mm, span {g.span * 1e3:.1f} mm), "
          f"rotor yoke {p.rotor_yoke_thickness * 1e3:.2f} mm")
    for k, v in k64.ASSUMED.items():
        print(f"assumed {k}: {v}")
    s = k64.study(make_solver("ngsolve"))
    l_mid = 0.5 * (s["l_end"][1.0] + s["l_end"][2.0])
    print(f"end winding per phase: {s['l_end'][1.0] * 1e3:.2f} mH (image 1) .. {s['l_end'][2.0] * 1e3:.2f} mH "
          f"(image 2); reported {l_mid * 1e3:.2f} mH")
    print("\nall tables (SI):")
    for name, t in s["tables"].items():
        print(f"  {name:<14} " + "  ".join(f"{q} {np.array2string(v, precision=5)}" for q, v in t.items()))
    two_d = s["tables"]["reference"]
    after = k64.corrected(two_d, l_mid)
    print("\n| Quantity | I (A) | Measured | Materu FEA | 2D | 2D + end winding | Error before | ± before | "
          "Error after | ± after |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for q, (unit, f) in UNITS.items():
        for n, i in enumerate(k64.CURRENTS):
            meas = k64.MEASURED[q][n]
            unc = []
            for budget in (s["budget_before"], s["budget_after"]):
                model = sum(row[q][n] for row in budget.values())
                rel = model / meas + (MEASUREMENT[q] or 0.0)
                unc.append(f"{100 * rel:.1f} %" + ("" if MEASUREMENT[q] else " + meas. n/s"))
            e0 = 100 * (two_d[q][n] - meas) / meas
            e1 = 100 * (after[q][n] - meas) / meas
            print(f"| {q} ({unit}) | {i:g} | {f * meas:.4g} | {f * k64.MATERU_FEA[q][n]:.4g} | {f * two_d[q][n]:.4g} | "
                  f"{f * after[q][n]:.4g} | {e0:+.1f} % | {unc[0]} | {e1:+.1f} % | {unc[1]} |")
    print("\nbudget rows (% of measured), before / after:")
    for name, row in s["budget_after"].items():
        cells = "  ".join(f"{q} " + "/".join(f"{100 * row[q][n] / k64.MEASURED[q][n]:.2f}" for n in range(3)) for q in row)
        print(f"  {name:<18} {cells}")
    print(f"  {'measurement':<18} Lu {100 * k64.LU_MEASUREMENT_SCATTER:.1f} % (La, T_avg: not stated)")
    print("\nSeward 3D/2D end leakage (reference line, not a correction): "
          + ", ".join(f"{q} {100 * v:.1f} %" for q, v in k64.SEWARD_END_LEAKAGE.items()))
    print("our end-winding share of the corrected inductance at 10 A: "
          f"La {100 * l_mid / after['La'][1]:.1f} %, Lu {100 * l_mid / after['Lu'][1]:.1f} %")


if __name__ == "__main__":
    main()
