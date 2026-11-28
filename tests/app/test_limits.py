import math
from unittest import mock

import pytest
from conftest import make_8_6

from srmapp.limits import SEARCH_REQUIRES_PASS, frequency_limit, hard_limits, rotor_limit
from srmapp.pipeline import SearchSettings, run_search
from srmapp.requirements import Requirements
from srmapp.sizing.generator import _DIMS, _machine
from srmcore.materials.library import load_material
from srmcore.model.design import RegionMaterials
from srmcore.post.rotor_stress import rotor_stress
from srmcore.topology.imported import parametric_iron
import numpy as np

JNEX = RegionMaterials(rotor="10JNEX900")


def _req(**kw):
    values = dict(peak_power_w=1000.0, peak_torque_nm=3.2, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    values.update(kw)
    return Requirements(**values)


def test_ok_above_the_safety_factor_passes():
    lim = rotor_limit(make_8_6(materials=JNEX), _req())
    assert lim.status == "pass" and lim.value >= 1.5
    assert "7 200 r/min" in lim.note and "at least 1.5" in lim.note and "1.2 x top speed" in lim.note


def test_ok_below_the_safety_factor_fails_and_names_it():
    lim = rotor_limit(make_8_6(materials=JNEX), _req(max_speed_rpm=60000.0))
    assert lim.status == "fail" and lim.value < 1.5
    assert f"rotor safety factor {lim.value:.2f} below 1.5 at 72 000 r/min" in lim.note


def test_no_fillet_and_out_of_range_fail():
    rotor = load_material("10JNEX900")
    bare = make_8_6(materials=JNEX, rotor_fillet_radius=0.0)
    assert rotor_stress(bare, rotor.density, rotor.mechanical, 6000.0).status == "no_fillet"
    assert rotor_limit(bare, _req()).status == "fail"
    base = make_8_6(materials=JNEX)
    chord = base.rotor_outer_diameter * math.sin(base.rotor_pole_arc / 2)
    # a yoke of 0.3 x the tip chord is below the stress model's 0.55 floor
    thin = make_8_6(materials=JNEX, rotor_yoke_thickness=0.3 * chord)
    assert rotor_stress(thin, rotor.density, rotor.mechanical, 6000.0).status == "kt_out_of_range"
    assert rotor_limit(thin, _req()).status == "fail"


def test_no_strength_data_and_imported_iron_are_not_run():
    assert rotor_limit(make_8_6(), _req()).status == "not_run"
    m = make_8_6(materials=JNEX)
    imported = m.model_copy(update={"iron": parametric_iron(m)})
    assert rotor_limit(imported, _req()).status == "not_run"


def test_gate_agrees_with_the_rating_stress_at_a_temperature():
    m = make_8_6(materials=JNEX)
    rotor = load_material("10JNEX900")
    hot = rotor_stress(m, rotor.density, rotor.mechanical, 6000.0, 120.0)
    assert rotor_limit(m, _req()).value == pytest.approx(hot.safety_factor)


def test_generator_rotor_yoke_ratio_is_in_the_stress_box():
    rng = np.random.default_rng(0)
    for u in rng.random((40, _DIMS)):
        m = _machine(u, 8, 6, 4, 0.08, 0.12, 6000.0, JNEX, 1e-4)
        w_r = m.rotor_outer_diameter * np.sin(m.rotor_pole_arc / 2)
        assert 0.55 - 1e-9 <= m.rotor_yoke_thickness / w_r <= 1.0 + 1e-9


def test_search_requires_a_checked_rotor():
    assert "rotor_stress" in SEARCH_REQUIRES_PASS
    with mock.patch("srmapp.pipeline.evaluate_stage2") as ev:
        res = run_search(_req(), SearchSettings(n_candidates=8, shortlist=3, seed=1, materials=RegionMaterials()))
    assert ev.call_count == 0 and res.evaluations == ()
    assert res.limit_rejected["rotor_stress"] > 0


def test_evaluation_with_a_failing_rotor_is_infeasible():
    from test_app_evaluate import _cand, _evaluate
    from srmcore.model.design import Design, MeshSettings
    from srmapp.sizing.generator import Candidate
    bad = make_8_6(materials=JNEX, rotor_fillet_radius=0.0)
    cand = Candidate("c0", Design(machine=bad, mesh=MeshSettings(preset="screening")))
    with mock.patch("test_app_evaluate._cand", return_value=cand):
        e, _ = _evaluate(_req())
    assert e.status == "ok" and not e.feasible
    assert {l.name: l for l in e.limits}["rotor_stress"].status == "fail" and "no root fillet" in e.error


def test_frequency_limit_by_pole_set():
    def st(nr, rpm):
        return frequency_limit(nr, _req(max_speed_rpm=rpm))
    assert st(16, 10610).status == "fail" and "2829 Hz" in st(16, 10610).note
    assert st(12, 10610).status == "pass"
    assert st(12, 15915).status == "fail"
    assert st(8, 19894).status == "pass"


def test_search_drops_pole_sets_above_the_frequency_cap():
    with mock.patch("srmapp.pipeline.evaluate_stage2") as ev:
        res = run_search(_req(max_speed_rpm=60000.0), SearchSettings(n_candidates=8, shortlist=3, materials=JNEX))
    assert res.sampled == 0 and ev.call_count == 0
    assert set(res.dropped_pole_sets) == {"6/4", "8/6", "12/8", "16/12", "24/16"}
    assert "Hz" in res.dropped_pole_sets["6/4"]


def test_frequency_limit_edge_passes():
    lim = frequency_limit(12, _req(max_speed_rpm=13900.0))
    assert lim.value == 2780.0 and lim.status == "pass"


def test_search_drops_only_the_sets_above_the_cap_and_samples_the_rest():
    with mock.patch("srmapp.pipeline.evaluate_stage2"):
        res = run_search(_req(max_speed_rpm=10610.0), SearchSettings(n_candidates=10, shortlist=3, materials=JNEX))
    assert set(res.dropped_pole_sets) == {"24/16"}
    assert res.sampled == 10


def test_hard_limits_include_the_frequency_and_a_case_above_it_is_infeasible():
    assert "iron_frequency" in {lim.name for lim in hard_limits(_req(), make_8_6())}
    from test_app_evaluate import _evaluate
    e, _ = _evaluate(_req(max_speed_rpm=30000.0))
    assert not e.feasible and "Hz" in e.error


def _bending_terms(machine, span):
    from srmapp.sizing.estimates import active_mass
    e, rho, d = 205e9, 7870.0, machine.shaft_diameter     # steel_1010 library values
    ei = e * math.pi * d ** 4 / 64
    w_r = math.sqrt(48 * ei / (active_mass(machine).rotor_iron * span ** 3))
    w_s = (math.pi / span) ** 2 * math.sqrt(ei / (rho * math.pi * d ** 2 / 4))
    return w_r * 30 / math.pi, w_s * 30 / math.pi


def test_bending_speed_matches_the_hand_arithmetic_and_is_below_both_terms():
    from srmapp.mechanical import BearingSetup, first_bending_rpm
    m = make_8_6()
    r_rpm, s_rpm = _bending_terms(m, 0.3)
    expected = (1 / r_rpm ** 2 + 1 / s_rpm ** 2) ** -0.5
    got = first_bending_rpm(m, BearingSetup(span_m=0.3))
    assert got == pytest.approx(expected, rel=1e-9)
    assert got < min(r_rpm, s_rpm)


def test_longer_span_lowers_the_bending_speed():
    from srmapp.mechanical import BearingSetup, first_bending_rpm
    m = make_8_6()
    assert first_bending_rpm(m, BearingSetup(span_m=0.4)) < first_bending_rpm(m, BearingSetup(span_m=0.3))


def test_bending_limit_passes_at_6000_rpm_with_the_span_note_and_fails_when_too_fast():
    from srmapp.limits import bending_limit
    lim = bending_limit(make_8_6(), _req())
    assert lim.status == "pass" and lim.value > 1.3 * 6000
    assert "estimated" in lim.note and "double-bearing" in lim.note
    assert bending_limit(make_8_6(), _req(max_speed_rpm=40000.0)).status == "fail"
    assert "bending" in SEARCH_REQUIRES_PASS and "bending" in {x.name for x in hard_limits(_req(), make_8_6())}


def test_given_span_drops_the_span_note_but_not_the_friction_placeholder():
    from srmapp.limits import bending_limit
    from srmapp.mechanical import BearingSetup
    assert "estimated" not in bending_limit(make_8_6(), _req(bearing=BearingSetup(span_m=0.2))).note
    assert BearingSetup(span_m=0.2).placeholder
    assert not BearingSetup(count=4, span_m=0.2).placeholder


def test_bearing_limit_edges_for_each_candidate_and_lubrication():
    from srmapp.limits import bearing_limit
    from srmapp.mechanical import BearingSetup
    assert bearing_limit(_req(max_speed_rpm=21590.0)).status == "pass"
    nsk = bearing_limit(_req(max_speed_rpm=21610.0))
    assert nsk.status == "fail" and nsk.limit == pytest.approx(25920.0)
    assert "NSK 30BNR19HTSUMP3" in nsk.note and "assumed" in nsk.note
    skf = BearingSetup(candidate="SKF 7005 CD/HCP4A")
    assert bearing_limit(_req(max_speed_rpm=29000.0, bearing=skf)).status == "pass"
    lim = bearing_limit(_req(max_speed_rpm=29050.0, bearing=skf))
    assert lim.status == "fail" and lim.limit == pytest.approx(34830.0) and "assumed" not in lim.note
    oil = BearingSetup(candidate="SKF 7005 CD/HCP4A", lubrication="oil_air")
    assert bearing_limit(_req(max_speed_rpm=45000.0, bearing=oil)).limit == pytest.approx(54270.0)
    assert bearing_limit(_req(max_speed_rpm=6000.0)).status == "pass"
    assert "bearing_speed" in {x.name for x in hard_limits(_req(), make_8_6())}
    assert "bearing_speed" not in SEARCH_REQUIRES_PASS


def test_candidate_and_lubrication_leave_the_friction_placeholder_alone():
    from srmapp.mechanical import BearingSetup
    assert BearingSetup(candidate="SKF 7006 CD/HCP4A", lubrication="oil_air").placeholder


def test_search_above_the_bearing_speed_rejects_every_stage1_pass(monkeypatch):
    import srmapp.pipeline as pipeline
    calls = []

    def counting(req, machine):
        calls.append(machine)
        return hard_limits(req, machine)
    monkeypatch.setattr(pipeline, "hard_limits", counting)
    with mock.patch("srmapp.pipeline.evaluate_stage2") as ev:
        res = run_search(_req(max_speed_rpm=24000.0),
                         SearchSettings(n_candidates=8, shortlist=3, seed=1, materials=JNEX))
    assert ev.call_count == 0 and res.evaluations == ()
    assert calls and res.limit_rejected["bearing_speed"] == len(calls)


def _gap_rating(cases, rotor_c=100.0, bore_c=80.0):
    from srmapp.thermal import Rating, SpeedRating
    sr = SpeedRating(3000.0, 1.0, 1.0, 1.0, None, None, rotor_c, rotor_c, bore_c, bore_c, 3, 10)
    return Rating((), (sr,), (), 180.0, "H", None, None, cases, 1.1, 5, (), "0")


def _gc(closure, centrifugal):
    from srmcore.post.rotor_stress import GapClosure
    return GapClosure(centrifugal, None, None, closure, "")


def test_gap_limit_full_closure_pass_and_fail():
    from srmapp.limits import GAP_SHARE, gap_limit
    m = make_8_6()
    half = GAP_SHARE * m.air_gap
    ok = {"continuous_overspeed": _gc(0.9 * half, 0.0), "peak_overspeed": _gc(0.5 * half, 0.0)}
    assert gap_limit(m, _gap_rating(ok)).status == "pass"
    bad = {"continuous_overspeed": _gc(0.5 * half, 0.0), "peak_overspeed": _gc(1.1 * half, 0.0)}
    lim = gap_limit(m, _gap_rating(bad))
    assert lim.status == "fail" and lim.value == pytest.approx(1.1 * half)


def test_gap_limit_centrifugal_only_and_not_run():
    from srmapp.limits import gap_limit
    m = make_8_6(materials=RegionMaterials(stator="10JNEX900", rotor="10JNEX900"))
    half = 0.5 * m.air_gap
    cases = lambda c: {"continuous_overspeed": _gc(None, c), "peak_overspeed": _gc(None, c)}  # noqa: E731
    assert gap_limit(m, _gap_rating(cases(0.5 * half))).status == "pass"
    assert gap_limit(m, _gap_rating(cases(1.5 * half))).status == "fail"
    assert gap_limit(m, _gap_rating(cases(0.5 * half), rotor_c=70.0)).status == "not_run"
    other = make_8_6(materials=RegionMaterials(stator="M19", rotor="10JNEX900"))
    assert gap_limit(other, _gap_rating(cases(0.5 * half))).status == "not_run"
    assert gap_limit(m, None).note.endswith("no rating")
    assert gap_limit(m, _gap_rating({})).status == "not_run"
