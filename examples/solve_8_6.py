"""Solve the 8/6 SRM magnetostatically at the aligned and unaligned positions and print ψ, torque,
energies and the saturation report.

Run from the repo root:  .venv\\Scripts\\python examples\\solve_8_6.py [screening|full]
"""
import math
import sys
import time

from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import arkkio_torque, flux_linkage, saturation_report
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
static = build_machine_mesh(design)
solver = SkfemReference()
for label, theta in (("aligned", 0.0), ("unaligned", math.pi / machine.n_rotor_poles), ("10 deg", math.radians(10.0))):
    mesh = mesh_at_angle(static, theta)
    problem = machine_problem(mesh, design)
    a = None
    print(f"--- {label} ({mesh.rotor_angle:.4f} rad)")
    for amps in (5.0, 10.0, 20.0):
        p = problem.with_currents([amps, 0.0, 0.0, 0.0])
        start = time.perf_counter()
        s = solver.solve(p, initial=a)
        seconds = time.perf_counter() - start
        a = s.a
        print(f"  i={amps:5.1f} A  {s.status.value:<16} it={s.iterations:2d} {seconds:5.1f}s  psi_A={flux_linkage(p, s)[0]:.5f} Wb  "
              f"T={arkkio_torque(p, s):+.4f} Nm  W={s.energy:.4f} J  W'={s.coenergy:.4f} J")
    peaks = {k: round(v.peak, 3) for k, v in saturation_report(p, s, machine).items()
             if k in ("stator_poles", "stator_yoke", "rotor_poles", "rotor_yoke")}
    print(f"  peak |B| at 20 A: {peaks}")
