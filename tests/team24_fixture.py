"""TEAM Problem 24 (Allen & Rodger, Univ. of Bath) as a 2D Magnetostatic2D: the locked-rotor test rig,
meshed with Gmsh directly. Dimensions in mm below are read from the report's Fig. 1 and Fig. 2 (see
docs/team24-feasibility.md for the source of every number). Fillets (3 mm) are omitted.

Layout (x right, y up): a solid-steel stator ring with two poles at +y and -y, a two-pole rotor with a
non-magnetic shaft, and one 350-turn coil around each stator pole. In the x-y section each coil shows
as two 24 x 17 mm sides either side of its pole; both coils are in one series circuit."""
import functools
import math
from dataclasses import dataclass

import gmsh
import numpy as np

from srmcore.materials.bh import process_bh
from srmcore.materials.laws import VACUUM
from srmcore.materials.schema import BHTable
from srmcore.physics.problem import BandInfo, Magnetostatic2D
from srmcore.physics.winding import Winding

MM = 1e-3
# Fig. 1
R_STATOR_OUT = 209.0 / 2 * MM
YOKE_THICKNESS = 21.4 * MM
R_YOKE_IN = R_STATOR_OUT - YOKE_THICKNESS            # 83.1 mm
R_STATOR_BORE = 107.5 / 2 * MM                       # stator pole tips
POLE_WIDTH_STATOR = 27.8 * MM
R_ROTOR_TIP = 102.1 / 2 * MM
R_SHAFT = 50.8 / 2 * MM
HUB_THICKNESS = 12.7 * MM                            # hub outer radius = shaft radius + 12.7 mm
R_HUB = R_SHAFT + HUB_THICKNESS
POLE_WIDTH_ROTOR = 25.4 * MM
DEPTH = 25.4 * MM
ROTOR_ANGLE = -math.radians(22.0)                    # rotor poles 22 deg clockwise from the stator poles
# Fig. 2
TURNS = 350
COIL_INNER_HALF_WIDTH = 34.0 / 2 * MM                # coil hole 34 mm wide across the pole
COIL_BUILD = 24.0 * MM                               # winding build in x
COIL_THICKNESS = 17.0 * MM                           # extent along y
COIL_MID_Y = 63.0 * MM
RESISTANCE = 3.09
VOLTAGE = 23.1

# Table I, H in A/m and B in T.
H_TABLE = (0, 400, 801, 1601, 2402, 3203, 4003, 4804, 6405, 8007, 9608, 11210, 12811, 14412, 17615, 20818,
           24020, 27223, 30426, 33629, 39634)
B_TABLE = (0, 1.413, 1.594, 1.751, 1.839, 1.896, 1.936, 1.967, 2.008, 2.042, 2.073, 2.101, 2.127, 2.151,
           2.197, 2.240, 2.281, 2.321, 2.361, 2.400, 2.472)
# The table stops at J = 2.42 T; the C1 tail beyond it needs a saturation polarisation, which the report
# does not give. This value is an assumption (the last table slope is still above mu0).
ASSUMED_JS = 2.6

# Band (air-gap annulus for Arkkio and virtual work) sits inside the 2.7 mm gap.
BAND_INNER = 51.6 * MM
BAND_OUTER = 53.2 * MM

COIL_SIDES = ("coil_top_right", "coil_top_left", "coil_bottom_right", "coil_bottom_left")
# Both coils carry flux in the same direction through their poles, so the same circulation about y:
# +z on the right side, -z on the left side, for the top and the bottom coil.
COIL_SIGNS = (1.0, -1.0, 1.0, -1.0)


def steel_law(js: float = ASSUMED_JS):
    return process_bh(BHTable(h=H_TABLE, b=B_TABLE), stacking_factor=1.0, saturation_polarisation=js)[0]


@dataclass(frozen=True, eq=False)
class Team24Mesh:
    nodes: np.ndarray
    triangles: np.ndarray
    region: np.ndarray                 # index into REGIONS
    band_elements: np.ndarray


REGIONS = ("air", "stator", "rotor", *COIL_SIDES)


def _occ():
    return gmsh.model.occ


def _disk(r):
    return _occ().addDisk(0, 0, 0, r, r)


def _rect(x0, y0, x1, y1):
    return _occ().addRectangle(x0, y0, 0, x1 - x0, y1 - y0)


def _surf(tags):
    return [(2, t) for t in tags]


def _cut(objects, tools):
    out, _ = _occ().cut(_surf(objects), _surf(tools))
    return [t for _, t in out]


