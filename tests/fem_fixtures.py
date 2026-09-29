"""Small analytic FEM problems for solver tests: a structured polar mesh (current-sheet toroid) and a
unit-square MMS problem. Plain numpy; no Gmsh."""
import math

import numpy as np

from srmcore.materials.laws import VACUUM
from srmcore.physics.problem import Magnetostatic2D
from srmcore.physics.winding import Winding


def polar_mesh(radii: np.ndarray, n_theta: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rings of n_theta nodes at radii[1:] around a centre node (radii[0] must be 0). Returns nodes,
    CCW triangles and each triangle's annulus index i (between radii[i] and radii[i+1])."""
    assert radii[0] == 0.0
    t = np.arange(n_theta) * 2 * math.pi / n_theta
    nodes = [np.zeros((1, 2))]
    for r in radii[1:]:
        nodes.append(np.column_stack([r * np.cos(t), r * np.sin(t)]))
    nodes = np.vstack(nodes)
    ring = lambda i: 1 + (i - 1) * n_theta + np.arange(n_theta)  # noqa: E731  node ids of radii[i]
    tris, layer = [], []
    first = ring(1)
    tris.append(np.column_stack([np.zeros(n_theta, int), first, np.roll(first, -1)]))
    layer.append(np.zeros(n_theta, int))
    for i in range(1, len(radii) - 1):
        a, b = ring(i), ring(i + 1)
        a1, b1 = np.roll(a, -1), np.roll(b, -1)
        tris += [np.column_stack([a, b, b1]), np.column_stack([a, b1, a1])]
        layer += [np.full(n_theta, i), np.full(n_theta, i)]
    return nodes, np.vstack(tris), np.concatenate(layer)


def triangle_area(nodes, tris):
    a, b, c = nodes[tris[:, 0]], nodes[tris[:, 1]], nodes[tris[:, 2]]
    return 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))


# Current-sheet toroid: +I in the inner sheet, -I in the outer sheet, iron ring in between. Between the
# sheets H = I / (2πr) exactly, whatever the material; outside them the field is zero.
SHEET_IN = (0.010, 0.011)
IRON = (0.012, 0.020)
SHEET_OUT = (0.021, 0.022)
R_OUTER = 0.030
DEPTH = 0.05


def toroid_problem(iron_law, current: float, n_theta: int = 256, layers_per_mm: int = 4) -> Magnetostatic2D:
    edges = [0.0, 0.005, *SHEET_IN, *IRON, *SHEET_OUT, R_OUTER]
    radii = [0.0]
    for lo, hi in zip(edges[:-1], edges[1:]):
        n = max(2, round((hi - lo) * 1000 * layers_per_mm)) if lo > 0 else 1
        radii += list(np.linspace(lo, hi, n + 1)[1:])
    radii = np.array(radii)
    nodes, tris, layer = polar_mesh(radii, n_theta)
    rmid = 0.5 * (radii[layer] + radii[layer + 1])
    in_sheet = (rmid > SHEET_IN[0]) & (rmid < SHEET_IN[1])
    out_sheet = (rmid > SHEET_OUT[0]) & (rmid < SHEET_OUT[1])
    iron = (rmid > IRON[0]) & (rmid < IRON[1])
    area = triangle_area(nodes, tris)
    region = np.where(in_sheet, 1, np.where(out_sheet, 2, np.where(iron, 3, 0)))
    coil = np.where(in_sheet, 0, np.where(out_sheet, 1, -1))
    winding = Winding(("sheet_in", "sheet_out"), ("c",),
                      np.array([[1.0 / area[in_sheet].sum()], [-1.0 / area[out_sheet].sum()]]), 1, False)
    outer = np.flatnonzero(np.isclose(np.hypot(nodes[:, 0], nodes[:, 1]), R_OUTER))
    return Magnetostatic2D(
        nodes=nodes, triangles=tris, element_law=iron.astype(np.int64), laws=(VACUUM, iron_law),
        element_region=region, region_names=("air", "sheet_in", "sheet_out", "iron"),
        region_kind={"air": "air", "sheet_in": "coil", "sheet_out": "coil", "iron": "stator_iron"},
        element_coil=coil, winding=winding, currents=np.array([current]), dirichlet_nodes=outer, depth=DEPTH,
    )


