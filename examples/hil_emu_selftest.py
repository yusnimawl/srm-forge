"""Bench self-test of the Teensy emulator without the controller board.

The emulator runs the analytic motor at a fixed 1000 rpm on its software gate pattern (phase A, both switches, 20 kHz,
50 %), reports its live statistics, records a buffered and a streamed capture, and the captured phase-A current is
compared at the step instants with srmsil.emumodel.run_model on the same edges.

    $env:PYTHONPATH="src;tests;tests/sil"; python examples\\hil_emu_selftest.py [COM4]

pyserial is taken from hil/.runtime when the interpreter has none.
"""
from __future__ import annotations

import struct
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.path.append(str(ROOT / "hil" / ".runtime" / "Lib" / "site-packages"))
    import serial
    from serial.tools import list_ports

from sil_fixtures import analytic_motor

from srmsil.emumodel import EDGE_DTYPE, run_model
from srmsil.hil import proto
from srmsil.hil.config import sensor_chain
from srmsil.hil.proto import Type
from srmsil.scenario import Scenario
from srmsil.tables import emu_tables

F_CPU = float(sys.argv[2]) if len(sys.argv) > 2 else 912e6
STEP = proto.EMU_DT
PERIOD = round(F_CPU / 20_000)                   # cycles: 20 kHz (emu.h EMU_SELFTEST_HZ), 50 % duty
ON, OFFSET = PERIOD // 2, 1000                   # first rise 1000 cycles into step 0 (emu.h EMU_SELFTEST_OFFSET)
STEP_TICKS = round(F_CPU * STEP)


class Link:
    def __init__(self, port: str):
        self.s = serial.Serial(port, timeout=0.05)
        self.buf = bytearray()
        self.seq = 0
        self.bad = 0

    def send(self, t: int, payload: bytes = b"") -> int:
        self.seq += 1
        self.s.write(proto.frame(t, self.seq, payload))
        return self.seq

    def frames(self, timeout: float):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            data = self.s.read(max(1, self.s.in_waiting))
            self.buf += data
            while (k := self.buf.find(0)) >= 0:
                raw, self.buf = bytes(self.buf[:k]), self.buf[k + 1:]
                if raw:
                    try:
                        frame = proto.unframe(raw)
                    except proto.ProtoError:
                        self.bad += 1          # e.g. the tail of a frame from before the port was opened
                        continue
                    yield frame

    def request(self, t: int, payload: bytes = b"", timeout: float = 2.0):
        seq = self.send(t, payload)
        for ft, fs, fp in self.frames(timeout):
            if fs == seq and ft in (t, Type.ERROR, Type.BUILD_INFO):
                if ft == Type.ERROR:
                    raise RuntimeError(fp.decode())
                return fp
        raise TimeoutError(f"no reply to {Type(t).name}")


def find_port() -> str:
    for p in list_ports.comports():
        if p.vid == 0x16C0:
            return p.device
    raise SystemExit("no Teensy found")


def config(m, scn: Scenario, tab, capture_steps: int) -> bytes:
    c = dict.fromkeys(proto.EMU_CONFIG_FIELDS, 0)
    sc = scn.converter
    c.update(resistance=m.resistance, bus_voltage=m.bus_voltage, speed=scn.speed_rpm * 2 * np.pi / 60,
             theta0=scn.theta0, inertia=scn.inertia, v_switch=sc.v_switch, v_diode=sc.v_diode,
             dead_time=sc.dead_time, turn_on_delay=sc.turn_on_delay, turn_off_delay=sc.turn_off_delay,
             theta_step=tab.theta_step, psi_step=tab.psi_step, psi_max=tab.psi_max, i_max=tab.i_max,
             n_theta=tab.current.shape[0], n_psi=tab.current.shape[1], capture_steps=capture_steps,
             n_phases=m.n_phases, n_rotor_poles=m.n_rotor_poles, mode=0)
    se = scn.sensors
    # output stage: the shared sensor chain (srmsil.hil.config.sensor_chain); the resolver and encoder settings of the
    # scenario
    c.update(sensor_chain(m, scn))
    c.update(volt_rc_tau=scn.adc.volt_rc_tau, encoder_cpr=se.encoder_cpr, encoder_offset=se.encoder_offset,
             encoder_ecc_amp=se.encoder_ecc_amp, encoder_ecc_harmonic=se.encoder_ecc_harmonic,
             rdc_bits=se.resolver_bits, resolver_pole_pairs=se.resolver_pole_pairs,
             resolver_gain_mismatch=se.resolver_gain_mismatch, resolver_phase_error=se.resolver_phase_error)
    return proto.pack_emu_config(c)


