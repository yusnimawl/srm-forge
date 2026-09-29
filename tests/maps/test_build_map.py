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
