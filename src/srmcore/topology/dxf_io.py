"""DXF export and import of the laminations. This is the only module that imports ezdxf.

`read_loops` reads the bytes with ezdxf's recover reader (ASCII or binary DXF, any line ending or encoding) and handles the file-level rules (`dxf_units`, `dxf_flat`, `dxf_entity`), chains the entities into
closed loops (an open chain is reported as `open_loop`) and reports duplicate or overlapping edges (`overlap`).
Loops are in metres. Everything else is checked by `iron_from_loops`.
"""
import io
import math

import ezdxf
from ezdxf import recover
from ezdxf.audit import AuditError
from ezdxf.document import Drawing
from ezdxf.lldxf.tagger import binary_tags_loader
import numpy as np
from ezdxf.math import bulge_to_arc
from scipy.spatial import cKDTree

from ..model.design import RadialSRMParams
from ..model.errors import ValidationIssue
from ..model.iron import ImportedIron, IronArc
from .imported import TOL, _at, _issue, iron_areas, iron_from_loops, parametric_iron, to_segments
from .primitives import Arc, Line, Segment

# $INSUNITS code -> metres per drawing unit (0 = unitless, read as mm)
_UNITS = {0: 1e-3, 1: 0.0254, 4: 1e-3, 6: 1.0}
_IGNORED = {"TEXT", "MTEXT", "DIMENSION", "HATCH", "POINT"}
_AREA_CHANGE = 0.10
_SPLINE_CHORD = 1e-6   # m
_GEOMETRY = {"LINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE", "LWPOLYLINE", "POLYLINE", "INSERT"}
_BINARY_SENTINEL = b"AutoCAD Binary DXF"


# --- write -------------------------------------------------------------------------------------

def _is_circle(loop) -> bool:
    return (len(loop) >= 2 and all(isinstance(s, IronArc) and math.hypot(*s.center) < TOL for s in loop)
            and max(math.hypot(*s.start) for s in loop) - min(math.hypot(*s.start) for s in loop) < TOL)


def _add_segments(msp, segs, layer: str) -> None:
    mm = 1e3
    for s in segs:
        a, b = (s.start[0] * mm, s.start[1] * mm), (s.end[0] * mm, s.end[1] * mm)
        if isinstance(s, Line):
            msp.add_line(a, b, dxfattribs={"layer": layer})
            continue
        c = (s.center[0] * mm, s.center[1] * mm)
        ccw = (a[0] - c[0]) * (b[1] - c[1]) - (a[1] - c[1]) * (b[0] - c[0]) > 0
        p, q = (a, b) if ccw else (b, a)
        msp.add_arc(c, math.dist(a, c), math.degrees(math.atan2(p[1] - c[1], p[0] - c[0])),
                    math.degrees(math.atan2(q[1] - c[1], q[0] - c[0])), dxfattribs={"layer": layer})


def write_dxf(p: RadialSRMParams) -> bytes:
    """R2010 DXF in mm with layers STATOR, ROTOR and COILS; the iron of `p.iron` or the parametric iron."""
    from .radial import _coil_sides  # radial imports this module

    iron = p.iron or parametric_iron(p)
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for name in ("STATOR", "ROTOR", "COILS"):
        doc.layers.add(name)
    msp = doc.modelspace()
    stator = (iron.stator_outer, iron.stator_bore, *iron.stator_holes)
    rotor = (iron.rotor_outer, iron.rotor_bore, *iron.rotor_holes)
    for layer, loops in (("STATOR", stator), ("ROTOR", rotor)):
        for loop in loops:
            if _is_circle(loop):
                msp.add_circle((0, 0), math.hypot(*loop[0].start) * 1e3, dxfattribs={"layer": layer})
            else:
                _add_segments(msp, to_segments(loop), layer)
    for side in _coil_sides(p):
        _add_segments(msp, side.boundary, "COILS")
    out = io.StringIO()
    doc.write(out)
    return out.getvalue().encode("utf-8")


# --- read --------------------------------------------------------------------------------------

def _arcs(c, r, a0: float, sweep: float, p0, p1) -> list[Segment]:
    """Minor arcs from p0 to p1 around c, starting at angle a0 and turning by the signed sweep."""
    n = 1 if abs(sweep) < math.pi - 1e-9 else math.ceil(abs(sweep) / (math.pi / 2) - 1e-9)
    pts = [p0] + [(c[0] + r * math.cos(a0 + sweep * k / n), c[1] + r * math.sin(a0 + sweep * k / n))
                  for k in range(1, n)] + [p1]
    return [Arc(pts[k], pts[k + 1], c) for k in range(n)]


