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

Core clock (owner decision, 2026-10-21): 1008 MHz, chosen from the table below. `board_build.f_cpu` in
`hil/platformio.ini` sets it at boot; the iMXRT1062 needs a heatsink at this clock. Every cycle constant is derived
from `F_CPU_ACTUAL`. The die temperature
(`tempmonGetTemp`) is reported in the live statistics (`temp_c`), and a run stops (READY low, `HIL_ERROR`) above
85 C. Single-precision plant, self-test pattern, 11 s per timing case:

| Case | 816 MHz | 1008 MHz |
|---|---|---|
| one phase: step mean / max, overruns | 2.12 / 3.10 us, 0 | 1.72 / 2.51 us, 0 |
| two overlapping phases: mean / max, overruns | 2.57 / 3.78 us, 0 | 2.08 / 3.06 us, 0 |
| one phase, buffered capture (8000 steps) | valid, contiguous, -0.001 % vs the PC model | valid, contiguous, -0.007 % vs the PC model |
| one phase, streamed capture | ring full after 35 380 samples (`valid = 0`); sustained output 154 k samples/s = 5.5 MB/s, 77 % of the 7.2 MB/s needed | 400 000 samples (2 s), `valid = 1` with a raw-reading host |
| two-phase soak, 2 min (24 M steps): max, overruns, die temperature start / end | 3.78 us, 0, 56.1 / 56.8 C | 3.06 us, 0, 66.7 / 66.7 C |

Streaming notes: the streamed rows use a host that reads raw bytes into a 16 MB buffer and parses afterwards. The
example script, which decodes every frame as it arrives, ends its streamed captures early (`valid = 0`) at either
clock. At 1008 MHz one buffered capture in five had a sequence gap of five packets (140 samples) on the host. The
emulator's capture end said valid, and no frame failed its CRC. One run at 816 MHz hit a CRC error on the first frame
read after a flash. The other runs were clean. No resets, USB drops or wedges at either clock.

Pending wiring: edge jitter on the GPIO path against a Nucleo pattern (< 150 ns target) and the Nucleo test-pattern
mode; the RUN/READY interlock with the controller. The self-test pattern bypasses the gate inputs, so its jitter
reads 0.

### Emulator outputs (2026-10-21, Teensy 4.1 at 1008 MHz, boards not wired to each other)

Output stage per mode (`hil/emulator/outputs.cpp`): emulated AD7606 on LPSPI4 as a slave (`ad7606_slave.cpp`),
MCP4922 x 2 / MCP4921 x 4 written by LPSPI4 as a master (`dac.cpp`), emulated AD2S1210 on LPSPI3 as a slave
(`ad2s1210_slave.cpp`) and the quadrature encoder scheduled on GPT2 (`encoder.cpp`, edge times from the host-tested
`enc_sched.c`). All eight builds compile (ad7606 and internal x encoder, ad2s1210, both; internal also with
mcp4921x4), clean with `-Wall -Wextra -Wdouble-promotion` in the emulator's own files.

Step time with the outputs on (`examples/hil_emu_selftest.py` configuration: analytic motor, fixed 1000 rpm, 180 x 192
tables, self-test pattern 20 kHz 50 %, encoder 4096 CPR, RDC 12 bits; 10.5 s = 2.09 M steps per case). "Errors" adds
the worst sensor model costs: encoder eccentricity 2 mrad at harmonic 2, resolver gain mismatch 1 % and phase error
0.01 rad. Max / overruns; target max < 4 us (80 % of dt), 0 overruns:

| Mode | 1 phase | 2 phases | 1 phase, errors | 2 phases, errors |
|---|---|---|---|---|
| ad7606, encoder | 3.41 us / 0 | 3.97 us / 0 | 3.48 us / 0 | **4.04 us** / 0 |
| ad7606, ad2s1210 | 2.87 us / 0 | 3.42 us / 0 | 2.98 us / 0 | 3.54 us / 0 |
| ad7606, both | 3.54 us / 0 | **4.10 us** / 0 | 3.64 us / 0 | **4.22 us** / 0 |
| internal, encoder | 3.55 us / 0 | **4.15 us** / 0 | 3.62 us / 0 | **4.22 us** / 0 |
| internal, ad2s1210 | 3.01 us / 0 | 3.71 us / 0 | 3.12 us / 0 | 3.82 us / 0 |
| internal, both | 3.81 us / 0 | **4.31 us** / 0 | 3.92 us / 0 | **4.42 us** / 0 |

