"""Run scenarios for the control simulator: operating point, mechanics, converter and sensors."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_STEPS = 50_000_000


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ConverterSettings(_Model):
    v_switch: float = Field(1.0, ge=0)       # V, conduction drop per switch
    v_diode: float = Field(1.0, ge=0)        # V, per diode
    dead_time: float = Field(0.5e-6, ge=0)   # s, added to every turn-on
    turn_on_delay: float = Field(0.1e-6, ge=0)
    turn_off_delay: float = Field(0.2e-6, ge=0)


class SensorSettings(_Model):
    encoder_cpr: int = Field(4096, ge=0)     # counts per mechanical revolution, 0 = no encoder


class Scenario(_Model):
    mode: Literal["fixed", "dynamic"] = "fixed"
    speed_rpm: float = 1000.0                # fixed speed, or the initial speed in dynamic mode
    duration: float = Field(0.02, gt=0)      # s
    dt: float = Field(0.5e-6, gt=0)          # s
    command_mode: Literal["torque", "speed"] = "torque"
    command_value: float = 0.0               # N*m or rpm
    inertia: float = Field(1e-3, gt=0)       # kg*m^2
    friction: float = Field(0.0, ge=0)       # N*m*s/rad
    load: float = 0.0                        # N*m
    load_step: float = 0.0                   # N*m added at load_step_time
    load_step_time: float = Field(0.0, ge=0)
    theta0: float = 0.0                      # rad, initial rotor angle (phase A aligned at 0)
    bus_voltage: float | None = Field(None, gt=0)   # V, None = the motor data's
    pwm_hz: float = Field(20000.0, gt=0)
    isr_hz: float | None = Field(None, gt=0)        # None = pwm_hz
    compute_delay: float | None = Field(None, ge=0)  # s, None = one ISR period
    seed: int = Field(0, ge=0, lt=2**32)
    params: dict[str, float] = {}
    converter: ConverterSettings = ConverterSettings()
    sensors: SensorSettings = SensorSettings()

    @property
    def n_steps(self) -> int:
        return round(self.duration / self.dt)

    @property
    def resolved_isr_hz(self) -> float:
        return self.pwm_hz if self.isr_hz is None else self.isr_hz

    @property
    def resolved_compute_delay(self) -> float:
        return 1.0 / self.resolved_isr_hz if self.compute_delay is None else self.compute_delay

    @model_validator(mode="after")
    def _check(self):
        n = self.n_steps
        if n < 1:
            raise ValueError(f"duration {self.duration} s is shorter than one step of {self.dt} s")
        if n > MAX_STEPS:
            raise ValueError(f"{n} steps (duration / dt) exceed the limit of {MAX_STEPS}; shorten the run or raise dt")
        if self.pwm_hz * self.dt > 1 or self.resolved_isr_hz * self.dt > 1:
            raise ValueError("pwm_hz and isr_hz must not exceed 1 / dt")
        return self
