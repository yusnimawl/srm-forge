"""Moving band: conforming triangulation between the rotor ring and the stator ring at any angle."""
import math

import numpy as np

TAU = 2 * math.pi


def snap_angle(theta: float, divisions: int) -> tuple[float, int]:
    pitch = TAU / divisions
    k = round(theta / pitch)
    return k * pitch, k


def zipper_band(inner_angles: np.ndarray, outer_angles: np.ndarray) -> np.ndarray:
    """Triangulate the annulus between an inner ring (local indices 0..n_in-1) and an outer ring
    (local indices n_in..n_in+n_out-1) by walking both rings together in increasing angle and, at
    each step, connecting whichever ring's next node comes first ("zipper" triangulation).

    Node angles may coincide exactly, including ties introduced only by floating-point noise at a
    multiple of either ring's pitch (e.g. two callers computing "the same" angle by different
    arithmetic paths a few ULPs apart): both rings' angles are snapped to a common tolerance grid
    before comparison, so the resulting topology is a function of the logical angles, not of
    bit-exact float noise.

    Precondition: the two rings must not be too mismatched in local spacing. If one ring is far
    coarser than the other (e.g. an outer ring an order of magnitude sparser than the inner ring),
    the zipper can be forced to emit an inverted (non-positive-area) triangle. This function does
    not check for that itself -- callers must verify the raw (un-oriented) triangle areas and
    reject the mesh if any are non-positive; do not rely on orientation normalisation (e.g.
    orient_ccw) to hide an inversion, since flipping winding does not fix a genuinely inverted
    (self-overlapping) triangle.
    """
    n_in = len(inner_angles)
    n_out = len(outer_angles)
    tol = 1e-9 * min(TAU / n_in, TAU / n_out)

    def _snap(a: np.ndarray) -> np.ndarray:
        q = np.mod(np.round(np.mod(a, TAU) / tol) * tol, TAU)
        return np.where(q >= TAU - tol / 2, 0.0, q)

    a_in = _snap(inner_angles)
    a_out = _snap(outer_angles)
    out_order = np.argsort(a_out, kind="stable")
    first_out = int(out_order[0])
    start = a_out[first_out]
    rel_in = _snap(a_in - start)
    rel_out = _snap(a_out - start)
    events = sorted([(float(rel_out[j]), 1, int(j)) for j in out_order[1:]]
                    + [(float(rel_in[i]), 0, i) for i in range(n_in)])
    # Where an inner and an outer node coincide in angle, the band cell between this tie and the
    # previous one is a quad, and the event order picks its diagonal. Alternating the diagonal from
    # tie to tie (outer-first on even ties, like the closing quad) makes the band mirror-symmetric
    # about every tie; one fixed diagonal biases the torque by ~1 % of peak with a sign set by it.
    ties = 0
    for k in range(len(events) - 1):
        if events[k][0] == events[k + 1][0] and events[k][1] != events[k + 1][1]:
            ties += 1
            if ties % 2 == 0 and events[k][1] == 0:
                events[k], events[k + 1] = events[k + 1], events[k]
    last_out = first_out
    last_in = int(np.argmax(rel_in))
    tris: list[tuple[int, int, int]] = []
    for _, kind, idx in events:
        if kind == 1:
            tris.append((last_in, n_in + last_out, n_in + idx))
            last_out = idx
        else:
            tris.append((last_in, n_in + last_out, idx))
            last_in = idx
    tris.append((last_in, n_in + last_out, n_in + first_out))
    return np.asarray(tris, dtype=np.int64)
