"""8/6 reference machine, screening mesh: zero current, linear Arkkio = co-energy, torque sign and
symmetry, energy identity, La/Lu band, saturation report, and the outer air ring."""
import dataclasses
import math

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.fields.solution import SolveStatus
from srmcore.materials.laws import VACUUM, LinearLaw
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.model.design import Design, MeshSettings
from srmcore.physics.build import machine_problem
from srmcore.post.quantities import arkkio_torque, flux_linkage, saturation_report
from srmcore.solvers.skfem_reference import SkfemReference

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


@pytest.fixture(scope="module")
def static():
    return build_machine_mesh(DESIGN)


@pytest.fixture(scope="module")
def solve(static):
    """solve(angle_in_band_pitches, amps_on_A, linear=False) -> (problem, solution), memoised."""
    cache = {}
    solver = SkfemReference()

    def run(k: int, amps: float, linear: bool = False, phase: str = "A"):
        key = (k, amps, linear, phase)
        if key not in cache:
            p = machine_problem(mesh_at_angle(static, k * static.settings.band_pitch), DESIGN, {phase: amps})
            if linear:
                p = dataclasses.replace(p, laws=tuple(law if law is VACUUM else LinearLaw(1000.0) for law in p.laws))
            cache[key] = (p, solver.solve(p))
        return cache[key]

    return run


def _pitches(static, degrees: float) -> int:
    k = math.radians(degrees) / static.settings.band_pitch
    assert abs(k - round(k)) < 1e-9, "test angles must sit on the band grid"
    return round(k)


def test_zero_current(solve):
    p, s = solve(0, 0.0)
    assert s.status is SolveStatus.OK
    assert np.all(flux_linkage(p, s) == 0) and arkkio_torque(p, s) == 0.0


def test_linear_arkkio_equals_coenergy_derivative(static, solve):
    k0, dk = _pitches(static, 10.0), 4
    p, s = solve(k0, 10.0, linear=True)
    dwc = (solve(k0 + dk, 10.0, linear=True)[1].coenergy - solve(k0 - dk, 10.0, linear=True)[1].coenergy) \
        / (2 * dk * static.settings.band_pitch)
    assert arkkio_torque(p, s) == pytest.approx(dwc, rel=0.01)       # trial: 0.26 %
    assert s.energy == pytest.approx(s.coenergy, rel=1e-12)


def test_torque_sign_symmetry_and_aligned_zero(static, solve):
    k = _pitches(static, 10.0)
    t_pos = arkkio_torque(*solve(k, 10.0))
    t_neg = arkkio_torque(*solve(-k, 10.0))
    t_aligned = arkkio_torque(*solve(0, 10.0))
    assert t_pos < 0 < t_neg                         # the rotor is pulled back towards alignment
    # Spec §8.3 zero-torque criterion is 1 %; the mirror-symmetric band gives ~0.02 % (trial).
    assert abs(t_pos + t_neg) < 0.002 * abs(t_pos)
    assert abs(t_aligned) < 0.002 * abs(t_pos)


def test_phase_sequence_for_counter_clockwise_motoring(solve):
    """At θ = 0 (A aligned), B pulls the rotor counter-clockwise and D clockwise, so counter-clockwise
    motoring excites A → B → C → D. The drive side (sub-project #4) relies on this convention."""
    t_b = arkkio_torque(*solve(0, 10.0, phase="B"))
    t_d = arkkio_torque(*solve(0, 10.0, phase="D"))
    assert t_b > 0 > t_d
    assert t_b == pytest.approx(-t_d, rel=0.02)


def test_energy_identity_and_status(solve):
    p, s = solve(0, 20.0)
    assert s.status is SolveStatus.OK
    psi = flux_linkage(p, s)
    assert s.energy + s.coenergy == pytest.approx(psi[0] * 20.0, rel=1e-8)
    assert psi[1] == pytest.approx(-psi[3], rel=1e-3)   # B and D are mirror images about phase A's axis


def test_aligned_to_unaligned_inductance_ratio(static, solve):
    psi_a = flux_linkage(*solve(0, 5.0))[0]
    psi_u = flux_linkage(*solve(_pitches(static, 30.0), 5.0))[0]
    assert 3.0 < psi_a / psi_u < 15.0                 # spec §7.3 "normal" La/Lu band


def test_saturation_report(solve):
    p, s = solve(0, 20.0)
    report = saturation_report(p, s, DESIGN.machine)
    for group in ("stator_iron", "rotor_iron", "shaft", "stator_poles", "stator_yoke", "rotor_poles", "rotor_yoke"):
        stats = report[group]
        assert stats.peak >= stats.p99 >= stats.p95 > 0
    assert report["stator_poles"].p95 > report["stator_yoke"].p95


@pytest.mark.slow
def test_deep_saturation_sweep(solve):
    """ψ(i) stays monotone and odd up to 160 A (stator pole tips well past the last B-H point)."""
    psi = [flux_linkage(*solve(0, amps))[0] for amps in (10.0, 40.0, 80.0, 160.0)]
    assert all(solve(0, amps)[1].status is SolveStatus.OK for amps in (10.0, 40.0, 80.0, 160.0))
    assert np.all(np.diff(psi) > 0)
    assert flux_linkage(*solve(0, -40.0))[0] == pytest.approx(-psi[1], rel=1e-9)


@pytest.mark.slow
def test_outer_air_ring_moves_the_zero_potential():
    ring = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening", outer_air_thickness=0.004))
    m = mesh_at_angle(build_machine_mesh(ring), 0.0)
    p = machine_problem(m, ring, {"A": 20.0})
    s = SkfemReference().solve(p)
    assert s.status is SolveStatus.OK
    r = np.hypot(m.nodes[:, 0], m.nodes[:, 1])
    on_od = np.isclose(r, DESIGN.machine.stator_outer_radius, rtol=1e-9)
    assert on_od.sum() > 0 and np.max(np.abs(s.a[on_od])) > 0
    assert np.all(s.a[p.dirichlet_nodes] == 0)
