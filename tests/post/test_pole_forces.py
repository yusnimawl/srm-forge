"""Per-pole Maxwell-stress forces on the 8/6 screening mesh."""
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.post.forces import pole_forces
from srmcore.post.quantities import arkkio_torque
from srmcore.solvers.skfem_reference import SkfemReference

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
NS = DESIGN.machine.n_stator_poles


@pytest.fixture(scope="module")
def static():
    return build_machine_mesh(DESIGN)


def _solve(static, degrees, amps):
    k = round(math.radians(degrees) / static.settings.band_pitch)
    p = machine_problem(mesh_at_angle(static, k * static.settings.band_pitch), DESIGN, {"A": amps})
    return p, SkfemReference().solve(p)


def test_zero_current_gives_zero_force(static):
    p, s = _solve(static, 0.0, 0.0)
    assert pole_forces(p, s, NS).shape == (NS, 2) and not np.any(pole_forces(p, s, NS))


def test_tangential_forces_sum_to_the_arkkio_torque(static):
    p, s = _solve(static, 10.0, 20.0)
    f = pole_forces(p, s, NS)
    r_mid = 0.5 * (p.band.inner_radius + p.band.outer_radius)
    assert f[:, 1].sum() * r_mid == pytest.approx(-arkkio_torque(p, s), rel=0.01)


def test_aligned_pole_pulls_radially_and_the_net_force_cancels(static):
    p, s = _solve(static, 0.0, 20.0)
    f = pole_forces(p, s, NS)
    print("pole forces at 0 deg, 20 A (N):", f.tolist())
    assert f[0, 0] < 0
    phi = np.arange(NS) * 2 * np.pi / NS
    net = np.array([np.sum(f[:, 0] * np.cos(phi) - f[:, 1] * np.sin(phi)),
                    np.sum(f[:, 0] * np.sin(phi) + f[:, 1] * np.cos(phi))])
    assert np.hypot(*net) < 1e-3 * abs(f[0, 0])
    assert abs(f[0, 1]) < 0.01 * abs(f[0, 0])
