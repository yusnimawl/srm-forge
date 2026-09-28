import math

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st

from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.model.errors import InputError
from srmcore.model.validator import validate_params
from srmcore.mesh import build_machine_mesh, mesh_at_angle, quality_report

TOPOLOGIES = [(6, 4, 3), (8, 6, 4), (12, 8, 3)]


@st.composite
def radial_designs(draw) -> RadialSRMParams:
    ns, nr, m = draw(st.sampled_from(TOPOLOGIES))
    rotor_od = draw(st.floats(0.05, 0.12))
    stator_od = rotor_od / draw(st.floats(0.5, 0.62))
    gap = draw(st.floats(0.00025, 0.0008))
    limit = 2 * math.pi / (m * nr)
    beta_s = draw(st.floats(1.02 * limit, 1.4 * limit))
    beta_r = draw(st.floats(beta_s, 1.6 * limit))
    return RadialSRMParams(
        n_stator_poles=ns, n_rotor_poles=nr, n_phases=m,
        stator_outer_diameter=stator_od, rotor_outer_diameter=rotor_od, air_gap=gap,
        stack_length=0.08, shaft_diameter=rotor_od * draw(st.floats(0.2, 0.35)),
        stator_pole_arc=beta_s, rotor_pole_arc=beta_r,
        stator_pole_taper=draw(st.floats(0.0, math.radians(5))),
        rotor_pole_taper=draw(st.floats(0.0, math.radians(5))),
        stator_yoke_thickness=stator_od * draw(st.floats(0.06, 0.1)),
        rotor_yoke_thickness=rotor_od * draw(st.floats(0.12, 0.2)),
        stator_fillet_radius=draw(st.sampled_from([0.0, 0.0005, 0.001])),
        rotor_fillet_radius=draw(st.sampled_from([0.0, 0.0005, 0.001])),
        turns_per_pole=40, fill_factor=0.5,
        slot_liner_thickness=0.0004, coil_inner_clearance=0.001,
    )


def _check(p: RadialSRMParams, theta_frac: float) -> None:
    assume(not any(i.severity == "error" for i in validate_params(p)))
    try:
        static = build_machine_mesh(Design(machine=p, mesh=MeshSettings(preset="screening")))
    except InputError:
        assume(False)
    m = mesh_at_angle(static, theta_frac * 2 * math.pi)
    tri = m.nodes[m.triangles]
    areas = 0.5 * ((tri[:, 1, 0] - tri[:, 0, 0]) * (tri[:, 2, 1] - tri[:, 0, 1])
                   - (tri[:, 2, 0] - tri[:, 0, 0]) * (tri[:, 1, 1] - tri[:, 0, 1]))
    assert np.all(areas > 0)
    assert areas.sum() == pytest.approx(math.pi * p.stator_outer_radius**2, rel=5e-3)
    assert len(static.stator_ring) == len(static.rotor_ring) == static.settings.band_divisions
    r = quality_report(m)
    assert r.band_min_angle_deg >= static.settings.band_min_angle_deg
    assert all(r.triangles_per_region[n] > 0 for n in m.region_names)


_COMMON = dict(deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])


@settings(max_examples=5, **_COMMON)
@given(radial_designs(), st.floats(0.0, 1.0))
def test_valid_designs_mesh_fast(p, theta_frac):
    _check(p, theta_frac)


@pytest.mark.slow
@settings(max_examples=50, **_COMMON)
@given(radial_designs(), st.floats(0.0, 1.0))
def test_valid_designs_mesh_many(p, theta_frac):
    _check(p, theta_frac)
