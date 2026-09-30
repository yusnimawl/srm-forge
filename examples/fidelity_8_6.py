r"""Screening-vs-full fidelity check on variants of the example 8/6 (I_max = 20 A).

Run from the repo root:  .venv\Scripts\python examples\fidelity_8_6.py [cache_dir] [n_designs]
Full maps are 600 points on the fine mesh; pass a cache_dir so reruns are free.
"""
import math
import sys
import time

from srmcore.maps.fidelity import KEYS, fidelity_check
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design, MeshSettings, RadialSRMParams

VARIANTS = ((18, 22), (20, 22), (22, 24), (20, 24))     # (stator, rotor) pole arc, degrees


def variant(beta_s: float, beta_r: float) -> Design:
    machine = RadialSRMParams(
        n_stator_poles=8, n_rotor_poles=6, n_phases=4,
        stator_outer_diameter=0.160, rotor_outer_diameter=0.080, air_gap=0.0004,
        stack_length=0.100, shaft_diameter=0.020,
        stator_pole_arc=math.radians(beta_s), rotor_pole_arc=math.radians(beta_r),
        stator_yoke_thickness=0.012, rotor_yoke_thickness=0.012,
        stator_fillet_radius=0.001, rotor_fillet_radius=0.001,
        turns_per_pole=60, fill_factor=0.5,
        slot_liner_thickness=0.0005, coil_inner_clearance=0.001,
    )
    return Design(machine=machine, mesh=MeshSettings(preset="screening"))


def main() -> None:
    cache_dir = sys.argv[1] if len(sys.argv) > 1 else None
    n = int(sys.argv[2]) if len(sys.argv) > 2 else len(VARIANTS)
    designs = []
    for bs, br in VARIANTS[:n]:
        d = variant(bs, br)
        build_machine_mesh(d)                       # raises InputError on an invalid variant
        designs.append(d)
    start = time.perf_counter()
    rep = fidelity_check(designs, 20.0, cache_dir=cache_dir)
    print(f"{len(designs)} designs, {time.perf_counter() - start:.0f} s wall")
    print("variant (bs/br)  " + "  ".join(f"{k:>12}" for k in KEYS))
    for j, (bs, br) in enumerate(VARIANTS[:n]):
        print(f"{bs:>5}/{br:<10}" + "  ".join(f"{100 * rep.rel_error[k][j]:>11.2f}%" for k in KEYS))
    print("spearman         " + "  ".join(f"{rep.spearman[k]:>12.3f}" for k in KEYS))
    print("ok:", rep.ok)


if __name__ == "__main__":       # spawn workers re-import this module
    main()
