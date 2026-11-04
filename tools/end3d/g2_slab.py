"""G2: the 3D slab model (no end effects) against the 2D solver, signed psi and torque.

    systemd-run --user --scope -q -p MemoryMax=20G -p MemorySwapMax=0 \
        .venv/bin/python tools/end3d/g2_slab.py [--max-dofs N] [--json PATH]

Points: the srmcore 8/6 at 20 A (phase A) aligned, at half overlap and unaligned, and TEAM 24 at 7.41 A. Each 3D solve
runs in its own process (so its peak RSS is its own); the JSON is rewritten after every row. A row whose H(curl) dof
count exceeds --max-dofs is recorded as skipped and fails the gate. Pass: every row converged, psi_rel <= PSI_TOL and
torque_rel_peak <= TORQUE_TOL.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "tools", ROOT / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import team24_fixture as fx  # noqa: E402
from end3d import post  # noqa: E402
from end3d.g0_timing import _ndof  # noqa: E402
from end3d.radial import ampere_turns as radial_at, radial_model  # noqa: E402
from end3d.solve import solve3d  # noqa: E402
from end3d.team24 import Team24Params, ampere_turns as team24_at, team24_swept_model  # noqa: E402
from srmapp.references import make_8_6  # noqa: E402
from srmcore.maps.point import solve_point  # noqa: E402
from srmcore.mesh import build_machine_mesh  # noqa: E402
from srmcore.mesh.settings import MeshSettings  # noqa: E402
from srmcore.model.design import Design  # noqa: E402
from srmcore.solvers.factory import make_solver  # noqa: E402
from srmcore.topology.radial import parametric_outline  # noqa: E402

PSI_TOL = 0.005
TORQUE_TOL = 0.01
N_ROTOR = 6
POINTS = (("8/6", 0.0, 20.0), ("8/6", math.pi / (2 * N_ROTOR), 20.0), ("8/6", math.pi / N_ROTOR, 20.0),
          ("TEAM 24", 0.0, float(fx.TABLE_CURRENT[-1])))
LEVEL_MM = {"8/6": (1.0, 3.0, 4.0, 12.0), "TEAM 24": (1.0, 4.0, 1.0, 3.0)}      # h_gap, h_iron, h_end, h_mid


def reference_2d(machine: str, angle: float, current: float) -> tuple[float, float]:
    """Signed (psi, torque) of the 2D solver: srmcore `full` mesh for the 8/6, the fixture mesh for TEAM 24."""
    from srmcore.post.quantities import arkkio_torque, flux_linkage
    solver = make_solver("ngsolve")
    if machine == "TEAM 24":
        p = fx.team24_problem(current)
        s = solver.solve(p)
        if s.status.value != "OK":
            raise RuntimeError(f"2D TEAM 24 solve: {s.status}")
        return float(flux_linkage(p, s)[0]), float(arkkio_torque(p, s))
    design = Design(machine=make_8_6(), mesh=MeshSettings(preset="full"))
    r = solve_point(build_machine_mesh(design), design, angle, {"A": current}, solver)
    if r.status.value == "NONCONVERGED":
        raise RuntimeError(f"2D 8/6 solve at {angle}: {r.status}")
    return float(r.psi[0]), float(r.torque_arkkio)


def _model(machine: str, angle: float, current: float, level_mm: tuple[float, ...]):
    h = [1e-3 * x for x in level_mm]
    if machine == "TEAM 24":
        params = Team24Params(slab=True)
        return team24_swept_model(params, *h), team24_at(params, current), fx.BAND_INNER, fx.BAND_OUTER
    design = Design(machine=make_8_6(), mesh=MeshSettings(preset="full"))
    out = parametric_outline(design.machine)
    return (radial_model(design, angle, "A", True, *h), radial_at(design, current, True),
            out.band_inner_radius, out.band_outer_radius)


def solve_slab(machine: str, angle: float, current: float, level_mm: tuple[float, ...], max_dofs: int) -> dict:
    """The 3D slab solve of one point: signed psi (Wb-turns) and torque (N.m), or `skipped` over the dof limit."""
    model, at, r_in, r_out = _model(machine, angle, current, level_mm)
    rec = {"ndof": _ndof(model), "skipped": False, "level_mm": list(level_mm)}
    if rec["ndof"] > max_dofs:
        return {**rec, "skipped": True, "converged": False}
    sol = solve3d(model, at)
    rec.update(converged=sol.converged, seconds=sol.seconds, peak_gb=sol.peak_rss_bytes / 1e9, psi_3d=None, torque_3d=None)
    if sol.converged:
        rec["psi_3d"] = post.flux_linkage(model, sol, model.coils, current, at)
        rec["torque_3d"] = post.arkkio_torque(model, sol, r_in, r_out)
    return rec


def _in_child(machine: str, angle: float, current: float, level_mm: tuple[float, ...], max_dofs: int) -> dict:
    cmd = [sys.executable, __file__, "--one", json.dumps([machine, angle, current, list(level_mm), max_dofs])]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode:
        return {"skipped": False, "converged": False, "failed": done.stderr.strip().splitlines()[-1:] or ["crashed"]}
    return json.loads(done.stdout.strip().splitlines()[-1])


def assess(rows: list[dict]) -> list[dict]:
    """Adds psi_rel and torque_rel_peak (against the peak |T2D| of the machine's rows) and the row verdict."""
    for row in rows:
        peak = max(abs(r["torque_2d"]) for r in rows if r["machine"] == row["machine"])
        ok = row.get("converged") and row.get("psi_3d") is not None
        row["psi_rel"] = abs(row["psi_3d"] - row["psi_2d"]) / abs(row["psi_2d"]) if ok else None
        row["torque_rel_peak"] = abs(row["torque_3d"] - row["torque_2d"]) / peak if ok else None
        row["passed"] = bool(ok and row["psi_rel"] <= PSI_TOL and row["torque_rel_peak"] <= TORQUE_TOL)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--max-dofs", type=int, default=3_000_000)
    ap.add_argument("--json", type=Path, default=ROOT / "docs/validation/r4_g2.json")
    ap.add_argument("--one", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.one:
        machine, angle, current, level, max_dofs = json.loads(args.one)
        print(json.dumps(solve_slab(machine, angle, current, tuple(level), max_dofs)))
        return 0
    rows = []
    for machine, angle, current in POINTS:
        psi, torque = reference_2d(machine, angle, current)
        rows.append({"machine": machine, "angle": angle, "current": current, "psi_2d": psi, "torque_2d": torque,
                     **_in_child(machine, angle, current, LEVEL_MM[machine], args.max_dofs)})
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"rows": rows}, indent=2))
        print(json.dumps(rows[-1]), flush=True)
    assess(rows)
    args.json.write_text(json.dumps({"rows": rows, "passed": all(r["passed"] for r in rows)}, indent=2))
    print("G2", "PASS" if all(r["passed"] for r in rows) else "FAIL", flush=True)
    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
