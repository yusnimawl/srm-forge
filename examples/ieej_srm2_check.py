"""Compare srmcore with the IEEJ TR 1589 2D maps of the IEEJ public-use SRM "SRM2" (18/12, 10JNEX900;
tests/ieej_srm2.py, fixture tests/validation/fixtures/ieej_srm2, results docs/ieej-srm2-results.md).

Solves phase A at the 16 portal positions and the chosen currents (a map through the process pool), then prints
flux linkage and torque against the portal tables, the mean stroke torque from the co-energy, and the check that
the portal torque table is the half-machine torque.

Run from the repo root:
    PYTHONPATH=tests python examples/ieej_srm2_check.py [--preset screening|full|reference] [--workers N]
        [--currents 50,100,150,200,250] [--stacking K] [--json PATH]
--stacking K replaces the 10JNEX900 stacking factor (library value 0.9) by K for this run only, in this process;
it runs the solves in-process (one worker), because pool workers load the library material.
"""
import argparse
import json
import math
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np

import ieej_srm2 as m
from srmcore.maps.run import run_map
from srmcore.mesh import build_machine_mesh


def _override_stacking(k: float) -> None:
    import srmcore.materials.laws as laws
    original = laws.load_material

    def load(name):
        mat = original(name)
        return mat.model_copy(update={"stacking_factor": k}) if name == "10JNEX900" else mat
    laws.load_material = load
    laws.library_law.cache_clear()


def _interp_ref(table: m.Table, currents: np.ndarray) -> np.ndarray:
    """Portal values at our currents (rows), linear in current; the portal grid is 10 A."""
    return np.array([[np.interp(i, table.currents, table.values[:, k]) for k in range(len(table.positions))]
                     for i in currents])