These are the figures after fix round 1, which started the GPT timers: before it the GPT1/GPT2 configuration
(oscillator source with EN_24M) left both counters at 0, so no encoder edge was put out and the first figures (up to
4.39 us) did not include the encoder interrupt. GPT1/GPT2 now count the peripheral clock (CLKSRC 1), 24 MHz from the
oscillator: 1 200 000 ticks per 50 ms window measured, and 3413 encoder edges per window put out (4096 CPR at
1000 rpm: 3413.3). The encoder compare interrupt costs up to about 340 cycles (peripheral register accesses).
No overrun in any case; the 2-phase maxima of the modes with the encoder exceed the 80 % warning level by up to
0.42 us. Means: 2.08-2.58 us (1 phase), 2.44-3.06 us (2 phases); without outputs the
2-phase maximum was 3.06 us. Output latency (last gate edge to the end of the output stage, self-test edges) 7.1-8.2
us. In the bench the DAC frames run with their pads released (RUN is not wired, so it is low; see the interlock
below), so a wired run adds the LDAC pulse (about 0.15 us per step). Die temperature 62-67 C.

Cost reductions applied (all on the board, measured with the cycle counter): one measured-angle computation per step
shared by the encoder and the RDC, the eccentricity sine from a 1024-point table (error below 5e-6 of the amplitude),
the resolver gain/phase error as a 1024-point table of the tracked-angle error over an electrical turn (about 1e-7
turn at 5 % / 0.05 rad, 1/150 of a 16-bit count), the velocity word cached while omega is constant, no 64-bit
integer arithmetic or division on the encoder's no-edge path, and GPT2 register reads only for edges within 2 us of
the last compare.

Interlock (safety rule): the DAC build drives Teensy 13 (SCK) and 11 (SDO) only while the RUN input itself is high.
The pads are switched to LPSPI4 at the start of a DAC sequence in a critical section that reads RUN; the RUN falling
edge (combined GPIO interrupt, priority 0) switches them back to GPIO inputs and raises every DAC chip select. The
self-test does not count as RUN. While RUN is low the DACs keep the last code written while it was high (they cannot
be written then; spec 5.4 says so since 2026-10-21); a stop while RUN is still high writes the zero-current code. In
the AD7606 build LPSPI4 is a slave with CFGR1.OUTCFG = 1.

Encoder faults: an edge whose compare tick has already passed is put out at once (never programmed in the past); a
compare that has not matched a step after its tick is pended by the step loop; that, a full edge queue or a step with
more edges than the schedule holds (a forced count jump) counts as an overrun, so the run is invalid.

LPSPI register semantics: the IMXRT1060RM PDF (pjrc.com copy, rev 3) is larger than the 10 MB the fetch tool reads,
so CFGR1 was not read in the manual itself. Evidence used instead: the NXP MCUXpresso SDK LPSPI driver
(`fsl_lpspi.h`, same LPSPI IP): `kLpspiDataOutTristate = 1U` "Data out is tristated when chip select is de-asserted"
(CFGR1.OUTCFG) and `kLPSPI_SdiInSdoOut = 0U` "LPSPI SDI input, SDO output" (CFGR1.PINCFG, both master and slave
configurations); the Teensy core's `imxrt.h` places OUTCFG at CFGR1 bit 26. Still to read in IMXRT1060RM (LPSPI
chapter, CFGR1 register description) and to confirm on the wire.

Pending wiring (spec section 15, `docs/r8b-hil-wiring.md` section 5), not measurable with the boards unwired:
- LPSPI4 SDO (Teensy 11) tri-state with CS (Teensy 10) high, on the scope or logic analyser;
- the highest reliable slave SCK for LPSPI4 (AD7606) and LPSPI3 (AD2S1210): start 8 MHz, step to 15 MHz, 10 000
  transfers without a CRC-checked mismatch; the Nucleo SPI1/SPI3 prescalers are set to that clock in the controller
  driver (Task 10);
