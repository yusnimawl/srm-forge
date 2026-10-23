"""Host tests of the emulator's portable step bookkeeping (hil/emulator/edge_ring.c)."""
import ctypes as C
import tempfile
from pathlib import Path

from sil_fixtures import run_in_child

from srmsil.build import compile_host

ROOT = Path(__file__).parents[2]
EMU = ROOT / "hil" / "emulator"
PLANT = ROOT / "src" / "srmsil" / "c" / "plant"
SHIM = Path(__file__).parent / "c" / "emu_ring_shim.c"
CACHE = Path(tempfile.gettempdir()) / "srm_emu_ring_tests"
P = 3000                 # cycles per window, a test value (the ring does not depend on the step)
LATE = 1200              # 2 us


def _lib():
    return compile_host([SHIM, EMU / "edge_ring.c"], [EMU, PLANT], CACHE)


def _bind(lib):
    d = C.CDLL(str(lib))
    d.shim_push.argtypes = [C.c_uint32, C.c_uint16]
    d.shim_extend.restype = C.c_uint64
    d.shim_extend.argtypes = [C.c_uint64, C.c_uint32]
    d.shim_gate_word.restype = C.c_uint16
    d.shim_gate_word.argtypes = [C.c_uint32]
    d.shim_overflows.restype = C.c_uint32
    d.shim_take.argtypes = [C.c_uint64, C.c_uint64, C.c_void_p, C.c_void_p, C.c_int]
    d.shim_pattern_init.argtypes = [C.c_uint64, C.c_uint64, C.c_uint64, C.c_uint16]
    d.shim_pattern_feed.argtypes = [C.c_uint64]
    return d


def _take(d, now64, t1, cap=64):
    t, g = (C.c_uint64 * 64)(), (C.c_uint16 * 64)()
    n = d.shim_take(now64, t1, t, g, cap)
    return [(t[i], g[i]) for i in range(n)]


def _scenarios(lib):
    d = _bind(lib)
    out = {}
    # 64-bit extension across the 32-bit wrap
    out["extend"] = [d.shim_extend(0xFFFF_F000, 0x0000_0100), d.shim_extend((5 << 32) + 10, 3000),
                     d.shim_extend(2**32 - 1, 0xFFFF_FFFF)]
    # windows across the wrap: window n = [base + n P, base + (n + 1) P), each taken LATE cycles after it ends
    base = 2**32 - 2 * P + 7
    stamps = [base + 5, base + P - 1, base + P, base + 2 * P - 1, base + 2 * P, base + 2 * P + LATE - 1]
    d.shim_reset()
    windows = []
    pushed = 0
    for n in range(3):
        t1 = base + (n + 1) * P
        now = t1 + LATE
        while pushed < len(stamps) and stamps[pushed] < now:   # the gate interrupt stamps edges up to the ISR start
            d.shim_push(stamps[pushed] & 0xFFFF_FFFF, pushed + 1)
            pushed += 1
        windows.append(_take(d, now, t1))
    out["windows"], out["base"] = windows, base
    # an edge stamped just after the step interrupt read the counter stays for the next window (across the wrap)
    d.shim_reset()
    now = 2**32 + 50
    d.shim_push((now - 100) & 0xFFFF_FFFF, 1)
    d.shim_push((now + 10) & 0xFFFF_FFFF, 2)
    out["after_now"] = [_take(d, now, now - 20), _take(d, now + P, now + P - 20)]
    # a window with more edges than the caller's buffer: the rest stays for the next call
    d.shim_reset()
    for k in range(5):
        d.shim_push(100 + k, k)
    out["partial"] = [_take(d, 200, 150, 3), _take(d, 200, 150, 3)]
    # overflow of the ring is counted and refused
    d.shim_reset()
    rc = [d.shim_push(k, 1) for k in range(300)]
    out["overflow"] = (rc.count(0), rc.count(-1), d.shim_overflows())
    # gate word from GPIO6: pins 14..21 are bits 18, 19, 23, 22 (upper A..D) and 17, 16, 26, 27 (lower A..D)
    out["gates"] = [d.shim_gate_word(1 << b) for b in (18, 19, 23, 22, 17, 16, 26, 27)]
    out["gates_noise"] = d.shim_gate_word(~((1 << 18) | (1 << 19) | (1 << 23) | (1 << 22) | (1 << 17) | (1 << 16)
                                            | (1 << 26) | (1 << 27)) & 0xFFFF_FFFF)
    # software pattern: 20 kHz (30000 cycles), 50 %, first rise 1000 cycles after a start near the wrap
    d.shim_reset()
    start = 2**32 - 40_000
    d.shim_pattern_init(start + 1000, 30_000, 15_000, 0x0101)
    fed = []
    for n in range(25):
        t1 = start + (n + 1) * P
        d.shim_pattern_feed(t1)
        fed += _take(d, t1 + LATE, t1)
    out["pattern"], out["pattern_start"] = fed, start
    return out


def test_emu_ring_bookkeeping():
    r = run_in_child(_scenarios, _lib())
    assert r["extend"] == [0x1_0000_0100, (5 << 32) + 3000, 2**32 - 1]
    b = r["base"]
    w = r["windows"]
    assert w[0] == [(b + 5, 1), (b + P - 1, 2)]
    assert w[1] == [(b + P, 3), (b + 2 * P - 1, 4)]       # the edges stamped in the late time of window 0 move here
    assert w[2] == [(b + 2 * P, 5), (b + 2 * P + LATE - 1, 6)]
    assert r["after_now"] == [[(2**32 - 50, 1)], [(2**32 + 60, 2)]]
    assert r["partial"] == [[(100, 0), (101, 1), (102, 2)], [(103, 3), (104, 4)]]
    assert r["overflow"][1] > 0 and r["overflow"][2] == r["overflow"][1] and r["overflow"][0] + r["overflow"][1] == 300
    assert r["gates"] == [1, 2, 4, 8, 0x100, 0x200, 0x400, 0x800]
    assert r["gates_noise"] == 0
    s = r["pattern_start"]
    want = []
    for m in range(3):
        want += [(s + 1000 + m * 30_000, 0x0101), (s + 1000 + m * 30_000 + 15_000, 0)]
    assert r["pattern"] == [e for e in want if e[0] < s + 25 * P]
