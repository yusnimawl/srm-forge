import math

import numpy as np
import pytest
from conftest import make_8_6

from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design, MeshSettings
from srmcore.model.iron import IronArc
from srmcore.post.cut_edge import B0, CUT_PROCESSES, band_fraction, cut_edges, edge_multiplier
from srmcore.topology.imported import _canonical, parametric_iron, to_segments

MM = 1e-3


def _strip(w, length, h):
    """Right-triangle mesh of [0, length] x [0, w] with spacing h."""
    nx, ny = round(length / h), round(w / h)
    x, y = np.meshgrid(np.arange(nx + 1) * h, np.arange(ny + 1) * h, indexing="ij")
    nodes = np.column_stack([x.ravel(), y.ravel()])
    idx = np.arange((nx + 1) * (ny + 1)).reshape(nx + 1, ny + 1)
    a, b, c, d = idx[:-1, :-1].ravel(), idx[1:, :-1].ravel(), idx[1:, 1:].ravel(), idx[:-1, 1:].ravel()
    return nodes, np.vstack([np.column_stack([a, b, c]), np.column_stack([a, c, d])])


def _areas(nodes, tris):
    p = nodes[tris]
    return 0.5 * np.abs((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1]) - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))


def _kind(static, part):
    return np.array([static.region_kind[n] for n in static.region_names])[part.region_ids]


def test_strip_fraction_matches_band_area():
    for w in (5e-3, 10e-3, 30e-3):
        nodes, tris = _strip(w, 0.05, 0.1e-3)
        d = 0.5e-3
        area = _areas(nodes, tris)
        frac = band_fraction(nodes, tris, d)
        exact = (2 * d * (0.05 + w) - 4 * d * d) / (w * 0.05)
        assert np.sum(frac * area) / area.sum() == pytest.approx(exact, rel=0.01)


def test_strip_multiplier_follows_one_over_w():
    for p in CUT_PROCESSES.values():
        for w in (5e-3, 10e-3, 30e-3):
            length = 0.05
            nodes, tris = _strip(w, length, 0.1e-3)
            area = _areas(nodes, tris)
            m = edge_multiplier(band_fraction(nodes, tris, p.delta), p.a, p.delta)
            ends = p.a / length - p.a * p.delta / (w * length) * 2
            assert np.sum(m * area) / area.sum() * B0 == pytest.approx(1 + p.a / w + ends, rel=0.01)


def test_fraction_limits():
    nodes, tris = _strip(20e-3, 20e-3, 1e-3)
    d = 0.5e-3
    nodes = np.vstack([nodes, [[0.1e-3, 5e-3], [0.3e-3, 5e-3], [0.1e-3, 5.2e-3],        # at an edge
                               [9e-3, 9e-3], [9.3e-3, 9e-3], [9e-3, 9.3e-3],             # far from every edge
                               [0.2e-3, 5e-3], [0.9e-3, 5e-3], [0.2e-3, 5.7e-3]]])      # across the band edge
    n0 = len(nodes) - 9
    extra = np.array([[n0, n0 + 1, n0 + 2], [n0 + 3, n0 + 4, n0 + 5], [n0 + 6, n0 + 7, n0 + 8]])
    # the cut edges come from the strip alone; the extra triangles are only sampled
    seg = cut_edges(nodes[:n0], tris)
    assert seg.shape[1:] == (2, 2)
    f = band_fraction(nodes, np.vstack([tris, extra]), d, cut=seg)[-3:]
    assert f[0] == pytest.approx(1.0) and f[1] == 0.0 and 0 < f[2] < 1 and np.all(np.isfinite(f))


def test_cut_edges_of_8_6_iron_form_closed_loops(srm_8_6):
    static = build_machine_mesh(Design(machine=srm_8_6, mesh=MeshSettings(preset="screening")))
    for part, kind in ((static.stator, "stator_iron"), (static.rotor, "rotor_iron")):
        iron = _kind(static, part) == kind
        seg = cut_edges(part.nodes, part.triangles[iron])
        _, counts = np.unique(np.round(seg.reshape(-1, 2), 12), axis=0, return_counts=True)
        assert np.all(counts == 2)
    seg = cut_edges(static.stator.nodes, static.stator.triangles[_kind(static, static.stator) == "stator_iron"])
    assert np.isclose(np.hypot(*seg.reshape(-1, 2).T).max(), srm_8_6.stator_outer_diameter / 2, rtol=1e-6)


def _circle(cx, cy, r):
    pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)]
    return tuple(IronArc(start=pts[i], end=pts[(i + 1) % 4], center=(cx, cy)) for i in range(4))


def test_imported_iron_hole_edges_are_cut_edges():
    p = make_8_6()
    rh = 2 * MM
    r = (p.shaft_radius + p.rotor_yoke_outer_radius) / 2
    holes = tuple(_canonical(list(to_segments(_circle(r * math.cos(k * math.pi / 3), r * math.sin(k * math.pi / 3), rh))), p)
                  for k in range(6))
    base = parametric_iron(p)
    design = Design(machine=p.model_copy(update={"iron": base.model_copy(update={"rotor_holes": holes})}),
                    mesh=MeshSettings(preset="screening"))
    static = build_machine_mesh(design)
    part = static.rotor
    tris = part.triangles[_kind(static, part) == "rotor_iron"]
    seg = cut_edges(part.nodes, tris)
    pts, counts = np.unique(np.round(seg.reshape(-1, 2), 12), axis=0, return_counts=True)
    assert np.all(counts == 2)
    # points on a hole circle: distance from a hole centre equals the hole radius
    dist = np.min([np.abs(np.hypot(pts[:, 0] - r * math.cos(k * math.pi / 3), pts[:, 1] - r * math.sin(k * math.pi / 3)) - rh)
                   for k in range(6)], axis=0)
    assert np.count_nonzero(dist < 1e-9) > 6 * 8
    assert np.all(np.isfinite(band_fraction(part.nodes, tris, 0.5 * MM)))
