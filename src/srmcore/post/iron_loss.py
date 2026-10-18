"""Iron loss per unit mass of a lamination element from its flux-density waveform over one period.

Per radial and tangential component of B (T), over a period T:

    hysteresis  sum over half-cycle reversals of  1/2 k_h (dB/2)^alpha (1 + K_DC |B_dc|^ALPHA_DC), divided by T
    classical   sigma d^2 / (12 rho_m) <(dB/dt)^2>
    excess      k_e C <|dB/dt|^1.5>

with C chosen so that a sinusoid of peak B at f gives k_e (f B)^1.5, which makes a sinusoid reproduce
`LossModel.sinusoid`. The two components are summed.
"""
import math
from dataclasses import dataclass

import numpy as np

from srmcore.materials import LossModel

# DC-bias hysteresis factor 1 + K_DC |B_dc|^ALPHA_DC: Urgera 2024 (Table 5.4), all-data fit on M250-35HS,
# 0.35 mm. It is a grade C extrapolation for 10JNEX900.
K_DC = 1.4664
ALPHA_DC = 3.7955

# Swings of a component smaller than this (T) are merged into the larger swing around them.
REVERSAL_BAND = 1e-3

# <|cos x|^1.5> over a period, and the excess-loss constant C = (2 pi)^-1.5 / <|cos x|^1.5>.
_MEAN_ABS_COS_1_5 = math.gamma(1.25) / (math.sqrt(math.pi) * math.gamma(1.75))
EXCESS_C = (2.0 * math.pi) ** -1.5 / _MEAN_ABS_COS_1_5

# A harmonic or an element group counts towards the fit-range flags above this share of the loss.
SHARE_LIMIT = 0.05


@dataclass(frozen=True)
class ElementLoss:
    hysteresis: np.ndarray   # W/kg per element
    classical: np.ndarray
    excess: np.ndarray
    beyond_fit_range: bool
    high_b_share: float = 0.0   # share of the weighted loss from elements with peak |B| above b_range[1]
    low_b_share: float = 0.0    # same for peak |B| below b_range[0]

    @property
    def total(self) -> np.ndarray:
        return self.hysteresis + self.classical + self.excess


def _turning_points(b: np.ndarray, band: float) -> np.ndarray:
    """Extrema of the periodic signal, starting at the global maximum and ending on it again."""
    b = np.asarray(b, dtype=float)
    keep = np.concatenate(([True], b[1:] != b[:-1]))
    b = b[keep]
    if b.size > 1 and b[0] == b[-1]:
        b = b[:-1]
    if b.size < 2:
        return np.empty(0)
    if b.size == 2:
        ext = b
    else:
        prev, nxt = np.roll(b, 1), np.roll(b, -1)
        ext = b[((b > prev) & (b > nxt)) | ((b < prev) & (b < nxt))]
    if ext.size < 2:
        return np.empty(0)
    ext = np.roll(ext, -int(np.argmax(ext)))
    p = list(ext) + [ext[0]]
    changed = True
    while changed and len(p) > 3:
        changed = False
        for i in range(1, len(p) - 2):
            if abs(p[i + 1] - p[i]) < band:
                del p[i:i + 2]
                changed = True
                break
    return np.array(p)


def reversals(b: np.ndarray, band: float = REVERSAL_BAND) -> list[tuple[float, float]]:
    """(swing, mean) of every half-cycle of a periodic 1-D waveform.

    Rainflow pairing on the extrema, starting at the global maximum, so every cycle closes: a closed
    cycle gives two half-cycles with the same swing and mean. Swings below `band` are merged.
    """
    points = _turning_points(b, band)
    out: list[tuple[float, float]] = []
    stack: list[float] = []
    for x in points:
        stack.append(float(x))
        while len(stack) >= 3:
            inner = abs(stack[-2] - stack[-3])
            last = abs(stack[-1] - stack[-2])
            if last < inner:
                break
            mean = 0.5 * (stack[-2] + stack[-3])
            if len(stack) == 3:
                out.append((inner, mean))
                del stack[0]
            else:
                out.extend([(inner, mean)] * 2)
                del stack[-3:-1]
    for a, c in zip(stack[:-1], stack[1:]):
        out.append((abs(c - a), 0.5 * (a + c)))
    return out


