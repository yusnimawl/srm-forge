import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import InputError
from srmcore.model.regions import CoilInfo
from srmcore.mesh.api import build_machine_mesh
from srmcore.mesh.machine import mesh_at_angle
from srmcore.mesh.quality import quality_report
from srmcore.mesh.static import build_static_mesh, orient_ccw
from srmcore.topology.radial import build_outline

EXPECTED_8_6_KINDS = {
    "stator_iron": "stator_iron", "slot_air": "air", "airgap_stator": "air",
    "rotor_iron": "rotor_iron", "shaft": "shaft", "airgap_rotor": "air", "rotor_slot_air": "air",
    "coil_A1+": "coil", "coil_A1-": "coil", "coil_A2+": "coil", "coil_A2-": "coil",
    "coil_B1+": "coil", "coil_B1-": "coil", "coil_B2+": "coil", "coil_B2-": "coil",
    "coil_C1+": "coil", "coil_C1-": "coil", "coil_C2+": "coil", "coil_C2-": "coil",
    "coil_D1+": "coil", "coil_D1-": "coil", "coil_D2+": "coil", "coil_D2-": "coil",
}


@pytest.fixture(scope="module")
def static_8_6():
    return build_static_mesh(Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))


def _areas(nodes, tris):
    p = nodes[tris]
    return 0.5 * ((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                  - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))


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


def test_rotor_mesh_is_not_disproportionately_larger(static_8_6):
    # Guards against a region (e.g. the interpolar rotor slot air) falling back into the
    # airgap size class, which previously produced a rotor mesh ~23x the stator's.
    s = static_8_6
    assert len(s.rotor.triangles) < 5 * len(s.stator.triangles)


def test_every_region_has_a_part_and_a_kind(static_8_6):
    s = static_8_6
    assert set(s.region_part) == set(s.region_names)
    assert set(s.region_kind) == set(s.region_names)
    assert s.region_kind == EXPECTED_8_6_KINDS


def test_every_coil_region_has_a_matching_coil_info(static_8_6):
    o = build_outline(make_8_6())
    assert set(static_8_6.coils) == {c.name for c in o.coil_sides}
    for c in o.coil_sides:
        info = static_8_6.coils[c.name]
        assert info == CoilInfo(pole=c.pole, phase=chr(ord("A") + c.phase), sign=c.sign)


def test_no_stray_refinement_point_nodes(static_8_6):
    # Free (non-embedded) points added for the Distance/MathEval size fields must not leak into a
    # MeshPart. Every node kept in a part must be referenced by at least one triangle.
    for part in (static_8_6.stator, static_8_6.rotor):
        used = np.unique(part.triangles)
        assert used.tolist() == list(range(len(part.nodes)))


def test_mesh_gate_passes_for_8_6_screening():
    # build_machine_mesh raises MeshRejected if quality drops below the settings' thresholds
    # (min angle >= 10 deg for the default screening preset); reaching this point is the gate.
    static = build_machine_mesh(Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))
    report = quality_report(mesh_at_angle(static, 0.0, check=False))
    assert report.min_angle_deg >= static.settings.min_angle_deg


def test_triangle_count_regression_within_25pct_of_baseline(static_8_6):
    # Baseline measured for this 8/6 screening design with the "airgap_interface" grading in
    # place (topology/radial.py, mesh/settings.py): stator 54674, rotor 29310 triangles. That
    # grading intentionally adds triangles near the slot-mouth arcs to fix rotor_slot_air/slot_air
    # sliver triangles that would otherwise fall below the quality gate.
    s = static_8_6
    assert len(s.stator.triangles) == pytest.approx(54674, rel=0.25)
    assert len(s.rotor.triangles) == pytest.approx(29310, rel=0.25)
