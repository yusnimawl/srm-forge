"""Kiyota 18/12 prototype with 10JNEX900 laminations: K. Kiyota and A. Chiba, Design of switched reluctance motor
competitive to 60-kW IPMSM in third-generation hybrid electric vehicle, IEEE Trans. Ind. Appl. 48(6), 2012
(Table II, Figs. 6 and 7), and K. Kiyota, T. Kakishima, A. Chiba, Comparison of test result and design stage
prediction of switched reluctance motor competitive with 60-kW rare-earth PM motor, IEEE Trans. Ind. Electron.
61(10), 2014 (Tables I to III, Fig. 16). Plan: docs/superpowers/plans/2026-11-18-kiyota-iron-check.md.
Figure readings: tools/digitise_kiyota.py."""
import math

from scipy.optimize import brentq

from srmcore.maps.end_winding import coil_geometry
from srmcore.model.design import Design, MeshSettings, RadialSRMParams, RegionMaterials
from srmcore.model.validator import waive_rules

# cited
STATOR_OD = 0.264                                    # 2012 Table II
ROTOR_R = 0.091                                      # rotor outer radius
AIR_GAP = 0.5e-3
STACK = 87.2e-3                                      # 87.25 mm stator, 87.15 mm rotor
STATOR_TAPER = math.radians(7.5)                     # 2012 Fig. 6
TURNS_PER_POLE = 20
WIRES, WIRE_D = 9, 0.9e-3                            # parallel strands, bare diameter
FILL = 0.56
BUS_V = 650.0
R_PHASE_20C = 97.8e-3                                # ohm, measured (20 C assumed)
LAMINATION = 0.10e-3
# read off Fig. 7
STATOR_ARC, ROTOR_ARC = math.radians(10.0), math.radians(10.46)
ROTOR_TAPER = math.radians(1.52)
SHAFT_R = 55.1e-3
ROTOR_YOKE = 17.0e-3                                 # rotor slot bottom radius 72.1 mm
STATOR_YOKE = 16.3e-3                                # slot bottom radius 115.7 mm; 15.5 mm is the design-study point
LINER = 0.3e-3
MIN_CLEARANCE = 0.1e-3                               # coil to bore; the smallest the mesh should carry
COPPER_AREA = TURNS_PER_POLE * WIRES * math.pi * (WIRE_D / 2) ** 2      # m², one coil side
ASSUMED = {
    "stator and rotor geometry": "Fig. 7 readings (about +-0.3 mm); stator taper 7.5 deg cited, not the 7.43 deg read",
    "stator yoke": "16.3 mm read; 15.5 mm (2012 design study point b) as a sensitivity row",
    "fillets": "0, the rounded slot corners of the drawing are not read",
    "slot_liner_thickness": "0.3 mm, not in the source",
    "shaft": "the 110 mm hub is the default shaft material",
    "coil": "fills the half slot against the yoke at 0.1 mm clearance (59.7 % of the coil area; the cited 56 % does not fit inside the liner)",
    "materials": "10JNEX900 stator and rotor, 0.10 mm",
    "resistance": "97.8 mohm taken at 20 C",
    "validator": "built inside waive_rules('self_starting') if the validator asks",
}


def waivers():
    return waive_rules("self_starting")


def _params(clearance: float, stator_yoke: float, fill: float = FILL) -> RadialSRMParams:
    return RadialSRMParams(
        n_stator_poles=18, n_rotor_poles=12, n_phases=3,
        stator_outer_diameter=STATOR_OD, rotor_outer_diameter=2 * ROTOR_R, air_gap=AIR_GAP,
        stack_length=STACK, shaft_diameter=2 * SHAFT_R,
        stator_pole_arc=STATOR_ARC, rotor_pole_arc=ROTOR_ARC,
        stator_pole_taper=STATOR_TAPER, rotor_pole_taper=ROTOR_TAPER,
        stator_yoke_thickness=stator_yoke, rotor_yoke_thickness=ROTOR_YOKE,
        stator_fillet_radius=0.0, rotor_fillet_radius=0.0,
        turns_per_pole=TURNS_PER_POLE, fill_factor=fill,
        slot_liner_thickness=LINER, coil_inner_clearance=clearance, lamination_thickness=LAMINATION,
    )


def machine(stator_yoke: float = STATOR_YOKE) -> RadialSRMParams:
    """The 18/12 with the coil packed against the yoke: the clearance is solved so the coil side holds the copper
    area at the cited slot fill. The cited 56 % does not fit the coil area inside the liner (192 mm² against the
    204 mm² it needs, 199 mm² at the 15.5 mm yoke), so the cited fill is taken over a larger slot area than the
    model's coil side; the coil then fills the half slot at MIN_CLEARANCE and `fill_factor` is the copper over
    that coil area."""
    target = COPPER_AREA / FILL
    p0 = _params(MIN_CLEARANCE, stator_yoke)
    area0 = coil_geometry(p0).area
    if area0 <= target:
        return _params(MIN_CLEARANCE, stator_yoke, COPPER_AREA / area0)
    hi = p0.stator_yoke_inner_radius - p0.slot_liner_thickness - p0.bore_radius - 1e-4
    clearance = brentq(lambda c: coil_geometry(_params(c, stator_yoke)).area - target, MIN_CLEARANCE, hi, xtol=1e-9)
    return _params(clearance, stator_yoke)


def design(preset: str = "full", stator_yoke: float = STATOR_YOKE) -> Design:
    p = machine(stator_yoke).model_copy(update={"materials": RegionMaterials(stator="10JNEX900", rotor="10JNEX900")})
    with waivers():
        return Design(machine=p, mesh=MeshSettings(preset=preset))
