"""Vehicle-motor requirements (v0 spec §3). Peak-only: no continuous rating."""
import math

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .wire import Wire

# Same plausibility window as the srmcore validator's stator_outer_diameter unit rule.
_OD_RANGE = (0.01, 2.0)
_POWER_TOLERANCE = 0.10


class Requirements(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    peak_power_w: float = Field(gt=0)
    peak_torque_nm: float = Field(gt=0)
    base_speed_rpm: float = Field(gt=0)
    max_speed_rpm: float = Field(gt=0)
    bus_voltage_v: float = Field(default=400.0, gt=0)
    max_outer_diameter_m: float | None = Field(default=None, gt=0)
    max_mass_kg: float | None = Field(default=None, gt=0)
    wires: tuple[Wire, ...] = ()                                   # wire mode when non-empty
    phase_current_a: float | None = Field(default=None, gt=0)      # inverter peak phase current, A
    max_slot_fill: float = Field(default=0.6, gt=0, le=0.9)        # outer wire area / coil-side area

    @field_validator("max_outer_diameter_m")
    @classmethod
    def _metres(cls, value):
        if value is not None and not _OD_RANGE[0] <= value <= _OD_RANGE[1]:
            raise ValueError(f"{value} is outside {_OD_RANGE} metres; lengths are in metres")
        return value

    @model_validator(mode="after")
    def _consistent(self):
        if self.wires and self.phase_current_a is None:
            raise ValueError("wire mode (wires given) needs phase_current_a")
        if self.max_speed_rpm < self.base_speed_rpm:
            raise ValueError("max_speed_rpm must not be below base_speed_rpm")
        power_at_base = self.peak_torque_nm * self.base_speed_rpm * 2 * math.pi / 60
        if abs(power_at_base - self.peak_power_w) > _POWER_TOLERANCE * self.peak_power_w:
            raise ValueError(f"power {self.peak_power_w:.0f} W disagrees with torque x base speed "
                             f"= {power_at_base:.0f} W by more than {_POWER_TOLERANCE:.0%}")
        return self

    @property
    def wire_mode(self) -> bool:
        return bool(self.wires)
