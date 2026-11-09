"""Thermal network of a machine with a cooling setup: element arrays, lumps and links for `srmcore.thermal`.

Front and rear ends are identical, so one end-space lump and one end-winding lump per coil carry both
ends (areas and conductances summed). A coil is its two coil sides, paired by region name
(`coil_A1+` and `coil_A1-` are coil `A1`). Shaft ends are adiabatic.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from srmcore.maps.end_winding import coil_geometry
from srmcore.materials.library import load_material
from srmcore.model.design import RadialSRMParams
from srmcore.thermal.correlations import air_properties
from srmcore.thermal.domain import ThermalDomain, boundary_edges
from srmcore.thermal.model import AreaLink, EdgeLink, Lump, LumpLink, ThermalModelError, ThermalProblem

from .cooling import AIR_FILM_C, Coefficients, CoolingSetup, MissingCoolingData
from .sizing.estimates import mean_turn_length
from .sizing.winding import Winding


@dataclass(frozen=True)
class Network:
    problem: ThermalProblem
    end_lumps: dict[str, str]        # coil -> its end-winding lump
    coil_of_side: dict[str, str]     # coil side region -> coil
    active_share: float              # 2 L_stack / mean turn length
    notes: tuple[str, ...]


def _edge_keys(tri: np.ndarray) -> set[tuple[int, int]]:
    e = np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]), axis=1)
    return set(map(tuple, e.tolist()))


def _tri_area(nodes: np.ndarray, tri: np.ndarray) -> np.ndarray:
    p = nodes[tri]
    return 0.5 * np.abs((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                        - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))


def _series(*g: float) -> float:
    return 1.0 / sum(1.0 / x for x in g)


def build_network(domain: ThermalDomain, machine: RadialSRMParams, winding: Winding, fill: float,
                  coeffs: Coefficients, setup: CoolingSetup,
                  iron_materials: tuple[str, str] = ("10JNEX900", "10JNEX900")) -> Network:
    if setup.end_spray is not None:
        raise MissingCoolingData("end spray: oil properties (specific heat) not cited, "
                                 "so the oil temperature rise cannot be computed")
    if not coeffs.h_air_gap > 0:
        raise ValueError("air-gap heat transfer coefficient must be positive")
    notes = list(coeffs.notes)
    copper, shaft = load_material("copper"), load_material("steel_1010")
    cap_iron = {}
    for part, name in zip(("stator", "rotor"), iron_materials):
        m = load_material(name)
        if getattr(m, "thermal", None) is None:
            raise ValueError(f"{part} material {name!r} has no thermal block (no cited conductivity)")
        c = m.thermal.specific_heat
        cap_iron[part] = 0.0 if c is None else c * m.density
    if any(v == 0.0 for v in cap_iron.values()):
        notes.append("iron has no cited specific heat: its capacity is zero (steady results unaffected)")
    notes.append("resin has no cited specific heat: coil capacity counts the copper only")

    L, r_out, t_h = machine.stack_length, machine.stator_outer_radius, setup.housing_thickness
    k_air = air_properties(AIR_FILM_C)["k"]
    kind, nodes, tri = domain.element_kind, domain.nodes, domain.triangles
    m = len(tri)
    area = _tri_area(nodes, tri)

    # element arrays
    k = np.full(m, k_air)
    cap = np.zeros(m)
    for sel, part in ((kind == "stator_iron", "stator"), (kind == "rotor_iron", "rotor")):
        k[sel], cap[sel] = coeffs.k_lamination, cap_iron[part]
    k[kind == "shaft"] = shaft.thermal.conductivity
    cap[kind == "shaft"] = shaft.thermal.specific_heat * shaft.density
    coil = kind == "coil"
    k[coil] = coeffs.k_cross_wire
    cap[coil] = fill * copper.density * copper.thermal.specific_heat

    # liner: the marked band is the liner plus the fillet allowance; its full geometric width conducts at k_liner
    liner = np.flatnonzero(kind == "liner")
    k[liner] = coeffs.k_liner
    notes.append("slot liner band uses the liner conductivity across its full geometric width "
                 "(no coil-to-liner contact assumed)")
    coil_edges = boundary_edges(tri[coil])
    liner_keys = _edge_keys(tri[liner]) if len(liner) else set()
    facing = np.array([tuple(e) in liner_keys for e in np.sort(coil_edges, axis=1).tolist()], dtype=bool)

    # coils
    if any(not (n.startswith("coil_") and n.endswith(("+", "-"))) for n in domain.coil_elements):
        raise ThermalModelError("coil side names must look like coil_<name>+ or coil_<name>-")
    coil_of_side = {n: n[len("coil_"):-1] for n in domain.coil_elements}
    coils = sorted(set(coil_of_side.values()))
    mtl = mean_turn_length(machine)
    l_end = (mtl - 2 * L) / 2
    geo = coil_geometry(machine)
    k_along = copper.thermal.conductivity * fill
    # g_side counts one end although the merged lump stands for both: deliberately conservative (plan call 2)
    g_side = k_along / (L / 2 + l_end / 2)
    end_cu_mass = winding.turns * winding.copper_area * 2 * l_end * copper.density
    end_area = 2 * (geo.depth + geo.build) * l_end * 2
    h_end = coeffs.h_end_face
    end_lumps = {c: f"end_{c}" for c in coils}

    lumps = [Lump(end_lumps[c], capacity=end_cu_mass * copper.thermal.specific_heat, hot_spot=True) for c in coils]
    lumps += [Lump("end_space"), Lump("airgap"), Lump("housing"), Lump("end_caps"),
              Lump("ambient", fixed_c=setup.ambient_c)]
    links: list = []
    for name, el in domain.coil_elements.items():
        links.append(AreaLink(el, end_lumps[coil_of_side[name]], g_side))
    links += [LumpLink(end_lumps[c], "end_space", h_end * end_area) for c in coils]

    # end space: stator and rotor iron end faces of both ends, the end caps, the air gap's annulus
    for sel in (kind == "stator_iron", kind == "rotor_iron"):
        links.append(AreaLink(np.flatnonzero(sel), "end_space", 2 * coeffs.h_end_face))
    cap_area = 2 * math.pi * r_out ** 2
    links += [LumpLink("end_caps", "end_space", coeffs.h_end_face * cap_area),
              LumpLink("end_caps", "ambient", coeffs.h_end_face * cap_area)]
    gap_area = 2 * math.pi * (machine.bore_radius ** 2 - machine.rotor_outer_radius ** 2)  # both ends
    links.append(LumpLink("airgap", "end_space", coeffs.h_air_gap * gap_area))
    for edges in (domain.bore_edges, domain.rotor_edges):
        links.append(EdgeLink(edges, "airgap", coeffs.h_air_gap))

    # stator back: contact, housing, end caps, ambient
    links.append(EdgeLink(domain.outer_edges, "housing", k_air / coeffs.contact_gap))
    links.append(LumpLink("housing", "end_caps", coeffs.k_housing * 2 * math.pi * r_out * t_h / (L / 2)))
    links.append(LumpLink("housing", "ambient", coeffs.h_end_frame * 2 * math.pi * (r_out + t_h) * L))
    if (j := setup.jacket) is not None:
        wall = t_h - j.channel_height
        if not wall > 0:
            raise ValueError("jacket channel height must be smaller than the housing thickness")
        a_j = j.passes * j.channel_width * 2 * math.pi * r_out
        links.append(LumpLink("housing", "coolant", _series(coeffs.k_housing * a_j / wall, coeffs.h_jacket * a_j)))
        f = coeffs.jacket_fluid
        lumps += [Lump("coolant_in", fixed_c=coeffs.jacket_inlet_c), Lump("coolant")]
        links.append(LumpLink("coolant_in", "coolant", 2 * coeffs.jacket_flow_m3s * f.density * f.specific_heat))

    # slot coolant on coil faces that border slot air other than the liner
    if setup.slot_oil is not None:
        air_keys = _edge_keys(tri[kind == "air"])
        exposed = np.array([tuple(e) in air_keys for e in np.sort(coil_edges, axis=1).tolist()], dtype=bool)
        f = coeffs.slot_fluid
        lumps += [Lump("slot_in", fixed_c=coeffs.slot_inlet_c), Lump("slot_oil")]
        links.append(EdgeLink(coil_edges[exposed & ~facing], "slot_oil", coeffs.h_slot_oil))
        links.append(LumpLink("slot_in", "slot_oil", 2 * coeffs.slot_flow_m3s * f.density * f.specific_heat))

    problem = ThermalProblem(domain, k, cap, L, tuple(lumps), tuple(links))
    return Network(problem, end_lumps, coil_of_side, 2 * L / mtl, tuple(notes))
