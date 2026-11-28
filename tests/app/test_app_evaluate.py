import dataclasses
import math
from unittest import mock

import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import inductance, synthetic_map

from srmapp.drive.envelope import Envelope
from srmapp.evaluate import Evaluation, StageTwoGrid, evaluate_stage2, requirement_ratios, rescale_turns, speed_grid, turns_scale
from srmapp.requirements import Requirements
from srmapp.sizing import estimates as est
from srmapp.sizing.generator import Candidate
from srmapp.sizing.stage1 import stage1
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import InputError, MapFailed, MeshRejected, WorkerCrashed

THICK = dict(kind="round", diameter=6.0e-3, outer_diameter=6.2e-3)


def _req(**kw):
    values = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    values.update(kw)
    return Requirements(**values)


def _cand():
    return Candidate("c0", Design(machine=make_8_6(), mesh=MeshSettings(preset="screening")))


def _map(stage):
    return synthetic_map(n_angles=24, currents=np.linspace(0.0, stage.i_map, 9))


def _evaluate(req, **kw):
    stage = stage1(req, make_8_6())
    with mock.patch("srmapp.evaluate.build_map", return_value=_map(stage)):
        return evaluate_stage2(_cand(), req, stage, max_turns=30, **{"thermal": False, **kw}), stage


def test_speed_grid_contains_base_and_max_exactly():
    g = speed_grid(_req())
    assert 3000.0 in g and 6000.0 in g
    assert np.all(np.diff(g) > 0) and g[0] < 3000.0


def test_requirement_ratios():
    speeds = np.array([300.0, 3000.0, 4500.0, 6000.0])
    torque = np.array([10.0, 4.0, 2.0, 1.0])
    power = torque * speeds * 2 * math.pi / 60
    env = Envelope(speeds, torque, power, np.zeros(4), np.zeros(4), np.ones(4), np.zeros(4), np.zeros(4), np.zeros(4),
                   None, np.zeros(4), np.zeros(4), np.zeros(4))
    t_ratio, p_ratio = requirement_ratios(env, _req())
    assert t_ratio == pytest.approx(4.0 / 3.2)
    assert p_ratio == pytest.approx(min(power[1:]) / 1000.0)


def test_stage_two_grid_defaults_to_the_preset():
    assert StageTwoGrid() == StageTwoGrid(None, None)


def test_failed_map_becomes_an_evaluation_and_does_not_raise():
    with mock.patch("srmapp.evaluate.build_map", side_effect=MapFailed(["3 of 50 points failed"], 3)):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()), thermal=False)
    assert isinstance(e, Evaluation)
    assert e.status == "MapFailed" and "3 of 50" in e.error
    assert not e.feasible and math.isnan(e.torque_ratio) and e.envelope is None and e.winding is None
    assert math.isnan(e.i_rms_a) and math.isnan(e.j_rms)


def test_cancelled_map_is_reported():
    partial = synthetic_map(complete=False)
    with mock.patch("srmapp.evaluate.build_map", return_value=partial):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()), thermal=False)
    assert e.status == "cancelled" and not e.feasible


def test_map_is_built_over_the_stage_one_range():
    stage = stage1(_req(), make_8_6())
    with mock.patch("srmapp.evaluate.build_map", return_value=_map(stage)) as bm:
        evaluate_stage2(_cand(), _req(), stage, max_turns=5, thermal=False)
    assert bm.call_args.args[1] == stage.i_map


def test_stage_two_scans_within_the_stage_one_cap_by_default():
    req = _req(wires=[THICK], phase_current_a=100.0)
    stage = stage1(req, make_8_6(), j_peak_max=40e6)
    assert stage.j_peak_max == 40e6
    with mock.patch("srmapp.evaluate.build_map", return_value=_map(stage)):
        e = evaluate_stage2(_cand(), req, stage, j_limit=25e6, thermal=False)     # an uncapped scan would go beyond 40 A/mm2
    assert e.scan and all(s.winding.current_density <= 40e6 * (1 + 1e-9) for s in e.scan)


