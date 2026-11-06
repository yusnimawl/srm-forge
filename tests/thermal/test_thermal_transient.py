from dataclasses import replace

import numpy as np
import pytest

from srmcore.thermal.model import (EdgeLink, Lump, LumpLink, Temperatures, ThermalLoad, ThermalModelError,
                                   ThermalProblem, ThermalRunaway)
from srmcore.thermal.solve import ThermalSolver
from test_thermal_steady import domain, rect, uniform


def prob(dom, k=1.0, cap=1.0, depth=1.0, lumps=(), links=()):
    m = len(dom.triangles)
    return ThermalProblem(dom, np.full(m, k), np.full(m, cap), depth, tuple(lumps), tuple(links))


def rc_solver(c=5.0, g=2.0):
    nodes, tri = rect(1e-3, 1e-3, 1, 1)
    # the plate is a negligible adiabatic island; the physics is the lump pair
    p = prob(domain(nodes, tri), cap=1e-9, lumps=[Lump("c", capacity=c), Lump("f", fixed_c=20.0)],
             links=[LumpLink("c", "f", g)])
    return ThermalSolver(p), len(tri), len(nodes)


def rc_error(n_steps):
    s, m, n = rc_solver()
    tau, p_w = 5.0 / 2.0, 10.0
    start = Temperatures(np.full(n, 20.0), {"c": 20.0, "f": 20.0})
    tr = s.transient(start, lambda _t: ThermalLoad(np.zeros(m), {"c": p_w}), tau, n_steps)
    exact = 20.0 + p_w / 2.0 * (1 - np.exp(-1.0))
    return abs(tr.final.lumps["c"] - exact) / (p_w / 2.0)


def test_lumped_rc_step():
    assert rc_error(200) < 5e-3


def test_time_step_is_first_order():
    assert 1.8 < rc_error(50) / rc_error(100) < 2.2


def test_adiabatic_element_heating():
    nodes, tri = rect(0.02, 0.01, 6, 3)
    rho_c, q, t_end = 4e6, 1e6, 30.0
    s = ThermalSolver(prob(domain(nodes, tri), cap=rho_c))
    tr = s.transient(Temperatures(np.full(len(nodes), 25.0), {}), uniform(q, len(tri)), t_end, 7)
    assert np.allclose(tr.final.field, 25.0 + q * t_end / rho_c, rtol=1e-9, atol=0)
    assert tr.times_s.shape == tr.hot_spot_c.shape == (8,)


def test_transient_settles_on_steady():
    nodes, tri = rect(0.04, 0.01, 16, 2)
    ends = [np.flatnonzero(np.isclose(nodes[:, 0], x)) for x in (0.0, 0.04)]
    links = [EdgeLink(np.stack([e[:-1], e[1:]], 1), "air", 200.0) for e in ends]
    s = ThermalSolver(prob(domain(nodes, tri), k=3.0, cap=3e6, depth=0.1, lumps=[Lump("air", fixed_c=25.0)],
                           links=links))
    load = uniform(2e5, len(tri))
    start = Temperatures(np.full(len(nodes), 25.0), {"air": 25.0})
    tr = s.transient(start, load, 2e5, 40)
    steady = s.steady(load)
    assert np.abs(tr.final.field - steady.field).max() < 0.1


def hot_problem(coil):
    nodes, tri = rect(0.02, 0.01, 4, 2)
    dom = replace(domain(nodes, tri), coil_elements=coil)
    lumps = [Lump("end", capacity=1.0, hot_spot=True), Lump("cool", capacity=1.0)]
    return ThermalSolver(prob(dom, lumps=lumps)), len(nodes)


def test_hot_spot_finds_end_winding():
    s, n = hot_problem({"coil_A1+": np.array([0, 1])})
    f = np.full(n, 50.0)
    t = Temperatures(f, {"end": 90.0, "cool": 200.0})
    hs = s.hot_spot(t)
    assert (hs.temperature_c, hs.location) == (90.0, "end")


def test_hot_spot_finds_coil_region():
    s, n = hot_problem({"coil_A1+": np.array([0]), "coil_A1-": np.array([5])})
    tri = s.problem.domain.triangles
    f = np.full(n, 30.0)
    f[tri[5][1]] = 70.0
    f[0] = 500.0   # iron node outside the coil elements does not count
    f[tri[0]] = np.minimum(f[tri[0]], 60.0)
    t = Temperatures(f, {"end": 40.0, "cool": 200.0})
    hs = s.hot_spot(t)
    assert (hs.temperature_c, hs.location) == (70.0, "coil_A1-")


def test_hot_spot_needs_a_target():
    nodes, tri = rect(0.02, 0.01, 2, 1)
    s = ThermalSolver(prob(domain(nodes, tri)))
    with pytest.raises(ThermalModelError, match="hot spot"):
        s.hot_spot(Temperatures(np.zeros(len(nodes)), {}))


def test_transient_rejects_bad_steps_and_names_capacity_free_orphan():
    s, m, n = rc_solver()
    start = Temperatures(np.full(n, 20.0), {"c": 20.0, "f": 20.0})
    load = lambda _t: ThermalLoad(np.zeros(m))
    with pytest.raises(ThermalModelError):
        s.transient(start, load, 0.0, 10)
    with pytest.raises(ThermalModelError):
        s.transient(start, load, 1.0, 0)
    nodes, tri = rect(1e-3, 1e-3, 1, 1)
    p = prob(domain(nodes, tri), cap=1e-9, lumps=[Lump("f", fixed_c=20.0), Lump("orphan")])
    with pytest.raises(ThermalModelError, match="orphan"):
        ThermalSolver(p).transient(Temperatures(np.full(len(nodes), 20.0), {"f": 20.0, "orphan": 20.0}), load,
                                   1.0, 5)


def test_transient_runaway():
    nodes, tri = rect(0.02, 0.01, 2, 1)
    s = ThermalSolver(prob(domain(nodes, tri), cap=1e3))
    with pytest.raises(ThermalRunaway):
        s.transient(Temperatures(np.zeros(len(nodes)), {}), uniform(1e9, len(tri)), 10.0, 5)
