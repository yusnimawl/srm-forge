import numpy as np
import pytest

from srmcore.thermal.domain import ThermalDomain, boundary_edges
from srmcore.thermal.model import (AreaLink, EdgeLink, Lump, LumpLink, Temperatures, ThermalLoad, ThermalModelError,
                                   ThermalProblem, ThermalRunaway)
from srmcore.thermal.solve import ThermalSolver


def domain(nodes, tri, n_stator=None):
    ns = len(tri) if n_stator is None else n_stator
    idx = np.arange(len(tri))
    return ThermalDomain(nodes, tri, np.array(["stator_iron"] * len(tri)), idx[:ns], idx[ns:], {},
                         np.zeros((0, 2), int), np.zeros((0, 2), int), np.zeros((0, 2), int))


def grid_tri(nx, ny):
    """Triangles of an (nx+1) x (ny+1) node lattice, node index i*(ny+1)+j."""
    i, j = np.meshgrid(np.arange(nx), np.arange(ny), indexing="ij")
    a = (i * (ny + 1) + j).ravel()
    b, c, d = a + ny + 1, a + ny + 2, a + 1
    return np.vstack([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])


def rect(lx, ly, nx, ny, x0=0.0, y0=0.0):
    x, y = np.meshgrid(np.linspace(x0, x0 + lx, nx + 1), np.linspace(y0, y0 + ly, ny + 1), indexing="ij")
    return np.stack([x.ravel(), y.ravel()], 1), grid_tri(nx, ny)


def problem(dom, k=1.0, depth=1.0, lumps=(), links=()):
    m = len(dom.triangles)
    return ThermalProblem(dom, np.full(m, k), np.full(m, 1.0), depth, tuple(lumps), tuple(links))


def uniform(q, m):
    return lambda _t: ThermalLoad(np.full(m, q))


def test_slab_uniform_heat_robin_ends():
    a, k, q, h, tinf = 0.02, 3.0, 5e5, 200.0, 25.0
    nodes, tri = rect(2 * a, 0.01, 20, 2, x0=-a)
    dom = domain(nodes, tri)
    ends = [np.flatnonzero(np.isclose(nodes[:, 0], s * a)) for s in (-1, 1)]
    links = [EdgeLink(np.stack([e[:-1], e[1:]], 1), "air", h) for e in ends]
    sol = ThermalSolver(problem(dom, k, 0.1, [Lump("air", fixed_c=tinf)], links))
    t = sol.steady(uniform(q, len(tri)))
    x = nodes[:, 0]
    exact = tinf + q * a / h + q * (a ** 2 - x ** 2) / (2 * k)
    scale = exact.max() - tinf
    # the diagonal split gives the end-column corner nodes unequal element-constant loads (2 and 1 triangles
    # where 1D needs 1.5 each), which tilts the ends antisymmetrically in y; the centre row is nodally exact
    centre = np.isclose(nodes[:, 1], 0.005)
    err = np.abs(t.field - exact)[centre].max() / scale
    print("slab centre row", err, "all nodes", np.abs(t.field - exact).max() / scale)
    assert err < 1e-9
    cols = (t.field - exact).reshape(21, 3).mean(axis=1)
    assert np.abs(cols).max() / scale < 1e-9


def test_annulus_uniform_heat():
    a, b, k, q, tb = 0.01, 0.03, 20.0, 1e6, 40.0
    nr, nt = 30, 96
    r = np.linspace(a, b, nr + 1)
    th = np.linspace(0, 2 * np.pi, nt, endpoint=False)
    nodes = np.stack([(r[:, None] * np.cos(th)).ravel(), (r[:, None] * np.sin(th)).ravel()], 1)
    id_ = lambda i, j: i * nt + j % nt
    tri = []
    for i in range(nr):
        for j in range(nt):
            tri += [[id_(i, j), id_(i + 1, j), id_(i + 1, j + 1)], [id_(i, j), id_(i + 1, j + 1), id_(i, j + 1)]]
    tri = np.array(tri)
    outer = np.array([[id_(nr, j), id_(nr, j + 1)] for j in range(nt)])
    sol = ThermalSolver(problem(domain(nodes, tri), k, 1.0, [Lump("tb", fixed_c=tb)], [EdgeLink(outer, "tb", 1e9)]))
    t = sol.steady(uniform(q, len(tri)))
    rr = np.hypot(*nodes.T)
    exact = tb + q * (b ** 2 - rr ** 2) / (4 * k) + q * a ** 2 * np.log(rr / b) / (2 * k)
    err = np.abs(t.field - exact).max() / (exact.max() - tb)
    print("annulus", err)
    assert err < 1e-3


