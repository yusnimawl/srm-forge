"""TEAM Problem 24 as a 3D model (the half z >= 0 with a mirror plane at z = 0, or a slab), built in
netgen.occ from the same cross-section as tests/team24_fixture.py."""
from __future__ import annotations

import math
from dataclasses import dataclass

import ngsolve as ng
from netgen.occ import Axis, Box, Cylinder, Glue, OCCGeometry, Pnt, X, Y, Z

import team24_fixture as fx
from srmcore.materials.laws import VACUUM

from .solve import Model3D

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


def team24_model(params: Team24Params = Team24Params()) -> Model3D:
    p = params
    if not p.r_rotor_tip < fx.BAND_INNER < fx.BAND_OUTER < p.r_stator_bore:
        raise ValueError(f"gap_shell [{fx.BAND_INNER}, {fx.BAND_OUTER}] m must lie between r_rotor_tip "
                         f"{p.r_rotor_tip} and r_stator_bore {p.r_stator_bore}")
    stator, rotor = _iron(p)
    coils, top = _coils(p)
    shaft = Cylinder(Pnt(0, 0, 0), Z, p.r_shaft, p.depth / 2)
    shaft.mat("shaft")
    shell = (Cylinder(Pnt(0, 0, 0), Z, fx.BAND_OUTER, p.depth / 2) - Cylinder(Pnt(0, 0, 0), Z, fx.BAND_INNER, p.depth / 2))
    shell.mat("gap_shell")
    shell.maxh = p.gap_maxh
    z_air = top if p.slab else top + p.air_end_factor * p.r_stator_out
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
