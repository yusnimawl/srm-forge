"""HilSession against the fake rig, and the serial transport's framing without a serial port."""

import math
import sys
import time
import types

import pytest
from sil_fixtures import analytic_motor

from srmsil.hil import HilError, proto
from srmsil.hil.config import HilModes
from srmsil.hil.fake import FakeRig
from srmsil.hil.proto import Type
from srmsil.hil.session import HilSession, clock_stats
from srmsil.scenario import Scenario

SCN = Scenario(speed_rpm=1000.0, duration=0.004, command_value=1.0)


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    return tmp_path_factory.mktemp("hil_session")


def session(cache, **kw):
    emu, ctrl = FakeRig(analytic_motor(), cache_dir=cache, **kw)
    return HilSession(emu, ctrl), emu, ctrl


def test_connect_refuses_mode_mismatch(cache):
    s, emu, ctrl = session(cache, mode_mismatch=True)
    with pytest.raises(HilError, match="board modes differ"):
        s.connect()
    for tr in (emu, ctrl):
        assert tr.requests == [Type.HELLO]
    with pytest.raises(HilError, match="not connected"):
        s.configure(analytic_motor(), SCN, HilModes())
    assert Type.START not in emu.requests + ctrl.requests
    assert Type.EMU_CONFIG not in emu.requests


def test_connect_reports_modes_and_hashes(cache):
    s, _, _ = session(cache, modes=HilModes(current_sense="internal", position="both", dac="mcp4921x4"))
    info = s.connect()
    assert info.modes == HilModes(current_sense="internal", position="both", dac="mcp4921x4")
    assert info.emulator_hash == info.controller_hash == 0x5EED0001


def test_capture_gap_invalid(cache):
    s, _, _ = session(cache, drop_after=3)
    m = analytic_motor()
    s.connect()
    s.configure(m, SCN, HilModes())
    s.start()
    try:
        cap = s.capture(800)
    finally:
        s.stop()
    assert not cap.valid
    assert "3" in cap.reason and "sequence" in cap.reason
    assert cap.result.traces == {}
    assert math.isnan(cap.result.summary.mean_torque)


def test_capture_complete_is_valid(cache):
    s, _, _ = session(cache)
    m = analytic_motor()
    s.connect()
    s.configure(m, SCN, HilModes())
    s.start()
    try:
        cap = s.capture(800)
    finally:
        s.stop()
    assert cap.valid, cap.reason
    tr = cap.result.traces
    assert tr["i"].shape == (4, 800) and tr["gate_u"].shape == (4, 800)
    assert tr["t"][1] - tr["t"][0] == pytest.approx(5e-6)
    assert cap.clipped == 0.0


def test_capture_reports_clipped_current(cache):
    s, _, _ = session(cache)
    s.connect()
    s.configure(analytic_motor(), SCN.model_copy(update={"bus_voltage": 400.0}), HilModes())   # runs far past 2 i_max
    s.start()
    try:
        cap = s.capture(800)
    finally:
        s.stop()
    assert cap.valid and 0.0 < cap.clipped < 1.0


def test_bad_frame_during_capture_invalid(cache):
    s, emu, _ = session(cache)
    recv = emu.recv

    def corrupting(timeout):
        f = recv(timeout)
        if f and f[0] == Type.CAPTURE_DATA and f[1] == 5:
            emu.bad_frames += 1
        return f

    emu.recv = corrupting
    s.connect()
    s.configure(analytic_motor(), SCN, HilModes())
    s.start()
    try:
        cap = s.capture(800)
    finally:
        s.stop()
    assert not cap.valid
    assert "1 bad frame" in cap.reason
    assert cap.result.traces == {}


def test_set_param_refused_status(cache):
    s, _, _ = session(cache)
    s.connect()
    s.configure(analytic_motor(), SCN, HilModes())
    s.start()
    try:
        assert s.set_param("theta_on", 10.0) == 0
        assert s.set_param("nope", 1.0) == -1
        assert s.set_param("resolver_pole_pairs", 2.0) == -2
    finally:
        s.stop()


def test_configure_refuses_bad_isr_and_fast_encoder(cache):
    s, emu, _ = session(cache)
    s.connect()
    m = analytic_motor()
    with pytest.raises(ValueError, match="k odd"):
        s.configure(m, SCN.model_copy(update={"isr_hz": 10000.0}), HilModes())
    with pytest.raises(ValueError, match="encoder edge rate"):
        s.configure(m, Scenario(speed_rpm=6000.0, duration=0.004), HilModes())
    with pytest.raises(ValueError, match="encoder edge rate"):
        s.configure(m, Scenario(mode="dynamic", speed_rpm=0.0, command_mode="speed", command_value=-6000.0,
                                duration=0.004), HilModes())
    with pytest.raises(HilError, match="modes"):
        s.configure(m, SCN, HilModes(current_sense="internal"))
    assert Type.EMU_CONFIG not in emu.requests
    rdc = HilModes(position="ad2s1210")
    s2, emu2, _ = session(cache, modes=rdc)
    s2.connect()
    s2.configure(m, Scenario(speed_rpm=6000.0, duration=0.004), rdc)   # no encoder output: no edge-rate limit
    assert emu2.requests.count(Type.EMU_CONFIG) == 1


def test_clock_stats():
    assert clock_stats([math.nan, math.nan], 20000.0) == (None, False, None)
    r, measured, spread = clock_stats([20200.0, 20250.0, math.nan, 20250.0], 20000.0)
    assert measured and r == pytest.approx(20233.333 / 20000.0)
    assert spread == pytest.approx(33.3333 / 20233.333 * 1e6, rel=1e-4)
    assert spread > 500


def test_pyserial_missing_message(monkeypatch):
    from srmsil.hil import transport

    monkeypatch.setitem(sys.modules, "serial", None)
    with pytest.raises(HilError, match="pyserial is not installed; install the hil extra"):
        transport.SerialTransport("COM99", 921600)
    with pytest.raises(HilError, match="pyserial is not installed"):
        transport.discover()


class _FakePort:
    """Stands in for serial.Serial: hands out the given chunks, then nothing."""

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.written = bytearray()

    @property
    def in_waiting(self):
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, n):
        if self.chunks:
            return self.chunks.pop(0)
        time.sleep(0.01)
        return b""

    def write(self, data):
        self.written += data

    def close(self):
        pass


def test_serial_reader_counts_bad_frames(monkeypatch):
    from srmsil.hil import transport

    good = [proto.frame(Type.LIVE_CTRL, k, bytes(proto.LIVE_CTRL.size)) for k in range(3)]
    bad = bytearray(good[1])
    bad[5] ^= 0x40
    stream = b"\x12\x34" + b"\x00" + good[0] + bytes(bad) + good[2]
    port = _FakePort([stream[:7], stream[7:50], stream[50:]])
    fake = types.ModuleType("serial")
    fake.Serial = lambda *a, **k: port
    monkeypatch.setitem(sys.modules, "serial", fake)
    t = transport.SerialTransport("COM99", 921600)
    try:
        got = [t.recv(1.0), t.recv(1.0), t.recv(0.1)]
        assert [g[1] for g in got[:2]] == [0, 2]
        assert got[2] is None
        assert t.bad_frames == 2          # the partial frame before the first delimiter and the CRC-bad one
        seq = t.send(Type.HELLO, b"")
        assert proto.unframe(bytes(port.written)) == (Type.HELLO, seq, b"")
    finally:
        t.close()
