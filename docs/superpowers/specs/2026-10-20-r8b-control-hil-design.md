# R8b — Control HIL — Design Spec

Status: draft for owner review (2026-10-20).
Roadmap: `2026-10-12-roadmap-r1-r10-design.md` §3 R8. R8a (PC SIL) is `2026-10-19-r8a-control-sil-design.md`; R8b builds on it. Wiring: `docs/r8b-hil-wiring.md`. Converter background: the topology study in the session notes (summary in §2 D3).

## 1. Goal

The owner's controller C runs unchanged on a real MCU (Nucleo-H723ZG) with real timers, ADC sampling and ISR timing, against a second board (Teensy 4.1) that emulates the SRM drive in real time from an evaluated case. The owner can tune the controller live, capture full-rate waveforms, and compare the hardware run with the SIL.

Done when (§12): the emulator model matches the SIL within 1 % on CI; each reference controller on the Nucleo spins the emulated 8/6 and matches the matched-delay SIL within 3 % (mean torque, RMS current) and ±5 points (ripple %); the speed loop follows a step; a live parameter change and a capture show in the Control tab; every run reports its timing health.

## 2. Decisions (owner, 2026-10-20)

| # | Decision |
|---|---|
| D1 | Controller board: Nucleo-H723ZG. Its STM32 driver fills `srm_hal_t`. |
| D2 | Emulator: Teensy 4.1 alone (no FPGA). 5 µs step with timestamped gate edges: each step uses the exact on-time of every switch. |
| D3 | Converter: asymmetric half-bridge (AHB) only, as in R8a. The topology study ranked AHB first for a 4-phase 8/6 (+V/0/−V per phase, independent phases in overlap, matches `set_switches(phase, upper, lower)`); 1.5q, boost-capacitor and Miller variants are not in R8b. |
| D4 | Current sensing has two modes, chosen at build time: `ad7606` (the Teensy emulates an AD7606 over SPI: 8 simultaneous channels = 4 phase currents + 4 phase voltages; no extra parts) and `internal` (DACs drive the Nucleo's own ADC pins). DACs: 2 × MCP4922 or 4 × MCP4921, chosen at build time. |
| D5 | Position has three modes: `encoder` (A/B/Z), `ad2s1210` (the Teensy emulates an AD2S1210 resolver-to-digital converter over SPI), `both`. A carrier-modulated analog resolver is out of scope. |
| D6 | All modes are wired at once (`docs/r8b-hil-wiring.md`); switching mode is a rebuild, never a rewire. |
| D7 | Toolchain: PlatformIO for both boards (`nucleo_h723zg` with STM32Cube, `teensy41`), pinned in `hil/platformio.ini`. |
| D8 | Results: hybrid. Live numbers at about 20 Hz, live parameter changes, and full-rate captures on demand streamed over the Teensy's high-speed USB. No PSRAM (the owner has none); captures that fit in RAM are buffered in full, longer ones stream. |
| D9 | PC links use COBS framing with CRC-16 (not CAN framing). Board-to-board signals follow the emulated chips' datasheets; there is no board-to-board protocol of ours. |
| D10 | Tolerances: emulator model vs SIL 1 % (CI); HIL vs matched-delay SIL 3 % on mean torque and RMS current, ±5 points on ripple % (bench). |
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
   plant C, 5 µs step          ── enc A/B/Z ──►   owner controller C (unchanged)
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
A 200 kHz timer interrupt (priority below the gate and encoder interrupts, above USB). Step n covers [t_n, t_n + dt], dt = 5 µs, and runs just after that interval ends:
1. Take the gate edges stamped inside the interval (§5.2) and form each switch's on-fraction and the ordered segments.
2. Call the plant step (§5.3) with the segment-averaged converter voltage.
3. Present the outputs: AD7606 sample registers, DAC words (SPI with DMA, then LDAC), encoder schedule (§5.8), AD2S1210 registers.
4. Push one packed sample to the capture ring and update the live statistics.

The outputs therefore lag the gates by one step plus the compute and transfer time. That latency is measured on the board and reported; the matched SIL (§11) uses it.

### 5.2 Gate edges and averaging
The 8 gate inputs (Teensy 14–21) are on GPIO1 bits 16–27, so one combined interrupt serves them. It runs at the highest priority, reads the port and the ARM cycle counter (1.67 ns), and pushes (time, 8-bit gate word) into a ring. Edge jitter is about 50–100 ns; it is measured against a known Nucleo pattern and reported.

Per phase, the interval splits into segments of constant (upper, lower). The converter's turn-on delay, turn-off delay and dead time (R8a `ConverterSettings`) shift the stamped edges exactly as the SIL does. The step's phase voltage is the duration-weighted mean of the AHB voltage of each segment (both on: V_dc − 2·V_sw; one on: −(V_sw + V_d); both off with i > 0: −(V_dc + 2·V_d); both off with i = 0: 0), evaluated with the current at the start of the step. The plant's clamp ψ ≥ 0 handles a current that reaches zero inside the step, as in the SIL.

### 5.3 Shared plant
`srm_sim.c` is split. `plant/` holds the state (ψ_k, θ, ω), `srm_plant_step(state, v_avg[], dt, load)` (the Heun step, table lookup, mechanics and the ψ ≥ 0 clamp now inside `srm_sim_run`), the AHB voltage function, and the sensor models. `sim/srm_sim.c` keeps the scheduler, HAL, gate queue and traces and calls the plant. The split must leave every existing `tests/sil` result unchanged.

The table element type is one compile-time type, `srm_table_t`: `double` on the PC, `float` on the emulator. The emulator's tables are uploaded at session start into fixed DTCM arrays (default grid 180 θ × 192 ψ for i(θ,ψ) and T(θ,ψ), about 270 KB); the field-energy table is not used on the emulator. The emulator firmware does not depend on the case, so changing case does not reflash it.

The SIL's static gate queue (65536 entries) stays in the PC scheduler only; the emulator has no queue (real gates arrive as edges).

Current pulses shorter than about two steps (for example low-current hard chopping in discontinuous conduction) are resolved only at the step instants, so a full-rate RMS reads about 1 to 2 % low at 5 µs; the FPGA emulator (R8c) lifts this.

### 5.4 Modes and the safety interlock
At connect the PC reads each board's build info (protocol version, firmware hash, `current_sense`, `position`, `dac`) and refuses a session when the modes differ. The Teensy drives the shared SCK wire (DAC mode) only while RUN is high, and the Nucleo raises RUN only after it has set PA5 to an input; a 330 Ω series resistor on that wire is the backstop. RUN low stops the emulator: BUSY goes low and the encoder holds; the DACs hold their last code, because the Teensy may not drive the shared wires while RUN is low (a stop while RUN is still high writes the zero-current code). READY low (emulator fault, overrun, stop) makes the Nucleo turn every gate off and report it.

### 5.5 AD7606 emulation (`current_sense = ad7606`)
Serial interface on LPSPI4 as a slave (Teensy 10 CS, 13 SCK, 11 DOUTA). CONVST rising edge (Teensy 5, interrupt) latches the latest step's 8 channel values into the SPI transmit FIFO and raises BUSY (Teensy 6) for t_conv (setting, default the datasheet's conversion time) before releasing it. Channels V1–V4 carry the phase currents (sensor gain in V/A), V5–V8 the phase voltages through a divider ratio and a first-order filter (τ setting, default 10 µs). Coding is 16-bit two's complement over the ±5 V or ±10 V range (setting), clipped at the range. The SPI clock target is 10–15 MHz, confirmed on the bench (§15).

