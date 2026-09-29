import numpy as np
from scipy.spatial import Delaunay

from srmcore.physics.fem import element_flux_density, p1_gradients, secant_residual


def _mesh():
    rng = np.random.default_rng(0)
    pts = rng.random((40, 2))
    return pts, Delaunay(pts).simplices


def test_gradients_of_a_linear_field_and_agreement_with_flux_density():
    pts, tri = _mesh()
    grads, areas = p1_gradients(pts, tri)
    a = 3.0 * pts[:, 0] - 5.0 * pts[:, 1]
    ga = np.einsum("eik,ei->ek", grads, a[tri])
    assert np.allclose(ga, [3.0, -5.0])
    assert np.allclose(element_flux_density(pts, tri, a), np.column_stack([ga[:, 1], -ga[:, 0]]))
    assert np.all(areas > 0)


def test_secant_residual_equals_the_dense_stiffness_product():
    pts, tri = _mesh()
    rng = np.random.default_rng(1)
    nu, a = rng.random(len(tri)) + 0.5, rng.random(len(pts))
    k = np.zeros((len(pts), len(pts)))
    for e, t in enumerate(tri):
        g, area = p1_gradients(pts, t[None])
        k[np.ix_(t, t)] += nu[e] * area[0] * g[0] @ g[0].T
    grads, areas = p1_gradients(pts, tri)
    assert np.allclose(secant_residual(grads, areas, tri, nu, a), k @ a, rtol=1e-12, atol=1e-13)