def test_manufactured_solution_second_order():
    k = 2.0

    def l2(n):
        nodes, tri = rect(1, 1, n, n)
        dom = domain(nodes, tri)
        e = boundary_edges(tri)
        sol = ThermalSolver(problem(dom, k, 1.0, [Lump("z", fixed_c=0.0)], [EdgeLink(e, "z", 1e9)]))
        c = nodes[tri].mean(axis=1)
        q = 2 * np.pi ** 2 * k * np.sin(np.pi * c[:, 0]) * np.sin(np.pi * c[:, 1])
        t = sol.steady(lambda _t: ThermalLoad(q))
        err = t.field - np.sin(np.pi * nodes[:, 0]) * np.sin(np.pi * nodes[:, 1])
        area = 0.5 / n ** 2
        return np.sqrt(area * (err ** 2).sum())

    e1, e2 = l2(8), l2(16)
    print("mms", e1, e2, e1 / e2)
    assert e1 / e2 > 3


def two_lump_case():
    nodes, tri = rect(0.1, 0.05, 6, 3)
    dom = domain(nodes, tri)
    left = np.flatnonzero(np.isclose(nodes[:, 0], 0))
    edges = np.stack([left[:-1], left[1:]], 1)
    lumps = [Lump("cool", fixed_c=30.0), Lump("mid")]
    links = [EdgeLink(edges, "cool", 500.0), AreaLink(np.arange(10), "mid", 80.0), LumpLink("mid", "cool", 0.7)]
    return dom, lumps, links


