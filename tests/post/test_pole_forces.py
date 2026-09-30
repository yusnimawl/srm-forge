"""Per-pole Maxwell-stress forces on the 8/6 screening mesh."""
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.model.constants import MU0
from srmcore.physics.fem import triangle_areas
from srmcore.post.forces import pole_forces
from srmcore.post.quantities import _MIDPOINTS, arkkio_torque
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


def test_partially_aligned_pole_is_pulled_towards_the_rotor_pole(static):
    p, s = _solve(static, 10.0, 20.0)
    f = pole_forces(p, s, NS)
    print("pole 0 force at 10 deg, 20 A (N):", f[0].tolist(), "torque", arkkio_torque(p, s))
    assert arkkio_torque(p, s) < 0                    # the rotor is pulled back towards alignment
    assert f[0, 1] > 0.01 * abs(f[0, 0])              # the reaction pulls the stator pole counter-clockwise


def test_pole_vectors_sum_to_minus_the_rotor_force(static):
    p, s = _solve(static, 10.0, 20.0)
    f = pole_forces(p, s, NS)
    phi = np.arange(NS) * 2 * np.pi / NS
    net = np.array([np.sum(f[:, 0] * np.cos(phi) - f[:, 1] * np.sin(phi)),
                    np.sum(f[:, 0] * np.sin(phi) + f[:, 1] * np.cos(phi))])
    el = p.band.elements
    tri = p.triangles[el]
    corners = p.nodes[tri]
    rotor = np.zeros(2)                                # Maxwell force on the rotor, integrated over the whole band
    for w in _MIDPOINTS:
        q = np.einsum("j,njk->nk", w, corners)
        bx, by = s.b[el, 0], s.b[el, 1]
        # rotor-side traction: T = (B·n)B/μ0 - |B|²n/(2μ0) with n = outward normal r̂ of the rotor, in x-y
        rx, ry = q[:, 0] / np.hypot(*q.T), q[:, 1] / np.hypot(*q.T)
        bn = bx * rx + by * ry
        tx, ty = (bn * bx - 0.5 * (bx**2 + by**2) * rx) / MU0, (bn * by - 0.5 * (bx**2 + by**2) * ry) / MU0
        area = triangle_areas(p.nodes, tri)
        rotor += np.array([tx @ area, ty @ area]) / 3
    rotor *= p.depth / (p.band.outer_radius - p.band.inner_radius)
    assert np.allclose(net, -rotor, rtol=1e-9, atol=1e-9 * abs(f[0, 0]))


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