def compare(result, flux: m.Table, torque: m.Table) -> dict:
    psi = result.psi[:, :, 0].T                     # (currents, angles)
    t = result.torque_arkkio.T
    w = result.coenergy.T
    psi_ref, t_ref = _interp_ref(flux, result.currents), _interp_ref(torque, result.currents)
    t_co_ref = _interp_ref(m.Table(flux.positions, flux.currents, m.coenergy_torque(flux)), result.currents)
    w_ref = _interp_ref(m.coenergy_table(flux), result.currents)
    rows = []
    for j, i in enumerate(result.currents):
        peak_ref = np.max(np.abs(t_ref[j]))
        rows.append({
            "current": float(i),
            "psi_rel": (psi[j] / psi_ref[j] - 1).tolist(),
            "torque": t[j].tolist(), "torque_ref": t_ref[j].tolist(), "torque_coenergy_ref": t_co_ref[j].tolist(),
            "torque_of_peak": ((t[j] - t_ref[j]) / peak_ref).tolist(),
            "peak": float(np.max(t[j])), "peak_ref": float(peak_ref),
            # mean torque over the stroke = W'(aligned) - W'(unaligned) over the stroke angle
            "mean": float((w[j, -1] - w[j, 0]) / m.STROKE), "mean_ref": float((w_ref[j, -1] - w_ref[j, 0]) / m.STROKE),
            "mean_table_ref": float(np.trapezoid(t_ref[j], flux.angles) / m.STROKE),
        })
    return {"rows": rows,
            "worst_psi_rel": float(max(max(abs(v) for v in r["psi_rel"]) for r in rows)),
            "worst_torque_of_peak": float(max(max(abs(v) for v in r["torque_of_peak"]) for r in rows))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="screening", choices=("screening", "full", "reference"))
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--currents", default="50,100,150,200,250")
    ap.add_argument("--stacking", type=float, default=None)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args()
    currents = np.array([float(v) for v in a.currents.split(",")])
    workers = a.workers if a.workers is not None else 1 if a.stacking is not None else None
    if a.stacking is not None:
        if workers != 1:
            raise SystemExit("--stacking runs in-process; use --workers 1")
        _override_stacking(a.stacking)
    if workers is None:
        from srmcore.maps.pool import default_workers
        workers = default_workers()

    flux, torque = m.flux_table(), m.torque_table()
    d = m.design(a.preset)
    t0 = time.time()
    static = build_machine_mesh(d)
    n_nodes = len(static.stator.nodes) + len(static.rotor.nodes)
    t_mesh = time.time() - t0
    done = [0]

    def progress(k, n):
        if k - done[0] >= max(1, n // 20) or k == n:
            done[0] = k
            print(f"  {k}/{n} points, {time.time() - t0:.0f} s", flush=True)
    result = run_map(static, d, flux.angles, currents, "ngsolve", workers=workers, progress=progress)
    t_solve = time.time() - t0 - t_mesh
    out = compare(result, flux, torque)

    ratio = m.coenergy_torque(flux)[-1, 2:-2] / (torque.values[-1, 2:-2] / m.TORQUE_TABLE_FACTOR)
    sf = a.stacking if a.stacking is not None else 0.9
    print(f"\nSRM2 18/12, `{a.preset}`, {n_nodes} stator and rotor nodes, band {m.BAND_DIVISIONS[a.preset]} divisions, "
          f"10JNEX900 stacking factor {sf:g}; mesh {t_mesh:.0f} s, {result.psi.shape[0] * len(currents)} solves "
          f"{t_solve:.0f} s on {workers} workers")
    print(f"portal check: co-energy torque of SRM2_Flux-I / SRM2_T-position at 250 A, interior positions: "
          f"{ratio.min():.3f} to {ratio.max():.3f}\n")
    last = out["rows"][-1]
    print(f"At {last['current']:g} A:\n")
    print("| stroke angle (deg) | psi (Wb) | psi IEEJ | dpsi | T (N m) | T IEEJ x2 | dT / peak | T IEEJ co-energy |")
    print("|---|---|---|---|---|---|---|---|")
    psi = result.psi[:, -1, 0]
    for k, x in enumerate(flux.positions):
        print(f"| {1.5 * (x - 10):.0f} | {psi[k]:.4f} | {flux.values[-1, k]:.4f} | {last['psi_rel'][k]:+.2%} | "
              f"{last['torque'][k]:+.1f} | {last['torque_ref'][k]:+.1f} | {last['torque_of_peak'][k]:+.2%} | "
              f"{last['torque_coenergy_ref'][k]:+.1f} |")
    print("\n| current (A) | worst dpsi | dpsi unaligned | dpsi aligned | peak T | peak T IEEJ x2 | worst dT / peak | "
          "mean T (co-energy) | mean T IEEJ (co-energy) | mean T IEEJ x2 (table) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in out["rows"]:
        print(f"| {r['current']:g} | {max(r['psi_rel'], key=abs):+.2%} | {r['psi_rel'][0]:+.2%} | {r['psi_rel'][-1]:+.2%} | "
              f"{r['peak']:.1f} | {r['peak_ref']:.1f} | {max(r['torque_of_peak'], key=abs):+.2%} | {r['mean']:.1f} | "
              f"{r['mean_ref']:.1f} | {r['mean_table_ref']:.1f} |")
    print(f"\nworst: psi {out['worst_psi_rel']:.2%}, torque {out['worst_torque_of_peak']:.2%} of the IEEJ peak")
    if a.json:
        a.json.write_text(json.dumps({
            "srmcore": version("srmcore"), "preset": a.preset, "nodes": n_nodes, "stacking_factor": sf,
            "band_divisions": m.BAND_DIVISIONS[a.preset], "workers": workers, "mesh_s": t_mesh, "solve_s": t_solve,
            "status": result.status.tolist(), "assumed": m.ASSUMED, "torque_table_ratio": [ratio.min(), ratio.max()],
            "angles_deg": [math.degrees(v) for v in flux.angles], "currents": currents.tolist(),
            "psi": result.psi[:, :, 0].tolist(), "torque": result.torque_arkkio.tolist(),
            "coenergy": result.coenergy.tolist(), **out}, indent=1))


if __name__ == "__main__":
    main()
