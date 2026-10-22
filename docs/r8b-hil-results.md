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

### Controller driver, fix round 1 and first wired runs (2026-10-22, boards wired per docs/r8b-hil-wiring.md)

Both boards were flashed with the same modes (ad7606, encoder; hash 0xbb2cda56, the first Teensy upload needed the
usual retry) before any run; BUILD_INFO on COM4 and COM6 agree.

Fix round 1:
- Hang stop: three triggers in a row that find `ctrl_isr` still running stop the run (gates off, RUN low, HIL_ERROR
  "stopped: ctrl_isr did not return for 3 triggers (abandoned)", live state bit HANG_STOP = 32). The trigger
  interrupt then makes the interrupted data interrupt return through a longjmp to `drv_data_done`, so the link and
  later starts keep working. Wired bench with `tests/sil/controllers/hang` (emulator running, fixed 1000 rpm): the run
  stopped with 3 overruns, live state 34 (READY + HANG_STOP), the link answered HELLO afterwards, and a second START
  hung and stopped the same way.
- Rates: the HIL accepts only `isr_hz = pwm_hz / k` with k odd (the SIL samples at (j + 1/2) / isr_hz, a carrier
  centre only then): `write_hil_config` raises before a build, the firmware refuses the start.
- LIVE_CTRL gained `tx_dropped` (41 bytes). The RDC angle uses `HIL_RDC_BITS`; the start enables the outputs with
  interrupts off after re-reading READY.
- All 30 builds (6 modes x hysteresis, pwm_current, tsf, open_loop, hang) compile without warnings; tests/hil 68 passed.

