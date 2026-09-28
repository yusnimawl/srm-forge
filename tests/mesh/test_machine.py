import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.model.design import Design, MeshSettings
from srmcore.mesh.machine import mesh_at_angle
from srmcore.mesh.quality import triangle_quality
from srmcore.mesh.static import build_static_mesh

TAU = 2 * math.pi


@pytest.fixture(scope="module")
def static_8_6():
    return build_static_mesh(Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))


def _areas(nodes, tris):
    p = nodes[tris]
    return 0.5 * ((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                  - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))


def test_triangle_quality_reference_shapes():
    nodes = np.array([[0.0, 0.0], [1.0, 0.0], [0.5, math.sqrt(3) / 2], [0.0, 1.0]])
    min_angle, aspect = triangle_quality(nodes, np.array([[0, 1, 2], [0, 1, 3]]))
    assert min_angle[0] == pytest.approx(60.0) and aspect[0] == pytest.approx(1.0)
    assert min_angle[1] == pytest.approx(45.0) and aspect[1] == pytest.approx(math.sqrt(2) / (2 * math.sqrt(3) * (1 - math.sqrt(2) / 2)))


def test_mesh_at_zero_is_complete_and_ccw(static_8_6):
    m = mesh_at_angle(static_8_6, 0.0)
    assert np.all(_areas(m.nodes, m.triangles) > 0)
    assert m.region_names[-1] == "moving_band"
    assert m.triangles[m.band_rows].shape[0] == 2 * static_8_6.settings.band_divisions
    assert _areas(m.nodes, m.triangles).sum() == pytest.approx(math.pi * make_8_6().stator_outer_radius**2, rel=2e-3)


def test_node_numbering_is_stable_and_rotor_rotates(static_8_6):
    theta = 0.123
    m0, m1 = mesh_at_angle(static_8_6, 0.0), mesh_at_angle(static_8_6, theta)
    ns = m0.n_stator_nodes
    assert np.array_equal(m0.nodes[:ns], m1.nodes[:ns])
    c, s = math.cos(theta), math.sin(theta)
    x, y = m0.nodes[ns:, 0], m0.nodes[ns:, 1]
    assert np.allclose(m1.nodes[ns:], np.c_[c * x - s * y, s * x + c * y], atol=1e-15)
    assert np.array_equal(m0.triangles[: m0.band_rows.start], m1.triangles[: m1.band_rows.start])


@pytest.mark.parametrize("shift", [TAU, -TAU, 7 * TAU])
def test_angle_wrapping(static_8_6, shift):
    a, b = mesh_at_angle(static_8_6, 0.4), mesh_at_angle(static_8_6, 0.4 + shift)
    assert b.rotor_angle == pytest.approx(a.rotor_angle, abs=1e-12)
    assert np.allclose(a.nodes, b.nodes, atol=1e-12)
    assert np.array_equal(a.triangles, b.triangles)


def test_band_quality_at_pitch_multiples_and_half_pitch(static_8_6):
    pitch = static_8_6.settings.band_pitch
    q = {}
    for k in (0.0, 1.0, 0.5, 3.25):
        m = mesh_at_angle(static_8_6, k * pitch)
        band = m.triangles[m.band_rows]
        q[k] = triangle_quality(m.nodes, band)[0].min()
        assert q[k] >= static_8_6.settings.band_min_angle_deg
    assert q[0.0] == pytest.approx(q[1.0], abs=1e-9)
