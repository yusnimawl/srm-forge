"""Bertotti core-loss model per unit mass, fitted to a sinusoidal loss table.

p(B, f) = k_h f B^alpha + k_c (f B)^2 + k_e (f B)^1.5   [W/kg, B peak in T, f in Hz]

k_c = pi^2 sigma d^2 / (6 rho_m) is computed from the conductivity, the lamination thickness and the
density; k_h, alpha and k_e are fitted to log(p) with alpha in [1.2, 3.0] and k_h, k_e >= 0.
"""
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.optimize import least_squares

from .library import load_material
from .schema import LossData

ALPHA_BOUNDS = (1.2, 3.0)


class MissingLossData(ValueError):
    """The material has no loss table (or is not a lamination steel)."""


@dataclass(frozen=True)
class LossModel:
    k_h: float
    alpha: float
    k_c: float
    k_e: float
    density: float
    thickness: float
    conductivity: float
    fit_error: float                       # max relative error over the data points
    frequency_range: tuple[float, float]
    confidence: str

    def sinusoid(self, b: float, f: float) -> float:
        """Loss in W/kg for a sinusoidal flux of peak b (T) at f (Hz)."""
        fb = f * b
        return self.k_h * f * b**self.alpha + self.k_c * fb**2 + self.k_e * fb**1.5


def _bertotti(params, b, f, k_c):
    k_h, alpha, k_e = params
    fb = f * b
    return k_h * f * b**alpha + k_c * fb**2 + k_e * fb**1.5


def fit_loss(data: LossData, *, density: float, thickness: float) -> LossModel:
    b = np.array([p.b for p in data.points])
    f = np.array([p.f for p in data.points])
    w = np.array([p.w_per_kg for p in data.points])
    k_c = math.pi**2 * data.conductivity * thickness**2 / (6.0 * density)

    def residual(x):
        model = _bertotti(x, b, f, k_c)
        return np.log(np.maximum(model, 1e-300)) - np.log(w)

    best = None
    for alpha0 in (1.6, 2.0, 2.5):
        # Seed k_h so the hysteresis term alone matches the lowest-frequency data.
        i = int(np.argmin(f))
        k_h0 = max(w[i] / (f[i] * b[i] ** alpha0), 1e-12)
        sol = least_squares(residual, x0=[k_h0, alpha0, 1e-4], bounds=([0.0, ALPHA_BOUNDS[0], 0.0],
                                                                       [np.inf, ALPHA_BOUNDS[1], np.inf]),
                            x_scale=[max(k_h0, 1e-6), 1.0, 1e-3])
        if best is None or sol.cost < best.cost:
            best = sol
    k_h, alpha, k_e = (float(v) for v in best.x)
    fit = _bertotti(best.x, b, f, k_c)
    fit_error = float(np.max(np.abs(fit - w) / w))
    return LossModel(k_h=k_h, alpha=alpha, k_c=k_c, k_e=k_e, density=density, thickness=thickness,
                     conductivity=data.conductivity, fit_error=fit_error,
                     frequency_range=data.frequency_range, confidence=data.confidence)


@lru_cache(maxsize=None)
def loss_model(name: str) -> LossModel:
    material = load_material(name)
    loss = getattr(material, "loss", None)
    if loss is None:
        raise MissingLossData(f"material {name!r} has no loss data")
    if material.thickness is None:
        raise MissingLossData(f"material {name!r} has no lamination thickness for the loss fit")
    return fit_loss(loss, density=material.density, thickness=material.thickness)
