"""The live HIL session: one rig per app, loopback host only.

HilSession is not thread-safe, so every call on it runs under one lock; the event stream polls `live()` under the same
lock, and a poll only drains frames that have already arrived. Captures are stored as `<cache_dir>/sil/hil/<id>.npz`
plus its `.json` sidecar (srmsil.run.save); the matched SIL run of a compared capture is `<id>.sil.npz` beside it."""
from __future__ import annotations

import re
import threading
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from fastapi import HTTPException

from srmsil import run as sil_run
from srmsil.hil import HilError
from srmsil.hil.compare import compare, matched_scenario
from srmsil.hil.config import HilModes
from srmsil.hil.session import HilSession, LiveStats, capture_health
from srmsil.hil.transport import SerialTransport, Transport, discover
from srmsil.tables import MotorData
from srmweb.config import Settings, is_loopback
from srmweb.jobs import HIL_REFUSED
from srmweb.schemas import ComparisonOut, HilCaptureOut, HilOpenIn, HilParamOut, HilSessionOut
from srmweb.serialize import to_json

NOT_OPEN = "no HIL session is open"
PARAM_MESSAGES = {-1: "unknown parameter", -2: "not changeable while running"}
POLL_S = 0.05                     # the event stream's poll period (20 Hz)
SETTLE_S = 0.06                   # live window in which a capture ends, kept for its health numbers
_CAPTURE_ID = re.compile(r"[0-9a-f]{32}")


def serial_transports() -> tuple[Transport, Transport]:
    """(emulator, controller) serial links of the first Teensy and ST-LINK found."""
    ports = discover()
    if ports.teensy is None or ports.stlink is None:
        raise HilError(f"rig not found: Teensy port {ports.teensy}, ST-LINK port {ports.stlink}")
    emu = SerialTransport(ports.teensy)
    try:
        return emu, SerialTransport(ports.stlink)
    except BaseException:
        emu.close()
        raise


def check_loopback(settings: Settings) -> None:
    if not is_loopback(settings.host):
        raise HTTPException(403, HIL_REFUSED)


