"""Exact 2D outline of a radial SRM at rotor angle 0.

Origin at the shaft centre. Stator pole k is centred at 2πk/Ns; rotor pole 0 is centred on +x.
Boundaries run counter-clockwise starting with pole 0's face.
"""
import math
from dataclasses import dataclass

from ..model.design import RadialSRMParams
from ..model.errors import InputError, ValidationIssue
from .primitives import (
    Arc, Line, Point, Segment, fillet_line_circle, line_circle_intersection, mirror_y, rotate,
)

ORIGIN: Point = (0.0, 0.0)


@dataclass(frozen=True)
class CoilSide:
    name: str
    pole: int
    phase: int
    sign: int
    boundary: tuple[Segment, ...]


@dataclass(frozen=True)
class RadialOutline:
    stator_outer_radius: float
    stator_inner_boundary: tuple[Segment, ...]
    bore_radius: float
    rotor_outer_radius: float
    rotor_outer_boundary: tuple[Segment, ...]
    shaft_radius: float
    band_inner_radius: float
    band_outer_radius: float
    coil_sides: tuple[CoilSide, ...]
    refinement_features: dict[str, tuple[Segment | Point, ...]]


@dataclass(frozen=True)
class _PoleSide:
    """Upper (+y) half of one pole in its local frame, pole axis on +x."""
    face_end: Point
    flank_end: Point
    root_end: Point
    fillet_center: Point | None
    corner: Point


def periodicity(p: RadialSRMParams) -> int:
    return math.gcd(p.n_stator_poles, p.n_rotor_poles)


def _angle(q: Point) -> float:
    return math.atan2(q[1], q[0])


def _pole_side(face_radius: float, arc: float, taper: float, root_radius: float,
               fillet_radius: float, outward: bool, pitch: float) -> _PoleSide:
    half = arc / 2
    if half >= pitch / 2:
        raise ValueError("pole face is wider than the pole pitch")
    face_end = (face_radius * math.cos(half), face_radius * math.sin(half))
    d = (math.cos(taper), math.sin(taper)) if outward else (-math.cos(taper), math.sin(taper))
    n = (-d[1], d[0]) if d[0] > 0 else (d[1], -d[0])  # unit normal pointing away from the pole axis
    corner, _ = line_circle_intersection(face_end, d, root_radius)
    if fillet_radius > 0:
        f = fillet_line_circle(face_end, d, n, root_radius, fillet_radius, inside=outward)
        side = _PoleSide(face_end, f.on_line, f.on_circle, f.center, corner)
    else:
        side = _PoleSide(face_end, corner, corner, None, corner)
    if not (0.0 < _angle(side.root_end) < pitch / 2):
        raise ValueError("pole root leaves no room between neighbouring poles")
    return side


def _salient_boundary(n_poles: int, side: _PoleSide, prefix: str) -> tuple[tuple[Segment, ...], list[Point]]:
    pitch = 2 * math.pi / n_poles
    segs: list[Segment] = []
    for k in range(n_poles):
        a, a_next = k * pitch, ((k + 1) % n_poles) * pitch

        def here(q: Point) -> Point:
            return rotate(q, a)

        def nxt(q: Point) -> Point:
            return rotate(mirror_y(q), a_next)

        segs.append(Arc(here(mirror_y(side.face_end)), here(side.face_end), ORIGIN, f"{prefix}_pole_tip"))
        segs.append(Line(here(side.face_end), here(side.flank_end), f"{prefix}_flank"))
        if side.fillet_center is not None:
            segs.append(Arc(here(side.flank_end), here(side.root_end), here(side.fillet_center), f"{prefix}_pole_root"))
        segs.append(Arc(here(side.root_end), nxt(side.root_end), ORIGIN, f"{prefix}_yoke"))
        if side.fillet_center is not None:
            segs.append(Arc(nxt(side.root_end), nxt(side.flank_end), nxt(side.fillet_center), f"{prefix}_pole_root"))
        segs.append(Line(nxt(side.flank_end), nxt(side.face_end), f"{prefix}_flank"))
    corners = [rotate(c, k * pitch) for k in range(n_poles) for c in (side.corner, mirror_y(side.corner))]
    return tuple(segs), corners


def _fit_error(parameter: str, rule: str, exc: Exception) -> InputError:
    return InputError([ValidationIssue(parameter, rule, str(exc))])


def build_outline(p: RadialSRMParams) -> RadialOutline:
    try:
        stator_side = _pole_side(p.bore_radius, p.stator_pole_arc, p.stator_pole_taper,
                                 p.stator_yoke_inner_radius, p.stator_fillet_radius, True,
                                 2 * math.pi / p.n_stator_poles)
    except ValueError as exc:
        raise _fit_error("stator_fillet_radius" if p.stator_fillet_radius > 0 else "stator_pole_arc",
                         "pole_fit", exc) from exc
    try:
        rotor_side = _pole_side(p.rotor_outer_radius, p.rotor_pole_arc, p.rotor_pole_taper,
                                p.rotor_yoke_outer_radius, p.rotor_fillet_radius, False,
                                2 * math.pi / p.n_rotor_poles)
    except ValueError as exc:
        raise _fit_error("rotor_fillet_radius" if p.rotor_fillet_radius > 0 else "rotor_pole_arc",
                         "pole_fit", exc) from exc

    stator, stator_corners = _salient_boundary(p.n_stator_poles, stator_side, "stator")
    rotor, rotor_corners = _salient_boundary(p.n_rotor_poles, rotor_side, "rotor")

    tips = tuple(s for s in stator + rotor if s.tag.endswith("_pole_tip"))
    if p.stator_fillet_radius > 0 or p.rotor_fillet_radius > 0:
        roots: tuple[Segment | Point, ...] = tuple(s for s in stator + rotor if s.tag.endswith("_pole_root"))
        if p.stator_fillet_radius == 0:
            roots += tuple(stator_corners)
        if p.rotor_fillet_radius == 0:
            roots += tuple(rotor_corners)
    else:
        roots = tuple(stator_corners + rotor_corners)

    return RadialOutline(
        stator_outer_radius=p.stator_outer_radius,
        stator_inner_boundary=stator,
        bore_radius=p.bore_radius,
        rotor_outer_radius=p.rotor_outer_radius,
        rotor_outer_boundary=rotor,
        shaft_radius=p.shaft_radius,
        band_inner_radius=p.band_inner_radius,
        band_outer_radius=p.band_outer_radius,
        coil_sides=(),
        refinement_features={"pole_tip": tips, "pole_root": roots},
    )
