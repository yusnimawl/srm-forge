"""End-winding correction of a 2D map (core spec §7.1). The FEM map stays 2D; the analytic end-turn
inductance of the excited phase is added afterwards, so cached maps, goldens and cross-tool fixtures are
unaffected. A constant inductance adds no torque."""
import dataclasses
import math
from dataclasses import dataclass

from ..model.design import RadialSRMParams
from ..post.end_winding import end_turn_inductance
from ..topology.primitives import Arc
from ..topology.radial import build_outline
from .run import MapResult

_ARC_SAMPLES = 512


@dataclass(frozen=True)
class CoilGeometry:
    area: float      # m², one coil side
    depth: float     # m, radial extent
    build: float     # m, area / depth
    span: float      # m, mean span of a turn across the pole end


def _polygon_area(boundary) -> float:
    pts = []
    for seg in boundary:
        if isinstance(seg, Arc):
            cx, cy = seg.center
            r = math.hypot(seg.start[0] - cx, seg.start[1] - cy)
            a0 = math.atan2(seg.start[1] - cy, seg.start[0] - cx)
            a1 = math.atan2(seg.end[1] - cy, seg.end[0] - cx)
            sweep = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi       # minor arc
            pts += [(cx + r * math.cos(a0 + sweep * k / _ARC_SAMPLES), cy + r * math.sin(a0 + sweep * k / _ARC_SAMPLES))
                    for k in range(_ARC_SAMPLES)]
        else:
            pts.append(seg.start)
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2


def coil_geometry(machine: RadialSRMParams) -> CoilGeometry:
    p = machine
    area = _polygon_area(build_outline(p).coil_sides[0].boundary)
    r_in = p.bore_radius + p.coil_inner_clearance
    r_out = p.stator_yoke_inner_radius - 2 * p.stator_fillet_radius - p.slot_liner_thickness
    depth = r_out - r_in
    build = area / depth
    half = p.stator_pole_arc / 2
    x_mid = r_in + depth / 2
    half_width = p.bore_radius * math.sin(half) + (x_mid - p.bore_radius * math.cos(half)) * math.tan(p.stator_pole_taper)
    return CoilGeometry(area, depth, build, 2 * half_width + 2 * p.slot_liner_thickness + build)


def end_winding_inductance(machine: RadialSRMParams, image_factor: float = 1.0) -> float:
    """End-winding inductance of one phase, H: the series coils of its poles; coupling between them is
    neglected (they sit on opposite sides of the machine). `image_factor` 1.0 (default) is the free-air
    lower bound, 2.0 the iron-image upper bound; reports use the midpoint 1.5."""
    g = coil_geometry(machine)
    per_coil = end_turn_inductance(machine.turns_per_pole, g.span, g.build, g.depth,
                                   machine.stack_length + g.build, image_factor)
    return per_coil * (machine.n_stator_poles // machine.n_phases)


def with_end_winding(result: MapResult, l_end: float) -> MapResult:
    """`result` with the excited phase's end-winding inductance `l_end` (H) added to ψ, W, W′ and L_inc.
    Apply once; the result must not be stored under the 2D map's provenance (store_map / write_map)."""
    if l_end < 0:
        raise ValueError(f"l_end must be non-negative, got {l_end}")
    k = result.circuits.index(result.excited)
    i = result.currents[None, :]
    psi = result.psi.copy()
    psi[..., k] += l_end * i
    l_inc = result.l_inc.copy()
    l_inc[..., k] += l_end
    w = 0.5 * l_end * i**2
    return dataclasses.replace(result, psi=psi, l_inc=l_inc, energy=result.energy + w, coenergy=result.coenergy + w)
