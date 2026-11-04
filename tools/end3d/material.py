"""Magnetic energy density as an NGSolve BSpline of s = |B|^2."""
import numpy as np
from ngsolve import BSpline
from scipy.interpolate import make_interp_spline

from srmcore.materials.laws import LinearLaw, ReluctivityLaw
from srmcore.model.constants import MU0

B_FIRST = 1e-4
B_SEARCH = 1000.0            # the join is searched up to here (T)
B_FAR = 2.0 * B_SEARCH       # the linear tail ends here (T)
NU_JOIN = 0.99               # nu/nu0 at the default join
B_LINEAR_DEFAULT = 6.0       # LinearLaw: exact at any b_max
B_KNEE_LO, B_KNEE_HI = 0.1, 3.0
N_LOW, N_MID, N_HIGH = 60, 500, 100


def join_field(law: ReluctivityLaw) -> float:
    """|B| at which nu(law) first reaches NU_JOIN * nu0 (T), searched up to B_SEARCH."""
    if isinstance(law, LinearLaw):
        return B_LINEAR_DEFAULT
    nu0 = 1.0 / MU0
    b = np.geomspace(1.0, B_SEARCH, 2000)
    hit = np.nonzero(law.nu_dnu(b**2)[0] >= NU_JOIN * nu0)[0]
    if hit.size == 0:
        raise ValueError(f"nu does not reach {NU_JOIN} nu0 below {B_SEARCH} T; pass b_max")
    return float(b[hit[0]])


def _iron_grid(b_max: float) -> np.ndarray:
    """|B| sample points: geometric to 0.1 T, uniform through the knee to 3 T, geometric to b_max."""
    if b_max <= B_KNEE_HI:
        return np.geomspace(B_FIRST, b_max, N_LOW + N_MID)
    return np.unique(np.r_[
        np.geomspace(B_FIRST, B_KNEE_LO, N_LOW),
        np.linspace(B_KNEE_LO, B_KNEE_HI, N_MID),
        np.geomspace(B_KNEE_HI, b_max, N_HIGH),
    ])


def energy_bspline(law: ReluctivityLaw, b_max: float | None = None) -> BSpline:
    """w(s), s = |B|^2 in T^2, w in J/m^3, so dw/ds = nu(s)/2.

    Cubic (NGSolve order 4 = degree 3) up to b_max, which defaults to `join_field(law)`. Beyond
    b_max a second piece continues the value linearly with slope nu0/2 (a quadruple knot at b_max^2
    lets the slope jump; nu differs from nu0 by about 1 % there). NGSolve does not extrapolate, so
    the tail has to be in the spline. A LinearLaw is one exact linear piece with slope nu/2.
    """
    if b_max is None:
        b_max = join_field(law)
    s0, s1 = b_max**2, B_FAR**2
    if isinstance(law, LinearLaw):
        t = [0.0] * 4 + [s1] * 4
        c = list(0.5 * law.nu * np.linspace(0.0, 1.0, 4) * s1)
        return BSpline(4, t, c)
    b = _iron_grid(b_max)
    s = np.r_[0.0, b**2]
    w = np.r_[0.0, law.energy_density(b)]
    left = make_interp_spline(s, w, k=3)
    cr = w[-1] + 0.5 / MU0 * (np.linspace(0.0, 1.0, 4) * (s1 - s0))
    t = np.r_[left.t, [s1] * 4]
    c = np.r_[left.c, cr]
    return BSpline(4, list(t), list(c))

def nu_from_bspline(w: BSpline, s: np.ndarray) -> np.ndarray:
    """nu = 2 dw/ds at the given s values."""
    dw = w.Differentiate()
    return np.array([2.0 * dw(float(v)) for v in np.atleast_1d(s)])
