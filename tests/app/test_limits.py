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