### 5.6 AD2S1210 emulation (`position = ad2s1210`)
Serial interface on LPSPI3 as a slave (Teensy 0 WR/FSYNC, 27 SCLK, 1 SDI, 26 SDO); SAMPLE (Teensy 9) and A0/A1 (22/23) are interrupt inputs. A SAMPLE edge latches position and velocity. A0/A1 select position, velocity or configuration as on the chip; position is the electrical angle (pole pairs from `SensorSettings.resolver_pole_pairs`) at the configured resolution (10–16 bits), velocity is two's complement, the fault register reads 0. Configuration writes are accepted; only the resolution is used. The R8a resolver errors (gain mismatch, phase error) enter as the angle error of atan2 of the imperfect sin/cos.

The HAL keeps `resolver_sincos`: the Nucleo driver returns sin and cos counts computed from the RDC angle, so controllers do not change.

### 5.7 DACs (`current_sense = internal`)
LPSPI4 as a master on the same SCK and data wires, chip selects on Teensy 24/25 (+28/29 for 4 × MCP4921), shared LDAC on 30, so all channels change together. Sensor model V = V_mid + k·i with 0 A at 0.2 V and full scale at 1.2 × the map's top current; the Nucleo HAL gets the matching `adc_amps_per_count` and offset. DAC references tie to one 3.3 V node. No artificial noise is added in either mode; the real converters bring their own.

### 5.8 Encoder
A/B/Z on Teensy 2/3/4. Each step computes the counts crossed between θ(t_n) and θ(t_n + dt) and schedules their edges at the interpolated times on an output-compare timer. CPR, offset and eccentricity follow the R8a `SensorSettings`. Each count is one A or B edge (a timer in x4 encoder mode reads the SIL count), so the edge rate is CPR·rev/s; it must stay at or below 400 k/s; the config check rejects faster settings.

