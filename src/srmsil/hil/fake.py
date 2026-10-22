"""A fake rig for tests and the web layer without boards: two transports that answer like the emulator and controller
firmware, with live statistics and captures taken from a SIL run of the controller."""

from __future__ import annotations

import math
import tempfile
import time
from collections import deque
from pathlib import Path

import numpy as np

from srmsil.hil import proto
from srmsil.hil.compare import SETTLE_S, matched_scenario
from srmsil.hil.config import HilModes
from srmsil.hil.proto import Type
from srmsil.hil.session import EMU_DT, RPM, build_codes
from srmsil.run import PARAMS, TRACE_CAP, SimResult, run
from srmsil.scenario import ConverterSettings, Scenario, SensorSettings
from srmsil.tables import MotorData

FAKE_PWM_HZ = 20000.0        # the fake firmware's build constants: pwm_hz = isr_hz
FAKE_HASH = 0x5EED0001
LIVE_S = 0.05
LATENCY_US = 8.0             # reported output latency; the fake's SIL runs with the matched timing for it
SIL_DT = 0.5e-6


class _Rig:
    def __init__(self, motor, modes, drop_after, mode_mismatch, clock_ratio, controller, cache_dir):
        self.m, self.modes, self.drop_after, self.clock_ratio = motor, modes, drop_after, clock_ratio
        self.controller, self.cache_dir = controller, Path(cache_dir)
        cs, pos, dac = build_codes(modes)
        self.codes = {1: (cs, pos, dac), 2: (1 if mode_mismatch else cs, pos, 1 if mode_mismatch else dac)}
        self.cfg: dict | None = None
        self.got = [0, 0]
        self.t_max = 0.0
        self.emu_on = self.ctrl_on = self.started = False
        self.params: dict[str, float] = {}
        self.cmd = (0, 0.0)
        self.sil: SimResult | None = None
        self.ctrl_t0 = 0.0         # monotonic time of the controller's start: emulator step 0

    def build_info(self, board: int) -> bytes:
        return proto.pack_build_info(proto.BuildInfo(proto.PROTOCOL_VERSION, board, *self.codes[board], FAKE_HASH))

    def step_now(self) -> int:
        return round((time.monotonic() - self.ctrl_t0) / EMU_DT) if self.started else 0

    def scenario(self, n_steps: int, s0: int = 0) -> Scenario:
        """n_steps of the run from emulator step s0 since the controller's start (fixed speed: the rotor angle then),
        on the rig's timing and ADC chain (as matched_scenario models it)."""
        c = self.cfg
        mode, value = self.cmd
        base = Scenario(
            mode="dynamic" if c["mode"] else "fixed", speed_rpm=c["speed"] / RPM, duration=n_steps * EMU_DT,
            dt=SIL_DT, command_mode="speed" if mode else "torque", command_value=value / RPM if mode else value,
            inertia=c["inertia"], friction=c["friction"], load=c["load"], load_step=c["load_step"],
            load_step_time=c["load_step_time"], theta0=math.remainder(c["theta0"] + c["speed"] * s0 * EMU_DT, 2 * math.pi),
            bus_voltage=c["bus_voltage"], pwm_hz=FAKE_PWM_HZ, seed=c["seed"], params=dict(self.params),
            converter=ConverterSettings(v_switch=c["v_switch"], v_diode=c["v_diode"], dead_time=c["dead_time"],
                                        turn_on_delay=c["turn_on_delay"], turn_off_delay=c["turn_off_delay"]),
            sensors=SensorSettings(
                encoder_cpr=c["encoder_cpr"], encoder_offset=c["encoder_offset"], encoder_ecc_amp=c["encoder_ecc_amp"],
                encoder_ecc_harmonic=c["encoder_ecc_harmonic"], resolver=bool(c["resolver"]),
                resolver_pole_pairs=c["resolver_pole_pairs"], resolver_bits=c["rdc_bits"],
                resolver_gain_mismatch=c["resolver_gain_mismatch"], resolver_phase_error=c["resolver_phase_error"]))
        return matched_scenario(base, LATENCY_US * 1e-6, self.modes, self.clock_ratio, m=self.m, end_s=None)

    def capture(self, seq: int, n: int) -> list[tuple[int, int, bytes]]:
        start = self.step_now()
        k = round(EMU_DT / SIL_DT)
        settle = round(SETTLE_S / EMU_DT)
        # a fixed-speed run is simulated from SETTLE_S before the capture, as the matched SIL does; a dynamic one from
        # the controller's start
        s0 = start - settle if not self.cfg["mode"] and start > settle else 0
        off = start - s0
        if (off + n) * k > TRACE_CAP:
            raise RuntimeError("fake rig: a dynamic capture must end within 1 s of the controller's start")
        res = run(self.m, self.controller, self.scenario(off + n, s0), cache_dir=self.cache_dir)
        self.sil = res
        c, tr, q = self.cfg, res.traces, self.m.n_phases
        idx = (off + np.arange(n)) * k
        scales = (2 * c["i_max"] / 32767, 2 * c["psi_max"] / 32767, 1.25 * (c["bus_voltage"] + 2 * c["v_diode"]) / 32767,
                  1.25 * (self.t_max or 1.0) / 32767, max(2 * abs(c["speed"]), 100.0) / 32767)
        hdr = proto.CaptureHeader(EMU_DT, *scales, n, q)

        def i16(x, scale):
            return np.clip(np.round(x / scale), -32767, 32767).astype(np.int16)

        s = np.zeros(n, proto.SAMPLE_DTYPE)
        s["step"] = start + np.arange(n)
        s["i"][:, :q] = i16(tr["i"][:, idx], hdr.i_scale).T
        s["psi"][:, :q] = i16(tr["psi"][:, idx], hdr.psi_scale).T
        v = tr["v"][:, off * k: (off + n) * k].reshape(q, n, k).mean(axis=2)   # averaged over each emulator step
        s["v"][:, :q] = i16(v, hdr.v_scale).T
        s["torque"] = i16(tr["torque"][idx], hdr.t_scale)
        s["theta"] = (np.mod(tr["theta"][idx] / (2 * math.pi), 1.0) * 65536).astype(np.uint32) & 0xFFFF
        s["omega"] = i16(tr["omega"][idx], hdr.omega_scale)
        w = np.arange(q)[:, None]
        s["gates"] = ((tr["gate_u"][:, idx].astype(np.uint16) << w).sum(0)
                      | (tr["gate_l"][:, idx].astype(np.uint16) << (w + 8)).sum(0))
        out = [(Type.CAPTURE_HDR, 0, proto.pack_capture_hdr(hdr))]
        n_pk = 0
        for j in range(0, n, proto.SAMPLES_PER_PACKET):
            part = s[j: j + proto.SAMPLES_PER_PACKET]
            if n_pk != self.drop_after:
                out.append((Type.CAPTURE_DATA, n_pk, proto.pack_capture_data(int(part["step"][0]), part)))
            n_pk += 1
        out.append((Type.CAPTURE_END, n_pk, proto.CAPTURE_END.pack(1, n)))
        return out

    def live_emu(self) -> bytes:
        trig = FAKE_PWM_HZ * self.clock_ratio if self.ctrl_on else math.nan
        if self.sil is not None:
            s = self.sil.summary
            phys = (s.mean_torque, s.ripple_pct, (*s.i_rms, *[0.0] * (4 - len(s.i_rms))))
        else:
            phys = (math.nan, math.nan, (math.nan,) * 4)
        return proto.pack_live_emu(proto.LiveEmu(self.step_now(), phys[0], phys[1], phys[2], self.cfg["speed"] / RPM,
                                                 2.0, 3.5, 0, 0, 20.0, LATENCY_US, 60.0, trig))

    def live_ctrl(self) -> bytes:
        state = (proto.CTRL_RUNNING if self.ctrl_on else 0) | (proto.CTRL_READY if self.emu_on else 0)
        return proto.pack_live_ctrl(proto.LiveCtrl(3.0 if self.ctrl_on else 0.0, 4.0 if self.started else 0.0, 0,
                                                   self.cmd[1], (0.0,) * 4, 17.0, 0, state))

    def handle(self, board: int, t: int, seq: int, p: bytes) -> list[tuple[int, int, bytes]]:
        def ack(err: str | None = None):
            return [(Type.ERROR, seq, err.encode())] if err else [(t, seq, b"")]

        size = proto.PAYLOAD_SIZE.get(t)
        if size and len(p) != size:
            return ack("bad payload size")
        if t == Type.HELLO:
            return [(Type.BUILD_INFO, seq, self.build_info(board))]
        if board == 1:
            return self._emulator(t, seq, p, ack)
        return self._controller(t, seq, p, ack)

    def _emulator(self, t, seq, p, ack):
        if t == Type.EMU_CONFIG:
            if self.emu_on:
                return ack("config refused: running")
            self.cfg, self.got, self.t_max = proto.unpack_emu_config(p), [0, 0], 0.0
            return ack()
        if t == Type.TABLE_CHUNK:
            which, off, vals = proto.unpack_table_chunk(p)
            if self.cfg is None or (off != 0 and off != self.got[which]):
                return ack("table refused: chunk out of order")
            self.got[which] = off + len(vals)
            if which == 1 and len(vals):
                self.t_max = max(self.t_max, float(np.abs(vals).max()))
            return []
        if t == Type.START:
            size = self.cfg["n_theta"] * self.cfg["n_psi"] if self.cfg else -1
            if self.got != [size, size]:
                return ack("start refused: tables incomplete")
            self.emu_on = True
            return ack()
        if t == Type.STOP:
            self.emu_on = self.ctrl_on = False       # READY falls and stops the controller
            return ack()
        if t == Type.COMMAND:
            return ack()
        if t == Type.CAPTURE_REQ:
            if not self.emu_on:
                return ack("capture refused: not running")
            n = proto.CAPTURE_REQ.unpack(p)[0] or self.cfg["capture_steps"]
            return self.capture(seq, n)
        return ack("unknown request")

    def _controller(self, t, seq, p, ack):
        if t == Type.PARAM_SET:
            name, value = proto.unpack_param_set(p)
            known = {k for k, _, _ in PARAMS.get(self.controller, [])}
            if known and name not in known:
                status = -1
            elif name == "resolver_pole_pairs" and self.started:
                status = -2
            else:
                self.params[name] = value
                status = 0
            return [(Type.PARAM_REPLY, seq, proto.pack_param_reply(name, status))]
        if t == Type.COMMAND:
            mode, value = proto.unpack_command(p)
            if mode > 1 or not math.isfinite(value):
                return ack("command refused: mode must be 0 (torque) or 1 (speed) with a finite value")
            self.cmd = (mode, value)
            return ack()
        if t == Type.START:
            if not self.emu_on:
                return ack("start refused: READY is low (start the emulator first)")
            self.ctrl_on = self.started = True
            self.ctrl_t0 = time.monotonic()
            return ack()
        if t == Type.STOP:
            self.ctrl_on = False
            return ack()
        return ack("unknown request")


