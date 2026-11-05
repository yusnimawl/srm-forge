"""A radial SRM (a parametric srmcore design) as a 3D model: the outline's 2D section, swept in z. The half
z >= 0 has a mirror plane at z = 0 (full mode: coils are U-shaped with end turns above the stack), or a slab
of the stack (slab mode: coil sides run straight, ends at the stator outer surface)."""
from __future__ import annotations

import math

import ngsolve as ng
from netgen.occ import ArcOfCircle, Face, OCCGeometry, Pnt, Glue, Segment, WorkPlane, Wire

from srmcore.maps.end_winding import coil_geometry
from srmcore.materials.laws import VACUUM, library_law
from srmcore.mesh.settings import resolve_mesh_settings
from srmcore.model.design import Design
from srmcore.topology.primitives import Arc, Line, map_segment, rotate
from srmcore.topology.radial import parametric_outline

from .solve import Model3D
from .swept import graded_layers, swept_mesh

EPS = 1e-6


def _phase_poles(design: Design, phase: str):
    """[(pole, plus_side, minus_side)] of the excited phase, in pole order: the coil of list index k is `coil_<k>`."""
    index = ord(phase) - ord("A")
    sides = [s for s in parametric_outline(design.machine).coil_sides if s.phase == index]
    if not sides:
        raise ValueError(f"phase {phase!r} does not exist")
    poles = sorted({s.pole for s in sides})
    return [(pole, *(next(s for s in sides if s.pole == pole and s.sign == sign) for sign in (1, -1))) for pole in poles]


def ampere_turns(design: Design, current: float, slab: bool) -> dict[str, float]:
    """Coil ampere-turns for the phase `current`: every pole coil carries turns_per_pole x current, entering at
    `<coil>_in`; a slab's return side (`b`, the '-' coil side) carries the negative."""
    n = design.machine.turns_per_pole * current
    count = design.machine.n_stator_poles // design.machine.n_phases
    if slab:
        return {f"coil_{k}{s}": sign * n for k in range(count) for s, sign in (("a", 1.0), ("b", -1.0))}
    return {f"coil_{k}": n for k in range(count)}


def _arc_mid(seg: Arc):
    cx, cy = seg.center
    a0, a1 = (math.atan2(q[1] - cy, q[0] - cx) for q in (seg.start, seg.end))
    r = math.hypot(seg.start[0] - cx, seg.start[1] - cy)
    mid = a0 + ((a1 - a0 + math.pi) % (2 * math.pi) - math.pi) / 2      # minor arc
    return cx + r * math.cos(mid), cy + r * math.sin(mid)


def _face(segments):
    """The face bounded by a closed chain of segments, always counter-clockwise (faces with opposite
    orientations are not merged by Glue along their shared edges)."""
    ring = [q for seg in segments for q in ((seg.start,) if isinstance(seg, Line) else (seg.start, _arc_mid(seg)))]
    if sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1])) < 0:
        segments = [Line(s.end, s.start) if isinstance(s, Line) else Arc(s.end, s.start, s.center) for s in reversed(segments)]
    edges = [Segment(Pnt(*s.start, 0), Pnt(*s.end, 0)) if isinstance(s, Line)
             else ArcOfCircle(Pnt(*s.start, 0), Pnt(*_arc_mid(s), 0), Pnt(*s.end, 0)) for s in segments]
    return Face(Wire(edges))


def _footprint(plus, minus):
    """The region over a pole between its two coil sides, radially over the coils' extent: bounded by the
    inner and outer coil radii and the slot centrelines."""
    (_, _, c1, d1) = (plus.boundary[0].start, plus.boundary[0].end, plus.boundary[2].start, plus.boundary[2].end)
    c2, d2 = minus.boundary[2].start, minus.boundary[2].end
    origin = (0.0, 0.0)
    return _face([Arc(d1, d2, origin), Line(d2, c2), Arc(c2, c1, origin), Line(c1, d1)])


