import math

import pytest
from conftest import make_8_6

from srmapp.mechanical import PLACEHOLDER_NOTE, BearingSetup, mechanical_loss, rotor_weight_n
from srmapp.requirements import Requirements
from srmcore.post.bearing_friction import bearing_friction

M = make_8_6()


def test_default_bearing_is_a_placeholder():
    assert BearingSetup().placeholder
    assert not BearingSetup(radial_load_n=50.0).placeholder
    assert not BearingSetup(type="angular_contact_ball").placeholder
    r = mechanical_loss(M, BearingSetup(), 6000)
    assert PLACEHOLDER_NOTE in r.notes
    assert PLACEHOLDER_NOTE not in mechanical_loss(M, BearingSetup(bore_diameter_m=0.02, radial_load_n=30.0), 6000).notes


def test_defaults_are_shaft_diameter_and_rotor_weight():
    r = mechanical_loss(M, BearingSetup(), 6000)
    f = bearing_friction("deep_groove_ball", M.shaft_diameter, rotor_weight_n(M), 6000)
    assert r.friction_w == pytest.approx(f.power_w)
    assert 0 < rotor_weight_n(M) < 500


def test_explicit_size_and_load_are_used():
    r = mechanical_loss(M, BearingSetup(bore_diameter_m=0.02, radial_load_n=100.0, type="tapered_roller"), 3000)
    assert r.friction_w == pytest.approx(0.0021 * 100.0 * 0.02 / 2 * 3000 * 2 * math.pi / 60)


def test_unfavourable_takes_the_high_ends():
    nom, hi = mechanical_loss(M, BearingSetup(), 6000), mechanical_loss(M, BearingSetup(), 6000, True)
    assert hi.windage_w == pytest.approx(nom.windage_w * (1 + nom.windage_rel[1]))
    assert hi.friction_w == pytest.approx(nom.friction_w * (1 + nom.friction_rel[1]))
    lo, up = nom.total_rel()
    assert lo < 0 < up
    assert nom.total_w * (1 + up) == pytest.approx(hi.total_w)


def test_zero_speed_gives_zero_loss():
    r = mechanical_loss(M, BearingSetup(), 0)
    assert r.total_w == 0.0 and r.total_rel() == (0.0, 0.0)


def test_requirements_carry_the_bearing_and_default_loads():
    kw = dict(peak_power_w=1e3, peak_torque_nm=10.0, base_speed_rpm=955.0, max_speed_rpm=3000.0)
    req = Requirements(**kw)
    assert req.bearing.placeholder
    again = Requirements.model_validate_json(Requirements(**kw, bearing=BearingSetup(count=3)).model_dump_json())
    assert again.bearing.count == 3
    with pytest.raises(ValueError):
        Requirements(**kw, bearing={"type": "plain"})
