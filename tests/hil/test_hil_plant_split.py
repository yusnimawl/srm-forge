import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest
from sil_fixtures import analytic_motor

from srmsil.build import zig_cc
from srmsil.run import run
from srmsil.scenario import Scenario

GOLDEN = Path(__file__).parent / "plant_golden.json"
CTRL = Path(__file__).parents[1] / "sil" / "controllers"


def _cases():
    return {
        "open_loop": (str(CTRL / "open_loop"),
                      Scenario(speed_rpm=1000.0, duration=0.02,
                               params={"theta_on": 0.1, "theta_off": 0.45})),
        "pwm_fixed": (str(CTRL / "pwm_fixed"), Scenario(speed_rpm=1000.0, duration=0.01)),
        "hysteresis": ("hysteresis", Scenario(mode="dynamic", speed_rpm=300.0, duration=0.02, inertia=1e-3,
                                              command_value=0.5)),
    }


def measure(cache_dir) -> dict:
    out = {}
    for name, (ctrl, scn) in _cases().items():
        r = run(analytic_motor(), ctrl, scn, cache_dir=cache_dir)
        s = r.summary
        out[name] = {"mean_torque": s.mean_torque, "ripple_pct": s.ripple_pct, "i_rms": [float(x) for x in s.i_rms],
                     "copper_loss": s.copper_loss, "energy_error": s.energy_error,
                     "i_sum": float(np.sum(r.traces["i"], dtype=np.float64))}
    return out


def test_plant_split_matches_golden(tmp_path):
    got = measure(tmp_path)
    if os.environ.get("HIL_REGEN") == "1":
        GOLDEN.write_text(json.dumps(got, indent=2))
    want = json.loads(GOLDEN.read_text())
    for name, vals in want.items():
        for key, v in vals.items():
            assert got[name][key] == pytest.approx(v, rel=1e-12, abs=1e-300), (name, key)


# The float build is the emulator's single-precision plant: no implicit promotion to double.
@pytest.mark.parametrize("flags", [[], ["-DSRM_TABLE_FLOAT", "-Wdouble-promotion"]])
def test_plant_compiles_alone(tmp_path, flags):
    plant = Path(__file__).parents[2] / "src" / "srmsil" / "c" / "plant"
    for i, src in enumerate(sorted(plant.glob("*.c"))):
        r = subprocess.run([*zig_cc(), "-std=c99", "-Wall", "-Wextra", "-Werror", *flags, f"-I{plant}", "-c",
                            "-o", str(tmp_path / f"{i}.o"), str(src)], capture_output=True, text=True)
        assert r.returncode == 0, f"{src.name}: {r.stderr}"
