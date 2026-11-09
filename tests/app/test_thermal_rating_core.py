import math

import numpy as np
import pytest

from srmapp.thermal import SpeedRating, rate_speed
from srmcore.thermal.domain import ThermalDomain
from srmcore.thermal.model import EdgeLink, Lump, LumpLink, ThermalLoad, ThermalProblem, ThermalRunaway
from srmcore.thermal.solve import ThermalSolver

T_COOL, G = 40.0, 2.0          # coolant degC, hot-lump to coolant conductance W/K
LIMIT, A_LOSS = 140.0, 5.0     # degC, loss W per (N m)^2


def make_solver(cap=1.0):
    """A plate (stator and rotor halves, no load, tied to the coolant) plus a hot-spot lump linked to the coolant."""
    nodes = np.array([[0, 0], [1e-2, 0], [2e-2, 0], [0, 1e-2], [1e-2, 1e-2], [2e-2, 1e-2]], float)
    tri = np.array([[0, 1, 4], [0, 4, 3], [1, 2, 5], [1, 5, 4]])
    kind = np.array(["stator_iron", "stator_iron", "rotor_iron", "rotor_iron"])
    edges = np.array([[0, 1], [1, 2]])
    dom = ThermalDomain(nodes, tri, kind, np.array([0, 1]), np.array([2, 3]), {}, np.zeros((0, 2), int),
                        np.zeros((0, 2), int), np.zeros((0, 2), int))
    m = len(tri)
    p = ThermalProblem(dom, np.full(m, 20.0), np.full(m, 1e6), 0.1,
                       (Lump("hot", capacity=cap, hot_spot=True), Lump("cool", fixed_c=T_COOL)),
                       (LumpLink("hot", "cool", G), EdgeLink(edges, "cool", 100.0)))
    return ThermalSolver(p)


def loss_fn(power):
    return lambda _t: ThermalLoad(np.zeros(4), {"hot": power})


def quad(torque):
    return loss_fn(A_LOSS * torque ** 2)


def rate(solver=None, load_at=quad, envelope=20.0, limit=LIMIT, peak_s=10.0):
    solver = solver or make_solver()
    return rate_speed(1000.0, envelope, limit, peak_s, lambda: solver, load_at)


def test_continuous_hits_limit():
    r = rate()
    assert isinstance(r, SpeedRating)
    assert abs(r.continuous_hot_spot.temperature_c - LIMIT) < 0.5 or r.continuous_nm > 0.99 * 20.0


def test_matches_closed_form():
    # R_th = 1 / G is the lump-to-coolant link, read from the network, not from a solve
    exact = math.sqrt((LIMIT - T_COOL) * G / A_LOSS)
    assert exact < 20.0
    assert rate().continuous_nm == pytest.approx(exact, rel=0.01)


def test_peak_at_least_continuous():
    r = rate(make_solver(cap=200.0))
    assert r.peak_nm >= r.continuous_nm > 0
    assert r.peak_hot_spot.temperature_c <= LIMIT + 0.5


def test_peak_capped_by_envelope():
    r = rate(make_solver(cap=1e9))
    assert r.peak_nm == 20.0 and r.continuous_nm < 20.0


def test_envelope_within_limit():
    r = rate(envelope=3.0)
    assert r.continuous_nm == 3.0 and r.peak_nm == 3.0


def test_coolant_above_limit():
    r = rate(limit=T_COOL - 5.0)
    assert r.continuous_nm == 0.0 and r.peak_nm == 0.0 and "no steady state" in r.note


def test_runaway_is_infeasible():
    t_run = 6.0

    def load_at(t):
        if t > t_run:
            def boom(_t):
                raise ThermalRunaway("runaway")
            return boom
        return quad(t)

    r = rate(load_at=load_at)
    assert 0 < r.continuous_nm <= t_run


def test_unreachable_torque():
    t_star = 4.0
    r = rate(load_at=lambda t: quad(t) if t <= t_star else None)
    assert 0 < r.continuous_nm <= t_star and r.peak_nm <= t_star


def test_transient_steps_doubled():
    r = rate(make_solver(cap=1e9), peak_s=2.0)
    assert r.peak_nm == 20.0 and r.transient_steps >= 50
    assert r.n_evaluations <= 24


def test_zone_temperatures():
    r = rate()
    assert r.rotor_c == pytest.approx(T_COOL, abs=1.0) and r.bore_c == pytest.approx(T_COOL, abs=1.0)
