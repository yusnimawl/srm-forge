"""Thermal case of the Kiyota 18/12 Fig. 8 hold (K. Kiyota, T. Kakishima, A. Chiba, IEEE Trans. Ind. Electron.
61(10), 2014, pp. 5714 to 5716): a 140.7 A RMS hold on the 18/12 for about 14 s, the coil-end temperature measured
from 51.1 degC. `run` solves the transient on the thermal network of `srmapp` with the current read off the figure
(`docs/validation/r5_v0_readings.json`, `kiyota_fig8.rms_current_a`) and the losses of the plan
(docs/superpowers/plans/2026-11-26-r5e-v4-v5.md, calls 1 to 6).

The phase resistance is an argument of `winding` and `run` on purpose: 97.8 mOhm is the value at the terminals
(2014 pp. 5714-5715); 5.3 mOhm of it is coil connections and terminal wiring, so the winding alone is 92.5 to 92.9 mOhm.
The caller picks one."""
import json
import math
import time
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

import kiyota_18_12 as k18
from srmapp.cooling import CoolingSetup, coefficients, k_iron_hi
from srmapp.sizing.estimates import copper_mass
from srmapp.sizing.winding import Winding
from srmapp.thermal_load import PointHeat, load_fn
from srmapp.thermal_network import Network, _tri_area, build_network
from srmcore.mesh import build_machine_mesh
from srmcore.thermal.domain import thermal_domain
from srmcore.thermal.model import Temperatures
from srmcore.thermal.solve import ThermalSolver

READINGS = Path(__file__).resolve().parents[1] / "docs" / "validation" / "r5_v0_readings.json"
_FIG8 = json.loads(READINGS.read_text())["kiyota_fig8"]["rms_current_a"]    # Fig. 8 reading, [s, A RMS] pairs
_T, _I = np.array(_FIG8).T

START_C = 51.1                  # Fig. 8 start reading
TARGET_K = (39.5, 0.4)          # measured rise at the peak, trace reading and its error (docs/r5-sources.md 9.2)
PRINTED_K = 41.0                # the rise the paper prints
M_IRON_W = 4400.0               # Table III (b), "iron and other", 130 A RMS
M_IRON_LOW_W = 600.0            # Table III (c), 7500 r/min, light load
MECH_W = 573.0                  # mechanical loss, Fig. 7 at 7493 r/min
RPM = 7500.0                    # 1500 Hz stator electrical frequency on 12 rotor poles
AMBIENT_C = 25.0                # assumed, not printed
RATED_MECH = 1.2                # the paper's 20 % bearing-condition scatter on the mechanical loss
T_REF_C = 20.0                  # the resistance handed to `winding` is the 20 degC value


def current(t) -> np.ndarray:
    """RMS phase current (A) at time `t` (s): linear between the Fig. 8 readings, 0 after the last one."""
    return np.interp(t, _T, _I, right=0.0)


@dataclass(frozen=True)
class Case:
    design: k18.Design
    static: object
    domain: object

    @property
    def machine(self):
        return self.design.machine


def build(preset: str = "screening", **geometry) -> Case:
    """Design (`geometry`: stator_yoke, stator_arc, rotor_arc, rotor_yoke), static mesh and thermal domain."""
    d = k18.design(preset, **geometry)
    with k18.waivers():
        static = build_machine_mesh(d)
    return Case(d, static, thermal_domain(static, d.machine))


TURN_AREA = k18.WIRES * math.pi * (k18.WIRE_D / 2) ** 2     # m2, one turn, 9 strands of 0.9 mm


def winding(case: Case, resistance: float) -> Winding:
    """20 turns of 9 strands of 0.9 mm per pole; `resistance` is one phase at 20 degC, ohm (no default: see the
    module docstring). The current field is the peak of the 140.7 A hold and is not read."""
    return Winding(turns=k18.TURNS_PER_POLE, strands=k18.WIRES, copper_area=TURN_AREA, current=140.7 * math.sqrt(2),
                   resistance=resistance, copper_mass=copper_mass(case.machine, k18.TURNS_PER_POLE, TURN_AREA),
                   wire=None)


def network(case: Case, wnd: Winding, rows=frozenset(), housing: float = 8e-3, ambient: float = AMBIENT_C):
    """The network without a jacket (air-cooled frame) and the coefficients of `rows` at `RPM`."""
    setup = CoolingSetup(jacket=None, housing_thickness=housing, ambient_c=ambient)
    m = case.machine
    coeffs = coefficients(setup, m, RPM, frozenset(rows), None, fill=m.fill_factor)
    return build_network(case.domain, m, wnd, m.fill_factor, coeffs, setup), coeffs


