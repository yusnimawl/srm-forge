"""The IEEJ public-use SRM "SRM2" (SRM_HV): the 18/12 of Chiba et al., IEEE Trans. Energy Convers. 30(1), 2015,
and its 2D FEA maps from IEEJ Technical Report 1589 (2025), published on the IEEJ portal
http://www2.iee.or.jp/~drm/PublicUseMotors/ (actualMotors/SRM/SRM_HV). Fixture: tests/validation/fixtures/ieej_srm2.
Shared by examples/ieej_srm2_check.py and the slow test tests/validation/test_ieej_srm2.py.

The geometry is read off the portal drawing SRM2_CAD.dxf (radii and angles below, exact to the drawing's
precision); the drawing cannot be imported as it is (partial section, construction circles, open contours)."""
import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from srmcore.model.design import Design, MeshSettings, RadialSRMParams, RegionMaterials

FIXTURE = Path(__file__).parent / "validation" / "fixtures" / "ieej_srm2"
SOURCE_URL = "http://www2.iee.or.jp/~drm/PublicUseMotors/"

# SRM2_CAD.dxf (mm in the drawing)
STATOR_OD = 0.269                               # yoke arc r = 134.5
ROTOR_OD = 0.178                                # rotor pole tips r = 89.0
AIR_GAP = 0.5e-3                                # bore r = 89.5
STATOR_SLOT_BOTTOM_R = 0.116                    # stator yoke 18.5 mm
ROTOR_SLOT_BOTTOM_R = 0.070
SHAFT_D = 0.070                                 # rotor inner circle r = 35
STATOR_HALF_ARC = math.radians(5.228482)        # flank meets the bore at 20 k +- 5.2285 deg
ROTOR_HALF_ARC = math.radians(5.513788)         # flank meets the rotor OD at 15 + 30 k +- 5.5138 deg
STATOR_TAPER = math.radians(10.0)               # flank direction against the pole axis, from the drawing
ROTOR_TAPER = math.radians(3.0)                 # 3.0014 deg in the drawing
COIL_INNER_R = 0.0905                           # coil sides start 1 mm outside the bore
# portal spec table (SRM2 column)
STACK = 0.135
TURNS_PER_POLE = 17
LAMINATION = 0.1e-3
CURRENT_MAX = 250.0

# The portal tables run over positions x = 10 .. 20 with zero torque at both ends and the flux linkage rising
# monotonically from x = 10 to 20, so x = 10 is unaligned and x = 20 aligned over half a rotor pole pitch (15 deg).
# In srmcore phase A is aligned at 0 and motoring is counter-clockwise, so the stroke runs from -15 deg to 0.
X_UNALIGNED, X_ALIGNED = 10.0, 20.0
STROKE = math.pi / 12

# SRM2_T-position.csv is the torque of the portal's half-machine model: the torque from the co-energy of
# SRM2_Flux-I.csv is 1.95 to 2.03 times the table at the interior positions (central differences on the 1 deg
# grid; checked in tests/validation/test_ieej_srm2.py).
TORQUE_TABLE_FACTOR = 2.0

ASSUMED = {
    "geometry": "read off SRM2_CAD.dxf; no fillets in the drawing",
    "slot_liner_thickness": "0.1 mm; the drawing's coil side lies on the pole flank (no liner)",
    "coil_inner_clearance": "1.0 mm, as drawn (coil from r = 90.5 mm to the slot bottom)",
    "fill_factor": "0.5, sets resistance only, not psi or torque",
    "shaft": "non-magnetic (copper, vacuum law); the portal gives no shaft material",
    "materials": "10JNEX900 from the srmcore library (catalogue curve, stacking factor 0.9); the portal shows "
                 "its B-H curve as a figure only, so the curve its maps used is not known exactly",
    "angle": "portal position x maps to rotor angle 1.5 (x - 10) - 15 deg (unaligned at x = 10)",
    "torque": f"portal torque table x {TORQUE_TABLE_FACTOR:g} (half-machine model)",
}


