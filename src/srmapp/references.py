"""Reference radial SRM designs (8/6 four-phase, 12/8 and 24/16 three-phase). Each factory takes `**overrides` for
any `RadialSRMParams` field."""
import math
from collections.abc import Callable

from srmcore.model.design import RadialSRMParams


def make_8_6(**overrides) -> RadialSRMParams:
    values = dict(
        n_stator_poles=8, n_rotor_poles=6, n_phases=4,
        stator_outer_diameter=0.160, rotor_outer_diameter=0.080, air_gap=0.0004,
        stack_length=0.100, shaft_diameter=0.020,
        stator_pole_arc=math.radians(20.0), rotor_pole_arc=math.radians(22.0),
        stator_yoke_thickness=0.012, rotor_yoke_thickness=0.012,
        stator_fillet_radius=0.001, rotor_fillet_radius=0.001,
        turns_per_pole=60, fill_factor=0.5,
        slot_liner_thickness=0.0005, coil_inner_clearance=0.001,
    )
    values.update(overrides)
    return RadialSRMParams(**values)


def make_12_8(**overrides) -> RadialSRMParams:
    values = dict(
        n_stator_poles=12, n_rotor_poles=8, n_phases=3,
        stator_outer_diameter=0.180, rotor_outer_diameter=0.100, air_gap=0.0003,
        stack_length=0.080, shaft_diameter=0.030,
        stator_pole_arc=math.radians(15.0), rotor_pole_arc=math.radians(16.0),
        stator_yoke_thickness=0.011, rotor_yoke_thickness=0.012,
        stator_fillet_radius=0.0008, rotor_fillet_radius=0.0008,
        turns_per_pole=30, fill_factor=0.5,
        slot_liner_thickness=0.0004, coil_inner_clearance=0.001,
    )
    values.update(overrides)
    return RadialSRMParams(**values)


def make_24_16(**overrides) -> RadialSRMParams:
    values = dict(
        n_stator_poles=24, n_rotor_poles=16, n_phases=3,
        stator_outer_diameter=0.200, rotor_outer_diameter=0.130, air_gap=0.0003,
        stack_length=0.060, shaft_diameter=0.050,
        stator_pole_arc=math.radians(7.5), rotor_pole_arc=math.radians(8.0),
        stator_yoke_thickness=0.009, rotor_yoke_thickness=0.010,
        stator_fillet_radius=0.0005, rotor_fillet_radius=0.0005,
        turns_per_pole=12, fill_factor=0.45,
        slot_liner_thickness=0.0003, coil_inner_clearance=0.0008,
    )
    values.update(overrides)
    return RadialSRMParams(**values)


REFERENCES: dict[str, Callable[..., RadialSRMParams]] = {"8/6": make_8_6, "12/8": make_12_8, "24/16": make_24_16}