def _polyline(pts, bulges, closed: bool, k: float) -> list[Segment]:
    out: list[Segment] = []
    m = len(pts)
    for i in range(m if closed else m - 1):
        p0, p1 = pts[i], pts[(i + 1) % m]
        a, b = (p0[0] * k, p0[1] * k), (p1[0] * k, p1[1] * k)
        if bulges[i]:
            c, _, _, r = bulge_to_arc((p0[0], p0[1]), (p1[0], p1[1]), bulges[i])
            c = (c.x * k, c.y * k)
            out += _arcs(c, r * k, math.atan2(a[1] - c[1], a[0] - c[0]),
                         math.copysign(4 * math.atan(abs(bulges[i])), bulges[i]), a, b)
        else:
            out.append(Line(a, b))
    return out


def _first_point(e):
    """A point of the entity as stored (in its own coordinate system), or None."""
    for name in ("start", "center", "insert", "location"):
        if e.dxf.hasattr(name):
            return tuple(e.dxf.get(name))
    t = e.dxftype()
    if t == "LWPOLYLINE" and len(e):
        x, y = e.get_points("xy")[0]
        return (x, y, e.dxf.get("elevation", 0.0))
    if t == "POLYLINE" and len(e.vertices):
        return tuple(e.vertices[0].dxf.location)
    if t == "SPLINE" and len(e.control_points):
        return tuple(e.control_points[0])
    return None


def _where(e, k: float) -> str:
    """" near (x, y) mm" in drawing (WCS) coordinates, or "" for an entity without any point."""
    v = _first_point(e)
    if v is None:
        return ""
    ext = e.dxf.get("extrusion", (0.0, 0.0, 1.0))
    if e.dxftype() != "ELLIPSE" and ext[2] < 0 and abs(ext[0]) < 1e-9 and abs(ext[1]) < 1e-9:
        v = tuple(e.ocs().to_wcs(v))
    return f" near {_at((v[0] * k, v[1] * k))}"


def _flatten(entities):
    for e in entities:
        if e.dxftype() == "INSERT":
            yield from _flatten(e.virtual_entities())
        else:
            yield e


class _Degenerate(Exception):
    """An entity without extent."""


class _Tilted(Exception):
    """An entity whose plane is not parallel to the drawing plane."""


def _ocs(e):
    """(to_wcs function, mirrored) for an entity drawn in its own coordinate system."""
    ext = e.dxf.get("extrusion", (0.0, 0.0, 1.0))
    if abs(ext[0]) > 1e-9 or abs(ext[1]) > 1e-9 or abs(abs(ext[2]) - 1) > 1e-9:
        raise _Tilted
    if ext[2] > 0:
        return (lambda v: (v[0], v[1], v[2])), False
    ocs = e.ocs()
    return (lambda v: tuple(ocs.to_wcs(v))), True


def _ellipse(e, k: float):
    """(segments, WCS z values) of a full or partial ELLIPSE. Its centre and major axis are stored in WCS; the
    extrusion only sets the direction in which the parameter runs. A circular one becomes minor arcs, any other
    is flattened to lines within the chord error."""
    ext = e.dxf.extrusion
    if abs(ext[0]) > 1e-9 or abs(ext[1]) > 1e-9 or abs(abs(ext[2]) - 1) > 1e-9:
        raise _Tilted
    c, major = e.dxf.center, e.dxf.major_axis
    t0, t1 = e.dxf.start_param, e.dxf.end_param
    sweep = (t1 - t0) % (2 * math.pi)
    if sweep < 1e-9 and abs(t1 - t0) > 1:
        sweep = 2 * math.pi
    if sweep < 1e-9:
        raise _Degenerate
    if math.hypot(major.x, major.y) < TOL / k:
        raise _Degenerate
    if abs(abs(e.dxf.ratio) - 1) < 1e-9:
        sign = (1.0 if ext[2] > 0 else -1.0) * (1.0 if e.dxf.ratio > 0 else -1.0)
        r = math.hypot(major.x, major.y)
        a0 = math.atan2(major.y, major.x) + sign * t0

        def pt(a):
            return ((c.x + r * math.cos(a)) * k, (c.y + r * math.sin(a)) * k)

        p0 = pt(a0)
        return _arcs((c.x * k, c.y * k), r * k, a0, sign * sweep, p0, p0 if sweep > 2 * math.pi - 1e-9
                     else pt(a0 + sign * sweep)), [c.z]
    pts = list(e.flattening(_SPLINE_CHORD / k))
    return [Line((a.x * k, a.y * k), (b.x * k, b.y * k)) for a, b in zip(pts, pts[1:])], [q.z for q in pts]


