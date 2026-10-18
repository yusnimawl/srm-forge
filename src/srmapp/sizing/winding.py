"""Windings a geometry can carry (v0a-2 spec §3, small-cycle spec §3). Wire mode fixes the wire and the phase
current and fits as many parallel strands as the slot holds; density mode fixes the current density. The poles of a
phase are connected in `paths` equal parallel paths, each carrying the phase current / paths."""
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
    resistance: float      # Ω, one phase at the requirement's winding temperature, its paths in parallel
    copper_mass: float     # kg, all coils
    wire: int | None       # index into Requirements.wires; None in density mode
    paths: int = 1         # parallel paths per phase

    @property
    def coil_current(self) -> float:
        """A, peak current in one coil."""
        return self.current / self.paths

    @property
    def current_density(self) -> float:
        """A/m², peak conductor current density."""
        return self.coil_current / self.copper_area


def path_counts(p: RadialSRMParams) -> list[int]:
    """Parallel path counts a phase allows: the divisors of its pole count."""
    poles = p.n_stator_poles // p.n_phases
    return [a for a in range(1, poles + 1) if poles % a == 0]


def _winding(p: RadialSRMParams, req: Requirements, turns: int, strands: int, copper_area: float, current: float,
             wire: int | None, paths: int) -> Winding:
    return Winding(turns, strands, copper_area, current, series_resistance(p, turns, copper_area, req.winding_temperature_c) / paths**2,
                   copper_mass(p, turns, copper_area), wire, paths)


def wire_windings(p: RadialSRMParams, req: Requirements, wire: int, j_peak_max: float) -> list[Winding]:
    """Every (paths, turns) `req.wires[wire]` can wind at `req.phase_current_a`, each with as many parallel strands
    as fit in `req.max_slot_fill` of the coil side, keeping the peak conductor current density within `j_peak_max`.
    Ordered by paths, then increasing turns."""
    w = req.wires[wire]
    room = req.max_slot_fill * coil_side_area(p) / w.outer_area     # conductors that fit in one coil side
    out = []
    for paths in path_counts(p):
        for turns in range(1, math.floor(room + _EPS) + 1):
            strands = math.floor(room / turns + _EPS)
            area = strands * w.copper_area
            if req.phase_current_a / paths / area <= j_peak_max * (1 + _EPS):
                out.append(_winding(p, req, turns, strands, area, req.phase_current_a, wire, paths))
    return out


def density_windings(p: RadialSRMParams, req: Requirements, j_peak: float,
                     max_turns: int = DENSITY_MAX_TURNS) -> list[Winding]:
    """Turn counts 1..max_turns for every path count, at current density `j_peak` in `p.fill_factor` of the coil
    side; windings whose peak phase current exceeds `req.phase_current_a` (when set) are left out. Ordered by
    paths, then increasing turns."""
    copper = p.fill_factor * coil_side_area(p)
    out = []
    for paths in path_counts(p):
        for turns in range(1, max_turns + 1):
            area = copper / turns
            current = j_peak * area * paths
            if req.phase_current_a is None or current <= req.phase_current_a * (1 + _EPS):
                out.append(_winding(p, req, turns, 1, area, current, None, paths))
    return out


def fixed_winding(p: RadialSRMParams, req: Requirements, turns: int, strands: int, paths: int, wire: int | None,
                  j_peak: float) -> Winding:
    """The winding a user chose, built like the generated ones. Wire mode (`wire` set) carries `req.phase_current_a`
    in `strands` strands of `req.wires[wire]`, which must fit `req.max_slot_fill`; density mode (`wire` None) has one
    strand filling `p.fill_factor` of the coil side and carries the current `j_peak` gives, which may not exceed
    `req.phase_current_a` when that is set. Raises ValueError naming the offending field."""
    if paths not in path_counts(p):
        raise ValueError(f"paths {paths} must divide the {p.n_stator_poles // p.n_phases} poles of a phase: "
                         f"one of {path_counts(p)}")
    if wire is None:
        if req.wire_mode:
            raise ValueError("wire must be set when the requirements give wires")
        if strands != 1:
            raise ValueError(f"strands must be 1 in density mode, got {strands}")
        area = p.fill_factor * coil_side_area(p) / turns
        current = j_peak * area * paths
        if req.phase_current_a is not None and current > req.phase_current_a * (1 + _EPS):
            raise ValueError(f"turns {turns} on {paths} paths carry {current:.1f} A at the peak current density, "
                             f"above the phase current limit {req.phase_current_a:g} A")
        return _winding(p, req, turns, 1, area, current, None, paths)
    if not req.wire_mode:
        raise ValueError("wire needs wires in the requirements")
    if not 0 <= wire < len(req.wires):
        raise ValueError(f"wire {wire} is outside the {len(req.wires)} wires given")
    w = req.wires[wire]
    if turns * strands * w.outer_area > req.max_slot_fill * coil_side_area(p) * (1 + _EPS):
        raise ValueError(f"turns {turns} x strands {strands} of wire {wire} do not fit "
                         f"max_slot_fill {req.max_slot_fill} of the coil side")
    return _winding(p, req, turns, strands, strands * w.copper_area, req.phase_current_a, wire, paths)


def max_mmf(p: RadialSRMParams, req: Requirements, j_peak: float, j_peak_max: float) -> float:
    """Largest peak ampere-turns per pole any allowed winding carries (v0a-2 spec §3.3); the map must cover it.
    0 when wire mode allows no winding."""
    if req.wire_mode:
        return max((w.turns * w.coil_current for i in range(len(req.wires))
                    for w in wire_windings(p, req, i, j_peak_max)), default=0.0)
    return j_peak * p.fill_factor * coil_side_area(p)
