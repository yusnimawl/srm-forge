"""Board links: the Transport protocol, the USB serial transport and board discovery.

pyserial is imported when a port is opened or listed, so `srmsil.hil` loads without it."""

from __future__ import annotations

import importlib
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Protocol

from srmsil.hil import HilError
from srmsil.hil import proto

TEENSY_VID = 0x16C0
STLINK_VID = 0x0483
RX_BUFFER_BYTES = 1 << 22    # driver receive buffer asked for on Windows


class Transport(Protocol):
    bad_frames: int          # received frames that failed COBS, CRC or the length check

    def send(self, type: int, payload: bytes) -> int:
        """Send one frame; returns its sequence number."""

    def recv(self, timeout: float) -> tuple[int, int, bytes] | None:
        """The next good frame (type, seq, payload), or None after `timeout` s."""

    def close(self) -> None: ...


def _import(name: str):
    try:
        return importlib.import_module(name)
    except ImportError as e:
        raise HilError("pyserial is not installed; install the hil extra") from e


class SerialTransport:
    """A board's USB serial port. A reader thread only appends raw bytes to a buffer; `recv` splits it on 0x00 and
    unframes, so a slow consumer never makes the port overflow while frames are being decoded."""

    def __init__(self, port: str, baud: int = 921600):
        serial = _import("serial")
        try:
            self._port = serial.Serial(port, baud, timeout=0.05)
        except (OSError, ValueError) as e:
            raise HilError(f"cannot open {port}: {e}") from e
        if hasattr(self._port, "set_buffer_size"):
            self._port.set_buffer_size(rx_size=RX_BUFFER_BYTES, tx_size=1 << 16)
        self.bad_frames = 0
        self._seq = 0
        self._raw = bytearray()
        self._frames: deque[tuple[int, int, bytes]] = deque()
        self._lock = threading.Lock()
        self._data = threading.Event()
        self._closed = False
        self._error: Exception | None = None
        self._reader = threading.Thread(target=self._read_loop, name=f"hil-{port}", daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        while not self._closed:
            try:
                data = self._port.read(self._port.in_waiting or 1)
            except Exception as e:  # noqa: BLE001 - reported by the next recv
                self._error = e
                self._data.set()
                return
            if data:
                with self._lock:
                    self._raw += data
                self._data.set()

    def _parse(self) -> None:
        with self._lock:
            end = self._raw.rfind(0)
            if end < 0:
                return
            chunk = bytes(self._raw[: end + 1])
            del self._raw[: end + 1]
        for raw in chunk.split(b"\x00")[:-1]:
            if not raw:
                continue
            try:
                self._frames.append(proto.unframe(raw))
            except proto.ProtoError:
                self.bad_frames += 1

    def send(self, type: int, payload: bytes = b"") -> int:
        self._seq = (self._seq + 1) & 0xFFFF
        try:
            self._port.write(proto.frame(type, self._seq, payload))
        except Exception as e:  # noqa: BLE001 - pyserial raises its own and OS errors
            raise HilError(f"write failed: {e}") from e
        return self._seq

    def recv(self, timeout: float) -> tuple[int, int, bytes] | None:
        deadline = time.monotonic() + timeout
        while True:
            self._data.clear()
            self._parse()
            if self._frames:
                return self._frames.popleft()
            if self._error is not None:
                raise HilError(f"read failed: {self._error}")
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            self._data.wait(left)

    def close(self) -> None:
        self._closed = True
        self._reader.join(1.0)
        self._port.close()


@dataclass(frozen=True)
class RigPorts:
    teensy: str | None
    stlink: str | None


def discover() -> RigPorts:
    """The first Teensy (emulator) and ST-LINK (controller VCP) serial ports by USB vendor id."""
    list_ports = _import("serial.tools.list_ports")
    teensy = stlink = None
    for p in list_ports.comports():
        if p.vid == TEENSY_VID and teensy is None:
            teensy = p.device
        elif p.vid == STLINK_VID and stlink is None:
            stlink = p.device
    return RigPorts(teensy, stlink)
