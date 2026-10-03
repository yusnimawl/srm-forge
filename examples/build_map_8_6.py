"""Build the 8/6 screening flux-linkage and torque map (I_max = 20 A) and time it.

Run from the repo root:  .venv\\Scripts\\python examples\\build_map_8_6.py [workers] [solver]
workers defaults to half the logical CPUs; solver is ngsolve (default) or skfem_reference.
"""
import math
import sys
import time

import numpy as np

from srmcore.maps import analyse_map, build_map
from srmcore.maps.grids import LA_CURRENT_FRACTION
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design, MeshSettings, RadialSRMParams


def main() -> None:
    workers = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] != "None" else None
    solver = sys.argv[2] if len(sys.argv) > 2 else "ngsolve"
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
    design = Design(machine=machine, mesh=MeshSettings(preset="screening"))

    start = time.perf_counter()
    build_machine_mesh(design)
    print(f"mesh build alone: {time.perf_counter() - start:.1f} s (build_map meshes again, inside the map time)")

    def progress(done: int, total: int) -> None:
        print(f"  point {done}/{total}  t = {time.perf_counter() - start:.1f} s", flush=True)

    start = time.perf_counter()
    r = build_map(design, 20.0, solver=solver, workers=workers, progress=progress)
    elapsed = time.perf_counter() - start
    n_points = r.status.size
    print(f"map ({solver}, workers={workers}): {elapsed:.1f} s wall, {n_points} points, "
          f"{elapsed / n_points:.2f} s wall per point")
    print("status counts (ok / fallback / nonconverged / not run):",
          [int((r.status == c).sum()) for c in (0, 1, 2, -1)], " filled:", int(r.filled.sum()))
    print(f"iterations: {r.iterations.min()}..{r.iterations.max()}")
    print(f"peak torque (Arkkio): {np.nanmax(np.abs(r.torque_arkkio)):.2f} N m")
    unaligned = int(np.argmin(np.abs(r.angles - math.pi / machine.n_rotor_poles)))
    i_la = int(np.argmin(np.abs(r.currents - LA_CURRENT_FRACTION * r.currents[-1])))
    ratio = r.psi[0, i_la, 0] / r.psi[unaligned, i_la, 0]
    print(f"psi_aligned / psi_unaligned at {r.currents[i_la]:.3f} A: {ratio:.2f}")

    report = analyse_map(r, design)
    k = report.key_numbers
    print(f"key numbers: La {k.la * 1e3:.3f} mH, Lu {k.lu * 1e3:.3f} mH, La/Lu {k.la_lu:.2f}, "
          f"peak torque {k.peak_torque:.2f} N m, psi_max {k.psi_max:.4f} Wb-turns")
    for c in report.checks:
        print(f"  [{c.status:4s}] {c.name}: {c.value:.4g} (limit {c.limit:.4g})")
    print("map ok" if report.ok else "map has failing checks")


if __name__ == "__main__":       # spawn workers re-import this module
    main()
