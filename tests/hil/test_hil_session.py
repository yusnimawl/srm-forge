"""HilSession against the fake rig, and the serial transport's framing without a serial port."""

import dataclasses
import math
import sys
import time
import types
from pathlib import Path

import numpy as np
import pytest
from sil_fixtures import analytic_motor

from srmsil.hil import HilError, proto
from srmsil.hil.config import HilModes
from srmsil.hil.build import BuildResult
from srmsil.hil.fake import FAKE_HASH, FakeRig
from srmsil.hil.proto import Type
from srmsil.hil.session import EMU_DT, HilSession, _capture_problem, clock_stats, emu_config, run_hil
from srmsil.scenario import Scenario, SensorSettings

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
    assert tr["t"][1] - tr["t"][0] == pytest.approx(EMU_DT)
    assert cap.clipped == 0.0


def test_capture_reports_clipped_current(cache):
    open_loop = str(Path(__file__).parents[1] / "sil" / "controllers" / "open_loop")
    s, _, _ = session(cache, controller=open_loop)
    s.connect()
    scn = Scenario(speed_rpm=1000.0, duration=0.01, params={"theta_on": 0.6, "theta_off": 0.95})   # peaks far past 2 i_max
    s.configure(analytic_motor(), scn, HilModes())
    s.start()
    try:
        cap = s.capture(2000)
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


def test_configure_resets_parameters_of_an_earlier_session(cache):
    """A parameter set live in one session must not leak into the next one: its matched SIL uses the build's
    defaults plus the new scenario's parameters, so configure resets the controller board first."""
    s, emu, ctrl = session(cache)
    m = analytic_motor()
    s.connect()
    s.configure(m, SCN, HilModes())
    s.start()
    try:
        assert s.set_param("theta_on", 20.0) == 0
    finally:
        s.stop()
    assert ctrl._rig.params == {"theta_on": 20.0}
    s2 = HilSession(emu, ctrl)
    s2.connect()
    ctrl.requests.clear()
    s2.configure(m, SCN.model_copy(update={"params": {"theta_off": 140.0}}), HilModes())
    assert ctrl._rig.params == {"theta_off": 140.0}
    assert ctrl.requests.index(Type.COMMAND) < ctrl.requests.index(Type.PARAM_SET)   # the reset comes first
    s2.start()
    try:
        assert s2.set_param("resolver_pole_pairs", 2.0) == -2     # fixed again once started after the reset
    finally:
        s2.stop()


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


def test_capture_speed_range_covers_the_run(cache):
    """A speed step from rest past 955 rpm (2 x 0 and the 100 rad/s floor) keeps its captured speed: the range comes
    from the speed command, or for a torque command from the peak torque over the settle and capture time. A speed
    beyond the range counts as clipped."""
    m = analytic_motor()
    rpm = 2 * math.pi / 60
    step = Scenario(mode="dynamic", speed_rpm=0.0, inertia=1e-4, duration=0.02, command_mode="speed",
                    command_value=1500.0)
    torque = step.model_copy(update={"command_mode": "torque", "command_value": 1.0, "speed_rpm": 100.0})
    assert emu_config(m, step, 4000, "encoder")["omega_max"] == pytest.approx(2 * 1500.0 * rpm)
    physics = 100.0 * rpm + float(np.max(np.abs(m.torque))) * (0.2 + 0.02) / 1e-4
    # a torque command is capped at the speed limit of the build's position sensors: 400 000 edges/s of a 4096-count
    # encoder, the resolver's tracking rate (1000 rev/s at 12 bits) per pole pair, the lower of the two for both
    enc, rdc = 2 * math.pi * 400_000 / 4096, 2 * math.pi * 1000 / 2
    torque = torque.model_copy(update={"sensors": SensorSettings(resolver_pole_pairs=2)})
    assert physics > rdc > enc
    assert emu_config(m, torque, 4000, "encoder")["omega_max"] == pytest.approx(enc)
    assert emu_config(m, torque, 4000, "ad2s1210")["omega_max"] == pytest.approx(rdc)
    assert emu_config(m, torque, 4000, "both")["omega_max"] == pytest.approx(enc)
    heavy = torque.model_copy(update={"inertia": 1.0})                   # slower than both limits
    assert emu_config(m, heavy, 4000, "both")["omega_max"] == pytest.approx(
        100.0 * rpm + float(np.max(np.abs(m.torque))) * 0.22)
    assert emu_config(m, SCN, 4000, "encoder")["omega_max"] == 0.0
    s, _, _ = session(cache)
    s.connect()
    s.configure(m, step, HilModes())
    s.start()
    try:
        cap = s.capture(4000)
    finally:
        s.stop()
    assert cap.valid, cap.reason
    w = cap.result.traces["omega"]
    assert cap.clipped == 0.0
    assert 1200 * rpm < w.max() < 2 * 1500.0 * rpm      # past the old 100 rad/s range, not saturated
    s, emu, _ = session(cache)
    s.connect()
    s.configure(m, step.model_copy(update={"command_value": 400.0}), HilModes())   # range 2 x 400 rpm = 83.8 rad/s
    s.start()
    try:
        s.command("speed", 1500.0)                       # raised while running: beyond the range
        cap = s.capture(4000)
    finally:
        s.stop()
    assert cap.valid, cap.reason
    assert cap.clipped > 0.0


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


