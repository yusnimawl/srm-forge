# R8b — Control HIL — Design Spec

Status: implemented and bench-accepted on branch `r8b-hil-spec` (2026-10-24), not merged; versions not bumped. The body describes the system as built; §16 lists the decisions made during implementation, with dates, and the results are in `docs/r8b-hil-results.md`.
Roadmap: `2026-10-12-roadmap-r1-r10-design.md` §3 R8. R8a (PC SIL) is `2026-10-19-r8a-control-sil-design.md`; R8b builds on it. Wiring: `docs/r8b-hil-wiring.md`. Converter background: the topology study in the session notes (summary in §2 D3).

## 1. Goal

The owner's controller C runs unchanged on a real MCU (Nucleo-H723ZG) with real timers, ADC sampling and ISR timing, against a second board (Teensy 4.1) that emulates the SRM drive in real time from an evaluated case. The owner can tune the controller live, capture full-rate waveforms, and compare the hardware run with the SIL.

Done when (§12): the emulator model matches the SIL within 1 % on CI; each reference controller on the Nucleo spins the emulated 8/6 and matches the matched SIL within 3 % (mean torque, RMS current) and ±5 points (median ripple % over complete strokes); the speed loop follows a step; a live parameter change and a capture show in the Control tab; every run reports its timing health.

## 2. Decisions (owner, 2026-10-20)