def test_scan_limit_note_follows_the_equivalent_turns():
    e, _ = _evaluate(_req())
    assert e.winding.turns == 30 and e.winding.paths == 1 and "limit" in e.error
    ratio = {(s.winding.turns, s.winding.paths): min(s.torque_ratio, s.power_ratio) for s in e.scan}
    margin = 0.5 * (ratio[21, 1] + ratio[22, 1])      # feasible up to 21 turns in series; 30 turns on 2 paths is only 15
    assert ratio[22, 1] < margin < ratio[21, 1] and ratio[30, 1] < margin
    e, _ = _evaluate(_req(), margin=margin)
    assert next(s for s in e.scan if (s.winding.turns, s.winding.paths) == (30, 2)).feasible
    assert (e.winding.turns, e.winding.paths) == (21, 1) and "limit" not in e.error


def test_no_winding_reasons_name_the_cap_in_wire_mode():
    req = _req(wires=[dict(kind="round", diameter=1e-3, outer_diameter=1.08e-3)], phase_current_a=1e6)
    s = stage1(req, make_8_6(), j_peak_max=40e6)
    assert not s.passes and "no winding" in s.reason and "j_peak_max 40 A/mm2" in s.reason


def _with_current(rows):
    """Wrap the envelope so the phase current is `rows(current)`: pins which speeds count as continuous."""
    from srmapp import turns
    real = turns._envelope

    def wrapped(*a, **k):
        env = real(*a, **k)
        w = dataclasses.replace(env.waveforms, current=rows(env.waveforms.current))
        return dataclasses.replace(env, waveforms=w)
    return mock.patch.multiple("srmapp.turns", _envelope=wrapped)


def test_continuous_speed_carries_the_coupling_note():
    def last_continuous(c):
        c = np.zeros_like(c)
        c[-1] = 1.0
        return c
    with _with_current(last_continuous):
        e, _ = _evaluate(_req())
    assert "continuous conduction at 6000 r/min" in e.error and "no mutual coupling" in e.error


def test_single_pulse_evaluation_has_no_coupling_note():
    with _with_current(np.zeros_like):
        e, _ = _evaluate(_req())
    assert "continuous conduction" not in e.error


@pytest.mark.parametrize("device_peak, binds", [(110.0, True), (1000.0, False)])
def test_ripple_note_only_where_the_ripple_lowers_the_current(device_peak, binds):
    req = _req(phase_current_a=device_peak, switching_frequency_hz=20e3)
    stage = stage1(req, make_8_6())
    r = _map(stage)
    l_inc = np.full(r.l_inc.shape, np.nan)
    l_inc[..., r.circuits.index(r.excited)] = inductance(r.angles)[:, None] + 0 * r.currents[None, :]
    with mock.patch("srmapp.evaluate.build_map", return_value=dataclasses.replace(r, l_inc=l_inc)):
        e = evaluate_stage2(_cand(), req, stage, max_turns=30, thermal=False)
    own = est.J_PEAK * e.winding.copper_area * e.winding.paths
    assert (e.winding.current < own) == binds
    assert (f"current limit {e.winding.current:.1f} A: the {device_peak:.0f} A device peak less half the" in e.error) == binds


def test_density_mode_evaluation_fills_the_metrics():
    e, stage = _evaluate(_req())
    assert e.status == "ok" and e.winding is not None and e.winding.wire is None
    m = e.design.machine
    assert m.turns_per_pole == e.winding.turns
    assert est.phase_resistance(m, 120.0) == pytest.approx(e.winding.resistance * e.winding.paths**2)
    assert e.mass_kg == pytest.approx(stage.mass.iron + e.winding.copper_mass)
    assert len(e.scan) == 60          # 30 turn counts x paths 1 and 2
    assert e.peak_power_w > 0
    assert e.power_density_kw_per_kg == pytest.approx(e.peak_power_w / 1000 / e.mass_kg)
    assert 0 < e.efficiency_base <= 1
    assert e.feasible == (e.torque_ratio >= 1 and e.power_ratio >= 1)


