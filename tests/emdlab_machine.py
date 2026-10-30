"""The EMDLAB / ANSYS Maxwell 8/6 benchmark machine and its reference data (tests/validation/fixtures/emdlab_8_6,
docs/emdlab-srm-reference.md). Shared by the slow test tests/validation/test_emdlab.py and examples/emdlab_check.py."""
import csv
import math
from dataclasses import dataclass
from pathlib import Path

from srmcore.model.design import Design, MeshSettings, RadialSRMParams, RegionMaterials

FIXTURE = Path(__file__).parent / "validation" / "fixtures" / "emdlab_8_6"
CURRENT = 3.6                      # A, phase A only
UNALIGNED = math.radians(30.0)     # Maxwell's theta_tab = 0
# The reference angles are steps of 30/29 deg = 2*pi/348. The band needs a multiple of lcm(Ns, 2*Nr) = 24
# divisions; 1392 = 2 * lcm(24, 348) puts every reference angle on a band node (no snapping) and is finer
# than the 888 the `full` preset would choose.
BAND_DIVISIONS = 1392

ASSUMED = {
    "slot_liner_thickness": "0.1 mm; EMDLAB's coil touches the tooth flank (no liner)",
    "coil_inner_clearance": "0.1 mm; EMDLAB's coil starts at the bore",
    "fill_factor": "0.5, sets resistance only, not psi or torque",
    "shaft": "copper (vacuum law); EMDLAB has no shaft and sets A = 0 at r = 10 mm",
    "materials": "M530_50A from EMDLAB's library, stacking factor 1.0 as EMDLAB uses",
    "band": f"{BAND_DIVISIONS} circumferential divisions so every reference angle is a band node",
}


def params() -> RadialSRMParams:
    """Paper Table 3 and emdlab_examples_srm86.m: parallel-sided teeth (taper 0), arcs at the bore and rotor OD."""
    return RadialSRMParams(
        n_stator_poles=8, n_rotor_poles=6, n_phases=4,
        stator_outer_diameter=0.125, rotor_outer_diameter=0.073, air_gap=0.0005,
        stack_length=0.070, shaft_diameter=0.020,
        stator_pole_arc=math.radians(17.1), rotor_pole_arc=math.radians(19.8),
        stator_yoke_thickness=0.0077, rotor_yoke_thickness=0.00753,
        turns_per_pole=278, fill_factor=0.5,
        slot_liner_thickness=1e-4, coil_inner_clearance=1e-4,
        materials=RegionMaterials(stator="M530_50A", rotor="M530_50A", shaft="copper"),
    )


def design(preset: str = "full") -> Design:
    return Design(machine=params(), mesh=MeshSettings(preset=preset, airgap_circumferential_divisions=BAND_DIVISIONS))


@dataclass(frozen=True)
class Reference:
    """One reference angle. `angle` is the srmcore rotor angle (rad, phase A aligned at 0); torque is positive on
    the unaligned-to-aligned stroke in both tools."""
    theta_tab_deg: float
    angle: float
    torque_maxwell: float
    psi: float
    energy: float
    coenergy: float
    torque_emdlab: float


def _rows(name: str) -> list[dict[str, str]]:
    with open(FIXTURE / name, newline="") as f:
        return list(csv.DictReader(f))


def references() -> list[Reference]:
    maxwell = _rows("maxwell_8_6_torque.csv")
    emdlab = _rows("emdlab_8_6_sweep.csv")
    out = []
    for m, e in zip(maxwell, emdlab, strict=True):
        if not math.isclose(float(m["theta_tab_deg"]), float(e["theta_tab_deg"]), abs_tol=1e-9):
            raise ValueError("Maxwell and EMDLAB rows are not on the same angles")
        out.append(Reference(
            theta_tab_deg=float(m["theta_tab_deg"]),
            angle=math.radians(float(m["rotor_deg_from_aligned"])),
            torque_maxwell=float(m["torque_nm"]),
            psi=float(e["psi_wb_turns"]),
            energy=float(e["energy_j"]),
            coenergy=float(e["coenergy_j"]),
            torque_emdlab=float(e["torque_arkkio_nm"]),
        ))
    return out