| # | Decision |
|---|---|
| D1 | Controller board: Nucleo-H723ZG. Its STM32 driver fills `srm_hal_t`. |
| D2 | Emulator: Teensy 4.1 alone (no FPGA), 912 MHz. 6 µs step with timestamped gate edges: each step uses the exact on-time of every switch. |
| D3 | Converter: asymmetric half-bridge (AHB) only, as in R8a. The topology study ranked AHB first for a 4-phase 8/6 (+V/0/−V per phase, independent phases in overlap, matches `set_switches(phase, upper, lower)`); 1.5q, boost-capacitor and Miller variants are not in R8b. |
| D4 | Current sensing has two modes, chosen at build time: `ad7606` (the Teensy emulates an AD7606 over SPI: 8 simultaneous channels = 4 phase currents + 4 phase voltages; no extra parts) and `internal` (DACs drive the Nucleo's own ADC pins). DACs: 2 × MCP4922 or 4 × MCP4921, chosen at build time. |
| D5 | Position has three modes: `encoder` (A/B/Z), `ad2s1210` (the Teensy emulates an AD2S1210 resolver-to-digital converter over SPI), `both`. A carrier-modulated analog resolver is out of scope. |
| D6 | All modes are wired at once (`docs/r8b-hil-wiring.md`); switching mode is a rebuild, never a rewire. |
| D7 | Toolchain: PlatformIO for both boards (`nucleo_h723zg` with STM32Cube, `teensy41`), pinned in `hil/platformio.ini`. |
| D8 | Results: hybrid. Live numbers at about 20 Hz, live parameter changes, and full-rate captures on demand streamed over the Teensy's high-speed USB. No PSRAM (the owner has none); captures that fit the 8192-sample RAM ring (49 ms) are buffered in full; longer ones would stream, which does not keep up (§8, §16). |
| D9 | PC links use COBS framing with CRC-16 (not CAN framing). Board-to-board signals follow the emulated chips' datasheets; there is no board-to-board protocol of ours. |
| D10 | Tolerances: emulator model vs SIL 1 % (CI); HIL vs matched SIL 3 % on mean torque and RMS current, ±5 points on the median per-stroke ripple % (bench). |
| D11 | The Nucleo driver is product-grade: it is the base of the owner's future motor controller board (§14). |
| D12 | The Tang Nano 9K is an optional bench logic analyser in R8b and the candidate board for an FPGA emulator later (R8c). |

## 3. Out of scope

FPGA emulator (R8c); CAN vehicle/ECU interface (§14); carrier-modulated analog resolver; real inverter or power stage; converter topologies other than AHB; mutual coupling between phases (as R8a); emulated chip features the driver does not use (AD7606 oversampling pins, AD2S1210 fault thresholds and excitation settings beyond accepting the writes).

## 4. Architecture and layout

```
 PC  (srmweb / Python srmsil.hil)
   │ Teensy USB (480 Mbit): config, tables, live numbers, captures
   │ ST-LINK USB serial: flash, parameters, commands, ISR statistics
   ▼                              ▼
 Teensy 4.1  motor emulator   ◄── 8 gates ────  Nucleo-H723ZG  controller
   plant C, 6 µs step          ── enc A/B/Z ──►   owner controller C (unchanged)
   gate-edge timestamps        ── AD7606 SPI ─►   srm_hal_stm32.c fills srm_hal_t
   AD7606 / AD2S1210 slaves    ── AD2S1210 SPI►
   DACs (internal mode)        ── analog ×4 ──►
                               ◄── RUN ─────────
                               ── READY ───────►
```

```
src/srmsil/c/
  srm_hal.h              + phase-voltage ADC fields (§7)
  srm_ctrl.h             ctrl_param callable any time (§7)
  plant/                 the model shared by the PC SIL and the emulator (§5.3)
  sim/                   PC scheduler, HAL, traces, ctypes entry points (uses plant/)
hil/
  platformio.ini         envs: emulator (teensy41), controller (nucleo_h723zg)
  common/                hil_proto.h (packets, COBS, CRC-16), shared by firmware and the Python tests
  emulator/              step loop, gate capture, AD7606/AD2S1210 slaves, DAC, encoder, USB
  controller/            srm_hal_stm32.c, AD7606 and AD2S1210 drivers, ISR scheduling, serial
  scripts/               PlatformIO extra script that adds the owner folder and the generated headers
src/srmsil/hil/          Python: build and flash, board discovery, protocols, run, compare, live session
```

Layering as R8a: `srmsil` imports `srmapp`/`srmcore`, never `srmweb`; firmware never imports Python. `hil/` is not a Python package.

## 5. Emulator (Teensy 4.1)

### 5.1 Step loop
A 166.7 kHz timer interrupt (priority below the gate, CONVST and encoder interrupts, above USB; NVIC levels: gates 0, CONVST 16, encoder 32, step 48). Step n covers [t_n, t_n + dt], dt = 6 µs (`HIL_EMU_STEP_NS` in `hil/common/hil_proto.h`, mirrored as `proto.EMU_STEP_NS` and `EMU_DT`; every step-derived constant follows it), and runs just after that interval ends. The core runs at 912 MHz (`board_build.f_cpu`; the Teensy needs a heatsink, and a run stops above 85 °C, reported as `temp_c` in the live statistics). At every START the emulator runs a self-check of the gate averager (`ga_selfcheck.c`, a hash over 4000 fixed windows) and refuses to start on a different result. Steps:
1. Take the gate edges stamped inside the interval (§5.2) and form each switch's on-fraction and the ordered segments.
2. Call the plant step (§5.3) with the segment-averaged converter voltage.
3. Present the outputs: AD7606 sample registers, DAC words (SPI with DMA, then LDAC), encoder schedule (§5.8), AD2S1210 registers.
4. Push one packed sample to the capture ring and update the live statistics.

The outputs therefore lag the gates by one step plus the compute and transfer time. That latency (last gate edge of a step's window to the end of that step's output stage) is measured on the board and reported; the matched SIL (§11) uses it.

### 5.2 Gate edges and averaging
The 8 gate inputs (Teensy 14–21) are on GPIO1 bits 16–27, so one combined interrupt serves them. It runs at the highest priority, reads the port and the ARM cycle counter (1.67 ns), and pushes (time, 8-bit gate word) into a ring. Edge jitter is about 50–100 ns; it is measured against a known Nucleo pattern and reported.

Per phase, the interval splits into segments of constant (upper, lower). The converter's turn-on delay, turn-off delay and dead time (R8a `ConverterSettings`) shift the stamped edges exactly as the SIL does. The step's phase voltage is the duration-weighted mean of the AHB voltage of each segment (both on: V_dc − 2·V_sw; one on: −(V_sw + V_d); both off with i > 0: −(V_dc + 2·V_d); both off with i = 0: 0), evaluated segment by segment on a running flux that starts from the step's flux and is clamped at zero per segment, so a current that reaches zero inside the step ends the diode conduction there; the averager returns v = (ψ_end − ψ_start) / dt.

### 5.3 Shared plant
`srm_sim.c` is split. `plant/` holds the state (ψ_k, θ, ω), `srm_plant_step(state, v_avg[], dt, load)` (the Heun step, table lookup, mechanics and the ψ ≥ 0 clamp now inside `srm_sim_run`), the AHB voltage function, and the sensor models. `sim/srm_sim.c` keeps the scheduler, HAL, gate queue and traces and calls the plant. The split must leave every existing `tests/sil` result unchanged.

The table element type is one compile-time type, `srm_table_t`: `double` on the PC, `float` on the emulator. In the emulator build the plant state, the plant step and the gate averager also use `float` (`srm_real_t`; the rotor angle and the time stay `double`); the PC builds stay `double`. The emulator's tables are uploaded at session start into fixed DTCM arrays (default grid 180 θ × 192 ψ for i(θ,ψ) and T(θ,ψ), about 270 KB); the field-energy table is not used on the emulator. The emulator firmware does not depend on the case, so changing case does not reflash it.

The SIL's static gate queue (65536 entries) stays in the PC scheduler only; the emulator has no queue (real gates arrive as edges).

Current pulses shorter than about two steps (for example low-current hard chopping in discontinuous conduction) are resolved only at the step instants, so the emulator sees them only at the step instants (12 µs). At 6 µs and a 20 kHz carrier (8 1/3 steps per period) the instants sweep the carrier phase and the full-rate RMS of such pulses reads about 0.2 % low; a carrier period that is a whole number of steps (16.67 kHz at 6 µs) brings back a 1 to 2 % low reading. The FPGA emulator (R8c) lifts this.

### 5.4 Modes and the safety interlock
At connect the PC reads each board's build info (protocol version, firmware hash, `current_sense`, `position`, `dac`) and refuses a session when the modes differ. The Teensy drives the shared SCK wire (DAC mode) only while RUN is high, and the Nucleo raises RUN only after it has set PA5 to an input; a 330 Ω series resistor on that wire is the backstop. RUN low stops the emulator: BUSY goes low and the encoder holds; the DACs hold their last code, because the Teensy may not drive the shared wires while RUN is low (a stop while RUN is still high writes the zero-current code). READY low (emulator fault, overrun, stop) makes the Nucleo turn every gate off and report it.

### 5.5 AD7606 emulation (`current_sense = ad7606`)
Serial interface on LPSPI4 as a slave (Teensy 10 CS, 13 SCK, 11 DOUTA). CONVST rising edge (Teensy 5, interrupt) latches the latest step's 8 channel values into the SPI transmit FIFO and raises BUSY (Teensy 6) for t_conv (setting, default the datasheet's conversion time) before releasing it. Channels V1–V4 carry the phase currents (sensor gain in V/A), V5–V8 the phase voltages through a divider ratio and a first-order filter (τ setting, default 10 µs). Coding is 16-bit two's complement over the ±5 V or ±10 V range (setting), clipped at the range. The SPI clock is 12.5 MHz by default (bench: reliable to 25 MHz, §15). BUSY is driven in hardware: CONVST is routed through XBAR1 to QTIMER4, whose output is BUSY (a one-shot of `t_conv`, 1 to 1000 µs enforced), and the CONVST interrupt only loads the frame.

