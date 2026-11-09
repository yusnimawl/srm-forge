"""Cross-wire conductivity of a potted winding (docs/r5-sources.md section 6.8, check in section 8)."""

# Milton xi by copper volume fraction. Marquez-Fernandez 2018 gives it for 0.37 only
# (docs/r5-sources.md 6.8); no other fill has a cited value.
MILTON_XI = {0.37: 0.324}

# Copper along the wire as used by Marquez-Fernandez 2018 (docs/r5-sources.md 6.6 and 8).
K_CU = 300.0


def hashin_shtrikman_lower(fill: float, k_copper: float, k_matrix: float) -> float:
    """Hashin-Shtrikman lower bound, Eq. (5) of Marquez-Fernandez 2018 (docs/r5-sources.md 6.8), W/(m K)."""
    t1, t2 = fill, 1.0 - fill
    l1, l2 = k_copper, k_matrix
    return l2 * ((1 + t1) * l1 + (1 - t2) * l2) / ((1 - t1) * l1 + (1 + t2) * l2)


def milton_k(fill: float, k_copper: float, k_matrix: float, xi: float) -> float:
    """Milton, Eq. (6) of Marquez-Fernandez 2018 (docs/r5-sources.md 6.8), W/(m K).

    xi depends on the fill factor; only MILTON_XI has a cited value (0.37).
    """
    t1, t2 = fill, 1.0 - fill
    l1, l2 = k_copper, k_matrix
    d = t1 * xi * (l1 - l2) ** 2
    num = (t1 * l1 + t2 * l2 + l1) * (l1 + l2) - d
    den = (t2 * l1 + t1 * l2 + l2) * (l1 + l2) - d
    return l2 * num / den
