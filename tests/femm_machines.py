"""Machines, comparison points, tolerance rule and fixture hashes for the FEMM cross-tool comparison
(docs/superpowers/specs/2026-10-04-m5c-femm-design.md). Shared by tools/femm_fixtures.py, the slow test
and examples/femm_check.py."""
import hashlib
import math
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext

import numpy as np

from conftest import make_12_8
from srmcore.materials.laws import MU0, library_law
from srmcore.mesh import snap_angle
from srmcore.mesh.settings import resolve_mesh_settings
from srmcore.model.design import Design, MeshSettings, RadialSRMParams
from srmcore.model.validator import waive_rules

B_KNEE = 1.5                                     # T, aligned air-gap flux density at the knee current
CURRENT_FACTORS = (0.4, 1.7, 3.9)                # linear, rated, deep saturation (× knee current)
ANGLE_FRACTIONS = tuple(k / 30 for k in (0, 4, 8, 15, 22, 28, 30))   # of the unaligned angle π/Nr
MID_RANGE = (1 / 6, 5 / 6)                       # angle fractions with the 3 % torque tolerance


def _krishnan_8_6() -> RadialSRMParams:
    return RadialSRMParams(
        n_stator_poles=8, n_rotor_poles=6, n_phases=4,
        stator_outer_diameter=0.190, rotor_outer_diameter=0.0996, air_gap=0.0005,
        stack_length=0.200, shaft_diameter=0.028,
        stator_pole_arc=math.radians(18.0), rotor_pole_arc=math.radians(22.0),
        stator_yoke_thickness=0.012, rotor_yoke_thickness=0.016,
        stator_fillet_radius=0.0, rotor_fillet_radius=0.0,
        turns_per_pole=77, fill_factor=0.22,
        slot_liner_thickness=0.0005, coil_inner_clearance=0.001,
    )


def _jiang_24_16() -> RadialSRMParams:
    return RadialSRMParams(
        n_stator_poles=24, n_rotor_poles=16, n_phases=3,
        stator_outer_diameter=0.264, rotor_outer_diameter=0.183, air_gap=0.0005,
        stack_length=0.092, shaft_diameter=0.052,
        stator_pole_arc=math.radians(7.0), rotor_pole_arc=math.radians(7.2),
        stator_pole_taper=math.radians(6.0), rotor_pole_taper=math.radians(5.5),
        stator_yoke_thickness=0.015, rotor_yoke_thickness=0.0915 - 0.026 - 0.020,
        stator_fillet_radius=0.0, rotor_fillet_radius=0.0,
        turns_per_pole=15, fill_factor=0.54,
        slot_liner_thickness=0.0003, coil_inner_clearance=0.001,
    )


MACHINES: dict[str, Callable[[], RadialSRMParams]] = {
    "krishnan_8_6": _krishnan_8_6,
    "jiang_24_16": _jiang_24_16,
    "synth_12_8": make_12_8,
}

_WAIVED: dict[str, tuple[str, ...]] = {"jiang_24_16": ("self_starting",)}

ASSUMED: dict[str, dict[str, str]] = {
    "krishnan_8_6": {
        "slot_liner_thickness": "0.5 mm, not in the source",
        "coil_inner_clearance": "1 mm, not in the source",
        "fillets_tapers": "0, not in the source",
        "fill_factor": "0.22 from 77 turns x 1.588 mm^2 in a 550 mm^2 coil side",
        "materials": "M19 for stator and rotor (source: M43, not in the library)",
    },
    "jiang_24_16": {
        "rotor_yoke_thickness": "45.5 mm from an assumed rotor pole height of 20 mm (40 x air gap)",
        "rotor_pole_taper": "5.5 deg, middle of the thesis's 3-8 deg sizing range",
        "slot_liner_thickness": "0.3 mm, not in the source",
        "coil_inner_clearance": "1 mm, not in the source",
        "stack_length": "92 mm = 108 mm total minus 16 mm end-turn allowance",
        "pole_shoe_fillet": "1 mm pole-shoe fillet dropped (no topology counterpart)",
        "materials": "M19 for stator and rotor (source: 10JNEX900, not in the library)",
        "validator": "built inside waive_rules('self_starting')",
    },
    "synth_12_8": {"all": "synthetic machine tests/conftest.py make_12_8, complete geometry"},
}


def design(name: str) -> Design:
    return Design(machine=MACHINES[name](), mesh=MeshSettings(preset="full"))


def waivers(name: str) -> AbstractContextManager:
    rules = _WAIVED.get(name)
    return waive_rules(*rules) if rules else nullcontext()


def knee_current(p: RadialSRMParams) -> float:
    """Phase current at which the aligned air gap reaches B_KNEE with one pole's MMF per gap."""
    return B_KNEE * p.air_gap / (MU0 * p.turns_per_pole)


def currents(p: RadialSRMParams) -> tuple[float, float, float]:
    ik = knee_current(p)
    return tuple(float(f"{f * ik:.2g}") for f in CURRENT_FACTORS)


def points(d: Design) -> list[tuple[float, float]]:
    """(rotor angle, phase-A current) pairs, angle-major. Angles are snapped to the band pitch of the
    design's mesh, so FEMM is drawn at exactly the angle srmcore solves."""
    divisions = resolve_mesh_settings(d.machine, d.mesh).band_divisions
    unaligned = math.pi / d.machine.n_rotor_poles
    angles = [snap_angle(f * unaligned, divisions)[0] for f in ANGLE_FRACTIONS]
    return [(a, i) for a in angles for i in currents(d.machine)]


def tolerance(d: Design, angle: float, current: float) -> float:
    """Relative torque tolerance (spec §8.3): 3 % mid-stroke at or below rated current, else 5 %."""
    fraction = angle / (math.pi / d.machine.n_rotor_poles)
    mid = MID_RANGE[0] - 1e-9 <= fraction <= MID_RANGE[1] + 1e-9
    return 0.03 if mid and current <= currents(d.machine)[1] else 0.05


def bh_table(name: str) -> tuple[np.ndarray, np.ndarray]:
    """The srmcore effective (stacked) law sampled densely from 0 to 4 T: the B-H curve given to FEMM."""
    law = library_law(name)
    b = np.unique(np.concatenate([np.linspace(0.0, law.bn, 240), np.geomspace(law.bn, 4.0, 80)]))
    return b, law.h_of_b(b)


def _iron_materials(d: Design) -> list[str]:
    m = d.machine.materials
    return sorted({m.stator, m.rotor, m.shaft})


def design_sha256(d: Design) -> str:
    return hashlib.sha256(d.model_dump_json().encode()).hexdigest()


def bh_sha256(d: Design) -> str:
    """Hash of the tables sent to FEMM, printed at 10 significant digits so it is stable across platforms."""
    h = hashlib.sha256()
    for name in _iron_materials(d):
        b, hh = bh_table(name)
        h.update(name.encode())
        h.update(" ".join(f"{v:.10e}" for v in np.concatenate([b, hh])).encode())
    return h.hexdigest()
