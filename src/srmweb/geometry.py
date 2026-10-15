"""Motor outline as SVG path data (millimetres, y flipped so SVG y points down)."""
from __future__ import annotations

import math

from srmcore.model.design import RadialSRMParams
from srmcore.model.errors import InputError
from srmcore.model.validator import validate_params
from srmcore.topology.primitives import Arc, Point, Segment
from srmcore.topology.radial import build_outline

_MM = 1000.0


def _num(v: float) -> str:
    return f"{round(v, 4) + 0.0:.4f}".rstrip("0").rstrip(".")


def _pt(p: Point) -> tuple[float, float]:
    return p[0] * _MM, -p[1] * _MM


def _xy(p: Point) -> str:
    x, y = _pt(p)
    return f"{_num(x)} {_num(y)}"


def _arc(seg: Arc) -> str:
    cx, cy = _pt(seg.center)
    sx, sy = _pt(seg.start)
    ex, ey = _pt(seg.end)
    ux, uy, vx, vy = sx - cx, sy - cy, ex - cx, ey - cy
    cross = ux * vy - uy * vx
    swept = abs(math.atan2(cross, ux * vx + uy * vy))
    large = int(swept > math.pi)
    sweep = int(cross > 0)  # SVG sweep 1 runs in the direction of increasing angle on screen
    r = _num(math.hypot(ux, uy))
    return f"A {r} {r} 0 {large} {sweep} {_num(ex)} {_num(ey)}"


def _circle(radius: float) -> str:
    r = _num(radius * _MM)
    return f"M {r} 0 A {r} {r} 0 0 1 -{r} 0 A {r} {r} 0 0 1 {r} 0 Z"


def _path(segments: tuple[Segment, ...]) -> str:
    parts: list[str] = []
    here: tuple[float, float] | None = None
    for seg in segments:
        if here is None or math.dist(here, _pt(seg.start)) > 1e-6:
            if parts:
                parts.append("Z")
            parts.append(f"M {_xy(seg.start)}")
        parts.append(_arc(seg) if isinstance(seg, Arc) else f"L {_xy(seg.end)}")
        here = _pt(seg.end)
    parts.append("Z")
    return " ".join(parts)


def outline_svg(machine: RadialSRMParams) -> dict:
    """Stator, rotor, shaft and coil-side paths. Raises InputError when a design rule fails."""
    issues = validate_params(machine)
    if any(i.severity == "error" for i in issues):
        raise InputError(issues)
    o = build_outline(machine)
    r = o.stator_outer_radius * _MM
    return {
        "view_box": [-r, -r, 2 * r, 2 * r],
        "stator": " ".join([_path(o.stator_outer_boundary) if o.stator_outer_boundary
                            else _circle(o.stator_outer_radius), _path(o.stator_inner_boundary),
                            *map(_path, o.stator_holes)]),
        "rotor": " ".join([_path(o.rotor_outer_boundary),
                           _path(o.rotor_inner_boundary) if o.rotor_inner_boundary else _circle(o.shaft_radius),
                           *map(_path, o.rotor_holes)]),
        "shaft": _circle(o.shaft_radius),
        "coils": [{"name": c.name, "phase": chr(ord("A") + c.phase),
                   "sign": "+" if c.sign > 0 else "-", "d": _path(c.boundary)}
                  for c in o.coil_sides],
    }
