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


def test_modes_reject_unknown():
    for kw in ({"current_sense": "x"}, {"position": "x"}, {"dac": "x"}, {"other": 1}):
        with pytest.raises(ValidationError):
            HilModes(**kw)


def test_pio_missing_message(monkeypatch, tmp_path):
    monkeypatch.setattr(build, "RUNTIME", tmp_path / "none")
    with pytest.raises(HilError, match="PlatformIO is not set up"):
        build.pio_executable()


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
