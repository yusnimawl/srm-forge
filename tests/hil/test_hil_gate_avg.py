import ctypes as C
import tempfile
from pathlib import Path

import numpy as np
import pytest
from sil_fixtures import analytic_motor, run_in_child

from srmsil.build import compile_host
from srmsil.run import run
from srmsil.scenario import ConverterSettings, Scenario

ROOT = Path(__file__).parents[2]
PLANT = ROOT / "src" / "srmsil" / "c" / "plant"
SHIM = Path(__file__).parent / "c" / "gate_avg_shim.c"
CTRL = ROOT / "tests" / "sil" / "controllers"
CACHE = Path(tempfile.gettempdir()) / "srm_gate_avg_tests"


def upper(k):
    return 1 << k


def lower(k):
    return 1 << (8 + k)


def _lib():
    return compile_host([SHIM, PLANT / "srm_gate_avg.c", PLANT / "srm_plant.c", PLANT / "srm_motor.c"],
                        [PLANT], CACHE)


def _windows(lib, q, bus, vs, vd, rise, fall, initial, edges, n_windows, dt, current):
    """Per-window (v, on_upper, on_lower), each n_windows x q; runs in a child process."""
    dll = C.CDLL(str(lib))
    dll.gate_avg_windows.restype = C.c_int
    dll.gate_avg_windows.argtypes = [C.c_int, C.c_double, C.c_double, C.c_double, C.c_int64, C.c_int64, C.c_uint16,
                                     C.c_int, C.c_void_p, C.c_void_p, C.c_int, C.c_uint64, C.c_void_p, C.c_void_p,
                                     C.c_void_p, C.c_void_p]
    et = np.array([e[0] for e in edges] or [0], np.uint64)
    eg = np.array([e[1] for e in edges] or [0], np.uint16)
    cur = np.ascontiguousarray(np.broadcast_to(np.asarray(current, np.float64), (n_windows, q)))
    v = np.zeros((n_windows, q))
    ou = np.zeros((n_windows, q), np.float32)
    ol = np.zeros((n_windows, q), np.float32)
    rc = dll.gate_avg_windows(q, bus, vs, vd, rise, fall, initial, len(edges), et.ctypes.data, eg.ctypes.data,
                              n_windows, dt, cur.ctypes.data, v.ctypes.data, ou.ctypes.data, ol.ctypes.data)
    assert rc == 0
    return v, ou, ol


def windows(q, edges, n_windows, dt, current, rise=0, fall=0, initial=0, bus=48.0, vs=0.0, vd=0.0):
    return run_in_child(_windows, _lib(), q, bus, vs, vd, rise, fall, initial, edges, n_windows, dt, current)


def test_single_window_exact():
    # 10 ticks of 0.5 us: on at 1.0 us (tick 2), off at 3.5 us (tick 7)
    v, ou, ol = windows(1, [(2, upper(0) | lower(0)), (7, 0)], 1, 10, [1e-3])
    assert ou[0, 0] == 0.5 and ol[0, 0] == 0.5
    assert abs(v[0, 0]) < 1e-12


def test_several_edges_and_boundary():
    # window 0 = ticks [0, 16): upper on 3..4 and 9..11, lower on 9..11; the edge at 16 belongs to window 1
    edges = [(3, upper(0)), (5, 0), (9, upper(0) | lower(0)), (12, 0), (16, upper(0) | lower(0))]
    vs, vd = 1.0, 0.7
    v, ou, ol = windows(1, edges, 2, 16, [1e-3], bus=48.0, vs=vs, vd=vd)
    assert abs(ou[0, 0] - 5 / 16) < 1e-12 and abs(ol[0, 0] - 3 / 16) < 1e-12
    assert abs(ou[1, 0] - 1.0) < 1e-12 and abs(ol[1, 0] - 1.0) < 1e-12
    both, one, none = 48.0 - 2 * vs, -(vs + vd), -(48.0 + 2 * vd)
    want = (2 * one + 3 * both + (16 - 2 - 3) * none) / 16
    assert abs(v[0, 0] - want) < 1e-12
    assert abs(v[1, 0] - both) < 1e-12


def test_short_pulse_swallowed():
    # tick = 0.1 us, rise delay 0.6 us = 6 ticks
    _, ou, _ = windows(1, [(10, upper(0)), (15, 0)], 4, 10, [1.0], rise=6)       # 0.5 us pulse
    assert np.all(ou == 0)
    _, ou, _ = windows(1, [(10, upper(0)), (17, 0)], 4, 10, [1.0], rise=6)       # 0.7 us pulse: 0.1 us on
    assert abs(ou[1, 0] - 0.1) < 1e-6 and abs(ou.sum() - 0.1) < 1e-6
    _, ou, _ = windows(1, [(10, upper(0)), (16, 0)], 4, 10, [1.0], rise=6)       # exactly the delay: swallowed
    assert np.all(ou == 0)


def test_pending_change_matures_in_later_window():
    # tick 0.1 us windows of 10 ticks; on at tick 15 with a 6-tick rise: the switch turns on at tick 21
    _, ou, _ = windows(1, [(15, upper(0))], 4, 10, [1.0], rise=6)
    assert list(ou[:, 0]) == pytest.approx([0.0, 0.0, 0.9, 1.0])


