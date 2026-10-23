"""SensorSettings.delay_jitter: each controller sample's sensed currents and voltages are delay + u * delay_jitter old,
u ~ U(0, 1) drawn per ISR sample from the run's seeded RNG."""

import numpy as np
import pytest
from sil_fixtures import analytic_motor
from test_sil_core import run

from srmsil.scenario import Scenario, SensorSettings

DT = 0.5e-6
D_STEPS, J_STEPS = 10, 12
# one ISR per step and a fine ADC on a current that rises with the rotor held (soft chop, no zero-current gaps), so
# each sample's code names the step it was taken from; pwm_fixed does not read the ADC, so every run has the same
# currents
KW = dict(speed_rpm=0.0, theta0=0.5, duration=0.004, dt=DT, isr_hz=1 / DT, adc={"bits": 16}, params={"soft": 1.0})


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    return tmp_path_factory.mktemp("hil_sil_jitter")


def adc(cache, **sensors):
    seed = sensors.pop("seed", 0)
    return run(cache, "pwm_fixed", analytic_motor(), "j", sensors=sensors, seed=seed, **KW).traces["adc_i"][0]


def test_zero_jitter_is_the_default(cache):
    base = run(cache, "pwm_fixed", analytic_motor(), "j", sensors={"delay": D_STEPS * DT}, **KW).traces
    zero = run(cache, "pwm_fixed", analytic_motor(), "j", sensors={"delay": D_STEPS * DT, "delay_jitter": 0.0},
               **KW).traces
    for k, a in base.items():
        np.testing.assert_array_equal(a, zero[k], err_msg=k)


def ages(ref, late, lo=-3, hi=J_STEPS + 4):
    """Per sample n, the extra ages e in [lo, hi) with late[n] == ref[n - e]; only samples with exactly one."""
    n0 = hi + 40
    got = []
    for n in range(n0, len(late) + lo):
        e = [k for k in range(lo, hi) if late[n] == ref[n - k]]
        if len(e) == 1:
            got.append(e[0])
    return np.array(got), len(late) + lo - n0


def test_jitter_spreads_the_sample_age(cache):
    ref = adc(cache, delay=D_STEPS * DT)
    late = adc(cache, delay=D_STEPS * DT, delay_jitter=J_STEPS * DT)
    assert len(np.unique(ref)) > 1000                  # the codes change from step to step
    e, n = ages(ref, late)
    assert len(e) > 0.5 * n
    assert e.min() == 0 and e.max() == J_STEPS       # ages within [delay, delay + jitter], both ends reached
    share = np.bincount(e, minlength=J_STEPS + 1) / len(e)
    # round((delay + u * jitter) / dt) - delay steps: 1/12 per inner step, 1/24 at the two ends
    assert np.all(share[1:-1] > 0.6 / J_STEPS) and np.all(share[1:-1] < 1.4 / J_STEPS)
    assert 0.3 / J_STEPS < share[0] < 0.7 / J_STEPS and 0.3 / J_STEPS < share[-1] < 0.7 / J_STEPS


def test_jitter_is_seeded(cache):
    a = adc(cache, delay=D_STEPS * DT, delay_jitter=J_STEPS * DT, seed=3)
    b = adc(cache, delay=D_STEPS * DT, delay_jitter=J_STEPS * DT, seed=3)
    c = adc(cache, delay=D_STEPS * DT, delay_jitter=J_STEPS * DT, seed=4)
    np.testing.assert_array_equal(a, b)
    assert np.any(a != c)


def test_jitter_without_delay(cache):
    ref = adc(cache)
    e, _ = ages(ref, adc(cache, delay_jitter=J_STEPS * DT))
    assert e.min() == 0 and e.max() == J_STEPS


def test_jitter_range():
    SensorSettings(delay_jitter=1e-4)
    with pytest.raises(ValueError):
        SensorSettings(delay_jitter=1.01e-4)
    with pytest.raises(ValueError):
        SensorSettings(delay_jitter=-1e-9)
    with pytest.raises(ValueError, match="jitter"):
        Scenario(dt=1e-8, sensors=SensorSettings(delay_jitter=1e-4))     # 10 000 steps of history
