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


def _fake(full_scale, screen_scale):
    """build_map stand-in: L scales with turns; the screening map is off by screen_scale(k)."""
    def build_map(design, i_max, **kw):
        k = (design.machine.turns_per_pole - 40) // 10
        s = 1.0 + k
        f = 1.0 if design.mesh.preset == "full" else screen_scale(k)
        return synthetic_map(l0=2e-3 * s * f, l1=1e-3 * s * f, psi_sat=None)
    return build_map


def test_errors_and_rho(monkeypatch):
    monkeypatch.setattr(fidelity, "build_map", _fake(None, lambda k: 1.01))
    rep = fidelity_check(_designs(4), 20.0)
    assert rep.designs == 4 and rep.ok
    assert set(rep.rel_error) == {"la", "lu", "peak_torque", "psi_max"}
    assert rep.rel_error["la"] == pytest.approx(np.full(4, 0.01))
    assert rep.rel_error["peak_torque"] == pytest.approx(np.full(4, 0.01))
    assert all(r == pytest.approx(1.0) for r in rep.spearman.values())


def test_not_ok_when_four_percent_off(monkeypatch):
    monkeypatch.setattr(fidelity, "build_map", _fake(None, lambda k: 1.04 if k == 2 else 1.0))
    rep = fidelity_check(_designs(4), 20.0)
    assert rep.rel_error["la"][2] == pytest.approx(0.04)
    assert not rep.ok


def test_two_designs_ignore_rho(monkeypatch):
    monkeypatch.setattr(fidelity, "build_map", _fake(None, lambda k: 1.0))
    rep = fidelity_check(_designs(2), 20.0)
    assert all(np.isnan(r) for r in rep.spearman.values())
    assert rep.ok
