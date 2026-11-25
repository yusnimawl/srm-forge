"""Faiz 8/6 stator for R5 gate V2: J. Faiz, B. Ganji, C. E. Carstensen, K. A. Kasper, R. W. De Doncker, "Temperature
Rise Analysis of Switched Reluctance Motors Due to Electromagnetic Losses", IEEE Trans. Magn. 45(7), 2009,
pp. 2927-2934. Inputs and their pages: docs/r5-sources.md section 9.1 and 9.3; figure readings:
tools/digitise_r5_v0.py (docs/validation/r5_v0_readings.json).

Their 2-D model (Fig. 2) is the stator only: frame, laminations, winding at an equivalent conductivity, slot liner and
slot wedge. The frame surface goes to the 20 degC ambient at h = 30, the pole faces and the wedge face (the bore) go
to the inside air of Fig. 8 at h = 70, and the losses of Table IV heat the stator parts. The rotor is not in it.
"""
import math
from dataclasses import dataclass, replace

import numpy as np

from srmcore.mesh.static import build_static_mesh
from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.thermal.domain import ThermalDomain, thermal_domain
from srmcore.thermal.model import EdgeLink, Lump, LumpLink, ThermalLoad, ThermalProblem

# Table I, p. 2928
STATOR_OD, SLOT_BOTTOM_D = 0.125, 0.100
ROTOR_OD, ROTOR_SLOT_BOTTOM_D, SHAFT_D = 0.063, 0.041, 0.021
AIR_GAP, STACK = 0.35e-3, 0.090
POLE_ARC = math.radians(21.0)
TURNS = 124
# Table II, p. 2928: k W/(m K), c J/(kg K), density kg/m3
IRON = (20.0, 438.0, 7650.0)
COPPER = (401.0, 385.0, 8933.0)
LINER = (0.076, 1172.0, 2150.0)
FRAME = (177.0, 875.0, 2770.0)
WEDGE = (0.29, 1172.0, 2150.0)
K_WINDING = 0.83                       # p. 2929
# Section V, pp. 2930-2931
H_BORE = 70.0                          # pole faces and wedge face, 1000 r/min
H_FRAME = 30.0                         # 4 m/s fan air on the frame, every later result
AMBIENT_C = 20.0                       # Figs. 8 to 10 start there
# Table IV, p. 2930, calculated
LOSS_STATOR_POLE, LOSS_STATOR_YOKE = 5.9, 10.0
LOSS_COPPER = 24.96 + 0.04             # dc plus ac

# read off Fig. 11(a) (faiz_fig11 in the readings): liner and wedge; Fig. 12 for the frame (an inference)
LINER_T = 1.0e-3
WEDGE_T = 2.2e-3
FRAME_T = 5.0e-3
# Table V, p. 2931: the R1-C1 node of their network (the only one with a path to ambient and a large capacity),
# read as the frame (an inference)
TABLE_V_R1, TABLE_V_C1 = 0.57, 5298.0   # K/W, J/K
FRAMES = ("printed", "table_v")


def machine(liner: float = LINER_T, wedge: float = WEDGE_T) -> RadialSRMParams:
    """Parallel-sided stator poles (taper 0 here), the coil filling the slot between the liners down to the wedge.
    The rotor is only there because the mesh needs one; the thermal problem drops it."""
    return RadialSRMParams(
        n_stator_poles=8, n_rotor_poles=6, n_phases=4,
        stator_outer_diameter=STATOR_OD, rotor_outer_diameter=ROTOR_OD, air_gap=AIR_GAP, stack_length=STACK,
        shaft_diameter=SHAFT_D, stator_pole_arc=POLE_ARC, rotor_pole_arc=POLE_ARC,
        stator_yoke_thickness=(STATOR_OD - SLOT_BOTTOM_D) / 2,
        rotor_yoke_thickness=(ROTOR_SLOT_BOTTOM_D - SHAFT_D) / 2,
        turns_per_pole=TURNS, fill_factor=0.5, slot_liner_thickness=liner, coil_inner_clearance=wedge)


def _stator_only(d: ThermalDomain) -> ThermalDomain:
    ns = len(d.stator_elements)
    tri = d.triangles[:ns]
    used = np.unique(tri)
    remap = np.full(len(d.nodes), -1)
    remap[used] = np.arange(len(used))
    return ThermalDomain(d.nodes[used], remap[tri], d.element_kind[:ns], d.stator_elements,
                         np.zeros(0, dtype=int), {k: v for k, v in d.coil_elements.items()},
                         remap[d.outer_edges], remap[d.bore_edges], np.zeros((0, 2), dtype=int))


