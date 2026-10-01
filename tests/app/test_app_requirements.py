import math

import pytest
from pydantic import ValidationError

from srmapp.requirements import Requirements
from srmapp.wire import RoundWire


def _ok(**kw):
    # 30 kW at 3000 rpm base: torque = 30000 / (3000 * 2π/60) = 95.49 N·m
    values = dict(peak_power_w=30_000.0, peak_torque_nm=95.5, base_speed_rpm=3000.0, max_speed_rpm=9000.0)
    values.update(kw)
    return Requirements(**values)


def test_defaults():
    r = _ok()
    assert r.bus_voltage_v == 400.0
    assert r.max_outer_diameter_m is None and r.max_mass_kg is None


def test_frozen():
    with pytest.raises(ValidationError):
        _ok().bus_voltage_v = 48.0


@pytest.mark.parametrize("field", ["peak_power_w", "peak_torque_nm", "base_speed_rpm", "max_speed_rpm",
                                   "bus_voltage_v"])
def test_positive_fields(field):
    with pytest.raises(ValidationError):
        _ok(**{field: 0.0})


def test_max_speed_not_below_base():
    with pytest.raises(ValidationError, match="max_speed_rpm"):
        _ok(max_speed_rpm=2000.0)


def test_power_torque_speed_must_agree():
    # 30 kW needs 95.5 N·m at 3000 rpm; 50 N·m is off by far more than 10 %
    with pytest.raises(ValidationError, match="power"):
        _ok(peak_torque_nm=50.0)


def test_millimetre_looking_outer_diameter_is_rejected():
    with pytest.raises(ValidationError, match="metres"):
        _ok(max_outer_diameter_m=160.0)
    assert _ok(max_outer_diameter_m=0.16).max_outer_diameter_m == 0.16


def test_no_extra_fields():
    with pytest.raises(ValidationError):
        _ok(colour="red")


_WIRE = dict(kind="round", diameter=1.0e-3, outer_diameter=1.08e-3)


def test_density_mode_by_default():
    r = _ok()
    assert r.wires == () and not r.wire_mode
    assert r.phase_current_a is None and r.max_slot_fill == 0.6


def test_wire_mode_needs_a_phase_current():
    with pytest.raises(ValidationError, match="phase_current_a"):
        _ok(wires=[_WIRE])
    r = _ok(wires=[_WIRE], phase_current_a=150.0)
    assert r.wire_mode and isinstance(r.wires[0], RoundWire)


def test_density_mode_accepts_a_current_cap():
    assert _ok(phase_current_a=200.0).phase_current_a == 200.0


@pytest.mark.parametrize("fill", [0.0, 0.95])
def test_slot_fill_range(fill):
    with pytest.raises(ValidationError):
        _ok(max_slot_fill=fill)
