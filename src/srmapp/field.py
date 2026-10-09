"""Static field mesh and single field frames (|B|, A_z, flux linkage, torque, B probes) for the web field view.

The stator and rotor triangles never change with the rotor angle, so the mesh is sent once; a frame carries only
the band triangles and the per-element and per-node values. Both are cached on disk under `<cache_dir>/fields`."""
import hashlib
import json
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from srmcore.maps.dataset import provenance, provenance_hash
from srmcore.maps.point import solve_point
from srmcore.materials.laws import library_law
from srmcore.mesh import build_machine_mesh, mesh_at_angle
from srmcore.mesh.static import StaticMesh
from srmcore.model.design import Design
from srmcore.solvers.factory import make_solver

PROBE_ZONES = ("stator_pole", "stator_yoke", "rotor_pole")


@dataclass(frozen=True)
class RegionInfo:
    name: str
    kind: str
    part: str
    phase: str | None
    sign: int | None


@dataclass(frozen=True, eq=False)
class FieldMesh:
    nodes: np.ndarray               # (n, 2): stator nodes, then rotor nodes at angle 0
    n_stator_nodes: int
    triangles: np.ndarray           # (m, 3): stator, then rotor (offset by n_stator_nodes); no band
    region: np.ndarray              # (m,) index into `regions`
    regions: tuple[RegionInfo, ...]
    b_last: float                   # T, the smaller of the stator and rotor last B-H points
    probes: dict[str, np.ndarray]   # element indices per probe zone


@dataclass(frozen=True, eq=False)
class FieldFrame:
    angle: float                    # mechanical rad
    coil_current: float             # A
    band: np.ndarray                # (k, 3) band triangles
    b: np.ndarray                   # (m + k,) float32 |B|, T
    a: np.ndarray                   # (n,) float32 A_z, Wb/m
    psi: float                      # phase A flux linkage
    torque: float                   # Arkkio, N m
    status: str
    probes: dict[str, float]        # area-weighted mean |B| per zone, T


def field_key(design: Design, solver: str) -> str:
    return provenance_hash(provenance(design, [], [], "A", make_solver(solver)))


def _fields_dir(cache_dir) -> Path:
    d = Path(cache_dir) / "fields"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(path: Path, **arrays) -> None:
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.tmp.npz")
    np.savez_compressed(tmp, **arrays)
    os.replace(tmp, path)


@lru_cache(maxsize=2)
def _static(design_json: str) -> StaticMesh:
    return build_machine_mesh(Design.from_json(design_json))


def _areas(nodes: np.ndarray, tri: np.ndarray) -> np.ndarray:
    p = nodes[tri]
    return 0.5 * np.abs((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                        - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))


def _probe_zones(design: Design, nodes, tri, region, regions) -> dict[str, np.ndarray]:
    m = design.machine
    kind = np.array([regions[i].kind for i in region])
    c = nodes[tri].mean(axis=1)
    r, phi = np.hypot(c[:, 0], c[:, 1]), np.arctan2(c[:, 1], c[:, 0])
    stator = (kind == "stator_iron") & (np.abs(phi) <= m.stator_pole_arc / 2)
    return {
        "stator_pole": np.flatnonzero(stator & (r >= m.bore_radius) & (r < m.stator_yoke_inner_radius)),
        "stator_yoke": np.flatnonzero(stator & (r >= m.stator_yoke_inner_radius)),
        "rotor_pole": np.flatnonzero((kind == "rotor_iron") & (r > m.rotor_yoke_outer_radius)
                                     & (np.abs(phi) <= m.rotor_pole_arc / 2)),
    }


def _mesh_from_static(design: Design, static: StaticMesh) -> FieldMesh:
    ns = len(static.stator.nodes)
    nodes = np.vstack([static.stator.nodes, static.rotor.nodes])
    tri = np.vstack([static.stator.triangles, static.rotor.triangles + ns]).astype(np.int64)
    region = np.concatenate([static.stator.region_ids, static.rotor.region_ids]).astype(np.int64)
    regions = tuple(
        RegionInfo(n, static.region_kind[n], static.region_part[n],
                   static.coils[n].phase if n in static.coils else None,
                   static.coils[n].sign if n in static.coils else None)
        for n in static.region_names)
    mats = design.machine.materials
    b_last = min(library_law(mats.stator).bn, library_law(mats.rotor).bn)
    return FieldMesh(nodes, ns, tri, region, regions, float(b_last), _probe_zones(design, nodes, tri, region, regions))


