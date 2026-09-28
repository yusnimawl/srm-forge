import math

import gmsh
import pytest

from srmcore.geometry.build import ROTOR_REGIONS, STATOR_REGIONS, build_geometry
from srmcore.geometry.session import gmsh_model
from srmcore.topology.radial import build_outline


def _area(tags):
    return sum(gmsh.model.occ.getMass(2, t) for t in tags)


def test_regions_parts_and_areas(srm_8_6):
    o = build_outline(srm_8_6)
    with gmsh_model():
        g = build_geometry(o, feature_step=1e-4)
        coil_names = {c.name for c in o.coil_sides}
        assert set(g.region_surfaces) == set(STATOR_REGIONS) | set(ROTOR_REGIONS) | coil_names
        assert all(len(t) >= 1 for t in g.region_surfaces.values())
        assert all(g.region_part[n] == "stator" for n in coil_names | set(STATOR_REGIONS))
        assert all(g.region_part[n] == "rotor" for n in ROTOR_REGIONS)
        assert g.region_size_key["coil_A1+"] == "coil"
        assert g.region_size_key["airgap_rotor"] == "airgap"
        assert g.region_part["rotor_slot_air"] == "rotor"
        assert g.region_size_key["rotor_slot_air"] == "slot_air"

        stator_total = sum(_area(g.region_surfaces[n]) for n in g.region_surfaces if g.region_part[n] == "stator")
        rotor_total = sum(_area(g.region_surfaces[n]) for n in g.region_surfaces if g.region_part[n] == "rotor")
        assert stator_total == pytest.approx(math.pi * (o.stator_outer_radius**2 - o.band_outer_radius**2), rel=1e-6)
        assert rotor_total == pytest.approx(math.pi * o.band_inner_radius**2, rel=1e-6)
        assert _area(g.region_surfaces["shaft"]) == pytest.approx(math.pi * o.shaft_radius**2, rel=1e-6)
        assert _area(g.region_surfaces["airgap_rotor"]) == pytest.approx(
            math.pi * (o.band_inner_radius**2 - o.rotor_outer_radius**2), rel=1e-6)
        assert all(_area(g.region_surfaces[n]) > 0 for n in coil_names)


def test_band_and_outer_curves_are_full_circles(srm_8_6):
    o = build_outline(srm_8_6)
    with gmsh_model():
        g = build_geometry(o, feature_step=1e-4)
        tags = {g.band_inner_curve, g.band_outer_curve, g.stator_outer_curve}
        assert len(tags) == 3
        for tag, radius in ((g.band_inner_curve, o.band_inner_radius),
                            (g.band_outer_curve, o.band_outer_radius),
                            (g.stator_outer_curve, o.stator_outer_radius)):
            assert gmsh.model.getType(1, tag) == "Circle"
            xmin, ymin, _, xmax, ymax, _ = gmsh.model.getBoundingBox(1, tag)
            assert xmax == pytest.approx(radius, rel=1e-4) and ymin == pytest.approx(-radius, rel=1e-4)
        names = {gmsh.model.getPhysicalName(d, t) for d, t in gmsh.model.getPhysicalGroups()}
        assert {"stator_outer", "band_outer", "band_inner", "stator_iron", "coil_A1+"} <= names


def test_refinement_points_sampled(srm_8_6):
    o = build_outline(srm_8_6)
    with gmsh_model():
        g = build_geometry(o, feature_step=1e-4)
    assert g.refinement_points["pole_tip"].shape[1] == 2
    assert len(g.refinement_points["pole_tip"]) > 14
    assert len(g.refinement_points["pole_root"]) >= 28


def test_session_isolation_and_reuse(srm_8_6):
    o = build_outline(srm_8_6)
    areas = []
    for _ in range(2):
        with gmsh_model() as name:
            g = build_geometry(o, feature_step=1e-4)
            areas.append(_area(g.region_surfaces["stator_iron"]))
        assert name not in gmsh.model.list()
    assert areas[0] == pytest.approx(areas[1], rel=1e-12)
