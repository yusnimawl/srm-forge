"""Swept (layered) prism meshes: a 2D cross-section triangulation stacked in z layers."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

import ngsolve as ng
import numpy as np
from netgen.meshing import Element2D, Element3D, FaceDescriptor, Mesh, MeshPoint, Pnt


@dataclass(frozen=True)
class Layers:
    """Increasing layer boundaries in z, starting at 0."""
    z: tuple[float, ...]

    @property
    def n(self) -> int:
        return len(self.z) - 1


def _graded(length: float, first: float, cap: float, ratio: float) -> list[float]:
    """Steps over `length`: the first is exactly `first` (or all of `length` if shorter); later ones grow by at
    most `ratio`, capped at `cap`. The steps that fit are scaled to fill the length: up when the remainder is
    below half a step (no sliver layer) as long as that keeps the growth within `ratio`, down otherwise."""
    if length <= first * (1 + 1e-9):
        return [length]
    steps, total = [first], first
    while total < length - 1e-12:
        steps.append(min(steps[-1] * ratio, cap))
        total += steps[-1]
    fits = steps[:-1] if len(steps) > 2 and length - (total - steps[-1]) < 0.5 * steps[-1] else None
    for cand in (fits, steps):
        if cand is None or len(cand) < 2:
            continue
        scale = (length - first) / sum(cand[1:])
        out = [first] + [x * scale for x in cand[1:]]
        if all(b <= ratio * a * (1 + 1e-9) for a, b in zip(out, out[1:])):
            return out
    return [first] + [x * (length - first) / sum(steps[1:]) for x in steps[1:]]


def graded_layers(z_end: float, z_top: float, h_end: float, h_mid: float, ratio: float = 1.3,
                  breaks: Sequence[float] = (), h_far: float | None = None) -> Layers:
    """Layer boundaries on [0, z_top] with a boundary at z_end and at every value in `breaks`.

    The spacing is h_end next to z_end on both sides and grows by at most `ratio` per layer away from it
    (across breaks too), capped at h_mid below the last break (or z_end) and at `h_far` (default 4 h_mid)
    above it. Layers shrink only where a segment is cut short by a break or an end.
    """
    if any(not z_end < b < z_top for b in breaks):
        raise ValueError(f"breaks {tuple(breaks)} must lie strictly between z_end {z_end} and z_top {z_top}")
    h_far = 4 * h_mid if h_far is None else h_far
    far_start = max(breaks, default=z_end)
    down = [z_end]
    for s in _graded(z_end, h_end, h_mid, ratio):
        down.append(down[-1] - s)
    z = [0.0, *reversed(down[1:-1]), z_end]
    up, step = z_end, h_end
    for target in sorted({z_top, *breaks} - {z_end}):
        first = h_end if up == z_end else min(h_far if up >= far_start else h_mid, step * ratio)
        for s in _graded(target - up, first, h_far if up >= far_start else h_mid, ratio):
            up += s
            z.append(up)
            step = s
        z[-1] = up = target
    return Layers(tuple(z))


def _section(mesh2d):
    pts = np.array([[p.p[0], p.p[1]] for p in mesh2d.Points()])
    tris, region = [], []
    for e in mesh2d.Elements2D():
        v = [x.nr - 1 for x in e.vertices]
        if (pts[v[1]] - pts[v[0]])[0] * (pts[v[2]] - pts[v[0]])[1] - (pts[v[1]] - pts[v[0]])[1] * (pts[v[2]] - pts[v[0]])[0] < 0:
            v[1], v[2] = v[2], v[1]
        tris.append(v)
        region.append(mesh2d.GetMaterial(e.index))
    edges = {}
    for s in mesh2d.Elements1D():
        name = mesh2d.GetBCName(s.index - 1)
        edges[frozenset(x.nr - 1 for x in s.vertices)] = None if name == "default" else name
    return pts, np.array(tris), region, edges


def swept_mesh(section, layers: Layers,
               material: Callable[[str, int], str | None],
               faces: Callable[[str, int], str | None],
               bottom: Callable[[str], str],
               top: Callable[[str], str | None]) -> ng.Mesh:
    """Stack the 2D `section` (a netgen 2D mesh with named regions and edges) into prisms.

    `material(region, k)` is the 3D material of a region in layer k (None: no cell). `faces(edge, k)` names the
    vertical face swept from a named 2D edge in layer k (None: no boundary element on an internal face). A cell
    face with no neighbour is named by `bottom`/`top` (horizontal) or `faces` (vertical); an exposed face that
    gets no name raises ValueError, so the mesh has no natural-condition boundary by accident.
    """
    pts, tris, region, edges = _section(section)
    m = Mesh(dim=3)
    ids: dict[tuple[int, int], object] = {}

    def vid(v, lev):
        if (v, lev) not in ids:
            ids[(v, lev)] = m.Add(MeshPoint(Pnt(pts[v][0], pts[v][1], layers.z[lev])))
        return ids[(v, lev)]

    def xyz(v, lev):
        return np.array([pts[v][0], pts[v][1], layers.z[lev]])

    domains: dict[str, int] = {}
    cells = {}      # (t, k) -> domain index
    for t, r in enumerate(region):
        for k in range(layers.n):
            name = material(r, k)
            if name is not None:
                cells[(t, k)] = domains.setdefault(name, len(domains) + 1)
    for name, d in domains.items():
        m.SetMaterial(d, name)

    # face key (sorted (vertex, level) tuple) -> [(cell, kind, ordered (vertex, level) list)]
    owner: dict[tuple, list] = {}
    for (t, k), d in cells.items():
        v = tris[t]
        lo, hi = [(int(x), k) for x in v], [(int(x), k + 1) for x in v]
        m.Add(Element3D(d, [vid(*q) for q in lo + hi]))
        quads = [[lo[i], lo[(i + 1) % 3], hi[(i + 1) % 3], hi[i]] for i in range(3)]
        for kind, ring in [("bottom", lo), ("top", hi)] + [(("side", i), q) for i, q in enumerate(quads)]:
            owner.setdefault(tuple(sorted(ring)), []).append(((t, k), kind, ring))

    fds: dict[str, int] = {}     # one face descriptor per name: NGSolve indexes boundaries by descriptor
    for found in owner.values():
        if len(found) > 2:
            raise ValueError("a face with more than two cells")
        cell, kind, ring = found[0]
        t, k = cell
        exposed = len(found) == 1
        if kind == "bottom" or kind == "top":
            name = (bottom if kind == "bottom" else top)(region[t]) if exposed else None
        else:
            edge = edges.get(frozenset(q[0] for q in ring))
            name = faces(edge, k) if edge is not None else None
        if name is None:
            if exposed:
                raise ValueError(f"exposed {kind} face of region {region[t]!r} in layer {k} has no name")
            continue
        domin = cells[cell]
        domout = 0 if exposed else cells[found[1][0]]
        p = [xyz(*q) for q in ring]
        outward = np.mean(p, axis=0) - np.mean([xyz(int(x), lev) for x in tris[t] for lev in (k, k + 1)], axis=0)
        if np.dot(np.cross(p[1] - p[0], p[2] - p[0]), outward) < 0:
            ring = ring[::-1]
        if name not in fds:
            fds[name] = m.Add(FaceDescriptor(surfnr=len(fds) + 1, domin=domin, domout=domout, bc=len(fds) + 1))
            m.SetBCName(len(fds) - 1, name)
        m.Add(Element2D(fds[name], [vid(*q) for q in ring]))
    return ng.Mesh(m)
