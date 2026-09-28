"""Triangle and mesh quality metrics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from ..model.errors import MeshRejected
from .settings import ResolvedMeshSettings

if TYPE_CHECKING:
    from .machine import MachineMesh


def triangle_quality(nodes: np.ndarray, triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    p = nodes[triangles]
    a = np.linalg.norm(p[:, 1] - p[:, 2], axis=1)
    b = np.linalg.norm(p[:, 0] - p[:, 2], axis=1)
    c = np.linalg.norm(p[:, 0] - p[:, 1], axis=1)
    ang_a = np.arccos(np.clip((b * b + c * c - a * a) / (2 * b * c), -1.0, 1.0))
    ang_b = np.arccos(np.clip((a * a + c * c - b * b) / (2 * a * c), -1.0, 1.0))
    ang_c = np.pi - ang_a - ang_b
    min_angle = np.degrees(np.minimum(np.minimum(ang_a, ang_b), ang_c))
    area = 0.5 * np.abs((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                        - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))
    inradius = area / (0.5 * (a + b + c))
    aspect = np.maximum(np.maximum(a, b), c) / (2 * np.sqrt(3) * inradius)
    return min_angle, aspect


@dataclass(frozen=True)
class MeshQualityReport:
    n_nodes: int
    n_triangles: int
    min_angle_deg: float
    max_aspect_ratio: float
    band_min_angle_deg: float
    triangles_per_region: dict[str, int]


def quality_report(mesh: MachineMesh) -> MeshQualityReport:
    min_angle, aspect = triangle_quality(mesh.nodes, mesh.triangles)
    in_band = np.zeros(len(mesh.triangles), dtype=bool)
    in_band[mesh.band_rows] = True
    counts = np.bincount(mesh.region_ids, minlength=len(mesh.region_names))
    return MeshQualityReport(
        n_nodes=len(mesh.nodes), n_triangles=len(mesh.triangles),
        min_angle_deg=float(min_angle[~in_band].min()), max_aspect_ratio=float(aspect[~in_band].max()),
        band_min_angle_deg=float(min_angle[in_band].min()),
        triangles_per_region={name: int(counts[i]) for i, name in enumerate(mesh.region_names)},
    )


def check_quality(report: MeshQualityReport, settings: ResolvedMeshSettings) -> None:
    reasons = []
    if report.min_angle_deg < settings.min_angle_deg:
        reasons.append(f"min angle {report.min_angle_deg:.2f}° < {settings.min_angle_deg}°")
    if report.max_aspect_ratio > settings.max_aspect_ratio:
        reasons.append(f"aspect ratio {report.max_aspect_ratio:.2f} > {settings.max_aspect_ratio}")
    if report.band_min_angle_deg < settings.band_min_angle_deg:
        reasons.append(f"band min angle {report.band_min_angle_deg:.2f}° < {settings.band_min_angle_deg}°")
    if reasons:
        raise MeshRejected(reasons, report)