def test_wire_mode_evaluation_uses_the_inverter_current():
    req = _req(wires=[THICK], phase_current_a=100.0)
    e, _ = _evaluate(req)
    assert e.status == "ok" and e.winding.wire == 0
    assert e.winding.current == 100.0 and e.winding.strands >= 1
    assert e.winding.current_density <= 40e6 * (1 + 1e-9)
    assert 0 < e.i_rms_a and e.j_rms <= 20e6 * (1 + 1e-9)
    assert e.j_rms == pytest.approx(e.i_rms_a / (e.winding.paths * e.winding.copper_area))
    assert est.phase_resistance(e.design.machine, 120.0) == pytest.approx(e.winding.resistance * e.winding.paths**2)


def test_margin_reaches_the_turns_choice():
    e, _ = _evaluate(_req(), margin=1e6)
    assert e.status == "ok" and not e.feasible


def test_capped_infeasible_result_carries_a_note():
    req = _req(wires=[THICK], phase_current_a=800.0, peak_torque_nm=1e3, peak_power_w=314_159.0)
    e, _ = _evaluate(req, j_limit=10e6, j_peak_max=20e6)          # cap 20 A/mm² leaves out the one-strand windings
    assert e.status == "ok" and not e.feasible
    assert "j_peak_max" in e.error


def test_no_winding_is_reported_not_raised():
    e, _ = _evaluate(_req(wires=[THICK], phase_current_a=100.0), j_peak_max=1.0)    # stricter than the stage-1 range
    assert e.status == "no_winding" and not e.feasible and e.winding is None and e.envelope is None


def test_mass_over_the_limit_after_the_winding_is_chosen_is_infeasible():
    req = _req(wires=[THICK], phase_current_a=100.0)
    free, _ = _evaluate(req)
    iron = stage1(req, make_8_6()).mass.iron
    limit = iron + 0.5 * free.winding.copper_mass
    e, stage = _evaluate(_req(wires=[THICK], phase_current_a=100.0, max_mass_kg=limit))
    assert stage.passes and e.status == "ok" and not e.feasible
    assert "mass" in e.error and f"{limit:.2f} kg limit" in e.error
    assert "not thermally rated" in free.error and "rotor stress not checked" in free.error


@pytest.mark.slow
def test_real_8_6_evaluation():
    pytest.importorskip("ngsolve")
    req = _req(peak_power_w=2000.0, peak_torque_nm=6.4, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    stage = stage1(req, make_8_6())
    e = evaluate_stage2(_cand(), req, stage, grid=StageTwoGrid(8, 4), workers=4, max_turns=120, thermal=False)
    assert e.status == "ok", e.error
    assert 1.0 < e.envelope.torque[0] < stage.torque_upper
    assert e.key is not None and e.key.peak_torque > 0


@pytest.mark.parametrize("exc", [MeshRejected(["min angle"], None), InputError([]), WorkerCrashed([3]),
                                 RuntimeError("boom"), ValueError("bad current")])
def test_any_exception_from_build_map_becomes_a_failed_evaluation(exc):
    with mock.patch("srmapp.evaluate.build_map", side_effect=exc):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()), thermal=False)
    assert e.status == type(exc).__name__ and not e.feasible
    assert math.isnan(e.torque_ratio) and e.envelope is None


def test_keyboard_interrupt_is_not_swallowed():
    with mock.patch("srmapp.evaluate.build_map", side_effect=KeyboardInterrupt), pytest.raises(KeyboardInterrupt):
        evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()), thermal=False)


def test_turns_are_chosen_on_the_end_winding_corrected_map():
    from srmapp import evaluate as ev
    from srmcore.maps.end_winding import end_winding_inductance
    req = _req()
    stage = stage1(req, make_8_6())
    raw = _map(stage)
    seen = []
    real = ev.choose_turns

    def spy(result, *a, **kw):
        seen.append(result)
        return real(result, *a, **kw)
    with mock.patch("srmapp.evaluate.build_map", return_value=raw), \
            mock.patch("srmapp.evaluate.choose_turns", side_effect=spy):
        evaluate_stage2(_cand(), req, stage, max_turns=30, thermal=False)
    l_end = end_winding_inductance(make_8_6(), image_factor=1.5)
    k = raw.circuits.index(raw.excited)
    assert l_end > 0
    np.testing.assert_allclose(seen[0].psi[..., k], raw.psi[..., k] + l_end * raw.currents[None, :])


