"""TEAM Problem 24 as a 3D model (the half z >= 0 with a mirror plane at z = 0, or a slab), built in
netgen.occ from the same cross-section as tests/team24_fixture.py."""
from __future__ import annotations

import math
from dataclasses import dataclass

import ngsolve as ng
from netgen.occ import Axis, Box, Cylinder, Glue, OCCGeometry, Pnt, WorkPlane, X, Y, Z

import team24_fixture as fx
from srmcore.materials.laws import VACUUM

from .post import face_flux
from .solve import Model3D, Solution3D
from .swept import graded_layers, swept_mesh

HALF = fx.DEPTH / 2
EPS = 1e-6                      # OCC bounding boxes are padded by 1e-7


@dataclass(frozen=True)
class Team24Params:
    r_stator_out: float = fx.R_STATOR_OUT
    r_yoke_in: float = fx.R_YOKE_IN
    r_stator_bore: float = fx.R_STATOR_BORE
    pole_width_stator: float = fx.POLE_WIDTH_STATOR
    r_rotor_tip: float = fx.R_ROTOR_TIP
    r_shaft: float = fx.R_SHAFT
    r_hub: float = fx.R_HUB
    pole_width_rotor: float = fx.POLE_WIDTH_ROTOR
    depth: float = fx.DEPTH
    rotor_angle: float = fx.ROTOR_ANGLE
    turns: int = fx.TURNS
    coil_inner_half_width: float = fx.COIL_INNER_HALF_WIDTH
    coil_build: float = fx.COIL_BUILD
    coil_thickness: float = fx.COIL_THICKNESS
    coil_mid_y: float = fx.COIL_MID_Y
    search_from_corner: float = fx.SEARCH_COIL_FROM_CORNER
    js: float = fx.ASSUMED_JS
    fillet: float = 0.0              # m; > 0 rounds the pole-root corners (stator pole to yoke, rotor pole to hub)
    end_clearance: float = 2e-3      # axial gap between the stack end face and the coil bridge
    air_radius_factor: float = 1.5   # outer air cylinder radius over r_stator_out
    air_end_factor: float = 1.0      # air beyond the coil bridge, in units of r_stator_out
    slab: bool = False
    maxh: float = 4e-3
    gap_maxh: float = 0.5e-3


def _faces_where(shape, pred):
    return [f for f in shape.faces if pred(f.bounding_box)]


def _name(shape, name, pred):
    for f in _faces_where(shape, pred):
        f.name = name


def _bottom(bb):
    return bb[1].z < EPS


def _fillet_roots(solid, points, r, h):
    """Round the z-parallel edges of `solid` that start at one of the xy `points`."""
    edges = [e for e in solid.edges
             if abs(e.end.z - e.start.z) > 0.5 * h
             and any(math.hypot(e.start.x - px, e.start.y - py) < 1e-6 for px, py in points)]
    assert len({(round(e.center.x, 7), round(e.center.y, 7)) for e in edges}) == 4, "expected 4 pole-root edges"
    return solid.MakeFillet(edges, r)


def _iron(p: Team24Params):
    h = p.depth / 2
    w = p.pole_width_stator / 2
    cavity = Cylinder(Pnt(0, 0, 0), Z, p.r_yoke_in, h) - Box(Pnt(-w, -p.r_stator_out, 0), Pnt(w, p.r_stator_out, h))
    stator = Cylinder(Pnt(0, 0, 0), Z, p.r_stator_out, h) - cavity - Cylinder(Pnt(0, 0, 0), Z, p.r_stator_bore, h)
    wr = p.pole_width_rotor / 2
    bars = Box(Pnt(-wr, -p.r_stator_out / 2, 0), Pnt(wr, p.r_stator_out / 2, h)) * Cylinder(Pnt(0, 0, 0), Z, p.r_rotor_tip, h)
    rotor = (Cylinder(Pnt(0, 0, 0), Z, p.r_hub, h) + bars) - Cylinder(Pnt(0, 0, 0), Z, p.r_shaft, h)
    if p.fillet > 0:
        ys = math.sqrt(p.r_yoke_in ** 2 - w ** 2)
        stator = _fillet_roots(stator, [(sx * w, sy * ys) for sx in (-1, 1) for sy in (-1, 1)], p.fillet, h)
        yr = math.sqrt(p.r_hub ** 2 - wr ** 2)
        rotor = _fillet_roots(rotor, [(sx * wr, sy * yr) for sx in (-1, 1) for sy in (-1, 1)], p.fillet, h)
    # search-coil chord on the pole that points to +y before the rotor turns, cut so that its face exists
    chord_y = math.sqrt(p.r_rotor_tip ** 2 - wr ** 2) - p.search_from_corner
    below = rotor * Box(Pnt(-p.r_stator_out, -p.r_stator_out, 0), Pnt(p.r_stator_out, chord_y, h))
    above = rotor - below
    _name(below, "search", lambda bb: abs(bb[0].y - chord_y) < EPS and abs(bb[1].y - chord_y) < EPS)
    rotated = [s.Rotate(Axis(Pnt(0, 0, 0), Z), math.degrees(p.rotor_angle)) for s in (below, above)]
    for s in rotated:
        s.mat("steel")
    stator.mat("steel")
    return stator, rotated