def exact_toroid_b(curve, current: float, r: np.ndarray) -> np.ndarray:
    """|B| in the iron ring at radius r: B such that H(B) = I / (2πr)."""
    grid = np.linspace(0.0, 5.0, 200_001)
    return np.interp(current / (2 * math.pi * r), curve.h_of_b(grid), grid)


class QuadraticLaw:
    """ν = ν0·(1 + α·B²): a smooth nonlinear law with closed-form energies, for MMS."""

    def __init__(self, nu0: float, alpha: float):
        self.nu0, self.alpha = nu0, alpha

    def nu_dnu(self, b2):
        b2 = np.asarray(b2, float)
        return self.nu0 * (1 + self.alpha * b2), np.full_like(b2, self.nu0 * self.alpha)

    def energy_density(self, b):
        b = np.asarray(b, float)
        return self.nu0 * (b**2 / 2 + self.alpha * b**4 / 4)

    def coenergy_density(self, b):
        b = np.asarray(b, float)
        return self.nu0 * (b**2 / 2 + 3 * self.alpha * b**4 / 4)


def mms_exact(x, y):
    return np.sin(math.pi * x) * np.sin(math.pi * y)


def mms_source(law: QuadraticLaw, x, y):
    """J = -∇·(ν(|∇A|²)∇A) for A = sin(πx)·sin(πy)."""
    p = math.pi
    sx, cx, sy, cy = np.sin(p * x), np.cos(p * x), np.sin(p * y), np.cos(p * y)
    ax, ay = p * cx * sy, p * sx * cy
    axx, ayy, axy = -p * p * sx * sy, -p * p * sx * sy, p * p * cx * cy
    g = ax * ax + ay * ay
    gx, gy = 2 * (ax * axx + ay * axy), 2 * (ax * axy + ay * ayy)
    nu, dnu = law.nu_dnu(g)
    return -(nu * (axx + ayy) + dnu * (gx * ax + gy * ay))


def mms_problem(law: QuadraticLaw, n: int) -> Magnetostatic2D:
    """Unit square, n×n cells split into triangles, A = 0 on the boundary; every element is its own
    'coil side' carrying the manufactured source at its centroid."""
    xs = np.linspace(0.0, 1.0, n + 1)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    nodes = np.column_stack([X.ravel(), Y.ravel()])
    idx = lambda i, j: i * (n + 1) + j  # noqa: E731
    i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    i, j = i.ravel(), j.ravel()
    tris = np.vstack([np.column_stack([idx(i, j), idx(i + 1, j), idx(i + 1, j + 1)]),
                      np.column_stack([idx(i, j), idx(i + 1, j + 1), idx(i, j + 1)])])
    c = nodes[tris].mean(axis=1)
    j_elem = mms_source(law, c[:, 0], c[:, 1])
    m = len(tris)
    on_boundary = np.flatnonzero((nodes[:, 0] % 1.0 == 0) | (nodes[:, 1] % 1.0 == 0))
    winding = Winding(tuple(f"e{k}" for k in range(m)), ("c",), j_elem[:, None], 1, False)
    return Magnetostatic2D(
        nodes=nodes, triangles=tris, element_law=np.zeros(m, np.int64), laws=(law,),
        element_region=np.zeros(m, np.int64), region_names=("square",), region_kind={"square": "stator_iron"},
        element_coil=np.arange(m), winding=winding, currents=np.array([1.0]), dirichlet_nodes=on_boundary,
        depth=1.0,
    )