def iron_load(case: Case, coeffs, watts: float) -> np.ndarray:
    """W/m3 per thermal element: `watts` is the measured iron and other; the nominal model carries it over
    `k_iron_hi(1500)` and the rated set (`coeffs.iron_factor`) gives it back whole. Uniform over the stator iron."""
    d = case.domain
    stator = d.element_kind == "stator_iron"
    volume = _tri_area(d.nodes, d.triangles)[stator].sum() * case.machine.stack_length
    w = np.zeros(len(d.triangles))
    w[stator] = watts / k_iron_hi(RPM * case.machine.n_rotor_poles / 60.0) * coeffs.iron_factor / volume
    return w


@dataclass(frozen=True)
class Rig:
    case: Case
    winding: Winding
    net: Network
    heat: PointHeat

    def load(self, i_rms: float):
        return load_fn(replace(self.heat, i_rms=i_rms), self.net, self.case.machine, self.winding)


def rig(case: Case, resistance: float, rows=frozenset(), iron_w: float = M_IRON_W, mech: str | None = "windage",
        housing: float = 8e-3, ambient: float = AMBIENT_C) -> Rig:
    """`mech` is "windage" (573 W in the rotor iron), "friction" (at the end caps) or None; the
    `mechanical_loss` row takes it x `RATED_MECH`."""
    wnd = winding(case, resistance)
    net, coeffs = network(case, wnd, rows, housing, ambient)
    mw = MECH_W * (RATED_MECH if "mechanical_loss" in rows else 1.0) if mech else 0.0
    heat = PointHeat(iron_load(case, coeffs, iron_w), 0.0, 0.0, 0.0, T_REF_C,
                     windage_w=mw if mech == "windage" else 0.0, friction_w=mw if mech == "friction" else 0.0)
    return Rig(case, wnd, net, heat)


@dataclass(frozen=True)
class Result:
    times_s: np.ndarray
    end_c: np.ndarray            # hottest end-winding lump, degC
    hot_c: np.ndarray            # rating hot spot (coil sides and end lumps), degC
    hot_where: tuple[str, ...]
    end_peak_k: float            # peak of end_c over START_C
    hot_peak_k: float
    hot_peak_where: str
    rise_10s_k: float            # end lump, over START_C
    rise_14s_k: float
    wall_s: float


def start_state(r: Rig, kind: str = "uniform", ambient: float = AMBIENT_C) -> Temperatures:
    """"uniform": START_C everywhere. "cold_iron": copper nodes and end lumps at START_C, the rest at `ambient`."""
    d, net = r.case.domain, r.net
    free = [lump for lump in net.problem.lumps]
    if kind == "uniform":
        return Temperatures(np.full(len(d.nodes), START_C),
                            {lump.name: START_C if lump.fixed_c is None else lump.fixed_c for lump in free})
    field = np.full(len(d.nodes), ambient)
    for el in d.coil_elements.values():
        field[np.unique(d.triangles[el])] = START_C
    ends = set(net.end_lumps.values())
    return Temperatures(field, {lump.name: START_C if lump.name in ends else (ambient if lump.fixed_c is None else lump.fixed_c)
                                for lump in free})


def run(r: Rig, dt: float = 0.05, t_end: float = 20.0, start: str = "uniform", ambient: float = AMBIENT_C,
        current_fn=current) -> Result:
    """One backward-Euler transient of `t_end / dt` steps; the load of step k is the current at (k + 1/2) dt on the
    temperatures of the step's start (`ThermalSolver.transient` calls it once per step)."""
    n = round(t_end / dt)
    solver = ThermalSolver(r.net.problem)
    ends = list(r.net.end_lumps.values())
    end_c, hot_c, where = [], [], []
    k = 0

    def sample(t):
        end_c.append(max(t.lumps[e] for e in ends))
        h = solver.hot_spot(t)
        hot_c.append(h.temperature_c)
        where.append(h.location)

    def load(t):
        nonlocal k
        sample(t)
        f = r.load(float(current_fn((k + 0.5) * dt)))
        k += 1
        return f(t)

    t0 = time.perf_counter()
    tr = solver.transient(start_state(r, start, ambient), load, t_end, n)
    sample(tr.final)
    wall = time.perf_counter() - t0
    end, hot = np.array(end_c), np.array(hot_c)
    i = int(np.argmax(hot))
    at = lambda s: float(end[min(round(s / dt), n)] - START_C)  # noqa: E731
    return Result(tr.times_s, end, hot, tuple(where), float(end.max() - START_C), float(hot.max() - START_C), where[i],
                  at(10.0), at(14.0), wall)