class FakeTransport:
    """One board's link to the fake rig. `requests` lists the frame types the host sent."""

    def __init__(self, rig: _Rig, board: int):
        self._rig, self._board = rig, board
        self._q: deque[tuple[int, int, bytes]] = deque()
        self._seq = 0
        self._next_live = time.monotonic() + LIVE_S
        self.bad_frames = 0
        self.requests: list[int] = []

    def send(self, type: int, payload: bytes = b"") -> int:
        self._seq = (self._seq + 1) & 0xFFFF
        self.requests.append(type)
        self._q.extend(self._rig.handle(self._board, type, self._seq, bytes(payload)))
        return self._seq

    def _live_due(self) -> bool:
        if time.monotonic() < self._next_live:
            return False
        self._next_live = time.monotonic() + LIVE_S
        if self._board == 1:
            if self._rig.emu_on:
                self._q.append((Type.LIVE_EMU, 0, self._rig.live_emu()))
        else:
            self._q.append((Type.LIVE_CTRL, 0, self._rig.live_ctrl()))
        return bool(self._q)

    def recv(self, timeout: float) -> tuple[int, int, bytes] | None:
        if self._q or self._live_due():
            return self._q.popleft()
        wait = min(timeout, self._next_live - time.monotonic())
        if wait > 0:
            time.sleep(wait)
        if self._q or self._live_due():
            return self._q.popleft()
        return None

    def close(self) -> None:
        pass


def FakeRig(motor: MotorData, *, modes: HilModes = HilModes(), drop_after: int | None = None,  # noqa: N802
            mode_mismatch: bool = False, clock_ratio: float = 1.0, controller: str = "hysteresis",
            cache_dir: Path | None = None) -> tuple[FakeTransport, FakeTransport]:
    """(emulator, controller) transports of a fake rig built for `modes` running `controller` (a reference name or
    a folder, as srmsil.run.run takes). `drop_after` leaves out the capture packet with that sequence number;
    `mode_mismatch` makes the controller report internal current sensing; the controller's clock runs at
    `clock_ratio` times nominal (its trigger rate and its SIL run)."""
    rig = _Rig(motor, modes, drop_after, mode_mismatch, clock_ratio, controller,
               cache_dir or Path(tempfile.gettempdir()) / "srmsil_fake_rig")
    return FakeTransport(rig, 1), FakeTransport(rig, 2)