def _entity(e, k: float):
    """(segments, WCS z values) of a supported entity, or None when it is not supported."""
    t = e.dxftype()
    if t == "LINE":
        s, f = e.dxf.start, e.dxf.end
        return [Line((s.x * k, s.y * k), (f.x * k, f.y * k))], [s.z, f.z]
    if t in ("ARC", "CIRCLE"):
        wcs, mirrored = _ocs(e)
        c, r = e.dxf.center, e.dxf.radius
        a0 = math.radians(e.dxf.start_angle) if t == "ARC" else 0.0
        sweep = math.radians((e.dxf.end_angle - e.dxf.start_angle) % 360) if t == "ARC" else 2 * math.pi

        def pt(a):
            w = wcs((c.x + r * math.cos(a), c.y + r * math.sin(a), c.z))
            return (w[0] * k, w[1] * k)

        w0 = wcs((c.x, c.y, c.z))
        ctr = (w0[0] * k, w0[1] * k)
        p0 = pt(a0)
        segs = _arcs(ctr, r * k, math.atan2(p0[1] - ctr[1], p0[0] - ctr[0]), -sweep if mirrored else sweep, p0,
                     p0 if t == "CIRCLE" else pt(a0 + sweep))
        return segs, [w0[2]]
    if t == "LWPOLYLINE" or (t == "POLYLINE" and e.is_2d_polyline):
        wcs, mirrored = _ocs(e)
        if t == "LWPOLYLINE":
            raw = [(x, y, b) for x, y, b in e.get_points("xyb")]
            z = e.dxf.get("elevation", 0.0)
            z = getattr(z, "z", z)
            closed = e.closed
        else:
            raw = [(v.dxf.location.x, v.dxf.location.y, v.dxf.get("bulge", 0.0)) for v in e.vertices]
            z = e.dxf.location.z if e.dxf.hasattr("location") else 0.0
            closed = e.is_closed
        w = [wcs((x, y, z)) for x, y, _ in raw]
        bulges = [-b if mirrored else b for _, _, b in raw]
        return _polyline(w, bulges, closed, k), [q[2] for q in w]
    if t == "POLYLINE" and e.is_3d_polyline:
        v = [(x.dxf.location, x.dxf.get("bulge", 0.0)) for x in e.vertices]
        return _polyline([q for q, _ in v], [b for _, b in v], e.is_closed, k), [q.z for q, _ in v]
    if t == "ELLIPSE":
        return _ellipse(e, k)
    if t == "SPLINE":
        pts = list(e.flattening(_SPLINE_CHORD / k))
        return [Line((a.x * k, a.y * k), (b.x * k, b.y * k)) for a, b in zip(pts, pts[1:])], [q.z for q in pts]
    return None


def _arc_span(x: Arc) -> tuple[float, float]:
    """(start angle, sweep) of the arc taken counter-clockwise."""
    cx, cy = x.center
    a0 = math.atan2(x.start[1] - cy, x.start[0] - cx)
    a1 = math.atan2(x.end[1] - cy, x.end[0] - cx)
    ccw = (x.start[0] - cx) * (x.end[1] - cy) - (x.start[1] - cy) * (x.end[0] - cx) > 0
    return (a0, (a1 - a0) % (2 * math.pi)) if ccw else (a1, (a0 - a1) % (2 * math.pi))


