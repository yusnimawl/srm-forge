from srmapp.requirements import Requirements
from srmapp.sizing.generator import POLE_SETS, REFERENCE_TURNS, sample_candidates
from srmcore.model.design import RegionMaterials
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
    assert set(dropped) == {"validator", "fit", "length"}
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


def test_full_preset_reference_turns_and_speed_are_set():
    cands, _ = sample_candidates(_req(), 8, seed=0)
    assert all(c.design.mesh.preset == "full" for c in cands)
    assert all(c.design.machine.turns_per_pole == REFERENCE_TURNS for c in cands)
    assert cands[0].design.machine.max_speed_rpm == 9000.0


def test_ids_are_unique():
    cands, _ = sample_candidates(_req(), 16, seed=0)
    assert len({c.id for c in cands}) == len(cands)


def test_very_restrictive_limit_returns_nothing_and_counts_drops():
    cands, dropped = sample_candidates(_req(max_outer_diameter_m=0.011), 8, seed=0)
    assert cands == []
    assert sum(dropped.values()) > 0


def test_split_is_even_over_pole_sets():
    cands, _ = sample_candidates(_req(), 8, seed=0)
    counts = [sum(c.design.machine.n_stator_poles == s for c in cands) for s, _, _ in POLE_SETS]
    assert counts == [2, 2, 2, 1, 1]


def test_small_n_uses_first_pole_sets():
    cands, _ = sample_candidates(_req(), 3, seed=0)
    assert [c.design.machine.n_stator_poles for c in cands] == [s for s, _, _ in POLE_SETS[:3]]


def test_materials_and_their_lamination_thickness_are_set():
    mats = RegionMaterials(stator="10JNEX900", rotor="10JNEX900")
    cands, _ = sample_candidates(_req(), 8, seed=0, materials=mats)
    assert all(c.design.machine.materials == mats for c in cands)
    assert all(c.design.machine.lamination_thickness == 1e-4 for c in cands)


def test_sample_candidates_preset():
    kept, _ = sample_candidates(_req(), 4, seed=0, preset="screening")
    assert kept and all(c.design.mesh.preset == "screening" for c in kept)


def test_16_12_samples_pass_the_validator_and_the_fit_check():
    cands, _ = sample_candidates(_req(), 4, seed=0, pole_sets=[(16, 12, 4)])
    assert len(cands) == 4 and all(c.design.machine.n_rotor_poles == 12 for c in cands)


def test_unset_length_limit_keeps_the_old_stack_mapping():
    import numpy as np
    from conftest import make_8_6
    from srmapp.sizing.generator import _DIMS, _machine
    for u in np.random.default_rng(0).random((5, _DIMS)):
        m = _machine(u, 8, 6, 4, 0.08, 0.12, 6000.0, RegionMaterials(), 1e-4)
        assert m.stack_length == m.stator_outer_diameter * (0.25 + 0.95 * u[1])


def test_length_limit_caps_the_total_and_still_fills_n():
    from srmapp.sizing.estimates import active_length
    limit = 0.07
    cands, dropped = sample_candidates(_req(max_length_m=limit), 12, seed=0)
    assert len(cands) == 12 and dropped["length"] > 0
    assert all(active_length(c.design.machine) <= limit for c in cands)
