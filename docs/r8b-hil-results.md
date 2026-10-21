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

Timing over 11 s (2.19 M steps) per case, after the result-neutral speedups (no capture running):

| Self-test phases | Step mean | Step max | Overruns | Target |
|---|---|---|---|---|
| one (A) | 3.41 us (68 %) | 4.90 us | 0 | max < 4 us, 0 overruns: max **not met** |
| two overlapping (A, B) | 4.17 us (83 %) | 6.16 us | 438 000 (2 per 10 steps, the edge windows) | **not met** |

Cycles per step (mean / max of the 3000 per step), one phase: gate averaging 534 / 1281, plant 1156 / 1211, the rest
about 350; two phases: gate averaging 645 / 1620, plant 1501 / 1630. Benchmarks on the board: an idle plant step (no
flux) costs 640 cycles, each conducting phase about 400 more (two table lookups of 128 each plus the wrap), a gate
window with one edge about 1225, a capture sample about 200. The maxima are the windows with a gate edge.

Captures with one phase (`examples/hil_emu_selftest.py`):

| Item | Result | Target |
|---|---|---|
| Buffered capture, 8000 steps | all samples, contiguous, no sequence gap; `valid = 0` (overruns while recording: max 5.5 us) | valid |
| Streamed capture, 100 000 steps | ring full after 9592 samples (`dropped` 1, `valid = 0`) | valid |
| Phase-A current vs `srmsil.emumodel.run_model` on the same edges, RMS at the step instants | +0.002 % (buffered and streamed); max sample difference 0.64 mA = half a count | within 1 % - met |
| Live statistics | 20 Hz, one packet per 10 000 steps | - |
| Output latency (last edge to the end of the output stage, stubbed) | 8.6 us | - |

Speedups applied, in order (first measurement: plant 7400 and gate averaging 2600 cycles max; the loop fell behind
and starved USB):
- result-neutral in both builds: int instead of int64 table indices and step counts, the averager's per-window
  divisions done once, its loops over changed or pending switches only, idle windings skipped, a fused one-segment
  path for windows with no edge and no pending change (`test_fast_path_identical_to_general_walk` checks it bit for
  bit against the general walk), the converter voltage inlined, -O3;
- in the float-table build only (the firmware and its PC model `srm_emu.c`, which stay identical): single-precision
  table lookup, one angle wrap per evaluation, zero-flux phases skip the lookup, the averaged voltage multiplied by
  1/dt.

The double (SIL) build is unchanged in its results (`tests/hil/test_hil_plant_split.py` golden at 1e-12). The step loop
stops itself and reports `HIL_ERROR` when a step finishes 20 steps late, so an overload cannot wedge the USB link.

Further result-neutral gains are small: the remaining time is double-precision Heun arithmetic and the per-switch walk
of edge windows, at about 2.5 cycles per instruction. Owner decision needed: a 816 MHz core clock (about 1.36 x:
two phases about 4.5 us max), a single-precision plant step, or a longer step.

Single-precision plant (owner decision, 2026-10-21): with `SRM_TABLE_FLOAT` the plant state and arithmetic and the
gate averager use `srm_real_t` = float (the rotor angle and the time stay double); the SIL builds stay double and
bit-identical (golden at 1e-12). The float build compiles clean with `-Wdouble-promotion` (host test, and the
firmware's own files on the board build). PC model against the SIL, before / after: open loop 0.030 % / 0.030 %
torque, 0.004 % / 0.004 % i_rms; soft chop 0.032 % / 0.029 % torque, 0.005 % / 0.003 % i_rms; hard chop at the step
instants -0.001 % / -0.001 %.

Timing with the single-precision plant, 11 s (2.19 M steps) per case:

| Case | Step mean | Step max | Overruns | Capture |
|---|---|---|---|---|
| one phase (A) | 2.88 us (58 %) | 4.21 us | 0 | - |
| two overlapping phases (A, B) | 3.49 us (70 %) | 5.14 us | 219 006 (1 per 10 steps) | - |
| one phase, buffered capture of 8000 steps | 2.88 us | 4.70 us | 0 | `valid = 1`, contiguous, phase A +0.002 % vs the PC model |
| one phase, streamed capture of 100 000 steps | 2.88 us | 4.70 us | 0 | ring full after 10 936 samples, `valid = 0` |

Target (max < 4 us, 0 overruns) still missed: one phase by 0.2 us (0.7 us while a capture records), two phases with
overruns on the steps with a gate edge. A streamed capture at 200 kHz (7.2 MB/s) does not keep up with the CPU time
left to the USB loop.

Pending wiring: edge jitter on the GPIO path against a Nucleo pattern (< 150 ns target) and the Nucleo test-pattern
mode; the RUN/READY interlock with the controller. The self-test pattern bypasses the gate inputs, so its jitter
reads 0.

## Acceptance

Pending.
