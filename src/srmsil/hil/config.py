"""Build-time modes of the HIL firmware and the generated `hil_config.h`."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from srmsil.run import ADC_HEADROOM
from srmsil.scenario import Scenario
from srmsil.tables import MotorData


ENCODER_EDGE_RATE_MAX = 400_000.0
"""Edges per second the emulator's encoder output may schedule: cpr * rev/s, one A or B edge per count."""


def check_encoder_rate(cpr: int, rpm: float) -> None:
    """Raise ValueError when cpr * rev/s exceeds ENCODER_EDGE_RATE_MAX."""
    rate = cpr * abs(rpm) / 60.0
    if rate > ENCODER_EDGE_RATE_MAX:
        raise ValueError(f"encoder edge rate {cpr} * {abs(rpm) / 60.0:g} rev/s = {rate:.0f} /s exceeds "
                         f"{ENCODER_EDGE_RATE_MAX:.0f} /s")


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


def write_hil_config(modes: HilModes, scenario: Scenario, m: MotorData, path: Path) -> None:
    ad = scenario.adc
    full_scale = ad.full_scale or ADC_HEADROOM * float(m.currents[-1])
    lines = [f"#define {n} 1" for n in mode_defines(modes)]
    lines += [
        f"#define HIL_PWM_HZ {scenario.pwm_hz!r}f",
        f"#define HIL_ISR_HZ {scenario.resolved_isr_hz!r}f",
        f"#define HIL_N_PHASES {m.n_phases}",
        f"#define HIL_ADC_BITS {ad.bits}",
        f"#define HIL_ADC_AMPS_PER_COUNT {full_scale / (2**ad.bits - 1)!r}f",
        f"#define HIL_ADC_OFFSET_COUNTS {ad.offset_counts}",
        f"#define HIL_ENCODER_CPR {scenario.sensors.encoder_cpr}",
    ]
    Path(path).write_text("#ifndef HIL_CONFIG_H\n#define HIL_CONFIG_H\n\n" + "\n".join(lines) + "\n\n#endif\n")
