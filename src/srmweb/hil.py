"""The live HIL session: one rig per app, loopback host only.

HilSession is not thread-safe, so every call on it runs under one lock; the event stream polls `live()` under the same
lock, and a poll only drains frames that have already arrived. Captures are stored as `<cache_dir>/sil/hil/<id>.npz`
plus its `.json` sidecar (srmsil.run.save); the matched SIL run of a compared capture is `<id>.sil.npz` beside it."""
from __future__ import annotations

import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from fastapi import HTTPException

from srmsil import run as sil_run
from srmsil.hil import HilError
from srmsil.hil.build import check_sources
from srmsil.hil.compare import compare, match_plan, refused
from srmsil.hil.config import HilModes
from srmsil.hil.session import HilSession, LiveStats, capture_health, check_build
from srmsil.hil.transport import SerialTransport, Transport, discover
from srmsil.tables import MotorData
from srmweb.config import Settings, is_loopback
from srmweb.jobs import HIL_REFUSED
from srmweb.schemas import ComparisonOut, HilCaptureOut, HilOpenIn, HilParamOut, HilSessionOut
from srmweb.serialize import to_json

NOT_OPEN = "no HIL session is open"
PARAM_MESSAGES = {-1: "unknown parameter", -2: "not changeable while running"}
POLL_S = 0.05                     # the event stream's poll period (20 Hz)
END_WAIT_S = 0.06                 # live window in which a capture ends, kept for its health numbers
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
    ports). `flashed(case_id, controller)` is the firmware hash of the newest finished Build & Flash of that case and
    controller (None when there is none); a session opens only when both boards run it."""

    def __init__(self, settings: Settings, transports: Callable[[], tuple[Transport, Transport]],
                 flash_active: Callable[[], bool], flashed: Callable[[str, str], int | None]):
        self.settings, self._transports, self._flash_active = settings, transports, flash_active
        self._flashed = flashed
        self.gate = threading.Lock()
        self._lock = threading.Lock()
        self._session: HilSession | None = None
        self._out: HilSessionOut | None = None
        self._live: LiveStats | None = None
        self._started = 0.0               # monotonic time just before the last Start
        self._last_change: float | None = None   # s after that Start of the last accepted param or command change
        self._compare_locks: dict[str, threading.Lock] = {}
        self._comparing = 0
        self._compare_guard = threading.Lock()

    def comparing(self) -> bool:
        """True while a compare is running (it writes the matched SIL run into the cache)."""
        with self._compare_guard:
            return self._comparing > 0

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
        """Connect to both boards, check that they run the case's newest Build & Flash of the controller and that the
        controller's sources, the case's tables and the scenario's build settings still give that build, and configure
        them for the case's motor and the scenario. HilError (no rig, mode mismatch, another build on a board, a
        setting the HIL does not emulate) and the scenario rules give 409 with the error's text."""
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
                flashed = self._flashed(case_id, body.controller)
                check_build(info, flashed)
                check_sources(body.controller, motor, body.scenario, body.modes, flashed)
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
            started = time.monotonic()
            s.start()
            self._started, self._last_change = started, None
            return self._update(running=True)
        return self._call(call)

    def stop(self) -> HilSessionOut:
        def call(s: HilSession) -> HilSessionOut:
            s.stop()
            return self._update(running=False)
        return self._call(call)

    def _changed(self) -> None:
        """Note the time since Start of an accepted change made while running (before Start it is in the scenario)."""
        if self._out.running:
            self._last_change = time.monotonic() - self._started

    def param(self, name: str, value: float) -> HilParamOut:
        """ctrl_param on the controller; an accepted value is kept in the session's scenario for the matched SIL."""
        def call(s: HilSession) -> HilParamOut:
            status = s.set_param(name, value)
            if status == 0:
                sc = self._out.scenario
                self._update(scenario=sc.model_copy(update={"params": {**sc.params, name: value}}))
                self._changed()
                return HilParamOut(status=0)
            return HilParamOut(status=status, message=PARAM_MESSAGES.get(status, "refused"))
        return self._call(call)

    def command(self, mode: str, value: float) -> HilSessionOut:
        """ctrl_command; the command is kept in the session's scenario for the matched SIL."""
        def call(s: HilSession) -> HilSessionOut:
            s.command(mode, value)
            self._changed()
            return self._update(scenario=self._out.scenario.model_copy(
                update={"command_mode": mode, "command_value": value}))
        return self._call(call)

    def capture(self, n_steps: int) -> HilCaptureOut:
        """Record n_steps of the running session and store it with its health numbers (`capture_health`), the case,
        the modes and `last_change_s` (match_plan); 409 before Start."""
        check_loopback(self.settings)
        out = self._out
        if out is not None and not out.running:
            raise HTTPException(409, "start the run before capturing")

        def call(s: HilSession) -> HilCaptureOut:
            cap = s.capture(n_steps)
            s.wait(END_WAIT_S)
            out = self._out
            hil = {**capture_health(s, cap, out.scenario.resolved_isr_hz), "case_id": out.case_id,
                   "modes": out.modes.model_dump(), "last_change_s": self._last_change}
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
        """The capture against its matched SIL run (srmsil.hil.compare.match_plan), which runs once and is stored
        beside it with its start `t0` in its hil block; `motor_of(case_id, bus_voltage)` is the case's motor. It needs
        no open session. A capture that cannot be matched, or a SIL run that fails, gives passed False and the
        reason."""
        path = self.capture_file(capture_id)
        with self._compare_guard:
            self._comparing += 1
            lock = self._compare_locks.setdefault(capture_id, threading.Lock())
        try:
            with lock:              # one SIL run per capture; concurrent compares wait for it
                return ComparisonOut(**to_json(self._compare(path, capture_id, motor_of)))
        finally:
            with self._compare_guard:
                self._comparing -= 1

    def _compare(self, path: Path, capture_id: str, motor_of: Callable[[str, float | None], MotorData]):
        hil = sil_run.load(path)
        h = hil.hil
        if not h["valid"]:
            return refused(hil, f"HIL run not valid: {h['reason']}")
        sil_file = self.dir / f"{capture_id}.sil.npz"
        m = motor_of(h["case_id"], hil.scenario.bus_voltage)
        if sil_file.is_file():
            sil = sil_run.load(sil_file)
            return compare(hil, sil, m=m, t0=sil.hil["t0"])
        plan = match_plan(hil, HilModes(**h["modes"]), m)
        if plan.scenario is None:
            return refused(hil, plan.reason)
        try:
            sil = sil_run.run(m, hil.controller, plan.scenario, cache_dir=self.settings.cache_dir)
        except (sil_run.SimError, ValueError) as exc:
            return refused(hil, f"the matched SIL run failed: {exc}")
        sil = replace(sil, hil={"t0": plan.t0})
        sil_run.save(sil, sil_file)
        return compare(hil, sil, m=m, t0=plan.t0)

    def poll(self) -> dict | None:
        """The session and the newest live statistics of both boards; None when no session is open."""
        with self._lock:
            if self._session is None:
                return None
            self._live = self._session.live() or self._live
            last = self._live
            return {"session": self._out.model_dump(mode="json"), "emu": to_json(last.emu) if last else None,
                    "ctrl": to_json(last.ctrl) if last else None}
