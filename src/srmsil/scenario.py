"""Run scenarios for the control simulator: operating point, mechanics, converter and sensors."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_STEPS = 50_000_000
MAX_DELAY_STEPS = 2048   # size of the sensor delay ring in c/plant/srm_sensors.h
MAX_PARAM_NAME = 23


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class ConverterSettings(_Model):
    v_switch: float = Field(1.0, ge=0)       # V, conduction drop per switch
    v_diode: float = Field(1.0, ge=0)        # V, per diode
    dead_time: float = Field(0.5e-6, ge=0)   # s, added to every turn-on
    turn_on_delay: float = Field(0.1e-6, ge=0)
    turn_off_delay: float = Field(0.2e-6, ge=0)


class SensorSettings(_Model):
    encoder_cpr: int = Field(4096, ge=0)     # counts per mechanical revolution, 0 = no encoder
    encoder_offset: float = 0.0              # rad, mounting offset
    encoder_ecc_amp: float = 0.0             # rad, angle error amplitude
    encoder_ecc_harmonic: int = Field(1, ge=1)
    resolver: bool = False
    resolver_pole_pairs: int = Field(1, ge=1)
    resolver_bits: int = Field(12, ge=2, le=16)
    resolver_gain_mismatch: float = 0.0      # cos amplitude = 1 + mismatch, sin = 1
    resolver_phase_error: float = 0.0        # rad, added to the cos argument
    delay: float = Field(0.0, ge=0, le=1e-3)  # s, transport delay of the sensed currents and voltages


class AdcSettings(_Model):
    bits: int = Field(12, ge=1, le=16)
    full_scale: float | None = Field(None, gt=0)    # A at the top code, None = 1.25 x the motor data's top current
    offset_counts: int = Field(0, ge=0)      # nominal zero-current code, given to the controller
    offset_error: float = 0.0                # counts
    gain_error: float = 0.0                  # relative
    noise: float = Field(0.0, ge=0)          # counts, Gaussian sigma
    rc_tau: float = Field(0.0, ge=0)         # s, first-order filter on the sensed current, 0 = none
    volt_full_scale: float | None = Field(None, gt=0)   # V at the top code of the bipolar phase-voltage channels, None = none
    volt_rc_tau: float = Field(10e-6, ge=0)  # s, first-order filter on the sensed voltages

    @model_validator(mode="after")
    def _check_offset(self):
        if self.offset_counts > 2**self.bits - 1:
            raise ValueError(f"offset_counts {self.offset_counts} exceeds the top code {2**self.bits - 1}")
        return self


class ParamStep(_Model):
    """A controller parameter changed during the run, just before the first ISR at or after `time`."""

    time: float = Field(ge=0)                # s
    name: str = Field(min_length=1, max_length=MAX_PARAM_NAME)
    value: float

    @field_validator("name")
    @classmethod
    def _ascii(cls, v: str) -> str:
        if not v.isascii():
            raise ValueError("parameter names are ASCII")
        return v


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
    # The controller's clock frequency / its nominal frequency (1 = exact): its ISR, ctrl_slow, PWM carrier and
    # micros() run this much faster in true time. The HAL constants pwm_hz and isr_hz stay nominal, and
    # compute_delay, sensors.delay, the plant and the sensors stay in true time.
    controller_clock: float = Field(1.0, ge=0.9, le=1.1)
    seed: int = Field(0, ge=0, lt=2**32)
    params: dict[str, float] = {}
    converter: ConverterSettings = ConverterSettings()
    sensors: SensorSettings = SensorSettings()
    adc: AdcSettings = AdcSettings()
    param_steps: list[ParamStep] = []

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
        if max(self.pwm_hz, self.resolved_isr_hz) * self.controller_clock * self.dt > 1:   # true-time rates
            raise ValueError("pwm_hz and isr_hz (times controller_clock) must not exceed 1 / dt")
        steps = math.floor(self.sensors.delay / self.dt + 0.5)   # the rule of srm_sensor_delay_steps
        if steps > MAX_DELAY_STEPS:
            raise ValueError(f"sensor delay {self.sensors.delay} s is {steps} steps of {self.dt} s, over the limit of "
                             f"{MAX_DELAY_STEPS}; raise dt or shorten the delay")
        return self
