"""Mesh an 8/6 SRM and save plots at two rotor angles.

Run from the repo root:  .venv\\Scripts\\python examples\\mesh_8_6.py
"""
import math
import sys

from srmcore.mesh import build_machine_mesh, mesh_at_angle, plot_mesh, quality_report
from srmcore.model.design import Design, MeshSettings, RadialSRMParams

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
preset = sys.argv[1] if len(sys.argv) > 1 else "full"
design = Design(machine=machine, mesh=MeshSettings(preset=preset))

static = build_machine_mesh(design)  # validates, meshes, and runs the quality gate
for label, theta in (("aligned", 0.0), ("half_pitch", static.settings.band_pitch / 2)):
    mesh = mesh_at_angle(static, theta)
    q = quality_report(mesh)
    out = plot_mesh(mesh, f"mesh_8_6_{preset}_{label}.png", title=f"8/6 {preset}, rotor at {math.degrees(theta):.3f} deg")
    print(f"{out}: {q}")
