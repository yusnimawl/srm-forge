"""Imported iron: conversions between model loops and outline segments, the canonical form, and the import checks.

Rules reported by `check_iron` (all with parameter "iron"):

- `open_loop`, `bad_segment`: a loop does not close; a zero-length or degenerate edge (an arc whose ends sit at
  different radii from its centre is not a minor arc of one circle).
- `centre`, `rotor_angle`: the drawing is shifted from the machine centre; the rotor is turned from angle 0.
- `self_intersection`, `bodies`: edges of one loop cross; loops cross each other or do not nest as the stator
  and rotor lamination.
- `stray_loop`: a loop that belongs to neither lamination.
- `air_gap`: iron outside the stator OD, inside the bore, outside the rotor radius or inside the shaft.
- `coil_overlap`, `repeat`, `web_width`.
"""
import math

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.spatial import cKDTree

from ..model.design import RadialSRMParams
from ..model.errors import ValidationIssue
from ..model.iron import ImportedIron, IronArc, IronLine, IronLoop
from ..model.validator import min_web_width
from .primitives import Arc, Line, Segment, sample_segment


def to_segments(loop: IronLoop) -> tuple[Segment, ...]:
    return tuple(Line(s.start, s.end) if isinstance(s, IronLine) else Arc(s.start, s.end, s.center) for s in loop)


def from_segments(segs: tuple[Segment, ...]) -> IronLoop:
    return tuple(IronLine(start=s.start, end=s.end) if isinstance(s, Line)
                 else IronArc(start=s.start, end=s.end, center=s.center) for s in segs)


def parametric_iron(p: RadialSRMParams) -> ImportedIron:
    """The contours of the parametric machine (ignoring `p.iron`): stator outer circle and shaft circle as
    four quarter arcs from angle 0, all in canonical form, the salient stator bore and rotor outer outlines, and no holes."""
    from .radial import _full_circle, parametric_outline  # radial imports this module

    o = parametric_outline(p)
    canon = lambda segs: _canonical(list(segs), p)  # noqa: E731
    return ImportedIron(
        stator_outer=canon(_full_circle(p.stator_outer_radius, "")),
        stator_bore=canon(o.stator_inner_boundary),
        rotor_outer=canon(o.rotor_outer_boundary),
        rotor_bore=canon(_full_circle(p.shaft_radius, "")),
    )


STEP = 1e-4        # sampling step along contours (m)
TOL = 1e-6         # geometric tolerance (m)
_CHUNK = 256
_REFINE = 256     # candidate web pairs measured exactly


def _issue(rule: str, message: str) -> ValidationIssue:
    return ValidationIssue("iron", rule, message)


def _at(q) -> str:
    return f"({q[0] * 1e3:.1f}, {q[1] * 1e3:.1f}) mm"


