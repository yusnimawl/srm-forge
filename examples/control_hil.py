"""Bench acceptance of the control HIL: each reference controller on the two-board rig against its matched SIL.

For each controller: build both firmwares for the case and scenario, flash them when the boards do not already run
that build (the firmware hash), run_hil at a fixed speed, run the matched SIL, compare, and print one row (mean
torque, RMS current, ripple, the three differences, pass/fail and reason, valid, clock ratio, emulator step mean/max,
overruns, dropped, ISR mean/max, latency).

    $env:PYTHONPATH="src;tests;tests/sil"; python examples\\control_hil.py [--case SETUP.srm-setup.json]
        [--cache-dir DIR] [--controllers hysteresis pwm_current tsf] [--modes ad7606,encoder] [--rpm 1000]
        [--torque 1.0] [--bus V] [--param NAME=VALUE ...] [--json PATH]

Without --case the analytic motor of tests/sil/sil_fixtures.py is used. With --case the setup file is evaluated
(srmapp.case.evaluate_design; the map comes from --cache-dir when it is there, so point it at srmweb's cache) and the
evaluated motor is kept in --cache-dir. In ad2s1210 mode the scenario has no encoder (encoder_cpr 0) and the
resolver on, so the controllers take the resolver angle. Exit status 0 only when every row passed.
pyserial is taken from hil/.runtime when the interpreter has none.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
try:
    import serial  # noqa: F401
except ImportError:
    sys.path.append(str(ROOT / "hil" / ".runtime" / "Lib" / "site-packages"))

from srmsil.hil import HilError
from srmsil.hil.build import BuildResult, build_and_flash
from srmsil.hil.compare import compare, match_plan, refused
from srmsil.hil.config import HilModes
from srmsil.hil.session import HilSession, check_build, run_hil
from srmsil.hil.transport import SerialTransport, discover
from srmsil.run import run
from srmsil.scenario import Scenario, SensorSettings
from srmsil.tables import MotorData, motor_data

CONTROLLERS = ("hysteresis", "pwm_current", "tsf")


def load_motor(case: str | None, cache_dir: Path, bus: float | None) -> MotorData:
    if case is None:
        from sil_fixtures import analytic_motor
        m = analytic_motor()
        return m if bus is None else replace(m, bus_voltage=bus)
    import srmapp
    from srmapp.case import evaluate_design, map_key
    from srmweb.setup import SetupFile, case_inputs_from_setup
    text = Path(case).read_text()
    inputs = case_inputs_from_setup(SetupFile.model_validate_json(text))
    # the winding choice is not cached with the map, so the evaluated motor is kept per setup file, srmapp version
    # (the winding choice) and map provenance (the map's design, grids, solver and srmcore version)
    key = hashlib.sha256("
".join((text, srmapp.__version__, map_key(inputs))).encode()).hexdigest()[:16]
    saved = Path(cache_dir) / "control_hil" / f"motor_{key}.npz"
    if saved.is_file():
        z = np.load(saved)
        m = MotorData(z["angles"], z["currents"], z["psi"], z["torque"], float(z["resistance"]), int(z["n_phases"]),
                      int(z["n_rotor_poles"]), float(z["bus_voltage"]))
    else:
        e = evaluate_design(inputs, cache_dir=cache_dir)
        if e.error:
            print(f"evaluation note: {e.error}")
        m = motor_data(e, inputs.requirements.bus_voltage_v)
        saved.parent.mkdir(parents=True, exist_ok=True)
        np.savez(saved, **{k: getattr(m, k) for k in ("angles", "currents", "psi", "torque", "resistance", "n_phases",
                                                       "n_rotor_poles", "bus_voltage")})
    return m if bus is None else replace(m, bus_voltage=bus)


def parse_modes(s: str) -> HilModes:
    cs, pos = s.split(",")
    return HilModes(current_sense=cs, position=pos)


def open_session() -> HilSession:
    ports = discover()
    if ports.teensy is None or ports.stlink is None:
        raise HilError(f"rig not found: Teensy port {ports.teensy}, ST-LINK port {ports.stlink}")
    emu = SerialTransport(ports.teensy)
    try:
        return HilSession(emu, SerialTransport(ports.stlink))
    except BaseException:
        emu.close()
        raise


def flash(controller: str, m: MotorData, scenario: Scenario, modes: HilModes, cache_dir: Path) -> BuildResult:
    """Flash both boards with the build of (controller, case, scenario, modes) unless both already run it. The first
    Teensy upload after a reboot often fails, so a failed upload is tried once more."""
    b = build_and_flash(controller, m, scenario, modes, cache_dir=cache_dir, upload=False)
    if not b.ok:
        raise HilError("build failed:\n" + b.log[-3000:])
    s = open_session()
    try:
        check_build(s.connect(), b.firmware_hash)
        return b
    except HilError:
        pass                                   # another build, an older protocol or a board that does not answer
    finally:
        s.close()
    for attempt in (1, 2):
        b = build_and_flash(controller, m, scenario, modes, cache_dir=cache_dir, upload=True)
        if b.ok:
            return b
        print(f"upload attempt {attempt} failed")
    raise HilError("upload failed:\n" + b.log[-3000:])


def run_one(controller: str, m: MotorData, scenario: Scenario, modes: HilModes, cache_dir: Path) -> dict:
    build = flash(controller, m, scenario, modes, cache_dir)
    s = open_session()
    try:
        res = run_hil(s, m, controller, scenario, expect=build)
    finally:
        s.close()
    h = res.hil
    plan = match_plan(res, modes, m)
    if plan.scenario is None:
        c = refused(res, h["reason"] or plan.reason)
    else:
        c = compare(res, run(m, controller, plan.scenario, cache_dir=cache_dir), m=m, t0=plan.t0)
    keep = ("valid", "reason", "clock_ratio", "clock_spread_ppm", "step_mean_us", "step_max_us", "overruns", "dropped",
            "isr_mean_us", "isr_max_us", "isr_overruns", "latency_us", "capture_clipped", "bad_frames", "errors")
    return {"controller": controller, "firmware_hash": f"{build.firmware_hash:08x}",
            "hil": {"mean_torque": res.summary.mean_torque, "i_rms": float(np.sqrt(np.mean(res.summary.i_rms ** 2))),
                    "ripple_pct": res.summary.ripple_pct},
            "comparison": asdict(c), **{k: h.get(k) for k in keep}}


COLUMNS = ("controller", "T N m", "I A", "ripple %", "dT %", "dI %", "dR pts", "pass", "valid", "clock",
           "step us", "ovr", "drop", "ISR us", "lat us", "reason")


def row(r: dict) -> list[str]:
    def f(x, fmt):
        return "-" if x is None or (isinstance(x, float) and not math.isfinite(x)) else format(x, fmt)

    c, hl = r["comparison"], r["hil"]
    return [r["controller"], f(hl["mean_torque"], ".3f"), f(hl["i_rms"], ".2f"), f(hl["ripple_pct"], ".1f"),
            f(c["d_torque_pct"], "+.2f"), f(c["d_irms_pct"], "+.2f"), f(c["d_ripple_pts"], "+.2f"),
            "yes" if c["passed"] else "no", "yes" if r["valid"] else "no", f(r["clock_ratio"], ".6f"),
            f"{f(r['step_mean_us'], '.2f')}/{f(r['step_max_us'], '.2f')}", str(r["overruns"]), str(r["dropped"]),
            f"{f(r['isr_mean_us'], '.2f')}/{f(r['isr_max_us'], '.2f')}", f(r["latency_us"], ".2f"),
            c["reason"] or r["reason"] or ""]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--case", help="setup file of the case (default: the analytic motor of tests/sil/sil_fixtures.py)")
    p.add_argument("--cache-dir", type=Path, default=Path(tempfile.gettempdir()) / "srm_control_hil")
    p.add_argument("--controllers", nargs="+", default=list(CONTROLLERS))
    p.add_argument("--modes", type=parse_modes, default=HilModes(), help="current_sense,position (default ad7606,encoder)")
    p.add_argument("--rpm", type=float, default=1000.0, help="fixed speed")
    p.add_argument("--torque", type=float, default=1.0, help="torque command, N m")
    p.add_argument("--bus", type=float, help="bus voltage, V (default: the case's)")
    p.add_argument("--param", action="append", default=[], metavar="NAME=VALUE",
                   help="controller parameter for every controller (repeatable)")
    p.add_argument("--json", type=Path)
    a = p.parse_args(argv)
    m = load_motor(a.case, a.cache_dir, a.bus)
    params = {k: float(v) for k, v in (kv.split("=", 1) for kv in a.param)}
    # the reference controllers take the encoder when encoder_cpr > 0, else the resolver
    sensors = SensorSettings(encoder_cpr=0 if a.modes.position == "ad2s1210" else 4096,
                             resolver=a.modes.position != "encoder")
    scenario = Scenario(speed_rpm=a.rpm, command_value=a.torque, bus_voltage=a.bus, params=params, sensors=sensors)
    print(f"modes {a.modes.env_string}, {a.rpm:g} rpm, {a.torque:g} N m, bus {a.bus or m.bus_voltage:g} V, "
          f"map i_max {m.currents[-1]:.2f} A, params {params or 'defaults'}")
    rows = []
    for ctrl in a.controllers:
        try:
            rows.append(run_one(ctrl, m, scenario, a.modes, a.cache_dir))
        except HilError as e:
            print(f"{ctrl}: {e}")
            rows.append({"controller": ctrl, "error": str(e)})
    table = [COLUMNS] + [row(r) for r in rows if "error" not in r]
    widths = [max(len(t[i]) for t in table) for i in range(len(COLUMNS) - 1)]
    for t in table:
        print("  ".join(x.ljust(w) for x, w in zip(t, widths)) + "  " + t[-1])
    if a.json:
        a.json.write_text(json.dumps({"modes": a.modes.env_string, "rpm": a.rpm, "torque": a.torque,
                                      "bus_voltage": a.bus or m.bus_voltage, "case": a.case, "params": params,
                                      "rows": rows},
                                     indent=1, default=str))
    return 0 if rows and all("error" not in r and r["comparison"]["passed"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
