"""Magnetic energy density as an NGSolve BSpline of s = |B|^2."""
import numpy as np
from ngsolve import BSpline
from scipy.interpolate import make_interp_spline

from srmcore.materials.laws import ReluctivityLaw
from srmcore.model.constants import MU0

B_FIRST = 1e-4
B_FAR = 100.0     # the linear tail ends here (T)


def energy_bspline(law: ReluctivityLaw, b_max: float = 6.0, n: int = 600) -> BSpline:
    """w(s), s = |B|^2 in T^2, w in J/m^3, so dw/ds = nu(s)/2.

    Cubic (NGSolve order 4), knots geometric in |B| from 1e-4 T to b_max. Beyond b_max a second
    piece continues the value linearly with slope nu0/2 out to 100 T (a quadruple knot at b_max^2
    lets the slope jump there). NGSolve does not extrapolate, so the tail has to be in the spline.
    """
    b = np.geomspace(B_FIRST, b_max, n)
    s = np.r_[0.0, b**2]
    w = np.r_[0.0, law.energy_density(b)]
    left = make_interp_spline(s, w, k=3)
    s0, s1 = b_max**2, B_FAR**2
    slope = 0.5 / MU0
    cr = w[-1] + slope * (np.linspace(0.0, 1.0, 4) * (s1 - s0))
    t = np.r_[left.t, [s1] * 4]
    c = np.r_[left.c, cr]
    return BSpline(4, list(t), list(c))


def nu_from_bspline(w: BSpline, s: np.ndarray) -> np.ndarray:
    """nu = 2 dw/ds at the given s values."""
    dw = w.Differentiate()
    return np.array([2.0 * dw(float(v)) for v in np.atleast_1d(s)])
