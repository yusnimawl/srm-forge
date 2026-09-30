import dataclasses

import numpy as np
import pytest
from conftest import make_8_6

from map_fixtures import synthetic_map
from srmcore.maps import fidelity
from srmcore.maps.fidelity import fidelity_check
from srmcore.model.design import Design, MeshSettings


def _designs(n):
    return [Design(machine=make_8_6(turns_per_pole=40 + 10 * k), mesh=MeshSettings(preset="screening"))
            for k in range(n)]


def _fake(psi_scale=lambda k, preset: 1.0, torque_scale=lambda k, preset: 1.0, base=lambda k: 1.0 + k):
    """build_map stand-in: design k has L scaled by `base(k)`. `psi_scale` scales the inductance (so la, lu,
    psi_max and the model's torque) and `torque_scale` scales torque only, per design index and preset."""
    def build_map(design, i_max, **kw):
        k = (design.machine.turns_per_pole - 40) // 10
        s = base(k) * psi_scale(k, design.mesh.preset)
        r = synthetic_map(l0=2e-3 * s, l1=1e-3 * s)
        t = torque_scale(k, design.mesh.preset)
        return dataclasses.replace(r, torque_arkkio=r.torque_arkkio * t, torque_virtual_work=r.torque_virtual_work * t)
    return build_map


def screening(f):
    return lambda k, preset: f(k) if preset == "screening" else 1.0


def test_errors_and_rho(monkeypatch):
    monkeypatch.setattr(fidelity, "build_map", _fake(screening(lambda k: 1.01)))
    rep = fidelity_check(_designs(4), 20.0)
    assert rep.designs == 4 and rep.ok
    assert set(rep.rel_error) == {"la", "lu", "peak_torque", "psi_max"}
    assert rep.rel_error["la"] == pytest.approx(np.full(4, 0.01))
    assert rep.rel_error["peak_torque"] == pytest.approx(np.full(4, 0.01))
    assert all(r == pytest.approx(1.0) for r in rep.spearman.values())


def test_not_ok_when_one_key_number_four_percent_off(monkeypatch):
    monkeypatch.setattr(fidelity, "build_map", _fake(torque_scale=screening(lambda k: 1.04 if k == 2 else 1.0)))
    rep = fidelity_check(_designs(4), 20.0)
    assert rep.rel_error["peak_torque"][2] == pytest.approx(0.04)
    for k in ("la", "lu", "psi_max"):
        assert rep.rel_error[k] == pytest.approx(np.zeros(4), abs=1e-9)
    assert not rep.ok


@pytest.mark.parametrize("la_error, ok", [(0.04, True), (0.06, False)])
def test_la_tolerance_is_five_percent(monkeypatch, la_error, ok):
    last = {}
    fake = _fake()

    def build_map(design, i_max, **kw):
        last["preset"] = design.mesh.preset
        return fake(design, i_max, **kw)

    real = fidelity.key_numbers

    def key_numbers(result, machine):
        key = real(result, machine)
        return dataclasses.replace(key, la=key.la * (1 + la_error)) if last["preset"] == "screening" else key

    monkeypatch.setattr(fidelity, "build_map", build_map)
    monkeypatch.setattr(fidelity, "key_numbers", key_numbers)
    rep = fidelity_check(_designs(4), 20.0)
    assert rep.rel_error["la"] == pytest.approx(np.full(4, la_error))
    assert rep.ok is ok


def test_not_ok_when_ranking_flips_within_tolerance(monkeypatch):
    # full scales 1, 1.01, 1.02, 1.03; screening off by +-2 % in alternation reverses the pairs' order
    flip = lambda k: 1.02 if k % 2 == 0 else 0.98
    monkeypatch.setattr(fidelity, "build_map", _fake(screening(flip), base=lambda k: 1.0 + 0.01 * k))
    rep = fidelity_check(_designs(4), 20.0)
    assert all(np.all(e < 0.03) for e in rep.rel_error.values())
    assert all(r < 0.95 for r in rep.spearman.values())
    assert not rep.ok


def test_nan_rho_fails_with_three_designs(monkeypatch):
    monkeypatch.setattr(fidelity, "build_map", _fake(base=lambda k: 1.0))       # constant key numbers
    rep = fidelity_check(_designs(3), 20.0)
    assert all(np.isnan(r) for r in rep.spearman.values())
    assert not rep.ok


def test_two_designs_ignore_rho(monkeypatch):
    monkeypatch.setattr(fidelity, "build_map", _fake())
    rep = fidelity_check(_designs(2), 20.0)
    assert all(np.isnan(r) for r in rep.spearman.values())
    assert rep.ok
