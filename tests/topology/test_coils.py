import math

import pytest

from conftest import make_8_6
from srmcore.model.errors import InputError
from srmcore.topology.primitives import sample_segment
from srmcore.topology.radial import build_outline


def _pts(coil):
    return [q for s in coil.boundary for q in sample_segment(s, 1e-4)]


def test_coil_count_names_and_signs(srm_8_6):
    coils = build_outline(srm_8_6).coil_sides
    assert len(coils) == 16
    assert len({c.name for c in coils}) == 16
    by_name = {c.name: c for c in coils}
    upper0 = [c for c in coils if c.pole == 0 and c.sign == +1][0]
    assert upper0.name == "coil_A1+"
    assert by_name["coil_A2-"].pole == 4 and by_name["coil_A2+"].pole == 4
    assert {c.phase for c in coils} == {0, 1, 2, 3}


def test_coil_boundaries_closed(reference_design):
    for c in build_outline(reference_design).coil_sides:
        segs = list(c.boundary)
        assert len(segs) == 4
        assert all(math.dist(a.end, b.start) < 1e-12 for a, b in zip(segs, segs[1:] + segs[:1]))


def test_coil_stays_inside_its_half_slot(srm_8_6):
    p = srm_8_6
    o = build_outline(p)
    upper0 = [c for c in o.coil_sides if c.pole == 0 and c.sign == +1][0]
    r_in = p.bore_radius + p.coil_inner_clearance
    r_out = p.stator_yoke_inner_radius - 2 * p.stator_fillet_radius - p.slot_liner_thickness
    half = p.stator_pole_arc / 2
    face_end = (p.bore_radius * math.cos(half), p.bore_radius * math.sin(half))
    tau = p.stator_pole_taper
    n = (-math.sin(tau), math.cos(tau))
    clearances = []
    for x, y in _pts(upper0):
        assert r_in - 1e-12 <= math.hypot(x, y) <= r_out + 1e-12
        assert math.atan2(y, x) < math.pi / p.n_stator_poles
        clearance = (x - face_end[0]) * n[0] + (y - face_end[1]) * n[1]
        assert clearance >= p.slot_liner_thickness - 1e-12
        clearances.append(clearance)
    assert min(clearances) == pytest.approx(p.slot_liner_thickness, rel=1e-6)


def test_coils_sharing_a_slot_are_one_liner_apart(srm_8_6):
    o = build_outline(srm_8_6)
    a = [c for c in o.coil_sides if c.pole == 0 and c.sign == +1][0]   # upper side of pole 0
    b = [c for c in o.coil_sides if c.pole == 1 and c.sign == -1][0]   # lower side of pole 1
    gap = min(math.dist(p, q) for p in _pts(a) for q in _pts(b))
    assert gap == pytest.approx(srm_8_6.slot_liner_thickness, rel=0.05)


def test_clearance_too_large_is_input_error():
    with pytest.raises(InputError) as info:
        build_outline(make_8_6(coil_inner_clearance=0.03))
    assert any(i.parameter == "coil_inner_clearance" and i.rule == "coil_fit" for i in info.value.issues)


def test_liner_too_thick_is_input_error():
    with pytest.raises(InputError) as info:
        build_outline(make_8_6(slot_liner_thickness=0.01))
    assert any(i.parameter == "slot_liner_thickness" and i.rule == "coil_fit" for i in info.value.issues)