def _overlaps(segs: list[Segment]) -> list[ValidationIssue]:
    def issue(mid):
        return _issue("overlap", f"Duplicate or overlapping edges near {_at(mid)}. Delete the repeated edge.")

    out: list[ValidationIssue] = []
    lines = [s for s in segs if isinstance(s, Line) and math.dist(s.start, s.end) > TOL]
    if len(lines) > 1:
        a = np.array([s.start for s in lines])
        d = np.array([s.end for s in lines]) - a
        ln = np.hypot(d[:, 0], d[:, 1])
        u = d / ln[:, None]
        for i in range(len(lines) - 1):
            j = np.arange(i + 1, len(lines))
            rel_a, rel_b = a[j] - a[i], a[j] + d[j] - a[i]
            ta, tb = rel_a @ u[i], rel_b @ u[i]
            off_a = np.abs(u[i, 0] * rel_a[:, 1] - u[i, 1] * rel_a[:, 0])
            off_b = np.abs(u[i, 0] * rel_b[:, 1] - u[i, 1] * rel_b[:, 0])
            lo, hi = np.maximum(np.minimum(ta, tb), 0), np.minimum(np.maximum(ta, tb), ln[i])
            for k in np.nonzero((off_a < TOL) & (off_b < TOL) & (hi - lo > TOL))[0]:
                out.append(issue(a[i] + u[i] * (lo[k] + hi[k]) / 2))
    arcs = [s for s in segs if isinstance(s, Arc)]
    for i, s in enumerate(arcs):
        r = math.dist(s.start, s.center)
        for t in arcs[i + 1:]:
            if math.dist(s.center, t.center) > TOL or abs(r - math.dist(t.start, t.center)) > TOL:
                continue
            (lo_s, w_s), (lo_t, w_t) = _arc_span(s), _arc_span(t)
            best = (0.0, 0.0)
            for d in ((lo_t - lo_s) % (2 * math.pi), (lo_t - lo_s) % (2 * math.pi) - 2 * math.pi):
                ov = min(w_s, d + w_t) - max(0.0, d)
                if ov > best[0]:
                    best = (ov, lo_s + max(0.0, d) + ov / 2)
            if best[0] * r > TOL:
                out.append(issue((s.center[0] + r * math.cos(best[1]), s.center[1] + r * math.sin(best[1]))))
    return out


def _flip(s: Segment) -> Segment:
    return Line(s.end, s.start) if isinstance(s, Line) else Arc(s.end, s.start, s.center)


def _join(chain: list[Segment]) -> tuple[Segment, ...]:
    """Make consecutive segments share their vertex exactly. An arc end is rebuilt from an angle and one radius,
    so it can sit a fraction of a micrometre off the true vertex; a line end is exact and wins, otherwise the
    midpoint is used."""
    n = len(chain)
    joint = []
    for i in range(n):
        a, b = chain[i], chain[(i + 1) % n]
        if isinstance(a, Line):
            joint.append(a.end)
        elif isinstance(b, Line):
            joint.append(b.start)
        else:
            joint.append(((a.end[0] + b.start[0]) / 2, (a.end[1] + b.start[1]) / 2))
    return tuple(Line(joint[i - 1], joint[i]) if isinstance(s, Line) else Arc(joint[i - 1], joint[i], s.center)
                 for i, s in enumerate(chain))