def _coils(p: Team24Params):
    h = p.depth / 2
    x0, b, t = p.coil_inner_half_width, p.coil_build, p.coil_thickness
    top = h if p.slab else h + p.end_clearance + t
    out = []
    for k, sign in enumerate((1, -1)):
        lo, hi = sorted((sign * (p.coil_mid_y - t / 2), sign * (p.coil_mid_y + t / 2)))
        side_a = Box(Pnt(x0, lo, 0), Pnt(x0 + b, hi, top))             # +z side, like the fixture's right side
        side_b = Box(Pnt(-x0 - b, lo, 0), Pnt(-x0, hi, top))           # -z side
        if p.slab:
            pieces = {f"coil_{k}a": side_a, f"coil_{k}b": side_b}
        else:
            bridge = Box(Pnt(-x0 - b, lo, h + p.end_clearance), Pnt(x0 + b, hi, top))
            pieces = {f"coil_{k}": side_a + side_b + bridge}
        for name, solid in pieces.items():
            solid.mat(name)
            if p.slab:
                _name(solid, f"{name}_in", _bottom)
                _name(solid, f"{name}_out", lambda bb, top=top: bb[0].z > top - EPS)
            else:
                _name(solid, f"{name}_in", lambda bb: _bottom(bb) and bb[0].x > 0)
                _name(solid, f"{name}_out", lambda bb: _bottom(bb) and bb[1].x < 0)
            out.append(solid)
    return out, top


def ampere_turns(params: Team24Params, current: float) -> dict[str, float]:
    """Coil ampere-turns for a series-circuit `current`: a slab's return side (`b`) carries the negative."""
    n = params.turns * current
    if params.slab:
        return {f"coil_{k}{s}": sign * n for k in (0, 1) for s, sign in (("a", 1.0), ("b", -1.0))}
    return {"coil_0": n, "coil_1": n}


def rotor_pole_flux(model: Model3D, sol: Solution3D) -> float:
    """Full-machine flux (Wb) into the rotor pole through the `search` chord: minus the radially outward `face_flux`,
    so it is positive for the TEAM 24 excitation, like team24_fixture.rotor_pole_flux."""
    return -face_flux(model, sol, "search")


def team24_model(params: Team24Params = Team24Params()) -> Model3D:
    p = params
    if not p.r_rotor_tip < fx.BAND_INNER < fx.BAND_OUTER < p.r_stator_bore:
        raise ValueError(f"gap_shell [{fx.BAND_INNER}, {fx.BAND_OUTER}] m must lie between r_rotor_tip "
                         f"{p.r_rotor_tip} and r_stator_bore {p.r_stator_bore}")
    stator, rotor = _iron(p)
    coils, top = _coils(p)
    shaft = Cylinder(Pnt(0, 0, 0), Z, p.r_shaft, p.depth / 2)
    shaft.mat("shaft")
    z_air = top if p.slab else top + p.air_end_factor * p.r_stator_out
    # the full model's shell runs to the top of the end air, where tangential A = 0 (outer face), so the
    # end-cap B_theta B_z term of the Arkkio torque vanishes
    z_shell = p.depth / 2 if p.slab else z_air
    if not p.slab and p.coil_mid_y - p.coil_thickness / 2 <= fx.BAND_OUTER:
        raise ValueError("a coil overlaps the gap_shell")
    shell = (Cylinder(Pnt(0, 0, 0), Z, fx.BAND_OUTER, z_shell) - Cylinder(Pnt(0, 0, 0), Z, fx.BAND_INNER, z_shell))
    shell.mat("gap_shell")
    shell.maxh = p.gap_maxh
    if not p.slab:
        _name(shell, "outer", lambda bb: bb[0].z > z_air - EPS)
    # a slab ends at the stator outer surface (A = 0 there, as in the 2D fixture) and has no outer air
    r_air = p.r_stator_out if p.slab else p.air_radius_factor * p.r_stator_out
    air = Cylinder(Pnt(0, 0, 0), Z, r_air, z_air)
    for s in (stator, *rotor, shaft, shell, *coils):
        air = air - s
    air.mat("air")
    _name(air, "outer", lambda bb: bb[0].z > z_air - EPS or bb[1].x > r_air - EPS)
    if p.slab:
        for s in (air, stator, *rotor, shaft, shell):
            _name(s, "end_z", lambda bb: bb[0].z > z_air - EPS)
        _name(stator, "outer", lambda bb: bb[1].x > r_air - EPS and bb[0].z < EPS and bb[1].z > z_air - EPS)
    for s in (air, stator, *rotor, shaft, shell):
        _name(s, "sym_z", _bottom)
    mesh = ng.Mesh(OCCGeometry(Glue([air, stator, *rotor, shaft, shell, *coils])).GenerateMesh(maxh=p.maxh))
    mesh.Curve(2)
    materials = list(dict.fromkeys(mesh.GetMaterials()))
    law = fx.steel_law(p.js)
    laws = {m: (law if m == "steel" else VACUUM) for m in materials}
    return Model3D(mesh, laws, tuple(m for m in materials if m.startswith("coil_")),
                   dirichlet="sym_z|end_z|outer" if p.slab else "sym_z|outer")


