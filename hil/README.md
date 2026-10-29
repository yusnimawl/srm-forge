# HIL firmware

Two PlatformIO environments: `emulator` (Teensy 4.1, motor plant) and `controller` (Nucleo-H723ZG, the controller under test).
Wiring: `docs/r8b-hil-wiring.md`. Spec: `docs/superpowers/specs/2026-10-20-r8b-control-hil-design.md`.

## Set up

`hil\setup.bat` (Windows) or `sh hil/setup.sh` creates `hil/.runtime` (git-ignored) with PlatformIO 6.2.0 and, on the first build,
the teensy 6.0.0 and ststm32 20.0.0 platforms in `hil/.runtime/core`. Nothing is installed outside that folder.

## Build

From Python: `srmsil.hil.build.build_and_flash(controller, motor, scenario, HilModes(...), cache_dir=...)` writes
`srm_motor_tables.h` and `hil_config.h`, then runs `pio run` for both environments (`upload=True` flashes both boards).

By hand, as CI does: set `SRM_HIL_GEN_DIR` (folder with both headers), `SRM_CTRL_DIR` (controller folders, `os.pathsep`
separated), `SRM_HIL_MODES` (`ad7606|internal,encoder|ad2s1210|both,mcp4922x2|mcp4921x4`) and `PLATFORMIO_CORE_DIR=hil/.runtime/core`,
then `hil/.runtime/Scripts/pio run -d hil` (`bin/pio` on Linux).

`scripts/add_sources.py` adds the shared sources (`common/`), the plant (emulator only), the controller folders and the mode macros.
The controller console is USART3 (ST-LINK virtual COM port) at 921600 baud; the emulator uses USB serial.
