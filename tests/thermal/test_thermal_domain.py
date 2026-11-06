import numpy as np
import pytest
from conftest import make_8_6

from srmcore.maps.end_winding import coil_geometry
from srmcore.mesh.static import build_static_mesh
from srmcore.model.design import Design, MeshSettings
from srmcore.thermal.domain import EXCLUDED_REGIONS, thermal_domain
from srmcore.topology.imported import parametric_iron


def _areas(nodes, tri):
    p = nodes[tri]
    return 0.5 * np.abs((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                        - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))


def _build(machine, **mesh):
    static = build_static_mesh(Design(machine=machine, mesh=MeshSettings(**mesh)))
    return static, thermal_domain(static, machine)


@pytest.fixture(scope="module")
def case():
    machine = make_8_6()
    return (machine, *_build(machine))


def test_gap_regions_removed(case):
    _, static, dom = case
    names = static.region_names
    excluded = {i for i, n in enumerate(names) if n in EXCLUDED_REGIONS}
    n_ex = sum(np.isin(part.region_ids, list(excluded)).sum() for part in (static.stator, static.rotor))
    total = len(static.stator.triangles) + len(static.rotor.triangles)
    assert n_ex > 0
    assert len(dom.triangles) == total - n_ex
    kept = np.concatenate([static.stator.region_ids[dom.stator_elements],
                           static.rotor.region_ids[dom.rotor_elements]])
    assert not np.isin(kept, list(excluded)).any()


def test_em_rows_map_one_to_one(case):
    _, static, dom = case
    q = np.arange(len(static.stator.triangles), dtype=float)
    out = dom.from_em(q, np.zeros(len(static.rotor.triangles)))
    ns = len(dom.stator_elements)
    assert np.array_equal(out[:ns], dom.stator_elements)
    for e in (0, ns // 2, ns - 1):
        em = static.stator.nodes[static.stator.triangles[int(out[e])]]
        assert np.allclose(dom.nodes[dom.triangles[e]], em)
    for e in (ns, len(dom.triangles) - 1):
        em = static.rotor.nodes[static.rotor.triangles[dom.rotor_elements[e - ns]]]
        assert np.allclose(dom.nodes[dom.triangles[e]], em)


def test_outer_edges_lie_on_the_od(case):
    machine, _, dom = case
    seg = dom.nodes[dom.outer_edges]
    length = np.linalg.norm(seg[:, 1] - seg[:, 0], axis=1).sum()
    assert length == pytest.approx(2 * np.pi * machine.stator_outer_radius, rel=5e-3)


def test_rotor_edges_close(case):
    _, _, dom = case
    deg = np.bincount(dom.rotor_edges.ravel())
    assert (deg[np.unique(dom.rotor_edges)] == 2).all()


def test_liner_band_area(case):
    # two pole-side walls of thickness t per coil, plus the yoke band across the whole slot
    machine, _, dom = case
    g = coil_geometry(machine)
    t, f = machine.slot_liner_thickness, machine.stator_fillet_radius
    r_out = machine.stator_yoke_inner_radius - 2 * f - t
    half = machine.stator_pole_arc / 2
    pole_w = 2 * (machine.bore_radius * np.sin(half)
                  + (r_out - machine.bore_radius * np.cos(half)) * np.tan(machine.stator_pole_taper))
    slot_w = 2 * np.pi * r_out / machine.n_stator_poles - pole_w
    expect = machine.n_stator_poles * (2 * t * g.depth + (t + 2 * f) * slot_w)
    area = _areas(dom.nodes, dom.triangles)[dom.element_kind == "liner"].sum()
    assert area == pytest.approx(expect, rel=0.25)


def test_slot_centre_is_not_liner(case):
    _, _, dom = case
    assert (dom.element_kind == "air").any()
    c = dom.nodes[dom.triangles].mean(axis=1)
    liner_r = np.hypot(*c[dom.element_kind == "liner"].T)
    coil_r = np.hypot(*c[dom.element_kind == "coil"].T)
    assert liner_r.min() < coil_r.min() or liner_r.max() > coil_r.max()
    assert set(dom.coil_elements) == {n for n, k in case[1].region_kind.items() if k == "coil"}
    assert all((dom.element_kind[v] == "coil").all() for v in dom.coil_elements.values())


def test_imported_iron_builds():
    machine = make_8_6()
    machine = machine.model_copy(update={"iron": parametric_iron(machine)})
    static, dom = _build(machine)
    assert {"stator_iron", "rotor_iron", "shaft", "coil", "liner"} <= set(dom.element_kind)
    assert len(dom.outer_edges) > 0 and len(dom.rotor_edges) > 0


def test_outer_air_design_keeps_outer_edges(case):
    machine = case[0]
    _, dom = _build(machine, outer_air_thickness=0.02)
    seg = dom.nodes[dom.outer_edges]
    length = np.linalg.norm(seg[:, 1] - seg[:, 0], axis=1).sum()
    assert length == pytest.approx(2 * np.pi * machine.stator_outer_radius, rel=5e-3)
    assert np.allclose(np.hypot(*dom.nodes[dom.outer_edges.ravel()].T), machine.stator_outer_radius, rtol=1e-6)
