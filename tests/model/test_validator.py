import math

import pytest

from conftest import make_8_6, make_12_8
from srmcore.model.design import Design, EdgeRefinement, MeshSettings
from srmcore.model.errors import InputError
from srmcore.model.validator import require_valid, validate_mesh_settings, validate_params


def _errors(issues):
    return {(i.parameter, i.rule) for i in issues if i.severity == "error"}


def _warnings(issues):
    return {(i.parameter, i.rule) for i in issues if i.severity == "warning"}


def test_reference_designs_are_valid(reference_design):
    assert _errors(validate_params(reference_design)) == set()


def test_millimetre_input_is_caught_as_units_error():
    p = make_8_6(stator_outer_diameter=160.0, rotor_outer_diameter=80.0, air_gap=0.4)
    errors = _errors(validate_params(p))
    assert ("stator_outer_diameter", "units") in errors
    assert ("air_gap", "units") in errors


def test_non_positive_lengths():
    errors = _errors(validate_params(make_8_6(air_gap=0.0, stack_length=-0.1)))
    assert ("air_gap", "positive") in errors
    assert ("stack_length", "positive") in errors


def test_negative_fillet_rejected():
    assert ("rotor_fillet_radius", "non_negative") in _errors(validate_params(make_8_6(rotor_fillet_radius=-1e-4)))


def test_phase_count_must_match_pole_numbers():
    assert ("n_phases", "phase_count") in _errors(validate_params(make_8_6(n_phases=3)))


def test_equal_pole_numbers_rejected():
    assert ("n_rotor_poles", "phase_count") in _errors(validate_params(make_8_6(n_rotor_poles=8)))


def test_self_starting_rule():
    p = make_8_6(stator_pole_arc=math.radians(12.0))  # min arc 12° < 360/(4*6) = 15°
    assert ("stator_pole_arc", "self_starting") in _errors(validate_params(p))


def test_self_starting_equality_is_allowed():
    assert _errors(validate_params(make_12_8())) == set()  # βs = 15° = 360/(3*8)


def test_pole_arc_sum_rule():
    p = make_8_6(stator_pole_arc=math.radians(28.0), rotor_pole_arc=math.radians(33.0))  # 61° ≥ 60°
    assert ("rotor_pole_arc", "pole_arc_sum") in _errors(validate_params(p))


def test_stator_arc_larger_than_rotor_is_only_a_warning():
    p = make_8_6(stator_pole_arc=math.radians(23.0), rotor_pole_arc=math.radians(21.0))
    issues = validate_params(p)
    assert _errors(issues) == set()
    assert ("stator_pole_arc", "arc_order") in _warnings(issues)


def test_radial_stack_rules():
    errors = _errors(validate_params(make_8_6(rotor_yoke_thickness=0.031)))  # 0.010 + 0.031 > 0.040
    assert ("rotor_yoke_thickness", "radial_stack") in errors
    errors = _errors(validate_params(make_8_6(stator_yoke_thickness=0.040)))  # 0.080 - 0.040 < 0.0404
    assert ("stator_yoke_thickness", "radial_stack") in errors


def test_fill_factor_range():
    assert ("fill_factor", "range") in _errors(validate_params(make_8_6(fill_factor=0.95)))


def test_thick_lamination_at_high_frequency_warns():
    p = make_8_6(lamination_thickness=0.00035, max_speed_rpm=15000)  # 6*15000/60 = 1.5 kHz
    assert ("lamination_thickness", "lamination_frequency") in _warnings(validate_params(p))


def test_mesh_settings_rules(srm_8_6):
    s = MeshSettings(
        airgap_radial_layers=3,
        airgap_circumferential_divisions=100,  # lcm(8, 6) = 24 does not divide 100
        region_sizes={"stator_iron": 0.002, "rotor": 0.002},
        refinement={"pole_tip": EdgeRefinement(size=0.0, growth=0.9)},
        skin_depth_layers=3,
    )
    errors = _errors(validate_mesh_settings(s, srm_8_6))
    assert ("airgap_radial_layers", "min_layers") in errors
    assert ("airgap_circumferential_divisions", "band_divisions") in errors
    assert ("region_sizes.rotor", "unknown_region") in errors
    assert ("refinement.pole_tip.size", "positive") in errors
    assert ("refinement.pole_tip.growth", "range") in errors
    assert ("skin_depth_layers", "not_implemented") in errors


def test_require_valid_raises_with_parameter_names():
    design = Design(machine=make_8_6(air_gap=-1.0))
    with pytest.raises(InputError) as info:
        require_valid(design)
    assert "air_gap" in str(info.value)


def test_require_valid_returns_warnings(srm_8_6):
    design = Design(machine=make_8_6(stator_pole_arc=math.radians(23.0), rotor_pole_arc=math.radians(21.0)))
    warnings = require_valid(design)
    assert [w.rule for w in warnings] == ["arc_order"]
