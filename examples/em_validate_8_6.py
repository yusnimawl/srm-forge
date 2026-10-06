r"""EM-validated label checks and uncertainty budget for the 8/6 golden design on a `full` map.

Usage: python examples\em_validate_8_6.py [workers] [--json PATH]   (default grids, about 1 h)
"""
import json
import math
import sys
import time
from pathlib import Path

from srmcore.maps import build_map, em_validate
from srmcore.maps.validation import KEYS
from srmcore.model.design import Design, MeshSettings, RadialSRMParams


def design_8_6() -> Design:
    machine = RadialSRMParams(
        n_stator_poles=8, n_rotor_poles=6, n_phases=4,
        stator_outer_diameter=0.160, rotor_outer_diameter=0.080, air_gap=0.0004,
        stack_length=0.100, shaft_diameter=0.020,
        stator_pole_arc=math.radians(20.0), rotor_pole_arc=math.radians(22.0),
        stator_yoke_thickness=0.012, rotor_yoke_thickness=0.012,
        stator_fillet_radius=0.001, rotor_fillet_radius=0.001,
        turns_per_pole=60, fill_factor=0.5,
        slot_liner_thickness=0.0005, coil_inner_clearance=0.001,
    )
    return Design(machine=machine, mesh=MeshSettings(preset="full"))


def _num(x: float) -> float | None:
    return None if not math.isfinite(x) else float(x)


def validation_json(v, map_s: float, validate_s: float) -> dict:
    b = v.budget
    return {"engine_version": v.engine_version, "label": v.label, "material_grades": dict(v.material_grades),
            "map_s": map_s, "validate_s": validate_s,
            "checks": [{"name": c.name, "status": c.status, "value": _num(c.value), "limit": _num(c.limit),
                        "detail": c.detail} for c in v.checks],
            "budget": {"keys": list(KEYS),
                       "values_2d": {k: _num(b.values_2d[k]) for k in KEYS},
                       "values": {k: _num(b.values[k]) for k in KEYS},
                       "rows": [{"source": r.source, "rel": {k: _num(r.rel[k]) for k in KEYS}, "note": r.note}
                                for r in b.rows],
                       "total": {k: _num(b.total[k]) for k in KEYS}}}


def main() -> None:
    args = sys.argv[1:]
    out_path = None
    if "--json" in args:
        i = args.index("--json")
        out_path = Path(args[i + 1])
        del args[i:i + 2]
    workers = int(args[0]) if args else None
    design = design_8_6()
    t0 = time.perf_counter()
    result = build_map(design, 20.0, workers=workers)
    t1 = time.perf_counter()
    v = em_validate(design, result, workers=workers)
    t2 = time.perf_counter()
    print(f"map {t1 - t0:.0f} s, em_validate {t2 - t1:.0f} s, engine {v.engine_version}, grades {v.material_grades}")
    print("\nchecks")
    for c in v.checks:
        print(f"  {c.name:26s} {c.status:5s} value {c.value:.4g} limit {c.limit:.4g}  {c.detail}")
    b = v.budget
    print("\nbudget (relative half-spread, %)")
    print(f"  {'source':14s}" + "".join(f"{k:>14s}" for k in KEYS))
    for row in b.rows:
        print(f"  {row.source:14s}" + "".join(f"{100 * row.rel[k]:14.3f}" for k in KEYS) + f"  {row.note}")
    print(f"  {'total':14s}" + "".join(f"{100 * b.total[k]:14.3f}" for k in KEYS))
    print("\nkey numbers")
    print(f"  {'':14s}" + "".join(f"{k:>14s}" for k in KEYS))
    print(f"  {'2D map':14s}" + "".join(f"{b.values_2d[k]:14.5g}" for k in KEYS))
    print(f"  {'end-corrected':14s}" + "".join(f"{b.values[k]:14.5g}" for k in KEYS))
    print(f"\nlabel: {v.label}")
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(validation_json(v, t1 - t0, t2 - t1), indent=1))


if __name__ == "__main__":
    main()
