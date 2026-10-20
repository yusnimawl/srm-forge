"""Cut-edge loss multiplier for lamination iron loss.

Cutting damages a band of width delta along every cut edge of a lamination and raises its hysteresis loss there by
a factor K. A strip of width w cut on both edges then has loss P(w) = P_bulk (1 + a / w) with a = 2 delta (K - 1),
the 1/w law measured on strips (A. T. Huynh et al., "A comprehensive review of electrical steel cutting techniques
for electric machine cores", Results in Engineering, 2026, doi 10.1016/j.rineng.2026.112686). Only the product a is
well known; delta only places the extra loss. Catalogue data come from 30 mm Epstein strips that already carry two
cut edges, so the multiplier is divided by B0 = 1 + EPSTEIN_A / EPSTEIN_WIDTH.

The cut edges of a mesh part are the edges used by exactly one iron triangle: iron against slot air, the air gap,
the outside, the shaft and imported hole air. `band_fraction` is the share of each triangle's area within delta of a
cut edge and `edge_multiplier` turns it into the factor on hysteresis and excess loss.
"""
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

EPSTEIN_A = 1.4e-3  # m; as-sheared Epstein strips, the punching nominal
EPSTEIN_WIDTH = 0.030  # m
B0 = 1 + EPSTEIN_A / EPSTEIN_WIDTH


@dataclass(frozen=True)
class CutProcess:
    """a: nominal width coefficient (m); a_low, a_high: its range (m); delta: damaged-band width (m)."""

    a: float
    a_low: float
    a_high: float
    delta: float


CUT_PROCESSES: dict[str, CutProcess] = {
    # wedm: delta from Huynh Table 6 (<= 0.2 mm); a from the "modest" loss rise of its section 7.1, a grade C estimate
    "wedm": CutProcess(a=0.3e-3, a_low=0.0, a_high=0.7e-3, delta=0.2e-3),
    # punching (or shearing): a nominal from NO20 0.2 mm (thinnest gauge with data), high from M400-50A 0.5 mm;
    # delta from Table 6 (0.5-2.5 mm, lower end)
    "punching": CutProcess(a=1.4e-3, a_low=1.4e-3, a_high=3.5e-3, delta=0.5e-3),
    # laser: a nominal and low from the 35WW270 width fit (1.64-1.96 mm), high from 35WW300 at 10 mm;
    # delta from Table 6 (0.2-1.5 mm)
    "laser": CutProcess(a=1.8e-3, a_low=1.6e-3, a_high=5.3e-3, delta=0.5e-3),
}

# symmetric 6-point rule: (barycentric coordinates, weight); the weights sum to 1
_A1, _B1, _W1 = 0.816847572980459, 0.091576213509771, 0.109951743655322
_A2, _B2, _W2 = 0.108103018168070, 0.445948490915965, 0.223381589678011
_BARY = np.array([[_A1, _B1, _B1], [_B1, _A1, _B1], [_B1, _B1, _A1],
                  [_A2, _B2, _B2], [_B2, _A2, _B2], [_B2, _B2, _A2]])
_WEIGHTS = np.array([_W1] * 3 + [_W2] * 3)


def cut_edges(nodes: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """(n_edges, 2, 2) end points of the edges used by exactly one of the given triangles."""
    tri = np.asarray(triangles)
    pairs = np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]), axis=1)
    edges, counts = np.unique(pairs, axis=0, return_counts=True)
    return np.asarray(nodes)[edges[counts == 1]]


def _segment_distance(pts: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distance from each point to its own segment a-b (all arrays (n, 2))."""
    ab = b - a
    len2 = np.einsum("ij,ij->i", ab, ab)
    t = np.clip(np.einsum("ij,ij->i", pts - a, ab) / np.where(len2 > 0, len2, 1.0), 0.0, 1.0)
    return np.hypot(*(pts - (a + t[:, None] * ab)).T)


def band_fraction(nodes: np.ndarray, triangles: np.ndarray, delta: float, cut: np.ndarray | None = None) -> np.ndarray:
    """(n_tri,) share of each triangle's area within delta of a cut edge, in [0, 1].

    `cut` are the cut-edge segments (default: those of `triangles`).
    """
    nodes = np.asarray(nodes)
    tri = np.asarray(triangles)
    seg = cut_edges(nodes, tri) if cut is None else cut
    if len(seg) == 0:
        return np.zeros(len(tri))
    a, b = seg[:, 0], seg[:, 1]
    longest = np.hypot(*(b - a).T).max()
    n = max(1, int(np.ceil(longest / (delta / 8))))
    t = np.linspace(0.0, 1.0, n + 1)
    along = a[:, None, :] + t[None, :, None] * (b - a)[:, None, :]
    owner = np.repeat(np.arange(len(seg)), n + 1)
    tree = cKDTree(along.reshape(-1, 2))

    samples = np.einsum("sk,tkd->tsd", _BARY, nodes[tri]).reshape(-1, 2)
    k = min(8, len(owner))
    _, near = tree.query(samples, k=k)
    cand = owner[near.reshape(len(samples), k)]
    dist = np.min([_segment_distance(samples, a[cand[:, j]], b[cand[:, j]]) for j in range(k)], axis=0)
    return (dist.reshape(len(tri), -1) <= delta) @ _WEIGHTS


def edge_multiplier(frac: np.ndarray, a: float, delta: float) -> np.ndarray:
    """Factor on hysteresis and excess loss for band fractions `frac`: (1 + a / (2 delta) * frac) / B0."""
    return (1 + a / (2 * delta) * np.asarray(frac)) / B0
