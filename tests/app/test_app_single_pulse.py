import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

from srmapp import turns
from srmapp.drive import envelope as drive
from srmapp.requirements import Requirements
from srmapp.sizing.winding import max_mmf
from srmapp.turns import choose_turns

MACHINE = make_8_6()
R = 0.1


@pytest.mark.parametrize("rpm, volts, rms", [(30.0, 400.0, None), (1500.0, 400.0, None), (9000.0, 400.0, None),
                                             (9000.0, 100.0, None), (40000.0, 100.0, None), (1500.0, 400.0, 10.0),
                                             (40000.0, 100.0, 10.0)])
def test_single_pulse_torque_is_the_torque_with_only_single_pulses(rpm, volts, rms):
    result = synthetic_map(n_angles=24)
    real = drive._strokes

    def pulses_only(*args):
        w_t, w_l, i2, valid, psi0 = real(*args)
        return w_t, w_l, i2, valid & (psi0 == 0), psi0

    full = drive.envelope(result, MACHINE, volts, R, [rpm], rms_limit=rms, waveforms=False)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(drive, "_strokes", pulses_only)
        pulse = drive.envelope(result, MACHINE, volts, R, [rpm], rms_limit=rms, waveforms=False)
    np.testing.assert_array_equal(full.torque_single_pulse, pulse.torque)
    np.testing.assert_array_equal(pulse.torque_single_pulse, pulse.torque)
    assert full.torque_single_pulse[0] <= full.torque[0]
    if (rpm, volts, rms) == (40000.0, 100.0, None):
        assert full.torque_single_pulse[0] < full.torque[0]     # continuous conduction wins here


def _equivalent(s):
    return s.winding.turns / s.winding.paths


def _scan(power_w, counts):
    """Density scan of the series windings with these turn counts at 100 V up to 40 000 r/min: on the synthetic map
    the single pulse delivers 1066 W at 40 turns and 1122.7 W at 39, against 1171.8 W and 1172.2 W with continuous
    conduction; below 39 turns the two agree."""
    req = Requirements(peak_power_w=power_w, peak_torque_nm=power_w / (1000.0 * 2 * np.pi / 60), base_speed_rpm=1000.0,
                       max_speed_rpm=40000.0,
                       bus_voltage_v=100.0)
    top = max_mmf(MACHINE, req, 20e6, 40e6) / MACHINE.turns_per_pole
    result = synthetic_map(n_angles=24, currents=np.linspace(0.0, top, 9))
    real = turns.density_windings
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(turns, "density_windings",
                   lambda *a: [w for w in real(*a) if w.paths == 1 and w.turns in counts])
        return choose_turns(result, MACHINE, req, max_turns=40)


def test_density_mode_prefers_single_pulse_windings():
    c = _scan(1100.0, (38, 39, 40))
    assert {s.winding.turns: s.single_pulse for s in c.scan} == {38: True, 39: True, 40: False}
    assert all(s.feasible for s in c.scan)
    assert c.point.winding.turns == 39      # 40 has the most turns but needs continuous conduction
    assert [s.winding.turns for s in c.ranked] == [39, 38, 40]


def test_density_mode_without_a_single_pulse_winding_keeps_the_turn_order():
    c = _scan(1130.0, (39, 40))
    assert all(s.feasible and not s.single_pulse for s in c.scan)
    assert [s.winding.turns for s in c.ranked] == [40, 39]


def test_wire_mode_ranking_ignores_single_pulse():
    from test_app_turns import THICK, THICKER, _map_for, _req
    req = _req(wires=[THICK, THICKER], phase_current_a=100.0)
    c = choose_turns(_map_for(req), MACHINE, req)
    key = lambda s: (s.winding.resistance, s.winding.turns, s.winding.paths)   # noqa: E731
    assert c.ranked == tuple(sorted((s for s in c.scan if s.feasible), key=key))
    assert c.point is c.ranked[0]
