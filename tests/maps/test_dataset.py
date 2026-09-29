import dataclasses
import json

import numpy as np
import pytest

from conftest import make_8_6
from srmcore.maps import dataset
from srmcore.maps.run import STATUS_OK, MapResult
from srmcore.model.design import Design, MeshSettings
from srmcore.solvers.skfem_reference import SkfemReference

DESIGN = Design(machine=make_8_6(), mesh=MeshSettings(preset="screening"))
ANGLES, CURRENTS = np.array([0.0, 0.01, 0.02]), np.array([0.0, 5.0])
SOLVER = SkfemReference()


def _result(complete=True):
    rng = np.random.default_rng(0)
    return MapResult(
        ANGLES, CURRENTS, ("A", "B", "C", "D"), "A", rng.random((3, 2, 4)), rng.random((3, 2)),
        rng.random((3, 2)), rng.random((3, 2)), np.full((3, 2), 7, dtype=np.int32),
        np.full((3, 2), STATUS_OK, dtype=np.int8), np.zeros((3, 2), dtype=bool), complete)


def _prov(design=DESIGN, angles=ANGLES, currents=CURRENTS, excited="A", solver=SOLVER):
    return dataset.provenance(design, angles, currents, excited, solver)


def test_write_read_round_trip(tmp_path):
    r, prov = _result(), _prov()
    dataset.write_map(tmp_path / "m.h5", r, prov)
    back, back_prov = dataset.read_map(tmp_path / "m.h5")
    for f in dataclasses.fields(MapResult):
        a, b = getattr(r, f.name), getattr(back, f.name)
        assert np.array_equal(a, b) if isinstance(a, np.ndarray) else a == b
    assert back_prov == prov and not list(tmp_path.glob("*.tmp"))


def test_hash_changes_with_every_input():
    base = dataset.provenance_hash(_prov())
    assert base == dataset.provenance_hash(_prov())
    other_design = Design(machine=make_8_6(air_gap=0.0005), mesh=MeshSettings(preset="screening"))
    variants = [_prov(design=other_design), _prov(angles=ANGLES[:2]), _prov(currents=CURRENTS * 2),
                _prov(excited="B")]
    stale = _prov()
    stale["solver_version"] = "0.0.0"
    variants.append(stale)
    assert len({base, *(dataset.provenance_hash(p) for p in variants)}) == 1 + len(variants)


def test_cache_only_holds_complete_maps(tmp_path):
    prov = _prov()
    assert dataset.cached_map(tmp_path, prov) is None
    assert dataset.store_map(tmp_path, _result(complete=False), prov) is None
    assert dataset.cached_map(tmp_path, prov) is None
    path = dataset.store_map(tmp_path, _result(), prov)
    assert path.exists() and dataset.cached_map(tmp_path, prov) is not None
    assert dataset.cached_map(tmp_path, _prov(excited="B")) is None


def test_interrupted_write_is_never_a_hit(tmp_path):
    prov = _prov()
    (tmp_path / f"map_{dataset.provenance_hash(prov)}.h5.tmp").write_bytes(b"partial")
    assert dataset.cached_map(tmp_path, prov) is None


def test_corrupt_or_mismatched_cache_file_is_a_miss(tmp_path):
    prov = _prov()
    path = tmp_path / f"map_{dataset.provenance_hash(prov)}.h5"
    path.write_bytes(b"not hdf5")
    assert dataset.cached_map(tmp_path, prov) is None


def test_provenance_is_json_serialisable():
    json.dumps(_prov(), sort_keys=True)
