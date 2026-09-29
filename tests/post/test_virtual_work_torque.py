"""Nodal-force (virtual-work) torque: agrees with Arkkio on the 8/6 screening mesh (spec §7.3)."""
import math

import pytest

from conftest import make_8_6
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import arkkio_torque, virtual_work_torque
from srmcore.solvers.skfem_reference import SkfemReference

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


@pytest.fixture(scope="module")
def solved():
    static = build_machine_mesh(DESIGN)
    problem = machine_problem(mesh_at_angle(static, math.radians(10.0)), DESIGN, {"A": 20.0})
    return problem, SkfemReference().solve(problem)


def test_virtual_work_matches_arkkio_within_one_percent(solved):
    problem, solution = solved
    arkkio = arkkio_torque(problem, solution)
    assert arkkio < 0                                   # counter-clockwise motoring sign at this angle
    assert virtual_work_torque(problem, solution) == pytest.approx(arkkio, abs=0.01 * abs(arkkio))


def test_virtual_work_needs_a_band(solved):
    import dataclasses
    problem, solution = solved
    with pytest.raises(ValueError, match="band"):
        virtual_work_torque(dataclasses.replace(problem, band=None), solution)


@pytest.mark.slow
def test_virtual_work_tracks_arkkio_over_a_stroke():
    static = build_machine_mesh(DESIGN)
    solver = SkfemReference()
    pairs = []
    for deg in (2.0, 6.0, 10.0, 14.0, 18.0, 22.0):
        p = machine_problem(mesh_at_angle(static, math.radians(deg)), DESIGN, {"A": 20.0})
        s = solver.solve(p)
        pairs.append((arkkio_torque(p, s), virtual_work_torque(p, s)))
    peak = max(abs(a) for a, _ in pairs)
    assert all(abs(a - v) <= 0.01 * peak for a, v in pairs), pairs
