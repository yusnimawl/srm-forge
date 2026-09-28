"""Full machine mesh at a rotor angle: fixed stator + rotated rotor + re-triangulated moving band."""
import math
from dataclasses import dataclass

import numpy as np

from ..model.errors import MeshRejected
from .band import TAU, zipper_band
from .quality import triangle_quality
from .static import StaticMesh, orient_ccw


@dataclass(frozen=True)
class MachineMesh:
    nodes: np.ndarray
    triangles: np.ndarray
    region_ids: np.ndarray
    region_names: tuple[str, ...]
    n_stator_nodes: int
    outer_edges: np.ndarray
    rotor_angle: float
    band_rows: slice


def _signed_areas(nodes: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    p = nodes[triangles]
    return 0.5 * ((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                  - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))


def mesh_at_angle(static: StaticMesh, theta: float, check: bool = True) -> MachineMesh:
    # theta % TAU can land exactly on TAU for tiny negative theta (e.g. -1e-20 % TAU == TAU in
    # float64, since TAU - 1e-20 rounds back to TAU), so clamp explicitly into [0, TAU).
    wrapped = theta % TAU
    if wrapped >= TAU:
        wrapped = 0.0
    c, s = math.cos(wrapped), math.sin(wrapped)
    rotor_xy = static.rotor.nodes @ np.array([[c, s], [-s, c]])
    nodes = np.vstack([static.stator.nodes, rotor_xy])
    ns = len(static.stator.nodes)

    ring_in = static.rotor.nodes[static.rotor_ring]
    ring_out = static.stator.nodes[static.stator_ring]
    # `wrapped` is now a stable, canonical [0, TAU) value for any theta representing the same
    # logical angle, so inner_angles is computed consistently across equivalent calls.
    inner_angles = np.arctan2(ring_in[:, 1], ring_in[:, 0]) + wrapped
    outer_angles = np.arctan2(ring_out[:, 1], ring_out[:, 0])
    lookup = np.concatenate([ns + static.rotor_ring, static.stator_ring])
    raw_local = zipper_band(inner_angles, outer_angles)
    raw_global = lookup[raw_local]

    # zipper_band's precondition can be violated by a coarse ring; orient_ccw only normalises
    # winding, it cannot fix a genuinely inverted triangle, so check the raw signed areas first.
    raw_areas = _signed_areas(nodes, raw_global)
    if np.any(raw_areas <= 0):
        bad = int(np.argmin(raw_areas))
        raise MeshRejected(
            ["inverted band triangle"],
            report={"rotor_angle": wrapped, "triangle_index": bad, "signed_area": float(raw_areas[bad])},
        )
    band = orient_ccw(nodes, raw_global)

    triangles = np.vstack([static.stator.triangles, static.rotor.triangles + ns, band])
    band_id = len(static.region_names)
    region_ids = np.concatenate([static.stator.region_ids, static.rotor.region_ids,
                                 np.full(len(band), band_id, dtype=np.int32)])
    start = len(triangles) - len(band)
    if check:
        worst = float(triangle_quality(nodes, band)[0].min())
        if worst < static.settings.band_min_angle_deg:
            raise MeshRejected([f"band min angle {worst:.2f}° < {static.settings.band_min_angle_deg}°"],
                               report={"rotor_angle": wrapped, "band_min_angle_deg": worst})
    return MachineMesh(
        nodes=nodes, triangles=triangles, region_ids=region_ids,
        region_names=static.region_names + ("moving_band",), n_stator_nodes=ns,
        outer_edges=static.outer_edges, rotor_angle=wrapped, band_rows=slice(start, len(triangles)),
    )