@dataclass(frozen=True)
class FaizCase:
    machine: RadialSRMParams
    domain: ThermalDomain
    part: np.ndarray            # per element: pole, yoke, winding, liner, wedge
    area: np.ndarray            # per element, m2

    def part_area(self, name: str) -> float:
        return float(self.area[self.part == name].sum())


def build(preset: str = "full", liner: float = LINER_T, wedge: float = WEDGE_T) -> FaizCase:
    m = machine(liner, wedge)
    static = build_static_mesh(Design(machine=m, mesh=MeshSettings(preset=preset)))
    d = _stator_only(thermal_domain(static, m))
    p = d.nodes[d.triangles]
    e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    area = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2
    r = np.hypot(*p.mean(axis=1).T)
    kind = d.element_kind
    part = np.full(len(kind), "", dtype=object)
    part[kind == "coil"] = "winding"
    iron = kind == "stator_iron"
    part[iron & (r >= m.stator_yoke_inner_radius)] = "yoke"
    part[iron & (r < m.stator_yoke_inner_radius)] = "pole"
    slot = (kind == "liner") | (kind == "air")         # all of slot_air: liner band, slot centre, wedge
    r_in = m.bore_radius + m.coil_inner_clearance
    part[slot & (r < r_in)] = "wedge"
    part[slot & (r >= r_in)] = "liner"
    if (part == "").any():
        raise ValueError(f"unassigned elements of kinds {sorted(set(kind[part == '']))}")
    return FaizCase(m, d, part.astype(str), area)


def problem(case: FaizCase, air_c: float, frame: str = "printed", frame_t: float = FRAME_T,
            winding_rho_c: float | None = None) -> ThermalProblem:
    """The bore goes to a fixed inside-air lump at `air_c`. The frame is one lump joined to the stator OD through
    half the thickness `frame_t` of the printed shell (both models). frame="printed": an aluminium shell of that
    thickness (Table II) to the ambient at h = 30 (Biot number h t / k about 1e-3). frame="table_v": the capacity
    C1 and resistance R1 of Table V."""
    if frame not in FRAMES:
        raise ValueError(f"frame must be one of {FRAMES}")
    # winding rho c: copper over the whole coil area, an inference (the paper gives no winding capacity; Table II lists copper); winding_rho_c overrides it
    props = {"pole": IRON, "yoke": IRON, "winding": (K_WINDING, COPPER[1], COPPER[2]), "liner": LINER, "wedge": WEDGE}
    k = np.array([props[p][0] for p in case.part])
    c = np.array([props[p][1] * props[p][2] for p in case.part])
    if winding_rho_c is not None:
        c[case.part == "winding"] = winding_rho_c
    r0 = case.machine.stator_outer_radius
    r1 = r0 + frame_t
    if frame == "table_v":
        frame_c, g_ambient = TABLE_V_C1, 1.0 / TABLE_V_R1
    else:
        frame_c, g_ambient = FRAME[1] * FRAME[2] * math.pi * (r1 ** 2 - r0 ** 2) * STACK, H_FRAME * 2 * math.pi * r1 * STACK
    lumps = (Lump("frame", capacity=frame_c), Lump("ambient", fixed_c=AMBIENT_C), Lump("inside_air", fixed_c=air_c))
    links = (EdgeLink(case.domain.outer_edges, "frame", FRAME[0] / (frame_t / 2)),
             LumpLink("frame", "ambient", g_ambient),
             EdgeLink(case.domain.bore_edges, "inside_air", H_BORE))
    return ThermalProblem(case.domain, k, c, STACK, lumps, links)


def load(case: FaizCase) -> ThermalLoad:
    """Table IV spread uniformly inside each part (the paper does not say how a part's loss is spread)."""
    q = np.zeros(len(case.part))
    for name, watts in (("pole", LOSS_STATOR_POLE), ("yoke", LOSS_STATOR_YOKE), ("winding", LOSS_COPPER)):
        q[case.part == name] = watts / (case.part_area(name) * STACK)
    return ThermalLoad(q)


def with_air(p: ThermalProblem, air_c: float) -> ThermalProblem:
    return replace(p, lumps=tuple(replace(l, fixed_c=air_c) if l.name == "inside_air" else l for l in p.lumps))