- the pin-13 LED load on SCK edges at that clock, and on the 20 MHz DAC SCK;
- the Teensy GND pads (beside pin 0, and between VIN and 3.3V) against the printed pinout card;
- the SPI modes the controller driver must use: AD7606 mode 2 (CPOL 1, CPHA 0: DB15 out at CS falling), AD2S1210
  mode 3 (CPOL 1, CPHA 1), DAC mode 0; the AD7606 frame is 128 bits (V1..V8, MSB first), the AD2S1210 normal-mode
  frame 24 bits (16-bit word, then the fault register 0), configuration frames 8 bits;
- the encoder A/B/Z edges and the DAC/LDAC sequence on the logic analyser, and the RUN-falling release of pins 13/11.

### Notes for the Nucleo driver (Task 10)

- SPI modes: AD7606 mode 2 (CPOL 1, CPHA 0; DB15 is out when CS falls), AD2S1210 mode 3 (CPOL 1, CPHA 1). AD7606:
  one 128-bit frame, V1..V8 as 16-bit two's complement, MSB first. AD2S1210 normal mode: a 24-bit frame (the 16-bit
  word MSB-aligned at the resolution, then the fault register 0); it can be read up to 8 times per SAMPLE or A0/A1
  change.
- CONVST is taken on its rising edge and SAMPLE on its falling edge, both latched by the GPIO edge detector in
  hardware, so the pulse need not last until the interrupt runs. Give each pulse at least 100 ns (the guaranteed
  minimum is not measured yet; real chips need about 25 ns for CONVST and 2 t_ck for SAMPLE), and space two CONVST
  or SAMPLE edges at least 1 us apart (edges within one interrupt latency count once).
- The AD7606 emulator loads the conversion into the SPI FIFO at the CONVST edge, so a read during BUSY already
  returns it; the driver must still read only after BUSY falls, as on the real chip.
- AD2S1210 configuration mode (A0 = A1 = 1): 8-bit frames, one per chip-select cycle, with a gap of at least 1 us
  between frames (the next byte is queued by an interrupt); an address byte (bit 7 set) makes the next frame return
  that register; position and velocity reads in configuration mode return 0. Only control register 0x92 RES1/RES0 is
  used (resolution 10, 12, 14, 16 bits).
- Encoder: one A or B edge per count (x4 encoder mode, ARR = cpr - 1); edges come out two steps (10 us) after the
  step that crossed them.

### Controller driver (2026-10-21, Nucleo-H723ZG alone, boards not wired to each other)

`hil/controller/` (README there). `pio run -e controller` compiles without warnings in all six modes (ad7606 and
internal x encoder, ad2s1210, both) with hysteresis, pwm_current, tsf and `tests/sil/controllers/open_loop`: flash
16-29 KB with open_loop, 66-79 KB with the reference controllers (their tables). Hard-float ABI and -O2: the board
package passed only `-mcpu` (software floating point) and its `-Os` overrode the `-O2` of `platformio.ini`; both are
fixed in `platformio.ini` and `scripts/add_sources.py`.

Register readback through OpenOCD while the firmware runs (20 kHz, ARR 5000):

| Item | Read | Expected |
|---|---|---|
| TIM1 CR1 / TIM8 CR1 | 0xA1 / 0xA1 | CEN, centre-aligned, ARR preload |
| TIM1 CR2 | 0x00200010 | MMS = enable (starts TIM8), MMS2 = update (ADC trigger) |
| TIM8 SMCR | 0x6 | trigger mode, ITR0 = tim1_trgo |
| CCMR1/2 (both) | 0x6868 | PWM mode 1, compare preload, CH1-CH4 |
| CCER (both) | 0x1111 | CH1-CH4 on, active high, no CHxN |
| BDTR stopped / running | 0x0C00 / 0x8C00 | OSSI, OSSR, dead time 0; MOE only while running |
| ARR / RCR | 5000 / 1 | 200 MHz / (2 x 20 kHz); one update per period |
| update at the underflow (`phase_ok`) | 1 on both timers | the counter counts up after each update |
| TIM1 - TIM8 count right after the start (`pwm_skew_ticks`) | 0 | (resolution: the register read time, several ticks) |
| SPI1 CFG1 / CFG2 (ad7606) | 0x3000400F / 0x86440000 | 12.5 MHz, RX DMA, 16 bits / master, mode 2, receive only |
| SPI3 CFG1 / CFG2 (ad2s1210) | 0x30000007 / 0x87440000 | 12.5 MHz, 8 bits / master, mode 3, receive only |
| GPIOD PD4 (READY) | input, pull-down, reads 0 unwired | a missing emulator reads "not ready" |
| RUN (PD6) | low until a start is accepted | |