def capture(link: Link, n: int, live: list):
    link.send(Type.CAPTURE_REQ, proto.CAPTURE_REQ.pack(n))
    hdr, parts, seqs, end = None, [], [], None
    t_start = time.monotonic()
    for t, s, p in link.frames(30.0):
        if t == Type.CAPTURE_HDR:
            hdr = proto.unpack_capture_hdr(p)
        elif t == Type.CAPTURE_DATA:
            seqs.append(s)
            parts.append(proto.unpack_capture_data(p)[1])
        elif t == Type.CAPTURE_END:
            end = proto.CAPTURE_END.unpack(p)
            break
        elif t == Type.LIVE_EMU:
            live.append(proto.unpack_live_emu(p))
        elif t == Type.ERROR:
            raise RuntimeError(p.decode())
    wall = time.monotonic() - t_start
    samples = np.concatenate(parts) if parts else np.zeros(0, proto.SAMPLE_DTYPE)
    gap = seqs != list(range(len(seqs)))
    return hdr, samples, end, gap, wall


def main() -> None:
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    m = analytic_motor()
    scn = Scenario(speed_rpm=1000.0, duration=STEP)
    tab = emu_tables(m)
    link = Link(port)
    info = proto.unpack_build_info(link.request(Type.HELLO))
    print("build info", info)
    link.request(Type.STOP)
    link.request(Type.EMU_CONFIG, config(m, scn, tab, 8000))
    for which, arr in ((0, tab.current), (1, tab.torque)):
        flat = np.ascontiguousarray(arr, np.float32).ravel()
        for off in range(0, flat.size, proto.TABLE_CHUNK_FLOATS):
            link.send(Type.TABLE_CHUNK, proto.pack_table_chunk(which, off, flat[off:off + proto.TABLE_CHUNK_FLOATS]))
    link.request(Type.COMMAND, proto.pack_command(proto.CMD_EMU_SELFTEST_PHASES, 1))
    link.request(Type.COMMAND, proto.pack_command(proto.CMD_EMU_SELFTEST, 0.5))
    link.request(Type.START)
    live: list = []
    for t, _, p in link.frames(1.0):
        if t == Type.LIVE_EMU:
            live.append(proto.unpack_live_emu(p))
    caps = {}
    for name, n in (("buffered", 8000), ("streamed", 100_000)):
        caps[name] = capture(link, n, live)
    for t, _, p in link.frames(0.5):
        if t == Type.LIVE_EMU:
            live.append(proto.unpack_live_emu(p))
    link.request(Type.STOP)
    print(f"bad frames skipped: {link.bad}")

    last = live[-1]
    print(f"live packets {len(live)}; last: step {last.step}, step mean {last.step_mean_us:.3f} us, "
          f"max {last.step_max_us:.3f} us, overruns {last.overruns}, dropped {last.dropped}, "
          f"jitter {last.edge_jitter_ns:.1f} ns, latency {last.latency_us:.3f} us, temp {last.temp_c:.1f} C, speed {last.speed_rpm:.2f} rpm, "
          f"mean torque {last.mean_torque:.5f}, i_rms {[round(x, 5) for x in last.i_rms]}")
    print("step_mean_us over windows: min %.3f max %.3f" % (min(x.step_mean_us for x in live),
                                                           max(x.step_mean_us for x in live)))
    n_model = max(int(c[1]["step"][-1]) for c in caps.values() if len(c[1])) + 2
    k = np.arange(0, n_model * STEP_TICKS // PERIOD + 2)
    edges = np.zeros(2 * len(k), EDGE_DTYPE)
    edges["t"][0::2], edges["gates"][0::2] = OFFSET + k * PERIOD, 0x0101
    edges["t"][1::2], edges["gates"][1::2] = OFFSET + k * PERIOD + ON, 0
    _, i_model = run_model(m, edges, scn.model_copy(update={"duration": n_model * STEP}), tick_s=1 / F_CPU,
                           cache_dir=Path(tempfile.gettempdir()) / "srm_emu_selftest", return_trace=True)
    for name, (hdr, s, end, gap, wall) in caps.items():
        if not len(s):
            print(f"{name}: no samples, end {end}")
            continue
        steps = s["step"].astype(np.int64)
        contiguous = bool(np.all(np.diff(steps) == 1))
        i_cap = s["i"][:, 0] * hdr.i_scale
        ref = i_model[0, steps]
        rms = lambda x: float(np.sqrt(np.mean(x ** 2)))  # noqa: E731
        err = rms(i_cap) / rms(ref) - 1
        print(f"{name}: {len(s)} samples (steps {steps[0]}..{steps[-1]}, contiguous {contiguous}), "
              f"end (valid, n) {end}, seq gap {gap}, wall {wall:.2f} s; phase-A rms capture {rms(i_cap):.5f} A, "
              f"model {rms(ref):.5f} A, err {err:.4%}, max |diff| {np.max(np.abs(i_cap - ref)):.5f} A "
              f"(i_scale {hdr.i_scale:.6f}), peak {np.max(ref):.4f} A")


if __name__ == "__main__":
    main()
