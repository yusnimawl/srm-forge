"""TEAM Problem 24 (Allen & Rodger, Univ. of Bath) as a 2D Magnetostatic2D: the locked-rotor test rig,
meshed with Gmsh directly. Dimensions in mm below are read from the report's Fig. 1 and Fig. 2 (see
docs/m5b-team24-results.md for the source of every number). Fillets (3 mm) are omitted.

Layout (x right, y up): a solid-steel stator ring with two poles at +y and -y, a two-pole rotor with a
non-magnetic shaft, and one 350-turn coil around each stator pole. In the x-y section each coil shows
as two 24 x 17 mm sides either side of its pole; both coils are in one series circuit."""
import functools
import math
from dataclasses import dataclass

import gmsh
import numpy as np
from matplotlib.tri import LinearTriInterpolator, Triangulation
from scipy.integrate import solve_ivp

from srmcore.materials.bh import process_bh
from srmcore.materials.laws import VACUUM
from srmcore.materials.schema import BHTable
from srmcore.physics.problem import BandInfo, Magnetostatic2D
from srmcore.physics.winding import Winding
from srmcore.post.quantities import arkkio_torque, flux_linkage

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
# Tables III-V share these sample times (s); point 1 (t = 0, all zero) is omitted.
TABLE_TIME = np.array([0.002, 0.005, 0.010, 0.015, 0.020, 0.030, 0.040, 0.050, 0.060, 0.070, 0.080, 0.090,
                       0.100, 0.120, 0.140, 0.160, 0.180, 0.200, 0.240, 0.300])
TABLE_CURRENT = np.array([0.91, 1.80, 2.95, 3.82, 4.49, 5.45, 6.05, 6.45, 6.71, 6.91, 7.04, 7.15, 7.22, 7.31,
                          7.36, 7.38, 7.40, 7.40, 7.41, 7.41])                      # Table III, A
TABLE_TORQUE = np.array([0.02, 0.17, 0.39, 0.68, 0.96, 1.48, 1.90, 2.24, 2.48, 2.68, 2.82, 2.93, 3.02, 3.11,
                         3.17, 3.19, 3.21, 3.22, 3.22, 3.22])                       # Table IV, N.m
TABLE_ROTOR_FLUX = 1e-4 * np.array([0.29, 0.77, 1.44, 1.99, 2.44, 3.11, 3.58, 3.91, 4.14, 4.31, 4.43, 4.52,
                                    4.58, 4.65, 4.69, 4.71, 4.72, 4.72, 4.72, 4.72])  # Table V, Wb
# Table II: measured coil voltage (s, V); constant 23.10 V after the last point.
VOLTAGE_TIME = np.array([0, 0.0002, 0.002, 0.005, 0.010, 0.030, 0.050, 0.070, 0.090, 0.120, 0.140])
VOLTAGE_TABLE = np.array([0, 23.60, 23.48, 23.38, 23.32, 23.18, 23.13, 23.12, 23.10, 23.10, 23.10])
# Rotor-pole search coil: wound around the rotor pole 8.7 mm from the pole corner (Fig. 1).
SEARCH_COIL_FROM_CORNER = 8.7 * MM

# Table I. The printed H column is in units of 1e4 A-t/m (entries 00.400 .. 39.634), confirmed by Fig. 3's
# H axis (0 .. 4.0e5 A/m). J = B - mu0*H peaks at 1.979 T at point 17 (240.2 kA/m) and then falls by up to
# 5 mT (points 18-21), which is at the table's digitisation level; process_bh needs J non-decreasing, so
# the table stops at point 17.
H_TABLE = tuple(1e4 * h for h in (0, 0.400, 0.801, 1.601, 2.402, 3.203, 4.003, 4.804, 6.405, 8.007, 9.608,
                                  11.210, 12.811, 14.412, 17.615, 20.818, 24.020))
B_TABLE = (0, 1.413, 1.594, 1.751, 1.839, 1.896, 1.936, 1.967, 2.008, 2.042, 2.073, 2.101, 2.127, 2.151,
           2.197, 2.240, 2.281)
