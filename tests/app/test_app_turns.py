import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

from srmapp.drive.envelope import envelope
from srmapp.requirements import Requirements
from srmapp.sizing.winding import max_mmf
from srmapp.turns import choose_turns, requirement_ratios, rescale_turns, speed_grid

MACHINE = make_8_6()
SPEEDS = np.array([100.0, 1500.0, 6000.0, 12000.0])


def test_rescale_moves_current_and_flux_and_keeps_torque_and_energy():
    r = synthetic_map(n_angles=16)
    s = rescale_turns(r, 2.0)
    np.testing.assert_allclose(s.currents, r.currents / 2)
    np.testing.assert_allclose(s.psi, 2 * r.psi)
    np.testing.assert_allclose(s.l_inc, 4 * r.l_inc)
    for name in ("torque_arkkio", "torque_virtual_work", "energy", "coenergy", "pole_force", "b_peak"):
        np.testing.assert_array_equal(getattr(s, name), getattr(r, name))
    assert s.angles is r.angles and s.complete == r.complete


def test_rescaled_drive_equals_the_original_at_scaled_voltage():
    # k times the turns: ψ' = kψ, i' = i/k, R' = k²R, so dψ/dt = V/k − R·i on the original map
    r, k, res = synthetic_map(n_angles=24), 3.0, 0.2
    scaled = envelope(rescale_turns(r, k), MACHINE, 300.0, k * k * res, SPEEDS, current_limit=20.0 / k)
    original = envelope(r, MACHINE, 300.0 / k, res, SPEEDS, current_limit=20.0)
    np.testing.assert_allclose(scaled.torque, original.torque, rtol=1e-9, atol=1e-12)
    np.testing.assert_allclose(scaled.copper_loss, original.copper_loss, rtol=1e-9, atol=1e-12)


@pytest.mark.slow
def test_fem_map_at_double_turns_matches_the_rescale():
    pytest.importorskip("ngsolve")
    from srmcore.maps import build_map
    from srmcore.model.design import Design, MeshSettings

    def run(turns, i_max):
        design = Design(machine=make_8_6(turns_per_pole=turns), mesh=MeshSettings(preset="screening"))
        return build_map(design, i_max, n_angles=6, n_currents=4, workers=2)
    base, double = run(40, 20.0), run(80, 10.0)
    predicted = rescale_turns(base, 2.0)
    np.testing.assert_allclose(double.currents, predicted.currents, rtol=1e-12)
    psi_scale = np.max(np.abs(double.psi))
    np.testing.assert_allclose(double.psi, predicted.psi, rtol=1e-6, atol=1e-7 * psi_scale)
    t_scale = np.max(np.abs(double.torque_arkkio))
    np.testing.assert_allclose(double.torque_arkkio, predicted.torque_arkkio, rtol=1e-6, atol=1e-7 * t_scale)


THICK = dict(kind="round", diameter=6.0e-3, outer_diameter=6.2e-3)
THICKER = dict(kind="rectangular", width=7.0e-3, height=4.0e-3, insulation=0.1e-3)


def _req(**kw):
    values = dict(peak_power_w=10.47, peak_torque_nm=0.1, base_speed_rpm=1000.0, max_speed_rpm=2000.0)
    values.update(kw)
    return Requirements(**values)


def _map_for(req, j_peak=20e6, j_peak_max=40e6):
    top = max_mmf(MACHINE, req, j_peak, j_peak_max) / MACHINE.turns_per_pole
    return synthetic_map(n_angles=24, currents=np.linspace(0.0, top, 9))


def test_wire_mode_picks_the_lowest_resistance_feasible_winding():
    req = _req(wires=[THICK, THICKER], phase_current_a=100.0)
    c = choose_turns(_map_for(req), MACHINE, req)
    assert c.point is not None and c.feasible and c.point.feasible
    feasible = [s for s in c.scan if s.feasible]
    assert c.point.winding.resistance == min(s.winding.resistance for s in feasible)
    same = [s.winding.turns for s in feasible
            if (s.winding.wire, s.winding.paths) == (c.point.winding.wire, c.point.winding.paths)]
    assert c.point.winding.turns == min(same)
    assert {s.winding.wire for s in c.scan} == {0, 1}


def _equivalent(s):
    return s.winding.turns / s.winding.paths


def test_density_mode_picks_the_most_equivalent_turns_then_the_fewest_paths():
    req = _req()
    c = choose_turns(_map_for(req), MACHINE, req, max_turns=40)
    assert c.feasible and len(c.scan) == 80          # 40 turn counts x paths 1 and 2
    feasible = [s for s in c.scan if s.feasible]
    assert _equivalent(c.point) == max(_equivalent(s) for s in feasible)
    assert c.point.winding.paths == min(s.winding.paths for s in feasible if _equivalent(s) == _equivalent(c.point))


