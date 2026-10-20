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

_CHUNK = 200_000  # sample points per distance query


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


def _sub_centroids(n: int) -> np.ndarray:
    """(n * n, 2) barycentric (u, v) of the centroids of the n * n equal sub-triangles of a triangle split uniformly."""
    i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    up = (i + j <= n - 1)
    down = (i + j <= n - 2)
    return np.vstack([np.column_stack([i[up] + 1 / 3, j[up] + 1 / 3]),
                      np.column_stack([i[down] + 2 / 3, j[down] + 2 / 3])]) / n


def band_fraction(nodes: np.ndarray, triangles: np.ndarray, delta: float, cut: np.ndarray | None = None) -> np.ndarray:
    """(n_tri,) share of each triangle's area within delta of a cut edge, in [0, 1].

    `cut` are the cut-edge segments (default: those of `triangles`). A triangle that may reach the band is split
    uniformly into n * n sub-triangles, n = ceil(longest edge / (delta / 4)); its fraction is the share of
    sub-centroids within delta (exact point-to-segment distance) of a cut segment.
    """
    nodes = np.asarray(nodes, dtype=float)
    tri = np.asarray(triangles)
    seg = cut_edges(nodes, tri) if cut is None else np.asarray(cut, dtype=float)
    frac = np.zeros(len(tri))
    if len(seg) == 0 or len(tri) == 0:
        return frac
    a, b = seg[:, 0], seg[:, 1]
    longest = np.hypot(*(b - a).T).max()
    m = max(1, int(np.ceil(longest / (delta / 8))))
    h = longest / m  # largest spacing of the samples along a segment
    t = np.linspace(0.0, 1.0, m + 1)
    samples = (a[:, None, :] + t[None, :, None] * (b - a)[:, None, :]).reshape(-1, 2)
    owner = np.repeat(np.arange(len(seg)), m + 1)
    tree = cKDTree(samples)

    # the nearest sample is at most h / 2 farther than the nearest segment point, and never nearer
    p = nodes[tri]
    edge = np.max(np.hypot(*(p - np.roll(p, 1, axis=1)).transpose(2, 0, 1)), axis=1)
    d_c, _ = tree.query(p.mean(axis=1))
    near = np.flatnonzero(d_c - h / 2 <= delta + edge)
    n_sub = np.maximum(1, np.ceil(edge[near] / (delta / 4)).astype(int))

    def within(pts: np.ndarray) -> np.ndarray:
        d_s, _ = tree.query(pts, distance_upper_bound=delta + h / 2)  # inf beyond the bound
        inside = d_s <= delta
        unsure = np.flatnonzero(~inside & (d_s - h / 2 <= delta))
        if len(unsure):
            hits = tree.query_ball_point(pts[unsure], delta + h / 2, return_sorted=False)
            counts = np.fromiter(map(len, hits), int, len(hits))
            row = np.repeat(unsure, counts)
            s = owner[np.concatenate(hits).astype(int)]
            ok = _segment_distance(pts[row], a[s], b[s]) <= delta
            inside[np.unique(row[ok])] = True
        return inside

    for n in np.unique(n_sub):
        uv = _sub_centroids(int(n))
        group = near[n_sub == n]
        step = max(1, _CHUNK // len(uv))
        for k in range(0, len(group), step):
            g = group[k:k + step]
            q = p[g]
            pts = (q[:, None, 0] + uv[None, :, 0, None] * (q[:, None, 1] - q[:, None, 0])
                   + uv[None, :, 1, None] * (q[:, None, 2] - q[:, None, 0])).reshape(-1, 2)
            frac[g] = within(pts).reshape(len(g), -1).mean(axis=1)
    return frac


def edge_multiplier(frac: np.ndarray, a: float, delta: float) -> np.ndarray:
    """Factor on hysteresis and excess loss for band fractions `frac`: (1 + a / (2 delta) * frac) / B0."""
    return (1 + a / (2 * delta) * np.asarray(frac)) / B0