def test_evaluation_carries_the_rescaled_map():
    from srmcore.maps.end_winding import end_winding_inductance, with_end_winding
    req = _req()
    stage = stage1(req, make_8_6())
    raw = _map(stage)
    with mock.patch("srmapp.evaluate.build_map", return_value=raw):
        e = evaluate_stage2(_cand(), req, stage, max_turns=30, thermal=False)
    assert e.status == "ok"
    expected = rescale_turns(with_end_winding(raw, end_winding_inductance(make_8_6(), image_factor=1.5)),
                             turns_scale(make_8_6(), e.winding))
    k = expected.circuits.index(expected.excited)
    np.testing.assert_allclose(e.map.psi, expected.psi[..., k])
    np.testing.assert_allclose(e.map.currents, expected.currents)
    np.testing.assert_allclose(e.map.angles, expected.angles)
    np.testing.assert_allclose(e.map.torque, expected.torque_arkkio)


def test_failed_evaluation_has_no_map():
    with mock.patch("srmapp.evaluate.build_map", side_effect=RuntimeError("boom")):
        e = evaluate_stage2(_cand(), _req(), stage1(_req(), make_8_6()), thermal=False)
    assert e.map is None


def _ranked_eval(monkeypatch, holds, ctx_error=None, cancel=None, n_ranked=3, error_at=None, rate_error=None,
                 ratios=None, seen=None, nominal=False):
    """Stage 2 with thermal mocked: `holds` gives check_requirement's answer per winding in order (a failing check
    fails at 3000 rpm on the hot spot). `n_ranked` windings are EM-feasible (0: none is); `error_at` = (k, exc)
    raises exc from the k-th check, `ctx_error` = (k, exc) from the k-th thermal_context call; `ratios` sets the
    torque and power ratio of each ranked winding and `seen` receives the ranked points; `nominal` is whether the
    nominal-set check (rows=frozenset()) holds."""
    import srmapp.thermal as th
    from srmapp.turns import TurnsChoice, choose_turns
    req = _req()
    stage = stage1(req, make_8_6())
    result = _map(stage)
    real = choose_turns

    def choose(*a, **k):
        c = real(*a, **k)
        assert len(c.scan) >= n_ranked
        ranked = c.scan[:n_ranked] if ratios is None else [dataclasses.replace(p, torque_ratio=r, power_ratio=r)
                                                            for p, r in zip(c.scan, ratios)]
        if seen is not None:
            seen.extend(ranked)
        return TurnsChoice(c.scan[0], n_ranked > 0, c.envelope, c.scan, c.capped, tuple(ranked))

    answers = iter(holds)
    rated = mock.Mock(return_value="RATING", side_effect=rate_error)
    checks = []

    def check(ctx, n, rows=None):
        if rows is not None:   # the nominal-set check
            return th.RequirementCheck(nominal, None if nominal else 3000.0, (), (), (), "" if nominal else th.HOT_SPOT_ABOVE)
        checks.append(ctx)
        if error_at is not None and len(checks) == error_at[0]:
            raise error_at[1]
        ok = next(answers)
        return th.RequirementCheck(ok, None if ok else 3000.0, (), (), (), "" if ok else th.HOT_SPOT_ABOVE)

    contexts = []

    def context(req_, ref, res, w, **kw):
        contexts.append(w)
        if ctx_error is not None and len(contexts) == ctx_error[0]:
            raise ctx_error[1]
        return w
    monkeypatch.setattr(th, "thermal_context", context)
    monkeypatch.setattr(th, "check_requirement", check)
    monkeypatch.setattr(th, "rate_context", rated)
    # a rating the evaluation can read
    monkeypatch.setattr("srmapp.evaluate._rated_kw_per_kg", lambda *a: 1.0)
    with mock.patch("srmapp.evaluate.build_map", return_value=result), mock.patch("srmapp.evaluate.choose_turns", choose):
        e = evaluate_stage2(_cand(), req, stage, max_turns=30, cancel=None if cancel is None else (lambda: cancel(checks)))
    return e, rated, checks