Wired, `open_loop` (theta 0.1-0.45 rad), analytic motor, fixed 1000 rpm, ad7606 + encoder, 20 kHz:
- AD7606 chain works on the wire: `ctrl_isr` runs on every trigger, 0 overruns, ISR mean 2.18 us, max 2.59 us;
  trigger to `ctrl_isr` 16.9 us (CONVST, the 4.15 us conversion and 128 bits at 12.5 MHz = 10.2 us, plus the
  emulator's latency). Emulator step mean 2.05 us, max 3.54 us, 0 overruns.
- **Encoder: no A/B signal at the Nucleo.** TIM4 CNT stayed 0. PD12 (A) and PD13 (B) read 0 in 300 of 300 samples of
  GPIOD IDR (OpenOCD) while the emulator ran at 1000 rpm (4096 CPR, about 68 000 edges/s; random samples would read
  high about half the time). TIM4 configuration read back as intended (SMCR 3, CCMR1 0x101, PD12/PD13 in AF2). The
  index bit was set once after the start (Z on PG14), so Z may be connected. With the count stuck at 0, open_loop keeps
  phase D on and A-C off: the emulator showed phase D at 94.6 A rms (beyond the map) and the Nucleo read 30.8 A rms on
  V4, the AD7606 clipping at 31.25 A. Stopped here as instructed: check the A/B wires (Teensy 2 -> PD12 = Zio D29 /
  CN10-21, Teensy 3 -> PD13 = Zio D28 / CN10-19) and that the emulator drives pins 2/3 before the remaining wired
  items (READY timing, encoder direction and index, AD7606/AD2S1210 code comparison and SPI clock, the spin test, the
  HSE measurement) are run.

### Wired bench, continued (2026-10-22)

Both boards run the committed code (HEAD 9e269fb) in ad7606 + encoder with `tests/sil/controllers/open_loop`,
analytic motor, fixed 1000 rpm, 4096 CPR, 20 kHz. The timing and SPI measurements used scratch instrumentation that
is not in the tree (described with each item); the boards were flashed back to the committed code afterwards.

**Encoder: the cause was a wiring fault.** The owner found the encoder A/B wire faulty and replaced it. No firmware
was changed. With the new wire (OpenOCD, 300 samples while running):
- PD12 (A) was high in 149 samples and PD13 (B) in 138. TIM4 CNT took 291 distinct values, rising by about 115 per
  sample and wrapping at 4096 with no jump, and the index was seen (live state 19 = READY + RUNNING + INDEX).
- Count against the emulator's true theta: the gate edges in three 8000-step captures, as
  p = (theta - k pitch/4) mod pitch, 12 on and 12 off edges per phase:

  | Phase | On at p (rad) | Delay after 0.1 rad | Off at p (rad) | Delay after 0.45 rad |
  |---|---|---|---|---|
  | A | 0.1052-0.1109 | 50-104 us | 0.4560-0.4607 | 58-102 us |
  | B | 0.1057-0.1099 | 55-95 us | 0.4560-0.4602 | 57-98 us |
  | C | 0.1063-0.1104 | 60-100 us | 0.4560-0.4608 | 58-103 us |
  | D | 0.1052-0.1099 | 50-95 us | 0.4555-0.4602 | 52-97 us |

  The expected delay is 42-102 us. That is the encoder lag (10-15 us), plus the wait for the ctrl_isr count read
  (0-49.3 us), plus the time from the read to the next PWM update (about 32 us), plus the 5 us capture step. So the
  count matches theta to within about one count (1.53 mrad, which is 14.6 us at 1000 rpm). The count is 0 at theta = 0
  after the index, and the direction is counter-clockwise (the count rises; the motoring window gives positive torque,
  below). Upper and lower gates were equal in every sample.

**(a) READY to gates off: 0.232-0.252 us (mean 0.245 us) over 40 stops.** This is far inside one PWM period (49 us).
It was timed on the Teensy (CYCCNT, 1008 MHz) from the write that lowers READY to the gate interrupt that first sees
all eight gates low, so it includes the Teensy's gate interrupt latency. A gate was on at the READY edge in all 40
stops. Scratch patch: `emu_stop` stamps the READY write, `gate_isr` stamps the all-low word, and HELLO reports both.
No logic analyser is attached to this PC.

**(c) AD7606 on the wire: bit-exact; highest reliable SCK 25 MHz (HIL_SPI_MBR 2).**
- Scratch pattern test: on each CONVST the emulator sends V1 = a 16-bit counter and V2-V8 = a hash of
  (counter, channel). The Nucleo checks every frame in the DMA-complete interrupt (all 7 hashes, and counter =
  previous + 1), and the counts are read through OpenOCD.
- The SPI kernel clock runs 1.07 % fast (item e), so the real clocks are 1.07 % above the nominal values below.

  | HIL_SPI_MBR | SCK (nominal) | Frames checked | Bad frames | Counter breaks | Trigger to ctrl_isr |
  |---|---|---|---|---|---|
  | 3 (default) | 12.5 MHz | 102 792 | 0 | 0 | 17.5 us |
  | 2 | 25 MHz | 102 034 + 1 214 568 | 0 | 0 | 12.2 us |
  | 1 | 50 MHz | 102 850 | 15 | 15 | 9.6 us |

- The default stays at MBR 3 (12.5 MHz). 25 MHz passes, but it has only a factor of 2 to the failing step, and it is
  at or above the serial clock rating of a real AD7606 (check the datasheet before raising it).
- Real data agree with the emulator, as far as the AD7606 full scale (31.25 A) allows. The Nucleo's rms current
  (`i_meas`) is compared with the emulator capture clipped at 31.25 A:
  - 0.1-0.45 rad: 16.47-16.82 A on the Nucleo, 16.74 A from the capture;
  - 0.6-0.95 rad: 14.96-15.12 A on the Nucleo, 15.00-15.08 A from the capture.

**(c) AD2S1210, first attempt: an open SCK wire (Nucleo PC10 = Zio D45 / CN8-6 -> Teensy 27).**
- The start was refused: "AD2S1210 control register reads 255, wrote 0x75". This happens with and without the scratch
  patches.
- Evidence:
  1. Transfers driven by hand from the halted Nucleo through OpenOCD read 0xFF in every frame: normal-mode position
     (expected 0x0000) and configuration mode.
  2. With FSYNC held high, the same transfer follows the Nucleo's own pull (pull-down 0x00, pull-up 0xFF), so the
     Nucleo receive path works. MISO goes high when FSYNC goes low.
  3. The Teensy's LPSPI3 then shows SR = FCF only, and its TX FIFO count stays at 8. The slave sees the chip select,
     but no clock edge.
  4. Each Nucleo RDC output was driven as a GPIO 0/1/0/1, with each Teensy pin read as a GPIO (scratch HELLO dump):

     | Nucleo pin | Teensy pin | Result |
     |---|---|---|
     | PC12 MOSI | 1 | follows |
     | PD2 FSYNC | 0 | follows |
     | PG2 SAMPLE | 9 | follows |
     | PG3 A0 | 22 | follows |
     | PD7 A1 | 23 | follows |
     | PC10 SCK | 27 | stays 1 (pad keeper) |

     The Nucleo's IDR confirmed that PC10 was driven.
- The Teensy's LPSPI3 mux and input select (pins 0/1/26/27; select inputs 0/0/1/1) match the Teensy SPI library's
  LPSPI3 table.
- The owner fixed the wire. No firmware was changed.

**(c) AD2S1210 with the fixed wire: configuration readback, position, velocity and SPI3 clock all correct.**
- The start is accepted in ad7606 + ad2s1210 and in ad7606 + both, so control register 0x92 reads back 0x75 (12 bits).
- Position against the emulator's theta, in `both` mode at 1000 rpm, with a scratch controller (not in the tree). It is
  open_loop driven by the angle from `resolver_sincos` (atan2), window 0.6-0.95 rad, and it also logs, on every
  sample, the resolver angle minus the encoder angle in counts of 4096.
  - Default sensors (no resolver errors):
    - The gate edges arrive 50-105 us (on) and 48-98 us (off) after the window marks, the same as the
      encoder-driven run.
    - Over 163 598 samples, RDC minus encoder is -1.01 to +1.01 counts (mean -0.21, std 0.41). That is the 12-bit
      rounding plus the encoder's floor and its 10-15 us lag.
    - Torque +2.83 N m (encoder-driven: +2.80).
  - Gain mismatch 1 %, phase error 0.01 rad:
    - Over 162 579 samples, RDC minus encoder is -2.01 to +8.01 counts (mean +3.06).
    - The expected value is the error of atan2(sin x, 1.01 cos(x + 0.01)), -1.32 to +7.87 counts (mean +3.28), plus
      the zero-error spread above, which gives about -2.3 to +8.9 (mean +3.07).
- Velocity, read by hand through OpenOCD after a run. The Nucleo was stopped and the emulator held its last step, with
  A0/A1 = 0/1 and a SAMPLE pulse.

  | Speed | Velocity frame | Expected (12 bits, 1000 rps full scale) |
  |---|---|---|
  | +1000 rpm | 0x02 0x20 0x00 | 0x0220 = 34 << 4, fault 0 |
  | -1000 rpm | 0xFD 0xE0 0x00 | 0xFDE0 = -34 << 4 |
  | +3000 rpm | 0x06 0x60 0x00 | 0x0660 = 102 << 4 |

  A second read returns the same frame. Position frames are MSB-aligned at 12 bits (low nibble 0).
- SPI3 clock: the scratch counter-and-hash pattern as for the AD7606. The position word steps by 40503 on each
  SAMPLE, and the fault byte is a hash of the word; every frame is checked on the Nucleo.

  | HIL_SPI_MBR | SCK (nominal) | Mode | SPI3 frames: ok / bad | AD7606 frames: ok / bad |
  |---|---|---|---|---|
  | 3 (default) | 12.5 MHz | ad7606 + ad2s1210 | 101 605 / 0 | 101 605 / 0 |
  | 3 (default) | 12.5 MHz | ad7606 + both | 204 330 / 0 | 204 330 / 0 |
  | 2 | 25 MHz | ad7606 + ad2s1210 | 102 954 / 0 | 102 954 / 0 |
  | 2 | 25 MHz | ad7606 + both | 202 631 / 0 | 202 631 / 0 |
  | 1 | 50 MHz | ad7606 + ad2s1210 | 101 316 / 0 | 94 355 / 6 961 |
  | 0 | 100 MHz | ad7606 + ad2s1210 | start refused: the control register reads 58 | - |

- The highest reliable clock is 50 MHz for SPI3 and 25 MHz for SPI1 (AD7606). `HIL_SPI_MBR` sets both, so the default
  stays at MBR 3 (12.5 MHz): a factor of 2 below the AD7606 limit and a factor of 4 below the SPI3 limit.
- In ad7606 + ad2s1210, `tests/sil/controllers/open_loop` leaves every gate off. It needs an encoder:
  `encoder_cpr` is 0 there, so its angle is 0/0 = NaN. That is expected, not a driver fault.
- Both boards are flashed back to the committed ad7606 + encoder + open_loop (the same build on both).

**(d) Spin test, open_loop, ad7606 + encoder, 1000 rpm fixed: 0 overruns.**

| Window (rad) | Mean torque | Emulator i_rms (true) | Nucleo i_meas (clipped at 31.25 A) | ISR mean / max | Trigger to ctrl_isr | Emulator step mean / max |
|---|---|---|---|---|---|---|
| 0.1-0.45 | -7.78 N m | 30.4 A | 16.5-16.8 A | 2.92 / 3.27 us | 16.9 us | 2.38 / 4.25 us |
| 0.6-0.95 | +2.80 N m | 21.1-21.4 A | 15.0-15.1 A | 2.72 / 3.24 us | 16.9 us | 2.47 / 4.50 us |

- 0 overruns on both boards and no errors (10 s runs plus a capture).
- The 0.1-0.45 rad window lies after alignment (L(theta) of the analytic motor peaks at p = 0), so at a fixed speed it
  generates; 0.6-0.95 rad motors.
- Open loop at 48 V has no current limit, so the peaks exceed the map (20 A; the capture clips at 2 i_max = 40 A),
  and the AD7606 clips at 31.25 A. So the rms on the Nucleo is lower than the true rms in both runs; with clipping taken
  into account, the two agree (item c).
- One motoring capture had a host-side packet gap (7972 of 8000 samples).
- The emulator step max (4.25-4.50 us) is above the 4 us budget, as in the Task 9 encoder modes, but there are no
  overruns.

**(e) Nucleo clock against the Teensy crystal: +10 650 ppm.** This is recorded only; HSE_VALUE is unchanged and the
owner decision is pending.
- TIM2 (`micros`) was read through OpenOCD every 2 s for 80 s with host timestamps: 1.0106336 per host second. The
  Teensy step counter gave 0.9999841 per host second over the same run.
- The LIVE_CTRL arrivals (every 50 SysTicks) over 90 s give +10 869 ppm (host jitter 22 ms rms).
- On 2026-10-21 the error was +14 000 ppm. So the ST-LINK's 8 MHz output drifts by thousands of ppm, which fits an
  RC-derived source rather than a crystal. A fixed HSE_VALUE would not hold; an HSE crystal (X3) would.

### Trigger-rate clock measurement (2026-10-22, Teensy 4.1 at 1008 MHz, boards wired)

The owner kept HSE_VALUE; every HIL run measures the Nucleo clock instead. LIVE_EMU `trigger_hz` is the controller's
sample-trigger rate per 50 ms window by the Teensy's cycle counter, (n - 1) / (t_last - t_first): CONVST in AD7606
builds, else SAMPLE in AD2S1210 builds, NaN below 2 triggers. Both boards ran the same modes, `open_loop`
(0.6-0.95 rad), analytic motor, fixed 1000 rpm, nominal isr_hz = pwm_hz = 20 kHz. Cross-checks over the same run:
the LIVE_CTRL arrival rate and TIM2 (`micros`) read through OpenOCD every 2 s, each against the Teensy step counter.

| Modes (both boards) | Run | Source | trigger_hz mean (window std) | Ratio to 20 kHz | LIVE_CTRL | TIM2 |
|---|---|---|---|---|---|---|
| ad7606 + encoder | 90 s | CONVST | 20 222.31 Hz (7.3 Hz) | 1.011115 | 1.011125 | 1.011135 |
| ad7606 + ad2s1210 | 45 s | CONVST | 20 224.43 Hz (6.7 Hz) | 1.011221 | 1.011130 | 1.011199 |
| ad7606 + ad2s1210, scratch build counting SAMPLE | 45 s | SAMPLE | 20 223.07 Hz (6.3 Hz) | 1.011154 | 1.011047 | 1.011148 |
| ad7606 + encoder (committed, last) | 40 s | CONVST | 20 222.14 Hz (8.6 Hz) | 1.011107 | 1.011105 | 1.011019 |

- The run means agree with both cross-checks to within 0.01 % (+11 107 to +11 221 ppm; earlier +10 650 and
  +14 000 ppm).
- The window-to-window spread (6-9 Hz, about 400 ppm) is the Nucleo clock wandering, not measurement noise: consecutive
  windows correlate at 0.79 and 1 s means still spread by 4.5 Hz. A single window is good to about 0.04 %; a matched
  SIL should use the run mean.
- With the controller stopped, every window reports NaN. 0 overruns on both boards in every run.
- The internal + ad2s1210 build (which counts SAMPLE without a scratch change) was not run. Internal sensing needs the
  DAC wiring and the Teensy driving the shared SCK wire, and no wired run has used it yet. The scratch build only moved
  the stamp from CONVST to SAMPLE. Both boards were flashed back to the committed
  ad7606 + encoder build.

### Host session, run_hil and the matched SIL (2026-10-22, Teensy 4.1 at 1008 MHz, boards wired)

`srmsil.hil.session` (`HilSession`, `run_hil`) over `srmsil.hil.transport.SerialTransport` (a reader thread appends raw
bytes to a buffer; `recv` splits on 0x00 and unframes; a 4 MB driver receive buffer is asked for on Windows) and
`discover()` (COM4 Teensy, COM6 ST-LINK). Both boards flashed with the same build (ad7606 + encoder,
`tests/sil/controllers/open_loop`, analytic motor, scenario bus 24 V; hash 0xaca15dd5 on both; the first Teensy upload
needed the usual retry). `run_hil`: fixed 1000 rpm, window 0.6-0.95 rad, 20 kHz, duration 0.02 s (a 4000-step buffered
capture after 0.2 s settling), summary over the capture's second half. The matched SIL is
`matched_scenario(scenario, latency_us, modes, clock_ratio)`: `sensors.delay` = latency + 4.15 us + 128 / 12.5 MHz,
`controller_clock` = the measured ratio.

| Bus | valid | clock_ratio (spread) | Emulator step mean / max, overruns | ISR mean / max, overruns | Latency | d_torque | d_irms | d_ripple | Passed |
|---|---|---|---|---|---|---|---|---|---|
| 24 V, run 1 | yes | 1.010967 (259 ppm) | 2.49 / 4.40 us, 0 | 2.74 / 3.10 us, 0 | 6.41 us | -0.31 % | -0.73 % | +0.42 pts | yes |
| 24 V, run 2 | yes | 1.010882 (175 ppm) | 2.49 / 4.36 us, 0 | 2.74 / 3.21 us, 0 | 6.47 us | +0.13 % | -0.22 % | -0.50 pts | yes |
| 48 V (the spin-test setting, same build) | yes | 1.010999 (151 ppm) | 2.49 / 4.37 us, 0 | 2.74 / 3.10 us, 0 | 6.56 us | +0.48 % | **-18.4 %** | +0.63 pts | **no** |

- 24 V: HIL 0.604-0.606 N m, ripple 36.6-37.5 %, 4.9-5.0 A rms; matched SIL 0.606 N m, 37.1 %, 4.9-5.0 A rms. Against
  a SIL at the nominal clock (controller_clock 1.0) the differences grow to +1.27 / +1.59 % torque and +2.85 / +1.93
  points ripple, so the measured clock ratio matters even for this angle-driven controller.
- 48 V fails on the RMS current: open loop at 48 V has no current limit, the peaks reach about 69 A (SIL), beyond the
  map (20 A) and beyond the capture's int16 range (2 x the table i_max = 40 A), so the captured currents clip. The
  capture now reports the share of clipped samples (`Capture.clipped`, `hil["capture_clipped"]`: 0.43 at 48 V, 0 at
  24 V on a repeat run, which again gave -18.4 % and -0.26 %); it does not change
  `valid`. Torque (+0.48 %) and ripple agree. Recorded, tolerances unchanged.
- `edge_jitter_ns` is the spread of the phase-A rise-to-rise period, which for open_loop is the stroke timing (14-20 us
  here), not gate-input jitter against a fixed carrier.

Capture sequence gaps (carried from the emulator-core and spin-test runs: one buffered capture in three to five had a
1- or 5-packet gap with CRC-bad frames on the host while the emulator reported valid). Buffered captures of 8000
steps on the run above:

| Host reader | Condition | Captures | Gaps | Bad frames |
|---|---|---|---|---|
| raw reader thread (`SerialTransport`) | idle host | 20 + 60 | 0 | 0 |
| decode-as-read in the caller's thread (as `examples/hil_emu_selftest.py`) | idle host | 20 + 60 | 0 | 0 |
| raw reader thread | 16 CPU-bound processes on the host | 30 | 0 | 0 |
| decode-as-read | 16 CPU-bound processes on the host | 30 | 0 | 0 |
| raw reader thread, the reader stalled 0.5 s / 2 s after the first capture bytes (4 MB and 4 KB driver buffer) | | 15 | 0 | 0 |

The loss did not reproduce in 235 captures with either reader, so neither side was changed. A Teensy-side mechanism
that matches the old symptom exists: `usb_serial_write` (teensy4 core) returns fewer bytes than asked once the host
has not taken data for 120 ms (TX_TIMEOUT_MSEC), and `link.cpp` does not check the count, so a frame is cut (CRC-bad
on the host, together with the frame it merges into), the packet is missing and the emulator's capture end still says
valid. On this PC the Windows USB serial driver kept accepting data through a 2 s host stall, so that path was not
reached. The host marks any gap or bad frame during a capture invalid, so a recurrence cannot pass unnoticed.

#### Revised matched SIL and emulator short-write count (2026-10-22, same rig)

The runs above used the first matched SIL (sensors.delay = latency + AD7606 conversion and SPI time, the SIL's own
12-bit ADC, the SIL run from t = 0 over the capture's duration). The matched SIL is now (`compare.matched_scenario`):
- compute_delay = 1 / (isr_hz x r): the sample is latched at the trigger, conversion and SPI only delay ctrl_isr, and
  the preloaded compares load at the next underflow, one controller ISR period later;
- sensors.delay = the emulator's measured `latency_us`: it runs from the last gate edge of a step's window to the end
  of that step's output stage, so for gate edges asynchronous to the emulator steps it already averages the age of a
  value latched at a random trigger (output delay D plus dt/2);
- the ADC of the HIL chain (`config.hil_adc`: for the AD7606, 16 bits, offset 32768, the amps and volts per count of
  `hil_config.h`, clipping at the range);
- the SIL runs from the controller's start to the end of the capture, and both sides are compared over the same
  window, the second half of the captured steps (`hil["window_s"]`, s since the controller's start; the emulator's
  step count runs only while RUN is high).

The emulator (`hil/emulator/link.cpp`) now checks every USB write; a short write counts in LIVE_EMU `dropped` (so the
run is invalid) and marks a capture being sent invalid. Both firmwares rebuilt and flashed with the same modes
(ad7606 + encoder, open_loop, 24 V; hash 0x5acbb3e0), then the 24 V run_hil + compare of the table above:

| Runs | valid | clock_ratio | d_torque | d_irms | d_ripple | Passed |
|---|---|---|---|---|---|---|
| first confirmation run | yes | 1.010912 (348 ppm) | +1.23 % | +0.65 % | +1.27 pts | yes |
| 25 further runs (one process each; 13 compared) | 23 | 1.01098-1.01230 | -1.69 to +1.44 % | -1.01 to +1.00 % | -3.11 to +1.27 pts | all 13 |

- Health in every run: emulator step mean 2.49 us, max 4.19-4.40 us, 0 overruns, `dropped` 0; ISR 2.74-2.75 / 3.1 us,
  0 overruns; latency 6.35-6.45 us; no clipped samples. The ratio rose to 1.0123 in one run (ST-LINK clock drift).
- Two of those runs were invalid with a 1-packet capture gap and 1 bad frame ("sequence gap: CAPTURE_DATA 129
  missing"), while the emulator's `dropped` stayed 0: so the loss is not a short write that the Teensy core reports.
  20 run_hil runs in one session and 20 in separate processes (bad-frame lengths recorded) showed no gap. The loss
  is rare (2 in about 280 captures with this firmware and host) and its side is still open; the host marks it invalid.
- Against a SIL at the nominal clock, the first run gave +1.18 % torque and +2.59 points ripple, and the run at
  r = 1.0123 +0.39 % and +2.02 points against -1.69 % and -1.05 points matched: in the revised model the measured
  clock changes this angle-driven controller's result mostly in the ripple, and the run-to-run spread (about +-1.5 %
  torque) is larger than the clock's effect on the mean.

## Acceptance

Pending.