def params(materials: RegionMaterials | None = None) -> RadialSRMParams:
    return RadialSRMParams(
        n_stator_poles=18, n_rotor_poles=12, n_phases=3,
        stator_outer_diameter=STATOR_OD, rotor_outer_diameter=ROTOR_OD, air_gap=AIR_GAP,
        stack_length=STACK, shaft_diameter=SHAFT_D,
        stator_pole_arc=2 * STATOR_HALF_ARC, rotor_pole_arc=2 * ROTOR_HALF_ARC,
        stator_pole_taper=STATOR_TAPER, rotor_pole_taper=ROTOR_TAPER,
        stator_yoke_thickness=STATOR_OD / 2 - STATOR_SLOT_BOTTOM_R,
        rotor_yoke_thickness=ROTOR_SLOT_BOTTOM_R - SHAFT_D / 2,
        turns_per_pole=TURNS_PER_POLE, fill_factor=0.5,
        slot_liner_thickness=1e-4, coil_inner_clearance=COIL_INNER_R - (ROTOR_OD / 2 + AIR_GAP),
        lamination_thickness=LAMINATION,
        materials=materials or RegionMaterials(stator="10JNEX900", rotor="10JNEX900", shaft="copper"),
    )


# The portal positions are whole degrees of the stroke, so a multiple of 360 band divisions puts every one of them
# on a band node; the band also needs a multiple of lcm(Ns, 2 Nr) = 72. Each value is the multiple of 360 nearest
# to what the preset would choose (1512, 2160, 6048), so the band keeps the preset's aspect.
BAND_DIVISIONS = {"screening": 1440, "full": 2160, "reference": 6120}


def design(preset: str = "screening", materials: RegionMaterials | None = None) -> Design:
    return Design(machine=params(materials),
                  mesh=MeshSettings(preset=preset, airgap_circumferential_divisions=BAND_DIVISIONS[preset]))


def angle_of(x: float) -> float:
    """srmcore rotor angle (rad) of portal position x."""
    return (x - X_UNALIGNED) / (X_ALIGNED - X_UNALIGNED) * STROKE - STROKE


@dataclass(frozen=True)
class Table:
    """One portal map: values[i, k] at currents[i] (A, phase U only) and positions[k] (portal x)."""
    positions: np.ndarray
    currents: np.ndarray
    values: np.ndarray

    @property
    def angles(self) -> np.ndarray:
        return np.array([angle_of(x) for x in self.positions])


def _table(name: str) -> Table:
    with open(FIXTURE / name, newline="") as f:
        rows = [r for r in csv.reader(f) if r]
    positions = np.array([float(v) for v in rows[0][1:]])
    currents = np.array([float(r[0]) for r in rows[1:]])
    values = np.array([[float(v) for v in r[1:]] for r in rows[1:]])
    return Table(positions, currents, values)


def flux_table() -> Table:
    """SRM2_Flux-I.csv: phase-U flux linkage (Wb) of the whole machine."""
    return _table("SRM2_Flux-I.csv")


def torque_table() -> Table:
    """SRM2_T-position.csv scaled to the whole machine (N m)."""
    t = _table("SRM2_T-position.csv")
    return Table(t.positions, t.currents, t.values * TORQUE_TABLE_FACTOR)


def coenergy_table(flux: Table) -> Table:
    """Co-energy W'(i, theta) = integral of psi di from 0 (J), trapezoidal on the portal's 10 A grid."""
    steps = 0.5 * (flux.values[1:] + flux.values[:-1]) * np.diff(flux.currents)[:, None]
    return Table(flux.positions, flux.currents, np.vstack([np.zeros(len(flux.positions)), np.cumsum(steps, axis=0)]))


def coenergy_torque(flux: Table) -> np.ndarray:
    """Torque (N m) from the co-energy of the flux table, dW'/dtheta by central differences, same shape."""
    return np.gradient(coenergy_table(flux).values, flux.angles, axis=1)
