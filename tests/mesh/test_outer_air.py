import math

import gmsh
import numpy as np
import pytest

from conftest import make_8_6
from srmcore.geometry.build import build_geometry
from srmcore.geometry.session import gmsh_model
from srmcore.mesh import build_machine_mesh, mesh_at_angle, quality_report
from srmcore.model.design import Design, MeshSettings
from srmcore.model.validator import validate_mesh_settings
from srmcore.topology.radial import build_outline

RING = 0.004


def test_geometry_outer_air_ring(srm_8_6):
    o = build_outline(srm_8_6)
    with gmsh_model():
        g = build_geometry(o, feature_step=1e-4, outer_air_radius=o.stator_outer_radius + RING)
        area = sum(gmsh.model.occ.getMass(2, t) for t in g.region_surfaces["stator_outer_air"])
        assert area == pytest.approx(math.pi * ((o.stator_outer_radius + RING) ** 2 - o.stator_outer_radius**2), rel=1e-6)
        assert g.region_kind["stator_outer_air"] == "air" and g.region_part["stator_outer_air"] == "stator"
        assert g.region_size_key["stator_outer_air"] == "slot_air"
        assert g.outer_boundary_curve != g.stator_outer_curve
        xmin, *_ = gmsh.model.getBoundingBox(1, g.outer_boundary_curve)
        assert -xmin == pytest.approx(o.stator_outer_radius + RING, rel=1e-4)


def test_without_ring_outer_boundary_is_stator_od(srm_8_6):
    with gmsh_model():
        g = build_geometry(build_outline(srm_8_6), feature_step=1e-4)
        assert "stator_outer_air" not in g.region_surfaces
        assert g.outer_boundary_curve == g.stator_outer_curve


def test_mesh_outer_edges_move_to_the_ring():
    p = make_8_6()
    static = build_machine_mesh(Design(machine=p, mesh=MeshSettings(preset="screening", outer_air_thickness=RING)))
    xy = static.stator.nodes[static.outer_edges.ravel()]
    assert np.allclose(np.hypot(xy[:, 0], xy[:, 1]), p.stator_outer_radius + RING, rtol=1e-9)
    m = mesh_at_angle(static, 0.0)
    assert quality_report(m).triangles_per_region["stator_outer_air"] > 0


def test_outer_air_thickness_validation(srm_8_6):
    errors = lambda t: {(i.parameter, i.rule) for i in validate_mesh_settings(  # noqa: E731
        MeshSettings(outer_air_thickness=t), srm_8_6) if i.severity == "error"}
    assert errors(0.0) == set() and errors(0.005) == set()
    assert ("outer_air_thickness", "non_negative") in errors(-0.001)
    assert ("outer_air_thickness", "units") in errors(5.0)
    assert ("outer_air_thickness", "finite") in errors(float("nan"))
