import numpy as np
import pytest

pytest.importorskip("ngsolve")

from end3d.material import energy_bspline, nu_from_bspline
from srmcore.materials.laws import VACUUM, library_law
from srmcore.model.constants import MU0
from team24_fixture import steel_law

B = np.array([0.1, 0.5, 1.0, 1.5, 1.9, 2.2])


@pytest.mark.parametrize("law", [library_law("10JNEX900"), steel_law()], ids=["10JNEX900", "team24"])
def test_energy_derivative_matches_law(law):
    nu = nu_from_bspline(energy_bspline(law), B**2)
    ref = law.nu_dnu(B**2)[0]
    assert np.allclose(nu, ref, rtol=1e-3, atol=0)


def test_linear_law_exact():
    b = np.array([0.01, 3.0])
    nu = nu_from_bspline(energy_bspline(VACUUM), b**2)
    assert np.allclose(nu, 1 / MU0, rtol=1e-9, atol=0)


def test_tail_is_vacuum_slope():
    w = energy_bspline(library_law("10JNEX900"))
    nu = nu_from_bspline(w, np.array([8.0**2, 20.0**2]))
    assert np.allclose(nu, 1 / MU0, rtol=1e-2, atol=0)
