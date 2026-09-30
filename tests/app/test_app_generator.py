import pytest

from srmapp.requirements import Requirements
from srmapp.sizing.generator import POLE_SETS, sample_candidates
from srmcore.model.validator import require_valid
from srmcore.topology.radial import build_outline


def _req(**kw):
    values = dict(peak_power_w=30_000.0, peak_torque_nm=95.5, base_speed_rpm=3000.0, max_speed_rpm=9000.0)
    values.update(kw)
    return Requirements(**values)


def test_deterministic_for_a_seed():
    a, _ = sample_candidates(_req(), 8, seed=3)
    b, _ = sample_candidates(_req(), 8, seed=3)
    assert [c.id for c in a] == [c.id for c in b]
    c, _ = sample_candidates(_req(), 8, seed=4)
    assert [x.id for x in a] != [x.id for x in c]


def test_every_candidate_is_valid_and_fits():
    cands, dropped = sample_candidates(_req(), 12, seed=1)
    assert len(cands) > 0
    assert set(dropped) == {"validator", "fit"}
    for c in cands:
        require_valid(c.design)
        build_outline(c.design.machine)


def test_all_pole_sets_are_represented():
    cands, _ = sample_candidates(_req(), 16, seed=0)
    seen = {(c.design.machine.n_stator_poles, c.design.machine.n_rotor_poles) for c in cands}
    assert seen == {(s, r) for s, r, _ in POLE_SETS}


def test_outer_diameter_limit_is_respected():
    cands, _ = sample_candidates(_req(max_outer_diameter_m=0.15), 8, seed=0)
    assert all(c.design.machine.stator_outer_diameter <= 0.15 for c in cands)


def test_screening_preset_and_speed_are_set():
    c = sample_candidates(_req(), 4, seed=0)[0][0]
    assert c.design.mesh.preset == "screening"
    assert c.design.machine.max_speed_rpm == 9000.0


def test_ids_are_unique():
    cands, _ = sample_candidates(_req(), 16, seed=0)
    assert len({c.id for c in cands}) == len(cands)


def test_very_restrictive_limit_returns_fewer_without_raising():
    cands, dropped = sample_candidates(_req(max_outer_diameter_m=0.02), 8, seed=0)
    assert len(cands) <= 8
    assert sum(dropped.values()) >= 0