def _section_faces(design: Design, angle: float, phase: str, slab: bool, h_gap: float, air_radius_factor: float):
    p = design.machine
    out = parametric_outline(p)
    disk = lambda r: WorkPlane().Circle(r).Face()                                           # noqa: E731
    turn = lambda s: map_segment(s, lambda q: rotate(q, angle))                             # noqa: E731
    r_out = out.stator_outer_radius
    faces = {"stator": disk(r_out) - _face(out.stator_inner_boundary),
             "rotor": _face(tuple(turn(s) for s in out.rotor_outer_boundary)) - disk(out.shaft_radius),
             "shaft": disk(out.shaft_radius),
             "gap_shell": disk(out.band_outer_radius) - disk(out.band_inner_radius)}
    footprints = []
    for k, (_, plus, minus) in enumerate(_phase_poles(design, phase)):
        faces[f"coil_{k}a"], faces[f"coil_{k}b"] = _face(plus.boundary), _face(minus.boundary)
        footprints.append(_footprint(plus, minus))
    r_air = r_out if slab else air_radius_factor * r_out
    air = disk(r_air)
    for f in faces.values():
        air = air - f
    faces["air"] = air
    if not slab:
        for k, fp in enumerate(footprints):
            for name in ("stator", "air"):
                part = faces[name] * fp
                if any(True for _ in part.faces):
                    faces[f"{name}@fp{k}"] = part
                    faces[name] = faces[name] - fp
    for name, f in faces.items():
        f.name = name
    on_circle = lambda e, r: all(abs(math.hypot(q.x, q.y) - r) < EPS for q in (e.start, e.end))   # noqa: E731
    gap_radii = (out.bore_radius, out.rotor_outer_radius, out.band_inner_radius, out.band_outer_radius)
    for name, f in faces.items():
        for e in f.edges:
            if name in ("air", "stator") and on_circle(e, r_out if slab else r_air) and (slab == (name == "stator")):
                e.name = "outer"
            if any(on_circle(e, r) for r in gap_radii):
                e.maxh = h_gap
    faces["gap_shell"].maxh = h_gap
    return faces


def radial_model(design: Design, angle: float, phase: str = "A", slab: bool = False,
                 h_gap: float | None = None, h_iron: float | None = None, h_end: float | None = None,
                 h_mid: float | None = None, h_far: float | None = None, end_clearance: float | None = None,
                 air_radius_factor: float = 1.5, air_end_factor: float = 1.0) -> Model3D:
    """The 3D model of a parametric radial SRM with the rotor turned `angle` (rad, counter-clockwise; phase A
    is aligned at 0) and only `phase` excited. Swept prism mesh: element size h_gap on the gap arcs and h_iron
    elsewhere in the section; layers of h_end at the stack end growing to h_mid. Defaults: the design's resolved
    mesh sizes, h_end = h_gap, h_mid = 4 h_end. Materials: stator, rotor, shaft (library laws), air, gap_shell
    (the band annulus) and the phase's coils; circles and arcs are polygons."""
    p = design.machine
    if p.iron is not None:
        raise NotImplementedError("imported iron is not supported by the 3D reference model")
    if slab and design.mesh.outer_air_thickness > 0:
        raise NotImplementedError("a slab puts its boundary at the stator outer radius: no outer air ring")
    resolved = resolve_mesh_settings(p, design.mesh)
    h_gap = resolved.gap_size if h_gap is None else h_gap
    h_iron = resolved.region_sizes["stator_iron"] if h_iron is None else h_iron
    h_end = h_gap if h_end is None else h_end
    h_mid = 4 * h_end if h_mid is None else h_mid
    clearance = p.slot_liner_thickness if end_clearance is None else end_clearance
    out = parametric_outline(p)
    build = coil_geometry(p).build
    h = p.stack_length / 2
    bridge_lo = h + clearance
    top = bridge_lo + build

    section = _section_faces(design, angle, phase, slab, h_gap, air_radius_factor)
    mesh2d = OCCGeometry(Glue(list(section.values())), dim=2).GenerateMesh(maxh=h_iron)
    if slab:
        layers = graded_layers(h, h, h_end, h_mid)
    else:
        layers = graded_layers(h, top + air_end_factor * out.stator_outer_radius, h_end, h_mid,
                               breaks=(bridge_lo, top), h_far=h_far)

    def material(region: str, k: int) -> str | None:
        zc = (layers.z[k] + layers.z[k + 1]) / 2
        base, _, fp = region.partition("@")
        if base.startswith("coil_"):
            return region if slab else (f"coil_{region[5:-1]}" if zc < top else "air")
        if fp:
            return f"coil_{fp[2:]}" if bridge_lo < zc < top else (base if zc < h else "air")
        return base if zc < h or base in ("gap_shell", "air") else "air"

    def faces(edge: str, k: int) -> str | None:
        return edge if edge == "outer" else None

    def bottom(region: str) -> str:
        if region.startswith("coil_"):
            return f"{region}_in" if slab else f"coil_{region[5:-1]}_{'in' if region[-1] == 'a' else 'out'}"
        return "sym_z"

    def top_name(region: str) -> str:
        if slab:
            return f"{region}_out" if region.startswith("coil_") else "end_z"
        return "outer"

    mesh = swept_mesh(mesh2d, layers, material, faces, bottom, top_name)
    materials = list(dict.fromkeys(mesh.GetMaterials()))
    role = {"stator": p.materials.stator, "rotor": p.materials.rotor, "shaft": p.materials.shaft}
    laws = {m: (library_law(role[m]) if m in role else VACUUM) for m in materials}
    return Model3D(mesh, laws, tuple(sorted((m for m in materials if m.startswith("coil_")), key=lambda m: (len(m), m))),
                   dirichlet="sym_z|end_z|outer" if slab else "sym_z|outer")
