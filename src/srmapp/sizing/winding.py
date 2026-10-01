"""Windings a geometry can carry (v0a-2 spec §3). Wire mode fixes the wire and the phase current and fits as
many parallel strands as the slot holds; density mode fixes the current density. Poles of a phase are in series."""
import math
from dataclasses import dataclass

from srmcore.model.design import RadialSRMParams

from ..requirements import Requirements
from .estimates import coil_side_area, copper_mass, series_resistance

DENSITY_MAX_TURNS = 500     # upper end of the density-mode turn scan
_EPS = 1e-9


@dataclass(frozen=True)
class Winding:
    turns: int             # per pole
    strands: int           # parallel conductors per turn
    copper_area: float     # m², one turn, all strands
    current: float         # A, peak phase current
    resistance: float      # Ω, one phase at 100 °C
    copper_mass: float     # kg, all coils
    wire: int | None       # index into Requirements.wires; None in density mode

    @property
    def current_density(self) -> float:
        return self.current / self.copper_area


def _winding(p: RadialSRMParams, turns: int, strands: int, copper_area: float, current: float,
             wire: int | None) -> Winding:
    return Winding(turns, strands, copper_area, current, series_resistance(p, turns, copper_area),
                   copper_mass(p, turns, copper_area), wire)


def wire_windings(p: RadialSRMParams, req: Requirements, wire: int, j_limit: float) -> list[Winding]:
    """Every turn count `req.wires[wire]` can wind at `req.phase_current_a`, each with as many parallel strands as
    fit in `req.max_slot_fill` of the coil side, keeping the current density within `j_limit`. Increasing turns."""
    w = req.wires[wire]
    room = req.max_slot_fill * coil_side_area(p) / w.outer_area     # conductors that fit in one coil side
    out = []
    for turns in range(1, math.floor(room + _EPS) + 1):
        strands = math.floor(room / turns + _EPS)
        area = strands * w.copper_area
        if req.phase_current_a / area <= j_limit * (1 + _EPS):
            out.append(_winding(p, turns, strands, area, req.phase_current_a, wire))
    return out


def density_windings(p: RadialSRMParams, req: Requirements, j_peak: float,
                     max_turns: int = DENSITY_MAX_TURNS) -> list[Winding]:
    """Turn counts 1..max_turns at current density `j_peak` in `p.fill_factor` of the coil side; turn counts whose
    peak current exceeds `req.phase_current_a` (when set) are left out. Increasing turns."""
    copper = p.fill_factor * coil_side_area(p)
    out = []
    for turns in range(1, max_turns + 1):
        area = copper / turns
        current = j_peak * area
        if req.phase_current_a is None or current <= req.phase_current_a * (1 + _EPS):
            out.append(_winding(p, turns, 1, area, current, None))
    return out


def max_mmf(p: RadialSRMParams, req: Requirements, j_peak: float, j_limit: float) -> float:
    """Largest peak ampere-turns per pole any allowed winding carries (spec §3.3); the map must cover it."""
    a = coil_side_area(p)
    if req.wire_mode:
        return j_limit * req.max_slot_fill * a * max(w.copper_area / w.outer_area for w in req.wires)
    return j_peak * p.fill_factor * a
