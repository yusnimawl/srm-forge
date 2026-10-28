# R8b control HIL results

Current configuration (end of Task 14): Teensy at 912 MHz, 6 us emulator step, matched SIL with the sensed-value age
jitter (`sensors.delay_jitter`), ripple compared as the median over complete strokes, buffered captures of up to 8192 samples (49 ms). The
Summary at the end is current. The sections before it are the record in the order the work was done; where one gives
a 600, 816 or 1008 MHz clock, a 5 us step or the "kept out of line" averager as the state of the firmware, a later
step supersedes it (Step 1d: the 1008 MHz failure; Step 1e: 912 MHz; Step 1f: 6 us).

Any edit under `hil/` (comments and READMEs included) changes the firmware hash, because the hash covers every file
there. Reflash both boards before the next session: `check_sources` refuses a session whose sources differ from the
flashed build.

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

Core clock (owner decision, 2026-10-21; superseded by Step 1e: the default is 912 MHz, 1008 MHz fails timing, see
Step 1d): 1008 MHz, chosen from the table below. `board_build.f_cpu` in
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

- The run means agree with both cross-checks to within about 0.011 % (+11 107 to +11 221 ppm; earlier +10 650 and
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

Steps 0 to 1d were measured at 1008 MHz and a 5 us step and are history: Step 1e (912 MHz) and Step 1f (6 us) set the
current configuration, and the re-run at the end of this section and the Summary give the current figures.

2026-10-23, Teensy 4.1 at 1008 MHz (COM4) and Nucleo-H723ZG (COM6), boards wired, both flashed with the same modes
before every run (the first Teensy upload after a flash of a different build failed about every second time; one
retry always worked). Case: the 8/6 reference machine (`srmapp.references`, with the requirements of the owner's 8/6
reference case: 10 kW, 32 N m, 3000 / 9000 rpm, 400 V) evaluated through srmweb at the `screening` preset. The
search's own winding for these requirements is 1 turn on 2 paths (0.5 equivalent turns: L_u 0.26 uH, I_max 6.5 kA,
0.02 mOhm), which no 20 kHz controller can chop (about 7.7 kA per 5 us at 400 V). So the HIL case is an edit of it
with a fixed winding of 60 turns on 1 path (the reference machine's own turns per pole): map I_max 54.3 A, R 0.307
Ohm, L_u 3.7 mH, L_a 34 mH, peak torque 28.6 N m (case `072f2112-8862-4ca1-81e0-327f4b240194`, "8/6 reference, 60
turns (HIL acceptance)"; the map is the cached screening map of the reference case). Operating point: fixed 1000 rpm,
torque command 10 N m, bus 400 V (the case's), 20 kHz PWM and ISR, default reference-controller parameters, 4096 CPR
encoder. Peak currents 19-34 A, inside the map (54.3 A), the AD7606 range (84.8 A) and the capture range (108.6 A);
no capture clipped. Tolerances unchanged (3 % torque, 3 % RMS current, 5 points ripple).

Runs: `examples/control_hil.py --case <setup file> --cache-dir <srmweb cache> --torque 10 [--modes ...]` (capture
4000 steps after 0.2 s, summary over its second half, matched SIL from 0.2 s before the capture).

### Step 0: capture speed range

The emulator's captured speed range was max(2 |initial speed|, 100 rad/s), so a speed step from rest saturated the
capture at 955 rpm. EMU_CONFIG now carries `omega_max` (`session.omega_max`): twice a dynamic run's speed command, or
for a torque command the initial speed plus the map's peak torque over the settle and capture time. The emulator takes
the largest of it, 2 |speed| and 100 rad/s. A captured speed at the range counts as clipped (`Capture.clipped`), so
the comparison refuses it. Test: `tests/hil/test_hil_session.py::test_capture_speed_range_covers_the_run` (fails with
`omega_max` 0). The clip count also showed that `test_window_matches_a_changing_run` had been passing on a speed
saturated at 100 rad/s in every sample. On the bench (Step 2) the 1500 rpm step is captured at 0.092 rpm per count
with no clipped sample. A dynamic torque command's range is capped at the position sensor's speed limit (the
encoder's 400 000 edges/s, else the resolver's tracking rate per pole pair), so a small inertia (J 1e-4 gave about
20 rpm per count) keeps a usable resolution (4096 counts: 613.6 rad/s full scale).

### Step 1: reference controllers at a fixed speed (ad7606 + encoder)

| Controller | Runs (valid) | Mean torque | RMS current | Ripple | d_torque | d_irms | d_ripple | Passed |
|---|---|---|---|---|---|---|---|---|
| hysteresis | 33 (27) | 13.57-13.90 N m | 14.75-15.21 A | 76.3-106.2 % | -1.64 to +0.79 % | -1.95 to +1.59 % | -2.23 to +27.92 pts | 20 of 27 |
| pwm_current | 5 (0) | - | - | - | - | - | - | **no**: emulator overrun |
| tsf | 6 (0) | - | - | - | - | - | - | **no**: emulator overrun |

Health (hysteresis, every run): emulator step mean 2.40-2.42 us, max 4.18-4.39 us, 0 overruns, 0 dropped; ISR mean
4.49-4.55 us, max 4.94-5.28 us, 0 ISR overruns; latency 6.15-6.31 us; clock ratio 1.01064-1.01208 (window spread
113-498 ppm); trigger to `ctrl_isr` 16.9 us; die temperature 65-67 C. Six of the 33 runs had a capture sequence gap
(1-2 packets, 1-2 bad frames on the host, `dropped` 0) and were marked invalid: 5 of them in the first 8 runs (within
about 15 minutes), then none in 45 debugging captures (20 in one session, 15 fresh sessions, 10 with a SIL run
between) and 1 in the remaining 25 runs. The loss comes in bursts; its side is still open.

**pwm_current and tsf: the emulator's 5 us step overruns.** Every run stopped with one overrun, 1.3 ms (pwm_current)
to 0.55 s (tsf) after the start: READY falls, the controller stops ("READY low"), and the capture ends without
CAPTURE_END. Before it the step maximum was 4.80-4.85 us (tsf); the overrun step took 5.03-5.43 us. A scratch build
(not in the tree) recorded the first overrun step: 5084-5294 of the 5040 cycles per step at 1008 MHz, gate averaging
1742-2546, plant 1397-1668, two gate edges in the window and two phases with flux; the rest (output stage, encoder and
GPIO interrupts preempting the step) 950-1900. Hysteresis switches only at the ISR instants and stays below 4.4 us.
pwm_current with `theta_off` 90 (one phase at a time) ran 2 of 4 runs without an overrun (step max 4.76-4.78 us; both
passed: -0.88 / +0.16 % torque, +0.07 / +0.10 % current, -0.84 / +0.92 pts ripple) and overran at the start in the
other two. In ad7606 + ad2s1210 (no encoder interrupt) both controllers overran as well (step max 5.07-5.43 us). Two
overlapping PWM phases need more than the 5 us step on this board: an owner decision (cheaper gate averaging per edge,
a longer step, or another step budget); not tuned away.

**hysteresis ripple: 7 of 27 valid runs fail the ripple bound (+5.6 to +27.9 points); torque and current pass in all
27.** In those windows the HIL ripple is 102-106 % (otherwise 76-80 %). One chop late in a stroke (after an earlier
chop that the SIL extends by one ISR period and the HIL does not) lands where the phase is saturated near alignment,
the current climbs from 16 to 32 A in 95 us while the next phase is already high, and the torque peaks at 22 N m
against 18.8. The emulator's torque and currents agree with the tables at those samples (within 0.03 N m). The
matched SIL does not produce such windows at the mean sensed-value age (6.2 us: 0 of 74 consecutive 10 ms windows
above 83 %; 28 variants of start angle, noise and seed: 77-80 %), but it does at the low end of the HIL's age range D
to D + dt: at 3.7 us 22 of 29 windows are at about 102 %, at 5.0-8.7 us none. The HIL samples each value at an age
uniform in that range, so a borderline chop decision can go either way, while the matched SIL models the mean age
only. The max-minus-min ripple of a 10 ms window is therefore bimodal at this operating point and the 5-point bound
fails on a share of valid runs: a limit of the matched SIL's age model (and of the ripple metric), for the owner; not
tuned away.

### Step 1b: emulator step time with two PWM phases (2026-10-23)

Goal: pwm_current and tsf at the Step 1 operating point with 0 overruns and step max <= 4.5 us (90 % of dt), by
result-neutral speedups only (dt 5 us, 1008 MHz and the overrun rule unchanged).

Profile (scratch build, not in the tree: cycle marks per stage of the step interrupt, the cycles of every preempting
interrupt including its closing `dsb`, the averager's cycles net of interrupts by edges in the window; 1008 cycles =
1 us, 5040 per step). Worst step of a run and stage mean over the run:

| | Worst step (cycles) | take / averager / capture+stats / plant / outputs | interrupts in it | Averager per window, 1 / 2 edges (mean / max) | Stage means: averager / plant / outputs |
|---|---|---|---|---|---|
| pwm_current, before | 5428 (overrun) | 190 / 2855 / 164 / 1587 / 616 | 1364 in 5 | 1141 / 1406, 1617 / 1844 | 643 / 1389 / 432 |
| tsf, before | 5283 (overrun) | 190 / 2582 / 163 / 1408 / 924 | 1021 in 2 | -, 1529 / 1865 | 487 / 1295 / 431 |
| pwm_current, after | 5106 (overrun) | 1093 / 1382 / 170 / 1523 / 922 | 1259 in 4 | 879 / 1112, 1184 / 1373 | 542 / 1435 / 440 |
| tsf, after | 4565 | 278 / 1272 / 170 / 2197 / 632 | 748 in 1 | 813 / 1117, 1122 / 1321 | 433 / 1298 / 432 |

Interrupt cost (mean, cycles): gate edges and CONVST 259-357, encoder compare 134-154, AD7606 BUSY timer 263-291; a
worst step carries 750-1460 cycles of them. On the board with interrupts off (minimum of 64 calls), the averager
takes 278 -> 251 cycles with no edge, 1104 -> 814 with one edge, 1822 -> 1281 with two; the plant step with two
conducting phases 1225-1260 (one table lookup 114).

What changed (commit f33a685):
- `srm_gate_avg_window` collects the window's segments between edges and maturing changes (32-bit ticks after the
  window start, events up to the start handled first as before), then advances each winding over them; the per-winding
  sequence of float operations is the one of the earlier walk, so the voltages are bit-identical. The switch-on
  fractions are optional (NULL): the emulator and its PC model `srm_emu.c` never used them.
- The gate interrupt reads GPIO6_ISR once (the output pins of the same port reuse it) and does not read GPIO7/GPIO9
  when no pin of that port is enabled.
- Result-neutrality checks: host, old against new on random streams (late edges, gaps between windows, delays up to
  3 windows, windows of more than 16 segments), double and float builds: bit-identical voltages and fractions; new
  test `test_matches_reference_walk` against a plain event walk. Board: a 20000-window run of averager and plant on
  the case tables (two phases chopping at random instants) gives the same hash (a9d0cb2e) as the earlier firmware.
  Inlined into the window function, the per-winding advance compiled by arm-none-eabi-gcc 15.2 at -O3 read
  uninitialised stack on the board (wrong voltages, a hash that changed between calls; the host build and -O2 were
  correct); it is kept out of line, which is bit-identical. (Superseded by Step 1d and Step 1e: the miscompile finding
  is withdrawn, the inlined code is correct at 912 MHz and `advance_all` is no longer forced out of line.)

Bench, final firmware, 10 runs each (`examples/control_hil.py --case ... --torque 10 --controllers ...`):

| Controller | Runs (valid) | d_torque | d_irms | d_ripple | Passed | Step mean / max | Overruns |
|---|---|---|---|---|---|---|---|
| tsf | 10 (10) | -0.09 to +0.30 % | -0.00 to +0.24 % | -1.44 to +0.82 pts | 10 of 10 | 2.35-2.37 / 4.55-4.75 us | 0 |
| pwm_current | 10 (0) | - | - | - | no | 0.52-0.56 / 5.03-5.20 us | 1 per run, in the first ms |

tsf now runs and passes (Task 14: every run overran), but its step max is 4.55-4.75 us, above the 4.5 us goal.
pwm_current still overruns at the start of every run, where two phases chop with edges in the same window: the worst
step is about 2600-2800 cycles of averager and plant, about 1100-1300 of the rest, and 1250-1450 of interrupts. Further
result-neutral gains are small (the plant step is latency-bound float arithmetic; the interrupt cost is peripheral
register access), so 0 overruns and 4.5 us need an owner decision (a longer emulator step, another step budget, or
moving the BUSY and CONVST handling into hardware).

### Step 1c: AD7606 CONVST and BUSY in hardware (2026-10-23)

Owner decision of 2026-10-23: move the CONVST/BUSY handling of the emulated AD7606 into hardware, and fall back to a
6 us emulator step only if that is not enough. dt 5 us, 1008 MHz, the overrun rule, the tolerances and HSE_VALUE are
unchanged; no pin was re-assigned.

What is in hardware now (`hil/emulator/ad7606_slave.cpp`):
- Pin 5 (GPIO_EMC_08) is XBAR1_INOUT17 (ALT3, `IOMUXC_XBAR1_IN17_SELECT_INPUT` 0). XBAR1 routes it to output 99,
  the input of QTIMER4 timer 1 (`IOMUXC_GPR_GPR6` QTIMER4_TRM1_INPUT_SEL).
- Pin 6 (GPIO_B0_10) is QTIMER4_TIMER1 (ALT1). The timer runs in triggered count mode (CM 6) on the IP bus clock
  (252 MHz, prescaled only for t_conv above 260 us), with OUTMODE 5 and inverted output: BUSY rises at the CONVST
  edge and falls when the count reaches COMP1 = round(t_conv x f) - 1, then the timer re-arms. An edge during BUSY
  restarts it (CSCTRL.TCI), as the old interrupt did. ONCE is not usable (the timer then fires once only), and
  without TCI an edge during BUSY stops the count, so BUSY stays high until the next edge (both seen in a board
  self-test that makes edges by switching XBAR1's select between the logic-low and logic-high inputs). t_conv is
  floored at 1 us, so the frame is always in the FIFO before BUSY falls.
- No BUSY interrupt (GPT1 is no longer used) and no CONVST work in the gate interrupt: GPIO9 is not read any more.

What is left on the CPU, and why: the frame load. The same edge sets the timer's input edge flag; its interrupt
(QTIMER4, priority 0 as the gates) clears the flag, writes CR.RTF, SR, TCR and the four TDR words from the latest
step's buffer, and stamps the trigger for `trigger_hz` with the cycle counter (as before). A DMA version was built and
worked on the wire: XBAR1 DMA request 0 to an eDMA scatter/gather chain (CR+SR, TCR, the four codes from the buffer
whose address the step writes into the third descriptor), the frame in the FIFO 0.43-0.46 us after the edge, plus
stamps of GPT1's count. It is not used because the Teensy took bus faults with any eDMA in use:

| Build (all else as committed) | tsf runs that started | Ended by a fault reboot |
|---|---|---|
| eDMA frame chain plus a stamp channel (the CPU reads its CITER once per 50 ms) | 18 | 3 |
| the same, stamp channel not enabled | 3 | 3 |
| eDMA frame chain with the stamps written to memory (no eDMA register reads) | 3 | 2 |
| no eDMA transfer, CPU reads of an eDMA TCD once per 50 ms | 2 | 2 |
| eDMA doing only one RAM-to-RAM copy per CONVST | 4 | 2 |
| no eDMA at all (hardware BUSY, frame not loaded) | 4 | 0 |
| HEAD (Step 1b firmware) | 8 | 0 |
| committed (hardware BUSY, CONVST interrupt) | 25 | 0 |

Every fault the Teensy's crash report caught (a scratch relay of `CrashReport` over HIL_ERROR) was the same: PRECISERR
in `pit_isr` reading PIT channel 0 TFLG, BFAR 0x4008418C; the instruction reads 0x4008410C, one address bit apart.
A faulted board reboots (the core's fault handler) and is gone from USB for a few seconds.
pwm_current never faulted with the eDMA in 16 runs (10 of them a 10-run bench: all valid and passed, 0 overruns, step
max 4.23-4.46 us); tsf did. The eDMA's registers and the PIT are both behind the AIPS-1 bridge, and the IP bus runs
at 252 MHz (1008 / 4), above the part's 150 MHz rating; that is the likely cause, not proven.

Wire checks (scratch builds `-DDBG14B2`, not in the tree: the emulator sends a pattern frame, V1 = a 16-bit counter
of published steps and V2-V8 a hash of it; the Nucleo checks every frame and times BUSY on both edges with EXTI3 and
its cycle counter, nominal 400 MHz, which runs 1.1 % fast; `open_loop`, 20 s each):

| Firmware | Frames checked / bad | Steps between frames | CONVST to BUSY falling: min / mean / max | trigger_hz windows finite, mean |
|---|---|---|---|---|
| HEAD | 404 710 / 0 | 9-11 | 5060 / 5120 / 5480 ns | 398 of 398, 20 229.5 Hz |
| committed | 405 365 / 0 | 9-11 | 4360 / 4385 / 4500 ns | 399 of 399, 20 220.6 Hz |

- Codes: bit-exact, no torn frame, and each frame carries the latest step's values (9.9 steps per CONVST on average).
- BUSY: CONVST to BUSY falling is t_conv (4.15 us; the timer gives 1046 / 252 MHz = 4.151 us) plus the Nucleo's EXTI
  latency, with 140 ns of spread instead of 420 ns. Before, BUSY rose after the interrupt had loaded the FIFO and
  fell in a second interrupt, so it ended 0.7 us later and the controller's sample time (trigger to `ctrl_isr`) was
  17.7-17.8 us; now it is 17.0-17.1 us. The width seen on the Nucleo is 3.94-4.16 us (rising edges are stamped late
  while the trigger interrupt is still running, so the falling edge is the reliable measure).
- trigger_hz: the same method as before ((n - 1) / (t_last - t_first) of the cycle stamps per 50 ms window).

Profile (scratch build, not in the tree, as in Step 1b; 3 runs each, cycles at 1008 MHz, 5040 per step):

| Firmware | pwm_current worst step (interrupts in it) | tsf worst step (interrupts) | Interrupt mean: gates / CONVST / BUSY / encoder |
|---|---|---|---|
| HEAD | 5136-5254, overrun in every run (1392-1527 in 4-5) | 4383-4448 (752-765 in 1) | 266-355 incl. CONVST / - / 265-301 / 134-156 |
| committed | 4318-4464, no overrun (398-573 in 3) | 3812-4180 (129-171 in 1) | 91-94 / 139 / - / 151-152 |

Bench, committed firmware (`examples/control_hil.py --case ... --torque 10 --controllers ...`):

| Controller | Attempts | Refused at START (self-check) | Ran | Valid | Passed | d_torque | d_irms | d_ripple | Step mean / max | Overruns |
|---|---|---|---|---|---|---|---|---|---|---|
| pwm_current | 22 | 10 | 12 | 11 | 11 | -0.03 to +0.28 % | -0.04 to +0.48 % | -1.33 to -0.32 pts | 2.57-2.58 / 4.31-4.64 us | 0 |
| tsf | 16 | 4 | 12 | 12 | 12 | -0.25 to +0.25 % | -0.27 to +0.22 % | -2.14 to +0.11 pts | 2.32-2.33 / 3.97-4.16 us | 0 |
| hysteresis | 3 | 1 | 2 | 2 | 2 | -0.03 to +0.45 % | -0.74 to +0.34 % | -1.00 to +1.87 pts | 2.38 / 3.65-3.68 us | 0 |
| hysteresis, ad7606 + ad2s1210 | 2 | 0 | 2 | 2 | 2 | -1.25 to +0.31 % | -1.40 to -0.21 % | 0.00 to +3.50 pts | 2.31-2.33 / 3.53 us | 0 |

The one invalid pwm_current run had a capture sequence gap (the known USB loss). Clock ratio 1.0102-1.0115 (from
trigger_hz), ISR max 5.90 us (pwm_current) and 7.08 us (tsf), latency 5.55-5.69 us. The step max of pwm_current
(4.31-4.64 us) is above Step 1b's 4.5 us goal in some runs but below the 5 us step in all; the overrun rule is
unchanged. Before the final firmware, 10 tsf runs of the same design with the scratch crash relay: 9 valid and
passed, 0 overruns, step max 3.98-4.22 us.

Part 2 (the 6 us step) was not needed: pwm_current runs with 0 overruns at 5 us.

START refusals by the gate averager self-check: during this bench the self-check at START refused with hash
8ea70d6e (the hash the inlined averager gives, see Step 1b) in a share of the starts, with this firmware and with
HEAD alike. A/B the same hour, each START after a fresh EMU_CONFIG and table upload (`starts.py`, scratch): HEAD 13 of
30 refused (and one start lost to a reboot), the committed firmware 5 of 30. With one configure and 60 starts: HEAD 1
of 40, committed 1 of 60. Once the board took a bus fault inside `advance_all` (the first load of its source array,
address 0x20068000, the top of the stack) at START instead. The averager source is unchanged by this step; the
refusal is the self-check working, and a refused start was repeated. Open for the owner (see Summary).

### Step 1d: root cause of the self-check refusals (2026-10-23)

The gate averager self-check refuses START because the Teensy computes wrongly at 1008 MHz, not because of the code.
The default clock is unchanged; the clock is an owner decision.

Method: a scratch build (not committed) compared every self-check window with a host table of per-window hashes and
reported the first differing window, its inputs, the state before it, FPSCR, FPCCR, SP and the cycles per window. A
mode counter in `emu_start` ran the check in one of four ways, in turn: (0) as committed; (1) after a 2 ms spin on
the cycle counter; (2) as (1), then a second check straight after the first; (3) after 2 ms of 8-wide float
multiply-adds. A scratch CrashReport relay reported faults. Each START came after a fresh EMU_CONFIG and table upload.
The running firmware hash was checked after every upload.

| Build, clock, core voltage | STARTs | Self-check wrong | Board faults |
|---|---|---|---|
| per-window build, 1008 MHz, 1575 mV | 30 | 18 (window 0 in 17, window 2 in 1) | 1 START lost (no relay) |
| same, interrupts masked during the check | 120 | 14 (window 0 in 9, window 2 in 5) | 3 STARTs lost (no relay) |
| mode build, 1008 MHz, 1575 mV (3 soaks) | 200 | mode 0: 4 of 50, mode 1: 21 of 50, mode 2: 24 of 50 (its second check: 0 of 50) | mode 3: 50 of 50 (30 relayed) |
| mode build, 1008 MHz, lazy FP stacking off | 80 | modes 0-2: 16 of 58 | mode 3: 22 of 22 |
| mode build, 960 MHz, 1550 mV | 80 | 0 of 60 | mode 3: 20 of 20 |
| mode build, 912 MHz, 1525 mV | 80 | 0 | 0 |
| mode build, 816 MHz, 1425 mV | 80 | 0 | 0 |
| mode build with advance_all inlined, 1008 MHz | 40 | 30 of 30 | 10 of 10 |
| mode build with advance_all inlined, 912 MHz | 40 | 0 | 0 |
| mode build, 1008 MHz, voltage lowered to 1525 mV | 40 | - | 40 of 40 |
| mode build, 912 MHz, voltage lowered to 1425 mV | 40 | 14 of 14 (all 8ea70d6e, window 0) | 26 of 26 |
| mode build, 912 MHz, voltage lowered to 1375 mV | 40 | - | 40 of 40 |
| committed source, 1008 MHz | 100 | 0 | 0 |

- Every wrong result is in the first windows of a check (window 0, rarely 2), with the same few values each time
  (8ea70d6e: only phase 3's voltage of window 0 wrong; 64fb7149: window 0's pending changes matured early).
  The cycle counts of a failing window are identical from run to run, so no interrupt hit it.
- Every fault is a PRECISERR at the same instruction, the first load of `src` in `advance_all`, with BFAR
  0x20070000 (past the end of DTCM). This is the fault Step 1c saw once at START. At 1375 mV other faulting addresses
  appear as well.
- Ruled out: interrupts during the check (masked: still wrong); lazy FP stacking (FPCCR.LSPEN off: no change); FP
  register or uninitialised-stack contents left by earlier code (mode 0 and mode 1 leave the same registers and differ,
  8 % against 42 %, and the stack scrub runs before each window either way); caches (code in ITCM, data and stack in
  DTCM); a miscompile (the inlined averager, refused 30 of 30 at 1008 MHz, is correct at 912 MHz in 40 of 40, and the
  host build is correct).
- What triggers it is the start of heavy work after lighter work. A check straight after another check is always
  right. A check after 2 ms of light spinning is often wrong. A check after 2 ms of full-throughput float work faults
  every time.
- Dose-response: at a fixed clock, lowering the core voltage turns every START into the same failure. At 912 MHz, a
  clock that is otherwise clean, the identical wrong hash 8ea70d6e and the identical fault (0x416, 0x20070000)
  appear when the voltage is lowered to 1425 mV. So these signatures are timing failures of the silicon. The Teensy
  core already runs the DCDC at its maximum, 1575 mV, at 1008 MHz; the part is rated 600 MHz.
- The committed build passed 100 of 100 STARTs at 1008 MHz in this session (it refused 15 of 43 in Step 1c). The rate
  depends on the code layout and the preceding load, so a passing soak does not show margin.
- The step interrupt starts the same kind of float burst every 5 us after the loop's light polling, so real runs at
  1008 MHz are exposed to the same failure. The Step 1c PIT faults (a one-bit wrong bus address) fit it.
- Step 1b's finding that GCC 15.2 at -O3 miscompiles the inlined `advance_all` is withdrawn. The inlined code is
  correct; it fails more often at 1008 MHz. `noinline` and its comment were left in the code until the owner decided
  on the clock (superseded by Step 1e: 912 MHz, `noinline` dropped).

### Step 1e: 912 MHz default (owner decision, 2026-10-23)

The Teensy now runs at 912 MHz (`hil/platformio.ini`, 1525 mV from the core's table). The 85 C guard is unchanged,
and so are the 5 us step, the overrun rule and the tolerances. With the same commits, the CONVST interrupt moved one
NVIC level below the gates (16; encoder 32, step 48), so a gate edge pending together with a CONVST edge is stamped
first. The emulator also refuses `ad7606_t_conv_us` outside 1..1000 us; on the board, 0.999 and 1000.5 are refused,
1 and 1000 accepted.

`advance_all` is no longer forced out of line. Inlined, it is correct at 912 MHz (40 of 40 stress STARTs in Step 1d)
and faster: 1060 against 1096 cycles per self-check window (the averager calls only, best of 5 checks of 4000 windows,
-3.3 %).

Soak at 912 MHz, each START after a fresh EMU_CONFIG and table upload, die at 63.2-64.6 C:

| Firmware | STARTs | Refused | Faults |
|---|---|---|---|
| committed | 150 | 0 | 0 |
| committed plus the Step 1d stress modes (40 each: plain, after a 2 ms spin, twice after the spin, after 2 ms of 8-wide float work) | 160 | 0 | 0 |

Captures at 912 MHz:

| Capture | Result |
|---|---|
| buffered, pwm_current on the case (8000 steps, session host) | 2 of 3 valid; the third had a sequence gap (the known USB loss); 0 overruns, step max 4.92-4.99 us |
| streamed, pwm_current on the case, 100 000 and 400 000 steps (session host) | 0 of 6 valid: in 4 the step overran (max 5.01-5.09 us) and the run stopped; in 2 the ring filled after 17 208 and 18 888 samples |
| buffered, self-test pattern (`examples/hil_emu_selftest.py`) | valid, -0.004 % against the PC model |
| streamed, self-test pattern, one phase, raw-reading host (bytes first, parsed afterwards; scratch) | ring full after 42 128-42 156 samples in 3 of 3 (100 000 and 400 000 steps): about 161 k samples/s sustained, 81 % of the 200 k/s needed; 0 overruns |

So streamed captures do not work at 912 MHz. At 1008 MHz the raw host kept up with the self-test pattern; at
816 MHz it reached 77 % (Bench checks). Captures that fit the 8192-sample RAM ring are buffered and work. Longer
captures are limited to about 40 000 steps (0.2 s) of a light load. With a controller, streaming adds enough CPU
load that pwm_current overruns. A re-check of the 1008 MHz streaming rate with the same host was not possible: the
self-check refused 2 of 2 STARTs there (hashes b89a73f9 and 31a2a3c0), as Step 1d predicts.

Bench at 912 MHz (`examples/control_hil.py --case ... --torque 10`; Task 14 case and operating point; ad7606 + encoder):

| Controller | Runs | Valid | Passed | d_torque | d_irms | d_ripple | Step mean / max | Overruns | ISR mean / max | Latency |
|---|---|---|---|---|---|---|---|---|---|---|
| pwm_current | 10 | 10 | 10 | +0.08 to +0.52 % | +0.00 to +0.54 % | -1.28 to -0.48 pts | 2.85 / 4.85-4.96 us | 0 | 5.26-5.30 / 5.90-5.91 us | 6.04-6.05 us |
| tsf | 12 | 11 | 11 | -0.37 to +0.30 % | -0.27 to +0.23 % | -2.00 to +0.35 pts | 2.55-2.57 / 4.34-4.55 us | 0 | 5.83-5.85 / 7.06 us | 5.86-5.89 us |
| hysteresis | 8 | 5 | 4 | -0.87 to +0.47 % | -1.54 to -0.10 % | +0.81 to +25.49 pts | 2.61-2.63 / 4.03-4.12 us | 0 | 4.51-4.55 / 5.20-5.21 us | 6.00-6.14 us |

- The invalid runs had capture sequence gaps (the known USB loss): 1 tsf, 3 hysteresis.
- The hysteresis run that failed had a ripple of +25.49 pts: the Step 1 bimodality, within its +5.6 to +27.9 range.
- Clock ratio 1.0105-1.0119.
- No run overran, so the 6 us step (Part 2 of Task 14b2) was not needed.
- pwm_current's step max (4.85-4.96 us) leaves 0.04-0.15 us of the 5 us step. At 1008 MHz it was 4.31-4.64 us.

### Step 1f: 6 us step (owner's fallback, 2026-10-23)

pwm_current had almost no step headroom at 912 MHz and overran while streaming (Step 1e), so the emulator step is
now 6 us. It is one constant, `HIL_EMU_STEP_NS` in `hil/common/hil_proto.h` (Python `srmsil.hil.proto.EMU_STEP_NS`
and `EMU_DT`). The firmware derives everything from it:
- the step cycles (5472 at 912 MHz);
- the PIT period (144 ticks of 24 MHz);
- the GPT ticks per step of the encoder schedule (144, checked at compile time);
- the plant dt and the capture header dt;
- the live-statistics window (8333 steps, about 50 ms).

The PC emulator model, the session, the fake rig, the self-test example and the web capture length take `EMU_DT`.
The host now refuses a capture whose header dt is not its own step, and it computes capture times from `EMU_DT`, not
from the header's float32 dt. The 912 MHz clock, the overrun rule, the tolerances, HSE_VALUE and the 0.5 us PC SIL
are unchanged.

Emulator model against the 0.5 us SIL (`tests/hil/test_hil_emulator_model.py`, CI, limit 1 %):

| Check | 5 us | 6 us |
|---|---|---|
| open_loop, mean torque | 0.030 % | 0.044 % |
| open_loop, RMS current (4 phases) | 0.004 % | 0.011-0.015 % |
| pwm_fixed, mean torque | 0.029 % | 0.050 % |
| pwm_fixed, RMS current | 0.003 % | 0.013 % |
| hard chop at 25 %, model against the SIL at the step instants | -0.001 % | -0.006 % |
| hard chop, the SIL at the step instants against its full-rate RMS | -1.34 % | -0.17 % |

Resolution limit: current pulses shorter than about two steps, now 12 us, are resolved only at the step instants.
The hard-chop pulses here are 12.5 us, about 2.1 steps. At 5 us the 50 us carrier was exactly 10 steps, so the
instants always fell at the same carrier phase, and the full-rate RMS read 1.3 % low. At 6 us the carrier is 8 1/3
steps, the instants sweep the carrier phase, and the error is 0.17 %. A carrier period that is a whole number of
steps (for example 16.67 kHz at 6 us) brings back the 1 to 2 % low reading.

Emulator self-test (`examples/hil_emu_selftest.py`, Teensy alone, firmware 9745b118):
- buffered 8000 samples against the PC model: -0.0026 %;
- streamed: 35 000 contiguous samples matched the model (-0.0019 %), then the ring filled;
- live windows at 20 Hz;
- step max 3.74 us, 0 overruns.

Bench at 912 MHz (`scratchpad/t14f/bench.py`: control_hil's `run_one` on the Task 14 case and operating point, ad7606
+ encoder). Both boards were flashed with the same build, and after every run HELLO read the running hash on both
boards. It matched the build in 32 of 32 runs.

| Controller | Runs | Valid | Passed | d_torque | d_irms | d_ripple | Step mean / max | Max / 6 us | Overruns | ISR mean / max | Latency |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pwm_current | 10 | 10 | 10 | +0.20 to +0.57 % | -0.00 to +0.55 % | -1.28 to -0.29 pts | 2.91 / 4.86-5.04 us | 81.0-84.1 % | 0 | 5.26-5.30 / 5.90-5.91 us | 6.49-6.52 us |
| tsf | 16 | 14 | 14 | -0.12 to +0.39 % | -0.15 to +0.23 % | -1.76 to +0.50 pts | 2.62 / 4.53-4.88 us | 75.5-81.3 % | 0 | 5.83-5.86 / 7.06 us | 6.36-6.40 us |
| hysteresis | 6 | 6 | 5 | -0.31 to +0.28 % | -0.55 to +0.35 % | -0.10 to +24.89 pts | 2.66 / 4.19-4.31 us | 69.8-71.8 % | 0 | 4.52-4.55 / 5.20-5.21 us | 6.42-6.58 us |

- Firmware hashes: pwm_current 9745b118, tsf 871f8907, hysteresis 46ce1e59.
  - Four tsf runs used d0a833c4. It was built while emu.h had a comment-only edit, which was later reverted.
  - The committed tsf build alone gave 12 runs, 10 valid, 10 passed.
- Invalid runs: 2 tsf, both capture sequence gaps (the known USB loss).
- The hysteresis run that failed had a ripple of +24.89 pts: the Step 1 bimodality.
- Clock ratio 1.0104-1.0114.
- The step max did not change in absolute terms (pwm_current 4.85-4.96 us at 5 us). The headroom grew from
  0.04-0.15 us to 0.96-1.14 us.
- pwm_current and the top of tsf are still above the 80 % step-time warning.
- The latency rose by about 0.5 us (half a step more of averaging age); the matched SIL takes it from the measurement.

Streamed captures, pwm_current on the case (`scratchpad/t14f/streamchk.py`, run_hil, session host, the Step 1e
lengths in steps, 3 each):

| Steps | Valid | Ring full (samples at the end) | Sequence gap | Overruns | Step max |
|---|---|---|---|---|---|
| 100 000 (0.6 s) | 0 | 2 (14 520, 17 376) | 1 | 0 | 5.09-5.13 us |
| 400 000 (2.4 s) | 0 | 2 (84 016, 156 228) | 1 | 0 | 5.03-5.13 us |

- Streaming no longer overruns: 0 of 6 runs, against 4 of 6 at 5 us.
- It still fails, because the host does not keep up with 166.7 k samples/s. The ring filled after 14 520 to 156 228
  samples, against 17 208 and 18 888 at 5 us.
- Every streamed run counted 1 dropped sample or cut frame.
- Captures within the 8192-sample ring (49 ms) are buffered and work.

### Step 2: speed step with the speed loop (dynamic, hysteresis)

Dynamic mode from rest, speed command 1500 rpm, J 1e-3 kg m^2, no load or friction; speed loop `speed_kp` 0.2,
`speed_ki` 2.5, `speed_filter_hz` 200 (faster than the defaults so the step fits a buffered capture: a streamed
capture on the wired rig ends at about 10 600 samples with a full ring). Capture 8000 steps (40 ms) from 0.3-0.6 ms
after Start; the matched SIL runs from Start (`match_plan`, dynamic).

| Firmware | Runs | 10 % reached (HIL / SIL) | Rise 10-90 % (HIL / SIL) | Overshoot (HIL / SIL) | Speed at 40 ms (HIL / SIL) | Speed difference max / rms |
|---|---|---|---|---|---|---|
| before the ctrl_slow fix | 3 | 2.48-2.67 / 3.06 ms | 4.59 / 4.58-4.59 ms | 6.8-6.9 / 6.6-6.7 % | 1602-1603 / 1599-1600 rpm | 131-193 / 39-58 rpm |
| after | 8 | 3.04-3.08 / 3.06 ms | 4.57-4.60 / 4.58-4.59 ms | 6.6-7.5 / 6.5-7.0 % | 1599-1612 / 1598-1606 rpm | 3.4-16.0 / 2.3-12.7 rpm |

The hysteresis drive only motors and nothing loads the rotor, so the overshoot is also the final error (6.6-7.5 % HIL,
6.5-7.0 % SIL). The window comparison is NaN in every run (neither side draws current in the summary window, after
the overshoot), so the step response is the comparison here. Health: step mean 1.70-1.72 us, max 4.26-4.66 us, 0
overruns; ISR 4.07-4.09 / 4.53-4.57 us; latency 6.5-7.0 us; clock ratio 1.0112-1.0120; no clipped sample.

Found and fixed: the HIL led the SIL by 0.4-0.6 ms because TIM6 (`ctrl_slow`, 1 kHz) ran free since boot, so the first
`ctrl_slow` after a start came at a random 0-1 ms, while the SIL calls it first one period after the start. TIM6 is
now restarted when RUN rises (`hil/controller/srm_hal_stm32.c`; bench evidence above, no host test reaches the
timer). In 2 of the 13 runs (the first two after that flash) `match_plan` gave "no matched SIL scenario" with a
pydantic finite-number error; it did not recur in 9 more runs and the field was not recorded (open).

### Step 3: live theta_on change and captures through srmweb

Loopback srmweb from the worktree (scratch DB and cache), routes only: Build & Flash job (`hil_flash`; the first
attempt failed on the Teensy upload, the resume passed), `POST /api/hil/session`, start, live numbers from
`/api/hil/session/events`, capture of 4000 steps, compare, `POST /api/hil/session/param` `theta_on` 20 (electrical
degrees), live numbers, capture, compare, stop. Hysteresis, 1000 rpm, 10 N m.

| | Live torque (24 windows) | Live RMS current per phase | Live ripple (last window) | Capture | d_torque | d_irms | d_ripple | Passed |
|---|---|---|---|---|---|---|---|---|
| defaults | 13.71 N m | 14.97 A | 105.3 % | `f6a0633508644827b373de6e46f6905e` | +0.81 % | +0.51 % | -1.18 pts | yes |
| theta_on 20 (live) | 13.28 N m | 13.61 A | 86.3 % | `8470573eb0454ea9a5f49997ad43fdad` | -1.42 % | -1.23 % | +1.79 pts | yes |

Live health: step max 4.15 / 4.31 us, 0 overruns; ISR mean 4.52 / 4.47 us, max 5.20 us, 0 ISR overruns; trigger to
`ctrl_isr` 16.95 us. A first pass of the same flow (before the reset fix below) gave +2.04 and -9.40 points ripple (the
second with the SIL at the high-ripple branch of Step 1).

Found and fixed: the reference controllers keep `ctrl_param` values in statics, so `theta_on` 20 from that session
stayed on the board, and the next `examples/control_hil.py` runs (which set no parameter) read -2.4 to -4.1 % torque
and -9.0 to -9.9 % RMS current against a matched SIL at the defaults. `HilSession.configure` now resets the controller
board first (`HIL_COMMAND` mode `HIL_CMD_CTRL_RESET`: stop, acknowledge, `NVIC_SystemReset` once the acknowledgement
has left the UART; the host waits for HELLO with the same build, 0.6 s on the bench). Test:
`tests/hil/test_hil_session.py::test_configure_resets_parameters_of_an_earlier_session`. Bench: 13.72 N m at the
defaults, 13.30 N m with `theta_on` 20, 13.73 N m after the next configure.

### Step 4: ad2s1210 (ad7606 + ad2s1210, hysteresis)

Resolver angle (12 bits, 1 pole pair, `encoder_cpr` 0), 1000 rpm, 10 N m, 3 runs per setting, 40 ms captures. Each
turn-on (both switches off for at least 200 us before it) at the true rotor angle of the capture is compared with the
matched SIL's turn-on in the same stroke (the SIL models the same resolver errors), and the shift of each turn-on
between the two settings with the tracked-angle error of atan2(sin x, (1 + g) cos(x + phi)) at that angle:

| Resolver errors | Turn-ons | HIL - SIL turn-on angle: mean / std / max | d_torque | d_irms | d_ripple | Passed |
|---|---|---|---|---|---|---|
| none | 48 | 0.07 / 2.28 / 4.52 mrad | -0.50 to +0.10 % | -0.66 to +0.15 % | -0.01 to +24.15 pts | 2 of 3 |
| gain mismatch 1 %, phase error 0.01 rad | 48 | 0.04 / 1.50 / 3.61 mrad | -0.53 to +0.06 % | -1.26 to -0.04 % | +2.70 to +26.43 pts | 1 of 3 |

The turn-ons agree with the SIL within one ISR period of rotation (5.2 mrad at 1000 rpm). With the errors set they
shift by -11.5 to +2.1 mrad against the model's -11.9 to +1.8 mrad (44 locations, residual 0.30 +- 1.61 mrad,
correlation 0.947): the angle error follows the set gain and phase errors (-1.3 to +7.9 counts of 4096, as expected).
The ripple failures are the Step 1 bimodality. Health: step 2.39-2.44 / 4.10-4.16 us, 0 overruns; ISR 6.10-6.18 /
6.78-6.88 us; latency 6.24-6.37 us. Hysteresis at the Step 1 settings in this mode: 2 runs, one valid (-0.33 % torque,
-0.32 % current, -0.58 pts ripple, passed), one capture gap.

### Step 5: internal current sensing

Not run: no DACs.

### Re-run: sensed-value age jitter and the ripple median (2026-10-24)

Owner decision (2026-10-23): the matched SIL models the spread of the sensed-value age, and the ripple is compared as
a median over strokes.
- The HIL latches the emulator's output at an age uniform in [D, D + dt], dt = `EMU_DT` (6 us); the measured latency
  is its mean. The matched SIL now draws each ISR sample's age from that range: `sensors.delay` = latency - dt/2,
  `sensors.delay_jitter` = dt (`SensorSettings.delay_jitter`, drawn from the run's seeded sensor RNG; 0 is
  bit-identical to before).
- `d_ripple_pts` is the median per-stroke ripple of the HIL minus the SIL's. A stroke is one torque period
  (2 pi / (q N_r), 15 deg here) of rotor angle from the angle traces; only complete strokes in the window count; fewer
  than 3 on either side fails. The whole-window ripples are kept as information. The 5-point bound, the 3 % torque and
  current bounds and the overrun rule are unchanged.
- A session refuses boards that do not run the flashed build of the controller (`run_hil(expect=...)`, srmweb
  `HilManager.open`); every run below checked it before the capture and read the hashes again after it.
- An emulator step max above 80 % of the step is reported as a warning (owner decision), not a failure.

Rig: Teensy 4.1 at 912 MHz (COM4), 6 us step, Nucleo-H723ZG (COM6), both boards flashed with the same build per
controller and mode. Case and operating point as in Step 1 (8/6 at 60 turns, fixed 1000 rpm, 10 N m command, 400 V,
20 kHz, default parameters). Captures are buffered, 8000 steps (48 ms, `--duration 0.048`), so the summary window (its
second half, 24 ms) holds 8 to 9 complete strokes. Tool: `examples/control_hil.py`'s `run_one` in a loop
(`scratchpad/t14c/bench.py`).

| Controller (mode) | Runs | Valid | Passed | Mean torque | RMS current | d_torque | d_irms | d_ripple (median) | Whole-window ripple HIL / SIL | Whole-window difference |
|---|---|---|---|---|---|---|---|---|---|---|
| hysteresis (encoder) | 26 | 25 | 25 | 13.67-13.89 N m | 14.90-15.22 A | -0.75 to +0.47 % | -0.67 to +0.46 % | -4.03 to +3.28 pts | 78.2-103.8 / 78.1-105.6 % | -23.48 to +25.39 pts (6 of 25 over 5) |
| pwm_current (encoder) | 12 | 11 | 11 | 9.57-9.68 N m | 10.93-11.05 A | +0.03 to +0.38 % | -0.08 to +0.34 % | -1.24 to -0.31 pts | 50.3-51.0 / 51.2-52.0 % | -1.41 to -0.52 pts |
| tsf (encoder) | 12 | 11 | 11 | 10.25-10.44 N m | 11.42-11.67 A | +0.21 to +0.55 % | +0.04 to +0.26 % | -0.74 to +0.59 pts | 69.0-71.0 / 69.1-71.2 % | -1.02 to +0.66 pts |
| hysteresis (ad2s1210) | 8 | 8 | 8 | 13.67-13.82 N m | 14.96-15.22 A | -0.58 to +0.43 % | -1.01 to +0.80 % | -1.82 to +2.88 pts | 78.4-104.3 / 78.1-84.5 % | -3.30 to +24.85 pts (3 of 8 over 5) |

Health (valid runs):

| Controller (mode) | Firmware | Step mean / max | Step-time warnings | Overruns, dropped, ISR overruns | ISR mean / max | Latency | Clock ratio |
|---|---|---|---|---|---|---|---|
| hysteresis (encoder) | 2ac78f20 | 2.64-2.68 / 4.18-4.32 us | 0 | 0, 0, 0 | 4.53-4.56 / 5.19-5.22 us | 6.43-6.65 us | 1.01055-1.01160 |
| pwm_current (encoder) | 43ff36ea | 2.90-2.93 / 5.03-5.14 us (84-86 %) | 11 of 11 | 0, 0, 0 | 5.29-5.31 / 5.90-5.91 us | 6.48-6.54 us | 1.01031-1.01125 |
| tsf (encoder) | 088451dd | 2.60-2.64 / 4.55-4.89 us | 1 of 11 | 0, 0, 0 | 5.83-5.86 / 7.06 us | 6.38-6.41 us | 1.01015-1.01112 |
| hysteresis (ad2s1210) | bb5a6725 | 2.59 / 3.87 us | 0 | 0, 0, 0 | 6.13-6.19 / 7.80-7.86 us | 6.39-6.50 us | 1.01059-1.01148 |

- The running hashes matched the flashed build before and after every run (58 of 58).
- Invalid: 3 runs (one per encoder-mode controller), each a capture sequence gap of 1-2 packets with 1-2 bad frames
  on the host (the known USB loss); 1 more hysteresis run before the series (the smoke run) had one too.
- The hysteresis bimodality is still there in both the HIL and, now, the matched SIL: whole-window ripples of about
  78 % or about 104 % on either side. With the age jitter the SIL reaches the high branch (SIL whole-window up to
  105.6 %), so the high windows no longer belong to the HIL alone; which side shows a late chop in a given window is
  random, and the whole-window difference is -23 to +25 points. The median over 8-9 strokes is not moved by such a
  stroke: -4.03 to +3.28 points, inside the 5-point bound in all 33 valid hysteresis runs.
- pwm_current's step max is 84-86 % of the step in every run: a warning, not a failure (owner decision).

### Summary

Current configuration (2026-10-24): Teensy at 912 MHz, 6 us emulator step, matched SIL with the sensed-value age
jitter, ripple compared as the median over complete strokes (re-run above).

Passed:
- Step 1 at a fixed speed, ad7606 + encoder: hysteresis 25 of 25 valid runs, pwm_current 11 of 11, tsf 11 of 11, on
  mean torque, RMS current and the median ripple; 0 overruns.
- Step 4, ad7606 + ad2s1210, hysteresis: 8 of 8 valid runs passed; the AD2S1210 angle chain with and without resolver
  errors agrees with the SIL within one ISR period (Step 4 table).
- Step 2: the speed step against the matched SIL (after the ctrl_slow fix).
- Step 3: the live theta_on change and captures through srmweb (after the reset fix).
- A session refuses boards that run another build than the flashed one (58 of 58 re-run runs checked).

Did not pass, or not run:
- Earlier comparisons, superseded by the re-run but kept as recorded:
  - Step 1 at 1008 MHz and 5 us: pwm_current (5 runs) and tsf (6 runs) stopped on an emulator overrun in every run.
  - Step 1 hysteresis (whole-window ripple, matched SIL at the mean age): 7 of 27 valid runs over the 5-point
    ripple bound (+5.6 to +27.9 points).
  - Step 4 (same metric): 3 of 6 ripple comparisons failed (resolver errors none: 1 of 3, up to +24.15 points; gain
    and phase errors: 2 of 3, up to +26.43 points).
  - Step 1e (912 MHz, 5 us): 1 of 5 valid hysteresis runs over the ripple bound; Step 1f (6 us): 1 of 6 (+24.89
    points).
- Step 2: the window comparison is NaN in every run (no current in the summary window after the overshoot); the step
  response is the comparison. 2 of 13 dynamic runs gave "no matched SIL scenario" (open, not reproduced).
- Step 5 (internal current sensing): not run, no DACs.
- Streamed captures longer than the 8192-sample ring (49 ms at 6 us) do not work: the host falls behind 166.7 k
  samples/s, so the ring fills or a frame is lost (Step 1f). Buffered captures work.
- Capture packet loss: 3 of 58 re-run captures invalid by a sequence gap (6 of 33 in Step 1; it comes in bursts; its
  side is still open).
- Warnings, not failures: pwm_current's step max is 84-86 % of the 6 us step in every run, above the 80 % warning
  line; tsf reached it in 1 of 11 runs.
