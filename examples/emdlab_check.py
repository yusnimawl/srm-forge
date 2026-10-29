"""Print the EMDLAB / ANSYS Maxwell 8/6 cross-tool comparison table (source of docs/emdlab-results.md).

Run from the repo root:  $env:PYTHONPATH="tests"; .venv\\Scripts\\python examples\\emdlab_check.py [--json PATH]
"""
import json
import sys
from importlib.metadata import version
from pathlib import Path

import emdlab_machine as em
from srmcore.maps.point import solve_point
from srmcore.mesh import build_machine_mesh
from srmcore.solvers.ngsolve_adapter import NgsolveAdapter

if __name__ == "__main__":
    args = sys.argv[1:]
    out_path = Path(args[args.index("--json") + 1]) if "--json" in args else None
    d = em.design()
    static = build_machine_mesh(d)
    n_nodes = len(static.stator.nodes) + len(static.rotor.nodes)
    solver = NgsolveAdapter()
    refs = em.references()
    peak_mx = max(abs(q.torque_maxwell) for q in refs)
    peak_em = max(abs(q.torque_emdlab) for q in refs)
    print(f"8/6 at {em.CURRENT} A, `full`, {n_nodes} stator and rotor nodes, band {em.BAND_DIVISIONS} divisions")
    print("| theta_tab (deg) | psi (Wb) | dpsi vs EMDLAB | dW | dW' | T (N m) | T Maxwell | dT/peak Maxwell | "
          "T EMDLAB | dT/peak EMDLAB |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    rows = []
    for q in refs:
        r = solve_point(static, d, q.angle, {"A": em.CURRENT}, solver)
        row = {"theta_tab_deg": q.theta_tab_deg, "psi": r.psi[0], "energy": r.energy, "coenergy": r.coenergy,
               "torque_arkkio": r.torque_arkkio, "torque_virtual_work": r.torque_virtual_work,
               "status": str(r.status), "ref": q.__dict__}
        rows.append(row)
        print(f"| {q.theta_tab_deg:.2f} | {r.psi[0]:.5f} | {r.psi[0] / q.psi - 1:+.3%} | "
              f"{r.energy / q.energy - 1:+.3%} | {r.coenergy / q.coenergy - 1:+.3%} | {r.torque_arkkio:+.4f} | "
              f"{q.torque_maxwell:+.4f} | {(r.torque_arkkio - q.torque_maxwell) / peak_mx:+.3%} | "
              f"{q.torque_emdlab:+.4f} | {(r.torque_arkkio - q.torque_emdlab) / peak_em:+.3%} |")
    worst = {
        "psi": max(abs(x["psi"] / x["ref"]["psi"] - 1) for x in rows),
        "energy": max(abs(x["energy"] / x["ref"]["energy"] - 1) for x in rows),
        "coenergy": max(abs(x["coenergy"] / x["ref"]["coenergy"] - 1) for x in rows),
        "torque_vs_maxwell": max(abs(x["torque_arkkio"] - x["ref"]["torque_maxwell"]) for x in rows) / peak_mx,
        "torque_vs_emdlab": max(abs(x["torque_arkkio"] - x["ref"]["torque_emdlab"]) for x in rows) / peak_em,
    }
    print("\nworst: " + ", ".join(f"{k} {v:.3%}" for k, v in worst.items()))
    if out_path:
        out_path.write_text(json.dumps({"srmcore": version("srmcore"), "nodes": n_nodes,
                                        "assumed": em.ASSUMED, "worst": worst, "rows": rows}, indent=1))