def _chains(segs: list[Segment]) -> tuple[list[tuple[Segment, ...]], list[ValidationIssue]]:
    """Join the segments end to end: closed chains are loops, the others are reported as open."""
    if not segs:
        return [], []
    ends = np.array([q for s in segs for q in (s.start, s.end)])
    tree = cKDTree(ends)
    used = [False] * len(segs)
    loops: list[tuple[Segment, ...]] = []
    issues: list[ValidationIssue] = []
    for first in range(len(segs)):
        if used[first]:
            continue
        used[first] = True
        chain = [segs[first]]
        while len(chain) == 1 or math.dist(chain[-1].end, chain[0].start) > TOL:
            cand = [c for c in tree.query_ball_point(chain[-1].end, TOL) if not used[c // 2]]
            if not cand:
                break
            c = min(cand, key=lambda c: math.dist(ends[c], chain[-1].end))
            used[c // 2] = True
            chain.append(segs[c // 2] if c % 2 == 0 else _flip(segs[c // 2]))
            if len(chain) == 2 and math.dist(chain[0].end, chain[0].start) <= TOL:
                break
        if math.dist(chain[-1].end, chain[0].start) <= TOL and (len(chain) > 1 or isinstance(chain[0], Arc)):
            loops.append(_join(chain))
        else:
            issues.append(_issue("open_loop", f"A contour is open near {_at(chain[-1].end)} (its other end is at "
                                 f"{_at(chain[0].start)}). Close the loop so its ends meet within 1 µm."))
    return loops, issues


def _geometry_before(doc) -> list[str]:
    return [f"{e.dxftype()} #{e.dxf.handle}" for e in doc.modelspace() if e.dxftype() in _GEOMETRY]


def _lost_geometry(doc, before: list[str], fixes=()) -> list[str]:
    """Geometry entities ("TYPE #handle") listed in `before` that the audit removed from the model space, plus
    the removal messages in `fixes`. Cosmetic repairs (undefined linetypes, colour indices, unused knots) lose
    nothing."""
    present = {f"{e.dxftype()} #{e.dxf.handle}" for e in doc.modelspace()}
    return [x for x in before if x not in present] + list(fixes)


def read_loops(data: bytes) -> tuple[list[tuple[Segment, ...]], list[ValidationIssue]]:
    """Closed loops (metres) of the geometry in a DXF and the file-level problems found."""
    try:
        if data.startswith(_BINARY_SENTINEL):
            doc = Drawing.load(binary_tags_loader(data))
            before, removed = _geometry_before(doc), []
            auditor = doc.audit()
        else:
            tool = recover.Recover.run(io.BytesIO(data))
            before = [f"{t.dxftype()} #{t.get_handle()}" for t in tool.section_dict.get("ENTITIES", [])
                      if t.dxftype() in _GEOMETRY]
            removed = [m for c, m in tool.fixes if c in (AuditError.REMOVED_INVALID_GRAPHIC_ENTITY,
                                                         AuditError.REMOVED_ENTITY_WITH_INVALID_OWNER_HANDLE)]
            doc, auditor = recover.read(io.BytesIO(data))
    except Exception as exc:  # ezdxf raises several unrelated types on a broken file
        return [], [_issue("dxf_file", f"The file is not a readable DXF ({exc}).")]
    if auditor.errors:
        return [], [_issue("dxf_file", f"The file is damaged and cannot be repaired ({auditor.errors[0].message}).")]
    lost = _lost_geometry(doc, before, removed)
    if lost:
        return [], [_issue("dxf_file", f"The reader removed invalid geometry: {lost[0]} ({len(lost)} in all). "
                           "Fix or delete it in the CAD program and export again.")]
    code = doc.header.get("$INSUNITS", 0)
    if code not in _UNITS:
        return [], [_issue("dxf_units", f"The drawing units ($INSUNITS = {code}) are not supported. Export in mm, "
                           "inch or m, or set the units to none (read as mm).")]
    k = _UNITS[code]
    segs: list[Segment] = []
    issues: list[ValidationIssue] = []
    z0: float | None = None
    for e in _flatten(doc.modelspace()):
        t = e.dxftype()
        if t in _IGNORED:
            continue
        try:
            got = _entity(e, k)
        except _Degenerate:
            issues.append(_issue("dxf_entity", f"A degenerate {t}{_where(e, k)} (zero size or zero sweep). "
                                 "Delete it."))
            continue
        except _Tilted:
            return [], [_issue("dxf_flat", f"A {t}{_where(e, k)} lies in a tilted plane. Draw everything in the "
                               "XY plane.")]
        if got is None:
            issues.append(_issue("dxf_entity", f"Unsupported DXF entity {t}{_where(e, k)}. Convert it to lines, "
                                 "arcs or a spline."))
            continue
        for z in got[1]:
            z0 = z if z0 is None else z0
            if abs(z - z0) > 1e-9:
                return [], [_issue("dxf_flat", f"The drawing is not flat: a {t}{_where(e, k)} is at z = {z:g} while "
                                   f"other entities are at z = {z0:g}. Project everything to one plane.")]
        segs += [s for s in got[0] if math.dist(s.start, s.end) > TOL or isinstance(s, Arc)]
    issues += _overlaps(segs)
    loops, open_issues = _chains(segs)
    return loops, issues + open_issues


def import_dxf(data: bytes, p: RadialSRMParams) -> tuple[ImportedIron | None, list[ValidationIssue]]:
    """`ImportedIron` from a DXF against the machine `p`, and every problem found (iron is None on an error)."""
    loops, issues = read_loops(data)
    if any(i.severity == "error" for i in issues):
        return None, issues
    iron, found = iron_from_loops(loops, p)
    issues += found
    if iron is not None:
        old = sum(iron_areas(p.iron or parametric_iron(p)))
        new = sum(iron_areas(iron))
        if abs(new - old) > _AREA_CHANGE * old:
            issues.append(ValidationIssue("iron", "iron_area", f"The iron area is {new * 1e4:.1f} cm², "
                          f"{abs(new - old) / old * 100:.0f} % different from the current {old * 1e4:.1f} cm². "
                          "Check that the file and its units are the right ones.", "warning"))
    return iron, issues
