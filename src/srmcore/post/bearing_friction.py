"""Bearing friction from a constant friction coefficient.

Source: JTEKT (Koyo) bearing knowledge, "Frictional coefficient (reference)", Eq. (8-2) and Table 8-1
(docs/r3-sources.md section 7): M = mu P d / 2, M in N m for P in N and d in m, with the reference mu range of each
bearing type "for stable operation under normal operating conditions". The page states no accuracy and says mu
depends on load, speed and lubrication, so the model has no speed or lubricant term: the band is the printed range.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Table 8-1: (low, high) friction coefficient.
BEARING_MU: dict[str, tuple[float, float]] = {
    "deep_groove_ball": (0.0010, 0.0015),
    "angular_contact_ball": (0.0012, 0.0020),
    "self_aligning_ball": (0.0008, 0.0012),
    "cylindrical_roller": (0.0008, 0.0012),
    "needle_full_complement": (0.0025, 0.0035),
    "needle_cage": (0.0020, 0.0030),
    "tapered_roller": (0.0017, 0.0025),
    "spherical_roller": (0.0020, 0.0025),
    "thrust_ball": (0.0010, 0.0015),
    "spherical_thrust_roller": (0.0020, 0.0025),
}

NOTE = ("bearing friction is mu P d / 2 with the reference mu of the bearing type (JTEKT Table 8-1): no speed, "
        "lubricant, seal or preload term")


@dataclass(frozen=True)
class BearingFriction:
    torque_nm: float        # all bearings, nominal (mid-range mu)
    power_w: float
    mu: float
    torque_low_nm: float    # mu at the low and high end of Table 8-1
    torque_high_nm: float
    power_low_w: float
    power_high_w: float


def bearing_friction(bearing_type: str, bore_diameter_m: float, radial_load_n: float, rpm: float) -> BearingFriction:
    """Friction torque and power of the bearings of `bearing_type`, all of one nominal bore, that carry
    `radial_load_n` (total, N) between them: the sum of mu P_i d / 2 does not depend on how the load is shared.
    Raises ValueError for an unknown type or a non-positive bore."""
    if bearing_type not in BEARING_MU:
        raise ValueError(f"unknown bearing type {bearing_type!r}; choose one of {sorted(BEARING_MU)}")
    if not bore_diameter_m > 0 or radial_load_n < 0:
        raise ValueError("bore diameter must be positive and the load non-negative")
    lo, hi = BEARING_MU[bearing_type]
    mid = 0.5 * (lo + hi)
    omega = rpm * 2 * math.pi / 60
    base = radial_load_n * bore_diameter_m / 2
    t = lambda mu: mu * base  # noqa: E731
    return BearingFriction(t(mid), t(mid) * omega, mid, t(lo), t(hi), t(lo) * omega, t(hi) * omega)
