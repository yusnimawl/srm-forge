import math
from unittest import mock

import pytest

import numpy as np

from srmapp.drive.envelope import Envelope
from srmapp.evaluate import Evaluation
from srmapp.pipeline import SearchResult, SearchSettings, run_search
from srmapp.requirements import Requirements
from srmapp.sizing.estimates import J_PEAK_SCREEN, J_SCREEN
from srmapp.sizing.generator import sample_candidates
from srmcore.model.design import RegionMaterials


def _req(**kw):
    values = dict(peak_power_w=5_000.0, peak_torque_nm=16.0, base_speed_rpm=3000.0, max_speed_rpm=6000.0)
    values.update(kw)
    return Requirements(**values)


def _fake(candidate, req, stage, **kw):
    nan = float("nan")
    if kw["cancel"] is not None and kw["cancel"]():
        return Evaluation(candidate.id, candidate.design, "cancelled", "map cancelled", stage.mass.iron, None,
                          nan, nan, nan, nan, nan, False, None, None)
    return Evaluation(candidate.id, candidate.design, "ok", "", stage.mass.total, None, 1.2, 1.1,
                      5500.0, 5.5 / stage.mass.total, 0.9, True, Envelope(*([np.zeros(2)] * 9), None, *([np.zeros(2)] * 3)), None)


def test_search_runs_stages_in_order_and_respects_shortlist():
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake) as ev:
        res = run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                         SearchSettings(n_candidates=12, shortlist=3, seed=1))
    assert isinstance(res, SearchResult)
    assert res.sampled > 0 and ev.call_count == len(res.evaluations) == 3
    assert not res.cancelled


def test_stage1_rejections_are_counted():
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake):
        res = run_search(_req(peak_torque_nm=5000.0, peak_power_w=1.57e6),
                         SearchSettings(n_candidates=8, shortlist=3, seed=1))
    assert res.stage1_rejected == res.sampled and res.evaluations == ()


def test_cancel_returns_partial_results():
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 3   # pre-check, then the fake's own poll for design 1; design 2 is cancelled mid-evaluation
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake):
        res = run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                         SearchSettings(n_candidates=12, shortlist=6, seed=1), cancel=cancel)
    assert res.cancelled
    assert len(res.evaluations) == 1
    assert all(e.status == "ok" for e in res.evaluations)


def test_settings_reach_stage_one():
    seen = []
    real = __import__("srmapp.pipeline", fromlist=["stage1"]).stage1

    def spy(req, p, margin, j_peak, j_peak_max):
        seen.append((margin, j_peak, j_peak_max))
        return real(req, p, margin, j_peak, j_peak_max)
    with mock.patch("srmapp.pipeline.stage1", side_effect=spy), mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake):
        run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                   SearchSettings(n_candidates=4, shortlist=1, seed=1, j_peak=25e6, j_limit=30e6))
    assert seen and set(seen) == {(SearchSettings().resolved_margin, 25e6, J_PEAK_SCREEN)}


def test_settings_reach_stage_two():
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake) as ev:
        run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                   SearchSettings(n_candidates=4, shortlist=1, seed=1, j_peak=25e6, j_limit=30e6))
    kw = ev.call_args.kwargs
    assert (kw["j_peak"], kw["j_limit"], kw["j_peak_max"], kw["margin"]) == (25e6, 30e6, J_PEAK_SCREEN, SearchSettings().resolved_margin)


def test_explicit_peak_cap_is_used():
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake) as ev:
        run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                   SearchSettings(n_candidates=4, shortlist=1, seed=1, j_peak_max=33e6))
    assert ev.call_args.kwargs["j_peak_max"] == 33e6


def test_progress_counts_designs():
    seen = []
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake):
        run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0), SearchSettings(n_candidates=12, shortlist=3, seed=1),
                   progress=lambda done, total: seen.append((done, total)))
    assert seen[-1] == (3, 3) and [d for d, _ in seen] == [1, 2, 3]


