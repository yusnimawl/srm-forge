import ctypes as C
import math
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


def _windows_at(lib, q, bus, vs, vd, rise, fall, initial, edges, t0s, firsts, dt, psi0, without_fractions):
    dll = C.CDLL(str(lib))
    dll.gate_avg_windows_at.restype = C.c_int
    dll.gate_avg_windows_at.argtypes = [C.c_int, C.c_double, C.c_double, C.c_double, C.c_int64, C.c_int64,
                                        C.c_uint16, C.c_int, C.c_void_p, C.c_void_p, C.c_int, C.c_void_p, C.c_void_p,
                                        C.c_uint64, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_int]
    et = np.array([e[0] for e in edges] or [0], np.uint64)
    eg = np.array([e[1] for e in edges] or [0], np.uint16)
    t0a = np.array(t0s, np.uint64)
    fa = np.array(firsts, np.int32)
    p0 = np.ascontiguousarray(psi0, np.float64)
    nw = len(t0s)
    v = np.zeros((nw, q))
    ou = np.zeros((nw, q), np.float32)
    ol = np.zeros((nw, q), np.float32)
    rc = dll.gate_avg_windows_at(q, bus, vs, vd, rise, fall, initial, len(edges), et.ctypes.data, eg.ctypes.data,
                                 nw, t0a.ctypes.data, fa.ctypes.data, dt, p0.ctypes.data, v.ctypes.data,
                                 ou.ctypes.data, ol.ctypes.data, int(without_fractions))
    assert rc == 0
    return v, ou, ol


def _reference(q, bus, vs, vd, rise, fall, initial, edges, t0s, firsts, dt, psi0):
    """The averager as one walk over every edge and maturing change in time order, every winding advanced at every
    segment; events before a window's start take effect at its start (all edges up to it first when an edge is the
    earliest)."""
    tick = 0.5e-6
    v_on, v_free, v_demag = bus - 2 * vs, -(vs + vd), -(bus + 2 * vd)
    cmd = eff = initial
    pend = {}
    vs_out, ou_out, ol_out = [], [], []
    for w, t0 in enumerate(t0s):
        ed = edges[firsts[w]:firsts[w + 1]]
        t1, now, e = t0 + dt, t0, 0
        psi = list(psi0[w])
        ou, ol = [0.0] * q, [0.0] * q

        def accumulate(span):
            tau = span * tick
            for k in range(q):
                u, lo = (eff >> k) & 1, (eff >> (8 + k)) & 1
                if not u and not lo and not psi[k] > 0:
                    continue
                v = v_on if u and lo else (v_free if psi[k] > 0 else 0.0) if u or lo else (v_demag if psi[k] > 0 else 0.0)
                psi[k] = psi[k] + v * tau if v >= 0 or psi[k] > -v * tau else 0.0
                ou[k] += u * span
                ol[k] += lo * span

        while True:
            te = ed[e][0] if e < len(ed) else math.inf
            tp = min(pend.values(), default=math.inf)
            ts = min(te, tp)
            if ts >= t1:
                break
            ts = max(ts, now)
            if ts > now:
                accumulate(ts - now)
            now = ts
            if te <= tp:
                while e < len(ed) and ed[e][0] <= ts:
                    word = ed[e][1]
                    for s in range(16):
                        bit = 1 << s
                        if not (word ^ cmd) & bit:
                            continue
                        if not (word ^ eff) & bit:
                            pend.pop(s, None)
                        else:
                            pend[s] = ts + (rise if word & bit else fall)
                    cmd = word
                    e += 1
            for s, t in list(pend.items()):
                if t <= ts:
                    eff = (eff & ~(1 << s)) | (cmd & (1 << s))
                    del pend[s]
        if t1 > now:
            accumulate(t1 - now)
        vs_out.append([(psi[k] - psi0[w][k]) / (dt * tick) for k in range(q)])
        ou_out.append([x / dt for x in ou])
        ol_out.append([x / dt for x in ol])
    return np.array(vs_out), np.array(ou_out, np.float32), np.array(ol_out, np.float32)


@pytest.mark.parametrize("seed", [4, 5, 6, 7])
def test_matches_reference_walk(seed):
    """The averager equals a plain event walk (rounding of the order of 1e-12), with late edges, gaps between windows,
    long delays, windows of more than 16 segments, and with the fractions left out."""
    rng = np.random.default_rng(seed)
    q, dt, n_w = 4, (10, 16, 40, 40)[seed - 4], 150
    gap, lag = int(rng.integers(0, 2)) * int(rng.integers(1, dt)), int(rng.integers(0, dt))
    t0s = [w * (dt + gap) for w in range(n_w)]
    span_end = t0s[-1] + dt
    n_e = int(rng.integers(n_w, n_w * (dt // 2)))
    t = np.sort(rng.choice(span_end, min(n_e, span_end), replace=False))
    t = t[t < span_end]
    words = rng.integers(0, 16, len(t)) | (rng.integers(0, 16, len(t)) << 8)
    edges = [(int(a), int(b)) for a, b in zip(t, words)]
    # window w takes the edges before its end less lag: those after are late edges of the next window
    firsts = [0]
    for w in range(n_w):
        lim = t0s[w] + dt - (lag if w < n_w - 1 else 0)
        firsts.append(int(np.searchsorted(t, lim)))
    psi0 = np.where(rng.random((n_w, q)) < 0.3, 0.0, rng.random((n_w, q)) * 1e-4)
    rise, fall = int(rng.integers(0, 3 * dt)), int(rng.integers(0, 3 * dt))
    args = (q, 48.0, 1.0, 0.8, rise, fall, 0x0103, edges, t0s, firsts, dt, psi0)
    v, ou, ol = run_in_child(_windows_at, _lib(), *args, False)
    rv, rou, rol = _reference(*args)
    assert np.array_equal(ou, rou) and np.array_equal(ol, rol)
    assert np.max(np.abs(v - rv)) <= 1e-9 * 48.0
    v2, _, _ = run_in_child(_windows_at, _lib(), *args, True)
    assert v2.tobytes() == v.tobytes()
