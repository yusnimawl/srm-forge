"""Field of a machine over one stroke with every phase carrying current: B(t) per iron and coil element.

The stator is periodic over one rotor pole pitch tau. A rotor element sees the stator field move past it, and
its own period is `rotor_pitches` pitches: the field at t + tau on a rotor point phi equals the field at t on the
point phi + tau, rotated by tau. So the rotor waveform over several pitches is assembled from one pitch of solves
by locating the rotated centroid in the rotor mesh. The stator waveforms keep one pitch as their period."""
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from ..fields.solution import SolveStatus
from ..mesh.band import snap_angle
from ..mesh.static import StaticMesh
from ..model.design import Design
from ..model.errors import MapFailed
from ..solvers.factory import make_solver
from .dataset import provenance, provenance_hash
from .point import solve_point
from .pool import default_workers, map_ordered
from .run import _init_worker, _WORKER

DEFAULT_STROKE_ANGLES = 60
# Candidate rotor triangles tested per located point.
_NEAREST = 12


@dataclass(frozen=True, eq=False)
class IronWaveforms:
    """B per iron element of the stator or the rotor over one period, in the part's own frame. Samples are
    uniform in time up to the snapping of the angles to the band pitch."""
    b: np.ndarray                 # (n_samples, n_el, 2) T
    pitches: int                  # period in rotor pole pitches
    pitch: float                  # rotor pole pitch tau, rad
    centroids: np.ndarray         # (n_el, 2) m
    areas: np.ndarray             # (n_el,) m²
    region: np.ndarray            # (n_el,) "stator_pole" and "stator_yoke", or "rotor_pole" and "rotor_yoke"
    material: np.ndarray          # (n_el,) material name

    def period_s(self, omega: float) -> float:
        """Period of the waveforms at rotor speed `omega` (rad/s)."""
        return self.pitches * self.pitch / omega


@dataclass(frozen=True, eq=False)
class StrokeFields:
    """Fields over a stroke: the stator iron over one rotor pole pitch (n_t samples), the rotor iron over
    `rotor.pitches` pitches (n_t * pitches samples), the coil elements over one pitch. B is the finite-element
    (stack-averaged) flux density."""
    angles: np.ndarray            # (n_t,) rotor angle of each sample of the first pitch, rad
    stator: IronWaveforms
    rotor: IronWaveforms
    b_coil: np.ndarray            # (n_t, n_coil, 2) T, stator frame
    coil_side: np.ndarray         # (n_coil,) coil region name
    coil_areas: np.ndarray        # (n_coil,) m²


def stroke_angles(static: StaticMesh, period: float, n: int = DEFAULT_STROKE_ANGLES) -> np.ndarray:
    """n angles evenly over [0, period) snapped to the band pitch, without duplicates."""
    divisions = static.settings.band_divisions
    snapped = {snap_angle(t, divisions)[1] for t in np.arange(n) * period / n}
    return np.array(sorted(snapped)) * (2 * math.pi / divisions)


def phase_currents(i_a: np.ndarray, n_phases: int) -> np.ndarray:
    """(n_t, q) currents: phase j is phase A delayed by j·n_t/q samples (periodic linear interpolation when
    n_t/q is not an integer), as in the drive envelope's line current."""
    i_a = np.asarray(i_a, dtype=float)
    n = i_a.shape[0]
    out = np.zeros((n, n_phases))
    for j in range(n_phases):
        a, f = divmod(j * n / n_phases, 1.0)
        a = int(a)
        out[:, j] = (1 - f) * np.roll(i_a, a) + f * np.roll(i_a, a + 1)
    return out


def _triangle_geometry(nodes: np.ndarray, triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    t = nodes[triangles]
    centroid = t.mean(axis=1)
    area = 0.5 * np.abs((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1])
                        - (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1]))
    return centroid, area


def _rot(phi: float) -> np.ndarray:
    """Matrix R with v @ R the row vector v rotated counter-clockwise by phi."""
    c, s = math.cos(phi), math.sin(phi)
    return np.array([[c, s], [-s, c]])


def _pole_data(static: StaticMesh, n_poles: int) -> tuple[np.ndarray, np.ndarray]:
    """Phase index and winding polarity (+1/-1) of every stator pole. The polarity is the sign of the coil side
    on the counter-clockwise flank of the pole (the sides of one pole carry opposite signs)."""
    phase = np.zeros(n_poles, dtype=int)
    polarity = np.zeros(n_poles, dtype=int)
    pitch = 2 * math.pi / n_poles
    for name, info in static.coils.items():
        rid = static.region_names.index(name)
        tri = static.stator.triangles[static.stator.region_ids == rid]
        centre = static.stator.nodes[tri].reshape(-1, 2).mean(axis=0)
        offset = (math.atan2(centre[1], centre[0]) - info.pole * pitch + math.pi) % (2 * math.pi) - math.pi
        phase[info.pole] = ord(info.phase) - ord("A")
        if offset > 0:
            polarity[info.pole] = info.sign
    if np.any(polarity == 0):
        raise ValueError("a stator pole has no coil side on its counter-clockwise flank")
    return phase, polarity


