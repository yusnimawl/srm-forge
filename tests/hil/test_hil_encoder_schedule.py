"""Host tests of the emulator's encoder edge schedule (hil/emulator/enc_sched.c) and the encoder rate check."""
import ctypes as C
import math
import subprocess
import tempfile
from pathlib import Path

import pytest
from sil_fixtures import run_in_child

from srmsil.build import compile_host, zig_cc
from srmsil.hil.config import check_encoder_rate

EMU = Path(__file__).parents[2] / "hil" / "emulator"
CACHE = Path(tempfile.gettempdir()) / "srm_hil_enc_tests"
CPR = 1000
DT = 5e-6
GRAY = [(0, 0), (1, 0), (1, 1), (0, 1)]        # (A, B) of count n mod 4: A leads while the count rises


def _lib():
    return compile_host([EMU / "enc_sched.c"], [EMU], CACHE)


def _run(lib, rpm, n_windows, theta0=0.3, cpr=CPR, offset=0.0, ecc=0.0, harm=0, cap=64):
    d = C.CDLL(str(lib))
    d.enc_edges.restype = C.c_int
    d.enc_edges.argtypes = [C.c_double, C.c_double, C.c_uint32, C.c_double, C.c_double, C.c_int, C.c_double,
                            C.c_double, C.c_void_p, C.c_void_p, C.c_int]
    w = rpm * 2 * math.pi / 60
    t = (C.c_double * cap)()
    s = (C.c_uint8 * cap)()
    out = []
    for k in range(n_windows):
        th0, th1 = theta0 + w * k * DT, theta0 + w * (k + 1) * DT
        n = d.enc_edges(th0, th1, cpr, offset, ecc, harm, k * DT, DT, t, s, cap)
        out.append((th0, th1, n, [t[j] for j in range(max(n, 0))], [s[j] for j in range(max(n, 0))]))
    return out


def _count(theta, cpr=CPR):
    return math.floor(theta / (2 * math.pi) * cpr)


def _check_quadrature(windows, direction):
    times, states = [], []
    for th0, th1, n, t, s in windows:
        assert n == abs(_count(th1) - _count(th0))
        times += t
        states += s
    assert times == sorted(times)
    count = _count(windows[0][0])
    for st in states:
        count += direction
        a, b = GRAY[count % 4]
        assert (st & 1, (st >> 1) & 1) == (a, b)
        assert bool(st & 4) == (count % CPR == 0)
    return len(states)


def test_encoder_edges_constant_speed():
    windows = run_in_child(_run, _lib(), 1000.0, 40_000)       # 0.2 s, 3.3 rev: crosses count 0 several times
    lo = [w[2] for w in windows]
    for (th0, th1, n, t, _), k in zip(windows, range(len(windows))):
        assert all(k * DT <= x <= (k + 1) * DT for x in t)
    assert max(lo) <= 1 and min(lo) >= 0
    n = _check_quadrature(windows, +1)
    assert n == _count(windows[-1][1]) - _count(windows[0][0])


def test_encoder_reverse():
    windows = run_in_child(_run, _lib(), -1000.0, 40_000, 10.0)
    assert _check_quadrature(windows, -1) > 3000


def _one(lib):
    d = C.CDLL(str(lib))
    d.enc_edges.argtypes = [C.c_double, C.c_double, C.c_uint32, C.c_double, C.c_double, C.c_int, C.c_double,
                            C.c_double, C.c_void_p, C.c_void_p, C.c_int]
    step = 2 * math.pi / CPR
    res = []
    for th0, th1, t0, cap in ((0.5, 2.5, 1.0, 4), (0.5, 2.5, 1.0, 1), (2.5, 0.5, 0.0, 4)):
        t, s = (C.c_double * 4)(), (C.c_uint8 * 4)()
        n = d.enc_edges(th0 * step, th1 * step, CPR, 0.0, 0.0, 0, t0, 2.0, t, s, cap)
        res.append((n, list(t)[:max(n, 0)], list(s)[:max(n, 0)]))
    return res


def test_encoder_edge_times_interpolate():
    # a window spanning two counts from mid-count: edges at a quarter and three quarters of the window
    fwd, small, back = run_in_child(_one, _lib())
    assert fwd[0] == 2 and fwd[1] == pytest.approx([1.5, 2.5]) and fwd[2] == [0b001, 0b011]
    assert small[0] == -1
    assert back[0] == 2 and back[1] == pytest.approx([0.5, 1.5]) and back[2] == [0b001, 0b100]   # Z at count 0


def test_encoder_offset_and_eccentricity():
    # an offset of a whole count shifts every crossing by one count; eccentricity keeps the count consistent
    windows = run_in_child(_run, _lib(), 1000.0, 4000, 0.3, CPR, 2 * math.pi / CPR, 0.002, 2)
    total = sum(w[2] for w in windows)
    meas = lambda th: th + 2 * math.pi / CPR + 0.002 * math.sin(2 * th)   # noqa: E731
    assert total == _count(meas(windows[-1][1])) - _count(meas(windows[0][0]))


def test_enc_sched_compiles_strict(tmp_path):
    r = subprocess.run([*zig_cc(), "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wdouble-promotion", f"-I{EMU}",
                        "-c", "-o", str(tmp_path / "e.o"), str(EMU / "enc_sched.c")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_encoder_rate_limit():
    check_encoder_rate(1000, 24000.0)           # 1000 * 400 rev/s = 400 000 edges/s, the limit
    check_encoder_rate(1000, -24000.0)
    with pytest.raises(ValueError, match="400"):
        check_encoder_rate(1000, 24001.0)
    with pytest.raises(ValueError):
        check_encoder_rate(4096, -6000.0)


def _decisions(lib):
    d = C.CDLL(str(lib))
    d.enc_edge_due.argtypes = [C.c_uint32, C.c_uint32]
    d.enc_compare_missed.argtypes = [C.c_uint32, C.c_uint32, C.c_uint32]
    w = 2**32
    due = [d.enc_edge_due(t % w, n % w) for t, n in ((100, 99), (100, 100), (100, 101), (w - 10, 5), (5, w - 10))]
    missed = [d.enc_compare_missed(due % w, now % w, 120)
              for due, now in ((1000, 1120), (1000, 1121), (w - 50, 100), (w - 50, 40), (1000, 900))]
    d.enc_next_action.argtypes = [C.c_uint32] * 3
    action = [d.enc_next_action(t % w, last % w, 48) for t, last in ((100, 100), (90, 100), (148, 100), (149, 100),
                                                                     (20, w - 30), (17, w - 30), (w - 40, 10))]
    return due, missed, action


def test_encoder_compare_decisions_wrap():
    due, missed, action = run_in_child(_decisions, _lib())
    # an edge is due at or after its tick, across the 32-bit wrap; a compare is missed only when a step overdue
    assert due == [0, 1, 1, 1, 0]
    assert missed == [0, 1, 1, 0, 0]
    # 0 put now, 1 program the compare (more than 48 ticks ahead of the fired compare), 2 read the counter first
    assert action == [0, 0, 2, 1, 1, 2, 0]
