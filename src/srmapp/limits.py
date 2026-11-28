"""Hard limits of a design: closed-form checks that decide feasibility in a search and in a case.
A `fail` makes a design infeasible. A `not_run` is a check that had no data; a search rejects it for the names in
`SEARCH_REQUIRES_PASS`, a case evaluation only notes it."""
from dataclasses import dataclass
from typing import Literal

from srmcore.materials.library import load_material
from srmcore.model.design import RadialSRMParams
from srmcore.post.rotor_stress import OVERSPEED, SAFETY_FACTOR, rotor_stress

from .cooling import K_IRON_HI
from .mechanical import BEARING_SPEED_RPM, DB_PRELOAD_A, SPAN_NOTE, first_bending_rpm
from .requirements import Requirements

# A search never shortlists a rotor whose stress was not checked (rotor bursting is not recoverable by a later step).
SEARCH_REQUIRES_PASS = ("rotor_stress", "bending")
BENDING_MARGIN = 1.3    # first bending speed over the top speed
GAP_SHARE = 0.5         # largest air-gap closure at overspeed, as a share of the air gap


@dataclass(frozen=True)
class Limit:
    name: str
    status: Literal["pass", "fail", "not_run"]
    value: float | None     # the computed quantity (None when not run)
    limit: float | None     # what it is compared with
    note: str


def rotor_limit(machine: RadialSRMParams, req: Requirements) -> Limit:
    """Rotor safety factor at the overspeed check (docs/r5-sources.md section 5) against `SAFETY_FACTOR`.
    `ok` below the factor, `kt_out_of_range` and `no_fillet` fail; no strength data and imported iron are not run."""
    rotor = load_material(machine.materials.rotor)
    s = rotor_stress(machine, rotor.density, rotor.mechanical, req.max_speed_rpm)
    rpm = f"{s.check_speed_rpm:,.0f}".replace(",", " ")
    if s.status == "ok":
        sf = s.safety_factor
        if sf >= SAFETY_FACTOR:
            return Limit("rotor_stress", "pass", sf, SAFETY_FACTOR,
                         f"rotor safety factor {sf:.2f}, at least {SAFETY_FACTOR:g}, at {rpm} r/min ({OVERSPEED:g} x top speed)")
        return Limit("rotor_stress", "fail", sf, SAFETY_FACTOR,
                     f"rotor safety factor {sf:.2f} below {SAFETY_FACTOR:g} at {rpm} r/min ({OVERSPEED:g} x top speed)")
    if s.status in ("kt_out_of_range", "no_fillet"):
        return Limit("rotor_stress", "fail", None, SAFETY_FACTOR, f"rotor stress not valid for this rotor: {s.note}")
    return Limit("rotor_stress", "not_run", None, SAFETY_FACTOR, f"rotor stress not checked: {s.note}")


def frequency_limit(n_rotor_poles: int, req: Requirements) -> Limit:
    """Top stator electrical frequency against the last frequency of the Kiyota iron-loss factor curve
    (`K_IRON_HI`); above it the loss factor is a held value, not a measurement."""
    f_max = K_IRON_HI[-1][0]
    f = n_rotor_poles * req.max_speed_rpm / 60
    if f <= f_max:
        return Limit("iron_frequency", "pass", f, f_max, f"stator electrical frequency {f:.0f} Hz at top speed")
    return Limit("iron_frequency", "fail", f, f_max,
                 f"stator electrical frequency {f:.0f} Hz at top speed, above {f_max:.0f} Hz (end of the iron-loss data)")


def bending_limit(machine: RadialSRMParams, req: Requirements) -> Limit:
    """First bending speed (`first_bending_rpm`) at least `BENDING_MARGIN` x the top speed; not run without shaft data."""
    bearing = req.bearing
    rpm = first_bending_rpm(machine, bearing)
    need = BENDING_MARGIN * req.max_speed_rpm
    if rpm is None:
        return Limit("bending", "not_run", None, need, "bending not checked: the shaft material has no Young's modulus")
    note = f"first bending speed {rpm:,.0f} r/min against {need:,.0f} r/min ({BENDING_MARGIN:g} x top speed)".replace(",", " ")
    if bearing.span_m is None:
        note += "; " + SPAN_NOTE
    return Limit("bending", "pass" if rpm >= need else "fail", rpm, need, note)


def bearing_limit(req: Requirements) -> Limit:
    """Overspeed x top speed against the catalogue limiting speed of the bearing candidate x `DB_PRELOAD_A`. Without a
    candidate the lowest of the three for the lubrication is used, so the check holds for whichever one is ordered."""
    b = req.bearing
    idx = 0 if b.lubrication == "grease" else 1
    name = b.candidate or min(BEARING_SPEED_RPM, key=lambda n: BEARING_SPEED_RPM[n][idx])
    cat = BEARING_SPEED_RPM[name][idx]
    limit = cat * DB_PRELOAD_A
    need = OVERSPEED * req.max_speed_rpm
    lube = "grease" if idx == 0 else "oil-air"
    def rpm(x: float) -> str:
        return f"{x:,.0f}".replace(",", " ")
    note = (f"{name} on {lube}: catalogue {rpm(cat)} r/min x set factor {DB_PRELOAD_A:g} = {rpm(limit)} r/min, "
            f"against {rpm(need)} r/min ({OVERSPEED:g} x top speed)")
    if not b.candidate:
        note += "; no bearing is chosen, so this is the lowest of the three candidates"
    if name.startswith("NSK"):
        note += ("; the set factor is assumed (not read for NSK) and is too high (unsafe) if the set has medium "
                 "preload")
    return Limit("bearing_speed", "pass" if need <= limit else "fail", need, limit, note)


def hard_limits(req: Requirements, machine: RadialSRMParams) -> tuple[Limit, ...]:
    return (rotor_limit(machine, req), frequency_limit(machine.n_rotor_poles, req), bending_limit(machine, req), bearing_limit(req))


def gap_limit(machine: RadialSRMParams, rating) -> Limit:
    """Larger gap closure of the continuous and peak overspeed cases (`Rating.gap`) against `GAP_SHARE` x the air gap.
    Without expansion data the closure is None: with one material for stator and rotor and the rotor at or above the
    bore temperature in both cases, the centrifugal part alone is checked (the thermal part, which only adds, is not
    run); otherwise the check is not run."""
    limit = GAP_SHARE * machine.air_gap
    cases = [] if rating is None else [rating.gap.get(k) for k in ("continuous_overspeed", "peak_overspeed")]
    if not cases or None in cases:
        return Limit("gap_closure", "not_run", None, limit, "gap closure not checked: no rating" if rating is None
                     else "gap closure not checked: the rating has no gap closure")
    what = "gap closure"
    if any(c.closure is None for c in cases):
        last = rating.rated[-1] if rating.rated else None
        same = machine.materials.stator == machine.materials.rotor
        if not (same and last and last.rotor_c >= last.bore_c and last.rotor_peak_c >= last.bore_peak_c):
            return Limit("gap_closure", "not_run", None, limit,
                         "gap closure not checked: no thermal expansion data for the stator and rotor materials")
        values = [c.centrifugal for c in cases]
        what = "centrifugal gap closure (thermal part not run)"
    else:
        values = [c.closure for c in cases]
    worst = max(values)
    note = f"{what} {worst * 1e3:.3f} mm at overspeed against {limit * 1e3:.3f} mm ({GAP_SHARE:g} x air gap)"
    return Limit("gap_closure", "pass" if worst <= limit else "fail", worst, limit, note)
