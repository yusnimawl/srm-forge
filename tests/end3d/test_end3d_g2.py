import math

import pytest

pytest.importorskip("ngsolve")

import end3d.g2_slab as g2  # noqa: E402

pytestmark = pytest.mark.slow


def _row(machine, angle, current):
    ref = g2.reference_2d(machine, angle, current)
    got = g2.solve_slab(machine, angle, current, g2.LEVEL_MM[machine], 3_000_000)
    return {"machine": machine, "angle": angle, "current": current, "psi_2d": ref[0], "torque_2d": ref[1], **got}


def test_g2_slab_matches_2d():
    """The half-overlap 8/6 point (a nonzero torque to normalise by) and TEAM 24 at the top table current."""
    rows = g2.assess([_row(*g2.POINTS[1]), _row(*g2.POINTS[3])])
    for r in rows:
        assert r["converged"], r
        assert math.copysign(1, r["psi_3d"]) == math.copysign(1, r["psi_2d"])
        assert math.copysign(1, r["torque_3d"]) == math.copysign(1, r["torque_2d"])
        assert r["psi_rel"] <= g2.PSI_TOL, r
        assert r["torque_rel_peak"] <= g2.TORQUE_TOL, r
