"""Moving band: conforming triangulation between the rotor ring and the stator ring at any angle."""
import math

import numpy as np

TAU = 2 * math.pi


def snap_angle(theta: float, divisions: int) -> tuple[float, int]:
    pitch = TAU / divisions
    k = round(theta / pitch)
    return k * pitch, k


def zipper_band(inner_angles: np.ndarray, outer_angles: np.ndarray) -> np.ndarray:
    n_in = len(inner_angles)
    a_in = np.mod(inner_angles, TAU)
    a_out = np.mod(outer_angles, TAU)
    out_order = np.argsort(a_out, kind="stable")
    first_out = int(out_order[0])
    start = a_out[first_out]
    rel_in = np.mod(a_in - start, TAU)
    rel_out = np.mod(a_out - start, TAU)
    events = sorted([(float(rel_out[j]), 1, int(j)) for j in out_order[1:]]
                    + [(float(rel_in[i]), 0, i) for i in range(n_in)])
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
