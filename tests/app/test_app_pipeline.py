from unittest import mock

import numpy as np

from srmapp.drive.envelope import Envelope
from srmapp.evaluate import Evaluation
from srmapp.pipeline import SearchResult, SearchSettings, run_search
from srmapp.requirements import Requirements
from srmapp.sizing.generator import sample_candidates


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
                      5500.0, 5.5 / stage.mass.total, 0.9, True, Envelope(*([np.zeros(2)] * 9)), None)


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
    assert seen and set(seen) == {(1.05, 25e6, 60e6)}


def test_settings_reach_stage_two():
    with mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=_fake) as ev:
        run_search(_req(peak_torque_nm=2.0, peak_power_w=630.0),
                   SearchSettings(n_candidates=4, shortlist=1, seed=1, j_peak=25e6, j_limit=30e6))
    kw = ev.call_args.kwargs
    assert (kw["j_peak"], kw["j_limit"], kw["j_peak_max"], kw["margin"]) == (25e6, 30e6, 60e6, 1.05)


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


def test_pareto_uses_feasible_designs_only():
    cands, _ = sample_candidates(_req(), 4, seed=0)

    def ev(i, feasible, mass, density, eff):
        c = cands[i]
        return Evaluation(c.id, c.design, "ok", "", mass, None, 1.1, 1.1, 1000.0, density, eff, feasible, None, None)
    evals = (ev(0, True, 10.0, 3.0, 0.9), ev(1, True, 12.0, 2.0, 0.8), ev(2, False, 5.0, 9.0, 0.99),
             ev(3, True, 8.0, 3.5, 0.85))
    res = SearchResult(_req(), 4, {}, 0, evals, False)
    ids = {e.id for e in res.pareto()}
    assert ids == {evals[0].id, evals[3].id}
