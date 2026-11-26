import numpy as np
import pytest
from conftest import make_8_6
from map_fixtures import synthetic_map

from srmapp.drive import envelope as drive

MACHINE = make_8_6()
VOLTS, R = 400.0, 0.1
SPEEDS = [30.0, 1500.0, 9000.0]
TOP = drive.N_THETA - 1


@pytest.fixture(scope="module")
def tables():
    return drive._tables(synthetic_map(n_angles=24), 2 * np.pi / MACHINE.n_rotor_poles, 20.0, drive.N_THETA)


@pytest.fixture(scope="module")
def pairs():
    return drive._stroke_pairs(drive.N_THETA, drive.N_ON, drive.N_OFF)


def _omega(rpm):
    return rpm * 2 * np.pi / 60


CASES = [(rpm, VOLTS) for rpm in SPEEDS] + [(9000.0, 100.0)]


@pytest.fixture(scope="module", params=CASES, ids=lambda c: f"{c[0]:g}rpm-{c[1]:g}V")
def solved(request, tables, pairs):
    on, off = pairs
    rpm, volts = request.param
    omega = _omega(rpm)
    return (omega, volts, drive._strokes(tables, omega, volts, R, on, off),
            drive._simulate(tables, omega, volts, R, on, off))


@pytest.mark.parametrize("rpm", SPEEDS)
@pytest.mark.parametrize("trace", [False, True])
def test_run_from_rest_is_simulate(tables, pairs, rpm, trace):
    on, off = pairs
    omega = _omega(rpm)
    run = drive._run(tables, omega, VOLTS, R, on, off, np.zeros(on.size), trace)
    sim = drive._simulate(tables, omega, VOLTS, R, on, off, trace)
    for a, b in zip(run[:3], sim[:3]):
        np.testing.assert_array_equal(a, b)
    if trace:
        np.testing.assert_array_equal(run[6], sim[4])
        np.testing.assert_array_equal(run[7], sim[5])
        assert not run[6][0].any() and not run[7][0].any()


def test_accepted_single_pulses_keep_their_numbers(solved):
    _, _, (w_t, w_l, i2, valid, psi0), (s_t, s_l, s_i2, s_valid) = solved
    assert np.all(valid[s_valid]) and not psi0[s_valid].any()
    for new, old in ((w_t, s_t), (w_l, s_l), (i2, s_i2)):
        np.testing.assert_array_equal(new[s_valid], old[s_valid])
    rest = ~s_valid & ~valid
    for new, old in ((w_t, s_t), (w_l, s_l), (i2, s_i2)):
        np.testing.assert_array_equal(new[rest], old[rest])
    assert not psi0[rest].any()


def test_periodic_strokes_are_periodic(tables, pairs, solved):
    on, off = pairs
    omega, volts, (_, _, _, valid, psi0), (*_, s_valid) = solved
    per = np.flatnonzero(valid & ~s_valid)
    tol = drive.PERIODIC_TOL * tables.psi[:, -1].max()
    if per.size == 0:
        pytest.skip("no periodic stroke at this speed")
    *_, end, _, beyond, psi_t, _ = drive._run(tables, omega, volts, R, on[per], off[per], psi0[per], trace=True)
    assert np.all(np.abs(end - psi0[per]) <= 2 * tol) and not beyond.any()
    # the flux (hence the current) stays inside the table at every step
    rows = (on[per][None, :] + np.arange(TOP + 1)[:, None]) % TOP
    assert np.all(psi_t <= tables.psi[rows, -1] * (1 + 1e-6))


def test_strokes_beyond_the_current_limit_are_rejected(tables, pairs):
    on, off = pairs
    omega = _omega(9000.0)
    *_, valid, psi0 = drive._strokes(tables, omega, 100.0, R, on, off)
    rej = np.flatnonzero(~drive._simulate(tables, omega, 100.0, R, on, off)[3])
    cap = tables.psi[on % TOP, -1]
    admissible = rej[drive._run(tables, omega, 100.0, R, on[rej], off[rej], cap[rej])[3] <= cap[rej]]
    left = admissible[~valid[admissible]]
    assert left.size                                      # converged roots that break the limit rule exist here
    assert not valid[left].any() and not psi0[left].any()
    ok = admissible[valid[admissible]]
    assert not drive._run(tables, omega, 100.0, R, on[ok], off[ok], psi0[ok])[5].any()


def test_brute_force_matches_root(tables, pairs):
    on, off = pairs
    omega = _omega(1500.0)
    w, _, _, valid, psi0 = drive._strokes(tables, omega, 100.0, R, on, off)
    per = np.flatnonzero(psi0 > 0)
    if per.size == 0:
        pytest.fail("no periodic stroke at 1500 r/min, 100 V")
    pick = per[np.linspace(0, per.size - 1, min(5, per.size)).astype(int)]
    p = np.zeros(pick.size)
    tol = drive.PERIODIC_TOL * tables.psi[:, -1].max()
    for _ in range(2000):
        nxt = drive._run(tables, omega, 100.0, R, on[pick], off[pick], p)[3]
        done = np.all(np.abs(nxt - p) <= tol)
        p = nxt
        if done:
            break
    np.testing.assert_allclose(p, psi0[pick], atol=10 * tol)
    work = drive._run(tables, omega, 100.0, R, on[pick], off[pick], p)[0]
    np.testing.assert_allclose(work, w[pick], rtol=1e-6)


