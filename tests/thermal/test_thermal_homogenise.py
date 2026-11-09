import pytest

from srmcore.thermal.homogenise import K_CU, MILTON_XI, hashin_shtrikman_lower, milton_k


# The paper prints 2.41 and 3.11; the gap is recorded in docs/r5-thermal-results.md.
def test_v3_milton_motorette_a():
    assert milton_k(0.37, K_CU, 1.0, MILTON_XI[0.37]) == pytest.approx(2.430, rel=0.005)


def test_v3_milton_motorette_b():
    assert milton_k(0.47, K_CU, 1.0, 0.324) == pytest.approx(3.439, rel=0.005)


def test_hs_values_and_below_milton():
    assert hashin_shtrikman_lower(0.37, K_CU, 1.0) == pytest.approx(2.158, rel=0.005)
    for km in (0.2, 0.6, 1.0):
        assert hashin_shtrikman_lower(0.37, K_CU, km) <= milton_k(0.37, K_CU, km, 0.324)
