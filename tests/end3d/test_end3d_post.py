import dataclasses
import functools
import math

import pytest

pytest.importorskip("ngsolve")

import team24_fixture as fx  # noqa: E402
from end3d import post  # noqa: E402
from end3d.solve import solve3d  # noqa: E402
from end3d.team24 import Team24Params, ampere_turns, team24_model  # noqa: E402
from srmcore.materials.laws import LinearLaw  # noqa: E402

CURRENT = 5.0
pytestmark = pytest.mark.slow


@functools.lru_cache(maxsize=None)
def _run(**kw):
    p = Team24Params(slab=True, maxh=8e-3, **kw)
    m = team24_model(p)
    m = dataclasses.replace(m, laws={k: (LinearLaw(1000.0) if k == "steel" else v)
                                     for k, v in m.laws.items()})
    at = ampere_turns(p, CURRENT)
    sol = solve3d(m, at)
    assert sol.converged
    return m, sol, at


def _psi(m, sol, at):
    return post.flux_linkage(m, sol, m.coils, CURRENT, at)


def _torque(m, sol):
    return post.arkkio_torque(m, sol, fx.BAND_INNER, fx.BAND_OUTER)


def test_slab_scales_with_depth():
    full = _run()
    half = _run(depth=fx.DEPTH / 2)  # depth 2D does not mesh at maxh 8e-3
    assert _psi(*full) / _psi(*half) == pytest.approx(2, rel=2e-3)
    assert _torque(*full[:2]) / _torque(*half[:2]) == pytest.approx(2, rel=2e-3)


def test_coenergy_equals_half_li_linear():
    m, sol, at = _run()
    assert post.coenergy(m, sol) == pytest.approx(0.5 * _psi(m, sol, at) * CURRENT, rel=5e-3)


def test_torque_virtual_work():
    d = math.radians(0.5)
    w = {}
    for sgn in (1, -1):
        m, sol, _ = _run(rotor_angle=fx.ROTOR_ANGLE + sgn * d)
        w[sgn] = post.coenergy(m, sol)
    m, sol, _ = _run()
    assert _torque(m, sol) == pytest.approx((w[1] - w[-1]) / (2 * d), rel=2e-2)