def test_unrated_evaluation_says_so():
    e, _ = _evaluate(_req(), thermal=False)
    assert e.rating is None and "not thermally rated" in e.error
    import srmcore
    assert e.srmcore_version == srmcore.__version__


def test_first_holding_winding_is_chosen(monkeypatch):
    e, rated, checks = _ranked_eval(monkeypatch, [False, True])
    assert e.status == "ok" and e.rating == "RATING" and e.winding is checks[1]
    assert rated.call_count == 1 and len(checks) == 2


def test_no_winding_holds(monkeypatch):
    e, rated, checks = _ranked_eval(monkeypatch, [False, False, False])
    assert e.rating is None and not e.feasible and e.winding is checks[0]
    assert "no winding holds the rated hot-spot limit" in e.error and not rated.called
    assert "3000 rpm" in e.error and "hot spot above the limit" in e.error and "EM-feasible windings" not in e.error


def test_thermal_checks_stop_at_the_cap(monkeypatch):
    from srmapp.evaluate import MAX_THERMAL_CHECKS
    e, rated, checks = _ranked_eval(monkeypatch, [False] * 10, n_ranked=10)
    assert MAX_THERMAL_CHECKS == 4 and len(checks) == 4
    assert not e.feasible and e.rating is None and not rated.called and e.winding is checks[0]
    assert "4 of 10" in e.error and "3000 rpm" in e.error


def test_windings_below_the_rated_torque_factor_are_checked_last(monkeypatch):
    # the rated set asks for 1 + TORQUE_FLOOR times the required torque: below that ratio a winding cannot hold
    ratios, ranked = [1.06, 1.02, 1.12, 1.099, 1.15], []
    e, _, checks = _ranked_eval(monkeypatch, [False] * 4, n_ranked=len(ratios), ratios=ratios, seen=ranked)
    assert checks == [ranked[k].winding for k in (2, 4, 0, 1)]   # best-first inside each group
    assert not e.feasible and e.winding is checks[0]   # the reported winding is the one the note describes


@pytest.mark.parametrize("at", [1, 2])
def test_runaway_in_a_check_is_a_failed_evaluation(monkeypatch, at):
    from srmcore.thermal.model import ThermalRunaway
    e, _, _ = _ranked_eval(monkeypatch, [False, False, False], error_at=(at, ThermalRunaway("runaway")))
    assert e.status == "ThermalRunaway" and not e.feasible and e.rating is None


def test_runaway_in_the_rating_is_a_failed_evaluation(monkeypatch):
    from srmcore.thermal.model import ThermalRunaway
    e, _, _ = _ranked_eval(monkeypatch, [True], rate_error=ThermalRunaway("runaway"))
    assert e.status == "ThermalRunaway" and not e.feasible


def test_model_error_in_a_later_context_is_a_failed_evaluation(monkeypatch):
    from srmcore.thermal.model import ThermalModelError
    e, _, checks = _ranked_eval(monkeypatch, [False, False, False], ctx_error=(2, ThermalModelError("no path")))
    assert e.status == "ThermalModelError" and not e.feasible and len(checks) == 1


def test_no_em_feasible_winding_is_not_rated(monkeypatch):
    e, rated, checks = _ranked_eval(monkeypatch, [], n_ranked=0)
    assert e.status == "ok" and not e.feasible and e.rating is None and checks == [] and not rated.called
    assert "no winding is EM-feasible" in e.error and "not thermally rated" in e.error


def test_refusal_is_infeasible(monkeypatch):
    from srmcore.materials.loss import MissingLossData
    e, rated, _ = _ranked_eval(monkeypatch, [], ctx_error=(1, MissingLossData("no loss table")))
    assert e.status == "ok" and e.rating is None and not e.feasible
    assert "no loss table" in e.error and "not thermally rated" in e.error


def test_cooling_refusal_is_infeasible(monkeypatch):
    from srmapp.cooling import MissingCoolingData
    e, rated, _ = _ranked_eval(monkeypatch, [], ctx_error=(1, MissingCoolingData("no oil data")))
    assert e.status == "ok" and e.rating is None and not e.feasible and e.nominal_check is None
    assert "no oil data" in e.error and "not thermally rated" in e.error


