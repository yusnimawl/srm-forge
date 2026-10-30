"""EMDLAB / ANSYS Maxwell cross-tool comparison on the 8/6 benchmark of the EMDLAB paper (Jamali-Fard et al.,
SoftwareX 32 (2025) 102446): srmcore `full` at 3.6 A on phase A over the 30 reference angles, against the
committed fixtures in tests/validation/fixtures/emdlab_8_6 (docs/emdlab-results.md)."""
import math

import pytest

import emdlab_machine as em
from srmcore.fields.solution import SolveStatus
from srmcore.maps.point import solve_point
from srmcore.mesh import build_machine_mesh

PSI_TOLERANCE = 0.02            # relative, against EMDLAB
# EMDLAB's mesh has about 8.5k nodes, and its error grows on the rising edge, where W' integrates the psi error.
ENERGY_TOLERANCE = 0.03         # relative, W and W' against EMDLAB
# Of the reference tool's peak torque, at every angle. Maxwell and EMDLAB differ from each other by up to
# 3.8 % of the peak, on the rising edge.
TORQUE_TOLERANCE = 0.05
END_TORQUE = 0.005              # of the Maxwell peak: aligned and unaligned torque is zero by symmetry

pytestmark = pytest.mark.slow


def _solver():
    try:
        from srmcore.solvers.ngsolve_adapter import NgsolveAdapter
        return NgsolveAdapter()
    except ImportError:
        from srmcore.solvers.skfem_reference import SkfemReference
        return SkfemReference()


@pytest.fixture(scope="module")
def compared():
    d = em.design()
    static = build_machine_mesh(d)
    solver = _solver()
    return [(q, solve_point(static, d, q.angle, {"A": em.CURRENT}, solver)) for q in em.references()]


def test_angles_are_band_nodes_and_solves_converge(compared):
    for q, r in compared:
        assert math.isclose(r.angle, q.angle % (2 * math.pi), abs_tol=1e-12)
        assert r.status in (SolveStatus.OK, SolveStatus.OK_WITH_FALLBACK)


def test_flux_linkage_against_emdlab(compared):
    bad = [f"{q.theta_tab_deg:.2f} deg: {r.psi[0] / q.psi - 1:+.3%}"
           for q, r in compared if abs(r.psi[0] - q.psi) > PSI_TOLERANCE * q.psi]
    assert not bad, bad


def test_energy_and_coenergy_against_emdlab(compared):
    bad = []
    for q, r in compared:
        for name, ours, ref in (("W", r.energy, q.energy), ("W'", r.coenergy, q.coenergy)):
            if abs(ours - ref) > ENERGY_TOLERANCE * ref:
                bad.append(f"{q.theta_tab_deg:.2f} deg {name}: {ours / ref - 1:+.3%}")
    assert not bad, bad


@pytest.mark.parametrize("tool", ["maxwell", "emdlab"])
def test_torque_against_reference_tool(compared, tool):
    ref = {q: (q.torque_maxwell if tool == "maxwell" else q.torque_emdlab) for q, _ in compared}
    peak = max(abs(v) for v in ref.values())
    bad = [f"{q.theta_tab_deg:.2f} deg: dT {r.torque_arkkio - ref[q]:+.4f} N m"
           for q, r in compared if abs(r.torque_arkkio - ref[q]) > TORQUE_TOLERANCE * peak]
    assert not bad, bad


def test_aligned_and_unaligned_torque_is_zero(compared):
    peak = max(abs(q.torque_maxwell) for q, _ in compared)
    ends = [(q, r) for q, r in compared if q.theta_tab_deg in (compared[0][0].theta_tab_deg, compared[-1][0].theta_tab_deg)]
    assert len(ends) == 2
    for q, r in ends:
        assert abs(r.torque_arkkio) < END_TORQUE * peak, q.theta_tab_deg