def _section_faces(p: Team24Params, h_gap: float):
    """The TEAM 24 cross-section as named, non-overlapping OCC faces: {region: face}.

    Region names: stator, rotor_lo, rotor_hi (the rotor split at the search chord), shaft, gap_shell, air,
    coil_<k>a / coil_<k>b (the two coil sides) and, in a full model, `stator@fp<k>` / `air@fp<k>` (the parts of
    the stator and air under coil k's bridge footprint).
    """
    def disk(r):
        return WorkPlane().Circle(r).Face()

    def rect(x0, y0, x1, y1):
        return WorkPlane().MoveTo(x0, y0).Rectangle(x1 - x0, y1 - y0).Face()

    def round_roots(face, points):
        """Fillet the section vertices at the xy `points` (the pole roots, as `_fillet_roots` does in 3D)."""
        verts = {(round(v.p.x, 7), round(v.p.y, 7)): v for v in face.vertices
                 if any(math.hypot(v.p.x - px, v.p.y - py) < 1e-6 for px, py in points)}
        assert len(verts) == 4, f"expected 4 pole-root vertices, found {len(verts)}"
        return face.faces[0].MakeFillet(list(verts.values()), p.fillet)

    R, w, wr = p.r_stator_out, p.pole_width_stator / 2, p.pole_width_rotor / 2
    stator = disk(R) - (disk(p.r_yoke_in) - rect(-w, -R, w, R)) - disk(p.r_stator_bore)
    bars = rect(-wr, -R / 2, wr, R / 2) * disk(p.r_rotor_tip)
    rotor = (disk(p.r_hub) + bars) - disk(p.r_shaft)
    if p.fillet > 0:
        ys, yr = math.sqrt(p.r_yoke_in ** 2 - w ** 2), math.sqrt(p.r_hub ** 2 - wr ** 2)
        stator = round_roots(stator, [(sx * w, sy * ys) for sx in (-1, 1) for sy in (-1, 1)])
        rotor = round_roots(rotor, [(sx * wr, sy * yr) for sx in (-1, 1) for sy in (-1, 1)])
    chord_y = math.sqrt(p.r_rotor_tip ** 2 - wr ** 2) - p.search_from_corner
    below = rotor * rect(-R, -R, R, chord_y)
    above = rotor - below
    turn = math.degrees(p.rotor_angle)
    rotor_lo, rotor_hi = (s.Rotate(Axis(Pnt(0, 0, 0), Z), turn) for s in (below, above))
    cx, cy = -chord_y * math.sin(p.rotor_angle), chord_y * math.cos(p.rotor_angle)
    for s in (rotor_lo, rotor_hi):
        for e in s.edges:
            if math.hypot(e.center.x - cx, e.center.y - cy) < EPS and abs(e.end.x - e.start.x) + abs(e.end.y - e.start.y) > 2 * wr * 0.9:
                e.name = "search"
    faces = {"stator": stator, "rotor_lo": rotor_lo, "rotor_hi": rotor_hi, "shaft": disk(p.r_shaft),
             "gap_shell": disk(fx.BAND_OUTER) - disk(fx.BAND_INNER)}
    x0, b, t = p.coil_inner_half_width, p.coil_build, p.coil_thickness
    bridges = []
    for k, sign in enumerate((1, -1)):
        lo, hi = sorted((sign * (p.coil_mid_y - t / 2), sign * (p.coil_mid_y + t / 2)))
        faces[f"coil_{k}a"] = rect(x0, lo, x0 + b, hi)
        faces[f"coil_{k}b"] = rect(-x0 - b, lo, -x0, hi)
        bridges.append(rect(-x0 - b, lo, x0 + b, hi))
    r_air = R if p.slab else p.air_radius_factor * R
    air = disk(r_air)
    for f in faces.values():
        air = air - f
    faces["air"] = air
    if not p.slab:
        for k, bridge in enumerate(bridges):
            for name in ("stator", "air"):
                part = faces[name] * bridge
                if any(True for _ in part.faces):
                    faces[f"{name}@fp{k}"] = part
                    faces[name] = faces[name] - bridge
    for name, f in faces.items():
        f.name = name
    for name in ("air", "stator"):
        for e in faces[name].edges:
            if e.bounding_box[1].x > r_air - EPS or e.bounding_box[0].x < -r_air + EPS:
                e.name = "outer"
    h = p.depth / 2
    arcs = {p.r_stator_bore, p.r_rotor_tip, fx.BAND_INNER, fx.BAND_OUTER}
    for f in faces.values():
        for e in f.edges:
            if any(abs(math.hypot(e.start.x, e.start.y) - r) < EPS and abs(math.hypot(e.end.x, e.end.y) - r) < EPS
                   for r in arcs):
                e.maxh = h_gap
    faces["gap_shell"].maxh = h_gap
    return faces, r_air


