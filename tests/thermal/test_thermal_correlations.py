import math

import pytest

from srmcore.thermal.correlations import Fluid, airgap_h, duct_h, fluid, natural_h, petroleum_oil_cp


def test_fluid_table_point():
    f = fluid("water_glycol_50", 65.6)
    assert f.density == pytest.approx(1036.0)
    assert f.viscosity == pytest.approx(1.18e-3)
    assert fluid("water_glycol_50", 40.0).conductivity == pytest.approx(0.417)


def test_fluid_refusals():
    with pytest.raises(ValueError):
        fluid("water_glycol_50", 20.0)
    with pytest.raises(ValueError):
        fluid("atf", 60.0)


def _by_hand(re, pr, k, d, length):
    f = (0.79 * math.log(re) - 1.64) ** -2
    nu = f / 8 * (re - 1000) * pr / (1 + 12.7 * math.sqrt(f / 8) * (pr ** (2 / 3) - 1))
    return nu * (1 + (d / length) ** (2 / 3)) * k / d


def test_gnielinski_point():
    fl = Fluid(1000.0, 4000.0, 0.5, 1e-3, "t")  # Pr 8
    d, v = 0.01, 2.0  # Re 20000
    assert duct_h(fl, d, v, 0.5) == pytest.approx(_by_hand(2e4, 8.0, 0.5, d, 0.5), rel=1e-12)
    assert 3000 < duct_h(fl, d, v, 0.5) < 20000


def test_duct_below_range_refused():
    fl = Fluid(1000.0, 4000.0, 0.5, 1e-3, "t")
    with pytest.raises(ValueError):
        duct_h(fl, 0.01, 0.3, 0.5)  # Re 3000


def test_duct_out_of_range():
    fl = Fluid(1000.0, 4000.0, 0.5, 1e-3, "t")
    with pytest.raises(ValueError):
        duct_h(fl, 0.01, 200.0, 0.5)  # Re 2e6


def test_airgap_faiz_point():
    # Faiz geometry, 40 degC row of Table III: L 11.67 mm, v 3.30 m/s -> about 65.5 W/(m2 K)
    L, v = 0.01167, 3.30
    re = L * v / 16.97e-6
    expect = 0.664 * math.sqrt(re) * 0.711 ** (1 / 3) * 0.0271 / L
    assert airgap_h(L, v, 40.0) == pytest.approx(expect, rel=1e-12)
    assert expect == pytest.approx(65.5, abs=0.5)
    with pytest.raises(ValueError):
        airgap_h(L, v, 80.0)


def test_natural_cylinder_point():
    D, ts, ta = 0.125, 50.0, 30.0  # film 40 degC
    ra = 9.80665 * 3.2e-3 * 20 * D ** 3 / (16.97e-6 * 25.87e-6)
    nu = (0.6 + 0.387 * ra ** (1 / 6) / (1 + (0.559 / 0.711) ** (9 / 16)) ** (8 / 27)) ** 2
    assert natural_h("cylinder", D, ts, ta) == pytest.approx(nu * 0.0271 / D, rel=1e-12)
    assert 3 < natural_h("cylinder", D, ts, ta) < 10
    assert natural_h("plate", 0.1, ts, ta) > 0
    with pytest.raises(ValueError):
        natural_h("cylinder", D, 90.0, 50.0)


def test_petroleum_oil_cp_matches_cragoe_table_12():
    # NBS Misc. Pub. 97 p. 28 example: a 30 API oil (d 0.8762) at 100 F has 0.463 cal/(g degC)
    assert petroleum_oil_cp(0.8762 * 999.0, (100 - 32) / 1.8) == pytest.approx(0.463 * 4186.8, rel=2e-3)
    with pytest.raises(ValueError, match="Cragoe"):
        petroleum_oil_cp(1000.0, 60.0)
