import numpy as np
import pytest

from srmcore.materials.bh import B_SMALL, process_bh, repair_monotone
from srmcore.materials.laws import VACUUM, LinearLaw, law_for_material, library_law
from srmcore.materials.library import load_material
from srmcore.materials.schema import BHTable
from srmcore.model.constants import MU0
from srmcore.model.errors import InputError

M19 = load_material("M19")


def _process(table, k=1.0, js=2.1):
    return process_bh(table, k, js)


def _table(h, b):
    return BHTable(h=tuple(float(x) for x in h), b=tuple(float(x) for x in b))


@pytest.mark.parametrize("h_scale,b_scale", [(1.0, 1000.0), (1.0, 10000.0), (1e-3, 1.0), (1 / 79.577, 1.0)],
                         ids=["B in mT", "B in gauss", "H in kA/m", "H in Oe"])
def test_unit_mixups_are_rejected(h_scale, b_scale):
    table = _table(np.array(M19.bh.h) * h_scale, np.array(M19.bh.b) * b_scale)
    with pytest.raises(InputError) as info:
        _process(table)
    assert info.value.issues[0].parameter == "bh" and info.value.issues[0].rule == "units"


def test_origin_is_added_and_reported():
    curve, report = _process(_table(M19.bh.h[1:], M19.bh.b[1:]), js=2.03)
    assert report.added_origin
    assert curve.h_of_b(np.array([0.0]))[0] == 0.0


def test_non_monotone_table_is_rejected_and_repair_reports_changes():
    h = [0.0, 50.0, 40.0, 100.0, 200.0, 1000.0]
    b = [0.0, 0.5, 0.6, 1.0, 1.2, 1.5]
    with pytest.raises(InputError) as info:
        _process(_table(h, b))
    assert info.value.issues[0].rule == "monotone"
    h2, b2, changes = repair_monotone(h, b)
    assert list(h2) == [0.0, 50.0, 100.0, 200.0, 1000.0]
    assert changes == ["dropped point 2 (H=40 A/m, B=0.6 T): not above point 1"]


def test_decreasing_polarisation_is_rejected():
    # dB/dH = 0.5·μ0 on the last segment: J = B - μ0·H would fall.
    h = [0.0, 100.0, 1000.0, 1e5, 2e5]
    b = [0.0, 1.0, 1.5, 2.0, 2.0 + 0.5 * MU0 * 1e5]
    with pytest.raises(InputError) as info:
        _process(_table(h, b), js=2.5)
    assert info.value.issues[0].rule == "polarisation"


def test_saturation_polarisation_must_exceed_last_point():
    with pytest.raises(InputError) as info:
        _process(M19.bh, k=1.0, js=1.9)
    assert info.value.issues[0].rule == "saturation"


def test_stacking_factor_applied_at_the_knots():
    k = 0.95
    curve, report = process_bh(M19.bh, k, M19.saturation_polarisation)
    h = np.array(M19.bh.h[1:])
    b_eff = k * np.array(M19.bh.b[1:]) + (1 - k) * MU0 * h
    assert np.allclose(curve.h_of_b(b_eff), h, rtol=1e-12)
    assert report.knot_max_relative_error < 1e-12
    assert report.tail_saturation_polarisation == pytest.approx(k * M19.saturation_polarisation)


@pytest.mark.parametrize("name", ["M19", "steel_1010"])
def test_tail_joins_c1_and_approaches_js(name):
    m = load_material(name)
    curve, report = process_bh(m.bh, m.stacking_factor, m.saturation_polarisation)
    bn, e = report.join_b, 1e-7
    below, above = curve.h_of_b(np.array([bn - e, bn + e]))
    assert above - below == pytest.approx(0.0, abs=1.0)                  # H ~ 2e5 A/m: C0
    d_below, d_above = curve.dh_db(np.array([bn - e, bn + e]))
    assert d_above == pytest.approx(d_below, rel=1e-6)                      # C1
    b = np.array([bn + 0.5, bn + 2.0, bn + 10.0])
    j = b - MU0 * curve.h_of_b(b)
    assert np.all(np.diff(j) >= 0) and np.all(j < report.tail_saturation_polarisation)
    assert np.all(curve.dh_db(b) <= 1 / MU0 * (1 + 1e-12))


@pytest.mark.parametrize("name", ["M19", "steel_1010"])
def test_energy_and_coenergy_densities_match_quadrature(name):
    m = load_material(name)
    curve, _ = process_bh(m.bh, m.stacking_factor, m.saturation_polarisation)
    for b_top in (0.3, 1.5, 2.2, 3.0):
        grid = np.linspace(0.0, b_top, 200_001)
        w_num = np.trapezoid(curve.h_of_b(grid), grid)
        assert curve.energy_density(np.array([b_top]))[0] == pytest.approx(w_num, rel=1e-6)
        h_top = curve.h_of_b(np.array([b_top]))[0]
        assert curve.coenergy_density(np.array([b_top]))[0] == pytest.approx(b_top * h_top - w_num, rel=1e-6)


def test_reluctivity_derivative_matches_finite_differences():
    curve = library_law("M19")
    b2 = np.array([0.3, 1.2, 1.9, 2.2, 2.5, 3.0, 4.0]) ** 2
    nu, dnu = curve.nu_dnu(b2)
    step = 1e-6 * b2
    fd = (curve.nu_dnu(b2 + step)[0] - curve.nu_dnu(b2 - step)[0]) / (2 * step)
    assert np.allclose(dnu, fd, rtol=1e-6)
    assert np.allclose(nu, curve.h_of_b(np.sqrt(b2)) / np.sqrt(b2))


def test_reluctivity_is_finite_at_zero_field():
    nu, dnu = library_law("M19").nu_dnu(np.array([0.0, 1e-14, (B_SMALL / 2) ** 2]))
    assert np.all(np.isfinite(nu)) and np.all(nu > 0) and np.all(dnu == 0)


def test_laws_for_materials():
    assert law_for_material(load_material("copper")) is VACUUM
    assert library_law("M19") is library_law("M19")
    lin = LinearLaw(1000.0)
    nu, dnu = lin.nu_dnu(np.array([1.0, 4.0]))
    assert np.allclose(nu, 1 / (1000 * MU0)) and np.all(dnu == 0)
    assert lin.energy_density(np.array([2.0]))[0] == pytest.approx(2.0 / (1000 * MU0))