def team24_swept_model(params: Team24Params, h_gap: float, h_iron: float, h_end: float, h_mid: float,
                       h_far: float | None = None) -> Model3D:
    """The same model as `team24_model` as a swept prism mesh: a 2D section (mesh size h_gap on the gap and the
    pole faces bordering it, h_iron elsewhere) stacked in layers of h_end at the stack end growing to h_mid.
    Layers above the coil bridge keep growing to h_far (default 4 h_mid). Circles are polygons (no curved elements)."""
    p = params
    if not p.r_rotor_tip < fx.BAND_INNER < fx.BAND_OUTER < p.r_stator_bore:
        raise ValueError(f"gap_shell [{fx.BAND_INNER}, {fx.BAND_OUTER}] m must lie between r_rotor_tip "
                         f"{p.r_rotor_tip} and r_stator_bore {p.r_stator_bore}")
    if not p.slab and p.coil_mid_y - p.coil_thickness / 2 <= fx.BAND_OUTER:
        raise ValueError("a coil overlaps the gap_shell")
    section, _ = _section_faces(p, h_gap)
    mesh2d = OCCGeometry(Glue(list(section.values())), dim=2).GenerateMesh(maxh=h_iron)
    h = p.depth / 2
    bridge_lo = h + p.end_clearance
    top = bridge_lo + p.coil_thickness
    if p.slab:
        layers = graded_layers(h, h, h_end, h_mid)
    else:
        layers = graded_layers(h, top + p.air_end_factor * p.r_stator_out, h_end, h_mid, breaks=(bridge_lo, top), h_far=h_far)

    def material(region: str, k: int) -> str | None:
        zc = (layers.z[k] + layers.z[k + 1]) / 2
        base, _, fp = region.partition("@")
        if region.startswith("coil_"):
            return region if p.slab else (f"coil_{region[5]}" if zc < top else "air")
        if fp:
            return f"coil_{fp[2]}" if bridge_lo < zc < top else (base_material(base) if zc < h else "air")
        return base_material(base) if zc < h or region in ("gap_shell", "air") else "air"

    def base_material(base: str) -> str:
        return "steel" if base in ("stator", "rotor_lo", "rotor_hi") else base

    def faces(edge: str, k: int) -> str | None:
        if edge == "outer":
            return "outer"
        return "search" if edge == "search" and (layers.z[k] + layers.z[k + 1]) / 2 < h else None

    def bottom(region: str) -> str:
        if region.startswith("coil_"):
            return f"{region}_in" if p.slab else f"coil_{region[5]}_{'in' if region[6] == 'a' else 'out'}"
        return "sym_z"

    def top_name(region: str) -> str:
        return f"{region}_out" if p.slab and region.startswith("coil_") else ("end_z" if p.slab else "outer")

    mesh = swept_mesh(mesh2d, layers, material, faces, bottom, top_name)
    materials = list(dict.fromkeys(mesh.GetMaterials()))
    law = fx.steel_law(p.js)
    laws = {m: (law if m == "steel" else VACUUM) for m in materials}
    return Model3D(mesh, laws, tuple(m for m in materials if m.startswith("coil_")),
                   dirichlet="sym_z|end_z|outer" if p.slab else "sym_z|outer")
