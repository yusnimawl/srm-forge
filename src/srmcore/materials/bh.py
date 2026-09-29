"""B-H processing (spec §5.2): unit checks, origin, stacking factor, monotone H(B) interpolation and a
C¹ saturation tail. The result is the effective (stacked) single-valued law the solver uses."""
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicHermiteSpline, PchipInterpolator

from ..model.constants import MU0
from ..model.errors import InputError, ValidationIssue
from .schema import BHTable

# Below this |B| the reluctivity is taken as its B = 0 limit and dν/d(B²) as 0: the closed forms
# lose all precision to cancellation there, and the Jacobian term they feed scales with B².
B_SMALL = 1e-5
# At B = 1 T every soft-magnetic steel has H in this range; outside it the table is almost always
# in kA/m, Oe or mT rather than A/m / T.
H_AT_1T_RANGE = (5.0, 5000.0)
B_MAX_PLAUSIBLE = 3.0


def _error(rule: str, message: str) -> InputError:
    return InputError([ValidationIssue("bh", rule, message)])


def check_bh_units(h: np.ndarray, b: np.ndarray) -> None:
    if b.max() > B_MAX_PLAUSIBLE:
        raise _error("units", f"max B = {b.max():g} T is implausible; B must be in tesla (not mT or gauss)")
    if b.max() >= 1.0 and np.all(np.diff(b) > 0):
        h1 = float(np.interp(1.0, b, h))
        lo, hi = H_AT_1T_RANGE
        if not lo <= h1 <= hi:
            raise _error("units", f"H at 1 T = {h1:g} is outside {lo:g}..{hi:g}; H must be in A/m (not kA/m or Oe)")


def repair_monotone(h, b) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Drop every point that does not strictly increase both H and B over the last kept point.
    Returns the kept points and one line per dropped point, naming it exactly."""
    h, b = np.asarray(h, float), np.asarray(b, float)
    keep = [0]
    changes: list[str] = []
    for i in range(1, len(h)):
        if h[i] > h[keep[-1]] and b[i] > b[keep[-1]]:
            keep.append(i)
        else:
            changes.append(f"dropped point {i} (H={h[i]:g} A/m, B={b[i]:g} T): not above point {keep[-1]}")
    return h[keep], b[keep], changes


@dataclass(frozen=True)
class BHReport:
    added_origin: bool
    stacking_factor: float
    initial_relative_permeability: float
    join_b: float
    join_h: float
    tail_saturation_polarisation: float
    tail_join_slope: float
    knot_max_relative_error: float


class BHCurve:
    """Effective single-valued law H(B): monotone cubic Hermite through the stacked data points, then
    J = B - μ0·H approaching Js_eff as J = Js - d / (1 + s·(H - Hn)/d), joined C¹ at the last point."""

    def __init__(self, h: np.ndarray, b: np.ndarray, js_eff: float):
        slopes = np.diff(h) / np.diff(b)
        d = PchipInterpolator(b, h).derivative()(b)
        # End derivative = last secant, so the tail's join slope dB/dH is exactly the last secant's,
        # which the polarisation check guarantees is >= μ0.
        d[-1] = slopes[-1]
        self._spline = CubicHermiteSpline(b, h, d)
        self._dspline = self._spline.derivative()
        self._w = self._spline.antiderivative()
        self.bn, self.hn = float(b[-1]), float(h[-1])
        self.jn = self.bn - MU0 * self.hn
        self.js = float(js_eff)
        self.gap = self.js - self.jn
        self.s = max(1.0 / slopes[-1] - MU0, 0.0)
        self.k = self.s / self.gap
        self.nu0 = float(d[0])
        self._wn = float(self._w(self.bn))

    def _tail_x(self, b: np.ndarray) -> np.ndarray:
        """H - Hn for B >= Bn: the stable root of μ0·k·x² + (μ0 - c·k)·x - (B - Bn) = 0."""
        db = b - self.bn
        c = db - self.gap
        q = MU0 - c * self.k
        return 2 * db / (q + np.sqrt(q * q + 4 * MU0 * self.k * db))

    def _tail_coenergy_increment(self, x: np.ndarray) -> np.ndarray:
        """∫ B dH from Hn to Hn + x on the tail."""
        h = self.hn + x
        log_term = self.gap * x if self.k == 0 else self.gap / self.k * np.log1p(self.k * x)
        return MU0 * (h * h - self.hn * self.hn) / 2 + self.js * x - log_term

    def h_of_b(self, b) -> np.ndarray:
        b = np.asarray(b, float)
        out = np.empty_like(b)
        data = b <= self.bn
        out[data] = self._spline(b[data])
        out[~data] = self.hn + self._tail_x(b[~data])
        return out

    def dh_db(self, b) -> np.ndarray:
        b = np.asarray(b, float)
        out = np.empty_like(b)
        data = b <= self.bn
        out[data] = self._dspline(b[data])
        u = 1 + self.k * self._tail_x(b[~data])
        out[~data] = 1.0 / (MU0 + self.s / (u * u))
        return out

    def nu_dnu(self, b2) -> tuple[np.ndarray, np.ndarray]:
        """Reluctivity ν = H/B and dν/d(B²) at squared flux density b2."""
        b2 = np.asarray(b2, float)
        b = np.sqrt(b2)
        small = b < B_SMALL
        bs = np.where(small, B_SMALL, b)
        h = self.h_of_b(bs)
        nu = np.where(small, self.nu0, h / bs)
        dnu = np.where(small, 0.0, (self.dh_db(bs) * bs - h) / (2 * bs**3))
        return nu, dnu

    def energy_density(self, b) -> np.ndarray:
        """w(B) = ∫0^B H dB, J/m³."""
        b = np.asarray(b, float)
        out = np.empty_like(b)
        data = b <= self.bn
        out[data] = self._w(b[data])
        bt = b[~data]
        x = self._tail_x(bt)
        h = self.hn + x
        out[~data] = self._wn + (bt * h - self.bn * self.hn) - self._tail_coenergy_increment(x)
        return out

    def coenergy_density(self, b) -> np.ndarray:
        """w'(B) = B·H(B) - w(B) = ∫0^H B dH, J/m³."""
        b = np.asarray(b, float)
        return b * self.h_of_b(b) - self.energy_density(b)


