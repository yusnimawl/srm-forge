import dataclasses
import math

import numpy as np
import pytest

from conftest import make_8_6
from map_fixtures import PERIOD, synthetic_map
from srmcore.maps import DriveTables, KeyNumbers, MapReport, analyse_map
from srmcore.maps.checks import Check, map_checks
from srmcore.model.design import Design, MeshSettings

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
M = DESIGN.machine
MU0 = 4e-7 * math.pi
P_PH, N = M.n_stator_poles / M.n_phases, M.turns_per_pole
LA_EST = P_PH * N**2 * MU0 * M.bore_radius * min(M.stator_pole_arc, M.rotor_pole_arc) * M.stack_length / M.air_gap
LU_EST = (P_PH * N**2 * MU0 * M.bore_radius * M.stator_pole_arc * M.stack_length
          / (M.air_gap + M.rotor_outer_radius - M.rotor_yoke_outer_radius))


def good_map(**kw):
    """Linear synthetic map whose La and Lu sit inside every design-dependent band."""
    la = 1.2 * LA_EST
    lu = la / 8
    return synthetic_map(l0=(la + lu) / 2, l1=(la - lu) / 2, currents=np.linspace(0, 5, 9), **kw)


def by_name(result, design=DESIGN):
    return {c.name: c for c in map_checks(result, design)}


def test_consistent_map_passes_every_check():
    checks = by_name(good_map())
    assert len(checks) == 14
    assert {n: c.status for n, c in checks.items() if c.status != "pass"} == {}
    assert all(isinstance(c, Check) for c in checks.values())


def test_torque_scaled_fails_coenergy_torque():
    r = good_map(n_angles=16)
    bad = dataclasses.replace(r, torque_arkkio=1.1 * r.torque_arkkio, torque_virtual_work=1.1 * r.torque_virtual_work)
    c = by_name(bad)["coenergy_torque"]
    assert c.status == "fail" and c.value == pytest.approx(0.1, abs=0.02)


def test_coarse_grid_warns_instead_of_failing_energy_checks():
    r = good_map(n_angles=12)
    bad = dataclasses.replace(r, torque_arkkio=1.1 * r.torque_arkkio, torque_virtual_work=1.1 * r.torque_virtual_work)
    c = by_name(bad)["coenergy_torque"]
    assert c.status == "warn" and c.value > c.limit and "grid too coarse" in c.detail and "12 angles < 16" in c.detail


def test_arkkio_vs_nodal_fails_on_disagreement():
    r = good_map()
    bad = dataclasses.replace(r, torque_virtual_work=1.05 * r.torque_virtual_work)
    assert by_name(bad)["arkkio_vs_nodal"].status == "fail"


def test_energy_identity_fails_on_wrong_energy():
    r = good_map()
    assert by_name(dataclasses.replace(r, energy=1.01 * r.energy))["energy_identity"].status == "fail"


def test_loop_energy_fails_when_flux_is_scaled():
    r = good_map(n_angles=16)
    psi = r.psi.copy()
    psi[..., 0] *= 1.1
    assert by_name(dataclasses.replace(r, psi=psi))["loop_energy"].status == "fail"


def test_zero_mean_torque_fails_on_offset():
    r = good_map()
    t = r.torque_arkkio + 0.05 * np.abs(r.torque_arkkio).max() * (r.currents[None, :] / r.currents[-1]) ** 2
    assert by_name(dataclasses.replace(r, torque_arkkio=t))["zero_mean_torque"].status == "fail"


def test_torque_at_aligned_fails_on_offset():
    r = good_map()
    t = r.torque_arkkio.copy()
    t[0] += 0.05 * np.abs(t).max()          # angle 0 is the aligned angle
    assert by_name(dataclasses.replace(r, torque_arkkio=t))["zero_torque_aligned_unaligned"].status == "fail"


def test_flipped_torque_fails_sign_pattern():
    r = good_map()
    bad = dataclasses.replace(r, torque_arkkio=-r.torque_arkkio)
    assert by_name(bad)["sign_pattern"].status == "fail"


@pytest.mark.parametrize("ratio, status", [(1.5, "fail"), (2.5, "warn"), (5.0, "pass"), (20.0, "warn")])
def test_la_lu_bands(ratio, status):
    la, lu = ratio * 1e-3, 1e-3
    r = synthetic_map(l0=(la + lu) / 2, l1=(la - lu) / 2)
    c = by_name(r)["la_lu"]
    assert c.status == status and c.value == pytest.approx(ratio, rel=1e-3)


def test_dpsi_di_positive_fails_on_decreasing_flux():
    r = good_map()
    psi = r.psi.copy()
    psi[5, -1, 0] = psi[5, -2, 0] - 1e-6
    assert by_name(dataclasses.replace(r, psi=psi))["dpsi_di_positive"].status == "fail"


