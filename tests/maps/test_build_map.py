import numpy as np
import pytest

from conftest import make_8_6
from srmcore.maps import api
from srmcore.maps.run import run_map
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design, MeshSettings

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))


def test_pool_result_equals_serial_result():
    static = build_machine_mesh(DESIGN)
    angles, currents = np.array([0.0, 2 * static.settings.band_pitch]), np.array([0.0, 5.0])
    serial = run_map(static, DESIGN, angles, currents, solver_name="skfem_reference", workers=1)
    pooled = run_map(static, DESIGN, angles, currents, solver_name="skfem_reference", workers=2)
    assert np.allclose(pooled.psi, serial.psi, rtol=1e-9, atol=1e-15)
    assert np.allclose(pooled.torque_arkkio, serial.torque_arkkio, rtol=1e-9, atol=1e-15)
    assert np.array_equal(pooled.status, serial.status)


def test_pool_matches_serial_to_1e12_and_progress_counts_points():
    static = build_machine_mesh(DESIGN)
    angles, currents = np.array([0.0, 2 * static.settings.band_pitch]), np.array([0.0, 2.5, 5.0])
    ticks = []
    serial = run_map(static, DESIGN, angles, currents, solver_name="skfem_reference", workers=1)
    pooled = run_map(static, DESIGN, angles, currents, solver_name="skfem_reference", workers=2,
                     progress=lambda done, total: ticks.append((done, total)))
    for name in ("psi", "torque_arkkio", "torque_virtual_work", "coenergy"):
        assert np.allclose(getattr(pooled, name), getattr(serial, name), rtol=1e-12, atol=1e-15)
    assert np.array_equal(pooled.iterations, serial.iterations)
    assert ticks[-1] == (6, 6) and {t for _, t in ticks} == {6}


def test_second_call_is_served_from_the_cache_without_meshing(tmp_path, monkeypatch):
    kw = dict(i_max=5.0, solver="skfem_reference", n_angles=2, n_currents=2, cache_dir=tmp_path, workers=1)
    first = api.build_map(DESIGN, **kw)
    monkeypatch.setattr(api, "build_machine_mesh", lambda d: pytest.fail("meshed on a cache hit"))
    second = api.build_map(DESIGN, **kw)
    assert np.array_equal(first.psi, second.psi) and second.complete
    assert len(list(tmp_path.glob("map_*.h5"))) == 1


def test_cancelled_map_is_not_cached(tmp_path):
    r = api.build_map(DESIGN, 5.0, solver="skfem_reference", n_angles=2, n_currents=2, cache_dir=tmp_path,
                      workers=1, cancel=lambda: True)
    assert not r.complete and not list(tmp_path.glob("map_*.h5"))


@pytest.mark.parametrize("excited", ["Z", "B"])
def test_only_phase_a_is_supported(excited):
    with pytest.raises(ValueError, match="excited"):
        api.build_map(DESIGN, 5.0, solver="skfem_reference", excited=excited, n_angles=2, n_currents=2)


@pytest.mark.parametrize("i_max", [0.0, -1.0, float("nan"), float("inf")])
def test_i_max_must_be_finite_and_positive(i_max):
    with pytest.raises(ValueError, match="i_max"):
        api.build_map(DESIGN, i_max, solver="skfem_reference", n_angles=2, n_currents=2)


def test_unknown_solver_fails_in_the_parent_before_the_pool():
    with pytest.raises(ValueError, match="unknown solver"):
        run_map(None, DESIGN, np.array([0.0]), np.array([0.0, 5.0]), solver_name="nope", workers=2)


@pytest.mark.parametrize("kw", [{"n_angles": 0, "n_currents": 2}, {"n_angles": 2, "n_currents": 1},
                                {"n_angles": 2, "n_currents": 0}])
def test_grid_sizes_must_be_usable(kw):
    with pytest.raises(ValueError, match="n_"):
        api.build_map(DESIGN, 5.0, solver="skfem_reference", **kw)
