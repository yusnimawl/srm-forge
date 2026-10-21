"""The Nucleo's TIM1/TIM8 compare values (hil/controller/pwm_compare.c) against the SIL converter's carrier rule.

The timers count 0..arr..0 in PWM mode 1 (output active while CNT < CCR) with the update at the underflow (CNT = 0),
where the SIL samples: the SIL carrier is 1 - CNT / arr. The arr + 1 counter values of half a period are compared
point by point with the SIL rule at carrier j / arr."""
import ctypes as C
import tempfile
from pathlib import Path

import numpy as np
import pytest
from sil_fixtures import run_in_child

from srmsil.build import compile_host

ROOT = Path(__file__).parents[2]
CTRL = ROOT / "hil" / "controller"
PLANT = ROOT / "src" / "srmsil" / "c" / "plant"
SIM = ROOT / "src" / "srmsil" / "c" / "sim"
SHIM = Path(__file__).parent / "c" / "pwm_shim.c"
CACHE = Path(tempfile.gettempdir()) / "srm_hil_pwm_tests"


def _lib():
    return compile_host([SHIM, CTRL / "pwm_compare.c", SIM / "srm_converter.c", PLANT / "srm_plant.c",
                         PLANT / "srm_motor.c"], [CTRL, PLANT, SIM], CACHE)


def _cases(lib, cases):
    d = C.CDLL(str(lib))
    d.shim_ahb_compare.argtypes = [C.c_float, C.c_int, C.c_uint16, C.c_void_p, C.c_void_p]
    d.shim_sil_states.argtypes = [C.c_double, C.c_int, C.c_int, C.c_void_p, C.c_void_p]
    out = []
    for duty, soft, arr in cases:
        u, lo = C.c_uint16(), C.c_uint16()
        d.shim_ahb_compare(duty, soft, arr, C.byref(u), C.byref(lo))
        su = np.zeros(arr + 1, np.uint8)
        sl = np.zeros(arr + 1, np.uint8)
        d.shim_sil_states(float(np.float32(duty)), soft, arr, su.ctypes.data, sl.ctypes.data)
        out.append((u.value, lo.value, su, sl))
    return out


def _timer_states(ccr, arr):
    """Output of PWM mode 1 at the SIL's points j = 0..arr (counter value arr - j)."""
    cnt = arr - np.arange(arr + 1)
    return (cnt < ccr).astype(np.uint8)


DUTIES = (0.0, 0.1, 0.5, 0.9, 1.0)


def test_ahb_compare_matches_sil_carrier():
    cases = [(d, soft, arr) for d in DUTIES for soft in (0, 1) for arr in (5000, 4999, 1000)]
    for (duty, soft, arr), (u, lo, su, sl) in zip(cases, run_in_child(_cases, _lib(), cases)):
        tu, tl = _timer_states(u, arr), _timer_states(lo, arr)
        assert u <= arr + 1 and lo <= arr + 1
        assert abs(int(tu.sum()) - int(su.sum())) <= 1, (duty, soft, arr)
        assert int(np.count_nonzero(tu != su)) <= 1, (duty, soft, arr)
        assert int(np.count_nonzero(tl != sl)) <= 1, (duty, soft, arr)
        if soft:
            assert lo == arr + 1
        else:
            assert lo == u


@pytest.mark.parametrize("duty", [-0.5, 1.5, float("nan"), float("inf"), float("-inf")])
def test_ahb_compare_clips(duty):
    arr = 5000
    (u, lo, su, sl), = run_in_child(_cases, _lib(), [(duty, 0, arr)])
    want = arr + 1 if duty == duty and duty >= 1.0 else 0     # NaN is off, as the SIL rule
    assert u == want and lo == want
    assert int(_timer_states(u, arr).sum()) == int(su.sum())


def test_ahb_compare_random_duties():
    rng = np.random.default_rng(3)
    cases = [(float(d), int(s), int(a)) for d, s, a in zip(rng.uniform(0, 1, 200), rng.integers(0, 2, 200),
                                                         rng.integers(100, 65534, 200))]
    for (duty, soft, arr), (u, lo, su, sl) in zip(cases, run_in_child(_cases, _lib(), cases)):
        assert int(np.count_nonzero(_timer_states(u, arr) != su)) <= 1, (duty, arr)
        assert int(np.count_nonzero(_timer_states(lo, arr) != sl)) <= 1, (duty, arr)
