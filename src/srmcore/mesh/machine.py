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


def mesh_at_angle(static: StaticMesh, theta: float, check: bool = True) -> MachineMesh:
    wrapped = theta % TAU
    c, s = math.cos(wrapped), math.sin(wrapped)
    rotor_xy = static.rotor.nodes @ np.array([[c, s], [-s, c]])
    nodes = np.vstack([static.stator.nodes, rotor_xy])
    ns = len(static.stator.nodes)

    ring_in = static.rotor.nodes[static.rotor_ring]
    ring_out = static.stator.nodes[static.stator_ring]
    inner_angles = np.arctan2(ring_in[:, 1], ring_in[:, 0]) + wrapped
    outer_angles = np.arctan2(ring_out[:, 1], ring_out[:, 0])
    lookup = np.concatenate([ns + static.rotor_ring, static.stator_ring])
    band = orient_ccw(nodes, lookup[zipper_band(inner_angles, outer_angles)])

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
