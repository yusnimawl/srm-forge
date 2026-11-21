"""Plain-word summary of a thermal rating: the verdict against the requirement, what binds each speed, the budget
shares and one hint per uncertainty. Pure functions on stored results; nothing is solved here."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from srmapp.cooling import K_IRON_HI
from srmapp.requirements import Requirements
from srmapp.thermal import (_TORQUE_TOL, BIG_K, HOT_SPOT_ABOVE, NO_STROKE, Rating, RequirementCheck, SpeedRating,
                            rating_speeds, required_torques)

BINDS_HEAT = "heat"
BINDS_EM = "EM"

ROW_LABELS = {
    "iron": "Iron loss band",
    "em_torque": "EM torque uncertainty",
    "cross_wire": "Winding conductivity",
    "liner": "Liner conductivity",
    "contact": "Contact gap",
    "air_gap": "Air-gap h",
    "cooling_h": "Cooling h",
    "lamination_k": "Lamination conductivity",
    "thermal_mesh": "Thermal mesh",
    "end_winding_model": "End-winding model",
    "mechanical_loss": "Mechanical loss band",
}

# One sentence per input a measurement or a design change can narrow.
HINTS = {
    "iron": "Iron loss is the largest uncertainty: a measured iron loss on this lamination narrows it.",
    "em_torque": "The EM torque uncertainty is the largest: a 3D model or a measured torque narrows it.",
    "cross_wire": "Winding conductivity is the largest: a measured slot conductivity or a different fill narrows it.",
    "liner": "Liner conductivity is the largest: a measured liner conductivity or a liner with higher conductivity "
             "narrows it.",
    "contact": "The contact gap is the largest: tighter lamination-to-housing contact or a measured gap narrows it.",
    "cooling_h": "Cooling h is the largest: a measured coolant flow and heat transfer coefficient narrows it.",
    "lamination_k": "Lamination conductivity is the largest: a measured through-stack conductivity narrows it.",
    "mechanical_loss": "Windage and bearing friction are the largest: the real bearing and rotor surface narrow it.",
}


def hint(row: str) -> str | None:
    return HINTS.get(row)


def binds(s: SpeedRating, which: str) -> str:
    torque = s.continuous_nm if which == "continuous" else s.peak_nm
    return BINDS_EM if torque >= s.envelope_nm - _TORQUE_TOL else BINDS_HEAT


def location_text(location: str) -> str:
    if location == "none":
        return "no steady state"
    if location.startswith("end_"):
        return f"end winding, {location[4:]}"
    return f"slot winding, {location}"


@dataclass(frozen=True)
class Verdict:
    holds: bool | None
    rpm: float | None
    margin_pct: float | None
    which: str | None
    binds: str | None
    hot_spot_c: float | None
    hot_spot_at: str | None
    reason: str | None
    text: str


def _finite(x: float | None) -> float | None:
    return x if x is not None and math.isfinite(x) else None


def _margins(rating: Rating, req: Requirements):
    for s in rating.rated:
        cont, peak = required_torques(req, s.rpm)
        if cont:
            yield 100 * (s.continuous_nm / cont - 1), s, "continuous"
        if peak:
            yield 100 * (s.peak_nm / peak - 1), s, "peak"


def _failing_hot(check: RequirementCheck, req: Requirements) -> tuple[str | None, float | None]:
    """Which torque failed and its hot spot, read from the check's per-speed lists (None for a runaway)."""
    k = len([r for r in rating_speeds(req) if r < check.rpm])
    if len(check.continuous_hot_c) == k + 1 and len(check.peak_hot_c) == k:
        return "continuous", _finite(check.continuous_hot_c[-1])
    if len(check.peak_hot_c) == k + 1:
        return "peak", _finite(check.peak_hot_c[-1])
    return None, None


def verdict(rating: Rating | None, check: RequirementCheck | None, req: Requirements) -> Verdict:
    if check is None:
        return Verdict(None, None, None, None, None, None, None, None, "No thermal check was made for this case.")
    if not check.holds:
        which, hot = _failing_hot(check, req)
        why = check.reason
        text = f"✗ Short at {check.rpm:.0f} r/min: {why}"
        if why == HOT_SPOT_ABOVE and hot is not None:
            text += f" ({hot:.0f} °C of {req.hot_spot_limit_c:.0f} °C)"
        return Verdict(False, check.rpm, None, which, None, hot, None, why, text)
    margin = min(_margins(rating, req), key=lambda m: m[0], default=None) if rating is not None else None
    if margin is None:
        return Verdict(True, None, None, None, None, None, None, None, "✓ Meets the requirement")
    pct, s, which = margin
    b = binds(s, which)
    text = f"✓ Meets the requirement · smallest margin {pct:+.0f} % at {s.rpm:.0f} r/min ({which}, binds {b})"
    return Verdict(True, s.rpm, pct, which, b, None, None, None, text)


def shares_at(rating: Rating, rpm: float) -> list[dict]:
    rows = [s for s in rating.shares if s.rpm == rpm and s.row not in ("thermal_mesh", "end_winding_model")]
    return [{"row": s.row, "label": ROW_LABELS.get(s.row, s.row), "k": s.hot_spot_rise_k,
             "runaway": s.hot_spot_rise_k >= BIG_K} for s in sorted(rows, key=lambda s: -s.hot_spot_rise_k)]


def iron_band(rating: Rating) -> tuple[float, float]:
    return K_IRON_HI[0][1], K_IRON_HI[-1][1]


def _speed(s: SpeedRating, req: Requirements, limit_c: float) -> dict:
    cont, peak = required_torques(req, s.rpm)
    hot = _finite(s.continuous_hot_spot.temperature_c)
    em = binds(s, "continuous") == BINDS_EM
    text = "no steady state" if hot is None else f"{location_text(s.continuous_hot_spot.location)} {hot:.0f} °C"
    return {"rpm": s.rpm, "need_continuous_nm": cont, "need_peak_nm": peak,
            "binds_continuous": binds(s, "continuous"), "binds_peak": binds(s, "peak"),
            "hot_spot_text": text, "headroom_k": limit_c - hot if em and hot is not None else None}


def summary(rating: Rating | None, check: RequirementCheck | None, req: Requirements) -> dict:
    v = verdict(rating, check, req)
    return {"verdict": asdict(v),
            "speeds": [] if rating is None else [_speed(s, req, rating.limit_c) for s in rating.rated],
            "least_margin_rpm": v.rpm,
            "iron_band": None if rating is None else list(iron_band(rating))}