def _load_mesh(path: Path) -> FieldMesh:
    with np.load(path) as z:
        regions = tuple(RegionInfo(**r) for r in json.loads(str(z["regions"])))
        return FieldMesh(z["nodes"], int(z["n_stator_nodes"]), z["triangles"], z["region"], regions,
                         float(z["b_last"]), {k: z[f"probe_{k}"] for k in PROBE_ZONES})


def field_mesh(design: Design, *, solver: str = "ngsolve", cache_dir=None) -> FieldMesh:
    path = _fields_dir(cache_dir) / f"mesh_{field_key(design, solver)}.npz" if cache_dir is not None else None
    if path is not None and path.exists():
        return _load_mesh(path)
    mesh = _mesh_from_static(design, _static(design.to_json()))
    if path is not None:
        _save(path, nodes=mesh.nodes, n_stator_nodes=mesh.n_stator_nodes, triangles=mesh.triangles,
              region=mesh.region, regions=json.dumps([r.__dict__ for r in mesh.regions]),
              b_last=mesh.b_last, **{f"probe_{k}": v for k, v in mesh.probes.items()})
    return mesh


def rotated_nodes(mesh: FieldMesh, angle: float) -> np.ndarray:
    """The nodes with the rotor turned counter-clockwise by `angle`."""
    c, s = math.cos(angle), math.sin(angle)
    out = mesh.nodes.copy()
    out[mesh.n_stator_nodes:] = out[mesh.n_stator_nodes:] @ np.array([[c, s], [-s, c]])
    return out


def _frame_path(design: Design, angle: float, coil_current: float, solver: str, cache_dir) -> Path:
    key = field_key(design, solver)
    h = hashlib.sha256(f"{key}|{angle!r}|{coil_current!r}".encode()).hexdigest()[:16]
    return _fields_dir(cache_dir) / f"frame_{h}.npz"


def _load_frame(path: Path) -> FieldFrame:
    with np.load(path) as z:
        return FieldFrame(float(z["angle"]), float(z["coil_current"]), z["band"], z["b"], z["a"],
                          float(z["psi"]), float(z["torque"]), str(z["status"]),
                          {k: float(z[f"probe_{k}"]) for k in PROBE_ZONES})


def cached_frame(design: Design, angle: float, coil_current: float, *, solver: str = "ngsolve",
                 cache_dir) -> FieldFrame | None:
    """The stored frame, or None; never solves."""
    path = _frame_path(design, angle, coil_current, solver, cache_dir)
    return _load_frame(path) if path.exists() else None


def field_frame(design: Design, angle: float, coil_current: float, *, solver: str = "ngsolve",
                cache_dir=None) -> FieldFrame:
    if cache_dir is not None and (hit := cached_frame(design, angle, coil_current, solver=solver,
                                                      cache_dir=cache_dir)) is not None:
        return hit
    mesh = field_mesh(design, solver=solver, cache_dir=cache_dir)
    static = _static(design.to_json())
    p = solve_point(static, design, angle, {"A": coil_current}, make_solver(solver, threads=1), keep_field=True)
    b = np.hypot(p.field.b[:, 0], p.field.b[:, 1])
    m = len(mesh.triangles)
    band = mesh_at_angle(static, angle).triangles[m:].astype(np.int64)
    area = _areas(mesh.nodes, mesh.triangles)
    probes = {z: float((b[:m][i] * area[i]).sum() / area[i].sum()) for z, i in mesh.probes.items()}
    frame = FieldFrame(angle, coil_current, band, b.astype(np.float32), p.field.a.astype(np.float32),
                       float(p.psi[0]), float(p.torque_arkkio), p.status.value, probes)
    if cache_dir is not None:
        _save(_frame_path(design, angle, coil_current, solver, cache_dir), angle=angle, coil_current=coil_current,
              band=frame.band, b=frame.b, a=frame.a, psi=frame.psi, torque=frame.torque, status=frame.status,
              **{f"probe_{k}": v for k, v in probes.items()})
    return frame
