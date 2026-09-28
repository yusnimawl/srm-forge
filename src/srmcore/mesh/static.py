"""Mesh the stator part and the rotor part once (rotor at angle 0). The band is built later per angle."""
import math
from dataclasses import dataclass

import gmsh
import numpy as np

from ..geometry.build import GeometryModel, build_machine_geometry
from ..geometry.session import gmsh_model
from ..model.design import Design
from ..model.errors import ValidationIssue
from ..model.validator import require_valid
from .settings import ResolvedMeshSettings, resolve_mesh_settings
from .sizing import SizeField

TRIANGLE = 2
LINE = 1


@dataclass(frozen=True)
class MeshPart:
    nodes: np.ndarray
    triangles: np.ndarray
    region_ids: np.ndarray


@dataclass(frozen=True)
class StaticMesh:
    region_names: tuple[str, ...]
    stator: MeshPart
    rotor: MeshPart
    stator_ring: np.ndarray
    rotor_ring: np.ndarray
    outer_edges: np.ndarray
    band_inner_radius: float
    band_outer_radius: float
    settings: ResolvedMeshSettings
    warnings: tuple[ValidationIssue, ...]


def orient_ccw(nodes: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    p = nodes[triangles]
    signed = ((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
              - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))
    out = triangles.copy()
    flip = signed < 0
    out[flip, 1], out[flip, 2] = triangles[flip, 2], triangles[flip, 1]
    return out


def _apply_mesh_options(geom: GeometryModel, resolved: ResolvedMeshSettings) -> None:
    opt = gmsh.option.setNumber
    opt("Mesh.MeshSizeExtendFromBoundary", 0)
    opt("Mesh.MeshSizeFromPoints", 0)
    opt("Mesh.MeshSizeFromCurvature", 0)
    opt("Mesh.Algorithm", 6)
    opt("Mesh.ElementOrder", 1)
    max_size = max(resolved.region_sizes.values())
    opt("Mesh.MeshSizeMax", max_size)
    for curve in (geom.band_inner_curve, geom.band_outer_curve):
        gmsh.model.mesh.setTransfiniteCurve(curve, resolved.band_divisions + 1)

    surface_size = {t: resolved.region_sizes[geom.region_size_key[name]]
                    for name, tags in geom.region_surfaces.items() for t in tags}
    curve_size: dict[int, float] = {}
    for _, c in gmsh.model.getEntities(1):
        up, _ = gmsh.model.getAdjacencies(1, c)
        curve_size[c] = min((surface_size[s] for s in up if s in surface_size), default=max_size)
    point_size: dict[int, float] = {}
    for _, q in gmsh.model.getEntities(0):
        up, _ = gmsh.model.getAdjacencies(0, q)
        point_size[q] = min((curve_size[c] for c in up if c in curve_size), default=max_size)
    by_dim = {0: point_size, 1: curve_size, 2: surface_size}
    field = SizeField([(geom.refinement_points[tag], size, growth)
                       for tag, (size, growth) in resolved.refinement.items() if tag in geom.refinement_points])

    def callback(dim: int, tag: int, x: float, y: float, z: float, lc: float) -> float:
        return field(x, y, by_dim.get(dim, {}).get(tag, max_size))

    gmsh.model.mesh.setSizeCallback(callback)


def _all_nodes() -> tuple[np.ndarray, np.ndarray]:
    tags, coords, _ = gmsh.model.mesh.getNodes()
    tags = np.asarray(tags, dtype=np.int64)
    order = np.argsort(tags)
    return tags[order], np.asarray(coords, dtype=float).reshape(-1, 3)[order, :2]


def _extract_part(geom: GeometryModel, region_names: tuple[str, ...], part: str,
                  sorted_tags: np.ndarray, sorted_xy: np.ndarray) -> tuple[MeshPart, np.ndarray]:
    tri_blocks, id_blocks = [], []
    for rid, name in enumerate(region_names):
        if geom.region_part[name] != part:
            continue
        for surface in geom.region_surfaces[name]:
            types, _, node_tags = gmsh.model.mesh.getElements(2, surface)
            for etype, tags in zip(types, node_tags):
                if etype != TRIANGLE:
                    raise RuntimeError(f"unexpected element type {etype} in region {name}")
                block = np.asarray(tags, dtype=np.int64).reshape(-1, 3)
                tri_blocks.append(block)
                id_blocks.append(np.full(len(block), rid, dtype=np.int32))
    tri_tags = np.vstack(tri_blocks)
    used = np.unique(tri_tags)
    nodes = sorted_xy[np.searchsorted(sorted_tags, used)].copy()
    triangles = orient_ccw(nodes, np.searchsorted(used, tri_tags).astype(np.int64))
    return MeshPart(nodes, triangles, np.concatenate(id_blocks)), used


def _local(used: np.ndarray, tags: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(used, tags)
    if np.any(idx >= len(used)) or np.any(used[idx] != tags):
        raise RuntimeError("boundary node not found in its part")
    return idx


def _ring(curve: int, used: np.ndarray, nodes: np.ndarray, n: int) -> np.ndarray:
    tags, _, _ = gmsh.model.mesh.getNodes(1, curve, includeBoundary=True)
    idx = _local(used, np.unique(np.asarray(tags, dtype=np.int64)))
    angles = np.mod(np.arctan2(nodes[idx, 1], nodes[idx, 0]), 2 * math.pi)
    idx = idx[np.argsort(angles)]
    if len(idx) != n:
        raise RuntimeError(f"band ring has {len(idx)} nodes, expected {n}")
    return idx


def _edges(curve: int, used: np.ndarray) -> np.ndarray:
    types, _, node_tags = gmsh.model.mesh.getElements(1, curve)
    blocks = [np.asarray(t, dtype=np.int64).reshape(-1, 2) for e, t in zip(types, node_tags) if e == LINE]
    return _local(used, np.vstack(blocks).ravel()).reshape(-1, 2)


def build_static_mesh(design: Design) -> StaticMesh:
    warnings = require_valid(design)
    p = design.machine
    resolved = resolve_mesh_settings(p, design.mesh)
    with gmsh_model():
        geom = build_machine_geometry(p, feature_step=resolved.gap_size)
        _apply_mesh_options(geom, resolved)
        try:
            gmsh.model.mesh.generate(2)
        finally:
            gmsh.model.mesh.removeSizeCallback()
        region_names = tuple(sorted(geom.region_surfaces))
        sorted_tags, sorted_xy = _all_nodes()
        stator, stator_used = _extract_part(geom, region_names, "stator", sorted_tags, sorted_xy)
        rotor, rotor_used = _extract_part(geom, region_names, "rotor", sorted_tags, sorted_xy)
        n = resolved.band_divisions
        stator_ring = _ring(geom.band_outer_curve, stator_used, stator.nodes, n)
        rotor_ring = _ring(geom.band_inner_curve, rotor_used, rotor.nodes, n)
        outer_edges = _edges(geom.stator_outer_curve, stator_used)
    return StaticMesh(
        region_names=region_names, stator=stator, rotor=rotor,
        stator_ring=stator_ring, rotor_ring=rotor_ring, outer_edges=outer_edges,
        band_inner_radius=p.band_inner_radius, band_outer_radius=p.band_outer_radius,
        settings=resolved, warnings=tuple(warnings),
    )
