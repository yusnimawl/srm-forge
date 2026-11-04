"""G0 cost spike: time the full (non-slab) TEAM 24 3D model at the top table current, nonlinear steel.

    .venv/bin/python tools/end3d/g0_timing.py [--levels 4e-3 2.8e-3 2e-3] [--max-dofs N] [--json PATH]

Each level is a maxh; the air-gap size is maxh / 8 (the 4e-3 / 0.5e-3 default ratio). The JSON is
rewritten after every level. A level whose H(curl) dof count exceeds --max-dofs is recorded as skipped,
a meshing failure as `failed`, and a non-converged solve carries no torque or flux.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "tools", ROOT / "tests"):       # tests/ holds team24_fixture
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ngsolve as ng  # noqa: E402
from netgen.meshing import NgException  # noqa: E402

import team24_fixture as fx  # noqa: E402
from end3d import post  # noqa: E402
from end3d.solve import solve3d  # noqa: E402
from end3d.team24 import Team24Params, ampere_turns, rotor_pole_flux, team24_model  # noqa: E402

CURRENT = float(fx.TABLE_CURRENT[-1])
GAP_RATIO = 8
SWEEP_SOLVES = 4 * 4 * 7 * 3            # spec §6 minimums: machines x stacks x angles x currents


def _build(maxh: float):
    params = Team24Params(maxh=maxh, gap_maxh=maxh / GAP_RATIO)
    return SimpleNamespace(params=params, model=team24_model(params))


def _ndof(model) -> int:
    """Free-dof count of the solver's space (H(curl) order, no gradients, Dirichlet faces)."""
    from end3d.solve import _names
    faces = [f"{c}{s}" for c in model.coils for s in ("_in", "_out")]
    fes = ng.HCurl(model.mesh, order=model.order, nograds=True, dirichlet=_names(*faces) + "|" + model.dirichlet)
    return sum(1 for f in fes.FreeDofs() if f)


def _nelements(model) -> int:
    return model.mesh.ne


def _ram_bytes():
    try:
        with open("/proc/meminfo") as f:
            return int(f.readline().split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None


def _host() -> dict:
    return {"node": platform.node(), "cpus": os.cpu_count(), "ram_bytes": _ram_bytes(), "ngsolve": ng.__version__}


def _level(maxh: float, max_dofs: int) -> dict:
    rec = {"maxh": maxh, "gap_maxh": maxh / GAP_RATIO, "skipped": False}
    t0 = time.perf_counter()
    try:
        built = _build(maxh)
    except NgException as e:
        return {**rec, "failed": str(e)}
    rec["mesh_seconds"] = time.perf_counter() - t0
    model = built.model
    rec["elements"] = _nelements(model)
    rec["ndof"] = _ndof(model)
    if rec["ndof"] > max_dofs:
        return {**rec, "skipped": True}
    at = ampere_turns(built.params, CURRENT)
    sol = solve3d(model, at)
    rec.update(seconds=sol.seconds, newton_iterations=sol.iterations, peak_rss_bytes=sol.peak_rss_bytes,
               converged=sol.converged, torque=None, psi=None, rotor_pole_flux=None)
    if sol.converged:
        rec["torque"] = post.arkkio_torque(model, sol, fx.BAND_INNER, fx.BAND_OUTER)
        rec["psi"] = post.flux_linkage(model, sol, model.coils, CURRENT, at)
        rec["rotor_pole_flux"] = rotor_pole_flux(model, sol)
    return rec


def _write(path: Path, host: dict, levels: list[dict]) -> None:
    done = [lv for lv in levels if lv.get("converged")]
    hours = done[-1]["seconds"] * SWEEP_SOLVES / 3600 if done else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"host": host, "current": CURRENT, "levels": levels,
                                "sweep_solves": SWEEP_SOLVES, "sweep_estimate_hours": hours}, indent=2))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--levels", type=float, nargs="+", default=[4e-3, 2.8e-3, 2e-3])
    ap.add_argument("--max-dofs", type=int, default=10**9)
    ap.add_argument("--json", type=Path, default=ROOT / "docs/validation/r4_g0.json")
    args = ap.parse_args(argv)
    host, levels = _host(), []
    for maxh in args.levels:
        levels.append(_level(maxh, args.max_dofs))
        _write(args.json, host, levels)
        print(json.dumps(levels[-1]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
