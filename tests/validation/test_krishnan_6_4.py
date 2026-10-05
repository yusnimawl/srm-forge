"""Krishnan/Materu 6/4 against its measurement (docs/m5d-krishnan-results.md). Pins the `full`-preset 2D
table and the end-winding inductance; regenerate the numbers with examples/krishnan_6_4_check.py."""
import numpy as np
import pytest

import krishnan_6_4 as k64
from srmcore.maps.end_winding import end_winding_inductance

pytestmark = pytest.mark.slow
pytest.importorskip("ngsolve")

FULL_2D = {"La": (0.85542, 0.13147, 0.06978), "Lu": (0.04568, 0.04596, 0.04568),
           "T_avg": (0.80119, 16.85075, 29.71777)}   # from the Step 2 output
L_END = {1.0: 3.86949e-3, 2.0: 7.73899e-3}            # H, from the Step 2 output


@pytest.fixture(scope="module")
def full_table():
    from srmcore.solvers.factory import make_solver
    return k64.table(k64.design(preset="full"), make_solver("ngsolve"))


def test_full_table_pinned(full_table):
    for q, want in FULL_2D.items():
        assert full_table[q] == pytest.approx(want, rel=1e-3)


def test_end_winding_pinned():
    for f, want in L_END.items():
        assert end_winding_inductance(k64.machine(), f) == pytest.approx(want, rel=1e-5)


def test_shape_of_the_result(full_table):
    la, lu = full_table["La"], full_table["Lu"]
    assert np.all(np.diff(la) < 0)                           # saturation: La falls with current
    assert np.ptp(lu) / lu.mean() < 0.05                     # Lu nearly constant (air dominated)
    assert la[0] == pytest.approx(k64.MEASURED["La"][0], rel=0.10)   # unsaturated La within 10 % of measured
    assert np.all(full_table["T_avg"] > 0)