class HilManager:
    """The app's one HIL session. `flash_active()` is true while a `hil_flash` job is queued or running; `gate` is held
    while a flash job is submitted and while a session opens, so the two never overlap (flashing re-enumerates the
    ports)."""

    def __init__(self, settings: Settings, transports: Callable[[], tuple[Transport, Transport]],
                 flash_active: Callable[[], bool]):
        self.settings, self._transports, self._flash_active = settings, transports, flash_active
        self.gate = threading.Lock()
        self._lock = threading.Lock()
        self._session: HilSession | None = None
        self._out: HilSessionOut | None = None
        self._live: LiveStats | None = None

    @property
    def dir(self) -> Path:
        return self.settings.cache_dir / "sil" / "hil"

    def is_open(self) -> bool:
        return self._session is not None

    def _check(self) -> HilSession:
        """The open session (call with the lock held); 403 off loopback, 409 when none is open."""
        check_loopback(self.settings)
        if self._session is None:
            raise HTTPException(409, NOT_OPEN)
        return self._session

    def open(self, case_id: str, body: HilOpenIn, motor: MotorData) -> HilSessionOut:
        """Connect to both boards and configure them for the case's motor and the scenario. HilError (no rig, mode
        mismatch, a setting the HIL does not emulate) and the scenario rules give 409 with the error's text."""
        check_loopback(self.settings)
        with self.gate, self._lock:
            if self._session is not None:
                raise HTTPException(409, "a HIL session is already open; close it first")
            if self._flash_active():
                raise HTTPException(409, "a Build & Flash job is queued or running; wait for it")
            try:
                session = HilSession(*self._transports())
            except HilError as exc:
                raise HTTPException(409, str(exc)) from exc
            try:
                info = session.connect()
                session.configure(motor, body.scenario, body.modes)
            except (HilError, ValueError) as exc:
                session.close()
                raise HTTPException(409, str(exc)) from exc
            except BaseException:
                session.close()
                raise
            self._session, self._live = session, None
            self._out = HilSessionOut(case_id=case_id, controller=body.controller, modes=body.modes,
                                      scenario=body.scenario, emulator_hash=info.emulator_hash,
                                      controller_hash=info.controller_hash, running=False)
            return self._out

    def close(self) -> None:
        """Stop both boards and close the links; nothing happens when no session is open."""
        check_loopback(self.settings)
        with self._lock:
            session, self._session, self._out = self._session, None, None
            if session is None:
                return
            try:
                session.stop()
            except HilError:
                pass                     # the links close either way
            finally:
                session.close()

    def _call(self, fn: Callable[[HilSession], object]):
        with self._lock:
            session = self._check()
            try:
                return fn(session)
            except (HilError, ValueError) as exc:
                raise HTTPException(409, str(exc)) from exc

    def _update(self, **fields) -> HilSessionOut:
        self._out = self._out.model_copy(update=fields)
        return self._out

    def start(self) -> HilSessionOut:
        def call(s: HilSession) -> HilSessionOut:
            s.start()
            return self._update(running=True)
        return self._call(call)

    def stop(self) -> HilSessionOut:
        def call(s: HilSession) -> HilSessionOut:
            s.stop()
            return self._update(running=False)
        return self._call(call)

    def param(self, name: str, value: float) -> HilParamOut:
        """ctrl_param on the controller; an accepted value is kept in the session's scenario for the matched SIL."""
        def call(s: HilSession) -> HilParamOut:
            status = s.set_param(name, value)
            if status == 0:
                sc = self._out.scenario
                self._update(scenario=sc.model_copy(update={"params": {**sc.params, name: value}}))
                return HilParamOut(status=0)
            return HilParamOut(status=status, message=PARAM_MESSAGES.get(status, "refused"))
        return self._call(call)

    def command(self, mode: str, value: float) -> HilSessionOut:
        """ctrl_command; the command is kept in the session's scenario for the matched SIL."""
        def call(s: HilSession) -> HilSessionOut:
            s.command(mode, value)
            return self._update(scenario=self._out.scenario.model_copy(
                update={"command_mode": mode, "command_value": value}))
        return self._call(call)

    def capture(self, n_steps: int) -> HilCaptureOut:
        """Record n_steps of the running session and store it with its health numbers (`capture_health`)."""
        def call(s: HilSession) -> HilCaptureOut:
            cap = s.capture(n_steps)
            s.wait(SETTLE_S)
            out = self._out
            hil = {**capture_health(s, cap, out.scenario.resolved_isr_hz), "case_id": out.case_id,
                   "modes": out.modes.model_dump()}
            res = replace(cap.result, scenario=out.scenario, controller=out.controller, hil=hil)
            capture_id = uuid.uuid4().hex
            self.dir.mkdir(parents=True, exist_ok=True)
            sil_run.save(res, self.dir / f"{capture_id}.npz")
            return HilCaptureOut(capture_id=capture_id, valid=hil["valid"], reason=hil["reason"], clipped=cap.clipped)
        return self._call(call)

    def capture_file(self, capture_id: str) -> Path:
        """The capture's npz; 403 off loopback, 404 for an unknown id."""
        check_loopback(self.settings)
        path = self.dir / f"{capture_id}.npz"
        if not _CAPTURE_ID.fullmatch(capture_id) or not path.is_file():
            raise HTTPException(404, f"no capture {capture_id}")
        return path

    def compare(self, capture_id: str, motor_of: Callable[[str, float | None], MotorData]) -> ComparisonOut:
        """The capture against its matched SIL run (srmsil.hil.compare), which is run once over the capture's window
        and stored beside it; `motor_of(case_id, bus_voltage)` is the case's motor. It needs no open session."""
        hil = sil_run.load(self.capture_file(capture_id))
        h = hil.hil
        if not h["valid"]:
            return ComparisonOut(d_torque_pct=None, d_irms_pct=None, d_ripple_pts=None, passed=False,
                                 clock_ratio=h.get("clock_ratio"), clock_measured=bool(h.get("clock_measured")),
                                 reason=f"HIL run not valid: {h['reason']}")
        sil_file = self.dir / f"{capture_id}.sil.npz"
        if sil_file.is_file():
            sil = sil_run.load(sil_file)
        else:
            if h.get("latency_us") is None:
                raise HTTPException(409, "the capture has no measured output latency to match")
            m = motor_of(h["case_id"], hil.scenario.bus_voltage)
            scenario = matched_scenario(hil.scenario, h["latency_us"] * 1e-6, HilModes(**h["modes"]),
                                        h["clock_ratio"], m=m, end_s=h["window_s"][1])
            try:
                sil = sil_run.run(m, hil.controller, scenario, cache_dir=self.settings.cache_dir)
            except (sil_run.SimError, ValueError) as exc:
                raise HTTPException(422, str(exc)) from exc
            sil_run.save(sil, sil_file)
        return ComparisonOut(**to_json(compare(hil, sil)))

    def poll(self) -> dict | None:
        """The session and the newest live statistics of both boards; None when no session is open."""
        with self._lock:
            if self._session is None:
                return None
            self._live = self._session.live() or self._live
            last = self._live
            return {"session": self._out.model_dump(mode="json"), "emu": to_json(last.emu) if last else None,
                    "ctrl": to_json(last.ctrl) if last else None}
