"""Krishnan 6/4 prototype with measured inductance and torque: P. N. Materu, Design and steady-state
analysis of the switched reluctance motor drive, PhD dissertation, Virginia Tech, 1989 (chair R. Krishnan),
Table 1 p. 41 and Appendix A pp. 287-288; reprinted as Table 2.3 in Krishnan, Switched Reluctance Motor
Drives, 2001. Decisions and spike: docs/superpowers/specs/2026-10-05-m5d-krishnan-6-4-design.md."""
import math

import numpy as np
from scipy.optimize import brentq

from srmcore.fields.solution import SolveStatus
from srmcore.maps.end_winding import coil_geometry, end_winding_inductance
from srmcore.maps.point import solve_point
from srmcore.mesh import build_machine_mesh
from srmcore.model.design import Design, MeshSettings, RadialSRMParams, RegionMaterials
from srmcore.model.validator import waive_rules

CURRENTS = (1.0, 10.0, 20.0)                                   # A
MEASURED = {"La": (0.879, 0.155, 0.089), "Lu": (0.0355, 0.0407, 0.0356), "T_avg": (0.90, 20.3, 41.6)}
MATERU_FEA = {"La": (0.843, 0.133, 0.0755), "Lu": (0.0258, 0.0258, 0.0258), "T_avg": (0.80, 18.5, 37.8)}
# 3D vs 2D FEA (Seward et al., SATECH'87, cited by Materu p. 44): end leakage as a fraction of the inductance
SEWARD_END_LEAKAGE = {"La": 0.075, "Lu": 0.35}
# Measured Lu is non-monotonic in current (35.5, 40.7, 35.6 mH): half its spread over its mean
LU_MEASUREMENT_SCATTER = 0.5 * (0.0407 - 0.0355) / (0.5 * (0.0407 + 0.0355))
IMAGE_FACTORS = (1.0, 2.0)

AWG19_AREA = 0.653e-6                                          # m², bare copper
TURNS_PER_POLE = 268                                           # 536 turns per phase over 2 poles
AIR_GAP, SHAFT, ROTOR_POLE_HEIGHT = 0.25e-3, 28.56e-3, 27.25e-3
BORES = {"book": (0.10206, 0.010515), "dissertation": (0.1220, 0.01015)}   # bore diameter, stator back iron
LINER = 0.3e-3
ASSUMED = {
    "bore": "book 102.06 mm / back iron 10.515 mm (reproduces Materu's 2D FEA La at 1 A); dissertation 122.0 / 10.15 mm as a budget row",
    "shaft, rotor pole height": "dissertation Appendix A (28.56 mm, 27.25 mm); rotor yoke derived",
    "coil": "packed against the yoke, bundle packing 0.5 (175 mm² copper in 350 mm²); 0.35-0.65 as a budget row",
    "slot_liner_thickness": "0.3 mm, not in the source",
    "fillets, tapers": "0, not in the source",
    "materials": "M19 (book); the dissertation names 'E140 steel', not in the library; steel_1010 as a crude bound",
    "validator": "built inside waive_rules('self_starting') (stator arc 24 deg < 30 deg)",
}


def waivers():
    return waive_rules("self_starting")


def _params(bore: str, clearance: float) -> RadialSRMParams:
    d_bore, yoke = BORES[bore]
    r_rotor = d_bore / 2 - AIR_GAP
    return RadialSRMParams(
        n_stator_poles=6, n_rotor_poles=4, n_phases=3,
        stator_outer_diameter=0.190, rotor_outer_diameter=2 * r_rotor, air_gap=AIR_GAP,
        stack_length=0.06037, shaft_diameter=SHAFT,
        stator_pole_arc=math.radians(24.0), rotor_pole_arc=math.radians(36.0),
        stator_yoke_thickness=yoke, rotor_yoke_thickness=r_rotor - SHAFT / 2 - ROTOR_POLE_HEIGHT,
        stator_fillet_radius=0.0, rotor_fillet_radius=0.0,
        turns_per_pole=TURNS_PER_POLE, fill_factor=0.5,
        slot_liner_thickness=LINER, coil_inner_clearance=clearance,
    )


