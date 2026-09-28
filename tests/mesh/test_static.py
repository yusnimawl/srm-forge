import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import InputError
from srmcore.mesh.sizing import SizeField, size_at
from srmcore.mesh.static import build_static_mesh, orient_ccw


@pytest.fixture(scope="module")
def static_8_6():
    return build_static_mesh(Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))


def _areas(nodes, tris):
    p = nodes[tris]
    return 0.5 * ((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                  - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))


def test_size_field_matches_size_at():
    rng = np.random.default_rng(0)
    features = [(rng.random((50, 2)), 0.01, 1.3), (rng.random((5, 2)), 0.002, 1.1)]
    field = SizeField(features)
    for x, y in rng.random((20, 2)):
        assert field(x, y, 0.05) == pytest.approx(size_at(x, y, 0.05, features))


def test_orient_ccw_flips_clockwise():
    nodes = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    assert orient_ccw(nodes, np.array([[0, 2, 1]])).tolist() == [[0, 1, 2]]


def test_parts_are_valid_and_ccw(static_8_6):
    for part in (static_8_6.stator, static_8_6.rotor):
        assert len(part.nodes) > 0 and len(part.triangles) > 0
        assert np.all(_areas(part.nodes, part.triangles) > 0)
        assert part.triangles.max() < len(part.nodes)


def test_part_areas_match_geometry(static_8_6):
    p = make_8_6()
    s = static_8_6
    assert _areas(s.stator.nodes, s.stator.triangles).sum() == pytest.approx(
        math.pi * (p.stator_outer_radius**2 - p.band_outer_radius**2), rel=2e-3)
    assert _areas(s.rotor.nodes, s.rotor.triangles).sum() == pytest.approx(math.pi * p.band_inner_radius**2, rel=2e-3)


def test_every_region_has_triangles(static_8_6):
    s = static_8_6
    used = set(np.unique(s.stator.region_ids)) | set(np.unique(s.rotor.region_ids))
    assert used == set(range(len(s.region_names)))
    assert "coil_D2-" in s.region_names and "airgap_rotor" in s.region_names


def test_band_rings_are_uniform(static_8_6):
    s = static_8_6
    n = s.settings.band_divisions
    for nodes, ring, radius in ((s.stator.nodes, s.stator_ring, s.band_outer_radius),
                                (s.rotor.nodes, s.rotor_ring, s.band_inner_radius)):
        assert len(ring) == n   # if this is n+1 or n-1, fix the setTransfiniteCurve count in static.py
        xy = nodes[ring]
        assert np.allclose(np.hypot(xy[:, 0], xy[:, 1]), radius, rtol=1e-9)
        ang = np.mod(np.arctan2(xy[:, 1], xy[:, 0]), 2 * math.pi)
        assert np.allclose(np.diff(ang), 2 * math.pi / n, rtol=1e-6)


def test_outer_edges_on_stator_od(static_8_6):
    xy = static_8_6.stator.nodes[static_8_6.outer_edges.ravel()]
    assert np.allclose(np.hypot(xy[:, 0], xy[:, 1]), make_8_6().stator_outer_radius, rtol=1e-9)


def test_gap_elements_are_small(static_8_6):
    s = static_8_6
    gap_id = s.region_names.index("airgap_stator")
    tris = s.stator.triangles[s.stator.region_ids == gap_id]
    p = s.stator.nodes[tris]
    longest = np.max(np.linalg.norm(p - np.roll(p, 1, axis=1), axis=2))
    pitch_len = s.band_outer_radius * s.settings.band_pitch
    assert longest <= 1.3 * max(s.settings.gap_size, pitch_len)


def test_invalid_design_fails_before_gmsh():
    with pytest.raises(InputError):
        build_static_mesh(Design(machine=make_8_6(air_gap=-0.001)))