def test_psi_bound_fails_above_the_iron_limit():
    r = good_map()
    psi = 100 * r.psi
    assert by_name(dataclasses.replace(r, psi=psi))["psi_bound"].status == "fail"


def test_psi_decreasing_fails_on_bump():
    r = good_map()
    psi = r.psi.copy()
    psi[3, -1, 0] += 0.3 * psi[:, -1, 0].max()      # a bump on the way from aligned to unaligned
    assert by_name(dataclasses.replace(r, psi=psi))["psi_decreasing"].status == "fail"


def test_la_analytic_warns_outside_band():
    lu = 2 * LU_EST
    r = synthetic_map(l0=(3 * LA_EST + lu) / 2, l1=(3 * LA_EST - lu) / 2, currents=np.linspace(0, 5, 9))
    c = by_name(r)["la_analytic"]
    assert c.status == "warn" and c.value == pytest.approx(3.0, rel=1e-2)


def test_lu_air_slot_fails_below_estimate():
    la = 1.2 * LA_EST
    lu = 0.5 * LU_EST
    r = synthetic_map(l0=(la + lu) / 2, l1=(la - lu) / 2, currents=np.linspace(0, 5, 9))
    c = by_name(r)["lu_air_slot"]
    assert c.status == "fail" and c.value == pytest.approx(0.5, rel=1e-2)


def test_iron_b_peak_warns_above_the_last_bh_point():
    from srmcore.materials.laws import library_law
    b_last = min(library_law(M.materials.stator).bn, library_law(M.materials.rotor).bn)
    ok = by_name(good_map(b_peak=0.99 * b_last))["iron_b_peak"]
    assert ok.status == "pass" and ok.limit == 1.0 and ok.value == pytest.approx(0.99)
    assert by_name(good_map(b_peak=1.01 * b_last))["iron_b_peak"].status == "warn"


def test_analyse_map_report():
    rep = analyse_map(good_map(), DESIGN)
    assert isinstance(rep, MapReport) and isinstance(rep.key_numbers, KeyNumbers)
    assert isinstance(rep.tables, DriveTables) and rep.ok
    assert rep.dpsi_dtheta.shape == rep.result.psi.shape
    bad = dataclasses.replace(rep.result, torque_arkkio=-rep.result.torque_arkkio)
    assert not analyse_map(bad, DESIGN).ok


def test_analyse_map_requires_complete():
    with pytest.raises(ValueError, match="incomplete"):
        analyse_map(good_map(complete=False), DESIGN)


@pytest.mark.slow
def test_real_8_6_map_checks(tmp_path):
    from srmcore.maps import build_map
    r = build_map(DESIGN, 20.0, n_angles=8, n_currents=3, workers=4, cache_dir=tmp_path)
    rep = analyse_map(r, DESIGN)
    status = {c.name: c.status for c in rep.checks}
    assert len(rep.checks) == 14 and np.isfinite(r.b_peak).all()
    # 8 angles is below MIN_ANGLES_FOR_ENERGY_CHECKS, so the two energy checks warn instead of failing.
    assert status["coenergy_torque"] == "warn" and status["loop_energy"] == "warn"
    assert rep.ok


def test_psi_decreasing_fails_on_dip_just_after_unaligned():
    r = good_map()
    first_up = int(np.flatnonzero(r.angles > PERIOD / 2)[0])
    psi = r.psi.copy()
    psi[first_up, -1, 0] = 0.0                       # below the unaligned flux
    assert by_name(dataclasses.replace(r, psi=psi))["psi_decreasing"].status == "fail"


def test_phase_b_map_uses_its_own_aligned_angle():
    r = good_map(excited="B")
    assert r.excited == "B" and r.angles[0] != 0.0
    checks = by_name(r)
    for name in ("sign_pattern", "zero_torque_aligned_unaligned", "psi_decreasing", "coenergy_torque"):
        assert checks[name].status == "pass", name
    flipped = dataclasses.replace(r, torque_arkkio=-r.torque_arkkio)
    assert by_name(flipped)["sign_pattern"].status == "fail"


def _nan_at(r, name):
    a = np.array(getattr(r, name), dtype=float)
    a[(0,) * a.ndim] = np.nan
    return dataclasses.replace(r, **{name: a})


@pytest.mark.parametrize("field, check", [("b_peak", "iron_b_peak"), ("torque_virtual_work", "arkkio_vs_nodal")])
def test_nan_in_a_field_is_not_a_pass(field, check):
    c = by_name(_nan_at(good_map(), field))[check]
    assert c.status != "pass" and "non-finite" in c.detail


def test_nan_inductances_are_not_a_pass():
    r = good_map()
    key = dataclasses.replace(analyse_map(r, DESIGN).key_numbers, la=float("nan"), lu=float("nan"),
                              la_lu=float("nan"))
    checks = {c.name: c for c in map_checks(r, DESIGN, key)}
    assert checks["la_lu"].status != "pass" and checks["lu_air_slot"].status != "pass"