### 5.9 Mechanics and health
Fixed speed or dynamic (J, B, load plus a step), as R8a. Every run reports the step time (mean, max), overruns, edge jitter, dropped capture packets and the measured output latency. Any overrun or dropped packet marks the run `valid = false`; a step over 80 % of dt is a warning.

## 6. Controller driver (Nucleo-H723ZG)

`hil/controller/srm_hal_stm32.c` fills `srm_hal_t`:
- **Gates:** TIM1 CH1–CH4 = upper A–D, TIM8 CH1–CH4 = lower A–D (independent channels, not CHxN), synchronised, centre-aligned at `pwm_hz`, dead time off (AHB has no shoot-through). `set_pwm` sets hard or soft chopping through the compare values; `set_switches` forces the outputs. Both are preloaded and take effect at the next period, as on a real drive.
- **Sampling:** the carrier centre triggers the conversion. `internal`: ADC1 + ADC2 in dual mode with DMA (pins PA3, PB1, PC0, PA4). `ad7606`: CONVST pulse, BUSY interrupt, SPI1 DMA read of the 8 channels. `ctrl_isr()` runs when the data are in.
- **Position:** `encoder`: TIM4 in encoder mode, Z on an EXTI; `ad2s1210`: SAMPLE pulse and SPI3 read.
- **Time:** `micros()` from a 32-bit timer; `ctrl_slow()` from a 1 kHz timer interrupt below the ISR.
- **Bus voltage:** `vbus_volts()` returns the configured value.
- **Measurements:** ISR execution time from the DWT cycle counter, ISR overruns (an ISR still running at the next trigger). An overrun marks the run invalid.
- **Serial (ST-LINK VCP):** parameters at any time (§7), commands, live statistics (ISR time, overruns, the controller's command and measured values) at about 20 Hz.

Owner code, the case's `srm_motor_tables.h` and a generated `hil_config.h` (modes, `pwm_hz`, `isr_hz`, scales) are added by the PlatformIO extra script. The controller firmware depends on the case, as a product build would.

## 7. Contract and HAL changes (shared with the SIL)

- `ctrl_param(name, value)` may be called at any time. Return 0 accepted, −1 unknown name, −2 known but not changeable while running. The reference controllers accept their angles, gains and limits live; the SIL keeps calling it before `ctrl_init` as today.
- `srm_hal_t` gains, at the end, `float adc_volts_per_count` and `int32_t adc_volt_offset_counts`. `adc_read(channel)` channels 0..q−1 are phase currents (as now) and q..2q−1 phase voltages; `adc_volts_per_count = 0` means no voltage channels. The SIL provides them through the shared voltage-sensor model (§5.5 filter).
- AD7606 two's complement codes reach the controller as unsigned codes with `adc_offset_counts = 32768`, so the current convention is unchanged.

## 8. PC protocol

Both links carry COBS-framed packets: type (u8), sequence (u16), payload, CRC-16/CCITT. `hil/common/hil_proto.h` defines the types and payloads; Python reads the same definitions (a test checks C and Python against shared vectors). Packet groups: hello/build info, config and table upload (emulator), parameter set and reply (controller), command, start/stop, live statistics, capture header, capture samples, capture end, error.

Capture samples are packed per step (int16 currents, fluxes and voltages, int16 torque, u16 angle, int16 speed, u8 gate word; scales in the capture header), about 32 bytes, about 6.4 MB/s. Captures that fit the RAM ring (OCRAM, about 80 ms) are buffered in full and then sent; longer ones stream while running. A sequence gap marks the capture invalid; it is never filled.

## 9. Python (`srmsil.hil`)

- `build_and_flash(controller, case, modes, *, cache_dir)`: writes the case header and `hil_config.h`, runs `pio run -e controller -e emulator -t upload` with the mode flags, caches builds by source hash, returns the log. A missing PlatformIO or board gives a clear error that names it.
- Board discovery by USB VID/PID (Teensy; ST-LINK VCP).
- `HilSession`: connect and check modes, upload tables and config, start/stop, set parameters, command, live statistics, capture. `run_hil(...)` scripts a fixed run and returns a `SimResult` like the SIL's plus a `hil` block (health numbers of §5.9 and §6, `valid`).
- `compare(hil, motor, controller, scenario)`: runs the SIL with the measured output latency and the sensing mode's latency as `SensorSettings.delay` (§11) and returns the differences in mean torque, RMS current and ripple against D10.

New optional extra `hil` = `pyserial` (pinned); `srmsil.hil` imports it lazily, so a missing package fails only when a session opens. PlatformIO runs from its own environment `hil/.runtime` (git-ignored), created by `hil/setup.bat` or `hil/setup.sh`, as `bench/` does; the shared `.venv` is never changed by the implementation sessions.

## 10. Web

- One live session at a time (one rig), loopback host only (it flashes boards and drives local USB), enforced at the routes and in the session.
- Build & Flash is a job of kind `hil_flash` on the main lane (steps queued, build, flash, saved). The live session is not a job: `POST /api/hil/session` opens it, `GET /api/hil/session/events` (SSE, as the job events) carries live statistics, `POST /api/hil/session/param|command|start|stop|capture` act on it, `DELETE` closes it. Captures are npz in `<cache_dir>/sil/hil/`, counted and cleared with the cache.
- **Control tab:** a SIL / HIL switch. HIL mode shows the mode selectors, Build & Flash with its log, board status, Start/Stop, live numbers, parameter controls that apply live, Capture, scopes that overlay the HIL capture on the matched SIL run, and the comparison pass/fail with the health numbers. Graphite theme, no blue, `plotTheme`.

## 11. SIL changes

- The plant split (§5.3), with unchanged results.
- `SensorSettings.delay` (s, default 0): a pure transport delay on the sensed currents and voltages, so the SIL can match the HIL's measured latency.
- Voltage channels in the HAL (§7) through the shared sensor model.
- `ctrl_param` −2 handling in `run.py` (reported, not an error before init).
- An emulator-model build of the plant for the PC: float tables at the emulator grid, a 5 µs step, gates fed as stamped edges and averaged as in §5.2. It is the CI stand-in for the Teensy model.

## 12. Verification

CI (no hardware):
1. Existing `tests/sil` pass unchanged after the plant split.
2. Emulator model vs SIL: open-loop pulse at fixed speed, float tables at the emulator grid, 5 µs step, averaged gates, against the 0.5 µs double SIL: mean torque within 1 %, RMS current within 1 %.
3. Gate averaging: known edge patterns (several edges in one step, an edge on a step boundary, a zero-current crossing inside a step) give the exact volt-seconds.
4. Protocol: COBS and CRC round trips; a corrupt packet and a sequence gap are detected; C and Python agree on shared vectors.
5. Emulated chip coding: AD7606 range and two's complement, AD2S1210 position and velocity scaling, against datasheet examples.
6. `SensorSettings.delay` delays the ADC trace by the set time; `ctrl_param` −2 path.
7. Firmware compiles for both environments in every mode (a CI job that runs when `hil/**` or `src/srmsil/c/**` changes).
8. Web: route and session tests with a fake board transport, the loopback rule, capture storage; vitest for the HIL panel; `noBlue`.

Bench (manual, recorded in `docs/r8b-hil-results.md`):
1. Health: zero overruns and dropped packets, step time under 80 % of dt; edge jitter, latency and ISR times reported.
2. Each reference controller (hysteresis, PWM current, TSF) spins an evaluated 8/6 case at fixed speed: HIL vs matched SIL within 3 % (mean torque, RMS current) and ±5 points (ripple %), in `ad7606` mode, and in `internal` mode once DACs are fitted.
3. Dynamic mode: the speed loop follows a speed step.
4. A live θ_on change moves the live numbers; a capture shows in the Control tab.
5. `ad2s1210` mode: the angle the controller reads matches the true angle within the set resolver errors.

## 13. Versions and dependencies

srmsil, srmweb and `web/` take the next minor version at merge, after R3c; the number is agreed with the coordinating session at merge time. srmcore is unchanged. The openapi schema is regenerated. Firmware carries `HIL_PROTOCOL_VERSION`, checked at connect. New dependencies: extra `hil` = `pyserial`; PlatformIO in `hil/.runtime` (§9).

## 14. Future use

- The Nucleo driver (`srm_hal_stm32.c`, the AD7606 and AD2S1210 drivers, the TIM1/TIM8 AHB PWM) is written to product standard and is the starting point for the owner's motor controller board.
- A CAN command interface (ISO 11898, 11-bit identifiers; J1939 only if a vehicle network requires it) for vehicle/ECU communication is a planned follow-up. The H723 has FDCAN and the Teensy 4.1 has CAN, so the same rig can test it, with the PC or the Teensy as the host ECU.
- R8c: an FPGA emulator (Tang Nano 9K) for PWM above about 40 kHz or detail inside one PWM period, on the same pins.

## 15. Bench items to confirm before relying on them

From the wiring check (`docs/r8b-hil-wiring.md` §5): LPSPI4 SDO tri-state when CS is high (OUTCFG) on the i.MX RT1062; the board's MB1364 revision and default solder bridges; the Teensy GND pads; the pin-13 LED load on SCK at the chosen SPI clock; the Teensy LPSPI slave's maximum reliable clock. The first implementation task on hardware checks these and records the results.
