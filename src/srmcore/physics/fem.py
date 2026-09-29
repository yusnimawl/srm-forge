"""Linear-triangle (P1) kinematics shared by every solver adapter and by post-processing."""
import numpy as np


def triangle_areas(nodes: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    a, b, c = nodes[triangles[:, 0]], nodes[triangles[:, 1]], nodes[triangles[:, 2]]
    # Explicit 2D cross product: numpy >= 2 rejects np.cross on 2-vectors.
    return 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))


def element_flux_density(nodes: np.ndarray, triangles: np.ndarray, a: np.ndarray) -> np.ndarray:
    """B = curl(A ẑ) = (∂A/∂y, -∂A/∂x), constant on each P1 triangle. Returns (n_elements, 2)."""
    x, y, av = nodes[triangles, 0], nodes[triangles, 1], a[triangles]
    det = (x[:, 1] - x[:, 0]) * (y[:, 2] - y[:, 0]) - (x[:, 2] - x[:, 0]) * (y[:, 1] - y[:, 0])
    dadx = ((y[:, 1] - y[:, 2]) * av[:, 0] + (y[:, 2] - y[:, 0]) * av[:, 1] + (y[:, 0] - y[:, 1]) * av[:, 2]) / det
    dady = ((x[:, 2] - x[:, 1]) * av[:, 0] + (x[:, 0] - x[:, 2]) * av[:, 1] + (x[:, 1] - x[:, 0]) * av[:, 2]) / det
    return np.column_stack([dady, -dadx])
