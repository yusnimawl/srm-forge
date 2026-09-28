"""2D outline primitives. Points are (x, y) in metres; circles are centred at the origin unless stated."""
import math
from collections.abc import Callable
from dataclasses import dataclass

Point = tuple[float, float]


@dataclass(frozen=True)
class Line:
    start: Point
    end: Point
    tag: str = ""


@dataclass(frozen=True)
class Arc:
    """Minor arc (< π) from start to end around center."""
    start: Point
    end: Point
    center: Point
    tag: str = ""


Segment = Line | Arc


def rotate(p: Point, angle: float) -> Point:
    c, s = math.cos(angle), math.sin(angle)
    return (c * p[0] - s * p[1], s * p[0] + c * p[1])


def mirror_y(p: Point) -> Point:
    return (p[0], -p[1])


def map_segment(seg: Segment, fn: Callable[[Point], Point]) -> Segment:
    if isinstance(seg, Line):
        return Line(fn(seg.start), fn(seg.end), seg.tag)
    return Arc(fn(seg.start), fn(seg.end), fn(seg.center), seg.tag)


def reverse(seg: Segment) -> Segment:
    if isinstance(seg, Line):
        return Line(seg.end, seg.start, seg.tag)
    return Arc(seg.end, seg.start, seg.center, seg.tag)


def line_circle_intersection(p0: Point, d: Point, radius: float,
                             t_ref: float | None = None) -> tuple[Point, float]:
    """Intersect p0 + t*d (|d| = 1) with |x| = radius.

    Returns the smallest positive root, or the root closest to t_ref when given.
    """
    px, py = p0
    dx, dy = d
    b = px * dx + py * dy
    c = px * px + py * py - radius * radius
    disc = b * b - c
    if disc < 0:
        raise ValueError("line does not reach the circle")
    sq = math.sqrt(disc)
    roots = (-b - sq, -b + sq)
    if t_ref is None:
        positive = [t for t in roots if t > 1e-15]
        if not positive:
            raise ValueError("circle is behind the line start")
        t = min(positive)
    else:
        t = min(roots, key=lambda r: abs(r - t_ref))
    return (px + t * dx, py + t * dy), t


@dataclass(frozen=True)
class Fillet:
    center: Point
    on_line: Point
    on_circle: Point
    t_line: float


def fillet_line_circle(p0: Point, d: Point, n: Point, circle_radius: float,
                       fillet_radius: float, inside: bool) -> Fillet:
    """Fillet of radius r tangent to the line p0 + t*d and to the circle |x| = R.

    n is the unit normal of the line pointing to the side the fillet lies on.
    inside=True: fillet inside the circle (|centre| = R - r); False: outside (|centre| = R + r).
    """
    r = fillet_radius
    _, t_corner = line_circle_intersection(p0, d, circle_radius)
    centre_radius = circle_radius - r if inside else circle_radius + r
    offset_start = (p0[0] + r * n[0], p0[1] + r * n[1])
    centre, t = line_circle_intersection(offset_start, d, centre_radius, t_ref=t_corner)
    if not (0.0 < t <= t_corner + 1e-12):
        raise ValueError("fillet does not fit on the line segment")
    on_line = (centre[0] - r * n[0], centre[1] - r * n[1])
    k = circle_radius / math.hypot(*centre)
    return Fillet(centre, on_line, (centre[0] * k, centre[1] * k), t)


def sample_segment(seg: Segment, max_step: float) -> list[Point]:
    """Points along the segment, spaced at most max_step apart, both endpoints included."""
    if isinstance(seg, Line):
        length = math.dist(seg.start, seg.end)
        n = max(1, math.ceil(length / max_step))
        return [(seg.start[0] + (seg.end[0] - seg.start[0]) * i / n,
                 seg.start[1] + (seg.end[1] - seg.start[1]) * i / n) for i in range(n + 1)]
    cx, cy = seg.center
    r = math.dist(seg.start, seg.center)
    a0 = math.atan2(seg.start[1] - cy, seg.start[0] - cx)
    a1 = math.atan2(seg.end[1] - cy, seg.end[0] - cx)
    delta = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi   # minor arc, signed
    n = max(1, math.ceil(abs(delta) * r / max_step))
    return [(cx + r * math.cos(a0 + delta * i / n), cy + r * math.sin(a0 + delta * i / n)) for i in range(n + 1)]