def rotor_pitches(static: StaticMesh, design: Design) -> int:
    """Rotor pole pitches after which a rotor element's flux density repeats.

    Rotating the machine by rho stator pole pitches maps pole p to p + rho. If that keeps every pole's phase and
    carries the winding polarity to a fixed multiple sigma = ±1 of itself, and rho·Nr/Ns is a whole number K of
    rotor pitches, the field repeats after K pitches (sigma = +1) or 2K pitches (sigma = -1, where it returns
    inverted after K). The smallest such period is returned; one full turn (Nr pitches) always qualifies."""
    p = design.machine
    ns, nr = p.n_stator_poles, p.n_rotor_poles
    phase, polarity = _pole_data(static, ns)
    best = nr
    for rho in range(1, ns + 1):
        if (rho * nr) % ns:
            continue
        shifted = np.roll(np.arange(ns), -rho)
        if np.any(phase[shifted] != phase):
            continue
        ratio = polarity[shifted] * polarity
        if not np.all(ratio == ratio[0]):
            continue
        best = min(best, rho * nr // ns * (2 if ratio[0] < 0 else 1))
    return best


def _locate(tree: cKDTree, tri_nodes: np.ndarray, points: np.ndarray) -> np.ndarray:
    """For each point the index of the triangle (rows of `tri_nodes`, (m, 3, 2)) that contains it, or the
    nearby triangle it is closest to lying in (largest smallest barycentric coordinate)."""
    _, cand = tree.query(points, k=min(_NEAREST, tri_nodes.shape[0]))
    t = tri_nodes[cand]                                    # (n, k, 3, 2)
    a, b, c = t[:, :, 0], t[:, :, 1], t[:, :, 2]
    d = (b[..., 1] - c[..., 1]) * (a[..., 0] - c[..., 0]) + (c[..., 0] - b[..., 0]) * (a[..., 1] - c[..., 1])
    x, y = points[:, None, 0] - c[..., 0], points[:, None, 1] - c[..., 1]
    l1 = ((b[..., 1] - c[..., 1]) * x + (c[..., 0] - b[..., 0]) * y) / d
    l2 = ((c[..., 1] - a[..., 1]) * x + (a[..., 0] - c[..., 0]) * y) / d
    inside = np.minimum(np.minimum(l1, l2), 1 - l1 - l2)
    return cand[np.arange(len(points)), np.argmax(inside, axis=1)]


def _solve_job(job):
    angle, currents = job
    r = solve_point(_WORKER["static"], _WORKER["design"], angle, currents, _WORKER["solver"], keep_field=True)
    return r.status, (None if r.status is SolveStatus.NONCONVERGED else r.field.b)


def _key(design, angles, currents, solver) -> str:
    return provenance_hash(provenance(design, angles, np.asarray(currents).ravel(),
                                      f"stroke{np.shape(currents)}", solver))


def stroke_key(design: Design, angles: np.ndarray, currents: np.ndarray, solver: str = "ngsolve") -> str:
    """File stem of the cached fields of `stroke_fields` with these arguments (`<cache_dir>/strokes/<key>.npz`)."""
    return _key(design, np.asarray(angles, dtype=float), np.asarray(currents, dtype=float), make_solver(solver))


def _cache_path(cache_dir, design, angles, currents, solver) -> Path:
    return Path(cache_dir) / "strokes" / f"{_key(design, angles, currents, solver)}.npz"


def _raw_fields(static, design, angles, currents, solver, workers, progress, cancel):
    """Per angle B on the stator iron (stator frame), rotor iron (rotor frame) and coil elements (stator frame)."""
    circuits = tuple(chr(ord("A") + k) for k in range(design.machine.n_phases))
    jobs = [(float(a), dict(zip(circuits, map(float, row)))) for a, row in zip(angles, currents)]
    rows = map_ordered(_solve_job, jobs, workers=workers, initializer=_init_worker,
                       initargs=(static, design, solver, 1 if workers > 1 else None),
                       cancel=cancel, progress=progress)
    if any(r is None for r in rows):
        raise InterruptedError("stroke solve cancelled")
    for angle, (status, _) in zip(angles, rows):
        if status is SolveStatus.NONCONVERGED:
            raise MapFailed([f"the solve at rotor angle {math.degrees(angle):.4f} deg did not converge"], 1)
    return np.stack([b for _, b in rows])                 # (n_t, n_triangles, 2)


def stroke_fields(static: StaticMesh, design: Design, angles: np.ndarray, currents: np.ndarray, *,
                  solver: str = "ngsolve", workers: int | None = None, cache_dir=None,
                  progress: Callable[[int, int], None] | None = None,
                  cancel: Callable[[], bool] | None = None) -> StrokeFields:
    """B(t) over a stroke. `angles` (n_t,) cover one rotor pole pitch [0, tau) and `currents` (n_t, n_phases)
    are the coil currents per phase at those angles (see `phase_currents`). Raises MapFailed naming the angle
    of a point that did not converge and InterruptedError when `cancel` fires. With `cache_dir`, the solved fields are stored under `strokes/`."""
    p = design.machine
    angles = np.asarray(angles, dtype=float)
    currents = np.asarray(currents, dtype=float)
    if currents.shape != (len(angles), p.n_phases):
        raise ValueError(f"currents must have shape ({len(angles)}, {p.n_phases}), got {currents.shape}")
    tau = 2 * math.pi / p.n_rotor_poles
    adapter = make_solver(solver)
    path = None if cache_dir is None else _cache_path(cache_dir, design, angles, currents, adapter)
    loaded = None
    if path is not None and path.exists():
        try:
            with np.load(path) as f:
                loaded = f["stator"], f["coil"], f["rotor"]
        except (OSError, ValueError, KeyError):
            loaded = None

    n_s_tri, n_r_tri = len(static.stator.triangles), len(static.rotor.triangles)
    kind_s = np.array([static.region_kind[n] for n in static.region_names])[static.stator.region_ids]
    kind_r = np.array([static.region_kind[n] for n in static.region_names])[static.rotor.region_ids]
    s_iron, r_iron, s_coil = kind_s == "stator_iron", kind_r == "rotor_iron", kind_s == "coil"
    if loaded is None:
        raw = _raw_fields(static, design, angles, currents, solver,
                          default_workers(workers, len(angles)), progress, cancel)
        loaded = (raw[:, :n_s_tri][:, s_iron], raw[:, :n_s_tri][:, s_coil],
                  raw[:, n_s_tri:n_s_tri + n_r_tri][:, r_iron])
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.stem}.{os.getpid()}.tmp.npz")
            try:
                np.savez_compressed(tmp, stator=loaded[0], coil=loaded[1], rotor=loaded[2])
                os.replace(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)
    b_stator, b_coil, b_rotor_global = loaded
    stator, rotor = iron_waveforms(static, design, angles, b_stator, b_rotor_global)
    _, as_ = _triangle_geometry(static.stator.nodes, static.stator.triangles)
    names = np.array(static.region_names)[static.stator.region_ids]
    return StrokeFields(angles=angles, stator=stator, rotor=rotor, b_coil=b_coil, coil_side=names[s_coil],
                        coil_areas=as_[s_coil])


