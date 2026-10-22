"""The SIL scenario that matches a HIL run, and the HIL/SIL comparison against the acceptance bounds (spec D10)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from srmsil.hil.config import AD7606_SPI_HZ, AD7606_T_CONV_US, HilModes
from srmsil.run import SimResult
from srmsil.scenario import Scenario

TORQUE_TOL_PCT = 3.0
IRMS_TOL_PCT = 3.0
RIPPLE_TOL_PTS = 5.0


def sense_latency(modes: HilModes | str) -> float:
    """s from the sample trigger to the data in the controller: the AD7606 conversion plus its 8 x 16-bit SPI read;
    0 for the controller's internal ADCs."""
    cs = modes if isinstance(modes, str) else modes.current_sense
    return AD7606_T_CONV_US * 1e-6 + 8 * 16 / AD7606_SPI_HZ if cs == "ad7606" else 0.0


def matched_scenario(scenario: Scenario, latency_s: float, modes: HilModes, clock_ratio: float | None = None) -> Scenario:
    """`scenario` with the HIL's sensed-value delay (the emulator's measured output latency plus the sensing chain's)
    and the controller clock measured on the rig (1.0 when it was not measured)."""
    d = scenario.model_dump()
    d["sensors"]["delay"] = latency_s + sense_latency(modes)
    d["controller_clock"] = 1.0 if clock_ratio is None else clock_ratio
    return Scenario.model_validate(d)


@dataclass(frozen=True)
class Comparison:
    d_torque_pct: float      # HIL mean torque relative to the SIL's
    d_irms_pct: float        # HIL RMS phase current (rms over the phases) relative to the SIL's
    d_ripple_pts: float      # HIL ripple % minus the SIL's
    passed: bool
    clock_ratio: float | None
    clock_measured: bool


def _rel_pct(a: float, b: float) -> float:
    return 100 * (a - b) / abs(b) if b != 0 else math.nan


def _irms(r: SimResult) -> float:
    return float(np.sqrt(np.mean(np.asarray(r.summary.i_rms, float) ** 2)))


def compare(hil: SimResult, sil: SimResult) -> Comparison:
    """Differences of a HIL run from its matched SIL run. It passes when the HIL run is valid and the mean torque and
    RMS current are within 3 % and the ripple within 5 points."""
    h = hil.hil or {}
    dt = _rel_pct(hil.summary.mean_torque, sil.summary.mean_torque)
    di = _rel_pct(_irms(hil), _irms(sil))
    dr = hil.summary.ripple_pct - sil.summary.ripple_pct
    ok = (bool(h.get("valid")) and all(math.isfinite(x) for x in (dt, di, dr))
          and abs(dt) <= TORQUE_TOL_PCT and abs(di) <= IRMS_TOL_PCT and abs(dr) <= RIPPLE_TOL_PTS)
    return Comparison(dt, di, dr, ok, h.get("clock_ratio"), bool(h.get("clock_measured")))
