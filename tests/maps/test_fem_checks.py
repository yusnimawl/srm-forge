import numpy as np
import pytest

from conftest import make_8_6
from srmcore.maps.fem_checks import fem_checks
from srmcore.model.design import Design, MeshSettings
from srmcore.post.quantities import arkkio_torque, arkkio_torque_annulus

pytest.importorskip("ngsolve")


def _solve(design, theta, current=20.0):
    from srmcore.mesh import build_machine_mesh
    from srmcore.mesh.machine import mesh_at_angle
    from srmcore.physics.build import machine_problem
    from srmcore.solvers.factory import make_solver
    problem = machine_problem(mesh_at_angle(build_machine_mesh(design), theta), design, {"A": current})
    return problem, make_solver("ngsolve").solve(problem)


def test_annulus_torque_band_identical_and_gaps_agree():
    design = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
    m = design.machine
    problem, sol = _solve(design, np.radians(10))
    band = problem.band
    t_band = arkkio_torque(problem, sol)
    assert arkkio_torque_annulus(problem, sol, band.elements, band.inner_radius, band.outer_radius) == t_band

    def gap(name, r_in, r_out):
        el = np.flatnonzero(problem.element_region == problem.region_names.index(name))
        return arkkio_torque_annulus(problem, sol, el, r_in, r_out)

    peak = abs(t_band)
    assert abs(gap("airgap_rotor", m.rotor_outer_radius, m.band_inner_radius) - t_band) < 0.01 * peak
    assert abs(gap("airgap_stator", m.band_outer_radius, m.bore_radius) - t_band) < 0.01 * peak


def test_fem_checks_skips_screening():
    from map_fixtures import synthetic_map
    design = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
    assert fem_checks(design, synthetic_map()) == ()


@pytest.mark.slow
def test_fem_checks_full_preset(capsys):
    import time
    from srmcore.maps import build_map
    design = Design(machine=make_8_6(), mesh=MeshSettings(preset="full"))
    r = build_map(design, 20.0, n_angles=8, n_currents=4)
    t0 = time.perf_counter()
    checks = fem_checks(design, r, n_samples=8)
    with capsys.disabled():
        print(f"FEM_CHECKS wall {time.perf_counter() - t0:.1f} s")
        for c in checks:
            print(f"CHECK {c.name:16s} {c.status:5s} value={c.value:.4g} limit={c.limit:.4g}")
    assert [c.name for c in checks] == ["held_out_psi", "held_out_torque", "band_radius"]
    assert next(c for c in checks if c.name == "band_radius").status == "pass"
