import math

import numpy as np
import pytest

from srmcore.mesh.band import snap_angle, zipper_band
from srmcore.mesh.static import orient_ccw

TAU = 2 * math.pi


def _rings(n_in, n_out, offset):
    a_in = np.arange(n_in) * TAU / n_in + offset
    a_out = np.arange(n_out) * TAU / n_out
    nodes = np.vstack([np.c_[np.cos(a_in), np.sin(a_in)], 1.1 * np.c_[np.cos(a_out), np.sin(a_out)]])
    return a_in, a_out, nodes


def _signed(nodes, tris):
    p = nodes[tris]
    return 0.5 * ((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                  - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))


def _polygon_area(n, r):
    return 0.5 * n * r * r * math.sin(TAU / n)


def test_snap_angle():
    pitch = TAU / 24
    assert snap_angle(0.26, 24) == (pytest.approx(pitch), 1)
    assert snap_angle(-0.01, 24)[1] == 0


@pytest.mark.parametrize("n_in,n_out,offset_frac", [
    (12, 12, 0.0), (12, 12, 0.5), (12, 12, 0.3), (12, 12, 1.0), (12, 12, -0.2), (10, 14, 0.25),
])
def test_zipper_covers_annulus_exactly(n_in, n_out, offset_frac):
    a_in, a_out, nodes = _rings(n_in, n_out, offset_frac * TAU / n_in)
    tris = orient_ccw(nodes, zipper_band(a_in, a_out))
    assert len(tris) == n_in + n_out
    areas = _signed(nodes, tris)
    assert np.all(areas > 1e-9)
    assert areas.sum() == pytest.approx(_polygon_area(n_out, 1.1) - _polygon_area(n_in, 1.0), rel=1e-12)


def test_zipper_band_can_invert_for_a_coarse_outer_ring():
    # (n_in, n_out) = (64, 8) with r=1, R=1.1: this ring-density mismatch violates zipper_band's
    # documented precondition -- the raw (un-oriented) output can contain a non-positive-area
    # triangle. Callers (mesh_at_angle) must check this themselves; orient_ccw only fixes
    # winding, it cannot fix a genuinely inverted triangle.
    a_in, a_out, nodes = _rings(64, 8, 0.0)
    tris = zipper_band(a_in, a_out)
    areas = _signed(nodes, tris)
    assert np.any(areas <= 0)


def test_every_ring_edge_used_once():
    n = 12
    a_in, a_out, nodes = _rings(n, n, 0.37 * TAU / n)
    tris = zipper_band(a_in, a_out)
    edges = {}
    for t in tris:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            key = (min(a, b), max(a, b))
            edges[key] = edges.get(key, 0) + 1
    for i in range(n):
        assert edges[(min(i, (i + 1) % n), max(i, (i + 1) % n))] == 1
        j, k = n + i, n + (i + 1) % n
        assert edges[(min(j, k), max(j, k))] == 1
