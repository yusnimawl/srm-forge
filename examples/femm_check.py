"""Print the FEMM 4.2 cross-tool comparison tables (source of docs/m5c-femm-results.md).

Run from the repo root:  $env:PYTHONPATH="tests"; .venv\\Scripts\\python examples\\femm_check.py [machine ...]
"""
import json
import math
import sys
from pathlib import Path

import femm_machines as fm
from srmcore.maps.point import solve_point
from srmcore.mesh import build_machine_mesh
from srmcore.solvers.ngsolve_adapter import NgsolveAdapter

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "validation" / "fixtures"

if __name__ == "__main__":
    names = sys.argv[1:] or list(fm.MACHINES)
    solver = NgsolveAdapter()
    for name in names:
        fixture = json.loads((FIXTURES / f"femm_{name}.json").read_text())
        pts = fixture["points"]
        peak = {}
        for q in pts:
            peak[q["current"]] = max(peak.get(q["current"], 0.0), abs(q["torque_age"]))
        d = fm.design(name)
        prov = fixture["provenance"]
        print(f"\n## {name}  (FEMM level {prov['level']}, B-H probe {prov['bh_probe_max_rel_dev']:.3%})")
        print("| deg | i (A) | psi FEMM | dpsi % | FEMM err psi % | T FEMM (N m) | dT % | dT % of peak | "
              "tol % | FEMM err T % of peak | AGE-WST % of peak |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        worst = {"psi": 0.0, "t_rel": 0.0, "t_peak": 0.0, "ratio": 0.0}
        with fm.waivers(name):
            static = build_machine_mesh(d)
            for q in pts:
                r = solve_point(static, d, q["angle"], {"A": q["current"]}, solver)
                pk = peak[q["current"]]
                dpsi = r.psi[0] / q["psi"] - 1
                dt = r.torque_arkkio - q["torque_age"]
                rel = dt / q["torque_age"] if abs(q["torque_age"]) >= 0.05 * pk else float("nan")
                limit = max(q["tolerance"] * abs(q["torque_age"]), 0.01 * pk)
                worst["psi"] = max(worst["psi"], abs(dpsi))
                worst["t_peak"] = max(worst["t_peak"], abs(dt) / pk)
                worst["ratio"] = max(worst["ratio"], abs(dt) / limit, abs(dpsi) / 0.02)
                if not math.isnan(rel):
                    worst["t_rel"] = max(worst["t_rel"], abs(rel))
                print(f"| {math.degrees(q['angle']):.2f} | {q['current']:g} | {q['psi']:.5f} | {dpsi:+.3%} | "
                      f"{abs(q['psi'] / q['psi_prev'] - 1):.3%} | {q['torque_age']:+.4f} | "
                      f"{'n/a' if math.isnan(rel) else f'{rel:+.2%}'} | {dt / pk:+.3%} | {q['tolerance']:.0%} | "
                      f"{abs(q['torque_age'] - q['torque_age_prev']) / pk:.3%} | "
                      f"{abs(q['torque_age'] - q['torque_wst']) / pk:.3%} |")
        print(f"\nworst: psi {worst['psi']:.3%}, torque {worst['t_rel']:.2%} relative (|T| >= 5 % of peak), "
              f"{worst['t_peak']:.3%} of peak; largest error / limit {worst['ratio']:.2f}")
