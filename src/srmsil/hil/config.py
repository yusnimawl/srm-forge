"""Build-time modes of the HIL firmware and the generated `hil_config.h`."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from srmsil.scenario import AdcSettings, Scenario
from srmsil.tables import MotorData


ENCODER_EDGE_RATE_MAX = 400_000.0
"""Edges per second the emulator's encoder output may schedule: cpr * rev/s, one A or B edge per count."""


def resolver_rps_max(bits: int) -> float:
    """Electrical rev/s the emulated AD2S1210 tracks at a resolution (the datasheet's values for an 8.192 MHz clock, as
    hil/emulator/ad2s1210_slave.cpp)."""
    return 2500.0 if bits <= 10 else 1000.0 if bits <= 12 else 500.0 if bits <= 14 else 125.0


def check_encoder_rate(cpr: int, rpm: float) -> None:
    """Raise ValueError when cpr * rev/s exceeds ENCODER_EDGE_RATE_MAX."""
    rate = cpr * abs(rpm) / 60.0
    if rate > ENCODER_EDGE_RATE_MAX:
        raise ValueError(f"encoder edge rate {cpr} * {abs(rpm) / 60.0:g} rev/s = {rate:.0f} /s exceeds "
                         f"{ENCODER_EDGE_RATE_MAX:.0f} /s")


def check_isr_rate(scenario: Scenario) -> None:
    """Raise ValueError unless isr_hz = pwm_hz / k with k odd (1..127): the HIL samples at the carrier centre."""
    k = scenario.pwm_hz / scenario.resolved_isr_hz
    if not (abs(k - round(k)) <= 1e-6 * k and round(k) % 2 == 1 and round(k) <= 127):
        raise ValueError(f"isr_hz {scenario.resolved_isr_hz:g} Hz: the HIL samples at the carrier centre, so isr_hz must "
                         f"be pwm_hz / k with k odd (1..127); pwm_hz / isr_hz is {k:g}")


