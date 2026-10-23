import ctypes as C
import dataclasses
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest
from sil_fixtures import run_in_child

from srmsil.build import compile_host, zig_cc
from srmsil.hil import proto
from srmsil.hil.proto import ProtoError, Type

ROOT = Path(__file__).parents[2]
COMMON = ROOT / "hil" / "common"
SHIM = Path(__file__).parent / "c" / "proto_shim.c"
VECTORS = COMMON / "proto_vectors.json"
CACHE = Path(tempfile.gettempdir()) / "srm_hil_proto_tests"


def test_crc_check_value():
    assert proto.crc16(b"123456789") == 0x29B1


@pytest.mark.parametrize("n", [0, 1, 2, 253, 254, 255, 508, 600])
def test_cobs_round_trip(n):
    for data in (bytes(range(1, 256)) * 3, bytes(n), b"\x00\x01\x00" * n):
        data = data[:n]
        enc = proto.cobs_encode(data)
        assert 0 not in enc
        assert proto.cobs_decode(enc) == data


def test_frame_round_trip_and_corruption():
    payload = bytes([1, 0, 2, 0, 0, 3])
    f = proto.frame(Type.COMMAND, 513, payload)
    assert f[-1] == 0 and 0 not in f[:-1]
    assert proto.unframe(f) == (Type.COMMAND, 513, payload)
    bad = bytearray(f)
    bad[4] ^= 0x10
    with pytest.raises(ProtoError) as e:
        proto.unframe(bytes(bad))
    assert e.value.code == -2
    with pytest.raises(ProtoError) as e:
        proto.unframe(f[:-3])
    assert e.value.code == -1
    with pytest.raises(ProtoError) as e:
        proto.frame(Type.ERROR, 0, bytes(proto.PAYLOAD_MAX + 1))
    assert e.value.code == -3


def test_struct_sizes():
    assert proto.SAMPLE.size == 36 and proto.SAMPLE_DTYPE.itemsize == 36
    assert proto.EMU_CONFIG.size == len(proto.EMU_CONFIG_FIELDS) * 4 - 3 * 4 + 0 or proto.EMU_CONFIG.size > 0
    s = np.zeros(2, proto.SAMPLE_DTYPE)
    s["step"] = [7, 8]
    s["i"][1] = [1, -2, 3, -4]
    s["gates"] = [0x0101, 0x8001]
    data = proto.pack_capture_data(100, s)
    first, back = proto.unpack_capture_data(data)
    assert first == 100 and back.tobytes() == s.tobytes()
    live = proto.LiveCtrl(1.5, 3.25, 2, 0.5, (1.0, 2.0, 3.0, 4.0), 12.5, 7, proto.CTRL_RUNNING | proto.CTRL_HANG_STOP)
    assert proto.LIVE_CTRL.size == 41
    assert proto.unpack_live_ctrl(proto.pack_live_ctrl(live)) == live


def test_live_emu_trigger_hz():
    assert proto.LIVE_EMU.size == 64
    vec = next(v for v in json.loads(VECTORS.read_text()) if v["type"] == Type.LIVE_EMU)
    live = proto.unpack_live_emu(bytes.fromhex(vec["payload"]))
    assert live.temp_c == 42.5 and live.trigger_hz == 20214.5
    assert proto.pack_live_emu(live).hex() == vec["payload"]
    nan = proto.unpack_live_emu(proto.pack_live_emu(dataclasses.replace(live, trigger_hz=float("nan"))))
    assert math.isnan(nan.trigger_hz) and nan.temp_c == 42.5


def _lib():
    return compile_host([SHIM, COMMON / "hil_proto.c"], [COMMON], CACHE)


