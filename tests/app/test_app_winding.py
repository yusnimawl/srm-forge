import math

import pytest
from conftest import make_12_8, make_8_6

from srmapp.requirements import Requirements
from srmapp.sizing import estimates as est
from srmapp.sizing.winding import density_windings, max_mmf, path_counts, wire_windings

P = make_8_6()
A = est.coil_side_area(P)
THICK = dict(kind="round", diameter=6.0e-3, outer_diameter=6.2e-3)    # a few turns fit: fast scans
THIN = dict(kind="round", diameter=1.0e-3, outer_diameter=1.08e-3)


def _req(**kw):
    values = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    values.update(kw)
    return Requirements(**values)


def test_series_resistance_and_copper_mass_reproduce_the_reference_winding():
    assert est.series_resistance(P, P.turns_per_pole, est.conductor_area(P)) == pytest.approx(est.phase_resistance(P))
    assert est.copper_mass(P, P.turns_per_pole, est.conductor_area(P)) == pytest.approx(est.active_mass(P).copper)
    m = est.active_mass(P)
    assert m.iron == pytest.approx(m.stator_iron + m.rotor_iron)


def test_wire_windings_fill_the_slot_with_the_most_strands():
    req = _req(wires=[THIN], phase_current_a=100.0)
    room = req.max_slot_fill * A / req.wires[0].outer_area
    ws = wire_windings(P, req, 0, 20e6)
    assert ws and {w.paths for w in ws} == {1, 2}
    for paths in (1, 2):
        turns = [w.turns for w in ws if w.paths == paths]
        assert turns == sorted(turns)
    for w in ws:
        assert w.turns * w.strands <= room * (1 + 1e-9)
        assert w.turns * (w.strands + 1) > room
        assert w.copper_area == pytest.approx(w.strands * req.wires[0].copper_area)
        assert w.current == 100.0 and w.coil_current == 100.0 / w.paths and w.wire == 0
        assert w.current_density <= 20e6 * (1 + 1e-9)
        assert w.resistance == pytest.approx(est.series_resistance(P, w.turns, w.copper_area) / w.paths**2)
        assert w.copper_mass == pytest.approx(est.copper_mass(P, w.turns, w.copper_area))


def test_wire_resistance_grows_with_turns():
    ws = wire_windings(P, _req(wires=[THIN], phase_current_a=100.0), 0, 20e6)
    for paths in (1, 2):
        r = [w.resistance for w in ws if w.paths == paths]
        assert len(r) > 1 and all(b > a for a, b in zip(r, r[1:]))


def test_peak_cap_keeps_densities_above_the_cooling_limit():
    req = _req(wires=[THICK], phase_current_a=800.0)       # one THICK strand at 800 A is about 28 A/mm²
    loose, tight = wire_windings(P, req, 0, 40e6), wire_windings(P, req, 0, 20e6)
    assert any(20e6 < w.current_density <= 40e6 * (1 + 1e-9) for w in loose)
    assert all(w.current_density <= 20e6 * (1 + 1e-9) for w in tight) and len(tight) < len(loose)


def test_path_counts_are_the_divisors_of_the_poles_per_phase():
    assert path_counts(P) == [1, 2]                  # 8/6: 2 poles per phase
    assert path_counts(make_12_8()) == [1, 2, 4]     # 12/8: 4 poles per phase


def test_parallel_paths_equal_the_series_winding_of_fewer_turns():
    ws = {(w.turns, w.paths): w for w in density_windings(P, _req(), 20e6, max_turns=40)}
    for n in (1, 7, 20):
        two, one = ws[(2 * n, 2)], ws[(n, 1)]
        assert two.resistance == pytest.approx(one.resistance)
        assert two.current == pytest.approx(one.current)
        assert two.copper_mass == pytest.approx(one.copper_mass)


def test_wire_too_thick_for_one_turn_gives_nothing():
    huge = dict(kind="round", diameter=19e-3, outer_diameter=19.9e-3)
    assert wire_windings(P, _req(wires=[huge], phase_current_a=10.0), 0, 20e6) == []


def test_current_too_high_for_any_turn_count_gives_nothing():
    assert wire_windings(P, _req(wires=[THICK], phase_current_a=1e6), 0, 20e6) == []


def test_density_windings():
    ws = density_windings(P, _req(), 20e6, max_turns=50)
    assert len(ws) == 100
    assert [w.turns for w in ws if w.paths == 1] == list(range(1, 51))
    assert [w.turns for w in ws if w.paths == 2] == list(range(1, 51))
    for w in ws:
        assert w.strands == 1 and w.wire is None
        assert w.copper_area == pytest.approx(P.fill_factor * A / w.turns)
        assert w.current_density == pytest.approx(20e6)
        assert w.current == pytest.approx(20e6 * w.copper_area * w.paths)


def test_density_current_cap():
    ws = density_windings(P, _req(phase_current_a=200.0), 20e6, max_turns=50)
    assert ws and all(w.current <= 200.0 * (1 + 1e-9) for w in ws)
    assert ws[0].turns == math.ceil(20e6 * P.fill_factor * A / 200.0 - 1e-9)


@pytest.mark.parametrize("wires", [[THIN], [THICK], [THIN, THICK]])
def test_max_mmf_covers_every_wire_winding(wires):
    req = _req(wires=wires, phase_current_a=60.0)
    top = max_mmf(P, req, 20e6, 20e6)
    for i in range(len(wires)):
        assert all(w.turns * w.coil_current <= top * (1 + 1e-9) for w in wire_windings(P, req, i, 20e6))


def test_max_mmf_is_the_largest_ampere_turns_of_the_allowed_windings():
    req = _req(wires=[THIN, THICK], phase_current_a=60.0)
    top = max(w.turns * w.coil_current for i in range(2) for w in wire_windings(P, req, i, 20e6))
    assert max_mmf(P, req, 20e6, 20e6) == top
    thin = _req(wires=[THIN], phase_current_a=60.0)
    old_bound = 20e6 * thin.max_slot_fill * A * max(w.copper_area / w.outer_area for w in thin.wires)
    assert max_mmf(P, thin, 20e6, 20e6) < old_bound


def test_max_mmf_is_zero_when_no_wire_fits():
    huge = dict(kind="round", diameter=0.019, outer_diameter=0.0195)
    assert max_mmf(P, _req(wires=[huge], phase_current_a=60.0), 20e6, 20e6) == 0.0


def test_max_mmf_density_mode():
    assert max_mmf(P, _req(), 20e6, 99e6) == pytest.approx(20e6 * P.fill_factor * A)
    assert all(w.turns * w.coil_current <= max_mmf(P, _req(), 20e6, 20e6) * (1 + 1e-9)
               for w in density_windings(P, _req(), 20e6, max_turns=50))
