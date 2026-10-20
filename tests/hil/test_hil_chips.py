import ctypes as C
import math
import random
import subprocess
import tempfile
from pathlib import Path

from sil_fixtures import run_in_child

from srmsil.build import compile_host, zig_cc

COMMON = Path(__file__).parents[2] / "hil" / "common"
CACHE = Path(tempfile.gettempdir()) / "srm_hil_chips_tests"
TWO_PI = 2 * math.pi


def _checks(lib):
    d = C.CDLL(str(lib))
    d.ad7606_code.restype = C.c_int16
    d.ad7606_code.argtypes = [C.c_double, C.c_double]
    d.ad7606_to_unsigned.restype = C.c_uint16
    d.ad7606_to_unsigned.argtypes = [C.c_int16]
    d.ad2s1210_position.restype = C.c_uint16
    d.ad2s1210_position.argtypes = [C.c_double, C.c_int]
    d.ad2s1210_angle.restype = C.c_double
    d.ad2s1210_angle.argtypes = [C.c_uint16, C.c_int]
    d.ad2s1210_velocity.restype = C.c_int16
    d.ad2s1210_velocity.argtypes = [C.c_double, C.c_int, C.c_double]
    d.mcp492x_word.restype = C.c_uint16
    d.mcp492x_word.argtypes = [C.c_int, C.c_uint16]
    d.dac_code.restype = C.c_uint16
    d.dac_code.argtypes = [C.c_double] * 4
    out = {}
    out["adc"] = [d.ad7606_code(v, 10.0) for v in (10.0, -10.0, 0.0, 99.0, -99.0, 10.0 / 32768, 0.5 * 10.0 / 32768, -0.5 * 10.0 / 32768)]
    out["adc5"] = d.ad7606_code(2.5, 5.0)
    out["uns"] = [d.ad7606_to_unsigned(c) for c in (-32768, 0, 32767)]
    out["pos"] = [d.ad2s1210_position(a, 12) for a in (math.pi, math.pi / 2, 0.0, -math.pi / 2, TWO_PI, TWO_PI - 1e-9)]
    rnd = random.Random(1)
    errs = {}
    for bits in (10, 12, 14, 16):
        worst = 0.0
        for _ in range(1000):
            a = rnd.uniform(-20, 20)
            back = d.ad2s1210_angle(d.ad2s1210_position(a, bits), bits)
            diff = abs((back - a + math.pi) % TWO_PI - math.pi)
            worst = max(worst, diff / (TWO_PI / 2**bits))
        errs[bits] = worst
    out["errs"] = errs
    out["low_bits"] = d.ad2s1210_position(math.pi, 10) & 0x3F
    out["vel"] = [d.ad2s1210_velocity(r, 12, 1000.0) for r in (0.0, TWO_PI * 500, -TWO_PI * 1000, TWO_PI * 5000, -TWO_PI * 5000)]
    out["mcp"] = [d.mcp492x_word(1, 0xABC), d.mcp492x_word(0, 0xABC), d.mcp492x_word(0, 0x1FFF)]
    out["dac"] = [d.dac_code(-1e3, 1.65, 0.1, 3.3), d.dac_code(1e3, 1.65, 0.1, 3.3), d.dac_code(0, 1.65, 0.1, 3.3)]
    return out


def test_chip_coding():
    o = run_in_child(_checks, compile_host([COMMON / "hil_chips.c"], [COMMON], CACHE))
    assert o["adc"] == [32767, -32768, 0, 32767, -32768, 1, 1, -1]
    assert o["adc5"] == 16384
    assert o["uns"] == [0, 32768, 65535]
    assert o["pos"] == [0x8000, 0x4000, 0, 0xC000, 0, 0]
    assert all(e <= 0.5 + 1e-9 for e in o["errs"].values()), o["errs"]
    assert o["low_bits"] == 0
    assert o["vel"] == [0, 16384, -32768, 32752, -32768]
    assert o["mcp"] == [0xBABC, 0x3ABC, 0x3FFF]
    assert o["dac"] == [0, 4095, 2048]


def test_chips_compile_strict(tmp_path):
    r = subprocess.run([*zig_cc(), "-std=c99", "-Wall", "-Wextra", "-Werror", f"-I{COMMON}", "-c",
                        "-o", str(tmp_path / "c.o"), str(COMMON / "hil_chips.c")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
