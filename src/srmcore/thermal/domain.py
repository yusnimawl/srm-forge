"""Thermal domain: the solid part of the static EM mesh, with the air gap dropped and the slot liner marked."""
from dataclasses import dataclass

import numpy as np

from ..mesh.static import StaticMesh
from ..model.design import RadialSRMParams

EXCLUDED_REGIONS = ("airgap_stator", "airgap_rotor", "rotor_slot_air", "stator_outer_air")
_CHUNK = 256


@dataclass(frozen=True)
class ThermalDomain:
    nodes: np.ndarray
    triangles: np.ndarray
    element_kind: np.ndarray
    stator_elements: np.ndarray
    rotor_elements: np.ndarray
    coil_elements: dict[str, np.ndarray]
    outer_edges: np.ndarray
    bore_edges: np.ndarray
    rotor_edges: np.ndarray

    def from_em(self, stator_values: np.ndarray, rotor_values: np.ndarray) -> np.ndarray:
        """Per-element arrays in EM order to thermal order."""
        return np.concatenate([np.asarray(stator_values)[self.stator_elements],
                               np.asarray(rotor_values)[self.rotor_elements]])


def boundary_edges(triangles: np.ndarray) -> np.ndarray:
    """Edges used by exactly one triangle."""
    e = np.sort(np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
    uniq, count = np.unique(e, axis=0, return_counts=True)
    return uniq[count == 1]


def distance_to_segments(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Exact distance from each point to the nearest of the segments a-b, chunked over the points."""
    ab = b - a
    ab2 = np.maximum((ab ** 2).sum(axis=1), 1e-300)
    out = np.empty(len(points))
    for i in range(0, len(points), _CHUNK):
        p = points[i:i + _CHUNK, None, :]
        s = np.clip(((p - a) * ab).sum(axis=2) / ab2, 0.0, 1.0)
        d = p - (a + s[..., None] * ab)
        out[i:i + _CHUNK] = np.sqrt((d ** 2).sum(axis=2).min(axis=1))
    return out


def thermal_domain(static: StaticMesh, machine: RadialSRMParams) -> ThermalDomain:
    names = static.region_names
    kept = np.array([n not in EXCLUDED_REGIONS for n in names])
    stator_elements = np.flatnonzero(kept[static.stator.region_ids])
    rotor_elements = np.flatnonzero(kept[static.rotor.region_ids])

    def compact(part, rows):
        tri = part.triangles[rows]
        used = np.unique(tri)
        return part.nodes[used], np.searchsorted(used, tri)

    s_nodes, s_tri = compact(static.stator, stator_elements)
    r_nodes, r_tri = compact(static.rotor, rotor_elements)
    nodes = np.vstack([s_nodes, r_nodes])
    triangles = np.vstack([s_tri, r_tri + len(s_nodes)])

    region = np.concatenate([static.stator.region_ids[stator_elements], static.rotor.region_ids[rotor_elements]])
    kind = np.array([static.region_kind[n] for n in names])[region]
    ns = len(stator_elements)

    # slot_air touching both a coil and the stator iron within the liner band is the liner
    slot = np.flatnonzero(np.array(names)[region] == "slot_air")
    if len(slot):
        reach = machine.slot_liner_thickness + 2 * machine.stator_fillet_radius
        centroid = nodes[triangles[slot]].mean(axis=1)
        near = np.ones(len(slot), dtype=bool)
        for k in ("coil", "stator_iron"):
            e = boundary_edges(triangles[:ns][kind[:ns] == k])
            near &= distance_to_segments(centroid, nodes[e[:, 0]], nodes[e[:, 1]]) <= reach
        kind[slot[near]] = "liner"

    coil_elements = {n: np.flatnonzero(region == i) for i, n in enumerate(names) if static.region_kind[n] == "coil"}

    s_edges = boundary_edges(s_tri)
    r = machine.stator_outer_radius * (1 - 1e-6)
    outer = (np.hypot(*s_nodes[s_edges].transpose(2, 0, 1)) >= r).all(axis=1)
    return ThermalDomain(nodes, triangles, kind.astype(str), stator_elements, rotor_elements, coil_elements,
                         s_edges[outer], s_edges[~outer], boundary_edges(r_tri) + len(s_nodes))