### 5.6 AD2S1210 emulation (`position = ad2s1210`)
Serial interface on LPSPI3 as a slave (Teensy 0 WR/FSYNC, 27 SCLK, 1 SDI, 26 SDO); SAMPLE (Teensy 9) and A0/A1 (22/23) are interrupt inputs. A SAMPLE edge latches position and velocity. A0/A1 select position, velocity or configuration as on the chip; position is the electrical angle (pole pairs from `SensorSettings.resolver_pole_pairs`) at the configured resolution (10–16 bits), velocity is two's complement, the fault register reads 0. Configuration writes are accepted; only the resolution is used. The R8a resolver errors (gain mismatch, phase error) enter as the angle error of atan2 of the imperfect sin/cos.

The HAL keeps `resolver_sincos`: the Nucleo driver returns sin and cos counts computed from the RDC angle, so controllers do not change.

### 5.7 DACs (`current_sense = internal`)
LPSPI4 as a master on the same SCK and data wires, chip selects on Teensy 24/25 (+28/29 for 4 × MCP4921), shared LDAC on 30, so all channels change together. Sensor model V = V_mid + k·i with 0 A at 0.2 V and full scale at 1.2 × the map's top current; the Nucleo HAL gets the matching `adc_amps_per_count` and offset. DAC references tie to one 3.3 V node. No artificial noise is added in either mode; the real converters bring their own.

### 5.8 Encoder
A/B/Z on Teensy 2/3/4. Each step computes the counts crossed between θ(t_n) and θ(t_n + dt) and schedules their edges at the interpolated times on an output-compare timer. CPR, offset and eccentricity follow the R8a `SensorSettings`. Each count is one A or B edge (a timer in x4 encoder mode reads the SIL count), so the edge rate is CPR·rev/s; it must stay at or below 400 k/s; the config check rejects faster settings.

### 5.9 Mechanics and health
Fixed speed or dynamic (J, B, load plus a step), as R8a. Every run reports the step time (mean, max), overruns, edge jitter, dropped capture packets and the measured output latency. Any overrun or dropped packet marks the run `valid = false`; a step max over 80 % of dt is a warning only: it does not invalidate the run and is shown in the live numbers and the capture health. Acceptance needs zero overruns.

