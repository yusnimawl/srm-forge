"""Steady thermal solve: P1 conduction in the domain coupled to lumps, one sparse factorisation reused per iteration."""
from typing import Callable

import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import splu

from .model import (AreaLink, EdgeLink, LumpLink, Temperatures, ThermalLoad, ThermalModelError, ThermalProblem,
                    ThermalRunaway)

RUNAWAY_C = 1000.0
LoadFn = Callable[[Temperatures | None], ThermalLoad]


def _areas_and_gradients(nodes: np.ndarray, tri: np.ndarray):
    p = nodes[tri]
    e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    # rows of the inverse transpose give the gradients of the barycentric functions
    g1 = np.stack([e2[:, 1], -e2[:, 0]], axis=1) / det[:, None]
    g2 = np.stack([-e1[:, 1], e1[:, 0]], axis=1) / det[:, None]
    grads = np.stack([-g1 - g2, g1, g2], axis=1)
    return np.abs(det) / 2, grads


def _add(rows, cols, vals, r, c, v):
    rows.append(np.asarray(r).ravel())
    cols.append(np.asarray(c).ravel())
    vals.append(np.asarray(v, dtype=float).ravel())


class ThermalSolver:
    def __init__(self, problem: ThermalProblem):
        d = problem.domain
        m, n = len(d.triangles), len(d.nodes)
        if len(problem.conductivity) != m or len(problem.capacity) != m:
            raise ThermalModelError("conductivity and capacity need one value per element")
        if np.any(~(np.asarray(problem.conductivity) > 0)):
            raise ThermalModelError("conductivity must be positive")
        if not problem.depth > 0:
            raise ThermalModelError("depth must be positive")
        names = [lump.name for lump in problem.lumps]
        if len(set(names)) != len(names):
            raise ThermalModelError("duplicate lump name")
        self.problem, self._n, self._names = problem, n, names
        self._index = {nm: n + i for i, nm in enumerate(names)}
        N = n + len(names)
        self._area, grads = _areas_and_gradients(d.nodes, d.triangles)
        rows, cols, vals = [], [], []
        ke = (problem.depth * problem.conductivity * self._area)[:, None, None] * np.einsum("eik,ejk->eij", grads, grads)
        _add(rows, cols, vals, np.repeat(d.triangles[:, :, None], 3, 2), np.repeat(d.triangles[:, None, :], 3, 1), ke)

        mass = np.full((3, 3), 1 / 12) + np.eye(3) / 12   # consistent P1 triangle mass / area
        edge_mass = np.array([[2, 1], [1, 2]]) / 6        # consistent P1 edge mass / length
        for link in problem.links:
            if isinstance(link, LumpLink):
                a, b = self._lump(link.a), self._lump(link.b)
                if not link.conductance > 0:
                    raise ThermalModelError(f"conductance of link {link.a}-{link.b} must be positive")
                g = link.conductance
                _add(rows, cols, vals, [a, b, a, b], [a, b, b, a], [g, g, -g, -g])
                continue
            lump = self._lump(link.lump)
            coef = link.h if isinstance(link, EdgeLink) else link.g
            if not coef > 0:
                raise ThermalModelError(f"coefficient of link to {link.lump} must be positive")
            if isinstance(link, EdgeLink):
                nod = np.asarray(link.edges)
                p = d.nodes[nod]
                w = coef * problem.depth * np.hypot(*(p[:, 1] - p[:, 0]).T)
                m_loc, size = edge_mass, 2
            else:
                nod = d.triangles[np.asarray(link.elements)]
                w = coef * self._area[np.asarray(link.elements)]
                m_loc, size = mass, 3
            _add(rows, cols, vals, np.repeat(nod[:, :, None], size, 2), np.repeat(nod[:, None, :], size, 1),
                 w[:, None, None] * m_loc)
            share = (w / size)[:, None] * np.ones(size)
            _add(rows, cols, vals, nod, np.full(nod.shape, lump), -share)
            _add(rows, cols, vals, np.full(nod.shape, lump), nod, -share)
            _add(rows, cols, vals, [lump], [lump], [w.sum()])
        self._a = sp.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                                shape=(N, N)).tocsr()
        fixed = np.array([lump.fixed_c is not None for lump in problem.lumps], dtype=bool)
        self._fixed = n + np.flatnonzero(fixed)
        self._free = np.concatenate([np.arange(n), n + np.flatnonzero(~fixed)])
        self._t_fixed = np.array([problem.lumps[i].fixed_c for i in np.flatnonzero(fixed)], dtype=float)
        self._lu = None

    def _lump(self, name: str) -> int:
        if name not in self._index:
            raise ThermalModelError(f"unknown lump {name!r}")
        return self._index[name]

    def _check_anchored(self):
        a = self._a
        _, label = connected_components(abs(a) > 0, directed=False)
        anchored = set(label[self._fixed])
        d, n = self.problem.domain, self._n
        ns = len(d.stator_elements)
        for c in sorted(set(label) - anchored):
            members = np.flatnonzero(label == c)
            if np.isin(members, np.unique(d.triangles[:ns])).any():
                what = "stator"
            elif (members < n).any():
                what = "rotor"
            else:
                what = self._names[members[0] - n]
            raise ThermalModelError(f"{what} has no path to a fixed-temperature lump")

    def _factorise(self):
        if self._lu is None:
            self._check_anchored()
            self._lu = splu(self._a[self._free][:, self._free].tocsc())
            self._a_fix = self._a[self._free][:, self._fixed]

    def _rhs(self, load: ThermalLoad) -> np.ndarray:
        d = self.problem.domain
        q = np.asarray(load.element_w_per_m3, dtype=float)
        if len(q) != len(d.triangles):
            raise ThermalModelError("load needs one value per element")
        b = np.zeros(self._a.shape[0])
        np.add.at(b, d.triangles, np.repeat((self.problem.depth * q * self._area / 3)[:, None], 3, 1))
        for name, w in load.lump_w.items():
            b[self._lump(name)] += w
        return b

    def _unpack(self, x: np.ndarray) -> Temperatures:
        full = np.zeros(self._a.shape[0])
        full[self._free] = x
        full[self._fixed] = self._t_fixed
        return Temperatures(full[:self._n].copy(), {nm: float(full[self._n + i]) for i, nm in enumerate(self._names)})

    def steady(self, load: LoadFn, tol_k: float = 0.01, max_iter: int = 50) -> Temperatures:
        self._factorise()
        prev = None
        for _ in range(max_iter):
            b = self._rhs(load(prev))[self._free] - self._a_fix @ self._t_fixed
            t = self._unpack(self._lu.solve(b))
            peak = max(t.field.max(), *t.lumps.values()) if t.lumps else t.field.max()
            if not peak < RUNAWAY_C:
                raise ThermalRunaway(f"temperature passed {RUNAWAY_C:g} degC")
            if prev is not None and max(np.abs(t.field - prev.field).max(),
                                        *(abs(v - prev.lumps[k]) for k, v in t.lumps.items()), 0.0) < tol_k:
                return t
            prev = t
        raise ThermalRunaway(f"no steady state within {max_iter} iterations")

    def heat_to_fixed(self, t: Temperatures) -> dict[str, float]:
        x = np.concatenate([t.field, [t.lumps[nm] for nm in self._names]])
        out = self._a[self._fixed] @ x
        return {self._names[i - self._n]: float(-v) for i, v in zip(self._fixed, out)}
