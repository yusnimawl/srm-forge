"""Map dataset: provenance hash, HDF5 file with labelled axes, and the complete-maps-only cache (spec §7.2)."""
import dataclasses
import hashlib
import json
import os
from importlib.metadata import version
from pathlib import Path

import h5py
import numpy as np

from ..materials import library
from ..mesh.settings import resolve_mesh_settings
from ..model.design import Design
from ..solvers.settings import SolverAdapter
from .overlap import OverlapResult
from .run import MapResult
from .tables import dpsi_dtheta

_DIMS = {"angles": ("angle",), "currents": ("current",), "psi": ("angle", "current", "circuit"),
         "torque_arkkio": ("angle", "current"), "torque_virtual_work": ("angle", "current"),
         "energy": ("angle", "current"), "coenergy": ("angle", "current"),
         "l_inc": ("angle", "current", "circuit"), "pole_force": ("angle", "current", "pole", "component"),
         "b_peak": ("angle", "current"), "iterations": ("angle", "current"),
         "status": ("angle", "current"), "filled": ("angle", "current")}


def provenance(design: Design, angles: np.ndarray, currents: np.ndarray, excited: str,
               solver: SolverAdapter) -> dict:
    """Everything that decides the numbers in a map. The design JSON covers geometry, the mesh preset name and material
    names; the resolved mesh settings cover the numbers `resolve_mesh_settings` produces (region and gap sizes,
    refinement, band divisions and the quality limits), so a change to a preset or to that resolution invalidates
    cached maps, while a change to the size field or meshing code is covered only by the srmcore version; the
    material files' hashes cover their data, and the versions of the numerical libraries cover the rest."""
    mesh_resolved = json.loads(json.dumps(dataclasses.asdict(resolve_mesh_settings(design.machine, design.mesh))))
    names = sorted(set(design.machine.materials.model_dump().values()))
    materials = {n: hashlib.sha256((library._data_dir() / f"{n}.json").read_bytes()).hexdigest() for n in names}
    libraries = {d: version(d) for d in ("gmsh", "numpy", "scipy", "h5py")}
    return {"srmcore": version("srmcore"), "libraries": libraries, "design": json.loads(design.to_json()), "mesh_resolved": mesh_resolved, "materials": materials,
            "angles": np.asarray(angles, float).tolist(), "currents": np.asarray(currents, float).tolist(),
            "excited": excited, "solver": solver.name, "solver_version": solver.version}


def provenance_hash(prov: dict) -> str:
    return hashlib.sha256(json.dumps(prov, sort_keys=True).encode()).hexdigest()[:16]


def write_map(path, result: MapResult, prov: dict) -> None:
    """Write via a process-unique temporary file and rename, so a reader never sees a half-written map and
    concurrent writers do not collide."""
    path = Path(path)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with h5py.File(tmp, "w") as f:
        for name, dims in _DIMS.items():
            f.create_dataset(name, data=getattr(result, name)).attrs["dims"] = list(dims)
        if result.complete:
            period = 2 * np.pi / prov["design"]["machine"]["n_rotor_poles"]
            f.create_dataset("dpsi_dtheta", data=dpsi_dtheta(result, period)).attrs["dims"] = list(_DIMS["psi"])
        f.create_dataset("circuits", data=np.array(result.circuits, dtype="S"))
        f.attrs.update(excited=result.excited, complete=result.complete,
                       provenance=json.dumps(prov, sort_keys=True), hash=provenance_hash(prov))
    os.replace(tmp, path)


def read_map(path) -> tuple[MapResult, dict]:
    with h5py.File(path, "r") as f:
        arrays = {name: f[name][()] for name in _DIMS}
        circuits = tuple(c.decode() for c in f["circuits"][()])
        result = MapResult(**arrays, circuits=circuits, excited=str(f.attrs["excited"]),
                           complete=bool(f.attrs["complete"]))
        return result, json.loads(f.attrs["provenance"])


def _path(cache_dir, prov: dict) -> Path:
    return Path(cache_dir) / f"map_{provenance_hash(prov)}.h5"


def cached_map(cache_dir, prov: dict) -> MapResult | None:
    """The stored map for this provenance, or None if absent, unreadable, incomplete or for other provenance."""
    path = _path(cache_dir, prov)
    if not path.exists():
        return None
    try:
        result, stored = read_map(path)
    except (OSError, KeyError, ValueError):
        return None
    return result if result.complete and stored == prov else None


def store_map(cache_dir, result: MapResult, prov: dict) -> Path | None:
    """Only complete maps are cached."""
    if not result.complete:
        return None
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    path = _path(cache_dir, prov)
    write_map(path, result, prov)
    return path


_OVERLAP_DIMS = {"angles": ("angle",), "currents_a": ("current_a",), "currents_b": ("current_b",),
                 "psi": ("angle", "current_a", "current_b", "circuit"),
                 "torque_arkkio": ("angle", "current_a", "current_b"),
                 "l_inc": ("angle", "current_a", "current_b", "row", "column"),
                 "status": ("angle", "current_a", "current_b")}


def overlap_provenance(design: Design, angles: np.ndarray, currents_a: np.ndarray, currents_b: np.ndarray,
                       solver: SolverAdapter) -> dict:
    prov = provenance(design, angles, currents_a, "AB", solver)
    return {**prov, "overlap": True, "currents_b": np.asarray(currents_b, float).tolist()}


def write_overlap(path, result: OverlapResult, prov: dict) -> None:
    path = Path(path)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with h5py.File(tmp, "w") as f:
        for name, dims in _OVERLAP_DIMS.items():
            f.create_dataset(name, data=getattr(result, name)).attrs["dims"] = list(dims)
        f.create_dataset("circuits", data=np.array(result.circuits, dtype="S"))
        f.attrs.update(complete=result.complete, provenance=json.dumps(prov, sort_keys=True),
                       hash=provenance_hash(prov))
    os.replace(tmp, path)


def read_overlap(path) -> tuple[OverlapResult, dict]:
    with h5py.File(path, "r") as f:
        arrays = {name: f[name][()] for name in _OVERLAP_DIMS}
        circuits = tuple(c.decode() for c in f["circuits"][()])
        result = OverlapResult(**arrays, circuits=circuits, complete=bool(f.attrs["complete"]))
        return result, json.loads(f.attrs["provenance"])


def _overlap_path(cache_dir, prov: dict) -> Path:
    return Path(cache_dir) / f"overlap_{provenance_hash(prov)}.h5"


def cached_overlap(cache_dir, prov: dict) -> OverlapResult | None:
    path = _overlap_path(cache_dir, prov)
    if not path.exists():
        return None
    try:
        result, stored = read_overlap(path)
    except (OSError, KeyError, ValueError):
        return None
    return result if result.complete and stored == prov else None


def store_overlap(cache_dir, result: OverlapResult, prov: dict) -> Path | None:
    """Only complete overlap maps are cached."""
    if not result.complete:
        return None
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    path = _overlap_path(cache_dir, prov)
    write_overlap(path, result, prov)
    return path
