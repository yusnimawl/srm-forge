"""Band-pitch convergence on the 8/6 `screening` mesh: ψ_A, Arkkio torque and nodal-force torque at 20 A
for band divisions D, 2D and 4D, at 10° and half a band pitch later.

Run from the repo root:  .venv\\Scripts\\python examples\\band_pitch_convergence.py
"""
import math

from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.mesh.settings import resolve_mesh_settings
from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import arkkio_torque, flux_linkage, virtual_work_torque
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
base = resolve_mesh_settings(machine, MeshSettings(preset="screening")).band_divisions
solver = SkfemReference()
print(f"default band divisions D = {base}")
print(f"{'divisions':>9} {'offset':>10} {'psi_A [Wb]':>12} {'T_arkkio [Nm]':>14} {'T_nodal [Nm]':>13}")
for factor in (1, 2, 4):
    design = Design(machine=machine, mesh=MeshSettings(preset="screening", airgap_circumferential_divisions=base * factor))
    static = build_machine_mesh(design)
    for label, extra in (("0", 0.0), ("half pitch", static.settings.band_pitch / 2)):
        problem = machine_problem(mesh_at_angle(static, math.radians(10.0) + extra), design, {"A": 20.0})
        s = solver.solve(problem)
        print(f"{base * factor:>9} {label:>10} {flux_linkage(problem, s)[0]:12.6f} "
              f"{arkkio_torque(problem, s):14.5f} {virtual_work_torque(problem, s):13.5f}")