def test_rejected_when_the_cap_is_not_enough(tables, pairs):
    on, off = pairs
    omega = _omega(9000.0)
    *_, valid, psi0 = drive._strokes(tables, omega, 100.0, R, on, off)
    rejected = np.flatnonzero(~drive._simulate(tables, omega, 100.0, R, on, off)[3])
    cap = tables.psi[on % TOP, -1]
    over = rejected[drive._run(tables, omega, 100.0, R, on[rejected], off[rejected], cap[rejected])[3] > cap[rejected]]
    assert over.size and not valid[over].any() and not psi0[over].any()


def test_full_period_pulse_is_an_always_on_stroke(tables, pairs):
    on, off = pairs
    omega = _omega(100.0)
    pair = (np.array([45]), np.array([TOP + 45]))
    assert not drive._simulate(tables, omega, VOLTS, R, *pair)[3][0]
    w_t, _, _, valid, psi0 = drive._strokes(tables, omega, VOLTS, R, *pair)
    assert valid[0]
    assert psi0[0] == pytest.approx(tables.psi[45, -1], rel=1e-6)
    best = drive._strokes(tables, omega, VOLTS, R, on, off)
    assert w_t[0] < 0.01 * best[0][best[3]].max()


@pytest.mark.parametrize("rpm", SPEEDS)
@pytest.mark.parametrize("volts", [100.0, 400.0])
def test_no_stroke_needs_the_iteration_cap(tables, pairs, monkeypatch, rpm, volts):
    on, off = pairs
    omega = _omega(rpm)
    full = drive._strokes(tables, omega, volts, R, on, off)
    monkeypatch.setattr(drive, "PERIODIC_MAX_ITER", 10_000)
    for a, b in zip(drive._strokes(tables, omega, volts, R, on, off), full):
        np.testing.assert_array_equal(a, b)


# --- envelope, least-copper and fixed strokes -------------------------------------------------------------------

MAP = synthetic_map(n_angles=24)
ENV_SPEEDS = np.array([100.0, 1500.0, 6000.0, 12000.0, 40000.0])


def _single_pulse(t, omega, volts, r, on, off):
    return (*drive._simulate(t, omega, volts, r, on, off), np.zeros(on.size))


@pytest.mark.parametrize("volts", [400.0, 100.0])
def test_envelope_is_the_single_pulse_envelope_or_better(monkeypatch, volts):
    real = drive.envelope(MAP, MACHINE, volts, 0.1, ENV_SPEEDS)
    monkeypatch.setattr(drive, "_strokes", _single_pulse)
    old = drive.envelope(MAP, MACHINE, volts, 0.1, ENV_SPEEDS)
    same = real.work_torque == old.work_torque
    for a, b in ((real.torque, old.torque), (real.i_rms, old.i_rms), (real.theta_on, old.theta_on),
                 (real.theta_off, old.theta_off), (real.copper_loss, old.copper_loss)):
        np.testing.assert_array_equal(a[same], b[same])
    assert np.all(real.work_torque[~same] > old.work_torque[~same])
    assert np.all(real.torque >= old.torque)
    if volts == 100.0:
        assert not same[-1]                  # 40 000 r/min needs continuous conduction


def test_continuous_stroke_waveform():
    env = drive.envelope(MAP, MACHINE, 100.0, 0.1, [12000.0, 40000.0])
    w = env.waveforms
    assert np.all(w.current[1] > 0)                      # the phase never turns off
    assert not np.all(w.current[0] > 0)                  # 12 000 r/min stays single pulse
    np.testing.assert_allclose(4 * w.torque[1].mean(), env.torque[1], rtol=1e-3)
    np.testing.assert_allclose(np.sqrt((w.current[1] ** 2).mean()), env.i_rms[1], rtol=1e-3)
    assert env.torque[1] > 2 * 0.06                       # single pulse gives 0.06 N·m (test_drive_tail)


def test_min_copper_and_fixed_stroke_continuous():
    rpm, volts = 40000.0, 100.0
    top = drive.envelope(MAP, MACHINE, volts, 0.1, [rpm]).torque[0]
    s = drive.min_copper_stroke(MAP, MACHINE, volts, 0.1, rpm, 0.95 * top)
    assert s is not None and s.psi_on > 0 and s.valid
    assert s.current.max() <= s.current_limit * (1 + 1e-9)
    again = drive.fixed_stroke(MAP, MACHINE, volts, 0.1, rpm, s.theta_on, s.theta_off, s.current_limit)
    assert again.valid and again.psi_on == pytest.approx(s.psi_on, rel=1e-9)
    assert again.torque_avg == pytest.approx(s.torque_avg, rel=1e-9)
    assert again.i_rms == pytest.approx(s.i_rms, rel=1e-9)
    # a lower torque at a speed that allows single pulses keeps psi_on at 0
    low = drive.min_copper_stroke(MAP, MACHINE, 400.0, 0.1, 1500.0, 0.5)
    assert low.psi_on == 0.0