class HilModes(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    current_sense: Literal["ad7606", "internal"] = "ad7606"
    position: Literal["encoder", "ad2s1210", "both"] = "encoder"
    dac: Literal["mcp4922x2", "mcp4921x4"] = "mcp4922x2"

    @property
    def env_string(self) -> str:
        """The `SRM_HIL_MODES` value: current sensing, position, DAC."""
        return f"{self.current_sense},{self.position},{self.dac}"


def mode_defines(modes: HilModes) -> list[str]:
    """Macro names set to 1 for these modes. The DAC applies only to internal current sensing."""
    d = [f"HIL_CURRENT_SENSE_{modes.current_sense.upper()}"]
    if modes.position in ("encoder", "both"):
        d.append("HIL_POSITION_ENCODER")
    if modes.position in ("ad2s1210", "both"):
        d.append("HIL_POSITION_AD2S1210")
    if modes.current_sense == "internal":
        d.append(f"HIL_DAC_{modes.dac.upper()}")
    return d


AD7606_RANGE_V = 10.0
"""V, the AD7606 input range (+-)."""
AD7606_T_CONV_US = 4.15
"""us, the AD7606 conversion time (datasheet maximum without oversampling). The emulator accepts 1..1000 us, so the
CONVST interrupt has loaded the frame before BUSY falls."""
SENSE_TOP_V = 8.0
"""V at the AD7606 inputs for 1.25 x the top map current, and for 1.25 x the bus voltage."""
DAC_V_MID = 0.2
"""V at the DAC output for 0 A."""
DAC_VREF = 3.3
"""V, reference of the DACs and of the Nucleo's ADC (VDDA)."""
NUCLEO_ADC_BITS = 16


def sensor_chain(m: MotorData, scenario: Scenario) -> dict[str, float]:
    """Gains of the emulated sensor chain, shared by the emulator config and the controller's `hil_config.h`: the AD7606
    sees 8 V at 1.25 x the top map current and at 1.25 x the bus voltage; the DACs put out 0.2 V at 0 A and 3.3 V at
    1.2 x the top current."""
    i_top = float(m.currents[-1])
    vbus = scenario.bus_voltage or m.bus_voltage
    return {"ad7606_range_v": AD7606_RANGE_V, "ad7606_t_conv_us": AD7606_T_CONV_US,
            "sense_v_per_a": SENSE_TOP_V / (1.25 * i_top), "volt_divider": SENSE_TOP_V / (1.25 * vbus),
            "dac_v_mid": DAC_V_MID, "dac_v_per_a": (DAC_VREF - DAC_V_MID) / (1.2 * i_top)}


def adc_constants(modes: HilModes, scenario: Scenario, m: MotorData) -> tuple[int, float, int, float, int]:
    """The controller's ADC HAL constants of the sensing chain of `modes`: (bits, amps per count, offset counts, volts
    per count, volt offset counts). AD7606 codes are handed over as offset binary, 16 bits; the Nucleo ADC reads the
    DACs at 16 bits and has no voltage channels (volts per count 0)."""
    c = sensor_chain(m, scenario)
    if modes.current_sense == "ad7606":
        lsb = c["ad7606_range_v"] / 32768
        return 16, lsb / c["sense_v_per_a"], 32768, lsb / c["volt_divider"], 32768
    lsb = DAC_VREF / 2**NUCLEO_ADC_BITS
    return NUCLEO_ADC_BITS, lsb / c["dac_v_per_a"], round(c["dac_v_mid"] / lsb), 0.0, 0


def hil_adc(modes: HilModes, scenario: Scenario, m: MotorData) -> AdcSettings:
    """SIL ADC settings with the HAL constants and code range of the HIL's sensing chain (`adc_constants`): the SIL's
    amps per count is full_scale / (2^bits - 1), and its bipolar voltage channels have 2 volt_full_scale /
    (2^bits - 1) volts per count about the mid code. The scenario's volt_rc_tau is kept (the emulator applies it)."""
    bits, amps, offset, volts, _ = adc_constants(modes, scenario, m)
    top = 2**bits - 1
    return AdcSettings(bits=bits, full_scale=amps * top, offset_counts=offset,
                       volt_full_scale=volts * top / 2 if volts else None, volt_rc_tau=scenario.adc.volt_rc_tau)


def write_hil_config(modes: HilModes, scenario: Scenario, m: MotorData, path: Path) -> None:
    """The controller firmware's build constants: modes, PWM and ISR rates, bus voltage, and the ADC scales of the
    sensing chain of `modes` (AD7606 codes are handed over as offset binary, 16 bits; the Nucleo ADC reads the DACs at
    16 bits and has no voltage channels)."""
    se = scenario.sensors
    check_isr_rate(scenario)
    if modes.position in ("ad2s1210", "both") and se.resolver_bits not in (10, 12, 14, 16):
        raise ValueError(f"resolver_bits {se.resolver_bits}: the AD2S1210 has 10, 12, 14 or 16 bits")
    if modes.position in ("encoder", "both") and not 1 <= se.encoder_cpr <= 65536:
        raise ValueError(f"encoder_cpr {se.encoder_cpr}: the controller's 16-bit encoder timer takes 1..65536")
    bits, amps, offset, volts, volt_offset = adc_constants(modes, scenario, m)
    lines = [f"#define {n} 1" for n in mode_defines(modes)]
    lines += [
        f"#define HIL_PWM_HZ {scenario.pwm_hz!r}f",
        f"#define HIL_ISR_HZ {scenario.resolved_isr_hz!r}f",
        f"#define HIL_N_PHASES {m.n_phases}",
        f"#define HIL_VBUS_V {float(scenario.bus_voltage or m.bus_voltage)!r}f",
        f"#define HIL_ADC_BITS {bits}",
        f"#define HIL_ADC_AMPS_PER_COUNT {amps!r}f",
        f"#define HIL_ADC_OFFSET_COUNTS {offset}",
        f"#define HIL_ADC_VOLTS_PER_COUNT {volts!r}f",
        f"#define HIL_ADC_VOLT_OFFSET_COUNTS {volt_offset}",
        f"#define HIL_ENCODER_CPR {se.encoder_cpr}",
        f"#define HIL_RDC_BITS {se.resolver_bits}",
    ]
    Path(path).write_text("#ifndef HIL_CONFIG_H\n#define HIL_CONFIG_H\n\n" + "\n".join(lines) + "\n\n#endif\n")