def test_energy_balance():
    dom, lumps, links = two_lump_case()
    sol = ThermalSolver(problem(dom, 5.0, 0.2, lumps, links))
    q = np.linspace(1e5, 4e5, len(dom.triangles))
    load = ThermalLoad(q, {"mid": 12.0})
    t = sol.steady(lambda _t: load)
    p = dom.nodes[dom.triangles]
    area = 0.5 * np.abs((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                        - (p[:, 1, 1] - p[:, 0, 1]) * (p[:, 2, 0] - p[:, 0, 0]))
    total = (q * area).sum() * 0.2 + 12.0
    got = sum(sol.heat_to_fixed(t).values())
    print("balance", abs(got - total) / total)
    assert got == pytest.approx(total, rel=1e-9)


def test_depth_scales_conduction_and_edges_alike():
    nodes, tri = rect(0.1, 0.05, 6, 3)
    dom = domain(nodes, tri)
    left = np.flatnonzero(np.isclose(nodes[:, 0], 0))
    link = EdgeLink(np.stack([left[:-1], left[1:]], 1), "c", 500.0)
    out = []
    for depth in (0.1, 0.2):
        sol = ThermalSolver(problem(dom, 5.0, depth, [Lump("c", fixed_c=30.0)], [link]))
        out.append(sol.steady(uniform(3e5, len(tri))).field)
    assert np.abs(out[0] - out[1]).max() < 1e-9


def lone_triangle_case(g_link):
    nodes, tri = rect(0.01, 0.01, 1, 1)
    dom = domain(nodes, tri)
    lumps = [Lump("f", fixed_c=20.0), Lump("x")]
    links = [AreaLink(np.arange(2), "x", 1e3), LumpLink("x", "f", g_link)]
    return ThermalSolver(problem(dom, 50.0, 1.0, lumps, links))


def test_temperature_dependent_load_converges():
    p0, alpha, g, tf = 10.0, 0.004, 0.5, 20.0
    t = lone_triangle_case(g).steady(
        lambda prev: ThermalLoad(np.zeros(2), {"x": p0 * (1 + alpha * (prev.lumps["x"] if prev else tf))}),
        tol_k=1e-9)
    assert t.lumps["x"] == pytest.approx((p0 + g * tf) / (g - alpha * p0), abs=1e-6)


def test_runaway_is_reported():
    p0, alpha = 10.0, 0.004
    with pytest.raises(ThermalRunaway):
        lone_triangle_case(0.02).steady(
            lambda prev: ThermalLoad(np.zeros(2), {"x": p0 * (1 + alpha * (prev.lumps["x"] if prev else 20.0))}))


def test_floating_rotor_refused():
    n1, t1 = rect(1, 1, 1, 1)
    n2, t2 = rect(1, 1, 1, 1, x0=3)
    dom = domain(np.vstack([n1, n2]), np.vstack([t1, t2 + 4]), n_stator=2)
    link = AreaLink(np.arange(2), "c", 10.0)
    sol = ThermalSolver(problem(dom, 1.0, 1.0, [Lump("c", fixed_c=0.0)], [link]))
    with pytest.raises(ThermalModelError, match="rotor"):
        sol.steady(uniform(1.0, 4))


def test_unknown_lump_refused():
    dom = domain(*rect(1, 1, 1, 1))
    with pytest.raises(ThermalModelError, match="ghost"):
        ThermalSolver(problem(dom, links=[AreaLink(np.arange(2), "ghost", 1.0)]))
    with pytest.raises(ThermalModelError):
        ThermalSolver(problem(dom, lumps=[Lump("a")], links=[LumpLink("a", "a", -1.0)]))
    with pytest.raises(ThermalModelError):
        ThermalSolver(problem(dom, k=-1.0))


def test_orphan_lump_named():
    dom = domain(*rect(1, 1, 1, 1))
    sol = ThermalSolver(problem(dom, lumps=[Lump("f", fixed_c=0.0), Lump("orphan")],
                                links=[AreaLink(np.arange(2), "f", 1.0)]))
    with pytest.raises(ThermalModelError, match="orphan"):
        sol.steady(uniform(1.0, 2))


def test_unconverged_iteration_raises():
    p0, alpha, tf = 10.0, 0.004, 20.0
    sol = lone_triangle_case(0.5)
    with pytest.raises(ThermalRunaway, match="iterations"):
        sol.steady(lambda prev: ThermalLoad(np.zeros(2), {"x": p0 * (1 + alpha * (prev.lumps["x"] if prev else tf))}),
                   tol_k=1e-9, max_iter=3)


@pytest.mark.parametrize("depth", [0.05, 0.2])
def test_area_link_block(depth):
    nodes, tri = rect(0.1, 0.05, 5, 3)
    dom = domain(nodes, tri)
    q, g, tf = 2e5, 700.0, 30.0
    sol = ThermalSolver(problem(dom, 5.0, depth, [Lump("f", fixed_c=tf)], [AreaLink(np.arange(len(tri)), "f", g)]))
    t = sol.steady(uniform(q, len(tri)))
    assert np.abs(t.field - (tf + q * depth / g)).max() < 1e-9


def test_link_quadratic_form_matches_exact_integrals():
    # T = 3 + 2x - y on the lump side L = 5: int h (T - L)^2 over the link, exact by hand per element/edge
    nodes, tri = rect(0.3, 0.2, 3, 2)
    dom = domain(nodes, tri)
    t_nodes = 3 + 2 * nodes[:, 0] - nodes[:, 1]
    lump_c = 5.0
    edges = np.array([[0, 1], [1, 2]])
    cases = [(AreaLink(np.arange(len(tri)), "l", 7.0), 1.0, None), (EdgeLink(edges, "l", 7.0), 0.4, edges)]
    for link, depth, e in cases:
        sol = ThermalSolver(problem(dom, 1.0, depth, [Lump("l")], [link]))
        # remove conduction: quadratic form of the link alone = full form - conduction form
        cond = ThermalSolver(problem(dom, 1.0, depth, [Lump("l")], [LumpLink("l", "l", 1e-30)]))
        x = np.concatenate([t_nodes, [lump_c]])
        got = x @ (sol._a - cond._a) @ x
        if e is None:
            p = nodes[tri]
            area = 0.5 * np.abs((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                                - (p[:, 1, 1] - p[:, 0, 1]) * (p[:, 2, 0] - p[:, 0, 0]))
            tt = t_nodes[tri]
            # int (T-L)^2 for linear T = A (mean(d)^2 + var-term): A/12 (sum d_i^2 + (sum d_i)^2)
            d = tt - lump_c
            want = 7.0 * (area / 12 * ((d ** 2).sum(1) + d.sum(1) ** 2)).sum()
        else:
            d = t_nodes[e] - lump_c
            length = np.hypot(*(nodes[e[:, 1]] - nodes[e[:, 0]]).T)
            want = 7.0 * depth * (length / 3 * (d[:, 0] ** 2 + d[:, 0] * d[:, 1] + d[:, 1] ** 2)).sum()
        assert got == pytest.approx(want, rel=1e-9)