Found by the readback and fixed: the repetition counter written after the counters started put the update events on
the overflows (the RM0468 note reads the other way), so it is now loaded before the start and checked at boot; SPI1
and SPI3 had lost MASTER (set while the internal SS was low, a mode fault); ADC2 calibration never finished when run
after the dual mode was set, so both ADCs are calibrated before it.

Link (COM6, 921600 baud): HELLO -> BUILD_INFO (board 2 and the build's modes); PARAM_SET `theta_on` -> 0, an unknown
name -> -1, `resolver_pole_pairs` after a start -> -2, a NaN value -> HIL_ERROR; COMMAND torque -> ack, mode 7 ->
HIL_ERROR; LIVE_CTRL 20 Hz (203 in 10 s); START with READY low -> "start refused: READY is low"; RUN stays low.

Runs with READY pulled up through the debugger (GPIOD PUPDR), `internal` + encoder (the ADCs convert the floating
inputs, so the whole chain runs without the emulator); 20 kHz, analytic 8/6 case, 10 s each:

| Controller | ISR mean | ISR max | Trigger to ctrl_isr | Overruns |
|---|---|---|---|---|
| open_loop (theta 0.1-0.45 rad) | 2.13 us | 2.59 us | 1.78 us | 0 |
| hysteresis (torque 1 N m) | 3.53 us | 4.70 us | 1.81 us | 0 |
| pwm_current (torque 2 N m) | 4.55 us | 4.74 us | 1.79 us | 0 |
| tsf (torque 2 N m) | 4.81 us | 5.26 us | 1.81 us | 0 |

While running, the compares follow the controller (hysteresis: phase B on, TIM1/TIM8 CCR2 = 5001 = ARR + 1, PE11 and
PC7 read high; pwm_current at full duty with soft chopping: upper and lower CCR = 5001). READY pulled low through the
debugger during a run: BDTR 0x0C00, every CCR 0, all eight gate pins low, RUN low, live state READY_STOP and
HIL_ERROR "stopped: READY low". `ad7606` + encoder without the emulator: the start is accepted with READY pulled up,
CONVST goes out, no BUSY comes, and the run stops after three triggers ("the sample chain stalled"), gates off.
`ad2s1210`: the start is refused, "AD2S1210 control register reads 0, wrote 0x75 (is it wired?)".

Board clock (owner decision needed): the 8 MHz bypass clock from the ST-LINK runs 1.40 % fast. TIM2 (`micros`)
counted 1.0140 us per host us over 10 s, and LIVE_CTRL arrives at 20.28 Hz; the host clock agrees with the Teensy's
crystal to 3e-5 (emulator steps per host second 200 005.5). So the Nucleo runs at about 405.6 MHz, the PWM at about
20.28 kHz and `micros` 1.4 % fast (the controller's speed estimate reads 1.4 % high). RCC was read back as configured
(HSE bypass, PLL1 M 1, N 100, P 2). Options: fit a crystal (X3) and use HSE crystal mode, or give the ST-LINK MCO its
measured frequency, or let the matched SIL use the measured rates.

Pending wiring: the `open_loop` spin test at 1000 rpm in `ad7606` + encoder (ISR time, 0 overruns), the READY-to-gates
time on the logic analyser (required within one PWM period; not measured yet), the AD7606 and AD2S1210
data on SPI (and the highest reliable SPI clock), the encoder count direction and the index reset.

## Acceptance

Pending.