def test_fall_delay_and_reon_keeps_switch_on():
    # off at tick 12 with a 3-tick fall delay, back on at tick 14: the switch never turns off
    _, ou, _ = windows(1, [(12, 0), (14, upper(0))], 3, 10, [1.0], fall=3, initial=upper(0))
    assert np.all(ou == 1.0)
    # without the re-on it turns off at tick 15
    _, ou, _ = windows(1, [(12, 0)], 3, 10, [1.0], fall=3, initial=upper(0))
    assert list(ou[:, 0]) == pytest.approx([1.0, 0.5, 0.0])


def test_flux_stops_at_zero_inside_a_window():
    # 10 ticks of 0.5 us, flux 1e-6 Wb: both off for 4 ticks (2 us) at 48 V, then both on for 3 us
    both_on = upper(0) | lower(0)
    v, ou, _ = windows(1, [(4, both_on)], 1, 10, [1e-6], vs=0.0, vd=0.0)
    assert abs(1e-6 + v[0, 0] * 5e-6 - 48.0 * 3e-6) < 1e-15
    assert abs(ou[0, 0] - 0.6) < 1e-6


def test_zero_current_both_off():
    v, _, _ = windows(2, [], 3, 10, [0.0, 0.0])
    assert np.all(v == 0.0)


def _plant_off(lib):
    dll = C.CDLL(str(lib))
    out = (C.c_double * 4)()
    dll.gate_avg_plant_off.argtypes = [C.c_double, C.c_double, C.c_int, C.c_void_p]
    dll.gate_avg_plant_off(0.05, 5e-3, 4000, C.cast(out, C.c_void_p))
    return list(out)


def test_zero_current_plant_stays_nonnegative():
    min_psi, min_i, psi, i = run_in_child(_plant_off, _lib())
    assert min_psi >= 0.0 and min_i >= 0.0
    assert psi == 0.0 and i == 0.0


def _gate_words(r):
    gu, gl = r.traces["gate_u"].astype(np.uint16), r.traces["gate_l"].astype(np.uint16)
    k = np.arange(gu.shape[0], dtype=np.uint16)[:, None]
    return ((gu << k).sum(axis=0) | (gl << (8 + k)).sum(axis=0)).astype(np.uint16)


def test_matches_sil_converter(tmp_path):
    motor = analytic_motor()
    ctrl = str(CTRL / "pwm_fixed")
    q = motor.n_phases
    zero = ConverterSettings(dead_time=0.0, turn_on_delay=0.0, turn_off_delay=0.0)
    cmd = run(motor, ctrl, Scenario(speed_rpm=1000.0, duration=0.005, converter=zero), cache_dir=tmp_path)
    conv = ConverterSettings()
    real = run(motor, ctrl, Scenario(speed_rpm=1000.0, duration=0.005, converter=conv), cache_dir=tmp_path)
    words = _gate_words(cmd)
    ticks = np.flatnonzero(np.diff(np.concatenate([[0], words.astype(np.int32)])) != 0)
    edges = [(int(n), int(words[n])) for n in ticks]
    assert len(edges) > 20
    tick = 0.5e-6
    rise, fall = round((conv.dead_time + conv.turn_on_delay) / tick), round(conv.turn_off_delay / tick)
    w = 10
    nw = words.size // w
    v, _, _ = windows(q, edges, nw, w, np.ones(q), rise=rise, fall=fall, bus=48.0, vs=conv.v_switch, vd=conv.v_diode)
    sil_v = real.traces["v"][:, : nw * w].reshape(q, nw, w).astype(np.float64)
    sil_i = real.traces["i"][:, : nw * w].reshape(q, nw, w)
    ok = np.all(sil_i > 0, axis=2).T
    assert ok[:, 0].sum() > 50
    diff = np.abs(v - sil_v.mean(axis=2).T)[ok]
    assert diff.max() <= 1e-6 * 48.0, diff.max()      # the SIL trace is float32


def _lib_general():
    return compile_host([SHIM, PLANT / "srm_gate_avg.c", PLANT / "srm_plant.c", PLANT / "srm_motor.c"],
                        [PLANT], CACHE, defines=("SRM_GATE_AVG_NO_FAST_PATH",))


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_fast_path_identical_to_general_walk(seed):
    """Windows with no edge and no pending change take a fused path; random edge streams with delays, idle windows,
    zero and positive fluxes and switch drops give bit-identical outputs with and without it."""
    rng = np.random.default_rng(seed)
    q, dt, n_w = 4, 10, 400
    t = np.sort(rng.choice(n_w * dt, 300, replace=False))
    t = t[(t // dt) % 3 != 0]                       # every third window has no edges
    words = rng.integers(0, 16, len(t)) | (rng.integers(0, 16, len(t)) << 8)
    edges = list(zip(t.tolist(), words.tolist()))
    psi0 = np.where(rng.random((n_w, q)) < 0.4, 0.0, rng.random((n_w, q)) * 1e-4)
    args = (q, 48.0, 1.0, 0.8, 3, 2, 0x0101, edges, n_w, dt, psi0)
    fast = run_in_child(_windows, _lib(), *args)
    slow = run_in_child(_windows, _lib_general(), *args)
    for a, b in zip(fast, slow):
        assert a.tobytes() == b.tobytes()
