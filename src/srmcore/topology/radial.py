"""Exact 2D outline of a radial SRM at rotor angle 0.

Origin at the shaft centre. Stator pole k is centred at 2πk/Ns; rotor pole 0 is centred on +x.
Boundaries run counter-clockwise starting with pole 0's face.
"""
import math
from dataclasses import dataclass

from ..model.design import RadialSRMParams
from ..model.errors import InputError, ValidationIssue
from .primitives import (
    Arc, Line, Point, Segment, fillet_line_circle, line_circle_intersection, map_segment, mirror_y, rotate,
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
    root_angle = _angle(side.root_end)
    if root_angle <= 0.0:
        raise ValueError("flank crosses the pole axis")
    if root_angle >= pitch / 2:
        raise ValueError("no room between neighbouring poles")
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


def _attribute_pole_fit(prefix: str, face_radius: float, arc: float, taper: float, root_radius: float,
                        fillet_radius: float, outward: bool, pitch: float) -> _PoleSide:
    """Build one pole's side, blaming the parameter that's actually responsible on failure.

    a. Pole face wider than the pole pitch -> *_pole_arc.
    b. Otherwise, if the same pole fits with no fillet but not with one -> *_fillet_radius.
    c. Otherwise (fails even without a fillet) -> *_pole_taper when taper != 0, else *_pole_arc.
    """
    try:
        return _pole_side(face_radius, arc, taper, root_radius, fillet_radius, outward, pitch)
    except ValueError as exc:
        if "wider than the pole pitch" in str(exc):
            raise _fit_error(f"{prefix}_pole_arc", "pole_fit", exc) from exc
        underlying = exc
        if fillet_radius > 0:
            try:
                _pole_side(face_radius, arc, taper, root_radius, 0.0, outward, pitch)
            except ValueError as sharp_exc:
                underlying = sharp_exc
            else:
                raise _fit_error(f"{prefix}_fillet_radius", "pole_fit", exc) from exc
        parameter = f"{prefix}_pole_taper" if taper != 0.0 else f"{prefix}_pole_arc"
        raise _fit_error(parameter, "pole_fit", underlying) from exc


def _upper_coil_boundary(p: RadialSRMParams) -> tuple[Segment, ...]:
    liner = p.slot_liner_thickness
    r_in = p.bore_radius + p.coil_inner_clearance
    r_out = p.stator_yoke_inner_radius - 2 * p.stator_fillet_radius - liner
    if r_out <= r_in:
        raise _fit_error("coil_inner_clearance", "coil_fit",
                         ValueError(f"coil radial extent {r_in:.5f}..{r_out:.5f} m is empty"))
    half = p.stator_pole_arc / 2
    face_end = (p.bore_radius * math.cos(half), p.bore_radius * math.sin(half))
    d = (math.cos(p.stator_pole_taper), math.sin(p.stator_pole_taper))
    n = (-d[1], d[0])
    # start well inside r_in so the first positive root is the crossing we want
    flank_start = (face_end[0] + liner * n[0] - p.bore_radius * d[0],
                   face_end[1] + liner * n[1] - p.bore_radius * d[1])
    alpha = math.pi / p.n_stator_poles
    u = (math.cos(alpha), math.sin(alpha))
    m = (math.sin(alpha), -math.cos(alpha))  # points from the slot centreline towards the pole
    centre_start = (0.5 * liner * m[0], 0.5 * liner * m[1])
    a, _ = line_circle_intersection(flank_start, d, r_in)
    b, _ = line_circle_intersection(flank_start, d, r_out)
    dd, _ = line_circle_intersection(centre_start, u, r_in)
    c, _ = line_circle_intersection(centre_start, u, r_out)
    if not (_angle(a) < _angle(dd) and _angle(b) < _angle(c)):
        raise _fit_error("slot_liner_thickness", "coil_fit", ValueError("no room for the coil between liners"))
    return (Line(a, b, "coil"), Arc(b, c, ORIGIN, "coil"), Line(c, dd, "coil"), Arc(dd, a, ORIGIN, "coil"))


def _coil_sides(p: RadialSRMParams) -> tuple[CoilSide, ...]:
    upper = _upper_coil_boundary(p)
    pitch = 2 * math.pi / p.n_stator_poles
    sides: list[CoilSide] = []
    for k in range(p.n_stator_poles):
        phase, group = k % p.n_phases, k // p.n_phases
        polarity = 1 if group % 2 == 0 else -1
        letter = chr(ord("A") + phase)
        a = k * pitch
        for sign, fn in ((polarity, lambda q: rotate(q, a)), (-polarity, lambda q: rotate(mirror_y(q), a))):
            boundary = tuple(map_segment(s, fn) for s in upper)
            sides.append(CoilSide(f"coil_{letter}{group + 1}{'+' if sign > 0 else '-'}", k, phase, sign, boundary))
    return tuple(sides)


def build_outline(p: RadialSRMParams) -> RadialOutline:
    stator_side = _attribute_pole_fit("stator", p.bore_radius, p.stator_pole_arc, p.stator_pole_taper,
                                      p.stator_yoke_inner_radius, p.stator_fillet_radius, True,
                                      2 * math.pi / p.n_stator_poles)
    rotor_side = _attribute_pole_fit("rotor", p.rotor_outer_radius, p.rotor_pole_arc, p.rotor_pole_taper,
                                     p.rotor_yoke_outer_radius, p.rotor_fillet_radius, False,
                                     2 * math.pi / p.n_rotor_poles)

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

    coil_sides = _coil_sides(p)
    refinement_features: dict[str, tuple[Segment | Point, ...]] = {"pole_tip": tips, "pole_root": roots}
    if p.slot_liner_thickness > 0:
        # The liner strip in slot_air is thin (slot_liner_thickness) compared to the generic
        # "iron"-scale element size, so it needs its own refinement feature to avoid forced
        # sliver triangles; see Task 11's quality-gate finding.
        refinement_features["slot_liner"] = tuple(seg for side in coil_sides for seg in side.boundary)

    return RadialOutline(
        stator_outer_radius=p.stator_outer_radius,
        stator_inner_boundary=stator,
        bore_radius=p.bore_radius,
        rotor_outer_radius=p.rotor_outer_radius,
        rotor_outer_boundary=rotor,
        shaft_radius=p.shaft_radius,
        band_inner_radius=p.band_inner_radius,
        band_outer_radius=p.band_outer_radius,
        coil_sides=coil_sides,
        refinement_features=refinement_features,
    )
