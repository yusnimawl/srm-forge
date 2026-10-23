"""Framed PC protocol, the Python mirror of hil/common/hil_proto.[ch].

Frame: COBS(type, seq LE, payload, CRC-16 LE) + 0x00; the CRC (CCITT-FALSE) covers type, seq and payload.
Payloads are little-endian and packed; each struct here has the size of its C struct.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

PROTOCOL_VERSION = 1
PAYLOAD_MAX = 1024
SAMPLES_PER_PACKET = 28
TABLE_CHUNK_FLOATS = 200
EMU_STEP_NS = 6000            # HIL_EMU_STEP_NS: the emulator step and the capture sample period
EMU_DT = EMU_STEP_NS / 1e9    # s


class Type(IntEnum):
    HELLO = 1
    BUILD_INFO = 2
    EMU_CONFIG = 3
    TABLE_CHUNK = 4
    PARAM_SET = 5
    PARAM_REPLY = 6
    COMMAND = 7
    START = 8
    STOP = 9
    LIVE_EMU = 10
    LIVE_CTRL = 11
    CAPTURE_REQ = 12
    CAPTURE_HDR = 13
    CAPTURE_DATA = 14
    CAPTURE_END = 15
    ERROR = 16


class ProtoError(Exception):
    """A malformed frame. `code` matches hil_unframe: -1 COBS, -2 CRC, -3 payload too long."""

    def __init__(self, code: int):
        super().__init__({-1: "COBS error", -2: "CRC error", -3: "payload too long"}.get(code, str(code)))
        self.code = code


def cobs_encode(data: bytes) -> bytes:
    out = bytearray([0])
    code_at, code = 0, 1
    for b in data:
        if b == 0:
            out[code_at] = code
            code_at, code = len(out), 1
            out.append(0)
        else:
            out.append(b)
            code += 1
            if code == 0xFF:
                out[code_at] = code
                code_at, code = len(out), 1
                out.append(0)
    out[code_at] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    out = bytearray()
    r, n = 0, len(data)
    while r < n:
        code = data[r]
        r += 1
        if code == 0 or r + code - 1 > n:
            raise ProtoError(-1)
        chunk = data[r : r + code - 1]
        if 0 in chunk:
            raise ProtoError(-1)
        out += chunk
        r += code - 1
        if code != 0xFF and r < n:
            out.append(0)
    return bytes(out)


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def frame(type: int, seq: int, payload: bytes = b"") -> bytes:
    if len(payload) > PAYLOAD_MAX:
        raise ProtoError(-3)
    raw = struct.pack("<BH", type, seq) + payload
    return cobs_encode(raw + struct.pack("<H", crc16(raw))) + b"\x00"


def unframe(data: bytes, cap: int = PAYLOAD_MAX) -> tuple[int, int, bytes]:
    """Parse one frame (the trailing 0x00 is optional) into (type, seq, payload)."""
    if data.endswith(b"\x00"):
        data = data[:-1]
    if len(data) > PAYLOAD_MAX + 5 + (PAYLOAD_MAX + 5) // 254 + 2:
        raise ProtoError(-3)
    raw = cobs_decode(data)
    if len(raw) < 5:
        raise ProtoError(-1)
    if crc16(raw[:-2]) != struct.unpack("<H", raw[-2:])[0]:
        raise ProtoError(-2)
    if len(raw) - 5 > min(cap, PAYLOAD_MAX):
        raise ProtoError(-3)
    t, s = struct.unpack("<BH", raw[:3])
    return t, s, raw[3:-2]


BUILD_INFO = struct.Struct("<HBBBBI")
PARAM_SET = struct.Struct("<24sf")
PARAM_REPLY = struct.Struct("<24sb")
COMMAND = struct.Struct("<Bf")
CMD_EMU_SELFTEST = 2       # emulator command: software gate pattern, 20 kHz, duty = value (0 = off)
CMD_EMU_SELFTEST_PHASES = 3   # emulator command: phases of the pattern, value = bit mask (default 1, phase A)
CMD_CTRL_RESET = 4         # controller command: stop and reset the board (parameters and command back to the build's)
CAPTURE_REQ = struct.Struct("<I")       # n_steps; 0 = the config's capture_steps
CAPTURE_END = struct.Struct("<BI")
LIVE_EMU = struct.Struct("<I9f2I4f")
LIVE_CTRL = struct.Struct("<2fIf4ffIB")
CAPTURE_HDR = struct.Struct("<6fIB")
TABLE_CHUNK_HEAD = struct.Struct("<BIH")
TABLE_CHUNK = struct.Struct("<BIH200f")

SAMPLE_DTYPE = np.dtype([("step", "<u4"), ("i", "<i2", 4), ("psi", "<i2", 4), ("v", "<i2", 4), ("torque", "<i2"),
                         ("theta", "<u2"), ("omega", "<i2"), ("gates", "<u2")])
SAMPLE = struct.Struct("<I13hHhH")
assert SAMPLE.size == SAMPLE_DTYPE.itemsize == 36

# Same order as hil_emu_config_t: floats, then u32, then u8.
EMU_CONFIG_FLOATS = (
    "resistance", "bus_voltage", "speed", "theta0", "inertia", "friction", "load", "load_step", "load_step_time",
    "v_switch", "v_diode", "dead_time", "turn_on_delay", "turn_off_delay", "theta_step", "psi_step", "psi_max",
    "i_max", "adc_noise", "adc_offset_error", "adc_gain_error", "sensor_delay", "encoder_offset", "encoder_ecc_amp",
    "resolver_gain_mismatch", "resolver_phase_error", "ad7606_range_v", "ad7606_t_conv_us", "sense_v_per_a",
    "volt_divider", "volt_rc_tau", "dac_v_mid", "dac_v_per_a", "omega_max")
EMU_CONFIG_U32 = ("n_theta", "n_psi", "encoder_cpr", "capture_steps", "seed")
EMU_CONFIG_U8 = ("n_phases", "n_rotor_poles", "mode", "rdc_bits", "resolver_pole_pairs", "encoder_ecc_harmonic",
                 "resolver")
EMU_CONFIG_FIELDS = EMU_CONFIG_FLOATS + EMU_CONFIG_U32 + EMU_CONFIG_U8
EMU_CONFIG = struct.Struct(f"<{len(EMU_CONFIG_FLOATS)}f{len(EMU_CONFIG_U32)}I{len(EMU_CONFIG_U8)}B")

# Payload size per fixed-size type; absent types are empty or variable.
PAYLOAD_SIZE = {
    Type.BUILD_INFO: BUILD_INFO.size, Type.EMU_CONFIG: EMU_CONFIG.size, Type.TABLE_CHUNK: TABLE_CHUNK.size,
    Type.PARAM_SET: PARAM_SET.size, Type.PARAM_REPLY: PARAM_REPLY.size, Type.COMMAND: COMMAND.size,
    Type.LIVE_EMU: LIVE_EMU.size, Type.LIVE_CTRL: LIVE_CTRL.size, Type.CAPTURE_HDR: CAPTURE_HDR.size,
    Type.CAPTURE_REQ: CAPTURE_REQ.size, Type.CAPTURE_END: CAPTURE_END.size,
}


@dataclass(frozen=True)
class BuildInfo:
    protocol: int
    board: int              # 1 emulator, 2 controller
    current_sense: int      # 0 ad7606, 1 internal
    position: int           # 0 encoder, 1 ad2s1210, 2 both
    dac: int                # 0 none, 1 mcp4922 x2, 2 mcp4921 x4
    firmware_hash: int


@dataclass(frozen=True)
class LiveEmu:
    step: int
    mean_torque: float
    ripple_pct: float
    i_rms: tuple[float, ...]
    speed_rpm: float
    step_mean_us: float
    step_max_us: float
    overruns: int
    dropped: int
    edge_jitter_ns: float
    latency_us: float
    temp_c: float           # die temperature
    trigger_hz: float       # controller sample-trigger rate by the emulator's crystal (NaN below 2 triggers)


@dataclass(frozen=True)
class LiveCtrl:
    isr_mean_us: float
    isr_max_us: float
    isr_overruns: int
    command: float
    i_meas: tuple[float, ...]   # A rms over the window
    sample_us: float            # mean time from the trigger to ctrl_isr
    tx_dropped: int             # frames the controller could not queue, since boot
    state: int                  # CTRL_* bits


CTRL_RUNNING = 1        # the controller runs (RUN is high)
CTRL_READY = 2          # the READY input is high
CTRL_READY_STOP = 4     # READY fell during the last run and stopped it
CTRL_STALL_STOP = 8     # the last run stopped because the sample chain stalled
CTRL_INDEX = 16         # an encoder index pulse was seen since the start
CTRL_HANG_STOP = 32     # the last run stopped because ctrl_isr did not return


@dataclass(frozen=True)
class CaptureHeader:
    dt: float
    i_scale: float
    psi_scale: float
    v_scale: float
    t_scale: float
    omega_scale: float
    n_steps: int
    n_phases: int


def pack_build_info(b: BuildInfo) -> bytes:
    return BUILD_INFO.pack(b.protocol, b.board, b.current_sense, b.position, b.dac, b.firmware_hash)


def unpack_build_info(data: bytes) -> BuildInfo:
    return BuildInfo(*BUILD_INFO.unpack(data))


def _name(name: str) -> bytes:
    raw = name.encode()
    if len(raw) > 23:
        raise ValueError(f"parameter name longer than 23 bytes: {name!r}")
    return raw


def pack_param_set(name: str, value: float) -> bytes:
    return PARAM_SET.pack(_name(name), value)


def unpack_param_set(data: bytes) -> tuple[str, float]:
    raw, value = PARAM_SET.unpack(data)
    return raw.split(b"\0", 1)[0].decode(), value


def pack_param_reply(name: str, status: int) -> bytes:
    return PARAM_REPLY.pack(_name(name), status)


def unpack_param_reply(data: bytes) -> tuple[str, int]:
    raw, status = PARAM_REPLY.unpack(data)
    return raw.split(b"\0", 1)[0].decode(), status


def pack_command(mode: int, value: float) -> bytes:
    return COMMAND.pack(mode, value)


def unpack_command(data: bytes) -> tuple[int, float]:
    return COMMAND.unpack(data)


def unpack_live_emu(data: bytes) -> LiveEmu:
    f = LIVE_EMU.unpack(data)
    return LiveEmu(f[0], f[1], f[2], tuple(f[3:7]), *f[7:])


def pack_live_emu(s: LiveEmu) -> bytes:
    return LIVE_EMU.pack(s.step, s.mean_torque, s.ripple_pct, *s.i_rms, s.speed_rpm, s.step_mean_us, s.step_max_us,
                         s.overruns, s.dropped, s.edge_jitter_ns, s.latency_us, s.temp_c,
                         s.trigger_hz)


def unpack_live_ctrl(data: bytes) -> LiveCtrl:
    f = LIVE_CTRL.unpack(data)
    return LiveCtrl(f[0], f[1], f[2], f[3], tuple(f[4:8]), f[8], f[9], f[10])


def pack_live_ctrl(s: LiveCtrl) -> bytes:
    return LIVE_CTRL.pack(s.isr_mean_us, s.isr_max_us, s.isr_overruns, s.command, *s.i_meas, s.sample_us, s.tx_dropped, s.state)


def pack_capture_hdr(h: CaptureHeader) -> bytes:
    return CAPTURE_HDR.pack(h.dt, h.i_scale, h.psi_scale, h.v_scale, h.t_scale, h.omega_scale, h.n_steps, h.n_phases)


def unpack_capture_hdr(data: bytes) -> CaptureHeader:
    return CaptureHeader(*CAPTURE_HDR.unpack(data))


def pack_capture_data(first_step: int, samples: np.ndarray) -> bytes:
    if len(samples) > SAMPLES_PER_PACKET:
        raise ValueError("too many samples for one packet")
    return struct.pack("<I", first_step) + np.ascontiguousarray(samples, SAMPLE_DTYPE).tobytes()


def unpack_capture_data(data: bytes) -> tuple[int, np.ndarray]:
    if (len(data) - 4) % SAMPLE_DTYPE.itemsize:
        raise ValueError("capture data is not a whole number of samples")
    return struct.unpack_from("<I", data)[0], np.frombuffer(data, SAMPLE_DTYPE, offset=4).copy()


def pack_table_chunk(which: int, offset: int, values) -> bytes:
    v = np.zeros(TABLE_CHUNK_FLOATS, "<f4")
    v[: len(values)] = values
    return TABLE_CHUNK_HEAD.pack(which, offset, len(values)) + v.tobytes()


def unpack_table_chunk(data: bytes) -> tuple[int, int, np.ndarray]:
    which, offset, n = TABLE_CHUNK_HEAD.unpack_from(data)
    return which, offset, np.frombuffer(data, "<f4", count=n, offset=TABLE_CHUNK_HEAD.size).copy()


def pack_emu_config(cfg: dict) -> bytes:
    return EMU_CONFIG.pack(*(cfg[k] for k in EMU_CONFIG_FIELDS))


def unpack_emu_config(data: bytes) -> dict:
    return dict(zip(EMU_CONFIG_FIELDS, EMU_CONFIG.unpack(data)))