def iron_waveforms(static: StaticMesh, design: Design, angles: np.ndarray, b_stator: np.ndarray,
                   b_rotor_global: np.ndarray) -> tuple[IronWaveforms, IronWaveforms]:
    """The stator and rotor `IronWaveforms` from the solved B of the iron elements: `b_stator` (n_t, n_stator_iron, 2)
    in the stator frame and `b_rotor_global` (n_t, n_rotor_iron, 2) in the stator frame at the rotor angles
    `angles`. The rotor B is rotated into the rotor frame and extended over its period."""
    p = design.machine
    tau = 2 * math.pi / p.n_rotor_poles
    kind_s = np.array([static.region_kind[n] for n in static.region_names])[static.stator.region_ids]
    kind_r = np.array([static.region_kind[n] for n in static.region_names])[static.rotor.region_ids]
    s_iron, r_iron = kind_s == "stator_iron", kind_r == "rotor_iron"
    cs, as_ = _triangle_geometry(static.stator.nodes, static.stator.triangles)
    cr, ar = _triangle_geometry(static.rotor.nodes, static.rotor.triangles)
    # Rotor-frame B at the first pitch: the global vector rotated back by the rotor angle.
    b_rotor = np.empty_like(b_rotor_global)
    for k, a in enumerate(angles):
        b_rotor[k] = b_rotor_global[k] @ _rot(-(a % (2 * math.pi)))
    k_pitch = rotor_pitches(static, design)
    rotor_c = cr[r_iron]
    tree = cKDTree(rotor_c)
    tri_nodes = static.rotor.nodes[static.rotor.triangles[r_iron]]
    blocks = [b_rotor]
    for j in range(1, k_pitch):
        src = _locate(tree, tri_nodes, rotor_c @ _rot(j * tau))
        blocks.append(b_rotor[:, src] @ _rot(-j * tau))

    n_s, n_r = int(s_iron.sum()), int(r_iron.sum())
    radius_s = np.hypot(*cs[s_iron].T)
    radius_r = np.hypot(*cr[r_iron].T)
    return (IronWaveforms(b_stator, 1, tau, cs[s_iron], as_[s_iron],
                          np.where(radius_s < p.stator_yoke_inner_radius, "stator_pole", "stator_yoke"),
                          np.array([p.materials.stator] * n_s)),
            IronWaveforms(np.concatenate(blocks, axis=0), k_pitch, tau, rotor_c, ar[r_iron],
                          np.where(radius_r > p.rotor_yoke_outer_radius, "rotor_pole", "rotor_yoke"),
                          np.array([p.materials.rotor] * n_r)))
