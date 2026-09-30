import csv
import dataclasses

import numpy as np
import pytest
from map_fixtures import PERIOD, synthetic_map
from scipy.io import loadmat

from srmcore.maps import KeyNumbers, MapReport, export_csv, export_mat
from srmcore.maps.tables import dpsi_dtheta, drive_tables


def _report(**kw):
    r = synthetic_map(psi_sat=0.05, **kw)
    key = KeyNumbers(3e-3, 1e-3, 3.0, 12.5, 0.04, 20.0, 0.1, 0.6)
    return MapReport(r, key, drive_tables(r), dpsi_dtheta(r, PERIOD), ())


def _rows(path):
    with open(path, newline="") as f:
        return list(csv.reader(f))


def _same(a, b):
    np.testing.assert_allclose(np.asarray(a, float), np.asarray(b, float), rtol=1e-12, atol=0)


def test_csv_round_trip(tmp_path):
    rep = _report()
    r, t = rep.result, rep.tables
    paths = export_csv(rep, tmp_path)
    assert [p.name for p in paths] == ["psi_map.csv", "inverse_current.csv", "key_numbers.csv"]

    rows = _rows(tmp_path / "psi_map.csv")
    assert rows[0] == ["angle_rad", "current_A", "psi_A", "psi_B", "psi_C", "psi_D",
                       "torque_Nm", "coenergy_J", "l_inc_H", "status", "filled"]
    body = np.array(rows[1:], float)
    na, nc = r.psi.shape[:2]
    assert len(body) == na * nc
    _same(body[:, 0], np.repeat(r.angles, nc))
    _same(body[:, 1], np.tile(r.currents, na))
    _same(body[:, 2:6], r.psi.reshape(na * nc, -1))
    _same(body[:, 6], r.torque_arkkio.ravel())
    _same(body[:, 7], r.coenergy.ravel())
    _same(body[:, 8], r.l_inc[..., 0].ravel())
    _same(body[:, 9], r.status.ravel())
    _same(body[:, 10], r.filled.ravel())

    inv = np.array(_rows(tmp_path / "inverse_current.csv")[1:], float)
    assert _rows(tmp_path / "inverse_current.csv")[0] == ["angle_rad", "psi_Wb", "current_A", "torque_Nm", "flat"]
    n_psi = len(t.psi_grid)
    assert np.isnan(t.current).any()                      # NaN must survive
    _same(inv[:, 0], np.repeat(t.angles, n_psi))
    _same(inv[:, 1], np.tile(t.psi_grid, na))
    _same(inv[:, 2], t.current.ravel())
    _same(inv[:, 3], t.torque.ravel())
    _same(inv[:, 4], t.flat.ravel())

    key = _rows(tmp_path / "key_numbers.csv")
    assert key[0] == ["name", "value", "unit"]
    got = {n: (float(v), u) for n, v, u in key[1:]}
    for f in dataclasses.fields(rep.key_numbers):
        assert got[f.name][0] == getattr(rep.key_numbers, f.name)
    assert got["peak_torque"][1] == "N*m"


def test_mat_round_trip(tmp_path):
    rep = _report()
    r, t = rep.result, rep.tables
    p = export_mat(rep, tmp_path / "map.mat", provenance_hash="abc123")
    m = loadmat(p, squeeze_me=True, struct_as_record=False)
    _same(m["angles"], r.angles)
    _same(m["currents"], r.currents)
    _same(m["psi"], r.psi)
    _same(m["torque"], r.torque_arkkio)
    _same(m["coenergy"], r.coenergy)
    _same(m["l_inc"], r.l_inc)
    _same(m["dpsi_dtheta"], rep.dpsi_dtheta)
    _same(m["psi_grid"], t.psi_grid)
    assert np.isnan(m["current_of_psi"]).sum() == np.isnan(t.current).sum() > 0
    _same(m["current_of_psi"], t.current)
    _same(m["torque_of_psi"], t.torque)
    _same(m["status"], r.status)
    assert list(np.atleast_1d(m["circuits"])) == list(r.circuits)
    for f in dataclasses.fields(rep.key_numbers):
        assert getattr(m["key_numbers"], f.name) == getattr(rep.key_numbers, f.name)
    assert m["provenance_hash"] == "abc123"


def test_mat_omits_hash_by_default(tmp_path):
    m = loadmat(export_mat(_report(), tmp_path / "m.mat"))
    assert "provenance_hash" not in m


def test_exports_refuse_incomplete_map(tmp_path):
    rep = _report()
    rep = dataclasses.replace(rep, result=dataclasses.replace(rep.result, complete=False))
    with pytest.raises(Exception):
        export_csv(rep, tmp_path)