def test_density_mode_prefers_the_series_winding_over_the_same_machine_on_two_paths():
    # worst ratio 112.6147 on this map is met up to 17 equivalent turns, so the 34 turns on 2 paths are as feasible
    # as the 17 in series; ranking by raw turns would pick them.
    req = _req()
    c = choose_turns(_map_for(req), MACHINE, req, max_turns=40, margin=112.6147)
    parallel = next(s for s in c.scan if (s.winding.turns, s.winding.paths) == (34, 2))
    assert parallel.feasible
    assert (c.point.winding.turns, c.point.winding.paths) == (17, 1)


def test_density_current_cap_limits_the_scan():
    req = _req(phase_current_a=200.0)
    c = choose_turns(_map_for(req), MACHINE, req, max_turns=40)
    assert c.scan and all(s.winding.current <= 200.0 * (1 + 1e-9) for s in c.scan)


def test_infeasible_requirement_reports_the_closest_winding():
    req = _req(peak_torque_nm=1e4, peak_power_w=1.047e6)
    c = choose_turns(_map_for(req), MACHINE, req, max_turns=20)
    assert not c.feasible and c.point is not None and not c.point.feasible
    assert c.point.worst == max(s.worst for s in c.scan)


def test_no_winding_when_nothing_fits():
    req = _req(wires=[THICK], phase_current_a=1e6)
    c = choose_turns(synthetic_map(n_angles=24), MACHINE, req)
    assert c.point is None and not c.feasible and c.envelope is None and c.scan == ()


def test_chosen_envelope_covers_the_full_speed_grid_and_matches_the_scan_ratios():
    req = _req(wires=[THICK], phase_current_a=100.0)
    c = choose_turns(_map_for(req), MACHINE, req)
    np.testing.assert_array_equal(c.envelope.speeds_rpm, speed_grid(req))
    assert requirement_ratios(c.envelope, req) == pytest.approx((c.point.torque_ratio, c.point.power_ratio))


def test_two_paths_scan_like_the_series_winding_of_half_the_turns():
    req = _req()
    c = choose_turns(_map_for(req), MACHINE, req, max_turns=40)
    by = {(s.winding.turns, s.winding.paths): s for s in c.scan}
    for n in (1, 7, 20):          # 2n turns on 2 paths act as n turns in series
        two, one = by[(2 * n, 2)], by[(n, 1)]
        assert (two.torque_ratio, two.power_ratio) == pytest.approx((one.torque_ratio, one.power_ratio), rel=1e-9)
        assert two.i_rms == pytest.approx(one.i_rms, rel=1e-9)
        assert two.j_rms == pytest.approx(one.j_rms, rel=1e-9)


def test_margin_sets_feasibility():
    req = _req()
    base = choose_turns(_map_for(req), MACHINE, req, max_turns=20, margin=1.0)
    assert all(s.feasible == (s.worst >= 1.0) for s in base.scan)
    bar = base.point.worst * 1.001
    strict = choose_turns(_map_for(req), MACHINE, req, max_turns=20, margin=bar)
    assert all(s.feasible == (s.worst >= bar) for s in strict.scan)
    assert not any(s.feasible for s in strict.scan if s.winding == base.point.winding)


def test_rms_limit_binds_the_scan():
    req = _req(wires=[THICK], phase_current_a=100.0)
    m = _map_for(req, j_peak_max=40e6)
    loose = choose_turns(m, MACHINE, req, j_limit=1e9, j_peak_max=40e6)
    limit = 0.5 * float(np.median([s.j_rms for s in loose.scan]))
    tight = choose_turns(m, MACHINE, req, j_limit=limit, j_peak_max=40e6)
    assert [s.winding for s in tight.scan] == [s.winding for s in loose.scan]
    assert all(s.j_rms <= limit * (1 + 1e-9) for s in tight.scan)
    assert any(t.torque_ratio < l.torque_ratio for t, l in zip(tight.scan, loose.scan))


def test_capped_flag_reports_windings_left_out_by_the_peak_cap():
    req = _req(wires=[THICK], phase_current_a=800.0)       # one THICK strand at 800 A is about 28 A/mm²
    assert choose_turns(_map_for(req, j_peak_max=20e6), MACHINE, req, j_peak_max=20e6).capped
    assert not choose_turns(_map_for(req, j_peak_max=1e12), MACHINE, req, j_peak_max=1e12).capped
