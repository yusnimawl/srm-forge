import dataclasses

import h5py
import numpy as np
import pytest

from map_fixtures import NR, PERIOD, dinductance, inductance, synthetic_map
from srmcore.maps import dataset
from srmcore.maps.tables import dpsi_dtheta, drive_tables


def test_dpsi_dtheta_matches_analytic():
    r = synthetic_map()
    got = dpsi_dtheta(r, PERIOD)[..., 0]
    want = dinductance(r.angles)[:, None] * r.currents[None, :]
    assert np.max(np.abs(got - want)) < 1e-2 * np.max(np.abs(want))


def test_linear_roundtrip_and_inverse():
    r = synthetic_map()
    t = drive_tables(r)
    assert t.monotone.all() and t.roundtrip_error < 1e-6 and not t.flat.any()
    assert t.psi_grid[0] == 0 and len(t.psi_grid) == 2 * len(r.currents)
    ok = ~np.isnan(t.current)
    psi = inductance(r.angles)[:, None] * t.current
    assert np.allclose(psi[ok], np.broadcast_to(t.psi_grid, psi.shape)[ok], rtol=1e-6, atol=1e-12)
    assert np.isnan(t.current).any()      # ψ above ψ(θ, I_max) of the unaligned angles


def test_flat_only_when_deeply_saturated():
    sat = drive_tables(synthetic_map(psi_sat=0.01, currents=np.linspace(0, 60, 13)))
    assert sat.flat.any()
    assert not drive_tables(synthetic_map()).flat.any()


def test_non_monotone_angle_flagged():
    r = synthetic_map()
    psi = r.psi.copy()
    psi[3, 5:, 0] = psi[3, 4, 0] - 1e-4
    t = drive_tables(dataclasses.replace(r, psi=psi))
    assert not t.monotone[3] and t.monotone.sum() == len(r.angles) - 1
    assert np.isnan(t.current[3]).all() and np.isnan(t.torque[3]).all()


def test_incomplete_raises():
    r = synthetic_map(complete=False)
    for f in (lambda: dpsi_dtheta(r, PERIOD), lambda: drive_tables(r)):
        with pytest.raises(ValueError, match="map is incomplete"):
            f()


def test_dataset_stores_dpsi_dtheta(tmp_path):
    r = synthetic_map()
    prov = {"design": {"machine": {"n_rotor_poles": NR}}}
    dataset.write_map(tmp_path / "m.h5", r, prov)
    with h5py.File(tmp_path / "m.h5") as f:
        assert f["dpsi_dtheta"].shape == r.psi.shape
        assert list(f["dpsi_dtheta"].attrs["dims"]) == ["angle", "current", "circuit"]
