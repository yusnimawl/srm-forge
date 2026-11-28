"""Shortlist order of `run_search` (D4): likely designs first, lightest first, round-robin over the pole sets."""
from dataclasses import replace
from unittest import mock

from srmapp import pipeline
from srmapp.evaluate import Evaluation
from srmapp.pipeline import SearchSettings, run_search
from srmapp.requirements import Requirements
from srmapp.sizing.estimates import Mass

NAN = float("nan")


def _req():
    return Requirements(peak_power_w=630.0, peak_torque_nm=2.0, base_speed_rpm=3000.0, max_speed_rpm=6000.0)


def _setup(feasible=lambda c: True, upper_of=None, mass_of=None, share=1.0):
    """Fakes: stage 1 gives each candidate a mass (by index) and a torque bound; evaluation is `feasible(candidate)`."""
    order = []

    def fake_stage1(req, p, margin, j_peak, j_peak_max):
        real = pipeline_stage1(req, p, margin, j_peak, j_peak_max)
        key = (p.n_stator_poles, round(p.stator_outer_diameter * 1e6))
        return replace(real, mass=Mass(mass_of(key), 0.0, 0.0) if mass_of else real.mass,
                       torque_upper=upper_of(key) if upper_of else real.torque_upper, passes=True, reason="")

    def fake_eval(candidate, req, stage, **kw):
        order.append(candidate)
        ok = feasible(candidate)
        return Evaluation(candidate.id, candidate.design, "ok", "", stage.mass.total, None, 1.2, 1.1, 5500.0, 1.0, 0.9,
                          ok, None, None)
    return order, fake_stage1, fake_eval


pipeline_stage1 = pipeline.stage1


def _run(order_fakes, **settings):
    order, s1, ev = order_fakes
    with mock.patch("srmapp.pipeline.stage1", side_effect=s1), mock.patch("srmapp.pipeline.evaluate_stage2", side_effect=ev), \
            mock.patch("srmapp.pipeline.BOUND_SHARE", 1.0):
        res = run_search(_req(), SearchSettings(n_candidates=30, seed=1, **settings))
    return order, res


def _sets(order):
    return [(c.design.machine.n_stator_poles) for c in order]


def test_within_a_set_unlikely_designs_come_last_and_each_group_is_lightest_first():
    # The bound decides likely: with share 1.0 a design is likely when its bound reaches margin x 2 N m.
    need = 2.0 * SearchSettings().resolved_margin
    mass = lambda key: key[1] % 1000 + 1.0                       # arbitrary but distinct per design
    upper = lambda key: need * (2.0 if key[1] % 2 == 0 else 0.5)  # even keys likely, odd keys not
    order, _ = _run(_setup(mass_of=mass, upper_of=upper), shortlist=1000, pole_sets=((8, 6, 4),))
    keys = [(c.design.machine.n_stator_poles, round(c.design.machine.stator_outer_diameter * 1e6)) for c in order]
    flags = [k[1] % 2 == 0 for k in keys]
    assert flags == sorted(flags, reverse=True)                   # likely first
    for group in (True, False):
        masses = [mass(k) for k, f in zip(keys, flags) if f == group]
        assert masses == sorted(masses)


def test_rounds_alternate_pole_sets_and_shortlist_caps_the_total():
    order, res = _run(_setup(), shortlist=6, pole_sets=((6, 4, 3), (8, 6, 4)))
    assert len(order) == len(res.evaluations) == 6
    assert _sets(order) == [6, 8, 6, 8, 6, 8] or _sets(order) == [8, 6, 8, 6, 8, 6]


def test_per_pole_set_one_with_feasible_fakes_evaluates_one_per_set():
    order, _ = _run(_setup(), shortlist=40, per_pole_set=1, pole_sets=((6, 4, 3), (8, 6, 4), (12, 8, 3)))
    assert sorted(_sets(order)) == [6, 8, 12]


def test_a_set_with_only_infeasible_designs_runs_until_its_list_ends():
    order, _ = _run(_setup(feasible=lambda c: c.design.machine.n_stator_poles != 8), shortlist=1000, per_pole_set=1,
                    pole_sets=((6, 4, 3), (8, 6, 4)))
    sets = _sets(order)
    assert sets.count(6) == 1 and sets.count(8) > 1
