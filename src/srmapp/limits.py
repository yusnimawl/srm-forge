"""Hard limits of a design: closed-form checks that decide feasibility in a search and in a case.
A `fail` makes a design infeasible. A `not_run` is a check that had no data; a search rejects it for the names in
`SEARCH_REQUIRES_PASS`, a case evaluation only notes it."""
from dataclasses import dataclass
from typing import Literal

from srmcore.materials.library import load_material
from srmcore.model.design import RadialSRMParams
from srmcore.post.rotor_stress import SAFETY_FACTOR, rotor_stress

from .requirements import Requirements

# A search never shortlists a rotor whose stress was not checked (rotor bursting is not recoverable by a later step).
SEARCH_REQUIRES_PASS = ("rotor_stress",)


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
                         f"rotor safety factor {sf:.2f} at {rpm} r/min (1.2 x top speed)")
        return Limit("rotor_stress", "fail", sf, SAFETY_FACTOR,
                     f"rotor safety factor {sf:.2f} below {SAFETY_FACTOR:g} at {rpm} r/min (1.2 x top speed)")
    if s.status in ("kt_out_of_range", "no_fillet"):
        return Limit("rotor_stress", "fail", None, SAFETY_FACTOR, f"rotor stress not valid for this rotor: {s.note}")
    return Limit("rotor_stress", "not_run", None, SAFETY_FACTOR, f"rotor stress not checked: {s.note}")


def hard_limits(req: Requirements, machine: RadialSRMParams) -> tuple[Limit, ...]:
    return (rotor_limit(machine, req),)