def test_pareto_uses_rated_values():
    cands, _ = sample_candidates(_req(), 4, seed=0)

    def ev(i, feasible, cont, peak):
        c = cands[i]
        return Evaluation(c.id, c.design, "ok", "", 10.0, None, 1.1, 1.1, 1000.0, 3.0, 0.9, feasible, None, None,
                          rated_continuous_kw_per_kg=cont, rated_peak_kw_per_kg=peak)
    nan = float("nan")
    evals = (ev(0, True, 1.0, 3.0), ev(1, True, 2.0, 2.0), ev(2, True, 1.0, 1.0), ev(3, True, nan, nan),
             ev(0, False, 9.0, 9.0))
    res = SearchResult(_req(), 4, {}, 0, evals, False)
    assert {e.id for e in res.pareto()} == {evals[0].id, evals[1].id}


def test_search_is_rated_by_default_and_settings_reach_stage_two():
    assert SearchSettings().j_limit == J_SCREEN and SearchSettings().thermal and SearchSettings().n_speeds == 6
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake) as ev:
        run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                   SearchSettings(n_candidates=4, shortlist=1, seed=1, thermal=False, n_speeds=3))
    assert (ev.call_args.kwargs["thermal"], ev.call_args.kwargs["n_speeds"]) == (False, 3)


def test_margin_follows_the_worst_material_grade():
    assert SearchSettings().resolved_margin == pytest.approx(1.05)                       # 10JNEX900, grade B
    assert SearchSettings(materials=RegionMaterials()).resolved_margin == pytest.approx(1.12)   # M19, grade C
    mixed = RegionMaterials(stator="10JNEX900", rotor="M19")
    assert SearchSettings(materials=mixed).resolved_margin == pytest.approx(1.12)


def test_explicit_margin_overrides_the_grade_rule():
    assert SearchSettings(margin=1.0).resolved_margin == 1.0


def test_search_candidates_use_the_settings_materials():
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake) as ev:
        run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                   SearchSettings(n_candidates=4, shortlist=1, seed=1, materials=RegionMaterials(rotor="10JNEX900")))
    assert ev.call_args.args[0].design.machine.materials == RegionMaterials(rotor="10JNEX900")
    assert ev.call_args.kwargs["margin"] == pytest.approx(1.12)


def test_point_progress_reaches_each_stage_two_map():
    seen = []

    def fake(candidate, req, stage, **kw):
        kw["progress"](5, 10)
        return _fake(candidate, req, stage, **kw)
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=fake):
        run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0), SearchSettings(n_candidates=12, shortlist=2, seed=1),
                   point_progress=lambda *a: seen.append(a))
    assert seen == [(1, 2, 5, 10), (2, 2, 5, 10)]


def test_no_point_progress_passes_none():
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake) as ev:
        run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0), SearchSettings(n_candidates=4, shortlist=1, seed=1))
    assert ev.call_args.kwargs["progress"] is None


def test_candidates_carry_the_rotor_root_fillet():
    from srmapp.sizing.generator import ROTOR_FILLET_SHARE
    from srmcore.post.rotor_stress import pole_half_width
    cands, _ = sample_candidates(_req(), 4, seed=0)
    for c in cands:
        m = c.design.machine
        root = 2 * pole_half_width(m, m.rotor_yoke_outer_radius)
        assert m.rotor_fillet_radius == pytest.approx(ROTOR_FILLET_SHARE * root)


def _failing(statuses):
    it = iter(statuses)

    def fake(candidate, req, stage, **kw):
        status = next(it)
        if status == "ok":
            return _fake(candidate, req, stage, **kw)
        return Evaluation(candidate.id, candidate.design, status, f"{status} last", stage.mass.iron, None,
                          *([float("nan")] * 5), False, None, None)
    return fake


def _run(statuses):
    with mock.patch("srmapp.pipeline.evaluate_stage2", _failing(statuses)):
        return run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                          SearchSettings(n_candidates=60, shortlist=len(statuses), seed=1))


def test_third_failure_of_one_status_stops_the_search():
    res = _run(["ok", "MapFailed", "MapFailed", "ok", "MapFailed", "ok", "ok"])
    assert len(res.evaluations) == 5 and not res.cancelled
    assert res.stopped == "stopped after 3 evaluations failed with MapFailed: MapFailed last"


def test_two_failures_of_each_of_two_statuses_do_not_stop_it():
    res = _run(["MapFailed", "ValueError", "MapFailed", "ValueError", "ok"])
    assert len(res.evaluations) == 5 and res.stopped == ""
