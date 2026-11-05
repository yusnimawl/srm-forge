"""G1: the 3D TEAM 24 model against the measured static torque and rotor-pole flux at 7.41 A, within a 3D budget.

    systemd-run --user --scope -q -p MemoryMax=22G -p OOMPolicy=continue \
        .venv/bin/python tools/end3d/g1_team24.py [--max-dofs N] [--json PATH] [--dry-run]

Mesh levels are (h_gap, h_iron, h_end, h_mid) in mm: COARSE, NOMINAL (1.5 / 10 / 2 / 8, G0's 1.71 M DOFs) and FINE
(1.2 / 8 / 1.5 / 6, 3.20 M DOFs). Every perturbation row runs at the NOMINAL level and the verdict's 3D values are
the NOMINAL run's; the mesh row is the distance of the NOMINAL value to the Richardson extrapolation of the three
levels (to the FINE value when the levels are not monotone). Each row is a worst-case term; the budget is their sum
for torque and flux separately, and the gate passes when |3D - measured| / measured <= the sum for both.

Each 3D solve runs in its own process, one at a time. The JSON is rewritten after every run; a rerun with the same
--json reuses the converged runs whose parameters and level are unchanged. A run over --max-dofs is recorded as skipped and fails the gate; a run that did not
converge is stored and makes `verdict` raise ValueError naming its row.

The material row follows `srmcore.maps.validation`: Js + 2 % only, as |plus - nominal|, because Js x 0.98 = 1.96 T lies
below the B-H data (last point J = 1.979 T), which `process_bh` rejects. It has no grade allowance: the spec builds this
budget from 3D runs only, and the curve is the measured EN9 curve with no grade given.
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
from end3d.g0_timing import _ndof, _nlayers  # noqa: E402
from end3d.solve import solve3d  # noqa: E402
from end3d.team24 import Team24Params, ampere_turns, rotor_pole_flux, team24_swept_model  # noqa: E402

CURRENT = float(fx.TABLE_CURRENT[-1])
MEASURED = {"torque": float(fx.TABLE_TORQUE[-1]), "flux": float(fx.TABLE_ROTOR_FLUX[-1])}
ROUNDING = {"torque": 0.005, "flux": 0.005e-4}          # half the last tabulated digit
COARSE, NOMINAL, FINE = (1.9, 12.5, 2.5, 10.0), (1.5, 10.0, 2.0, 8.0), (1.2, 8.0, 1.5, 6.0)
MM = 1e-3

# key -> (Team24Params overrides, mesh level)
RUNS = {
    "mesh_coarse": ({}, COARSE),
    "nominal": ({}, NOMINAL),
    "mesh_fine": ({}, FINE),
    "slab": ({"slab": True}, NOMINAL),
    "air_radius": ({"air_radius_factor": 2.25}, NOMINAL),
    "air_end": ({"air_end_factor": 1.5}, NOMINAL),
    "js_hi": ({"js": fx.ASSUMED_JS * 1.02}, NOMINAL),
    "fillet": ({"fillet": 3 * MM}, NOMINAL),
    "hub_plus": ({"r_hub": fx.R_HUB + 0.5 * MM}, NOMINAL),
    "hub_minus": ({"r_hub": fx.R_HUB - 0.5 * MM}, NOMINAL),
    "yoke_plus": ({"r_yoke_in": fx.R_YOKE_IN - 0.5 * MM}, NOMINAL),      # a thicker yoke has a smaller inner radius
    "yoke_minus": ({"r_yoke_in": fx.R_YOKE_IN + 0.5 * MM}, NOMINAL),
    "search_plus": ({"search_from_corner": fx.SEARCH_COIL_FROM_CORNER + 1 * MM}, NOMINAL),
    "search_minus": ({"search_from_corner": fx.SEARCH_COIL_FROM_CORNER - 1 * MM}, NOMINAL),
    "end_1mm": ({"end_clearance": 1 * MM}, NOMINAL),
    "end_5mm": ({"end_clearance": 5 * MM}, NOMINAL),
}
RUN_KEYS = tuple(RUNS)
ROWS = ("mesh", "air_box", "material", "table_rounding", "fillets", "hub_radius", "yoke_thickness", "search_coil",
        "coil_end")
QUANTITIES = ("torque", "flux")


def _ok(run) -> bool:
    return bool(run and run.get("converged") and run.get("torque") is not None)


def _rel(a, b):
    return abs(a - b) / abs(b)


def _richardson_distance(f1: float, f2: float, f3: float, h: tuple[float, float, float]) -> float:
    """|f2 - extrapolated limit| / |f2| for values f1, f2, f3 at sizes h1 > h2 > h3 with the order fitted from the
    three values (bisection, order 1 to 8); |f2 - f3| / |f2| when the sequence is not monotone."""
    if (f1 - f2) * (f2 - f3) <= 0:
        return abs(f2 - f3) / abs(f2)
    q = (f1 - f2) / (f2 - f3)
    ratio = lambda p: (h[0] ** p - h[1] ** p) / (h[1] ** p - h[2] ** p)    # noqa: E731
    lo, hi = 1.0, 8.0      # below order 1 the fit is noise between levels, and the extrapolation grows without limit
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ratio(mid) < q else (lo, mid)
    p = (lo + hi) / 2
    limit = f3 + (f3 - f2) * h[2] ** p / (h[1] ** p - h[2] ** p)
    return abs(f2 - limit) / abs(f2)


def budget(nominal: dict, runs: dict) -> dict[str, dict[str, float | None]]:
    """Row -> {"torque": rel, "flux": rel} from the nominal run and the perturbation runs (key -> run record).
    A row whose runs are missing, skipped or not converged is None, which `verdict` refuses."""
    out: dict[str, dict[str, float | None]] = {}

    def row(name, keys, fn, only=QUANTITIES):
        need = [nominal] + [runs.get(k) for k in keys]
        valid = all(_ok(r) for r in need)
        out[name] = {q: None if not valid else (fn(*[r[q] for r in need]) if q in only else 0.0) for q in QUANTITIES}

    row("mesh", ("mesh_coarse", "mesh_fine"),
        lambda n, c, f: _richardson_distance(c, n, f, (COARSE[0], NOMINAL[0], FINE[0])))
    row("air_box", ("air_radius", "air_end"), lambda n, r, e: (abs(r - n) + abs(e - n)) / abs(n))
    row("material", ("js_hi",), lambda n, hi: _rel(hi, n))
    out["table_rounding"] = {q: ROUNDING[q] / MEASURED[q] for q in QUANTITIES}
    row("fillets", ("fillet",), lambda n, v: _rel(v, n))
    row("hub_radius", ("hub_plus", "hub_minus"), lambda n, a, b: abs(a - b) / 2 / abs(n))
    row("yoke_thickness", ("yoke_plus", "yoke_minus"), lambda n, a, b: abs(a - b) / 2 / abs(n))
    row("search_coil", ("search_plus", "search_minus"), lambda n, a, b: abs(a - b) / 2 / abs(n), only=("flux",))
    row("coil_end", ("end_1mm", "end_5mm"), lambda n, a, b: abs(a - b) / 2 / abs(n))
    return out


def verdict(nominal: dict, measured: dict, rows: dict) -> dict:
    """Per quantity |3D - measured| / measured against the sum of the rows; ValueError names a row (or the nominal
    run) that has no converged result."""
    if not _ok(nominal):
        raise ValueError("nominal run did not converge or was skipped")
    for name, vals in rows.items():
        if any(v is None for v in vals.values()):
            raise ValueError(f"row {name}: a run did not converge, was skipped or is missing")
    out = {}
    for q in QUANTITIES:
        err, tot = _rel(nominal[q], measured[q]), sum(r[q] for r in rows.values())
        out[q] = {"error_rel": err, "budget_rel": tot, "pass": err <= tot}
    out["pass"] = all(out[q]["pass"] for q in QUANTITIES)
    return out


def _solve_one(spec: dict, max_dofs: int, dry_run: bool) -> dict:
    params = Team24Params(**spec["params"])
    model = team24_swept_model(params, *[x * MM for x in spec["level_mm"]])
    rec = {"ndof": _ndof(model), "layers": _nlayers(model), "skipped": False, "converged": False,
           "level_mm": spec["level_mm"]}
    if dry_run:
        return rec
    if rec["ndof"] > max_dofs:
        return {**rec, "skipped": True}
    at = ampere_turns(params, CURRENT)
    sol = solve3d(model, at)
    rec.update(converged=sol.converged, seconds=sol.seconds, peak_gb=sol.peak_rss_bytes / 1e9, torque=None, flux=None,
               psi=None, iterations=sol.iterations)
    if sol.converged:
        rec["torque"] = post.arkkio_torque(model, sol, fx.BAND_INNER, fx.BAND_OUTER)
        rec["flux"] = rotor_pole_flux(model, sol)
        rec["psi"] = post.flux_linkage(model, sol, model.coils, CURRENT, at)
    return rec


def _in_child(spec: dict, max_dofs: int, dry_run: bool = False) -> dict:
    cmd = [sys.executable, __file__, "--one", json.dumps([spec, max_dofs, dry_run])]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode:
        return {"skipped": False, "converged": False, "failed": done.stderr.strip().splitlines()[-1:] or ["crashed"]}
    return json.loads(done.stdout.strip().splitlines()[-1])


def _report(runs: dict) -> dict:
    """Rows, errors and verdict (or the reason there is none yet) and the hook check, from the runs so far."""
    nominal = runs.get("nominal")
    rows = budget(nominal, runs) if _ok(nominal) else None
    try:
        if rows is None:
            raise ValueError("nominal run did not converge, was skipped or is missing")
        v = verdict(nominal, MEASURED, rows)
    except ValueError as e:
        v = {"pass": False, "reason": str(e)}
    out = {"measured": MEASURED, "rows": rows, "verdict": v}
    if _ok(nominal) and _ok(runs.get("slab")):
        out["hook"] = {"psi_full_minus_slab": nominal["psi"] - runs["slab"]["psi"],
                       "analytic_image_1_5": fx.end_winding_inductance(1.5) * CURRENT}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--max-dofs", type=int, default=3_300_000)
    ap.add_argument("--json", type=Path, default=ROOT / "docs/validation/r4_g1.json")
    ap.add_argument("--dry-run", action="store_true", help="build every model, print key, DOFs and layers, solve nothing")
    ap.add_argument("--one", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.one:
        spec, max_dofs, dry = json.loads(args.one)
        print(json.dumps(_solve_one(spec, max_dofs, dry)))
        return 0
    runs: dict = {}
    if not args.dry_run and args.json.exists():
        runs = json.loads(args.json.read_text()).get("runs", {})
    for key, (params, level) in RUNS.items():
        old = runs.get(key) or {}
        if _ok(old) and old.get("params") == params and old.get("level_mm") == list(level) and not args.dry_run:
            print(f"{key}: reused", flush=True)
            continue
        rec = _in_child({"key": key, "params": params, "level_mm": list(level)}, args.max_dofs, args.dry_run)
        if args.dry_run:
            print(f"{key}: level {level} ndof {rec.get('ndof')} layers {rec.get('layers')}"
                  f"{' (over --max-dofs)' if rec.get('ndof', 0) > args.max_dofs else ''}", flush=True)
            continue
        runs[key] = {**rec, "params": params, "level_mm": list(level)}
        args.json.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.json.with_suffix(".tmp")
        tmp.write_text(json.dumps({"runs": runs, **_report(runs)}, indent=2))
        tmp.replace(args.json)
        print(f"{key}: " + json.dumps({k: rec.get(k) for k in ("ndof", "converged", "skipped", "torque", "flux", "seconds",
                                                               "peak_gb")}), flush=True)
    if args.dry_run:
        return 0
    v = _report(runs)["verdict"]
    if "reason" in v:
        print("G1 INCOMPLETE", json.dumps(v), flush=True)
        return 2
    print("G1", "PASS" if v["pass"] else "FAIL", json.dumps(v), flush=True)
    return 0 if v["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
