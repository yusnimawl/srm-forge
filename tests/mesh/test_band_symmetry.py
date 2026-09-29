import math

import numpy as np

from srmcore.mesh.band import zipper_band


def _labelled(tris: np.ndarray, n: int) -> set[frozenset]:
    label = lambda v: ("in", v) if v < n else ("out", v - n)  # noqa: E731
    return {frozenset(map(label, t)) for t in tris.tolist()}


def test_coinciding_rings_give_a_mirror_symmetric_band():
    """With both rings on the same angles every band cell is a quad. Its diagonal alternates, so the band
    is mirror-symmetric about each node; one fixed diagonal biased torque by ~1 % of peak."""
    n = 24
    angles = np.arange(n) * 2 * math.pi / n
    tris = _labelled(zipper_band(angles, angles.copy()), n)
    assert len(tris) == 2 * n
    mirrored = {frozenset((ring, (-k) % n) for ring, k in t) for t in tris}
    assert mirrored == tris
    rising = sum(frozenset({("in", k), ("out", (k + 1) % n)}) <= t for t in tris for k in range(n))
    falling = sum(frozenset({("in", (k + 1) % n), ("out", k)}) <= t for t in tris for k in range(n))
    assert rising == falling == n  # each diagonal lies in two triangles, n/2 quads per direction