@pytest.mark.parametrize("nominal", [True, False])
def test_failing_winding_gets_a_nominal_check(monkeypatch, nominal):
    e, _, _ = _ranked_eval(monkeypatch, [False, False, False], nominal=nominal)
    assert e.nominal_check is not None and e.nominal_check.holds is nominal and not e.feasible


def test_holding_winding_has_no_nominal_check(monkeypatch):
    e, _, _ = _ranked_eval(monkeypatch, [True])
    assert e.nominal_check is None


def test_rated_kw_per_kg_reads_the_chosen_set():
    from srmapp.evaluate import _rated_kw_per_kg
    from srmapp.thermal import Rating, SpeedRating
    from srmcore.thermal.solve import HotSpot
    hs = HotSpot(100.0, "coil")

    def at(cont):
        return SpeedRating(3000.0, 2 * cont, cont, 2 * cont, hs, hs, 80.0, 90.0, 70.0, 75.0, 3, 10)
    rating = Rating((at(2.0),), (at(1.0),), (), 180.0, "H", None, None, {}, 1.1, 5, (), "0")
    w = 2 * math.pi / 60
    assert _rated_kw_per_kg(rating, _req(), "continuous_nm", 1.0, "nominal") == pytest.approx(2.0 * 3000 * w / 1000)
    assert _rated_kw_per_kg(rating, _req(), "continuous_nm", 1.0) == pytest.approx(1.0 * 3000 * w / 1000)


def test_cancel_during_checks(monkeypatch):
    e, _, checks = _ranked_eval(monkeypatch, [False, False, False], cancel=lambda checks: len(checks) >= 1)
    assert e.status == "cancelled" and len(checks) == 1


@pytest.mark.parametrize("exc", [MapFailed(["1 of 60 strokes failed"], 1), WorkerCrashed([3])])
def test_failed_stroke_solve_is_an_evaluation_not_a_raise(monkeypatch, exc):
    import srmapp.thermal as th

    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(th, "thermal_context", lambda *a, **k: None)
    monkeypatch.setattr(th, "check_requirement", boom)
    stage = stage1(_req(), make_8_6())
    with mock.patch("srmapp.evaluate.build_map", return_value=_map(stage)):
        e = evaluate_stage2(_cand(), _req(), stage, max_turns=30)
    assert isinstance(e, Evaluation) and e.status == type(exc).__name__ and not e.feasible


def test_rated_kw_per_kg_is_the_lowest_rated_power_from_base_speed_over_mass():
    from srmapp.evaluate import _rated_kw_per_kg
    from srmapp.thermal import Rating, SpeedRating
    from srmcore.thermal.solve import HotSpot
    hs = HotSpot(100.0, "coil")

    def at(rpm, cont, peak):
        return SpeedRating(rpm, 2 * peak, cont, peak, hs, hs, 80.0, 90.0, 70.0, 75.0, 3, 10)
    rated = (at(1500.0, 1.0, 9.0), at(3000.0, 2.0, 4.0), at(4500.0, 1.2, 3.5), at(6000.0, 1.0, 2.5))
    rating = Rating((), rated, (), 180.0, "H", None, None, {}, 1.1, 5, (), "0")
    req, mass = _req(), 2.0
    w = 2 * math.pi / 60
    assert _rated_kw_per_kg(rating, req, "continuous_nm", mass) == pytest.approx(min(2.0 * 3000, 1.2 * 4500, 6000) * w / 1000 / mass)
    assert _rated_kw_per_kg(rating, req, "peak_nm", mass) == pytest.approx(min(4.0 * 3000, 3.5 * 4500, 2.5 * 6000) * w / 1000 / mass)
    assert math.isnan(_rated_kw_per_kg(None, req, "peak_nm", mass))