def _components(b: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    """(n_t, n_el, 2) in the element frame to radial and tangential components about the origin."""
    r = np.hypot(centroids[:, 0], centroids[:, 1])
    ur = centroids / np.where(r > 0, r, 1.0)[:, None]
    ut = np.stack([-ur[:, 1], ur[:, 0]], axis=1)
    return np.stack([np.einsum("tek,ek->te", b, ur), np.einsum("tek,ek->te", b, ut)], axis=2)


def waveform_loss(b: np.ndarray, centroids: np.ndarray, period_s: float, model: LossModel,
                  weights: np.ndarray | None = None) -> ElementLoss:
    """Loss per element (W/kg) of B over one period; b is (n_t, n_el, 2), uniform in time.

    `beyond_fit_range` is True when the model is used outside the range it was fitted on: the
    fundamental, or a harmonic carrying more than 5 % of the classical loss, is above
    `frequency_range[1]`; or more than 5 % of the total loss comes from elements whose peak |B| (vector norm over
    time) exceeds `b_range[1]`; or more than 5 % of the total loss comes from elements whose peak |B| is below
    `b_range[0]`. The harmonic
    shares are per unit mass. `weights` (n_el, e.g. element areas) weights each element's W/kg in the low-B
    share; without it every element counts equally. Call once per material and per side (stator or rotor) with
    all of that side's iron elements, so the share is a share of that side's loss: the two sides have different
    periods and cannot share one call.
    """
    b = np.asarray(b, dtype=float)
    n_t, n_el = b.shape[0], b.shape[1]
    if weights is not None:
        weights = np.asarray(weights, dtype=float)
        if weights.shape != (n_el,):
            raise ValueError(f"weights must have shape ({n_el},), got {weights.shape}")
    if not (math.isfinite(period_s) and period_s > 0):
        raise ValueError(f"period_s must be positive and finite, got {period_s}")
    if n_t < 3:
        raise ValueError(f"need at least 3 time samples for central differences, got {n_t}")
    # A centroid at the origin gives zero loss (radial direction undefined); it cannot occur in laminated iron.
    comp = _components(b, np.asarray(centroids, dtype=float))
    dt = period_s / n_t
    db = (np.roll(comp, -1, axis=0) - np.roll(comp, 1, axis=0)) / (2.0 * dt)

    classical = (model.conductivity * model.thickness**2 / (12.0 * model.density)
                 * np.mean(db**2, axis=0).sum(axis=1))
    excess = model.k_e * EXCESS_C * np.mean(np.abs(db) ** 1.5, axis=0).sum(axis=1)

    hysteresis = np.zeros(n_el)
    for e in range(n_el):
        for c in range(2):
            for swing, mean in reversals(comp[:, e, c]):
                hysteresis[e] += (0.5 * model.k_h * (0.5 * swing) ** model.alpha
                                  * (1.0 + K_DC * abs(mean) ** ALPHA_DC))
    hysteresis /= period_s

    total = hysteresis + classical + excess
    peak = np.linalg.norm(b, axis=2).max(axis=0)
    shared = total if weights is None else total * weights
    high_share = low_share = 0.0
    if shared.sum() > 0:
        high_share = float(shared[peak > model.b_range[1]].sum() / shared.sum())
        low_share = float(shared[peak < model.b_range[0]].sum() / shared.sum())
    beyond = high_share > SHARE_LIMIT or low_share > SHARE_LIMIT
    spectrum = np.abs(np.fft.rfft(comp, axis=0)) ** 2
    orders = np.arange(spectrum.shape[0])
    harmonic_classical = (orders**2)[:, None, None] * spectrum
    harmonic_classical = harmonic_classical.sum(axis=(1, 2))
    if harmonic_classical.sum() > 0:
        share = harmonic_classical / harmonic_classical.sum()
        freq = orders / period_s
        high = freq > model.frequency_range[1]
        beyond = beyond or bool(high[1] and share[1] > 0) or bool(np.any(high[2:] & (share[2:] > SHARE_LIMIT)))
    return ElementLoss(hysteresis=hysteresis, classical=classical, excess=excess, beyond_fit_range=beyond,
                       high_b_share=high_share, low_b_share=low_share)
