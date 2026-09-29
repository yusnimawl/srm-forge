"""Map runner: layout, failed-point policy, cancellation. Solves are faked except in the last test."""
import numpy as np
import pytest

from conftest import make_8_6
from srmcore.fields.solution import SolveStatus
from srmcore.maps import run
from srmcore.maps.point import PointResult, solve_point
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design, MeshSettings
from srmcore.model.errors import MapFailed

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
CIRCUITS = ("A", "B", "C", "D")
ANGLES = np.arange(8) * 0.01
CURRENTS = np.arange(8) * 2.5          # 64 points: one failure is 1.6 %, two are 3.1 %


def _fake(monkeypatch, failing=(), currents=CURRENTS):
    """solve_point stand-in, linear in current so PCHIP reproduces it exactly; `failing` is a set of
    (angle index, current index) that come back NONCONVERGED with garbage values."""
    bad = {(round(float(ANGLES[a]), 9), round(float(currents[i]), 9)) for a, i in failing}

    def fake(static, design, angle, currents, solver, **kw):
        amps = currents["A"]
        failed = (round(angle, 9), round(amps, 9)) in bad
        psi = np.array([0.01 * (1 + angle) * amps, 0.0, 0.0, 0.0])
        return PointResult(
            angle=angle, circuits=CIRCUITS, currents=np.array([amps, 0.0, 0.0, 0.0]),
            psi=np.full(4, 1e9) if failed else psi, torque_arkkio=1e9 if failed else 0.5 * amps,
            torque_virtual_work=1e9 if failed else 0.5 * amps, energy=0.2 * amps,
            coenergy=1e9 if failed else 0.3 * amps,
            status=SolveStatus.NONCONVERGED if failed else SolveStatus.OK,
            iterations=3, fallbacks=(), load_fraction=1.0)

    monkeypatch.setattr(run, "solve_point", fake)
    monkeypatch.setattr(run, "make_solver", lambda *a, **k: object())


def _run(**kw):
    return run.run_map(None, DESIGN, ANGLES, CURRENTS, **kw)


def test_layout_and_no_failures(monkeypatch):
    _fake(monkeypatch)
    r = _run()
    assert r.psi.shape == (8, 8, 4) and r.torque_arkkio.shape == (8, 8)
    assert r.circuits == CIRCUITS and r.excited == "A" and r.complete
    assert np.all(r.status == run.STATUS_OK) and not r.filled.any()
    assert np.allclose(r.psi[3, 5, 0], 0.01 * (1 + ANGLES[3]) * CURRENTS[5])


def test_one_interior_failure_is_interpolated_and_flagged(monkeypatch):
    _fake(monkeypatch, failing={(2, 3)})
    r = _run()
    assert r.filled[2, 3] and r.filled.sum() == 1 and r.status[2, 3] == run.STATUS_NONCONVERGED
    assert r.psi[2, 3, 0] == pytest.approx(0.01 * (1 + ANGLES[2]) * CURRENTS[3], rel=1e-9)
    assert r.torque_arkkio[2, 3] == pytest.approx(0.5 * CURRENTS[3], rel=1e-9)
    assert r.torque_virtual_work[2, 3] == pytest.approx(0.5 * CURRENTS[3], rel=1e-9)
    assert r.coenergy[2, 3] == pytest.approx(0.3 * CURRENTS[3], rel=1e-9)


def test_exactly_two_percent_failing_passes(monkeypatch):
    currents = np.arange(10) * 2.0                 # 5 angles x 10 currents = 50 points, one failure = 2 %
    _fake(monkeypatch, failing={(2, 3)}, currents=currents)
    r = run.run_map(None, DESIGN, ANGLES[:5], currents)
    assert r.filled.sum() == 1 and r.filled[2, 3]


@pytest.mark.parametrize("failing, reason", [
    ({(0, 3)}, "aligned"), ({(4, 7)}, "I_max"), ({(2, 0)}, "zero current"), ({(2, 2), (3, 3)}, "2 %")])
def test_map_fails_on_the_policy_conditions(monkeypatch, failing, reason):
    _fake(monkeypatch, failing=failing)
    with pytest.raises(MapFailed) as e:
        _run()
    assert any(reason in r for r in e.value.reasons) and e.value.n_failed == len(failing)


def test_cancel_keeps_partial_results_unfilled(monkeypatch):
    _fake(monkeypatch, failing={(0, 3)})           # would fail the policy if it were applied
    calls = []
    r = _run(cancel=lambda: len(calls) >= 3, progress=lambda done, total: calls.append(done))
    assert not r.complete and calls == [1, 2, 3]
    assert np.all(r.status[3:] == run.STATUS_NOT_RUN) and np.isnan(r.psi[3:]).all()
    assert np.all(r.status[:3] != run.STATUS_NOT_RUN) and not r.filled.any()


@pytest.mark.parametrize("excited", ["Z", "B"])
def test_only_phase_a_is_supported(monkeypatch, excited):
    _fake(monkeypatch)
    with pytest.raises(ValueError, match="excited"):
        _run(excited=excited)


@pytest.mark.parametrize("currents", [[0.0, 2.0, 2.0], [3.0, 1.0], [1.0], [0.0, np.nan, 4.0], [0.0, 2.0, np.inf]])
def test_currents_must_increase(monkeypatch, currents):
    _fake(monkeypatch)
    with pytest.raises(ValueError, match="currents"):
        run.run_map(None, DESIGN, ANGLES, np.array(currents))


def test_real_solves_match_solve_point():
    static = build_machine_mesh(DESIGN)
    pitch = static.settings.band_pitch
    angles, currents = np.array([0.0, 2 * pitch]), np.array([0.0, 5.0])
    r = run.run_map(static, DESIGN, angles, currents, solver_name="skfem_reference")
    solver = run.make_solver("skfem_reference")
    direct = solve_point(static, DESIGN, angles[1], {"A": 5.0}, solver)
    assert r.circuits == direct.circuits
    assert np.allclose(r.psi[1, 1], direct.psi, rtol=1e-9)
    assert r.torque_arkkio[1, 1] == pytest.approx(direct.torque_arkkio, rel=1e-9)
    assert np.all(r.psi[:, 0] == 0.0)
