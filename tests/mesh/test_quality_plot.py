import dataclasses

import numpy as np
import pytest

from conftest import make_8_6, make_12_8, make_24_16
from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.model.errors import MeshRejected
from srmcore.mesh import build_machine_mesh, check_quality, mesh_at_angle, plot_mesh, quality_report


@pytest.fixture(scope="module")
def static_8_6():
    return build_machine_mesh(Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))


def test_report_counts(static_8_6):
    m = mesh_at_angle(static_8_6, 0.0)
    r = quality_report(m)
    assert r.n_nodes == len(m.nodes) and r.n_triangles == len(m.triangles)
    assert sum(r.triangles_per_region.values()) == r.n_triangles
    assert r.triangles_per_region["moving_band"] == 2 * static_8_6.settings.band_divisions
    assert r.min_angle_deg >= static_8_6.settings.min_angle_deg
    assert r.max_aspect_ratio <= static_8_6.settings.max_aspect_ratio


def test_check_quality_lists_all_violations(static_8_6):
    r = quality_report(mesh_at_angle(static_8_6, 0.0))
    strict = dataclasses.replace(static_8_6.settings, min_angle_deg=59.0, band_min_angle_deg=59.0, max_aspect_ratio=1.01)
    with pytest.raises(MeshRejected) as info:
        check_quality(r, strict)
    assert len(info.value.reasons) == 3
    assert info.value.report is r


def test_build_machine_mesh_rejects_bad_quality():
    with pytest.raises(MeshRejected):
        build_machine_mesh(Design(machine=make_8_6(), mesh=MeshSettings(preset="screening", min_angle_deg=59.0)))


def test_plot_writes_png(static_8_6, tmp_path):
    out = plot_mesh(mesh_at_angle(static_8_6, 0.1), tmp_path / "mesh.png", title="8/6 screening")
    assert out.exists() and out.stat().st_size > 10_000


def test_sharp_corners_mesh():
    s = build_machine_mesh(Design(machine=make_8_6(stator_fillet_radius=0.0, rotor_fillet_radius=0.0),
                                  mesh=MeshSettings(preset="screening")))
    assert len(mesh_at_angle(s, 0.0).triangles) > 0


def test_airgap_interface_grading_fixes_rotor_slot_air_slivers():
    """Regression test: this valid, validate_params-passing 6/4/3 design produced sliver triangles
    all along the slot-mouth arcs (rotor_slot_air's min angle was 6.51 deg, below the 10 deg gate)
    because the background size jumped straight from the air gap's fine size to the iron-scale size
    across those arcs, with no grading. The "airgap_interface" refinement feature
    (topology/radial.py, mesh/settings.py) grades the size away from both interfaces instead.
    """
    p = RadialSRMParams(
        n_stator_poles=6, n_rotor_poles=4, n_phases=3,
        stator_outer_diameter=0.125, rotor_outer_diameter=0.0625, air_gap=0.00025,
        stack_length=0.08, shaft_diameter=0.015625,
        stator_pole_arc=0.625, rotor_pole_arc=0.625,
        stator_pole_taper=0.0, rotor_pole_taper=0.0,
        stator_yoke_thickness=0.0078125, rotor_yoke_thickness=0.0078125,
        stator_fillet_radius=0.0, rotor_fillet_radius=0.0,
        turns_per_pole=40, fill_factor=0.5,
        slot_liner_thickness=0.0004, coil_inner_clearance=0.001,
    )
    s = build_machine_mesh(Design(machine=p, mesh=MeshSettings(preset="screening")))
    r = quality_report(mesh_at_angle(s, 0.0))
    assert r.min_angle_deg >= s.settings.min_angle_deg
    assert r.max_aspect_ratio <= s.settings.max_aspect_ratio


def test_two_builds_in_one_process_are_identical(static_8_6):
    again = build_machine_mesh(Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))
    assert np.array_equal(again.stator.nodes, static_8_6.stator.nodes)
    assert np.array_equal(again.rotor.triangles, static_8_6.rotor.triangles)
    assert again.region_names == static_8_6.region_names


@pytest.mark.slow
@pytest.mark.parametrize("factory", [make_12_8, make_24_16])
@pytest.mark.parametrize("preset", ["screening", "full"])
def test_other_reference_designs_mesh(factory, preset, tmp_path):
    s = build_machine_mesh(Design(machine=factory(), mesh=MeshSettings(preset=preset)))
    m = mesh_at_angle(s, 0.3 * s.settings.band_pitch)
    plot_mesh(m, tmp_path / f"{factory.__name__}_{preset}.png")
    check_quality(quality_report(m), s.settings)
