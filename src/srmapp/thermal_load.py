"""Heat sources of a thermal solve from one stroke: iron loss per element, copper loss per coil side and end lump."""
import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from srmcore.materials.library import load_material
from srmcore.model.design import RadialSRMParams
from srmcore.thermal.model import Temperatures, ThermalLoad

from .copper import ac_copper_parts
from .drive.envelope import StrokeTrace
from .losses import StrokeLoss, phase_current_samples
from .sizing.winding import Winding
from .thermal_network import Network, _tri_area

DENSITY_NOTE = "density mode: no wire, so the AC copper loss is not computed"


@dataclass(frozen=True)
class PointHeat:
    iron_w_per_m3: np.ndarray    # thermal element order, iron factor included
    i_rms: float                 # A, phase
    skin_ref_w: float            # W, all phases, at t_ref_c
    prox_ref_w: float            # W, at t_ref_c
    t_ref_c: float
    notes: tuple[str, ...] = ()


def point_heat(stroke: StrokeLoss, trace: StrokeTrace, domain, static, winding: Winding, wire,
               machine: RadialSRMParams, t_ref_c: float, iron_factor: float, rpm: float) -> PointHeat:
    """`rpm` is the speed the stroke was solved at (it sets the period of the AC terms)."""
    kinds = np.array([static.region_kind[n] for n in static.region_names])
    em = []
    for part, kind, side in ((static.stator, "stator_iron", stroke.sides[0]), (static.rotor, "rotor_iron", stroke.sides[1])):
        w = np.zeros(len(part.triangles))
        w[np.flatnonzero(kinds[part.region_ids] == kind)] = side.element_w
        em.append(w)
    volume = _tri_area(domain.nodes, domain.triangles) * machine.stack_length
    iron = domain.from_em(*em) / volume * iron_factor
    skin = prox = 0.0
    if wire is not None:
        f, tau = stroke.fields, stroke.fields.stator.pitch
        phase = phase_current_samples(trace.current, f.angles, tau, machine.n_phases)[:, 0]
        skin, prox = ac_copper_parts(winding, wire, phase, tau / (rpm * 2 * math.pi / 60), f.b_coil, f.coil_side,
                                     f.coil_areas, machine, t_ref_c)
    return PointHeat(iron, trace.i_rms, skin, prox, t_ref_c, () if wire is not None else (DENSITY_NOTE,))


def load_fn(heat: PointHeat, network: Network, machine: RadialSRMParams,
            winding: Winding) -> Callable[[Temperatures | None], ThermalLoad]:
    """Thermal load as a function of the temperatures: copper loss follows the resistivity of each coil side and
    end lump (DC and AC), iron loss is fixed. `None` uses `heat.t_ref_c` everywhere."""
    domain, depth = network.problem.domain, network.problem.depth
    rho = load_material(machine.materials.coil).resistivity_at
    ref = rho(heat.t_ref_c)
    area = _tri_area(domain.nodes, domain.triangles)
    n_sides = len(network.coil_of_side)
    n_coils = len(network.end_lumps)
    p_ref = machine.n_phases * heat.i_rms ** 2 * winding.resistance   # W, DC loss of all phases at t_ref
    a = network.active_share
    prox_area = sum(area[e].sum() for e in domain.coil_elements.values())

    def load(t: Temperatures | None) -> ThermalLoad:
        w = heat.iron_w_per_m3.copy()
        lump_w = {}
        for side, el in domain.coil_elements.items():
            if t is None:
                scale = 1.0
            else:
                scale = rho(float(t.field[np.unique(domain.triangles[el])].mean())) / ref
            dc = p_ref * a / n_sides
            skin = heat.skin_ref_w * a / n_sides
            prox = heat.prox_ref_w * area[el].sum() / prox_area
            # AC terms scale as 1/rho
            w[el] = (dc * scale + (skin + prox) / scale) / (area[el].sum() * depth)
        for lump in network.end_lumps.values():
            scale = 1.0 if t is None else rho(t.lumps[lump]) / ref
            lump_w[lump] = (p_ref * (1 - a) * scale + heat.skin_ref_w * (1 - a) / scale) / n_coils
        return ThermalLoad(w, lump_w)

    return load