def process_bh(table: BHTable, stacking_factor: float, saturation_polarisation: float) -> tuple[BHCurve, BHReport]:
    h = np.asarray(table.h, float)
    b = np.asarray(table.b, float)
    if np.any(h < 0) or np.any(b < 0):
        raise _error("monotone", "B-H points must be non-negative (first-quadrant magnetisation curve)")
    added_origin = not (h[0] == 0 and b[0] == 0)
    if added_origin:
        h, b = np.concatenate([[0.0], h]), np.concatenate([[0.0], b])
    if not (np.all(np.diff(h) > 0) and np.all(np.diff(b) > 0)):
        bad = int(np.argmin(np.minimum(np.diff(h), np.diff(b)))) + 1
        raise _error("monotone", f"B-H points must strictly increase in H and B; point {bad} does not "
                                 f"(use repair_monotone to drop offending points)")
    check_bh_units(h, b)
    k = stacking_factor
    b_eff = k * b + (1 - k) * MU0 * h
    secant = np.diff(b_eff) / np.diff(h)
    if np.any(secant < MU0 * (1 - 1e-9)):
        i = int(np.argmin(secant))
        raise _error("polarisation", f"dB/dH < μ0 between B = {b_eff[i]:g} and {b_eff[i + 1]:g} T: "
                                     f"polarisation J = B - μ0·H decreases, which no material does")
    js_eff = k * saturation_polarisation
    jn = b_eff[-1] - MU0 * h[-1]
    if js_eff <= jn:
        raise _error("saturation", f"saturation polarisation {saturation_polarisation:g} T is not above the "
                                   f"polarisation at the last data point ({jn / k:g} T)")
    curve = BHCurve(h, b_eff, js_eff)
    knot_err = np.abs(curve.h_of_b(b_eff[1:]) - h[1:]) / h[1:]
    report = BHReport(
        added_origin=added_origin, stacking_factor=k,
        initial_relative_permeability=1.0 / (MU0 * curve.nu0),
        join_b=curve.bn, join_h=curve.hn, tail_saturation_polarisation=js_eff, tail_join_slope=curve.s,
        knot_max_relative_error=float(knot_err.max()),
    )
    return curve, report

