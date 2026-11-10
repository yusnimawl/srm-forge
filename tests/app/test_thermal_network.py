import math

import numpy as np
import pytest
from conftest import make_8_6

from srmapp.cooling import CoolingSetup, EndSpray, Jacket, MissingCoolingData, SlotOil, coefficients
from srmapp.sizing.estimates import coil_side_area
from srmapp.sizing.winding import Winding
from srmapp.thermal_network import _edge_keys, _tri_area, build_network
from srmcore.mesh.static import build_static_mesh
from srmcore.model.design import Design, MeshSettings
from srmcore.model.iron import IronArc
from srmcore.thermal.domain import thermal_domain
from srmcore.thermal.model import Lump, ThermalLoad, ThermalProblem
from srmcore.thermal.solve import ThermalSolver
from srmcore.topology.imported import _canonical, parametric_iron, to_segments

M = make_8_6()
M = getattr(M, "machine", M)
STATIC = build_static_mesh(Design(machine=M, mesh=MeshSettings(preset="screening")))
DOM = thermal_domain(STATIC, M)
TURNS, CU = 20, 2e-6
FILL = TURNS * CU / coil_side_area(M)
W = Winding(turns=TURNS, strands=1, copper_area=CU, current=10.0, resistance=0.1, copper_mass=1.0, wire=None)


def net(setup=CoolingSetup(), machine=M, dom=DOM, **kw):
    co = coefficients(setup, machine, 3000.0, frozenset(), None, fill=FILL)
    return build_network(dom, machine, W, FILL, co, setup, **kw), co


def coil_load(n, q=1e6):
    q_el = np.zeros(len(DOM.triangles))
    q_el[DOM.element_kind == "coil"] = q
    return lambda _t: ThermalLoad(q_el)


def test_every_part_anchored():
    n, _ = net()
    s = ThermalSolver(n.problem)
    t = s.steady(lambda _t: ThermalLoad(np.zeros(len(DOM.triangles))))
    # no load: everything sits between the two fixed temperatures (ambient 40, coolant inlet 65)
    assert max(t.field.max(), *t.lumps.values()) <= 65.0 + 1e-6 and min(t.field.min(), *t.lumps.values()) >= 40.0 - 1e-6


def test_energy_balance_and_coolant_rise():
    n, co = net()
    s = ThermalSolver(n.problem)
    t = s.steady(coil_load(len(DOM.triangles)))
    p = n.problem
    area = _tri_area(DOM.nodes, DOM.triangles)
    q_in = 1e6 * area[DOM.element_kind == "coil"].sum() * p.depth
    out = s.heat_to_fixed(t)
    assert sum(out.values()) == pytest.approx(q_in, rel=1e-9)
    f = co.jacket_fluid
    rise = t.lumps["coolant"] - 65.0
    assert rise == pytest.approx(out["coolant_in"] / (2 * co.jacket_flow_m3s * f.density * f.specific_heat), rel=1e-9)


def test_liner_conductance():
    n, co = net()
    p = n.problem
    dom = p.domain
    kind = dom.element_kind
    # test-only problem: coil nodes held at 100 via a fixed lump, iron at 0 via another
    coil_nodes = np.unique(dom.triangles[kind == "coil"])
    from srmcore.thermal.model import EdgeLink
    from srmcore.thermal.domain import boundary_edges
    ce = boundary_edges(dom.triangles[kind == "coil"])
    lk = _edge_keys(dom.triangles[kind == "liner"])
    ce = ce[[tuple(e) in lk for e in np.sort(ce, axis=1).tolist()]]     # coil faces that touch the liner
    ie = boundary_edges(dom.triangles[(kind == "stator_iron") | (kind == "rotor_iron") | (kind == "shaft")])
    big = 1e9
    prob = ThermalProblem(dom, p.conductivity, p.capacity, p.depth,
                          (Lump("hot", fixed_c=100.0), Lump("cold", fixed_c=0.0)),
                          (EdgeLink(ce, "hot", big), EdgeLink(ie, "cold", big)))
    s = ThermalSolver(prob)
    t = s.steady(lambda _t: ThermalLoad(np.zeros(len(dom.triangles))))
    # flux through the liner band is bounded by the band's own conductance: k * (face length * depth) / t
    q = s.heat_to_fixed(t)["cold"]
    nodes = dom.nodes
    face = np.hypot(*(nodes[ce][:, 1] - nodes[ce][:, 0]).T).sum()
    # independent bounds: contact (every face at gap t) above; every face at the widest gap
    # t + 2 fillet (the slot back face, topology/radial.py) below
    bound = co.k_liner * face * p.depth * 100.0
    assert q <= bound / co.liner_thickness
    assert q >= 0.9 * bound / (co.liner_thickness + 2 * M.stator_fillet_radius)


