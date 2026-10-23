import os
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError
from sil_fixtures import analytic_motor

from srmsil.hil import HilError, build
from srmsil.hil.config import HilModes, write_hil_config
from srmsil.run import controller_dir
from srmsil.scenario import Scenario
from srmsil.tables import ctrl_tables, write_header

ROOT = Path(__file__).parents[2]
HAVE_PIO = (ROOT / "hil" / ".runtime" / ("Scripts/pio.exe" if os.name == "nt" else "bin/pio")).is_file()


def test_hil_config_header(tmp_path):
    p = tmp_path / "hil_config.h"
    write_hil_config(HilModes(current_sense="ad7606", position="ad2s1210"), Scenario(), analytic_motor(), p)
    t = p.read_text()
    assert "#define HIL_CURRENT_SENSE_AD7606 1" in t
    assert "#define HIL_POSITION_AD2S1210 1" in t
    assert "HIL_POSITION_ENCODER" not in t
    assert "HIL_DAC_" not in t
    assert "#define HIL_N_PHASES 4" in t and "HIL_PWM_HZ" in t and "HIL_ISR_HZ" in t
    write_hil_config(HilModes(current_sense="internal", position="both", dac="mcp4921x4"), Scenario(),
                     analytic_motor(), p)
    t = p.read_text()
    assert "HIL_CURRENT_SENSE_INTERNAL 1" in t and "HIL_DAC_MCP4921X4 1" in t
    assert "HIL_POSITION_ENCODER 1" in t and "HIL_POSITION_AD2S1210 1" in t


def _macros(path):
    out = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "#define":
            out[parts[1]] = float(parts[2].rstrip("f"))
    return out


def test_hil_config_sensor_scales(tmp_path):
    m, p = analytic_motor(), tmp_path / "hil_config.h"
    write_hil_config(HilModes(current_sense="ad7606"), Scenario(), m, p)
    d = _macros(p)
    i_top = float(m.currents[-1])
    assert d["HIL_ADC_BITS"] == 16 and d["HIL_ADC_OFFSET_COUNTS"] == 32768 and d["HIL_ADC_VOLT_OFFSET_COUNTS"] == 32768
    assert d["HIL_ADC_AMPS_PER_COUNT"] == pytest.approx(10.0 / 32768 * 1.25 * i_top / 8.0)
    assert d["HIL_ADC_VOLTS_PER_COUNT"] == pytest.approx(10.0 / 32768 * 1.25 * m.bus_voltage / 8.0)
    assert d["HIL_VBUS_V"] == pytest.approx(m.bus_voltage) and d["HIL_RDC_BITS"] == 12
    write_hil_config(HilModes(current_sense="internal"), Scenario(bus_voltage=60.0), m, p)
    d = _macros(p)
    assert d["HIL_ADC_VOLTS_PER_COUNT"] == 0 and d["HIL_VBUS_V"] == 60.0
    v_per_a = 3.1 / (1.2 * i_top)
    assert d["HIL_ADC_OFFSET_COUNTS"] == round(0.2 / 3.3 * 65536)
    assert d["HIL_ADC_AMPS_PER_COUNT"] == pytest.approx(3.3 / 65536 / v_per_a)
    with pytest.raises(ValueError, match="AD2S1210"):
        write_hil_config(HilModes(position="both"), Scenario(sensors={"resolver_bits": 11}), m, p)
    for isr in (40000.0, 10000.0, 5000.0):        # 2 x pwm, k = 2 and 4: not the carrier centre
        with pytest.raises(ValueError, match="k odd"):
            write_hil_config(HilModes(), Scenario(pwm_hz=20000.0, isr_hz=isr), m, p)
    write_hil_config(HilModes(), Scenario(pwm_hz=30000.0, isr_hz=10000.0), m, p)
    assert "#define HIL_ISR_HZ 10000.0f" in p.read_text()
    with pytest.raises(ValueError, match="encoder_cpr"):
        write_hil_config(HilModes(position="encoder"), Scenario(sensors={"encoder_cpr": 0}), m, p)
    write_hil_config(HilModes(position="ad2s1210"), Scenario(sensors={"encoder_cpr": 0}), m, p)


def test_modes_reject_unknown():
    for kw in ({"current_sense": "x"}, {"position": "x"}, {"dac": "x"}, {"other": 1}):
        with pytest.raises(ValidationError):
            HilModes(**kw)


def test_pio_missing_message(monkeypatch, tmp_path):
    monkeypatch.setattr(build, "RUNTIME", tmp_path / "none")
    with pytest.raises(HilError, match="PlatformIO is not set up"):
        build.pio_executable()


def test_firmware_hash_is_the_build_hash(monkeypatch, tmp_path):
    """firmware_hash (the session's check of the current sources) gives the hash build_and_flash builds with."""
    monkeypatch.setattr(build, "pio_executable", lambda: Path("pio"))
    monkeypatch.setattr(build.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "SUCCESS", ""))
    m, scn = analytic_motor(), Scenario()
    for ctrl, modes in (("hysteresis", HilModes()), ("tsf", HilModes(position="ad2s1210"))):
        r = build.build_and_flash(ctrl, m, scn, modes, cache_dir=tmp_path, upload=True)
        assert r.firmware_hash == build.firmware_hash(ctrl, m, scn, modes)
    assert build.firmware_hash("hysteresis", m, scn, HilModes()) != build.firmware_hash("tsf", m, scn, HilModes())


@pytest.mark.skipif(not HAVE_PIO, reason="hil/.runtime is not set up (run hil/setup.bat)")
@pytest.mark.parametrize("modes", [HilModes(), HilModes(current_sense="internal", position="ad2s1210")])
def test_pio_compiles_both_envs(modes, tmp_path):
    r = build.build_and_flash("hysteresis", analytic_motor(), Scenario(), modes, cache_dir=tmp_path, upload=False)
    assert r.ok, r.log[-3000:]
    assert 0 <= r.firmware_hash < 2**32
    assert "SUCCESS" in r.log


def test_script_mode_validation():
    import sys
    sys.path.insert(0, str(ROOT / "hil" / "scripts"))
    from hil_modes import mode_macros

    assert mode_macros("ad7606,both,mcp4922x2") == ["HIL_CURRENT_SENSE_AD7606=1", "HIL_POSITION_ENCODER=1",
                                                    "HIL_POSITION_AD2S1210=1"]
    assert "HIL_DAC_MCP4921X4=1" in mode_macros("internal,encoder,mcp4921x4")
    assert mode_macros("") == []
    for bad in ("ad7606,resolver", "foo,encoder", "internal,encoder,dac9", "ad7606", "a,b,c,d", "ad7606,encoder,x"):
        with pytest.raises(ValueError):
            mode_macros(bad)