# Saturation polarisation of the C1 tail beyond point 17 (assumed; the dropped points sit at J = 1.974 to
# 1.979 T). Peak iron |B| at 7.41 A is about 2.3 T, so results move < 0.01 % over Js = 1.98 .. 2.05 T.
ASSUMED_JS = 2.0

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


def table_ii_voltage(t: float) -> float:
    """Measured coil voltage at time t (s), linear between the Table II points."""
    return float(np.interp(t, VOLTAGE_TIME, VOLTAGE_TABLE))


def current_rise(psi_of_i, times, resistance: float = RESISTANCE, voltage=VOLTAGE) -> np.ndarray:
    """Series-circuit current (A) at `times` (s) after a voltage step on the locked rotor, from
    dpsi/dt = V(t) - R*i on the psi(i) map: di/dt = (V(t) - R*i) / psi'(i). `psi_of_i` is a scipy
    piecewise polynomial (PCHIP) in Wb-turns; `voltage` is a constant in V or a callable of t."""
    v = voltage if callable(voltage) else (lambda t: voltage)
    dpsi = psi_of_i.derivative()
    times = np.asarray(times, float)
    sol = solve_ivp(lambda t, y: [(v(t) - resistance * y[0]) / float(dpsi(y[0]))], (0.0, float(times.max())),
                    [0.0], t_eval=times, max_step=2e-4, rtol=1e-8, atol=1e-10)
    if not sol.success:
        raise RuntimeError(f"current rise integration failed: {sol.message}")
    return sol.y[0]


def rotor_pole_flux(problem: Magnetostatic2D, solution, pole: int = 1) -> float:
    """Flux (Wb) through the rotor pole on the chord across both flanks at the search-coil position:
    SEARCH_COIL_FROM_CORNER along the flank from the tip corner. pole = 1 is the rotor pole under the
    top stator pole, -1 the opposite one. Flux = depth * |A(flank 1) - A(flank 2)|."""
    half = POLE_WIDTH_ROTOR / 2
    dist = math.sqrt(R_ROTOR_TIP ** 2 - half ** 2) - SEARCH_COIL_FROM_CORNER
    axis = pole * np.array([math.sin(-ROTOR_ANGLE), math.cos(-ROTOR_ANGLE)])
    normal = np.array([axis[1], -axis[0]])
    a = LinearTriInterpolator(Triangulation(problem.nodes[:, 0], problem.nodes[:, 1], problem.triangles),
                              solution.a)
    p1, p2 = dist * axis + half * normal, dist * axis - half * normal
    a1, a2 = a(*p1), a(*p2)
    if np.ma.is_masked(a1) or np.ma.is_masked(a2):
        raise ValueError("search-coil chord end lies outside the mesh")
    return DEPTH * abs(float(a1) - float(a2))


# Locked-rotor map currents (A): dense below 1 A where psi(i) bends, to 7.75 A (above V/R = 7.48 A).
MAP_CURRENTS = np.concatenate([np.linspace(0.0, 1.0, 9), np.linspace(1.25, 7.75, 27)])


def locked_rotor_map(solver, currents=MAP_CURRENTS, size_scale: float = 1.0, js: float = ASSUMED_JS) -> dict:
    """psi (Wb-turns), Arkkio torque (N.m, absolute) and rotor-pole flux (Wb) at each current, each point
    started from the previous solution. Raises if a point does not converge."""
    out = {"current": np.asarray(currents, float), "psi": [], "torque": [], "rotor_flux": []}
    a0 = None
    for i in out["current"]:
        p = team24_problem(float(i), size_scale, js)
        s = solver.solve(p, initial=a0)
        if s.status.value != "OK":
            raise RuntimeError(f"TEAM 24 solve at {i} A: {s.status}")
        a0 = s.a
        out["psi"].append(flux_linkage(p, s)[0])
        out["torque"].append(abs(arkkio_torque(p, s)))
        out["rotor_flux"].append(rotor_pole_flux(p, s))
    return {k: np.asarray(v, float) for k, v in out.items()}
