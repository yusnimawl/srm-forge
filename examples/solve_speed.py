r"""Time cold and warm solves of the 8/6 on the screening preset with each solver.

Run:  .venv\Scripts\python examples\solve_speed.py [screening|full]
"""
import math
import sys
import time

from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.physics.build import machine_problem
from srmcore.solvers.ngsolve_adapter import NgsolveAdapter
from srmcore.solvers.skfem_reference import SkfemReference

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
preset = sys.argv[1] if len(sys.argv) > 1 else "screening"
design = Design(machine=machine, mesh=MeshSettings(preset=preset))
start = time.perf_counter()
static = build_machine_mesh(design)
print(f"mesh build {time.perf_counter() - start:.1f} s")
problem = machine_problem(mesh_at_angle(static, 0.0), design)
print(f"{len(problem.nodes)} nodes")

for solver in (NgsolveAdapter(), SkfemReference()):
    print(f"--- {solver.name}")
    for amps in (20.0, 20.0):     # the first call also builds the discretisation
        start = time.perf_counter()
        s = solver.solve(problem.with_currents([amps, 0, 0, 0]))
        print(f"  cold {amps:4.0f} A  {s.status.value:<16} it={s.iterations:2d}  {time.perf_counter() - start:5.2f} s")
    total_it, start = 0, time.perf_counter()
    a = None
    for amps in (5.0, 10.0, 20.0):
        s = solver.solve(problem.with_currents([amps, 0, 0, 0]), initial=a)
        a, total_it = s.a, total_it + s.iterations
    print(f"  sweep 5-10-20 A (warm start)  it={total_it}  {time.perf_counter() - start:5.2f} s")