@functools.lru_cache(maxsize=4)
def team24_mesh(size_scale: float = 1.0) -> Team24Mesh:
    """Conformal triangle mesh of stator, rotor, four coil sides, air and the gap band. `size_scale`
    multiplies every element size."""
    if not gmsh.isInitialized():
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("team24")
    try:
        domain = _disk(R_STATOR_OUT)
        cavity = _cut([_disk(R_YOKE_IN)], [_rect(-POLE_WIDTH_STATOR / 2, -R_STATOR_OUT, POLE_WIDTH_STATOR / 2, R_STATOR_OUT)])
        stator = _cut([_disk(R_STATOR_OUT)], [*cavity, _disk(R_STATOR_BORE)])
        bars = _occ().intersect(_surf([_rect(-POLE_WIDTH_ROTOR / 2, -R_STATOR_OUT / 2, POLE_WIDTH_ROTOR / 2, R_STATOR_OUT / 2)]),
                                _surf([_disk(R_ROTOR_TIP)]))[0]
        hub = _disk(R_HUB)
        fused = _occ().fuse(_surf([hub]), bars)[0]
        rotor = _cut([t for _, t in fused], [_disk(R_SHAFT)])
        _occ().rotate(_surf(rotor), 0, 0, 0, 0, 0, 1, ROTOR_ANGLE)
        shaft = _disk(R_SHAFT)
        band = _cut([_disk(BAND_OUTER)], [_disk(BAND_INNER)])
        coils = []
        for y0 in (COIL_MID_Y, -COIL_MID_Y):
            lo, hi = y0 - COIL_THICKNESS / 2, y0 + COIL_THICKNESS / 2
            x0 = COIL_INNER_HALF_WIDTH
            coils.append(_rect(x0, lo, x0 + COIL_BUILD, hi))         # right
            coils.append(_rect(-x0 - COIL_BUILD, lo, -x0, hi))       # left
        # COIL_SIDES order: top_right, top_left, bottom_right, bottom_left
        coil_tags = [coils[0], coils[1], coils[2], coils[3]]
        tools = [stator, rotor, [shaft], band, *[[c] for c in coil_tags]]
        flat = [t for group in tools for t in group]
        _, out_map = _occ().fragment(_surf([domain]), _surf(flat))
        _occ().synchronize()
        pieces = [[t for _, t in m] for m in out_map]
        owner = {}
        offset = 1
        for gi, group in enumerate(tools):
            for _ in group:
                for t in pieces[offset]:
                    owner[t] = gi
                offset += 1
        air = [t for t in pieces[0] if t not in owner]
        kind_of = {**{t: 0 for t in air}}
        for t, gi in owner.items():
            kind_of[t] = {0: 1, 1: 2, 2: 0, 3: 0}.get(gi, gi - 4 + 3)
        band_surfaces = [t for t, gi in owner.items() if gi == 3]
        curves = sorted({c for _, c in gmsh.model.getBoundary(_surf(band_surfaces), oriented=False)})
        f = gmsh.model.mesh.field
        f.add("Distance", 1)
        f.setNumbers(1, "CurvesList", curves)
        f.setNumber(1, "Sampling", 400)
        f.add("Threshold", 2)
        f.setNumber(2, "InField", 1)
        f.setNumber(2, "SizeMin", 0.45 * MM * size_scale)
        f.setNumber(2, "SizeMax", 4.0 * MM * size_scale)
        f.setNumber(2, "DistMin", 1.0 * MM)
        f.setNumber(2, "DistMax", 14.0 * MM)
        f.setAsBackgroundMesh(2)
        for opt in ("Mesh.MeshSizeFromPoints", "Mesh.MeshSizeFromCurvature", "Mesh.MeshSizeExtendFromBoundary"):
            gmsh.option.setNumber(opt, 0)
        gmsh.model.mesh.generate(2)

        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        index = {int(t): i for i, t in enumerate(node_tags)}
        nodes = np.asarray(coords).reshape(-1, 3)[:, :2]
        tris, region, is_band = [], [], []
        for t, kind in kind_of.items():
            types, _, enodes = gmsh.model.mesh.getElements(2, t)
            for ty, en in zip(types, enodes):
                assert ty == 2, "expected linear triangles"
                conn = np.array([index[int(n)] for n in en]).reshape(-1, 3)
                tris.append(conn)
                region.append(np.full(len(conn), kind))
                is_band.append(np.full(len(conn), t in band_surfaces))
        tris, region, is_band = np.vstack(tris), np.concatenate(region), np.concatenate(is_band)
        a, b, c = nodes[tris[:, 0]], nodes[tris[:, 1]], nodes[tris[:, 2]]
        cw = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]) < 0
        tris[cw] = tris[cw][:, [0, 2, 1]]
        used = np.unique(tris)
        remap = np.full(len(nodes), -1)
        remap[used] = np.arange(len(used))
        return Team24Mesh(nodes[used], remap[tris], region, np.flatnonzero(is_band))
    finally:
        gmsh.model.remove()


def _triangle_area(nodes, tris):
    a, b, c = nodes[tris[:, 0]], nodes[tris[:, 1]], nodes[tris[:, 2]]
    return 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))


def team24_problem(current: float, size_scale: float = 1.0, js: float = ASSUMED_JS) -> Magnetostatic2D:
    """TEAM 24 at a given series-circuit current in A (350 turns per coil); `js` is the assumed
    saturation polarisation in T."""
    m = team24_mesh(size_scale)
    law = steel_law(js)
    area = _triangle_area(m.nodes, m.triangles)
    n_side = len(COIL_SIDES)
    first_coil = REGIONS.index(COIL_SIDES[0])
    coil = np.where(m.region >= first_coil, m.region - first_coil, -1)
    matrix = np.array([[COIL_SIGNS[s] * TURNS / area[coil == s].sum()] for s in range(n_side)])
    winding = Winding(COIL_SIDES, ("series",), matrix, 1, False)
    iron = np.isin(m.region, (1, 2))
    kinds = {"air": "air", "stator": "stator_iron", "rotor": "rotor_iron", **{s: "coil" for s in COIL_SIDES}}
    outer = np.flatnonzero(np.isclose(np.hypot(m.nodes[:, 0], m.nodes[:, 1]), R_STATOR_OUT, rtol=0, atol=1e-7))
    return Magnetostatic2D(
        nodes=m.nodes, triangles=m.triangles, element_law=iron.astype(np.int64), laws=(VACUUM, law),
        element_region=m.region.astype(np.int64), region_names=REGIONS, region_kind=kinds,
        element_coil=coil, winding=winding, currents=np.array([current]), dirichlet_nodes=outer, depth=DEPTH,
        band=BandInfo(m.band_elements, BAND_INNER, BAND_OUTER),
    )