## 6. Controller driver (Nucleo-H723ZG)

`hil/controller/srm_hal_stm32.c` fills `srm_hal_t`:
- **Gates:** TIM1 CH1–CH4 = upper A–D, TIM8 CH1–CH4 = lower A–D (independent channels, not CHxN), synchronised, centre-aligned at `pwm_hz`, dead time off (AHB has no shoot-through). `set_pwm` sets hard or soft chopping through the compare values; `set_switches` forces the outputs. Both are preloaded and take effect at the next period, as on a real drive.
- **Sampling:** the carrier centre triggers the conversion; `isr_hz` must be `pwm_hz / k` with k odd (1..127), so the sample instant is the carrier centre (refused in `write_hil_config` before the build, and by the firmware). The hysteresis reference set runs with `pwm_hz = isr_hz`. `internal`: ADC1 + ADC2 in dual mode with DMA (pins PA3, PB1, PC0, PA4). `ad7606`: CONVST pulse, BUSY interrupt, SPI1 DMA read of the 8 channels. `ctrl_isr()` runs when the data are in.
- **Position:** `encoder`: TIM4 in encoder mode, Z on an EXTI; `ad2s1210`: SAMPLE pulse and SPI3 read.
- **Time:** `micros()` from a 32-bit timer; `ctrl_slow()` from a 1 kHz timer interrupt below the ISR.
- **Bus voltage:** `vbus_volts()` returns the configured value.
- **Measurements:** ISR execution time from the DWT cycle counter, ISR overruns (an ISR still running at the next trigger). An overrun marks the run invalid. A `ctrl_isr` that does not return is abandoned and the run stops. The emulator measures the controller's sample-trigger rate (CONVST rising or SAMPLE falling, stamped on the Teensy's crystal), so the PC knows the controller's true clock; with `current_sense = internal` and `position = encoder` there is no trigger wire, the ratio is unknown and 1.0 is used (`clock_measured` is false).
- **Serial (ST-LINK VCP):** parameters at any time (§7), commands, live statistics (ISR time, overruns, the controller's command and measured values) at about 20 Hz.

Owner code, the case's `srm_motor_tables.h` and a generated `hil_config.h` (modes, `pwm_hz`, `isr_hz`, scales) are added by the PlatformIO extra script. The controller firmware depends on the case, as a product build would.

## 7. Contract and HAL changes (shared with the SIL)

- `ctrl_param(name, value)` may be called at any time. Return 0 accepted, −1 unknown name, −2 known but not changeable while running. The reference controllers accept their angles, gains and limits live; the SIL keeps calling it before `ctrl_init` as today.
- `srm_hal_t` gains, at the end, `float adc_volts_per_count` and `int32_t adc_volt_offset_counts`. `adc_read(channel)` channels 0..q−1 are phase currents (as now) and q..2q−1 phase voltages; `adc_volts_per_count = 0` means no voltage channels. The SIL provides them through the shared voltage-sensor model (§5.5 filter).
- AD7606 two's complement codes reach the controller as unsigned codes with `adc_offset_counts = 32768`, so the current convention is unchanged.

## 8. PC protocol

Both links carry COBS-framed packets: type (u8), sequence (u16), payload, CRC-16/CCITT. `hil/common/hil_proto.h` defines the types and payloads; Python reads the same definitions (a test checks C and Python against shared vectors). Packet groups: hello/build info, config and table upload (emulator), parameter set and reply (controller), command, start/stop, live statistics, capture header, capture samples, capture end, error.

Capture samples are packed per step (int16 currents, fluxes and voltages, int16 torque, u16 angle, int16 speed, u8 gate word; scales in the capture header), a sample is 36 bytes, about 6 MB/s at 6 µs. Captures that fit the RAM ring (RAM2, 8192 samples = 49.152 ms) are buffered in full and then sent; this is the supported mode and the default capture length. Longer captures stream while running, which does not keep up (the ring fills or a frame is lost; known limit, §16). A sequence gap marks the capture invalid; it is never filled. The capture's speed scale covers the run's speed range, and the host refuses a capture whose header dt is not `EMU_DT`.

## 9. Python (`srmsil.hil`)

- `build_and_flash(controller, case, modes, *, cache_dir)`: writes the case header and `hil_config.h`, runs `pio run -e controller -e emulator -t upload` with the mode flags, caches builds by source hash (the hash covers `hil/`, the `.c` and `.h` files of the plant and the controller folders, the generated headers and the modes), returns the log and the firmware hash. `firmware_hash` recomputes it from the current sources, and `check_sources` refuses a session or run whose sources changed since the flash. A missing PlatformIO or board gives a clear error that names it.
- Board discovery by USB VID/PID (Teensy 0x16C0; ST-LINK 0x0483), so COM numbers are never configured.
- `HilSession`: connect and check modes, upload tables and config, start/stop, set parameters, command, live statistics, capture. `configure` resets the controller board (parameters of an earlier session return to the build's defaults) and refuses a scenario that sets what the HIL does not emulate: `param_steps`, `adc.offset_error`, `adc.gain_error`, `adc.noise`, `adc.rc_tau`, `sensors.delay`, `sensors.delay_jitter` (the sensed-value delay, its jitter and the ADC are those of the rig). A session also refuses boards that run another build than the flashed one (`check_build`; the hashes are read from both boards before and after a run). `run_hil(...)` scripts a fixed run and returns a `SimResult` like the SIL's plus a `hil` block (health numbers of §5.9 and §6, `valid`).
- `matched_scenario` and `compare(hil, sil, *, m, t0)`: the matched SIL (§11) and the differences in mean torque, RMS current and ripple against D10, over the HIL capture's window. The ripple compared is the median over the complete strokes of each side (`stroke_ripples`; a stroke is one torque period of rotor angle; fewer than 3 on either side fails); the whole-window ripples are kept as information. The comparison fails (`passed = False`, with a reason) for an invalid HIL run, a capture with clipped current samples, a SIL that does not cover the window, and, in a live session, parameters or a command changed within `SETTLE_S` before the capture (fixed speed) or while running (dynamic). `match_plan` builds the SIL of a live capture: at fixed speed it starts `SETTLE_S` (0.2 s) before the capture at the rotor angle the HIL had then, in dynamic mode at Start.
- `srmsil.hil.fake`: a fake rig (two transports that answer like the firmware, captures from a SIL run) for tests and the web layer.

New optional extra `hil` = `pyserial` (pinned); `srmsil.hil` imports it lazily, so a missing package fails only when a session opens. PlatformIO runs from its own environment `hil/.runtime` (git-ignored), created by `hil/setup.bat` or `hil/setup.sh`, as `bench/` does; the shared `.venv` is never changed by the implementation sessions.

## 10. Web

- One live session at a time (one rig), loopback host only (it flashes boards and drives local USB), enforced at the routes and in the session.
- Build & Flash is a job of kind `hil_flash` on the main lane (steps queued, build, flash, saved). The live session is not a job: `POST /api/hil/session` opens it, `GET /api/hil/session/events` (SSE, as the job events) carries live statistics, `POST /api/hil/session/param|command|start|stop|capture` act on it, `DELETE` closes it. Captures are npz in `<cache_dir>/sil/hil/`, counted and cleared with the cache. `POST /api/cases/{id}/hil/flash` starts the flash job and `GET /api/jobs/{id}/hil-flash` returns its log and firmware hash; `GET /api/hil/captures/{id}` returns the decimated traces (with the matched SIL overlaid once compared) and `GET /api/hil/captures/{id}/compare` the comparison.
- **Control tab:** a SIL / HIL switch. HIL mode shows the mode selectors, Build & Flash with its log, board status, Start/Stop, live numbers, parameter controls that apply live, Capture, scopes that overlay the HIL capture on the matched SIL run, and the comparison pass/fail with the health numbers. Graphite theme, no blue, `plotTheme`.

## 11. SIL changes

- The plant split (§5.3), with unchanged results.
- `SensorSettings.delay` (s, default 0) and `delay_jitter` (s, default 0): a transport delay on the sensed currents and voltages; with a jitter each ISR sample's age is drawn uniformly from [delay, delay + delay_jitter] (the run's seeded sensor RNG; 0 is bit-identical to a run without it). The matched SIL uses delay = measured latency - dt/2 and delay_jitter = dt, because the HIL latches the emulator's output at a random instant within a step.
- `Scenario.controller_clock` (default 1.0): the controller's clock over true time. It scales the controller's real ISR, PWM, slow-loop and `micros()` timing while the HAL constants stay nominal. The matched SIL sets it to the measured ratio (about 1.010 on the Nucleo, whose HSE comes from the ST-LINK MCO).
- Matched timing: the controller samples at the trigger (the SIL's ISR instant), and conversion and SPI only delay the start of `ctrl_isr`; the preloaded compares load at the next underflow, so `compute_delay` is one ISR period of the controller's clock in true time (`1 / (isr_hz * r)`). Matched ADC: the HIL chain's (`config.hil_adc`: 16 bit, full scale, offset and amps per count of the AD7606 chain, clipping at the range).
- Voltage channels in the HAL (§7) through the shared sensor model.
- `ctrl_param` −2 handling in `run.py` (reported, not an error before init).
- An emulator-model build of the plant for the PC: float tables at the emulator grid, a 6 µs step, gates fed as stamped edges and averaged as in §5.2 (`srmsil.emumodel`, `c/emu/srm_emu.c`). It is the CI stand-in for the Teensy model.

## 12. Verification

CI (no hardware):
1. Existing `tests/sil` pass unchanged after the plant split.
2. Emulator model vs SIL: open-loop pulse at fixed speed, float tables at the emulator grid, 6 µs step, averaged gates, against the 0.5 µs double SIL: mean torque within 1 %, RMS current within 1 %.
3. Gate averaging: known edge patterns (several edges in one step, an edge on a step boundary, a zero-current crossing inside a step) give the exact volt-seconds.
4. Protocol: COBS and CRC round trips; a corrupt packet and a sequence gap are detected; C and Python agree on shared vectors.
5. Emulated chip coding: AD7606 range and two's complement, AD2S1210 position and velocity scaling, against datasheet examples.
6. `SensorSettings.delay` delays the ADC trace by the set time; `ctrl_param` −2 path.
7. Firmware compiles for both environments in every mode (a CI job that runs when `hil/**` or `src/srmsil/c/**` changes).
8. Web: route and session tests with a fake board transport, the loopback rule, capture storage; vitest for the HIL panel; `noBlue`.

Bench (manual, recorded in `docs/r8b-hil-results.md`):
1. Health: zero overruns and dropped packets; step time, edge jitter, latency and ISR times reported (a step max over 80 % of dt is a warning, §5.9).
2. Each reference controller (hysteresis, PWM current, TSF) spins an evaluated 8/6 case at fixed speed: HIL vs matched SIL within 3 % (mean torque, RMS current) and ±5 points (median per-stroke ripple %), in `ad7606` mode, and in `internal` mode once DACs are fitted.
3. Dynamic mode: the speed loop follows a speed step.
4. A live θ_on change moves the live numbers; a capture shows in the Control tab.
5. `ad2s1210` mode: the angle the controller reads matches the true angle within the set resolver errors.

## 13. Versions and dependencies

srmsil, srmweb and `web/` take the next minor version at merge, after R3c; the number is agreed with the coordinating session at merge time (not bumped on the branch). srmcore is unchanged. The openapi schema is regenerated. Firmware carries `HIL_PROTOCOL_VERSION`, checked at connect. New dependencies: extra `hil` = `pyserial`; PlatformIO in `hil/.runtime` (§9).

## 14. Future use

- The Nucleo driver (`srm_hal_stm32.c`, the AD7606 and AD2S1210 drivers, the TIM1/TIM8 AHB PWM) is written to product standard and is the starting point for the owner's motor controller board.
- A CAN command interface (ISO 11898, 11-bit identifiers; J1939 only if a vehicle network requires it) for vehicle/ECU communication is a planned follow-up. The H723 has FDCAN and the Teensy 4.1 has CAN, so the same rig can test it, with the PC or the Teensy as the host ECU.
- R8c: an FPGA emulator (Tang Nano 9K) for PWM above about 40 kHz or detail inside one PWM period, on the same pins.

## 15. Bench items to confirm before relying on them

From the wiring check (`docs/r8b-hil-wiring.md` §5): LPSPI4 SDO tri-state when CS is high (OUTCFG) on the i.MX RT1062; the board's MB1364 revision and default solder bridges; the Teensy GND pads; the pin-13 LED load on SCK at the chosen SPI clock; the Teensy LPSPI slave's maximum reliable clock. The first implementation task on hardware checks these and records the results. The wired-bench results are in `docs/r8b-hil-results.md`: the AD7606 SPI is reliable to 25 MHz (default 12.5 MHz, replacing the 10–15 MHz target of §5.5) and the AD2S1210 SPI3 to 50 MHz (default 12.5 MHz).

## 16. Decisions made during implementation

Owner decisions and rulings that changed the design after the 2026-10-20 draft; the body above states the result. Evidence is in `docs/r8b-hil-results.md` (step names in parentheses).

Emulator
- **Float plant on the emulator** (owner, 2026-10-21): the plant step and the gate averager use `float` in the emulator build only; the PC SIL stays `double`. With a double-precision step at 600 MHz the two-phase maximum was 6.16 µs with overruns; the CI model check against the SIL is unchanged at 1 % (0.03 % torque).
- **Gate averaging follows the flux** (ruling, 2026-10-21): the averager walks the segments in order on a running flux and clamps it at zero per segment, instead of using the start-of-step current. A hard-chopped discontinuous-conduction pulse of about 6 µs was undersampled at 5 µs and cancelled a later on-segment's volt-seconds. Pulses shorter than about two steps are a resolution limit (§5.3); the CI checks the model against the SIL sampled at the same instants.
- **Teensy clock 912 MHz** (owner, 2026-10-23; the clock had been set to 816 MHz and then 1008 MHz on 2026-10-21): the gate-averager self-check refused 15 of 43 STARTs at 1008 MHz with a wrong hash, and a START took bus faults. Root cause: marginal silicon at 1008 MHz with the core DCDC already at its 1575 mV maximum (wrong results only at 1008 MHz, gone at 912 and 816 MHz, back at 912 MHz with the voltage lowered to 1425 mV; interrupts, lazy FP stacking, stack contents, caches and DMA were ruled out). The earlier finding of a GCC -O3 miscompile of the inlined averager is withdrawn and `noinline` was dropped (inlined code is 3.3 % faster). Evidence: Step 1d, Step 1e. A 150-START soak at 912 MHz had no refusals or faults.
- **Emulator step 6 µs, was 5 µs** (owner's fallback, 2026-10-23): at 912 MHz pwm_current had 0.04 to 0.15 µs of headroom in a 5 µs step and overran when streaming. `HIL_EMU_STEP_NS` is one constant; the step max did not change in absolute terms (4.85 to 5.04 µs) and the headroom is now about 1 µs. The 1 % model check holds (torque 0.044 %, RMS current 0.011 to 0.015 %). Capture times are step × `EMU_DT` (the float32 header dt broke compares), and the host refuses a header dt that is not its step. Step 1f.
- **AD7606 BUSY in hardware** (owner, 2026-10-23): CONVST → XBAR1 → QTIMER4 produces BUSY, and the CONVST interrupt (NVIC level 16, below the gates) only loads the frame in about 139 cycles. eDMA worked on the wire but any eDMA use made the step's PIT read fault and reboot the Teensy, so it was dropped. This removed the start-up overrun of pwm_current at 5 µs. `ad7606_t_conv_us` outside 1 to 1000 µs is refused. Step 1c.
- **RAM capture ring 8192 samples** (ruling, 2026-10-21): 16384 samples of 36 bytes exceed the 512 KB RAM2, so the buffered window is 8192 samples (41 ms at 5 µs, 49 ms at 6 µs).
- **DAC outputs hold their last code while RUN is low** (ruling, 2026-10-21): the Teensy may not drive the shared SCK and data wires then (§5.4); a stop while RUN is still high writes the zero-current code.
- **Encoder edge-rate limit CPR × rev/s ≤ 400 000** (ruling, 2026-10-21): each count is one A or B edge (a timer in x4 mode reads the SIL count), not four edges per count; the config check rejects faster settings.
- **The emulator measures the controller's sample-trigger rate** (owner decision on the clock, 2026-10-22; ruling, 2026-10-22): the Nucleo's HSE comes from the ST-LINK MCO and ran 1.0 to 1.4 % fast, drifting from day to day. Every run measures the trigger rate (first and last CONVST or SAMPLE edge of the live windows) on the Teensy's crystal, exact to about 1e-6. It is unavailable with `internal` current sensing and `encoder` position (no trigger wire); the comparison then uses 1.0 and reports `clock_measured` false. The final board gets an HSE crystal.
- **Step time over 80 % of dt is a warning only** (owner, 2026-10-23; §12 bench item 1 reworded to match §5.9): shown in the live numbers and the capture health; acceptance needs zero overruns. pwm_current runs at 81 to 86 % of the 6 µs step.
- **Self-check of the gate averager at every START** (ruling, 2026-10-23): the check runs on the same machine code as the step and refuses with `HIL_ERROR` on a different hash. It guards real runs, not the boot (the boot-time hash varied once, partly unexplained; Step 1b).

Controller board and contract
- **`isr_hz = pwm_hz / k`, k odd** (ruling, 2026-10-22): only then is the sample instant the carrier centre, as in the SIL. Refused in `write_hil_config` and in the firmware; the SIL's sample instant is unchanged. The hysteresis reference runs with `pwm_hz = isr_hz`.
- **A `ctrl_isr` that does not return is abandoned and the run stops** (review fix, 2026-10-22), by unwinding from the timer interrupt.
- **`ctrl_slow` first runs one period after RUN rises**, as in the SIL, and the controller board is reset when a session is configured, so parameters from an earlier session cannot differ from the matched SIL (2026-10-23).
- **Live parameter refusal in the SIL**: a `param_steps` entry the controller refuses (`ctrl_param` ≠ 0) raises `ValueError` naming the parameter and the code (2026-10-21).

Matched SIL and comparison
- **Matched timing replaces the sense-latency formula of the draft §9 and §11** (ruling, 2026-10-22): the AD7606/RDC sample is taken at the trigger, the SIL's ISR instant; conversion and SPI only delay the ISR start, and the preloaded compares load at the next underflow. So `compute_delay` is one true ISR period (`1 / (isr_hz × r)`, r the measured clock ratio), and the sensed-value age is `sensors.delay = latency − dt/2` with `sensors.delay_jitter = dt` (owner, 2026-10-23: the HIL latches the emulator's output at a uniform age in [D, D + dt] and a chop near its threshold depends on where in that range the sample falls). The measured latency is the mean, D + dt/2. `sense_latency` was dropped: the draft formula would have made the SIL's data about 14 µs older than the HIL's.
- **`Scenario.controller_clock`** (ruling, 2026-10-22): the controller's clock over true time scales its real ISR, PWM, slow-loop and `micros()` timing while the HAL constants stay nominal, so the SIL can use the measured clock. Default 1.0 is bit-identical.
- **Matched SIL ADC = the HIL chain's** (ruling, 2026-10-22): the controller sees the same HAL constants, code range and clipping.
- **Fields the HIL refuses** (ruling, 2026-10-22): `adc.offset_error`, `adc.gain_error`, `adc.noise`, `adc.rc_tau`, `sensors.delay`, `sensors.delay_jitter` and `param_steps` (HilError or ValueError naming them before anything is sent); explicit beats silently ignored.
- **A capture with clipped current samples stays valid but cannot pass** (ruling, 2026-10-22): `passed` is false with the reason "capture clipped"; an RMS of clipped currents is not comparable.
- **Live-capture matched SIL** (rulings, 2026-10-22 and 2026-10-23): at fixed speed it starts `SETTLE_S` (0.2 s) before the capture window at the rotor angle the HIL then had, so any capture time works; in dynamic mode it starts at Start. Both summaries use the same absolute window (the second half of the captured steps). Parameter or command changes are tracked by their host time; a change after the SIL's start (fixed) or any change while running (dynamic) gives `passed` false with the reason, never a SIL that replays the wrong history.
- **Ripple is compared as the median over strokes** (owner, 2026-10-23): hysteresis chops at a threshold, so the whole-window ripple is bimodal (about 78 % or 104 %) on both sides once the age jitter is modelled. The compared value is the median per-stroke ripple over the complete strokes of the window (at least 3 each side); the whole-window ripples are kept as information. The 5-point bound is unchanged. The default capture is the whole ring (49 ms, about 9.8 strokes at 8/6 and 1000 rpm).
- **Build identity check** (2026-10-24): a session or run is refused when a board reports another firmware hash than the flashed one (`check_build`, read before and after every run), and when the sources changed since the flash (`check_sources` recomputes the hash). The web session opens only after srmweb's own Build & Flash of that case and controller.
- **Web HIL panel**: parameters send on blur or Enter (a half-typed number must not reach the controller); custom controllers get free-form name = value rows; the command is live; the flash log has a route of its own (`GET /api/jobs/{id}/hil-flash`, 2026-10-23).

Known limits and open items
- **Full-rate streaming does not work** (ruling, 2026-10-23): at 912 MHz and 6 µs a capture longer than the 8192-sample ring ends with the ring full or a lost frame (the host falls behind 166.7 k samples/s); buffered captures of up to 49 ms are the supported mode. A follow-up session could compare the host reader with the Teensy's USB transmit budget.
- **Capture packet gaps**: 3 of 58 buffered captures in the final re-run (6 of 33 earlier) had a 1 to 2 packet gap while the emulator reported none dropped; the host marks them invalid (about 3 % of runs need a repeat). Cause open, and not shown to be on the host or the Teensy side.
- **`internal` current sensing was not benched** (no DACs fitted): CI compiles it in every mode, but the DAC outputs, the 0.2 V zero-current offset and the Nucleo ADC path have no bench result, and with the encoder it has no trigger wire for the clock measurement.
- **Other packages**: srmcore is unchanged; srmapp gains only `case.map_key` (the map's provenance hash, used by the `control_hil` example's motor cache); `web/openapi.json` and `web/src/api/schema.ts` are regenerated.