def machine(bore: str = "book", packing: float = 0.5) -> RadialSRMParams:
    """The 6/4 with the coil packed against the yoke: the clearance is solved so the coil side holds the
    copper at the given bundle packing (copper area / coil area)."""
    target = TURNS_PER_POLE * AWG19_AREA / packing
    lo = 1e-5
    p0 = _params(bore, lo)
    hi = p0.stator_yoke_inner_radius - p0.slot_liner_thickness - p0.bore_radius - 1e-4
    if coil_geometry(p0).area < target:
        raise ValueError(f"packing {packing}: the coil needs {target * 1e6:.0f} mm², more than the slot holds")
    clearance = brentq(lambda c: coil_geometry(_params(bore, c)).area - target, lo, hi, xtol=1e-9)
    return _params(bore, clearance)


def design(bore: str = "book", packing: float = 0.5, material: str = "M19", preset: str = "reference") -> Design:
    p = machine(bore, packing).model_copy(update={"materials": RegionMaterials(stator=material, rotor=material)})
    with waivers():
        return Design(machine=p, mesh=MeshSettings(preset=preset))


def point_table(points: dict, machine: RadialSRMParams) -> dict[str, np.ndarray]:
    """La, Lu (secant ψ/i at 0 and π/Nr) and Krishnan's stroke-averaged torque
    T_avg = m·Nr·(W′_aligned − W′_unaligned)/2π from {(angle, current): PointResult}."""
    unaligned = math.pi / machine.n_rotor_poles
    for (angle, i), r in points.items():
        if r.status is SolveStatus.NONCONVERGED:
            raise RuntimeError(f"6/4 solve did not converge at angle {angle:.4f} rad, {i} A")
    strokes = machine.n_phases * machine.n_rotor_poles
    la = np.array([points[(0.0, i)].psi[0] / i for i in CURRENTS])
    lu = np.array([points[(unaligned, i)].psi[0] / i for i in CURRENTS])
    t = np.array([strokes * (points[(0.0, i)].coenergy - points[(unaligned, i)].coenergy) / (2 * math.pi)
                  for i in CURRENTS])
    return {"La": la, "Lu": lu, "T_avg": t}


def table(d: Design, solver) -> dict[str, np.ndarray]:
    with waivers():
        static = build_machine_mesh(d)
    unaligned = math.pi / d.machine.n_rotor_poles
    points = {(a, i): solve_point(static, d, a, {"A": i}, solver) for a in (0.0, unaligned) for i in CURRENTS}
    return point_table(points, d.machine)


def corrected(t: dict, l_end: float) -> dict:
    return {"La": t["La"] + l_end, "Lu": t["Lu"] + l_end, "T_avg": t["T_avg"]}


def study(solver) -> dict:
    """Every table the report needs and the uncertainty budget (absolute half-spreads, SI). The primary
    result is `reference`; the other rows are at `full`, against the `full` primary."""
    tables = {
        "reference": table(design(preset="reference"), solver),
        "full": table(design(preset="full"), solver),
        "steel_1010": table(design(material="steel_1010", preset="full"), solver),
        "dissertation": table(design(bore="dissertation", preset="full"), solver),
        "packing_0.35": table(design(packing=0.35, preset="full"), solver),
        "packing_0.65": table(design(packing=0.65, preset="full"), solver),
    }
    l_end = {f: end_winding_inductance(machine(), f) for f in IMAGE_FACTORS}
    full = tables["full"]

    def half(a, b):
        return {q: np.abs(a[q] - b[q]) / 2 for q in a}

    before = {
        "mesh": {q: np.abs(tables["full"][q] - tables["reference"][q]) for q in full},
        "material": half(tables["steel_1010"], full),
        "geometry": half(tables["dissertation"], full),
        "coil packing": half(tables["packing_0.35"], tables["packing_0.65"]),
    }
    spread = abs(l_end[2.0] - l_end[1.0]) / 2
    after = before | {"end-winding model": {"La": np.full(3, spread), "Lu": np.full(3, spread), "T_avg": np.zeros(3)}}
    return {"tables": tables, "l_end": l_end, "budget_before": before, "budget_after": after}