def test_failed_reconnect_clears_rig_info(cache):
    s, _, ctrl = session(cache)
    assert s.connect().modes == HilModes()
    ctrl._rig.codes[2] = (1, 0, 1)                      # the controller board now reports internal sensing
    with pytest.raises(HilError, match="board modes differ"):
        s.connect()
    assert s.info is None
    with pytest.raises(HilError, match="board modes differ"):
        run_hil(s, analytic_motor(), "hysteresis", SCN)


def test_run_hil_keeps_the_run_error_when_stop_fails(cache):
    s, _, _ = session(cache)
    s.connect()

    def failing_stop():
        raise HilError("stop failed")

    def failing_capture(n):
        s.stop = failing_stop
        raise HilError("capture failed")

    s.capture = failing_capture
    with pytest.raises(HilError, match="capture failed"):
        run_hil(s, analytic_motor(), "hysteresis", SCN)


def test_short_capture_invalid():
    hdr = proto.CaptureHeader(EMU_DT, 1, 1, 1, 1, 1, 100, 4)
    parts = [np.zeros(28, proto.SAMPLE_DTYPE) for _ in range(3)]
    for k, p in enumerate(parts):
        p["step"] = 28 * k + np.arange(28)
    assert _capture_problem(84, hdr, [0, 1, 2], parts, (3, 1, 84), 0, []) == ""
    assert _capture_problem(100, hdr, [0, 1, 2], parts, (3, 1, 84), 0, []) == "short capture: 84 of 100 samples"
    # the header's dt arrives as float32
    f32 = proto.unpack_capture_hdr(proto.pack_capture_hdr(hdr))
    assert _capture_problem(84, f32, [0, 1, 2], parts, (3, 1, 84), 0, []) == ""
    old = dataclasses.replace(hdr, dt=5e-6)
    assert _capture_problem(84, old, [0, 1, 2], parts, (3, 1, 84), 0, []) == (
        "capture step 5 us, the host expects 6 us (emulator firmware of another build)")


@pytest.mark.parametrize("field", [{"adc": {"offset_error": 1.0}}, {"adc": {"gain_error": 0.01}},
                                   {"adc": {"noise": 0.5}}, {"adc": {"rc_tau": 1e-6}}, {"sensors": {"delay": 1e-6}},
                                   {"sensors": {"delay_jitter": 1e-6}}])
def test_configure_refuses_settings_the_hil_does_not_emulate(cache, field):
    s, emu, _ = session(cache)
    s.connect()
    scn = Scenario(speed_rpm=1000.0, duration=0.004, **field)
    (group, values), = field.items()
    (name, _), = values.items()
    with pytest.raises(HilError, match=f"does not emulate {group}.{name}"):
        s.configure(analytic_motor(), scn, HilModes())
    assert Type.EMU_CONFIG not in emu.requests


def test_run_hil_checks_the_boards_run_the_expected_build(cache):
    """run_hil(expect=...) refuses, before configuring, a rig whose boards run another build than the one flashed."""
    m = analytic_motor()
    s, emu, _ = session(cache)
    res = run_hil(s, m, "hysteresis", SCN, expect=BuildResult(True, "", FAKE_HASH))
    assert res.hil["valid"], res.hil["reason"]
    s, emu, _ = session(cache)
    with pytest.raises(HilError, match="the controller board runs another build"):
        run_hil(s, m, "hysteresis", SCN, expect=BuildResult(True, "", 0x1234))
    assert Type.EMU_CONFIG not in emu.requests
    s, emu, _ = session(cache, emulator_hash=0x1234)
    with pytest.raises(HilError, match="the emulator board runs another build"):
        run_hil(s, m, "hysteresis", SCN, expect=BuildResult(True, "", FAKE_HASH))
    assert Type.EMU_CONFIG not in emu.requests


def test_fake_rig_reports_the_chosen_hashes(cache):
    s, _, _ = session(cache, emulator_hash=0x11, controller_hash=0x22)
    info = s.connect()
    assert (info.emulator_hash, info.controller_hash) == (0x11, 0x22)


def test_step_time_over_80_percent_is_a_warning_not_a_failure(cache):
    """An emulator step max above 80 % of the step is reported in hil["warnings"]; the run stays valid."""
    from srmsil.hil.session import Capture, capture_health
    from srmsil.run import SimResult
    s, _, _ = session(cache)
    live = dict(step=1, mean_torque=1.0, ripple_pct=1.0, i_rms=(1.0,) * 4, speed_rpm=1000.0, step_mean_us=2.0,
                overruns=0, dropped=0, edge_jitter_ns=20.0, latency_us=6.0, temp_c=60.0, trigger_hz=20000.0)
    s.ctrl_windows = [proto.LiveCtrl(3.0, 4.0, 0, 0.0, (0.0,) * 4, 17.0, 0, proto.CTRL_RUNNING)]
    cap = Capture(SimResult({}, None, SCN, "", "", ""), True, "")
    for step_max, warned in ((4.8, False), (4.81, True)):
        s.emu_windows = [proto.LiveEmu(step_max_us=step_max, **live)]
        h = capture_health(s, cap, 20000.0)
        assert h["valid"] and h["reason"] == ""
        assert bool(h["warnings"]) == warned
    assert h["warnings"] == ["emulator step max 4.81 us is 80.2 % of the 6 us step (warning above 80 %)"]
