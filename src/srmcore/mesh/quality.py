"""Triangle and mesh quality metrics."""
import numpy as np


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