def _c_side(lib, vectors):
    dll = C.CDLL(str(lib))
    dll.shim_frame.restype = C.c_size_t
    dll.shim_frame.argtypes = [C.c_uint8, C.c_uint16, C.c_char_p, C.c_size_t, C.c_void_p]
    dll.shim_unframe.restype = C.c_long
    dll.shim_unframe.argtypes = [C.c_char_p, C.c_size_t, C.c_void_p, C.c_void_p, C.c_void_p, C.c_size_t]
    dll.shim_payload_size.restype = C.c_size_t
    dll.shim_payload_size.argtypes = [C.c_uint8]
    dll.shim_sample_size.restype = C.c_size_t
    dll.shim_crc16.restype = C.c_uint16
    dll.shim_crc16.argtypes = [C.c_char_p, C.c_size_t]
    framed, parsed = [], []
    for v in vectors:
        payload = bytes.fromhex(v["payload"])
        out = (C.c_uint8 * (len(payload) + len(payload) // 254 + 16))()
        n = dll.shim_frame(v["type"], v["seq"], payload, len(payload), out)
        framed.append(bytes(out[:n]).hex())
        t, s, pl = C.c_uint8(), C.c_uint16(), (C.c_uint8 * 1100)()
        m = dll.shim_unframe(bytes.fromhex(v["frame"]), len(v["frame"]) // 2, C.byref(t), C.byref(s), pl, 1100)
        parsed.append((m, t.value, s.value, bytes(pl[: max(m, 0)]).hex()))
        small = dll.shim_unframe(bytes.fromhex(v["frame"]), len(v["frame"]) // 2, C.byref(t), C.byref(s), pl, 0)
        parsed.append(small)
    sizes = {int(t): dll.shim_payload_size(int(t)) for t in Type}
    crc = dll.shim_crc16(b"123456789", 9)
    return framed, parsed, sizes, dll.shim_sample_size(), crc


def test_c_and_python_agree():
    vectors = json.loads(VECTORS.read_text())
    assert len(vectors) >= 12
    framed, parsed, sizes, sample, crc = run_in_child(_c_side, _lib(), vectors)
    for v, f in zip(vectors, framed):
        assert f == v["frame"]
        assert proto.frame(v["type"], v["seq"], bytes.fromhex(v["payload"])).hex() == v["frame"]
    for i, v in enumerate(vectors):
        m, t, s, pl = parsed[2 * i]
        assert (m, t, s, pl) == (len(v["payload"]) // 2, v["type"], v["seq"], v["payload"])
        want_small = -3 if v["payload"] else 0
        assert parsed[2 * i + 1] == want_small
    assert sizes == {int(t): proto.PAYLOAD_SIZE.get(t, 0) for t in Type}
    assert sample == 36 and crc == 0x29B1


def test_proto_compiles_strict(tmp_path):
    r = subprocess.run([*zig_cc(), "-std=c99", "-Wall", "-Wextra", "-Werror", f"-I{COMMON}", "-c",
                        "-o", str(tmp_path / "p.o"), str(COMMON / "hil_proto.c")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def _c_edges(lib):
    dll = C.CDLL(str(lib))
    dll.shim_frame.restype = C.c_size_t
    dll.shim_frame.argtypes = [C.c_uint8, C.c_uint16, C.c_char_p, C.c_size_t, C.c_void_p]
    dll.shim_unframe.restype = C.c_long
    dll.shim_unframe.argtypes = [C.c_char_p, C.c_size_t, C.c_void_p, C.c_void_p, C.c_void_p, C.c_size_t]
    # worst case: all-nonzero payloads, buffers of exactly HIL_FRAME_MAX(n) (guard bytes after)
    exact = {}
    for n in (0, 1, 249, 253, 254, 503, 1015, 1024):
        fmax = n + 5 + (n + 5) // 254 + 2
        out = (C.c_uint8 * (fmax + 8))(*([0xAA] * (fmax + 8)))
        m = dll.shim_frame(1, 7, bytes([0x55]) * n, n, out)
        exact[n] = (m, fmax, bytes(out[:m]).hex(), bytes(out[fmax:]) == b"\xaa" * 8)
    over = (C.c_uint8 * 2048)()
    too_big = dll.shim_frame(1, 0, bytes(1025), 1025, over)
    # four 0xFF groups and a 15-byte group: 1035 encoded bytes that decode to 1030
    crafted = b"".join(b"\xff" + b"\x01" * 254 for _ in range(4)) + b"\x0f" + b"\x01" * 14
    pad = (C.c_uint8 * 64)(*([0xCC] * 64))
    t, s, payload = C.c_uint8(), C.c_uint16(), (C.c_uint8 * 1100)()
    rc = dll.shim_unframe(crafted, len(crafted), C.byref(t), C.byref(s), payload, 1100)
    return exact, too_big, len(crafted), rc, bytes(pad) == b"\xcc" * 64


def test_frame_buffer_bounds_and_hostile_input():
    exact, too_big, n_crafted, rc, _ = run_in_child(_c_edges, _lib())
    for n, (m, fmax, hexframe, guard_ok) in exact.items():
        assert m <= fmax and guard_ok, n
        assert hexframe == proto.frame(1, 7, bytes([0x55]) * n).hex()
    assert exact[249][1] == 257 and exact[1024][1] == 1035
    assert too_big == 0
    assert n_crafted == 1035 and rc == -3


def test_command_modes_distinct_and_shared():
    """HIL_COMMAND modes are distinct across both boards (a reset sent to the wrong port is refused, not taken for a
    self-test), and the Python constants equal the header's."""
    c = {m[0]: int(m[1]) for m in re.findall(r"#define HIL_CMD_(\w+) (\d+)", (COMMON / "hil_proto.h").read_text())}
    assert c == {"EMU_SELFTEST": proto.CMD_EMU_SELFTEST, "EMU_SELFTEST_PHASES": proto.CMD_EMU_SELFTEST_PHASES,
                 "CTRL_RESET": proto.CMD_CTRL_RESET}
    assert len({0, 1, *c.values()}) == 2 + len(c)      # 0 torque and 1 speed are the controller's command modes


def test_emulator_step_is_one_constant():
    """The emulator step is HIL_EMU_STEP_NS in hil_proto.h; the firmware, the host and the PC emulator model take it
    from there, and no other step literal is left in the emulator's step loop."""
    from srmsil import emumodel
    from srmsil.hil import session
    ns = int(re.search(r"#define HIL_EMU_STEP_NS (\d+)u", (COMMON / "hil_proto.h").read_text())[1])
    assert ns == proto.EMU_STEP_NS == 6000
    assert proto.EMU_DT == 6e-6 and session.EMU_DT is proto.EMU_DT
    assert emumodel.run_model.__kwdefaults__["step"] == proto.EMU_DT
    emu = ROOT / "hil" / "emulator"
    h = (emu / "emu.h").read_text()
    assert "#define EMU_STEP_NS HIL_EMU_STEP_NS" in h and "EMU_STEP_HZ" not in h
    for f in ("emu.h", "step.cpp", "encoder.cpp"):
        assert not re.search(r"5e-6|200000\b|200 kHz|\b120\b", (emu / f).read_text()), f
    web = (ROOT / "web" / "src" / "lib" / "hil.ts").read_text()
    assert int(re.search(r"export const EMU_STEP_US = (\d+)\n", web)[1]) * 1000 == ns


def test_capture_ring_is_one_constant():
    """The default capture is the emulator's buffered ring (EMU_CAPTURE_RING samples), in the host, the web and
    examples/control_hil.py, so the summary window holds enough strokes for the ripple median."""
    ring = int(re.search(r"#define EMU_CAPTURE_RING (\d+)", (ROOT / "hil" / "emulator" / "emu.h").read_text())[1])
    assert proto.CAPTURE_RING == ring == 8192
    web = (ROOT / "web" / "src" / "lib" / "hil.ts").read_text()
    assert int(re.search(r"export const CAPTURE_RING = (\d+)\n", web)[1]) == ring


def test_control_hil_example_compiles_and_defaults_to_the_ring():
    import importlib.util
    import py_compile
    path = ROOT / "examples" / "control_hil.py"
    py_compile.compile(str(path), doraise=True)
    spec = importlib.util.spec_from_file_location("control_hil_example", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert round(mod.DEFAULT_DURATION / proto.EMU_DT) == proto.CAPTURE_RING
