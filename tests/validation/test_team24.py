"""TEAM Problem 24 (spec §2.3, §8.2 suite 5): the 2D magnetostatic model against the published
measurements. The model omits 3D end flux and eddy currents, so the checks are regression pins, signs
and a sanity band, not a pass/fail tolerance against the measurement (docs/m5b-team24-results.md)."""
import numpy as np
import pytest
from scipy.interpolate import PchipInterpolator

import team24_fixture as t24
from srmcore.materials.laws import MU0


def test_bh_table_reading():
    h, b = np.array(t24.H_TABLE), np.array(t24.B_TABLE)
    assert len(h) == 17
    assert h[1] == pytest.approx(4000.0) and h[-1] == pytest.approx(240200.0)
    j = b - MU0 * h
    assert np.all(np.diff(j) > 0)
    assert t24.ASSUMED_JS > j[-1]
    t24.steel_law()          # process_bh accepts the table


def test_table_ii_voltage():
    assert t24.table_ii_voltage(0.0) == 0.0
    assert t24.table_ii_voltage(0.0002) == pytest.approx(23.60)
    assert t24.table_ii_voltage(0.5) == pytest.approx(23.10)


def test_current_rise_linear_inductor():
    # psi = L i with constant V: i(t) = V/R (1 - exp(-R t / L))
    inductance, r, v = 0.05, 3.0, 23.1
    grid = np.linspace(0.0, 10.0, 11)
    times = np.array([0.002, 0.01, 0.05, 0.2])
    got = t24.current_rise(PchipInterpolator(grid, inductance * grid), times, resistance=r, voltage=v)
    want = v / r * (1 - np.exp(-r * times / inductance))
    assert got == pytest.approx(want, rel=1e-5)


def test_current_rise_callable_voltage():
    grid = np.linspace(0.0, 10.0, 11)
    psi = PchipInterpolator(grid, 0.05 * grid)
    times = np.array([0.01, 0.1])
    const = t24.current_rise(psi, times, voltage=23.1)
    measured = t24.current_rise(psi, times, voltage=t24.table_ii_voltage)
    assert np.all(measured > const)          # Table II overshoots 23.1 V early on
    assert np.all(np.diff(measured) > 0)
