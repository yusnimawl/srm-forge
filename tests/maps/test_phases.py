"""Diagonal maps: every phase of the 8/6 is the phase-A machine rotated by k·ε (screening mesh, 10 A)."""
import math

import pytest

from conftest import make_8_6
from srmcore.maps.grids import aligned_angle
from srmcore.maps.point import solve_point
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design, MeshSettings
from srmcore.solvers.factory import make_solver

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
TAU = 2 * math.pi / DESIGN.machine.n_rotor_poles


@pytest.mark.slow
def test_every_phase_is_symmetric_to_phase_a():
    static, solver = build_machine_mesh(DESIGN), make_solver("ngsolve")
    ref = solve_point(static, DESIGN, 0.0, {"A": 10.0}, solver)
    quarter = solve_point(static, DESIGN, TAU / 4, {"A": 10.0}, solver)
    for k, letter in enumerate("BCD", start=1):
        theta = aligned_angle(DESIGN.machine, letter)
        aligned = solve_point(static, DESIGN, theta, {letter: 10.0}, solver)
        off = solve_point(static, DESIGN, theta + TAU / 4, {letter: 10.0}, solver)
        assert abs(aligned.torque_arkkio) < 0.01 * abs(off.torque_arkkio)
        assert aligned.psi[k] == pytest.approx(ref.psi[0], rel=1e-3)
        assert off.torque_arkkio == pytest.approx(quarter.torque_arkkio, rel=1e-3)