def test_end_lump_per_coil():
    n, _ = net()
    ends = [lump for lump in n.problem.lumps if lump.hot_spot]
    assert len(ends) == M.n_stator_poles and set(n.end_lumps.values()) == {x.name for x in ends}
    assert 0 < n.active_share < 1


def test_slot_oil_builds_and_balances():
    setup = CoolingSetup(slot_oil=SlotOil(channel_height=3e-3, channel_width=10e-3, inlet_c=60.0, flow_m3s=1e-4))
    n, _ = net(setup)
    names = {lump.name for lump in n.problem.lumps}
    assert {"slot_in", "slot_oil"} <= names
    s = ThermalSolver(n.problem)
    t = s.steady(coil_load(0))
    assert sum(s.heat_to_fixed(t).values()) > 0


def test_missing_thermal_block_refused():
    with pytest.raises(ValueError, match="M19"):
        net(iron_materials=("M19", "M19"))


def test_end_spray_takes_end_heat_into_the_oil():
    plain, _ = net()
    n, co = net(CoolingSetup(end_spray=EndSpray(inlet_c=60.0, flow_m3s=1e-5)))
    s0, s = ThermalSolver(plain.problem), ThermalSolver(n.problem)
    t0, t = s0.steady(coil_load(0)), s.steady(coil_load(0))
    out = s.heat_to_fixed(t)
    assert out["spray_in"] > 0
    assert t.lumps["spray_oil"] - 60.0 == pytest.approx(out["spray_in"] / (2 * 1e-5 * co.spray_rho_cp), rel=1e-9)
    hot = lambda r: max(r.lumps[e] for e in n.end_lumps.values())  # noqa: E731
    assert hot(t) < hot(t0)


def test_end_spray_out_of_cragoe_range_refused():
    with pytest.raises(MissingCoolingData, match="end spray"):
        net(CoolingSetup(end_spray=EndSpray(inlet_c=250.0, flow_m3s=1e-5)))


def test_jacket_wall_refused():
    with pytest.raises(ValueError, match="channel height"):
        net(CoolingSetup(housing_thickness=4e-3, jacket=Jacket(channel_height=4e-3)))


def _hole(radius, angle, size):
    cx, cy = radius * math.cos(angle), radius * math.sin(angle)
    pts = [(cx + size * math.cos(a), cy + size * math.sin(a)) for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)]
    return tuple(IronArc(start=pts[i], end=pts[(i + 1) % 4], center=(cx, cy)) for i in range(4))


def test_imported_iron_builds():
    canon = lambda loop: _canonical(list(to_segments(loop)), M)  # noqa: E731
    r_s = (M.stator_yoke_inner_radius + M.stator_outer_radius) / 2
    r_r = (M.shaft_radius + M.rotor_yoke_outer_radius) / 2
    iron = parametric_iron(M).model_copy(update={
        "stator_holes": tuple(canon(_hole(r_s, 2 * math.pi * k / 8, 1e-3)) for k in range(8)),
        "rotor_holes": tuple(canon(_hole(r_r, 2 * math.pi * k / 6, 1e-3)) for k in range(6))})
    machine = M.model_copy(update={"iron": iron})
    dom = thermal_domain(build_static_mesh(Design(machine=machine, mesh=MeshSettings(preset="screening"))), machine)
    n, _ = net(machine=machine, dom=dom)
    s = ThermalSolver(n.problem)
    s.steady(lambda _t: ThermalLoad(np.zeros(len(dom.triangles))))
