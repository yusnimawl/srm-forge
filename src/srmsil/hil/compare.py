"""The SIL scenario that matches a HIL run, and the HIL/SIL comparison against the acceptance bounds (spec D10)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from srmsil.hil.config import HilModes, hil_adc
from srmsil.hil.proto import EMU_DT
from srmsil.run import TRACE_CAP, SimResult
from srmsil.scenario import Scenario
from srmsil.tables import MotorData

TORQUE_TOL_PCT = 3.0
IRMS_TOL_PCT = 3.0
RIPPLE_TOL_PTS = 5.0
SETTLE_S = 0.2           # s the matched SIL of a fixed-speed capture runs before the capture (and run_hil's settle)
RPM = 2 * math.pi / 60


def matched_scenario(scenario: Scenario, latency_s: float, modes: HilModes, clock_ratio: float | None = None, *,
                     m: MotorData, end_s: float | None) -> Scenario:
    """`scenario` as the HIL ran it, for the SIL:

    - Timing. The controller samples at the trigger (the carrier centre, the SIL's ISR instant): the AD7606 and the
      AD2S1210 latch the emulator's output there, and conversion and SPI only delay the start of ctrl_isr. Its
      compares are preloaded and load at the next underflow, one ISR period of the controller's clock later, so
      compute_delay = 1 / (isr_hz * r) in true time (r the measured clock ratio, 1 when None).
    - Sensed-value age. The emulator's output after step k holds the plant state at the end of the step (t_k) and
      appears D after it; a trigger at a random instant latches it at an age uniform in [D, D + dt] (dt = EMU_DT),
      mean D + dt/2. The measured `latency_us` is the time from the last gate edge of a step's window to the end of
      that step's output stage, (t_k - t_edge) + D; with gate edges asynchronous to the emulator steps, t_k - t_edge
      averages dt/2, so the mean latency is already D + dt/2. The SIL draws each sample's age from the same range:
      sensors.delay = latency_s - dt/2 (D, at least 0) and sensors.delay_jitter = dt. A chop decision near its
      threshold depends on where in that range the sample falls, which the mean age alone does not reproduce.
    - ADC. The controller's HAL constants and code range of the HIL sensing chain (`config.hil_adc`).
    - Duration. `end_s` (the end of the HIL capture since the controller's start, `hil["window_s"][1]`), so the SIL
      covers the HIL's window from the same start; None keeps the scenario's duration (a scenario that already runs
      from the controller's start to the end of the window). It has no default, so a caller with a window passes it."""
    d = scenario.model_dump()
    r = 1.0 if clock_ratio is None else clock_ratio
    d["controller_clock"] = r
    d["compute_delay"] = 1.0 / (scenario.resolved_isr_hz * r)
    d["sensors"]["delay"] = max(0.0, latency_s - EMU_DT / 2)
    d["sensors"]["delay_jitter"] = EMU_DT
    d["adc"] = hil_adc(modes, scenario, m).model_dump()
    if end_s is not None:
        d["duration"] = end_s
    return Scenario.model_validate(d)


@dataclass(frozen=True)
class Comparison:
    d_torque_pct: float      # HIL mean torque relative to the SIL's
    d_irms_pct: float        # HIL RMS phase current (rms over the phases) relative to the SIL's
    d_ripple_pts: float      # HIL ripple % minus the SIL's
    passed: bool
    clock_ratio: float | None
    clock_measured: bool
    reason: str = ""         # why it did not pass ("" when it passed)


def _rel_pct(a: float, b: float) -> float:
    return 100 * (a - b) / abs(b) if b != 0 else math.nan


def window_stats(r: SimResult, t_start: float, t_end: float) -> tuple[float, float, float]:
    """(mean torque, ripple %, RMS phase current over the phases) of the samples with t_start <= t < t_end."""
    t = r.traces["t"]
    w = (t >= t_start - 1e-12) & (t < t_end - 1e-12)
    if not w.any():
        return math.nan, math.nan, math.nan
    tq = r.traces["torque"][w]
    mean = float(np.mean(tq))
    ripple = 100 * float(np.max(tq) - np.min(tq)) / abs(mean) if abs(mean) > 1e-12 else math.nan
    i = r.traces["i"][:, w].astype(np.float64)
    return mean, ripple, float(np.sqrt(np.mean(i**2)))


def covers(r: SimResult, t_start: float, t_end: float) -> bool:
    """True when r's samples span [t_start, t_end): the first at or before t_start, the last within one sample period
    of t_end."""
    t = r.traces.get("t")
    if t is None or len(t) < 2:
        return False
    return bool(t[0] <= t_start + 1e-12 and t[-1] + (t[1] - t[0]) >= t_end - 1e-12)


def _summary_stats(r: SimResult) -> tuple[float, float, float]:
    s = r.summary
    return s.mean_torque, s.ripple_pct, float(np.sqrt(np.mean(np.asarray(s.i_rms, float) ** 2)))


@dataclass(frozen=True)
class MatchPlan:
    scenario: Scenario | None   # the matched SIL scenario; None when the capture cannot be matched
    t0: float                   # s since the controller's start at which the SIL starts
    reason: str = ""            # why there is no scenario


def match_plan(hil: SimResult, modes: HilModes, m: MotorData) -> MatchPlan:
    """The matched SIL of a capture taken in a live session (`hil.hil` from session.capture_health plus
    `last_change_s`, the time since Start of the last accepted parameter or command change, None for none).

    - Fixed speed: the SIL starts SETTLE_S before the capture (at Start when the capture began earlier), at the rotor
      angle the HIL had then, and runs to the end of the summary window; `compare(..., t0=plan.t0)` shifts the window.
      A change after the SIL's start cannot be matched.
    - Dynamic: the speed depends on the whole run, so the SIL runs from Start; a change while running cannot be
      matched.
    Either way the SIL must keep every step (at most TRACE_CAP steps of the scenario's dt). Invalid scenarios give a
    reason, never an exception."""
    h, sc = hil.hil or {}, hil.scenario
    win, t = h.get("window_s"), hil.traces.get("t")
    if not win or t is None or not len(t):
        return MatchPlan(None, 0.0, "the capture has no window")
    if h.get("latency_us") is None:
        return MatchPlan(None, 0.0, "the capture has no measured output latency to match")
    change = h.get("last_change_s")
    if sc.mode == "dynamic":
        t0 = 0.0
        if change is not None:
            return MatchPlan(None, t0, "parameters or command changed while running; a dynamic run is matched from "
                                       "Start, so capture after a fresh Start")
        if round(win[1] / sc.dt) > TRACE_CAP:
            return MatchPlan(None, t0, f"dynamic run captured too late for the matched SIL (capture within "
                                       f"{TRACE_CAP * sc.dt:g} s of Start)")
    else:
        t0 = max(0.0, float(t[0]) - SETTLE_S)
        if change is not None and change >= t0:
            return MatchPlan(None, t0, f"parameters or command changed within {SETTLE_S:g} s before the capture")
        if round((win[1] - t0) / sc.dt) > TRACE_CAP:
            return MatchPlan(None, t0, f"the capture is too long for the matched SIL at dt {sc.dt:g} s (at most "
                                       f"{TRACE_CAP * sc.dt - SETTLE_S:g} s)")
    try:
        start = Scenario.model_validate({**sc.model_dump(),
                                         "theta0": math.remainder(sc.theta0 + sc.speed_rpm * RPM * t0, 2 * math.pi)})
        scenario = matched_scenario(start, h["latency_us"] * 1e-6, modes, h.get("clock_ratio"), m=m,
                                    end_s=win[1] - t0)
    except ValueError as exc:
        return MatchPlan(None, t0, f"no matched SIL scenario: {exc}")
    return MatchPlan(scenario, t0)


def refused(hil: SimResult, reason: str) -> Comparison:
    """A comparison that did not run (the SIL could not be matched or run)."""
    h = hil.hil or {}
    n = math.nan
    return Comparison(n, n, n, False, h.get("clock_ratio"), bool(h.get("clock_measured")), reason)


def compare(hil: SimResult, sil: SimResult, *, t0: float = 0.0) -> Comparison:
    """Differences of a HIL run from its matched SIL run, both over the HIL's window (`hil["window_s"]`, times since
    the controller's start; the SIL's times are t0 earlier; the summaries when there is no window). It passes when the
    HIL run is valid, its capture did not clip, the SIL covers the window, and the mean torque and RMS current are
    within 3 % and the ripple within 5 points."""
    h = hil.hil or {}
    win = h.get("window_s")
    if win:
        win = (win[0] - t0, win[1] - t0)
    uncovered = bool(win) and not covers(sil, *win)
    reasons = ["SIL does not cover the HIL window"] if uncovered else []
    b = (math.nan,) * 3 if uncovered else window_stats(sil, *win) if win else _summary_stats(sil)
    a = _summary_stats(hil)
    dt, di, dr = _rel_pct(a[0], b[0]), _rel_pct(a[2], b[2]), a[1] - b[1]
    if not h.get("valid"):
        reasons.append(f"HIL run not valid: {h.get('reason') or 'no hil block'}")
    if h.get("capture_clipped"):
        reasons.append(f"capture clipped ({100 * h['capture_clipped']:.1f} % of samples)")
    if not all(math.isfinite(x) for x in (dt, di, dr)):
        if not uncovered:
            reasons.append("a difference is not finite")
    else:
        if abs(dt) > TORQUE_TOL_PCT:
            reasons.append(f"mean torque {dt:+.2f} % (limit {TORQUE_TOL_PCT:g} %)")
        if abs(di) > IRMS_TOL_PCT:
            reasons.append(f"RMS current {di:+.2f} % (limit {IRMS_TOL_PCT:g} %)")
        if abs(dr) > RIPPLE_TOL_PTS:
            reasons.append(f"ripple {dr:+.2f} points (limit {RIPPLE_TOL_PTS:g})")
    return Comparison(dt, di, dr, not reasons, h.get("clock_ratio"), bool(h.get("clock_measured")), "; ".join(reasons))
