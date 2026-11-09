import dataclasses
import math

import numpy as np
import pytest
from conftest import make_8_6

from srmapp.cooling import CoolingSetup, coefficients
from srmapp.drive.envelope import StrokeTrace
from srmapp.losses import RegionLoss, StrokeLoss, _Side, stroke_losses
from srmapp.sizing.estimates import coil_side_area
from srmapp.sizing.winding import Winding
from srmapp.thermal_load import DENSITY_NOTE, PointHeat, load_fn, point_heat
from srmapp.thermal_network import _tri_area, build_network
from srmapp.wire import RoundWire
from srmcore.maps.stroke import StrokeFields, stroke_angles
from srmcore.materials.library import load_material
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design, MeshSettings, RegionMaterials
from srmcore.thermal.domain import thermal_domain
from srmcore.thermal.model import Temperatures

IRON = RegionMaterials(stator="10JNEX900", rotor="10JNEX900")
M = make_8_6(materials=IRON, lamination_thickness=1.0e-4)
DESIGN = Design(machine=M, mesh=MeshSettings(preset="screening"))
TURNS, CU = 20, 2e-6
W = Winding(turns=TURNS, strands=1, copper_area=CU, current=10.0, resistance=0.1, copper_mass=1.0, wire=0)
WIRE = RoundWire(diameter=1.0e-3, outer_diameter=1.08e-3)
RHO = load_material(M.materials.coil).resistivity_at


@pytest.fixture(scope="module")
def rig():
    static = build_machine_mesh(DESIGN)
    dom = thermal_domain(static, M)
    fill = TURNS * CU / coil_side_area(M)
    setup = CoolingSetup()
    net = build_network(dom, M, W, fill, coefficients(setup, M, 3000.0, frozenset(), None, fill=fill), setup)
    return static, dom, net


def _heat(dom, **kw):
    v = dict(iron_w_per_m3=np.zeros(len(dom.triangles)), i_rms=10.0, skin_ref_w=30.0, prox_ref_w=12.0, t_ref_c=120.0)
    v.update(kw)
    return PointHeat(**v)


def _total(dom, load, depth=M.stack_length):
    return float(np.sum(load.element_w_per_m3 * _tri_area(dom.nodes, dom.triangles) * depth)) + sum(load.lump_w.values())


def test_copper_total_at_uniform_t(rig):
    _, dom, net = rig
    heat = _heat(dom)
    f = load_fn(heat, net, M, W)
    assert _total(dom, f(None)) == pytest.approx(M.n_phases * 100 * W.resistance + 42.0, rel=1e-9)
    t = 60.0
    temps = Temperatures(np.full(len(dom.nodes), t), {n: t for n in net.end_lumps.values()})
    s = RHO(t) / RHO(120.0)
    assert _total(dom, f(temps)) == pytest.approx(M.n_phases * 100 * W.resistance * s + 42.0 / s, rel=1e-9)


def test_density_mode_no_ac(rig):
    static, dom, _ = rig
    side = lambda n: _Side({}, 0.1, "A", 0, 0, False, element_w=np.zeros(n))
    kinds = np.array([static.region_kind[n] for n in static.region_names])
    sides = (side(int((kinds[static.stator.region_ids] == "stator_iron").sum())),
             side(int((kinds[static.rotor.region_ids] == "rotor_iron").sum())))
    stroke = StrokeLoss(None, sides, {}, 0.0)
    # fields are only read for the AC terms, which density mode skips
    f = dataclasses.make_dataclass("F", ["stator", "angles"])(dataclasses.make_dataclass("S", ["pitch"])(1.0), np.zeros(4))
    trace = StrokeTrace(0, 0, 0, np.ones(4), np.ones(4), 1.0, 5.0, 1.0)
    h = point_heat(dataclasses.replace(stroke, fields=f), trace, dom, static, W, None, M, 120.0, 1.0, 1000.0)
    assert (h.skin_ref_w, h.prox_ref_w) == (0.0, 0.0) and DENSITY_NOTE in h.notes


def test_element_w_matches_regions():
    from srmapp.losses import _side_loss
    from srmcore.maps.stroke import IronWaveforms
    n, t = 5, np.arange(16) / 16
    b = np.zeros((16, n, 2))
    b[:, :, 0] = 1.0 * np.sin(2 * np.pi * t)[:, None] * np.linspace(0.5, 1, n)
    side = IronWaveforms(b, 1, 0.1, np.zeros((n, 2)), np.full(n, 1e-5), np.array(["a", "a", "b", "b", "b"]),
                         np.array(["10JNEX900"] * n))
    mult = np.linspace(1.0, 2.0, n)
    s = _side_loss(side, 2 * math.pi * 50, 0.05, None, 1e-4, mult)
    for r, loss in s.regions.items():
        assert s.element_w[side.region == r].sum() == pytest.approx(loss.hysteresis + loss.classical + loss.excess)


@pytest.mark.slow
def test_iron_total_and_ac_scaling(rig, tmp_path):
    from srmapp.copper import ac_copper_parts
    static, dom, net = rig
    angles = stroke_angles(static, 2 * math.pi / M.n_rotor_poles, 12)
    cur = 20.0 * np.clip(np.sin(np.pi * angles / angles[-1] * 1.0), 0, None) * 3
    coil = np.zeros((len(angles), M.n_phases))
    coil[:, 0] = cur
    rpm = 3000.0
    sl = stroke_losses(static, DESIGN, angles, coil, rpm, cache_dir=tmp_path)
    trace = StrokeTrace(0, 0, 0, cur, cur, 1.0, 8.0, 1.0)
    h = point_heat(sl, trace, dom, static, W, WIRE, M, 120.0, 1.3, rpm)
    vol = _tri_area(dom.nodes, dom.triangles) * M.stack_length
    assert float(np.sum(h.iron_w_per_m3 * vol)) == pytest.approx(sl.iron_w * 1.3, rel=1e-9)
    # AC terms scaled from 120 C to 40 C against a recompute at 40 C (winding resistance moves with rho)
    s = RHO(120.0) / RHO(40.0)
    tau = sl.fields.stator.pitch
    args = (sl.fields.angles, )
    f = sl.fields
    w40 = dataclasses.replace(W, resistance=W.resistance / s)
    period = tau / (rpm * 2 * math.pi / 60)
    from srmapp.losses import phase_current_samples
    ph = phase_current_samples(cur, f.angles, tau, M.n_phases)[:, 0]
    skin, prox = ac_copper_parts(w40, WIRE, ph, period, f.b_coil, f.coil_side, f.coil_areas, M, 40.0)
    assert h.skin_ref_w * s == pytest.approx(skin, rel=0.01)
    assert h.prox_ref_w * s == pytest.approx(prox, rel=0.01)