def _rot(pts: np.ndarray, angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return pts @ np.array([[c, s], [-s, c]])


def _sample_loop(segs, step: float = STEP) -> np.ndarray:
    pts: list = []
    for s in segs:
        pts.extend(sample_segment(s, step)[:-1])
    return np.array(pts)


def _seg_dist(pts: np.ndarray, seg: Segment) -> np.ndarray:
    if isinstance(seg, Line):
        a = np.array(seg.start)
        d = np.array(seg.end) - a
        l2 = float(d @ d)
        t = np.clip(((pts - a) @ d) / l2, 0.0, 1.0) if l2 > 0 else np.zeros(len(pts))
        return np.hypot(*(pts - (a + t[:, None] * d)).T)
    c = np.array(seg.center)
    rel = pts - c
    a0 = math.atan2(seg.start[1] - c[1], seg.start[0] - c[0])
    a1 = math.atan2(seg.end[1] - c[1], seg.end[0] - c[0])
    delta = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    u = ((np.arctan2(rel[:, 1], rel[:, 0]) - a0) * math.copysign(1.0, delta)) % (2 * math.pi)
    d_arc = np.abs(np.hypot(rel[:, 0], rel[:, 1]) - math.dist(seg.start, seg.center))
    d_end = np.minimum(np.hypot(*(pts - np.array(seg.start)).T), np.hypot(*(pts - np.array(seg.end)).T))
    return np.where(u <= abs(delta), d_arc, d_end)


def _dist(pts: np.ndarray, segs) -> np.ndarray:
    """Exact distance from every point to the nearest of the segments."""
    out = np.full(len(pts), np.inf)
    for s in segs:
        np.minimum(out, _seg_dist(pts, s), out=out)
    return out


def _inside(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Even-odd point-in-polygon for every row of pts."""
    x0, y0 = poly[:, 0][None, :], poly[:, 1][None, :]
    nxt = np.roll(poly, -1, axis=0)
    x1, y1 = nxt[:, 0][None, :], nxt[:, 1][None, :]
    out = np.empty(len(pts), dtype=bool)
    for k in range(0, len(pts), _CHUNK):
        x, y = pts[k:k + _CHUNK, 0][:, None], pts[k:k + _CHUNK, 1][:, None]
        straddle = (y0 > y) != (y1 > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xi = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
        out[k:k + _CHUNK] = (straddle & (x < xi)).sum(axis=1) % 2 == 1
    return out


def _parity(pts: np.ndarray, polys) -> np.ndarray:
    n = np.zeros(len(pts), dtype=int)
    for poly in polys:
        n += _inside(pts, poly)
    return n % 2 == 1


class _Body:
    """One lamination: its loops (outer, bore, holes), their samples and the pole counts of the machine."""

    def __init__(self, name: str, n: int, p: RadialSRMParams, loops, labels):
        self.name, self.n, self.labels = name, n, labels
        self.ns, self.nr = p.n_stator_poles, p.n_rotor_poles
        self.loops = [to_segments(loop) for loop in loops]
        self.segs = [s for loop in self.loops for s in loop]
        self.pts: list[np.ndarray] = []


def _loop_issues(body: _Body) -> list[ValidationIssue]:
    out = []
    for label, segs in zip(body.labels, body.loops):
        if len(segs) < 2:
            where = _at(segs[0].start) if segs else _at((0.0, 0.0))
            out.append(_issue("bad_segment", f"The {body.name} {label} contour near {where} has fewer than 2 edges. "
                              "Redraw it as a closed contour."))
            continue
        for i, s in enumerate(segs):
            nxt = segs[(i + 1) % len(segs)]
            if math.dist(s.end, nxt.start) > TOL:
                out.append(_issue("open_loop", f"The {body.name} {label} contour is open near {_at(s.end)}."))
            if math.dist(s.start, s.end) < TOL:
                out.append(_issue("bad_segment", f"Zero-length edge in the {body.name} {label} contour at {_at(s.start)}."))
            elif isinstance(s, Arc) and math.dist(s.start, s.end) >= 2 * math.dist(s.start, s.center) * math.sin(math.pi / 2 - 1e-6):
                out.append(_issue("bad_segment", f"Arc in the {body.name} {label} contour near {_at(s.start)} sweeps "
                                  f"180° or more; split it in two. {_REEXPORT}"))
            elif isinstance(s, Arc) and abs(math.dist(s.start, s.center) - math.dist(s.end, s.center)) > TOL:
                out.append(_issue("bad_segment", f"Arc in the {body.name} {label} contour near {_at(s.start)} is not a "
                                  "minor arc of one circle (its ends are at different radii from its centre)."))
    return out


MAX_SEGMENTS = 20_000
_CANON_TOL = 2e-7  # the 0.1 µm rounding of the canonical form, twice (rounding after snapping is not idempotent)
_REEXPORT = "Export and re-import the DXF to get canonical coordinates."


def _trust_issues(p: RadialSRMParams, loops) -> list[ValidationIssue]:
    """Refuse what the later checks cannot measure safely: too many segments, non-finite or far-away
    coordinates."""
    if sum(len(loop) for loop in loops) > MAX_SEGMENTS:
        return [_issue("bad_segment", f"The iron has more than {MAX_SEGMENTS} edges; simplify the drawing.")]
    reach = 1.5 * p.stator_outer_radius
    for loop in loops:
        for s in loop:
            pts = (s.start, s.end) + ((s.center,) if isinstance(s, IronArc) else ())
            for q in pts:
                if not all(math.isfinite(c) for c in q):
                    return [_issue("bad_segment", f"An edge has a non-finite coordinate (near {_at(s.start)}).")]
                if math.hypot(*q) > reach:
                    return [_issue("bad_segment", f"An edge near {_at(q)} is farther than 1.5 x the stator outer radius "
                                   f"({reach * 1e3:.1f} mm) from the machine centre.")]
    return []


def _not_canonical(p: RadialSRMParams, loops) -> list[ValidationIssue]:
    """Each loop must equal the form `iron_from_loops` produces (what meshing and the repeat checks rely on)."""
    for loop in loops:
        want = _canonical(list(to_segments(loop)), p)
        if len(want) != len(loop) or any(
                type(a) is not type(b) or max(math.dist(a.start, b.start), math.dist(a.end, b.end)) > _CANON_TOL
                or (isinstance(a, IronArc) and math.dist(a.center, b.center) > _CANON_TOL) for a, b in zip(loop, want)):
            return [_issue("bad_segment", f"The contour near {_at(loop[0].start)} is not in canonical form. {_REEXPORT}")]
    return []


def _crossings(bodies: list[_Body]) -> list[ValidationIssue]:
    """Sampled edges that cross: of two loops (bodies) or of one loop (self_intersection)."""
    pts, lid, nxt, tag = [], [], [], []
    base = 0
    for body in bodies:
        for label, arr in zip(body.labels, body.pts):
            n = len(arr)
            pts.append(arr)
            lid.append(np.full(n, len(tag)))
            nxt.append(base + (np.arange(n) + 1) % n)
            tag.append(f"{body.name} {label}")
            base += n
    P, lid, nxt = np.vstack(pts), np.concatenate(lid), np.concatenate(nxt)
    pr = cKDTree(P).query_pairs(2.0001 * STEP, output_type="ndarray")
    if not len(pr):
        return []
    i, j = pr[:, 0], pr[:, 1]
    adjacent = (lid[i] == lid[j]) & ((nxt[i] == j) | (nxt[j] == i) | (nxt[i] == nxt[j]))
    i, j = i[~adjacent], j[~adjacent]
    a0, a1, b0, b1 = P[i], P[nxt[i]], P[j], P[nxt[j]]

    def cross(o, u, v):
        return (u[:, 0] - o[:, 0]) * (v[:, 1] - o[:, 1]) - (u[:, 1] - o[:, 1]) * (v[:, 0] - o[:, 0])

    hit = (cross(a0, a1, b0) * cross(a0, a1, b1) < 0) & (cross(b0, b1, a0) * cross(b0, b1, a1) < 0)
    out, seen = [], set()
    for k in np.nonzero(hit)[0]:
        la, lb = int(lid[i[k]]), int(lid[j[k]])
        if (min(la, lb), max(la, lb)) in seen:
            continue
        seen.add((min(la, lb), max(la, lb)))
        where = _at((a0[k] + b0[k]) / 2)
        if la == lb:
            out.append(_issue("self_intersection", f"The {tag[la]} contour crosses itself near {where}."))
        else:
            out.append(_issue("bodies", f"The {tag[la]} and {tag[lb]} contours cross near {where}; "
                              "each lamination must be one connected piece."))
    return out


def _nesting(stator: _Body, rotor: _Body) -> list[ValidationIssue]:
    out = []

    def inside(pt, polys) -> bool:
        return bool(_parity(np.array([pt]), polys)[0])

    s_out, s_bore, r_out, r_bore = stator.pts[0], stator.pts[1], rotor.pts[0], rotor.pts[1]
    if not inside(s_bore[0], [s_out]):
        out.append(_issue("bodies", f"The stator bore contour near {_at(s_bore[0])} is outside the stator outer contour."))
    if not inside(r_out[0], [s_bore]):
        out.append(_issue("bodies", f"The rotor outer contour near {_at(r_out[0])} is outside the stator bore."))
    if not inside(r_bore[0], [r_out]):
        out.append(_issue("bodies", f"The rotor bore contour near {_at(r_bore[0])} is outside the rotor outer contour."))
    for body, shell, hollow in ((stator, s_out, s_bore), (rotor, r_out, r_bore)):
        holes = body.pts[2:]
        for k, h in enumerate(holes):
            others = [o for m, o in enumerate(holes) if m != k]
            if not inside(h[0], [shell]) or inside(h[0], [hollow]) or inside(h[0], others):
                out.append(_issue("stray_loop", f"A {body.name} hole near {_at(h[0])} is not inside the lamination material."))
    return out


def _centre(p: RadialSRMParams, bodies: list[_Body]) -> list[ValidationIssue]:
    radii = (p.stator_outer_radius, p.bore_radius, p.rotor_outer_radius, p.shaft_radius)
    for body in bodies:
        for s in body.segs:
            if isinstance(s, Arc) and math.hypot(*s.center) > TOL and any(
                    abs(math.dist(s.start, s.center) - r) <= TOL for r in radii):
                return [_issue("centre", f"The drawing is off-centre: the circle at {_at(s.start)} is centred at "
                               f"({s.center[0] * 1e3:.2f}, {s.center[1] * 1e3:.2f}) mm. Move the machine centre to (0, 0).")]
    return []


def _rotor_angle(p: RadialSRMParams, rotor: _Body) -> list[ValidationIssue]:
    """The rotation of the parametric rotor vertices that best fits the imported rotor contour must be zero."""
    pitch = 2 * math.pi / p.n_rotor_poles
    v = np.array([s.start for s in parametric_iron(p).rotor_outer])
    segs = rotor.loops[0]

    def cost(phi: float) -> float:
        return float(np.median(_dist(_rot(v, -phi), segs)))

    step = math.radians(0.5)
    grid = np.arange(-pitch / 2 + step, pitch / 2 + step / 2, step)
    best = float(grid[int(np.argmin([cost(g) for g in grid]))])
    phi = minimize_scalar(cost, bounds=(best - step, best + step), method="bounded", options={"xatol": 1e-10}).x
    phi = (phi + pitch / 2) % pitch - pitch / 2
    if abs(phi) <= 1e-4:
        return []
    return [_issue("rotor_angle", f"The rotor is turned {math.degrees(phi):.2f}° from the exported position "
                   "(a rotor pole on phase A at 0°). Turn it back to 0° before importing.")]


def _air_gap(p: RadialSRMParams, stator: _Body, rotor: _Body) -> list[ValidationIssue]:
    out = []
    checks = (
        (stator, 0, True, p.stator_outer_radius, "stator outer", "beyond the stator outside radius"),
        (stator, 1, False, p.bore_radius, "stator bore",
         "inside the bore radius; pole faces may be notched outward from the gap, never into it"),
        (rotor, 0, True, p.rotor_outer_radius, "rotor outer",
         "beyond the rotor radius; rotor edits may only cut inward"),
        (rotor, 1, False, p.shaft_radius, "rotor bore", "inside the shaft radius; the shaft stays a circle"),
    )
    for body, k, upper, bound, label, text in checks:
        pts = body.pts[k]
        r = np.hypot(pts[:, 0], pts[:, 1])
        bad = np.nonzero(r > bound + TOL if upper else r < bound - TOL)[0]
        if len(bad):
            q = bad[int(np.argmax(r[bad] if upper else -r[bad]))]
            out.append(_issue("air_gap", f"Iron of the {label} contour near {_at(pts[q])} reaches {r[q] * 1e3:.2f} mm, "
                              f"{text} ({bound * 1e3:.2f} mm)."))
    return out


def _coil_overlap(p: RadialSRMParams, stator: _Body) -> list[ValidationIssue]:
    from .radial import _coil_sides  # radial imports this module

    half = p.slot_liner_thickness / 2
    sides = [side.boundary for side in _coil_sides(p)]
    pts = np.vstack(stator.pts[1:])  # the bore and the holes; the outer contour is far from the coils
    near = np.nonzero(_dist(pts, [s for b in sides for s in b]) < half)[0]
    if len(near):
        return [_issue("coil_overlap", f"Iron near {_at(pts[near[0]])} is closer than half the slot-liner thickness "
                       f"({half * 1e3:.2f} mm) to a coil. Keep iron out of the coil region.")]
    coil_pts = np.vstack([_sample_loop(b, 2e-3) for b in sides])
    # coils lie inside the outer contour, so a point is in iron when it is in none or an even number of the others
    inside = np.nonzero(~_parity(coil_pts, stator.pts[1:]))[0]
    inside = inside[_dist(coil_pts[inside], stator.segs) > TOL]
    if len(inside):
        return [_issue("coil_overlap", f"A coil near {_at(coil_pts[inside[0]])} lies inside solid iron. "
                       "Keep iron out of the coil region (the slots must stay open).")]
    for b in sides:
        poly = _sample_loop(b)
        sel = np.nonzero(np.all((pts >= poly.min(axis=0)) & (pts <= poly.max(axis=0)), axis=1))[0]
        if len(sel):
            hit = sel[_inside(pts[sel], poly) & (_dist(pts[sel], b) > TOL)]
            if len(hit):
                return [_issue("coil_overlap", f"Iron near {_at(pts[hit[0]])} lies inside a coil region. "
                               "Keep iron out of the coil region.")]
    return []


def _repeat(body: _Body) -> list[ValidationIssue]:
    ang = 2 * math.pi / body.n
    pts = np.vstack(body.pts)
    bad = np.nonzero(_dist(_rot(pts, ang), body.segs) > TOL)[0]
    if not len(bad):
        return []
    q = pts[bad[0]]
    k = sum(1 for j in range(body.n) if _dist(_rot(q[None, :], j * ang), body.segs)[0] <= TOL)
    return [_issue("repeat", f"{body.name.capitalize()} edit near ({q[0] * 1e3:.1f}, {q[1] * 1e3:.1f}) mm repeats {k} "
                   f"times; it must repeat every {360 / body.n:g}° ({body.n} times on this {body.ns}/{body.nr} "
                   f"{body.name}). Draw it once and polar-array it {body.n}× around the centre.")]


def _web(body: _Body, web: float) -> list[ValidationIssue]:
    """The narrowest iron: the smallest distance between two boundary samples that face each other across iron
    (a ball centred at their midpoint touches the boundary at both)."""
    P = np.vstack(body.pts)
    lid = np.concatenate([np.full(len(a), k) for k, a in enumerate(body.pts)])
    idx = np.concatenate([np.arange(len(a)) for a in body.pts])
    ln = np.concatenate([np.full(len(a), len(a)) for a in body.pts])
    tree = cKDTree(P)
    pr = tree.query_pairs(web * 1.05, output_type="ndarray")
    if not len(pr):
        return []
    i, j = pr[:, 0], pr[:, 1]
    gap = np.abs(idx[i] - idx[j])
    gap = np.minimum(gap, ln[i] - gap)
    keep = ~((lid[i] == lid[j]) & (gap <= 3))
    i, j = i[keep], j[keep]
    d = np.hypot(*(P[i] - P[j]).T)
    mid = (P[i] + P[j]) / 2
    # the nearest sample is never closer than the true boundary, so this only discards impossible pairs
    keep = (tree.query(mid)[0] >= 0.9 * d / 2) & (d < web * 1.05)
    d, mid = d[keep], mid[keep]
    order = np.argsort(d)
    d, mid, i, j = d[order], mid[order], i[keep][order], j[keep][order]
    found: list[int] = []
    for k in range(0, len(d), _CHUNK):
        m = mid[k:k + _CHUNK]
        ok = (_dist(m, body.segs) >= 0.9 * d[k:k + _CHUNK] / 2) & _parity(m, body.pts)
        found.extend(k + int(n) for n in np.nonzero(ok)[0])
        if len(found) >= _REFINE:
            break
    best = None
    for n in found[:_REFINE]:
        w = _exact_width(body, P[i[n]], P[j[n]])
        if best is None or w[0] < best[0]:
            best = w
    if best is not None and best[0] < web - 1e-9:
        return [_issue("web_width", f"The {body.name} iron is only {best[0] * 1e3:.2f} mm wide near {_at(best[1])}; "
                       f"the minimum is {web * 1e3:.2f} mm (max(1 mm, 2 x lamination thickness)). "
                       "Thicken it or move the hole or groove.")]
    return []


def _facing(body: _Body, q: np.ndarray) -> list[Segment]:
    return [s for s in body.segs if _seg_dist(q[None, :], s)[0] < 1e-9]


def _slide(seg: Segment, q: np.ndarray) -> np.ndarray:
    """Points of the segment within one sampling step of q, 1 µm apart."""
    t = np.linspace(-STEP, STEP, 201)
    if isinstance(seg, Line):
        u = np.array(seg.end) - np.array(seg.start)
        pts = q + t[:, None] * (u / np.hypot(*u))
    else:
        c = np.array(seg.center)
        r = math.dist(seg.start, seg.center)
        a = np.arctan2(q[1] - c[1], q[0] - c[0]) + t / r
        pts = c + r * np.stack([np.cos(a), np.sin(a)], axis=1)
    return pts[_seg_dist(pts, seg) < 1e-9]


def _exact_width(body: _Body, a: np.ndarray, b: np.ndarray) -> tuple[float, np.ndarray]:
    """The width across iron between two facing boundary samples, from exact distances: each point slides along
    its own edge and is measured to the edges at the other point."""
    best = (math.dist(a, b), (a + b) / 2)
    for p0, p1 in ((a, b), (b, a)):
        other = _facing(body, p1)
        for seg in _facing(body, p0):
            pts = _slide(seg, p0)
            if len(pts):
                d = _dist(pts, other)
                k = int(np.argmin(d))
                if d[k] < best[0]:
                    best = (float(d[k]), (pts[k] + p1) / 2)
    return best


def check_iron(p: RadialSRMParams) -> list[ValidationIssue]:
    """The iron checks of spec section 5 on `p.iron` against the machine parameters in `p`. Structural problems
    (open or degenerate loops, a shifted drawing, crossing or mis-nested loops) are returned alone, because the
    other checks need sound contours."""
    iron = p.iron
    if iron is None:
        return []
    all_loops = [iron.stator_outer, iron.stator_bore, *iron.stator_holes,
                 iron.rotor_outer, iron.rotor_bore, *iron.rotor_holes]
    if issues := _trust_issues(p, all_loops):
        return issues
    stator = _Body("stator", p.n_stator_poles, p, [iron.stator_outer, iron.stator_bore, *iron.stator_holes],
                   ["outer", "bore"] + ["hole"] * len(iron.stator_holes))
    rotor = _Body("rotor", p.n_rotor_poles, p, [iron.rotor_outer, iron.rotor_bore, *iron.rotor_holes],
                  ["outer", "bore"] + ["hole"] * len(iron.rotor_holes))
    issues = _loop_issues(stator) + _loop_issues(rotor)
    if issues:
        return issues
    if issues := _not_canonical(p, all_loops):
        return issues
    for b in (stator, rotor):
        b.pts = [_sample_loop(loop) for loop in b.loops]
    issues = _centre(p, [stator, rotor]) or (_crossings([stator, rotor]) + _nesting(stator, rotor))
    if issues:
        return issues
    web = min_web_width(p)
    return (_rotor_angle(p, rotor) + _air_gap(p, stator, rotor) + _coil_overlap(p, stator)
            + _repeat(stator) + _repeat(rotor) + _web(stator, web) + _web(rotor, web))


# --- loops to ImportedIron ---------------------------------------------------------------------

def _flip(s: Segment) -> Segment:
    return Line(s.end, s.start, s.tag) if isinstance(s, Line) else Arc(s.end, s.start, s.center, s.tag)


def _chain(loop) -> list[Segment]:
    """The loop's segments each oriented to continue the previous one (closure is left to check_iron)."""
    segs = list(loop)
    if len(segs) > 1:
        a, b = segs[0], segs[1]
        if (min(math.dist(a.end, b.start), math.dist(a.end, b.end)) > TOL
                and min(math.dist(a.start, b.start), math.dist(a.start, b.end)) <= TOL):
            segs[0] = _flip(a)
    for i in range(1, len(segs)):
        if math.dist(segs[i - 1].end, segs[i].start) > TOL and math.dist(segs[i - 1].end, segs[i].end) <= TOL:
            segs[i] = _flip(segs[i])
    return segs


def _matches(loop, boundary) -> bool:
    from .radial import _same_segment  # radial imports this module

    return len(loop) == len(boundary) and all(any(_same_segment(s, b) for b in boundary) for s in loop)


def _angle_key(q) -> tuple[float, float]:
    a = math.atan2(q[1], q[0])
    a = 0.0 if -1e-9 < a < 0 else a % (2 * math.pi)
    return (round(a, 9), round(math.hypot(*q), 9))


def _canonical(segs: list[Segment], p: RadialSRMParams) -> IronLoop:
    """Coordinates rounded to 0.1 µm, arc centres near the origin on it, vertices near the bore, rotor, stator OD
    or shaft circle on it, counter-clockwise, starting at the vertex with the smallest (angle, radius)."""
    circles = (p.stator_outer_radius, p.bore_radius, p.rotor_outer_radius, p.shaft_radius)

    def vertex(q):
        x, y = round(q[0], 7), round(q[1], 7)
        r = math.hypot(x, y)
        for c in circles:
            if r > 0 and abs(r - c) < TOL:
                return (x * c / r, y * c / r)
        return (x, y)

    def centre(q):
        x, y = round(q[0], 7), round(q[1], 7)
        return (0.0, 0.0) if math.hypot(x, y) < TOL else (x, y)

    ends = [vertex(s.end) for s in segs]
    out: list[Segment] = []
    for i, s in enumerate(segs):
        a, b = ends[i - 1], ends[i]
        out.append(Line(a, b) if isinstance(s, Line) else Arc(a, b, centre(s.center)))
    poly = _sample_loop(out)
    if float(np.dot(poly[:, 0], np.roll(poly[:, 1], -1)) - np.dot(poly[:, 1], np.roll(poly[:, 0], -1))) < 0:
        out = [_flip(s) for s in reversed(out)]
    first = min(range(len(out)), key=lambda i: _angle_key(out[i].start))
    return from_segments(tuple(out[first:] + out[:first]))


def _classify(loops: list[list[Segment]], p: RadialSRMParams):
    """Nest the loops into stator outer, bore and holes, rotor outer, bore and holes (spec 5.4)."""
    polys = [_sample_loop(loop) for loop in loops]
    area = [abs(float(np.dot(q[:, 0], np.roll(q[:, 1], -1)) - np.dot(q[:, 1], np.roll(q[:, 0], -1)))) / 2 for q in polys]
    n = len(loops)
    parent: list[int | None] = []
    for j in range(n):
        cands = [i for i in range(n) if i != j and _inside(polys[j][:1], polys[i])[0]]
        parent.append(min(cands, key=lambda i: area[i]) if cands else None)
    kids = lambda i: [j for j in range(n) if parent[j] == i]  # noqa: E731
    origin = np.zeros((1, 2))
    around = lambda i: bool(_inside(origin, polys[i])[0])  # noqa: E731
    issues: list[ValidationIssue] = []
    used: set[int] = set()
    roles: dict = {"sh": [], "rh": []}
    roots = sorted((i for i in range(n) if parent[i] is None), key=lambda i: -area[i])
    if not roots:
        return None, [_issue("bodies", f"No iron outline found near {_at((0.0, 0.0))}; the drawing needs the stator "
                             "and rotor contours (coil outlines are ignored).")]
    roles["so"] = roots[0]
    used.add(roots[0])
    bore = [k for k in kids(roots[0]) if around(k)]
    if not bore:
        issues.append(_issue("bodies", f"No stator bore loop around the centre near {_at((p.bore_radius, 0.0))}. "
                             "Close the stator bore contour and keep it around the machine centre."))
    else:
        roles["sb"] = bore[0]
        used.add(bore[0])
        for k in kids(roots[0]):
            if k != bore[0] and not kids(k):
                roles["sh"].append(k)
                used.add(k)
        rkids = kids(bore[0])
        rotor = [k for k in rkids if around(k)]
        if not rotor:
            where = _at(polys[rkids[0]][0]) if rkids else _at((p.rotor_outer_radius, 0.0))
            issues.append(_issue("bodies", f"The rotor must be one closed loop around the centre; found {len(rkids)} "
                                 f"loop(s) inside the stator bore (first near {where}) and none around the centre. "
                                 "Join the rotor pieces into one contour."))
        else:
            roles["ro"] = rotor[0]
            used.add(rotor[0])
            inner = [k for k in kids(rotor[0]) if around(k)]
            if not inner:
                issues.append(_issue("bodies", f"No rotor bore loop around the centre near {_at((p.shaft_radius, 0.0))}. "
                                     "Draw the shaft circle inside the rotor outline."))
            else:
                roles["rb"] = inner[0]
                used.add(inner[0])
                for k in kids(rotor[0]):
                    if k != inner[0] and not kids(k):
                        roles["rh"].append(k)
                        used.add(k)
    if not issues:
        for i in range(n):
            if i not in used:
                issues.append(_issue("stray_loop", f"The loop near {_at(polys[i][0])} is not part of the stator or rotor "
                                     "lamination or a coil outline."))
    return (None if issues else roles), issues


def iron_from_loops(loops: list[tuple[Segment, ...]], p: RadialSRMParams) -> tuple[ImportedIron | None, list[ValidationIssue]]:
    """Closed loops (metres, machine centre at the origin) to canonical `ImportedIron` and the problems found.

    Loops that match a parametric coil side (1 µm) are dropped first. Iron is None when any issue is an error."""
    from .radial import _coil_sides  # radial imports this module

    coils = [side.boundary for side in _coil_sides(p)]
    rest = [_chain(loop) for loop in loops if not any(_matches(loop, c) for c in coils)]
    if any(len(loop) < 2 for loop in rest):
        bad = next(loop for loop in rest if len(loop) < 2)
        return None, [_issue("bad_segment", f"A loop near {_at(bad[0].start)} has fewer than 2 edges. "
                             "Redraw it as a closed contour.")]
    gaps = [_issue("open_loop", f"A contour is open near {_at(s.end)} (gap {math.dist(s.end, loop[(i + 1) % len(loop)].start) * 1e3:.3f} mm). "
                   "Close the loop so its ends meet within 1 µm.")
            for loop in rest for i, s in enumerate(loop) if math.dist(s.end, loop[(i + 1) % len(loop)].start) > TOL]
    if gaps:
        return None, gaps
    roles, issues = _classify(rest, p)
    if roles is None:
        return None, issues
    canon = lambda i: _canonical(rest[i], p)  # noqa: E731
    holes = lambda ids: tuple(sorted((canon(i) for i in ids), key=lambda h: _angle_key(h[0].start)))  # noqa: E731
    iron = ImportedIron(stator_outer=canon(roles["so"]), stator_bore=canon(roles["sb"]), stator_holes=holes(roles["sh"]),
                        rotor_outer=canon(roles["ro"]), rotor_bore=canon(roles["rb"]), rotor_holes=holes(roles["rh"]))
    found = check_iron(p.model_copy(update={"iron": iron}))
    return (None if any(i.severity == "error" for i in found) else iron), found


# --- areas -------------------------------------------------------------------------------------

def _loop_area(loop: IronLoop) -> float:
    """Area enclosed by a loop: the chord polygon plus the circular segment of each arc, exact."""
    signed = 0.0
    for s in to_segments(loop):
        (x0, y0), (x1, y1) = s.start, s.end
        signed += (x0 * y1 - x1 * y0) / 2
        if isinstance(s, Arc):
            r = math.dist(s.start, s.center)
            theta = 2 * math.asin(min(1.0, math.dist(s.start, s.end) / (2 * r)))
            ccw = ((x0 - s.center[0]) * (y1 - s.center[1]) - (y0 - s.center[1]) * (x1 - s.center[0])) > 0
            signed += (1 if ccw else -1) * r * r / 2 * (theta - math.sin(theta))
    return abs(signed)


def iron_areas(iron: ImportedIron) -> tuple[float, float]:
    """(stator, rotor) lamination areas in m², holes subtracted."""
    stator = _loop_area(iron.stator_outer) - _loop_area(iron.stator_bore) - sum(_loop_area(h) for h in iron.stator_holes)
    rotor = _loop_area(iron.rotor_outer) - _loop_area(iron.rotor_bore) - sum(_loop_area(h) for h in iron.rotor_holes)
    return stator, rotor
