# R8b control HIL results

## Bring-up

Firmware project: PlatformIO 6.2.0, teensy 6.0.0, ststm32 20.0.0. Both environments compile in the modes ad7606+encoder and internal+ad2s1210 (internal+both also checked). Each firmware only answers HELLO with BUILD_INFO.

Bench (2026-10-21, modes ad7606 + encoder, hysteresis reference controller, analytic motor; boards not wired to each other):

- Nucleo-H723ZG: ST-LINK V3 (VID 0483 PID 374E), VCP on COM6. `build_and_flash(upload=True)` flashed through OpenOCD (programming and verify OK). Controller firmware: flash 9380 B (0.9 %), RAM 1236 B (0.4 %).
- Teensy 4.1: COM4 (VID 16C0 PID 0483). The first `teensy-cli` upload failed with "error writing to Teensy"; a retry a few seconds later succeeded (no button press). Emulator firmware: flash code 10404 B + data 3016 B (`teensy_size`).
- HELLO at 921600 baud on COM6 and over USB serial on COM4, decoded BUILD_INFO (protocol, board, current_sense, position, dac, firmware_hash):
  - COM6: (1, 2, 0, 0, 0, 0x1986e876), the controller, as expected.
  - COM4: (1, 1, 0, 0, 0, 0x1986e876), the emulator, as expected.
  - The hash equals the build's `firmware_hash`.
- First attempt on COM6 got no reply. Read through OpenOCD: PLL1 and the bus dividers were as configured, but USART3 BRR was 339, i.e. a 312 MHz kernel clock. The stm32cube framework carries its own `stm32h7xx_hal_conf.h` with `HSE_VALUE` 25 MHz, which the HAL library builds use instead of `hil/controller/stm32h7xx_hal_conf.h`, so the HAL computed the clock for 25 MHz. Fixed with `-DHSE_VALUE=8000000UL` in the controller `build_flags`; the reply then arrived.

## Bench checks

### Emulator core (2026-10-21, Teensy 4.1 at 600 MHz, mode ad7606 + encoder, boards not wired to each other)

`examples/hil_emu_selftest.py`: the analytic motor at a fixed 1000 rpm, tables uploaded on the 180 x 192 grid, the
default converter delays, and the emulator's software gate pattern (`HIL_COMMAND` mode 2: phase A, both switches,
20 kHz, 50 %, first rise 1000 cycles into step 0) in place of the gate inputs and RUN.

| Item | Result | Target |
|---|---|---|
| Step time, mean | 3.86 us (77 % of dt) | - |
| Step time, max | 5.6 us | < 4 us (80 %) - **not met** |
| Overruns (step longer than 5 us) | about 10 % of steps | 0 - **not met** |
| Buffered capture, 8000 steps | all samples, contiguous, no sequence gap; `valid = 0` (overruns during it) | valid |
| Streamed capture, 100 000 steps | ring full after 8556 samples (`dropped` 1, `valid = 0`) | valid |
| Phase-A current vs `srmsil.emumodel.run_model` on the same edges, RMS at the step instants | +0.002 % (buffered), +0.002 % (streamed part); max sample difference 0.64 mA = half a count | within 1 % - met |
| Live statistics | 20 Hz, one packet per 10 000 steps | - |
| Output latency (last edge to the end of the output stage, stubbed) | 8.7 us | - |

Profile with the cycle counter (mean / max cycles of the 3000 per step): gate averaging 767 / 1338, plant step
1189 / 1243, the rest (edge take, statistics, safety) about 350 mean; a capture sample adds about 200. One phase
carries flux in this test; each further conducting phase adds about 250 cycles to the plant step.

Changes made after the first measurement (plant 7400 and gate averaging 2600 cycles max, the loop fell behind and
starved USB): int instead of int64 table indices, the per-window divisions of the averager done once, idle windings
skipped in the averager, and in the float-table build only (firmware and its PC model `srm_emu.c`) the table lookup in
single precision with one angle wrap per evaluation and zero-flux phases skipped; -O3. The double (SIL) build is
unchanged in its results (`tests/hil/test_hil_plant_split.py` golden at 1e-12). The step loop stops itself and
reports `HIL_ERROR` when a step finishes 20 steps late, so an overload cannot wedge the USB link.

Owner decision needed for the timing: a 816 MHz core clock (about 1.36 x), a single-precision plant step, or a
longer step. At 600 MHz the core does not leave room for two conducting phases, the Task 9 output stage or
streaming.

Pending wiring: edge jitter on the GPIO path against a Nucleo pattern (< 150 ns target) and the Nucleo test-pattern
mode; the RUN/READY interlock with the controller. The self-test pattern bypasses the gate inputs, so its jitter
reads 0.

## Acceptance

Pending.
