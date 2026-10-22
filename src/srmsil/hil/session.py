"""A live HIL session on the two boards, captures, and `run_hil`, a scripted fixed run returned as a SimResult."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np

from srmsil.hil import HilError, proto
from srmsil.hil.config import HilModes, check_encoder_rate, check_isr_rate, mode_defines, sensor_chain
from srmsil.hil.proto import BuildInfo, LiveCtrl, LiveEmu, Type
from srmsil.hil.transport import Transport
from srmsil.run import SimResult, SimSummary
from srmsil.scenario import Scenario
from srmsil.tables import MotorData, emu_tables

EMU_DT = 5e-6                 # s, the emulator step and the capture sample period
REPLY_TIMEOUT_S = 2.0
CLOCK_SPREAD_WARN_PPM = 500.0
RPM = 2 * math.pi / 60

CS_CODES = {"ad7606": 0, "internal": 1}
POS_CODES = {"encoder": 0, "ad2s1210": 1, "both": 2}
DAC_CODES = {"mcp4922x2": 1, "mcp4921x4": 2}


def build_codes(modes: HilModes) -> tuple[int, int, int]:
    """BUILD_INFO (current_sense, position, dac) of firmware built for `modes`; the DAC is 0 with the AD7606."""
    dac = DAC_CODES[modes.dac] if modes.current_sense == "internal" else 0
    return CS_CODES[modes.current_sense], POS_CODES[modes.position], dac


def _modes_of(info: BuildInfo) -> HilModes:
    def name(codes: dict, code: int, what: str) -> str:
        for k, v in codes.items():
            if v == code:
                return k
        raise HilError(f"board reports an unknown {what} code {code}")

    cs = name(CS_CODES, info.current_sense, "current_sense")
    pos = name(POS_CODES, info.position, "position")
    if cs == "internal":
        return HilModes(current_sense=cs, position=pos, dac=name(DAC_CODES, info.dac, "dac"))
    return HilModes(current_sense=cs, position=pos)


@dataclass(frozen=True)
class RigInfo:
    modes: HilModes
    emulator_hash: int
    controller_hash: int


@dataclass(frozen=True)
class LiveStats:
    emu: LiveEmu | None
    ctrl: LiveCtrl | None


@dataclass(frozen=True)
class Capture:
    result: SimResult       # traces empty and summary NaN unless every sample arrived
    valid: bool
    reason: str             # "" when valid
    clipped: float = 0.0    # share of samples with a phase current at the capture's int16 limit (2 x the table i_max)


def emu_config(m: MotorData, scenario: Scenario, capture_steps: int) -> dict:
    """HIL_EMU_CONFIG fields of a scenario on the emulator's table grid. The firmware does not model the SIL's ADC
    errors or `sensors.delay`; those fields are sent as 0."""
    tab = emu_tables(m)
    sc, se = scenario.converter, scenario.sensors
    c = dict.fromkeys(proto.EMU_CONFIG_FIELDS, 0)
    c.update(resistance=m.resistance, bus_voltage=scenario.bus_voltage or m.bus_voltage,
             speed=scenario.speed_rpm * RPM, theta0=scenario.theta0, inertia=scenario.inertia,
             friction=scenario.friction, load=scenario.load, load_step=scenario.load_step,
             load_step_time=scenario.load_step_time, v_switch=sc.v_switch, v_diode=sc.v_diode,
             dead_time=sc.dead_time, turn_on_delay=sc.turn_on_delay, turn_off_delay=sc.turn_off_delay,
             theta_step=tab.theta_step, psi_step=tab.psi_step, psi_max=tab.psi_max, i_max=tab.i_max,
             encoder_offset=se.encoder_offset, encoder_ecc_amp=se.encoder_ecc_amp,
             resolver_gain_mismatch=se.resolver_gain_mismatch, resolver_phase_error=se.resolver_phase_error,
             volt_rc_tau=scenario.adc.volt_rc_tau, n_theta=tab.current.shape[0], n_psi=tab.current.shape[1],
             encoder_cpr=se.encoder_cpr, capture_steps=capture_steps, seed=scenario.seed, n_phases=m.n_phases,
             n_rotor_poles=m.n_rotor_poles, mode=int(scenario.mode == "dynamic"), rdc_bits=se.resolver_bits,
             resolver_pole_pairs=se.resolver_pole_pairs, encoder_ecc_harmonic=se.encoder_ecc_harmonic,
             resolver=int(se.resolver))
    c.update(sensor_chain(m, scenario))
    return c


def _nan_summary(q: int) -> SimSummary:
    n = math.nan
    return SimSummary(n, n, np.full(q, n), n, n, n, n, n, n)


def capture_traces(hdr: proto.CaptureHeader, s: np.ndarray) -> dict[str, np.ndarray]:
    """SimResult-style traces of captured samples (the quantities the emulator records)."""
    q = hdr.n_phases
    k = np.arange(q)[:, None]
    g = s["gates"].astype(np.uint16)[None, :]
    return {
        "t": s["step"].astype(np.float64) * hdr.dt,       # since the controller's start: the plant steps only while RUN is high
        "theta": s["theta"].astype(np.float64) * (2 * math.pi / 65536),
        "omega": s["omega"] * float(hdr.omega_scale),
        "torque": s["torque"] * float(hdr.t_scale),
        "i": (s["i"][:, :q].T * hdr.i_scale).astype(np.float32),
        "psi": (s["psi"][:, :q].T * hdr.psi_scale).astype(np.float32),
        "v": (s["v"][:, :q].T * hdr.v_scale).astype(np.float32),
        "gate_u": ((g >> k) & 1).astype(np.uint8),
        "gate_l": ((g >> (k + 8)) & 1).astype(np.uint8),
    }


def capture_summary(traces: dict[str, np.ndarray], resistance: float) -> SimSummary:
    """The SIL's summary quantities over the second half of a capture. The energy balance, the table round trip and
    the beyond-map share are not measured on the HIL (NaN)."""
    n = len(traces["t"])
    w = slice(n // 2, n)
    t = traces["torque"][w]
    i = traces["i"][:, w].astype(np.float64)
    v = traces["v"][:, w].astype(np.float64)
    mean_t = float(np.mean(t))
    ripple = 100 * float(np.max(t) - np.min(t)) / abs(mean_t) if abs(mean_t) > 1e-12 else math.nan
    i2 = np.mean(i**2, axis=1)
    return SimSummary(mean_torque=mean_t, ripple_pct=ripple, i_rms=np.sqrt(i2), copper_loss=resistance * float(i2.sum()),
                      power_in=float(np.mean(np.sum(v * i, axis=0))),
                      power_mech=float(np.mean(t * traces["omega"][w])), beyond_map_fraction=math.nan,
                      energy_error=math.nan, roundtrip_error=math.nan)


def clock_stats(trigger_hz: list[float], isr_hz: float) -> tuple[float | None, bool, float | None]:
    """(ratio, measured, spread_ppm) of the controller's clock from the per-window trigger rates: the mean of the
    finite windows over the nominal isr_hz, and the largest window deviation from that mean. NaN windows (no trigger
    wire, controller stopped) are skipped; with none left the ratio is None."""
    f = np.array([x for x in trigger_hz if math.isfinite(x)])
    if not len(f):
        return None, False, None
    mean = float(f.mean())
    return mean / isr_hz, True, float(np.max(np.abs(f - mean)) / mean * 1e6)


class HilSession:
    """The emulator and controller boards over two transports. Frames that are not the reply being waited for
    (live statistics, errors a board sends by itself) are kept: `emu_windows`, `ctrl_windows` and `errors` since the
    last `start`."""

    def __init__(self, emulator: Transport, controller: Transport):
        self.emu, self.ctrl = emulator, controller
        self.info: RigInfo | None = None
        self.emu_windows: list[LiveEmu] = []
        self.ctrl_windows: list[LiveCtrl] = []
        self.errors: list[str] = []
        self._new_emu: LiveEmu | None = None
        self._new_ctrl: LiveCtrl | None = None
        self._m: MotorData | None = None
        self._scenario: Scenario | None = None

    # -- frame handling

    def _keep(self, frame: tuple[int, int, bytes]) -> None:
        t, _, p = frame
        if t == Type.LIVE_EMU and len(p) == proto.LIVE_EMU.size:
            self._new_emu = proto.unpack_live_emu(p)
            self.emu_windows.append(self._new_emu)
        elif t == Type.LIVE_CTRL and len(p) == proto.LIVE_CTRL.size:
            self._new_ctrl = proto.unpack_live_ctrl(p)
            self.ctrl_windows.append(self._new_ctrl)
        elif t == Type.ERROR:
            self.errors.append(p.decode(errors="replace"))

    def _drain(self, tr: Transport) -> None:
        while (f := tr.recv(0.0)) is not None:
            self._keep(f)

    def _wait(self, tr: Transport, match, timeout: float):
        """The first frame on `tr` for which match(frame) holds, keeping the others; None after `timeout` s."""
        other = self.ctrl if tr is self.emu else self.emu
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            f = tr.recv(min(left, 0.02))
            self._drain(other)
            if f is None:
                continue
            if match(f):
                return f
            self._keep(f)
        return None

    def _request(self, tr: Transport, type: int, payload: bytes = b"", reply: int | None = None,
                 timeout: float = REPLY_TIMEOUT_S) -> bytes:
        reply = type if reply is None else reply
        seq = tr.send(type, payload)
        f = self._wait(tr, lambda f: f[1] == seq and f[0] in (reply, Type.ERROR), timeout)
        board = "emulator" if tr is self.emu else "controller"
        if f is None:
            raise HilError(f"{board}: no reply to {Type(type).name}")
        if f[0] == Type.ERROR:
            raise HilError(f"{board}: {f[2].decode(errors='replace')}")
        return f[2]

    def wait(self, seconds: float) -> None:
        """Keep the live statistics of both boards for `seconds`."""
        self._wait(self.emu, lambda f: False, seconds)

    # -- session

    def connect(self) -> RigInfo:
        """Ask both boards for their build; raises before anything else is sent when the protocol, the board roles or
        the build modes do not match."""
        self.info = None
        infos = []
        for tr, board, name in ((self.emu, 1, "emulator"), (self.ctrl, 2, "controller")):
            b = proto.unpack_build_info(self._request(tr, Type.HELLO, reply=Type.BUILD_INFO))
            if b.protocol != proto.PROTOCOL_VERSION:
                raise HilError(f"{name}: protocol {b.protocol}, this host speaks {proto.PROTOCOL_VERSION}")
            if b.board != board:
                raise HilError(f"the {name} port answers as board {b.board} (ports swapped?)")
            infos.append(b)
        e, c = infos
        ce, cc = (e.current_sense, e.position, e.dac), (c.current_sense, c.position, c.dac)
        if ce != cc:
            raise HilError(f"board modes differ: emulator (current_sense, position, dac) = {ce}, controller = {cc}; "
                           "flash both boards with the same modes")
        self.info = RigInfo(_modes_of(e), e.firmware_hash, c.firmware_hash)
        return self.info

    def _connected(self) -> RigInfo:
        if self.info is None:
            raise HilError("not connected")
        return self.info

    def configure(self, m: MotorData, scenario: Scenario, modes: HilModes) -> None:
        """Check the scenario against the HIL's rules, stop both boards, upload the emulator config and tables, set
        the controller parameters and command. Rule checks raise ValueError, and modes or settings the HIL does not
        emulate raise HilError, before anything is sent."""
        info = self._connected()
        if mode_defines(modes) != mode_defines(info.modes):
            raise HilError(f"modes {modes.env_string} differ from the boards' build {info.modes.env_string}")
        check_isr_rate(scenario)
        if modes.position in ("encoder", "both"):
            rpm = abs(scenario.speed_rpm)
            if scenario.mode == "dynamic" and scenario.command_mode == "speed":
                rpm = max(rpm, abs(scenario.command_value))
            check_encoder_rate(scenario.sensors.encoder_cpr, rpm)
        if scenario.param_steps:
            raise ValueError("param_steps are not timed on the HIL; set parameters live with set_param")
        ad, se = scenario.adc, scenario.sensors
        unsupported = [name for name, v in (("adc.offset_error", ad.offset_error), ("adc.gain_error", ad.gain_error),
                                            ("adc.noise", ad.noise), ("adc.rc_tau", ad.rc_tau),
                                            ("sensors.delay", se.delay)) if v != 0]
        if unsupported:
            raise HilError(f"the HIL does not emulate {', '.join(unsupported)}; set them to 0 (the sensed-value delay "
                           "and the ADC are those of the rig)")
        n = round(scenario.duration / EMU_DT)
        self.stop()
        self._request(self.emu, Type.EMU_CONFIG, proto.pack_emu_config(emu_config(m, scenario, n)))
        tab = emu_tables(m)
        n_err = len(self.errors)
        for which, arr in ((0, tab.current), (1, tab.torque)):
            flat = np.ascontiguousarray(arr, np.float32).ravel()
            for off in range(0, flat.size, proto.TABLE_CHUNK_FLOATS):
                self.emu.send(Type.TABLE_CHUNK, proto.pack_table_chunk(which, off, flat[off:off + proto.TABLE_CHUNK_FLOATS]))
        self._request(self.emu, Type.HELLO, reply=Type.BUILD_INFO, timeout=10.0)   # chunks are refused before this
        if len(self.errors) > n_err:
            raise HilError(f"emulator: {self.errors[n_err]}")
        for name, value in scenario.params.items():
            status = self.set_param(name, value)
            if status:
                raise HilError(f"controller refused parameter {name!r} (status {status})")
        self.command(scenario.command_mode, scenario.command_value)
        self._m, self._scenario = m, scenario

    def start(self) -> None:
        """Start the emulator (READY high), then the controller (RUN high)."""
        self._connected()
        self.emu_windows, self.ctrl_windows, self.errors = [], [], []
        self._request(self.emu, Type.START)
        try:
            self._request(self.ctrl, Type.START)
        except HilError:
            self._request(self.emu, Type.STOP)
            raise

    def stop(self) -> None:
        """Stop the controller, then the emulator."""
        self._request(self.ctrl, Type.STOP)
        self._request(self.emu, Type.STOP)

    def set_param(self, name: str, value: float) -> int:
        """ctrl_param on the controller: 0 accepted, -1 unknown name, -2 not changeable now."""
        p = self._request(self.ctrl, Type.PARAM_SET, proto.pack_param_set(name, value), reply=Type.PARAM_REPLY)
        return proto.unpack_param_reply(p)[1]

    def command(self, mode: Literal["torque", "speed"], value: float) -> None:
        """ctrl_command: torque in N*m or speed in rpm, as Scenario.command_value."""
        if mode == "speed":
            self._request(self.ctrl, Type.COMMAND, proto.pack_command(1, value * RPM))
        else:
            self._request(self.ctrl, Type.COMMAND, proto.pack_command(0, value))

    def live(self) -> LiveStats | None:
        """The newest statistics of both boards when either sent any since the last call, else None."""
        self._new_emu = self._new_ctrl = None
        self._drain(self.emu)
        self._drain(self.ctrl)
        if self._new_emu is None and self._new_ctrl is None:
            return None
        return LiveStats(self.emu_windows[-1] if self.emu_windows else None,
                         self.ctrl_windows[-1] if self.ctrl_windows else None)

    def capture(self, n_steps: int) -> Capture:
        """Record n_steps emulator steps of the running session. Valid only when every packet arrived in sequence
        with no bad frame on the link, all n_steps samples are there in consecutive steps and the emulator reports
        the capture valid; otherwise the traces are left empty (a gap is never filled)."""
        if self._m is None or self._scenario is None:
            raise HilError("not configured")
        if n_steps < 1:
            raise ValueError("n_steps must be at least 1")
        q = self._m.n_phases
        bad0, errors0 = self.emu.bad_frames, len(self.errors)
        seq = self.emu.send(Type.CAPTURE_REQ, proto.CAPTURE_REQ.pack(n_steps))
        capture_types = (Type.CAPTURE_HDR, Type.CAPTURE_DATA, Type.CAPTURE_END)
        hdr, parts, seqs, end = None, [], [], None
        deadline = time.monotonic() + n_steps * EMU_DT + 10.0
        while end is None and (left := deadline - time.monotonic()) > 0:
            f = self._wait(self.emu, lambda f: f[0] in capture_types or (f[0] == Type.ERROR and f[1] == seq), left)
            if f is None:
                break
            t, s, p = f
            if t == Type.ERROR:
                raise HilError(f"emulator: {p.decode(errors='replace')}")
            if t == Type.CAPTURE_HDR:
                hdr = proto.unpack_capture_hdr(p)
            elif t == Type.CAPTURE_DATA:
                seqs.append(s)
                parts.append(proto.unpack_capture_data(p)[1])
            else:
                end = (s, *proto.CAPTURE_END.unpack(p))
        bad = self.emu.bad_frames - bad0
        reason = _capture_problem(n_steps, hdr, seqs, parts, end, bad, self.errors[errors0:])
        none = SimResult({}, _nan_summary(q), self._scenario, "", "", "")
        if reason and (hdr is None or reason != _EMU_INVALID):
            return Capture(none, False, reason)
        samples = np.concatenate(parts)
        traces = capture_traces(hdr, samples)
        res = SimResult(traces, capture_summary(traces, self._m.resistance), self._scenario, "", "", "")
        clipped = float(np.mean(np.any(np.abs(samples["i"][:, :q].astype(np.int32)) >= 32767, axis=1)))
        return Capture(res, not reason, reason, clipped)

    def close(self) -> None:
        self.emu.close()
        self.ctrl.close()


_EMU_INVALID = "the emulator marked the capture invalid (an overrun, a full ring or a stop while it recorded)"


def _capture_problem(n_steps, hdr, seqs, parts, end, bad, errors) -> str:
    """Why a capture is not valid ("" when it is). Missing or broken data come first; _EMU_INVALID means the data are
    complete but the emulator saw a fault while recording."""
    if hdr is None:
        return "no capture header received"
    expected = end[0] if end is not None else (max(seqs) + 1 if seqs else 0)
    missing = sorted(set(range(expected)) - set(seqs))
    if missing:
        return f"sequence gap: CAPTURE_DATA {missing[0]} missing ({len(missing)} packets)" + (
            f", {bad} bad frames" if bad else "")
    if seqs != list(range(len(seqs))):
        return "CAPTURE_DATA out of sequence"
    if bad:
        return f"{bad} bad frame{'s' if bad != 1 else ''} on the link during the capture"
    if end is None:
        return "no capture end received" + (f" ({errors[0]})" if errors else "")
    n = sum(len(p) for p in parts)
    if n < n_steps or end[2] < n_steps:
        return f"short capture: {n} of {n_steps} samples"
    steps = np.concatenate(parts)["step"].astype(np.int64)
    if np.any(np.diff(steps) != 1):
        return f"step jump after sample {int(np.flatnonzero(np.diff(steps) != 1)[0])}"
    if not end[1]:
        return _EMU_INVALID
    return ""


def run_hil(session: HilSession, m: MotorData, controller: str, scenario: Scenario, *, settle_s: float = 0.2) -> SimResult:
    """Configure, start, settle, capture `scenario.duration` of steps, stop. The result's traces and summary come
    from the capture (summary over its second half); `hil` is `capture_health` of the run."""
    info = session.info or session.connect()
    session.configure(m, scenario, info.modes)
    n = round(scenario.duration / EMU_DT)
    session.start()
    try:
        session.wait(settle_s)
        cap = session.capture(n)
        session.wait(0.06)               # the window in which the capture ended
    except BaseException:
        try:
            session.stop()
        except HilError:
            pass                         # the run's own error is the one to report
        raise
    session.stop()
    return replace(cap.result, controller=controller, hil=capture_health(session, cap, scenario.resolved_isr_hz))


def capture_health(session: HilSession, cap: Capture, isr_hz: float) -> dict:
    """The `SimResult.hil` block of a capture: the health numbers over the session's live windows since `start`, the
    measured controller clock, `window_s` (the summary's window in s since the controller's start, for the matched
    SIL: compare.matched_scenario(..., end_s=window_s[1])), `valid` and `reason`."""
    ew, cw = session.emu_windows, session.ctrl_windows
    t = cap.result.traces.get("t")
    # the summary's window, the second half of the captured steps, in s since the controller's start
    window = (float(t[len(t) // 2]), float(t[-1]) + EMU_DT) if t is not None and len(t) else None

    def mean(xs):
        xs = [x for x in xs if math.isfinite(x)]
        return float(np.mean(xs)) if xs else math.nan

    ratio, measured, spread = clock_stats([w.trigger_hz for w in ew], isr_hz)
    hil = {
        "step_mean_us": mean([w.step_mean_us for w in ew]),
        "step_max_us": max((w.step_max_us for w in ew), default=math.nan),
        "overruns": ew[-1].overruns if ew else None,
        "dropped": ew[-1].dropped if ew else None,
        "edge_jitter_ns": mean([w.edge_jitter_ns for w in ew]),
        "latency_us": mean([w.latency_us for w in ew]),
        "isr_mean_us": mean([w.isr_mean_us for w in cw if w.state & proto.CTRL_RUNNING]),
        "isr_max_us": max((w.isr_max_us for w in cw), default=math.nan),
        "isr_overruns": cw[-1].isr_overruns if cw else None,
        "clock_ratio": ratio,
        "clock_measured": measured,
        "clock_spread_ppm": spread,
        "bad_frames": session.emu.bad_frames + session.ctrl.bad_frames,
        "capture_clipped": cap.clipped,
        "window_s": window,
        "errors": list(session.errors),
    }
    reason = cap.reason
    if not reason:
        if not ew or not cw:
            reason = "no live statistics from both boards"
        elif hil["overruns"] or hil["isr_overruns"] or hil["dropped"]:
            reason = (f"overruns {hil['overruns']}, ISR overruns {hil['isr_overruns']}, dropped {hil['dropped']}")
        elif session.errors:
            reason = f"a board reported: {session.errors[0]}"
    hil["valid"] = not reason
    hil["reason"] = reason
    return hil
