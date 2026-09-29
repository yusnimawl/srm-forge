"""Refining the band pitch shrinks the change in Arkkio torque (spec §9 M3: band-pitch convergence)."""
import math

import pytest

from conftest import make_8_6
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.mesh.settings import resolve_mesh_settings
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import arkkio_torque
from srmcore.solvers.skfem_reference import SkfemReference


@pytest.mark.slow
def test_arkkio_torque_converges_with_band_divisions():
    machine = make_8_6()
    base = resolve_mesh_settings(machine, MeshSettings(preset="screening")).band_divisions
    torques = []
    for factor in (1, 2, 4):
        design = Design(machine=machine, mesh=MeshSettings(preset="screening", airgap_circumferential_divisions=base * factor))
        problem = machine_problem(mesh_at_angle(build_machine_mesh(design), math.radians(10.0)), design, {"A": 20.0})
        torques.append(arkkio_torque(problem, SkfemReference().solve(problem)))
    assert abs(torques[2] - torques[1]) < abs(torques[1] - torques[0])
