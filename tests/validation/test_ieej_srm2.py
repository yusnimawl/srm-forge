"""IEEJ public-use SRM "SRM2" (18/12, 10JNEX900; tests/ieej_srm2.py): the portal tables in
tests/validation/fixtures/ieej_srm2 and srmcore against the IEEJ TR 1589 2D maps (docs/ieej-srm2-results.md).

The fixture and geometry tests are fast. The comparison is slow: `screening` at 250 A, phase A only, at the
16 portal positions."""
import math

import numpy as np
import pytest

import ieej_srm2 as m
from srmcore.topology.radial import build_outline

# Regression limits for `screening` with the library 10JNEX900 (stacking factor 0.9): the screening results of
# docs/ieej-srm2-results.md (psi -4.76 %, torque -6.46 % of the peak, mean torque -6.2 %, unaligned psi -0.19 %)
# plus margin. They are not an agreement claim: the B-H curve behind the portal maps is published as a figure
# only, and with stacking factor 1.0 the same mesh reads +4.4 % and +7.7 % instead; the portal sits between.
PSI_LIMIT = {"unaligned": 0.01, "any": 0.06}       # relative to the portal flux linkage
TORQUE_LIMIT = 0.08                                 # of the portal peak torque (table x 2), at every position
MEAN_TORQUE_LIMIT = 0.08                            # relative, mean stroke torque from the co-energy
END_TORQUE = 0.005                                  # of the portal peak: zero by symmetry at both ends


def test_portal_tables_share_one_grid():
    flux, torque = m.flux_table(), m.torque_table()
    assert np.array_equal(flux.positions, torque.positions)
    assert np.array_equal(flux.currents, torque.currents)
    assert flux.currents[0] == 0 and flux.currents[-1] == m.CURRENT_MAX
    assert np.allclose(np.diff(flux.currents), 10.0)
    assert np.allclose(np.degrees(np.diff(flux.angles)), 1.0)
    assert math.isclose(flux.angles[0], -m.STROKE) and math.isclose(flux.angles[-1], 0.0, abs_tol=1e-15)
    # psi rises from unaligned to aligned at every current: x = 10 is unaligned
    assert np.all(np.diff(flux.values[1:], axis=1) > 0)


def test_torque_table_is_the_half_machine_torque():
    flux, torque = m.flux_table(), m.torque_table()
    ratio = m.coenergy_torque(flux)[-1, 2:-2] / torque.values[-1, 2:-2]
    assert np.all((ratio > 0.97) & (ratio < 1.03)), ratio


def test_geometry_matches_the_drawing():
    p = m.params()
    assert math.isclose(p.bore_radius, 0.0895)
    assert math.isclose(p.stator_yoke_inner_radius, 0.116)
    assert math.isclose(p.rotor_yoke_outer_radius, 0.070)
    outline = build_outline(p)
    assert outline is not None
    # the stator flank from the bore at half-arc 5.2285 deg reaches the slot bottom at 6.318 deg (drawing:
    # r 115.929 mm at 6.318 deg; the drawing's flank stops 0.07 mm short of the slot-bottom arc)
    face = (p.bore_radius * math.cos(m.STATOR_HALF_ARC), p.bore_radius * math.sin(m.STATOR_HALF_ARC))
    d = (math.cos(m.STATOR_TAPER), math.sin(m.STATOR_TAPER))
    s = 0.0265                                      # drawn flank length, m
    end = (face[0] + s * d[0], face[1] + s * d[1])
    assert math.isclose(math.hypot(*end), 0.115929, abs_tol=2e-6)
    assert math.isclose(math.degrees(math.atan2(end[1], end[0])), 6.318, abs_tol=2e-3)


@pytest.fixture(scope="module")
def compared():
    from srmcore.maps.point import solve_point
    from srmcore.mesh import build_machine_mesh
    from srmcore.solvers.ngsolve_adapter import NgsolveAdapter
    d = m.design("screening")
    static = build_machine_mesh(d)
    solver = NgsolveAdapter()
    flux, torque = m.flux_table(), m.torque_table()
    results = [solve_point(static, d, a, {"A": m.CURRENT_MAX}, solver) for a in flux.angles]
    return flux, torque, results


@pytest.mark.slow
def test_solves_converge_on_band_nodes(compared):
    from srmcore.fields.solution import SolveStatus
    flux, _, results = compared
    for a, r in zip(flux.angles, results):
        assert math.isclose(r.angle, a % (2 * math.pi), abs_tol=1e-12)
        assert r.status in (SolveStatus.OK, SolveStatus.OK_WITH_FALLBACK)


@pytest.mark.slow
def test_flux_linkage_against_the_portal_at_250_a(compared):
    flux, _, results = compared
    rel = np.array([r.psi[0] for r in results]) / flux.values[-1] - 1
    assert abs(rel[0]) < PSI_LIMIT["unaligned"], rel[0]
    assert np.max(np.abs(rel)) < PSI_LIMIT["any"], rel


@pytest.mark.slow
def test_torque_against_the_portal_at_250_a(compared):
    flux, torque, results = compared
    t = np.array([r.torque_arkkio for r in results])
    ref = torque.values[-1]
    peak = np.max(np.abs(ref))
    assert abs(t[0]) < END_TORQUE * peak and abs(t[-1]) < END_TORQUE * peak, (t[0], t[-1])
    assert np.max(np.abs(t - ref)) < TORQUE_LIMIT * peak, (t - ref) / peak
    mean = (results[-1].coenergy - results[0].coenergy) / m.STROKE
    w = m.coenergy_table(flux).values[-1]
    mean_ref = (w[-1] - w[0]) / m.STROKE
    assert abs(mean / mean_ref - 1) < MEAN_TORQUE_LIMIT, (mean, mean_ref)
