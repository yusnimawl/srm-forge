import math

import numpy as np
import pytest

from conftest import make_8_6
from map_fixtures import synthetic_map
from srmcore.maps.end_winding import coil_geometry, end_winding_inductance, with_end_winding
from srmcore.post.end_winding import end_turn_inductance


def test_coil_geometry_8_6_consistent():
    p = make_8_6()
    g = coil_geometry(p)
    r_in = p.bore_radius + p.coil_inner_clearance
    r_out = p.stator_yoke_inner_radius - 2 * p.stator_fillet_radius - p.slot_liner_thickness
    assert g.depth == pytest.approx(r_out - r_in)
    assert g.build == pytest.approx(g.area / g.depth)
    half = p.stator_pole_arc / 2
    pole_width = 2 * p.bore_radius * math.sin(half)            # untapered pole: parallel flanks
    assert g.span == pytest.approx(pole_width + 2 * p.slot_liner_thickness + g.build)
    assert 0 < g.build < math.pi * p.stator_yoke_inner_radius / p.n_stator_poles


def test_coil_geometry_area_shrinks_with_clearance():
    assert coil_geometry(make_8_6(coil_inner_clearance=0.004)).area < coil_geometry(make_8_6()).area


def test_tapered_pole_span_uses_mid_depth_width():
    p = make_8_6(stator_pole_taper=math.radians(5.0))
    g = coil_geometry(p)
    half = p.stator_pole_arc / 2
    r_in = p.bore_radius + p.coil_inner_clearance
    x_mid = r_in + g.depth / 2
    half_w = p.bore_radius * math.sin(half) + (x_mid - p.bore_radius * math.cos(half)) * math.tan(p.stator_pole_taper)
    assert g.span == pytest.approx(2 * half_w + 2 * p.slot_liner_thickness + g.build)


def test_end_winding_inductance_sums_poles_of_a_phase():
    p = make_8_6()
    g = coil_geometry(p)
    per_coil = end_turn_inductance(p.turns_per_pole, g.span, g.build, g.depth, p.stack_length + g.build, 1.5)
    assert end_winding_inductance(p, 1.5) == pytest.approx(per_coil * (p.n_stator_poles // p.n_phases))


@pytest.mark.parametrize("excited", ["A", "C"])
def test_with_end_winding_shifts_excited_column(excited):
    m = synthetic_map(excited=excited)
    m.l_inc[...] = 1e-3
    m.l_inc[0, 1, :] = np.nan
    l_end = 2e-4
    c = with_end_winding(m, l_end)
    k = m.circuits.index(excited)
    i = m.currents[None, :]
    assert np.allclose(c.psi[..., k], m.psi[..., k] + l_end * i)
    others = [j for j in range(len(m.circuits)) if j != k]
    assert np.array_equal(c.psi[..., others], m.psi[..., others])
    assert np.allclose(c.coenergy, m.coenergy + 0.5 * l_end * i**2)
    assert np.allclose(c.energy, m.energy + 0.5 * l_end * i**2)
    assert np.isnan(c.l_inc[0, 1, k]) and c.l_inc[1, 1, k] == pytest.approx(1e-3 + l_end)
    assert np.array_equal(c.torque_arkkio, m.torque_arkkio)
    assert np.array_equal(m.psi[..., k], synthetic_map(excited=excited).psi[..., k])   # input untouched


def test_with_end_winding_rejects_negative():
    with pytest.raises(ValueError):
        with_end_winding(synthetic_map(), -1e-4)