def test_screen_capped_infeasible_result_says_screen():
    # A thick wire at a high current keeps the scan small: the screen keeps 9 of the 12 windings that fit.
    req = _req(wires=[dict(kind="round", diameter=6.0e-3, outer_diameter=6.2e-3)], phase_current_a=2500.0)
    e, stage = _evaluate(req, margin=1e6)
    assert stage.j_peak_max == est.J_PEAK_SCREEN
    assert e.status == "ok" and not e.feasible
    assert "peak screen 80 A/mm2" in e.error and "j_peak_max" in e.error
    assert all(s.winding.current_density <= est.J_PEAK_SCREEN * (1 + 1e-9) for s in e.scan)


def _failing_stage2(monkeypatch, rate_failed):
    import srmapp.thermal as th
    from srmapp.turns import TurnsChoice, choose_turns
    req = _req()
    stage = stage1(req, make_8_6())
    real = choose_turns

    def choose(*a, **k):
        c = real(*a, **k)
        return TurnsChoice(c.scan[0], True, c.envelope, c.scan, c.capped, tuple(c.scan[:2]))
    fields = []

    def rated(ctx, *, fields_out=None, **kw):
        if fields_out is not None:
            fields_out("FIELDS")
        return "RATING"
    monkeypatch.setattr(th, "thermal_context", lambda req_, ref, res, w, **kw: w)
    monkeypatch.setattr(th, "check_requirement",
                        lambda ctx, n, rows=None: th.RequirementCheck(False, 6000.0, (), (), ("6000 rpm: HOT_SPOT_ABOVE",), "HOT_SPOT_ABOVE"))
    monkeypatch.setattr(th, "rate_context", rated)
    monkeypatch.setattr("srmapp.evaluate._rated_kw_per_kg", lambda *a: 1.0)
    with mock.patch("srmapp.evaluate.build_map", return_value=_map(stage)), mock.patch("srmapp.evaluate.choose_turns", choose):
        e = evaluate_stage2(_cand(), req, stage, max_turns=30, rate_failed=rate_failed, fields_out=fields.append)
    return e, fields


def test_failing_case_is_rated_when_asked(monkeypatch):
    e, _ = _failing_stage2(monkeypatch, True)
    assert e.feasible is False and e.rating == "RATING" and e.thermal_check.reason == "HOT_SPOT_ABOVE"
    assert math.isfinite(e.rated_continuous_kw_per_l) and math.isfinite(e.rated_peak_kw_per_l)
    e, _ = _failing_stage2(monkeypatch, False)
    assert e.rating is None and e.thermal_check.reason == "HOT_SPOT_ABOVE"


def test_fields_reach_the_sink(monkeypatch):
    _, fields = _failing_stage2(monkeypatch, True)
    assert fields == ["FIELDS"]


def test_rated_infeasible_stays_off_the_front():
    from srmapp.pipeline import SearchResult
    c = _cand()

    def ev(feasible, v):
        return Evaluation(c.id, c.design, "ok", "", 10.0, None, 1.1, 1.1, 1000.0, 3.0, 0.9, feasible, None, None,
                          rated_continuous_kw_per_kg=v, rated_peak_kw_per_kg=v)
    res = SearchResult(_req(), 2, {}, 0, (ev(False, 9.0), ev(True, 1.0)), False)
    assert [e.feasible for e in res.pareto()] == [True]


def test_input_error_from_the_context_is_a_failed_evaluation_and_is_logged(monkeypatch, caplog):
    from srmcore.model.errors import InputError
    with caplog.at_level("ERROR", logger="srmapp.evaluate"):
        e, _, _ = _ranked_eval(monkeypatch, [], ctx_error=(1, InputError([])))
    assert e.status == "InputError" and not e.feasible
    assert any(r.exc_info for r in caplog.records) and _cand().id in caplog.text


def test_choose_turns_error_is_a_failed_evaluation_and_is_logged(caplog):
    stage = stage1(_req(), make_8_6())
    with mock.patch("srmapp.evaluate.build_map", return_value=_map(stage)), \
            mock.patch("srmapp.evaluate.choose_turns", side_effect=ValueError("scan broke")), \
            caplog.at_level("ERROR", logger="srmapp.evaluate"):
        e = evaluate_stage2(_cand(), _req(), stage, max_turns=30)
    assert e.status == "ValueError" and "scan broke" in e.error and not e.feasible
    assert any(r.exc_info for r in caplog.records) and _cand().id in caplog.text
