import dataclasses
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import MeshRejected
from srmcore.mesh.machine import mesh_at_angle
from srmcore.mesh.quality import triangle_quality
from srmcore.mesh.settings import ResolvedMeshSettings
from srmcore.mesh.static import MeshPart, StaticMesh, build_static_mesh

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


def test_machine_mesh_exposes_region_metadata_and_band_radii(static_8_6):
    m = mesh_at_angle(static_8_6, 0.0)
    assert m.region_part == {**static_8_6.region_part, "moving_band": "band"}
    assert set(m.region_part) == set(m.region_names)
    assert m.coils == static_8_6.coils
    assert set(m.region_kind) == set(m.region_names)
    assert m.region_kind["moving_band"] == "air"
    for name in static_8_6.region_names:
        assert m.region_kind[name] == static_8_6.region_kind[name]
    assert m.band_inner_radius == static_8_6.band_inner_radius
    assert m.band_outer_radius == static_8_6.band_outer_radius


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


def _kvals(static):
    n = static.settings.band_divisions
    return (0, 1, 5, 37, n - 1)


def test_band_topology_stable_across_full_turns_at_pitch_multiples(static_8_6):
    # At theta = k*pitch, every inner node ties in angle with an outer node. Before the fix,
    # tiny (~1e-15) float noise between logically-equal representations of the same angle
    # (theta vs theta + TAU) could flip the tie-break and change the band topology.
    pitch = static_8_6.settings.band_pitch
    for k in _kvals(static_8_6):
        theta = k * pitch
        a = mesh_at_angle(static_8_6, theta)
        b = mesh_at_angle(static_8_6, theta + TAU)
        assert np.array_equal(a.triangles, b.triangles), f"k={k}"
        assert np.allclose(a.nodes, b.nodes, atol=1e-12), f"k={k}"


def test_band_topology_stable_near_pitch_multiples(static_8_6):
    pitch = static_8_6.settings.band_pitch
    for k in _kvals(static_8_6):
        theta = k * pitch
        for eps in (1e-13, -1e-13):
            a = mesh_at_angle(static_8_6, theta + eps)
            b = mesh_at_angle(static_8_6, theta + eps + TAU)
            assert np.array_equal(a.triangles, b.triangles), f"k={k} eps={eps}"
            assert np.allclose(a.nodes, b.nodes, atol=1e-12), f"k={k} eps={eps}"


def test_rotor_angle_strictly_below_tau_for_tiny_negative_theta(static_8_6):
    # (-1e-20) % TAU rounds back to exactly TAU in float64; mesh_at_angle must clamp this into
    # the documented [0, TAU) range rather than returning rotor_angle == TAU.
    m = mesh_at_angle(static_8_6, -1e-17)
    assert m.rotor_angle < TAU


def _synthetic_static(n_in: int, n_out: int, r: float, R: float, band_min_angle_deg: float = 10.0) -> StaticMesh:
    a_in = np.arange(n_in) * TAU / n_in
    a_out = np.arange(n_out) * TAU / n_out
    rotor_nodes = r * np.c_[np.cos(a_in), np.sin(a_in)]
    stator_nodes = R * np.c_[np.cos(a_out), np.sin(a_out)]
    empty_tris = np.empty((0, 3), dtype=np.int64)
    empty_ids = np.empty((0,), dtype=np.int32)
    settings = ResolvedMeshSettings(
        gap_size=0.001, region_sizes={}, refinement={}, band_divisions=n_in,
        min_angle_deg=15.0, band_min_angle_deg=band_min_angle_deg, max_aspect_ratio=5.0,
    )
    return StaticMesh(
        region_names=("dummy",),
        region_part={"dummy": "stator"},
        region_kind={"dummy": "air"},
        coils={},
        stator=MeshPart(stator_nodes, empty_tris, empty_ids),
        rotor=MeshPart(rotor_nodes, empty_tris, empty_ids),
        stator_ring=np.arange(n_out, dtype=np.int64),
        rotor_ring=np.arange(n_in, dtype=np.int64),
        outer_edges=np.empty((0, 2), dtype=np.int64),
        band_inner_radius=r, band_outer_radius=R,
        settings=settings, warnings=(),
    )


def test_mesh_at_angle_rejects_an_inverted_band_triangle():
    # Same ring-density mismatch as test_band.py's coarse-ring case: a rotor ring far finer
    # than the stator ring forces an inverted raw zipper triangle. orient_ccw would silently
    # hide this by flipping winding, so mesh_at_angle must check raw signed areas first.
    static = _synthetic_static(n_in=64, n_out=8, r=1.0, R=1.1)
    with pytest.raises(MeshRejected, match="inverted"):
        mesh_at_angle(static, 0.0)


def test_band_min_angle_rejection_and_check_false_bypass(static_8_6):
    # No triangle can have a minimum angle above 60 degrees (equilateral), so this threshold
    # guarantees rejection regardless of the actual mesh geometry.
    strict_settings = dataclasses.replace(static_8_6.settings, band_min_angle_deg=60.1)
    strict_static = dataclasses.replace(static_8_6, settings=strict_settings)
    with pytest.raises(MeshRejected):
        mesh_at_angle(strict_static, 0.0)
    m = mesh_at_angle(strict_static, 0.0, check=False)
    assert m.rotor_angle == pytest.approx(0.0)
