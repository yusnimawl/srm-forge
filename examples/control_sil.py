"""Run the hysteresis and TSF reference controllers on the analytic test motor (R8a control SIL) and print the summaries.

    PYTHONPATH=tests/sil python examples/control_sil.py

Each run is 200 rpm at 0.3 x the motor's peak torque. The controller is compiled with zig and run in a spawned child."""
import tempfile
from pathlib import Path

from sil_fixtures import analytic_motor

from srmsil.run import run
from srmsil.scenario import Scenario

if __name__ == "__main__":
    motor = analytic_motor()
    t_cmd = 0.3 * float(motor.torque.max())
    scenario = Scenario(speed_rpm=200.0, duration=0.05, command_mode="torque", command_value=t_cmd)
    with tempfile.TemporaryDirectory(prefix="srmsil_example_") as cache:
        for name in ("hysteresis", "tsf"):
            result = run(motor, name, scenario, cache_dir=Path(cache))
            print(f"{name}: {result.summary}")
