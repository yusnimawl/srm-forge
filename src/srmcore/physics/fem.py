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


def p1_gradients(nodes: np.ndarray, triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Shape-function gradients (n_elements, 3, 2) and areas (n_elements,) of P1 triangles, either orientation."""
    x, y = nodes[triangles, 0], nodes[triangles, 1]
    det = (x[:, 1] - x[:, 0]) * (y[:, 2] - y[:, 0]) - (x[:, 2] - x[:, 0]) * (y[:, 1] - y[:, 0])
    gx = np.stack([y[:, 1] - y[:, 2], y[:, 2] - y[:, 0], y[:, 0] - y[:, 1]], axis=1) / det[:, None]
    gy = np.stack([x[:, 2] - x[:, 1], x[:, 0] - x[:, 2], x[:, 1] - x[:, 0]], axis=1) / det[:, None]
    return np.stack([gx, gy], axis=2), 0.5 * np.abs(det)


def secant_residual(grads: np.ndarray, areas: np.ndarray, triangles: np.ndarray, nu: np.ndarray,
                    a: np.ndarray) -> np.ndarray:
    """K(ν)·A per unit depth for element-constant ν: Σ_e ν_e·area_e·(∇φ_i · ∇A_e), scattered to the nodes."""
    ga = np.einsum("eik,ei->ek", grads, a[triangles])
    contribution = (nu * areas)[:, None] * np.einsum("eik,ek->ei", grads, ga)
    return np.bincount(triangles.ravel(), weights=contribution.ravel(), minlength=len(a))
