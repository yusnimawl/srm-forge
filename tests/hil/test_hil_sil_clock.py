"""Scenario.controller_clock: the controller's ISR, ctrl_slow, PWM carrier and micros() run on a clock r times its
nominal rate, while the plant, the sensors and the HAL constants stay on true time and nominal values."""

import math

import numpy as np
import pytest
from sil_fixtures import analytic_motor
from test_sil_core import IDEAL, run

from srmsil.scenario import Scenario

DT, DURATION, ISR_HZ = 0.5e-6, 0.02, 20000.0
N_STEPS = round(DURATION / DT)
R = 1.0125


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    return tmp_path_factory.mktemp("hil_sil_clock")


def step_of(seconds):
    return math.floor(seconds / DT + 0.5)    # llround for the positive times of the sim


def isr_steps(r):
    out, k = [], 0
    while (s := step_of((k + 0.5) / (ISR_HZ * r))) < N_STEPS:
        out.append(s)
        k += 1
    return np.array(out)


def slow_steps(r):
    out, k = [], 1
    while (s := step_of(k * (1e-3 / r))) < N_STEPS:
        out.append(s)
        k += 1
    return np.array(out)


def micros_gate(r):
    """Expected phase-2 gate: bit 0 of micros() / 100 latched at each ISR step and held until the next."""
    g = np.zeros(N_STEPS, np.uint8)
    for s in isr_steps(r):
        g[s:] = (math.floor(s * DT * 1e6 * r + 0.5) // 100) & 1
    return g


def edges(g):
    return np.flatnonzero(np.diff(g.astype(int))) + 1


def probe(cache, tag, **extra):
    return run(cache, "clock_probe", analytic_motor(), tag, speed_rpm=1000.0, duration=DURATION, dt=DT,
               pwm_hz=ISR_HZ, compute_delay=0.0, converter=IDEAL, params={"pwm_hz": ISR_HZ, "isr_hz": ISR_HZ},
               **extra)


def test_default_clock_is_unchanged(cache):
    base = probe(cache, "c")
    one = probe(cache, "c", controller_clock=1.0)
    for k, a in base.traces.items():
        np.testing.assert_array_equal(a, one.traces[k], err_msg=k)
    g = base.traces["gate_u"]
    np.testing.assert_array_equal(edges(g[0]), isr_steps(1.0))
    np.testing.assert_array_equal(edges(g[1]), slow_steps(1.0))
    np.testing.assert_array_equal(g[2], micros_gate(1.0))
    pwm = dict(speed_rpm=1000.0, duration=0.005, dt=DT, converter=IDEAL)
    a = run(cache, "pwm_fixed", analytic_motor(), "c", **pwm).traces
    b = run(cache, "pwm_fixed", analytic_motor(), "c", controller_clock=1.0, **pwm).traces
    for k in a:
        np.testing.assert_array_equal(a[k], b[k], err_msg=k)


def test_fast_clock_scales_isr_slow_and_micros(cache):
    g1 = probe(cache, "c").traces["gate_u"]
    g = probe(cache, "c", controller_clock=R).traces["gate_u"]
    isr = edges(g[0])
    np.testing.assert_array_equal(isr, isr_steps(R))
    n1 = len(edges(g1[0]))
    assert abs(len(isr) / n1 - R) < 1.0 / n1
    np.testing.assert_array_equal(edges(g[1]), slow_steps(R))
    np.testing.assert_array_equal(g[2], micros_gate(R))
    m1, m = edges(g1[2]), edges(g[2])
    assert np.mean(np.diff(m1)) / np.mean(np.diff(m)) == pytest.approx(R, rel=1e-3)


def test_hal_constants_stay_nominal(cache):
    g = probe(cache, "c", controller_clock=R).traces["gate_u"][3]
    first = isr_steps(R)[0]
    assert g[first:].all() and not g[:first].any()


def test_fast_clock_scales_pwm_carrier(cache):
    tr = run(cache, "pwm_fixed", analytic_motor(), "c", speed_rpm=1000.0, duration=0.005, dt=DT, converter=IDEAL,
             controller_clock=R).traces
    u = tr["gate_u"][0].astype(int)
    rise = (np.flatnonzero(np.diff(u) > 0) + 1)[1:]     # the first pulse starts mid-carrier, when the command lands
    fall = np.flatnonzero(np.diff(u) < 0) + 1
    period = 1.0 / (ISR_HZ * R) / DT
    assert len(rise) > 50
    assert np.abs(np.diff(rise) - period).max() <= 1.0
    fall = fall[fall > rise[0]][: len(rise)]
    centres = (rise[: len(fall)] + fall) / 2      # the ISR sits at the carrier centre
    k = np.round(centres * DT * ISR_HZ * R - 0.5)
    assert np.abs(centres - (k + 0.5) / (ISR_HZ * R) / DT).max() <= 1.0


@pytest.mark.parametrize("r", [0.89, 1.11])
def test_clock_out_of_range_rejected(r):
    with pytest.raises(ValueError):
        Scenario(controller_clock=r)


def test_clock_range_and_true_time_rate_limit():
    Scenario(controller_clock=0.9)
    Scenario(controller_clock=1.1)
    Scenario(dt=DT, pwm_hz=1 / DT)
    with pytest.raises(ValueError, match="1 / dt"):
        Scenario(dt=DT, pwm_hz=1 / DT, controller_clock=1.05)
