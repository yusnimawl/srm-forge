# R8b Control HIL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the owner's controller C on a Nucleo-H723ZG against a Teensy 4.1 that emulates the SRM drive in real time, with live tuning, full-rate captures and a pass/fail comparison against the SIL.

**Architecture:** The SIL's model is split into a shared `plant/` (C) that both the PC SIL and the Teensy firmware compile. A host-side "emulator model" build of the same plant (float tables, 5 µs step, averaged gate edges) is the CI stand-in for the Teensy. Firmware lives in `hil/` (PlatformIO, two environments); Python `srmsil.hil` builds, flashes and talks to both boards over COBS/CRC framed USB serial; srmweb adds a flash job and a live session; the Control tab gets a HIL mode.

**Tech Stack:** C99 (plant, protocol, chip coding), PlatformIO with STM32Cube (Nucleo) and Teensyduino (Teensy), Python 3.12 (ctypes, numpy, pydantic, pyserial), FastAPI + SSE, React 19 / TypeScript / Plotly.

**Spec:** `docs/superpowers/specs/2026-10-20-r8b-control-hil-design.md` (wiring: `docs/r8b-hil-wiring.md`).

## Global Constraints

- Never `pip install` into the shared `.venv`; run Python with `PYTHONPATH=src` (and `tests` / `tests/sil` where a test needs it). PlatformIO lives only in `hil/.runtime` (git-ignored), created by `hil/setup.bat` / `hil/setup.sh`.
- C is C99, no dynamic allocation, no OS calls in plant, protocol, chip-coding and controller code. Controller maths is `float`; the plant may use `double`.
- Converter is the asymmetric half-bridge only. Gate word: `uint16_t`, bit k = upper switch of phase k, bit 8+k = lower switch of phase k.
- Emulator step dt = 5 µs. Emulator table grid default 180 θ × 192 ψ, `float`.
- Tolerances: emulator model vs SIL 1 % (mean torque, RMS current); HIL vs matched SIL 3 % (mean torque, RMS current) and ±5 points (ripple %).
- Encoder edge rate limit CPR·rev/s ≤ 400 000 /s (one A or B edge per count). Step time warning above 80 % of dt; any overrun or dropped capture packet makes the run `valid = False`.
- PC links: COBS framing, CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), little-endian packed payloads, `HIL_PROTOCOL_VERSION = 1`.
- HIL routes and the session work only on a loopback host (403 otherwise), checked at the route and in the session.
- Versions are not bumped on the branch (the bump above srmweb 0.9.0 / srmsil 0.8.0 is agreed with the coordinating session at merge). srmcore is unchanged.
- Test files: Python tests for this work are `tests/hil/test_hil_*.py` (basenames unique repo-wide); C sources compile with zig as in `srmsil.build`.
- Comments describe the code as it is, never task history. Web: Graphite theme, no blue (`noBlue.test.ts`), `plotTheme`.
- The living project doc is updated in Task 15 (and by the coordinating session's reports after each task).

## Review Focus

1. A gate pulse shorter than the switch's rise delay must produce no on-time (the SIL swallows it); the averaging must match — test in Task 3.
2. A current that reaches zero inside a 5 µs step while the switches are off must not drive ψ negative or produce reverse current — test in Task 3.
3. A session opened with the two boards built in different modes (e.g. Teensy `internal`, Nucleo `ad7606`) must be refused before RUN goes high, because both boards could drive the shared SCK wire — test in Task 11.
4. A capture with a sequence gap (lost USB packet) must be reported invalid, never interpolated — test in Task 11.
5. A live `ctrl_param` that the controller answers with −2 (not live-changeable) must be shown to the user as refused, not silently ignored — tests in Task 2 (SIL) and Task 12 (route).

---

## File Structure

```
src/srmsil/c/plant/srm_plant.h          config/tables structs (moved from sim), srm_table_t, plant state and step, AHB voltage
src/srmsil/c/plant/srm_plant.c          plant step (Heun, mechanics, ψ ≥ 0 clamp)
src/srmsil/c/plant/srm_motor.c          moved from sim/ (table lookup on srm_table_t)
src/srmsil/c/plant/srm_sensors.c        moved from sim/ (+ transport delay, voltage channels)
src/srmsil/c/plant/srm_gate_avg.[ch]    edge-timestamp gate averaging
src/srmsil/c/sim/srm_sim.[ch]           scheduler, HAL, queue, traces (uses plant/)
src/srmsil/c/sim/srm_converter.c        SIL converter (uses srm_ahb_voltage)
src/srmsil/c/emu/srm_emu.c              host build of the emulator model (ctypes entry point)
src/srmsil/emumodel.py                  run the emulator model on the PC
hil/common/hil_proto.[ch]               packets, COBS, CRC-16
hil/common/hil_chips.[ch]               AD7606 / AD2S1210 / MCP492x coding
hil/platformio.ini, hil/setup.bat, hil/setup.sh, hil/scripts/add_sources.py
hil/emulator/*.cpp|*.c                  Teensy firmware
hil/controller/*.c                      Nucleo firmware (srm_hal_stm32.c, drivers, main)
src/srmsil/hil/{__init__,proto,config,build,transport,fake,session,compare}.py
src/srmweb/hil.py                       HilManager (session singleton, routes helpers)
web/src/components/analysis/HilPanel.tsx, HilScopes.tsx (+ tests)
docs/r8b-hil-results.md                 bench results
```

---

### Task 1: Shared plant split (SIL results unchanged)

**Files:**
- Create: `src/srmsil/c/plant/srm_plant.h`, `src/srmsil/c/plant/srm_plant.c`
- Move: `src/srmsil/c/sim/srm_motor.c` → `src/srmsil/c/plant/srm_motor.c`, `src/srmsil/c/sim/srm_sensors.c` → `src/srmsil/c/plant/srm_sensors.c`
- Modify: `src/srmsil/c/sim/srm_sim.h`, `src/srmsil/c/sim/srm_sim.c`, `src/srmsil/c/sim/srm_converter.c`, `src/srmsil/run.py` (`sim_library` sources and include dirs), `src/srmsil/build.py` only if a path list lives there
- Test: `tests/hil/test_hil_plant_split.py`, `tests/hil/plant_golden.json`

**Interfaces:**
- Produces (in `srm_plant.h`; `srm_sim.h` includes it and keeps every existing declaration):
  - `typedef double srm_table_t;` unless `SRM_TABLE_FLOAT` is defined, then `float`.
  - `srm_sim_config_t`, `srm_sim_tables_t` (moved unchanged except `const srm_table_t *current, *torque, *w_field;`; `w_field` may be NULL).
  - `typedef struct { double theta, omega, ttot; double psi[SRM_SIM_MAX_PHASES], cur[...], trq[...], wf[...]; } srm_plant_t;`
  - `double srm_plant_eval(const srm_sim_config_t *c, const srm_sim_tables_t *t, double theta, const double *psi, double *i, double *trq, double *w);` (total torque; W = 0 when `w_field` is NULL)
  - `void srm_plant_init(srm_plant_t *p, const srm_sim_config_t *c, const srm_sim_tables_t *t);`
  - `void srm_plant_step(srm_plant_t *p, const srm_sim_config_t *c, const srm_sim_tables_t *t, const double *v, double t_now, int64_t n);` — the Heun step now in `srm_sim_run` (fixed speed uses `theta0 + speed*(n+1)*dt`), ψ ≥ 0 clamp, updates cur/trq/wf/ttot.
  - `double srm_ahb_voltage(const srm_sim_config_t *c, int upper, int lower, double current);` — the four AHB cases of `srm_conv_voltage`.

- [ ] **Step 1: Record the golden before touching C.** Write `tests/hil/test_hil_plant_split.py` with a helper that runs, on `analytic_motor()`, the `open_loop` (θ_on 0.1, θ_off 0.45 rad, 1000 rpm, 0.02 s), `pwm_fixed` and `hysteresis` (torque 0.5 N·m, dynamic, J 1e-3) controllers and returns `mean_torque, ripple_pct, i_rms, copper_loss, energy_error` plus the sum of `traces["i"]`. Add a `--regen` path (env `HIL_REGEN=1`) that writes `tests/hil/plant_golden.json`; run it once on the unmodified code and commit the JSON.
- [ ] **Step 2: Test asserts equality.** `test_plant_split_matches_golden`: every number equals the golden to `rel=1e-12` (the split must not change arithmetic order). Run: `PYTHONPATH=src;tests;tests/sil python -m pytest tests/hil/test_hil_plant_split.py -v` → PASS on the old code.
- [ ] **Step 3: Split.** Create `plant/`, move the files, make `srm_sim_run` call `srm_plant_init` / `srm_plant_step` and `srm_conv_voltage` call `srm_ahb_voltage`; keep the energy and summary bookkeeping in `srm_sim.c`. Update `sim_library` to compile `plant/*.c` + `sim/*.c` with both folders on the include path.
- [ ] **Step 4: Run** the golden test and `python -m pytest tests/sil -q` → all PASS.
- [ ] **Step 5: Commit** `refactor(sil): shared plant for the SIL and the HIL emulator`.

### Task 2: Sensor delay, voltage channels and live `ctrl_param`

**Files:**
- Modify: `src/srmsil/c/srm_hal.h`, `src/srmsil/c/srm_ctrl.h`, `src/srmsil/c/plant/srm_plant.h`, `src/srmsil/c/plant/srm_sensors.c`, `src/srmsil/c/sim/srm_sim.c`, `src/srmsil/_abi.py` (`SRM_SIM_ABI = 3`), `src/srmsil/scenario.py`, `src/srmsil/run.py`, the three reference controllers and `controllers/common/srm_ref.c`, their READMEs
- Test: `tests/hil/test_hil_sil_additions.py`

**Interfaces:**
- `srm_hal_t` appends `float adc_volts_per_count; int32_t adc_volt_offset_counts;`. `adc_read(ch)`: ch < q currents, q ≤ ch < 2q phase voltages, else 0. `adc_volts_per_count == 0` means no voltage channels.
- `srm_sim_config_t` adds (8-byte block) `double sensor_delay, volt_full_scale, volt_rc_tau;` and (4-byte block) `int32_t n_param_steps;` plus a pointer `const srm_param_step_t *param_steps` with `typedef struct { double t; float value; char name[24]; } srm_param_step_t;` (mirror order in `_abi.Config`, 8-byte members first).
- `SensorSettings.delay: float = Field(0.0, ge=0, le=1e-3)` (s): pure transport delay of the sensed currents and voltages (ring of ⌈delay/dt⌉ steps, max 2048 steps; larger is a validation error).
- `AdcSettings.volt_full_scale: float | None = None` (V at the top code; None = no voltage channels) and `AdcSettings.volt_rc_tau: float = Field(10e-6, ge=0)`. Voltage code = 2^(bits−1) + v_filtered / (2·full_scale) · (2^bits − 1), clipped (bipolar, `adc_volt_offset_counts = 2^(bits−1)`).
- `Scenario.param_steps: list[ParamStep] = []`, `ParamStep(time: float ≥ 0, name: str ≤ 23 chars, value: float)`; applied in the sim loop just before the ISR whose time ≥ `time`.
- `ctrl_param` contract text in `srm_ctrl.h`: callable any time; 0 accepted, −1 unknown, −2 known but not changeable while running. Reference controllers accept every parameter live except `resolver_pole_pairs` (−2 after init).
- A −2 or −1 from a param step aborts the SIL run with `SimError("controller refused live parameter <name> (code <c>)")`.

- [ ] **Step 1: Failing tests** in `tests/hil/test_hil_sil_additions.py`:
  - `test_sensor_delay_shifts_adc_trace`: `pwm_fixed`, `delay=10e-6`, dt 0.5 µs: `adc_i` trace equals the `delay=0` trace shifted by 20 samples (max abs diff ≤ one ADC count after the first 20 samples).
  - `test_voltage_channels_read_phase_voltage`: `probe` controller extended (in `tests/sil/controllers/probe`) to log `adc_read(q)`; with `volt_full_scale=100`, `volt_rc_tau=0`, a phase held at +V reads `2048 + round(V_dc/200·4095)` ± 1.
  - `test_live_param_changes_torque`: `open_loop` with `param_steps=[ParamStep(time=0.01, name="theta_off", value=0.30)]` → mean torque over the last 5 ms is lower than without the step by more than 10 %.
  - `test_live_param_refused_is_error`: hysteresis with a step setting `resolver_pole_pairs` → `SimError` containing `refused live parameter resolver_pole_pairs (code -2)`.
  - `test_plant_split_matches_golden` (Task 1) still passes with the new defaults.
- [ ] **Step 2: Run** → FAIL (missing fields).
- [ ] **Step 3: Implement** the HAL fields, config fields + ABI 3, delay ring and voltage channel model in `srm_sensors.c`, param steps in `srm_sim.c`, Scenario models, `_run_loaded` wiring (`adc_volts_per_count = 2·volt_full_scale/(2^bits−1)`, offset mid-code), controller −2 rule, READMEs.
- [ ] **Step 4: Run** `tests/hil` and `tests/sil` → PASS.
- [ ] **Step 5: Commit** `feat(sil): sensor delay, voltage channels, live controller parameters`.

### Task 3: Gate-edge averaging

**Files:**
- Create: `src/srmsil/c/plant/srm_gate_avg.h`, `src/srmsil/c/plant/srm_gate_avg.c`
- Test: `tests/hil/test_hil_gate_avg.py` (compiles a tiny test shim with zig and calls it in a child via `sil_fixtures.call_in_child` style, or exports the function from a shared lib built by `srmsil.build.compile_host`)

**Interfaces:**
- `typedef struct { uint64_t t; uint16_t gates; } srm_edge_t;` — commanded gate word valid from tick `t`.
- `typedef struct { uint16_t cmd, eff; uint64_t pending_t[16]; uint16_t pending_valid; int64_t rise_ticks, fall_ticks; } srm_gate_avg_t;`
- `void srm_gate_avg_init(srm_gate_avg_t *g, int64_t rise_ticks, int64_t fall_ticks, uint16_t initial);`
- `void srm_gate_avg_window(srm_gate_avg_t *g, const srm_sim_config_t *c, const srm_edge_t *edges, int n, uint64_t t0, uint64_t dt, const double *current, double *v_out, float *on_upper, float *on_lower);` — consumes the edges with t in [t0, t0+dt) (sorted), writes each phase's duration-weighted AHB voltage (via `srm_ahb_voltage` with the start-of-step current) and on-fractions.
- Delay semantics (identical to the SIL's `follow`): a commanded level reaches the switch `rise_ticks` (on) or `fall_ticks` (off) after the command, only if the command still holds then; a pulse shorter than the delay never reaches the switch. `rise_ticks = round((dead_time + turn_on_delay)/tick)`, `fall_ticks = round(turn_off_delay/tick)`.

- [ ] **Step 1: Failing tests:**
  - `test_single_window_exact`: q=1, edge on at 1.0 µs, off at 3.5 µs in a 5 µs window, no delays, current 1 A, V_dc 48, ideal switches → v = 48·0.5 + (−48)·0.5 = 0.0 (both off with i>0 gives −V_dc); `on_upper == 0.5`.
  - `test_several_edges_and_boundary`: three edges inside one window plus one exactly at t0+dt (belongs to the next window) → on-fractions match a hand sum to 1e-12.
  - `test_short_pulse_swallowed` (Review Focus 1): rise delay 0.6 µs, on-pulse 0.5 µs → on-fraction 0 in all windows; a 0.7 µs pulse → on-time 0.1 µs.
  - `test_zero_current_both_off` (Review Focus 2): both off for the whole window, current 0 → v = 0; with the plant, ψ stays ≥ 0 and current ≥ 0 after the step.
  - `test_matches_sil_converter`: feed the SIL `pwm_fixed` gate trace (dt 0.5 µs, delays from `ConverterSettings()` defaults applied by the averager on the commanded edges recovered from a delay-free run) and compare per-window mean voltage with the SIL `v` trace averaged over the same 5 µs windows, on the windows where the SIL current stays > 0 for the whole window: max abs diff ≤ 1e-9·V_dc.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `srm_gate_avg.c` (a per-switch walk through the window's events, effective edges after delays, segment durations per phase).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(sil): gate-edge averaging for the real-time emulator`.

### Task 4: Emulator model on the PC (the 1 % CI check)

**Files:**
- Create: `src/srmsil/c/emu/srm_emu.c`, `src/srmsil/emumodel.py`
- Modify: `src/srmsil/tables.py` (add `emu_tables(m, n_theta=180, n_psi=192) -> SimTables` returning float32 arrays; reuse `sim_tables` internals)
- Test: `tests/hil/test_hil_emulator_model.py`

**Interfaces:**
- C: `SRM_SIM_API int srm_emu_run(const srm_sim_config_t *cfg, const srm_sim_tables_t *tab, const srm_edge_t *edges, int64_t n_edges, double tick_s, srm_sim_summary_t *sum);` compiled with `-DSRM_TABLE_FLOAT`; `cfg->dt` is the emulator step; open loop (gates only from `edges`); fills the same summary fields as `srm_sim_run` over the second half of the run.
- Python: `edges_from_trace(traces: dict, dt: float) -> np.ndarray` (structured `[('t','<u8'),('gates','<u2')]`, ticks of `dt`, one entry per change of the commanded gate word; built from a delay-free SIL run's `gate_u`/`gate_l`).
- Python: `run_model(m: MotorData, edges: np.ndarray, scenario: Scenario, *, tick_s: float, step: float = 5e-6, grid: tuple[int, int] = (180, 192), cache_dir: Path) -> SimSummary` (runs in a spawned child like `run.run`).

- [ ] **Step 1: Failing test** `test_emulator_model_within_1pct`: analytic motor, `open_loop` θ 0.1–0.45 rad at 1000 rpm and `pwm_fixed` at 1000 rpm, 0.04 s: SIL (dt 0.5 µs, double, `ConverterSettings()` defaults) vs `run_model` on the commanded edges of a delay-free run with the same converter settings → `abs(Δmean_torque)/abs(mean) ≤ 0.01` and every phase `abs(Δi_rms)/i_rms ≤ 0.01`. Print both numbers.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `emu_tables`, `srm_emu.c` (loop: per step `srm_gate_avg_window` then `srm_plant_step`), `emumodel.py`.
- [ ] **Step 4: Run** → PASS. If the 180 × 192 grid fails the 1 % bound, report the measured errors at 180×192, 240×256 and 360×256 to the coordinator and stop: the grid is an owner decision (RAM budget §5.3).
- [ ] **Step 5: Commit** `feat(sil): PC build of the HIL emulator model, 1 % check against the SIL`.

### Task 5: PC protocol (C and Python)

**Files:**
- Create: `hil/common/hil_proto.h`, `hil/common/hil_proto.c`, `src/srmsil/hil/__init__.py`, `src/srmsil/hil/proto.py`, `hil/common/proto_vectors.json`
- Test: `tests/hil/test_hil_proto.py`

**Interfaces:**
- C: `HIL_PROTOCOL_VERSION 1`; `enum hil_type { HIL_HELLO=1, HIL_BUILD_INFO, HIL_EMU_CONFIG, HIL_TABLE_CHUNK, HIL_PARAM_SET, HIL_PARAM_REPLY, HIL_COMMAND, HIL_START, HIL_STOP, HIL_LIVE_EMU, HIL_LIVE_CTRL, HIL_CAPTURE_REQ, HIL_CAPTURE_HDR, HIL_CAPTURE_DATA, HIL_CAPTURE_END, HIL_ERROR };`
  - `size_t hil_cobs_encode(const uint8_t *in, size_t n, uint8_t *out);` `long hil_cobs_decode(const uint8_t *in, size_t n, uint8_t *out);` (−1 on a malformed frame)
  - `uint16_t hil_crc16(const uint8_t *p, size_t n);` (CCITT-FALSE; check value of "123456789" is 0x29B1)
  - `size_t hil_frame(uint8_t type, uint16_t seq, const void *payload, size_t n, uint8_t *out);` → COBS(type, seq LE, payload, CRC LE) + 0x00
  - `long hil_unframe(const uint8_t *frame, size_t n, uint8_t *type, uint16_t *seq, uint8_t *payload, size_t cap);` → payload length, −1 COBS error, −2 CRC error, −3 too long
  - `size_t hil_payload_size(uint8_t type);` (0 for variable-length types)
  - Packed payload structs (`#pragma pack(push, 1)`): `hil_build_info_t {u16 protocol; u8 board /*1 emulator, 2 controller*/; u8 current_sense /*0 ad7606, 1 internal*/; u8 position /*0 encoder, 1 ad2s1210, 2 both*/; u8 dac /*0 none, 1 mcp4922x2, 2 mcp4921x4*/; u32 firmware_hash;}`, `hil_param_set_t {char name[24]; float value;}`, `hil_param_reply_t {char name[24]; int8_t status;}`, `hil_command_t {u8 mode; float value;}`, `hil_live_emu_t {u32 step; float mean_torque, ripple_pct, i_rms[4], speed_rpm, step_mean_us, step_max_us; u32 overruns, dropped; float edge_jitter_ns, latency_us;}`, `hil_live_ctrl_t {float isr_mean_us, isr_max_us; u32 isr_overruns; float command, i_meas[4];}`, `hil_capture_hdr_t {float dt, i_scale, psi_scale, v_scale, t_scale, omega_scale; u32 n_steps; u8 n_phases;}`, `hil_sample_t {u32 step; int16_t i[4], psi[4], v[4], torque; uint16_t theta; int16_t omega; uint16_t gates;}` (36 bytes), `hil_table_chunk_t {u8 which /*0 current, 1 torque*/; u32 offset; u16 n; float data[200];}`, `hil_emu_config_t` (the plant/sensor fields of `srm_sim_config_t` the emulator uses, as floats/ints, plus `n_theta, n_psi, theta_step, psi_step, psi_max, i_max`, `ad7606_range_v, ad7606_t_conv_us, sense_v_per_a, volt_divider, volt_rc_tau, dac_v_mid, dac_v_per_a, rdc_bits, capture_steps`). A `HIL_CAPTURE_DATA` payload is a u32 first-step index followed by up to 28 `hil_sample_t`.
- Python `src/srmsil/hil/__init__.py` defines `class HilError(Exception)` (used by every later task).
- Python `srmsil.hil.proto`: `cobs_encode/cobs_decode`, `crc16`, `frame(type, seq, payload: bytes) -> bytes`, `unframe(frame) -> (type, seq, payload)` raising `ProtoError(code)`, `Type` IntEnum, and one `struct.Struct` per packed payload with `pack_*/unpack_*` helpers and dataclasses for build info, live stats, capture header and samples (numpy structured dtype `SAMPLE_DTYPE` for samples).

- [ ] **Step 1: Failing tests:** `test_crc_check_value` (0x29B1), `test_cobs_round_trip` (empty, 1 byte, 253/254/255 bytes, zeros), `test_frame_round_trip_and_corruption` (flip one byte → `ProtoError` CRC; truncate → COBS error), `test_c_and_python_agree` (the C side, built with zig into a host lib exposing `hil_frame`, `hil_unframe`, `hil_payload_size`, frames every vector in `proto_vectors.json` to the same bytes as Python, and `hil_payload_size` equals each `struct.Struct.size`, including `hil_sample_t == 36`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hil): framed PC protocol shared by firmware and Python`.

### Task 6: Emulated chip coding

**Files:**
- Create: `hil/common/hil_chips.h`, `hil/common/hil_chips.c`
- Test: `tests/hil/test_hil_chips.py`

**Interfaces:**
- `int16_t ad7606_code(double volts, double range_v);` — 16-bit two's complement, code = round(volts/range_v·32768), clipped to [−32768, 32767].
- `uint16_t ad7606_to_unsigned(int16_t code);` — `code + 32768` (what the Nucleo driver hands to `adc_read`).
- `uint16_t ad2s1210_position(double elec_angle, int bits);` — angle wrapped to [0, 2π), quantised to `bits` (10–16), MSB-aligned in 16 bits.
- `int16_t ad2s1210_velocity(double elec_rad_s, int bits, double max_rps);` — two's complement, full scale ±max_rps (the chip's tracking rate for the resolution), MSB-aligned.
- `double ad2s1210_angle(uint16_t word, int bits);` — inverse used by the Nucleo driver.
- `uint16_t mcp492x_word(int channel, uint16_t code12);` — channel bit, BUF=0, GA=1 (1×), SHDN=1, 12-bit code.
- `uint16_t dac_code(double amps, double v_mid, double v_per_a, double vref);` — 12-bit, clipped.

- [ ] **Step 1: Failing tests** against datasheet examples: AD7606 ±10 V: +10 V → 32767, −10 V → −32768, 0 V → 0, 1 LSB = 305.2 µV; AD2S1210 12-bit: π → 0x8000, π/2 → 0x4000; position round trip within ½ LSB for 1000 random angles at 10/12/14/16 bits; MCP4922 word for channel B, code 0xABC → 0xBABC (A/B=1, BUF=0, GA=1, SHDN=1); DAC code clipping at 0 and 4095.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hil): AD7606, AD2S1210 and MCP492x coding`.

### Task 7: Firmware project, runtime and build from Python

**Files:**
- Create: `hil/platformio.ini`, `hil/setup.bat`, `hil/setup.sh`, `hil/README.md`, `hil/scripts/add_sources.py`, `hil/emulator/main.cpp` (hello/build-info only), `hil/controller/main.c` (hello/build-info only), `src/srmsil/hil/config.py`, `src/srmsil/hil/build.py`, `.github/workflows/hil.yml`
- Modify: `.gitignore` (`hil/.runtime/`, `hil/.pio/`), `pyproject.toml` (extra `hil = ["pyserial==3.5"]`)
- Test: `tests/hil/test_hil_build.py`

**Interfaces:**
- `HilModes(BaseModel, frozen, extra="forbid")`: `current_sense: Literal["ad7606","internal"] = "ad7606"`, `position: Literal["encoder","ad2s1210","both"] = "encoder"`, `dac: Literal["mcp4922x2","mcp4921x4"] = "mcp4922x2"`.
- `write_hil_config(modes: HilModes, scenario: Scenario, m: MotorData, path: Path) -> None` — `hil_config.h` with `#define HIL_CURRENT_SENSE_AD7606 1` (or `_INTERNAL`), `HIL_POSITION_*`, `HIL_DAC_*`, `HIL_PWM_HZ`, `HIL_ISR_HZ`, `HIL_N_PHASES`, ADC scales, encoder CPR.
- `pio_executable() -> Path` — `hil/.runtime/Scripts/pio.exe` or `hil/.runtime/bin/pio`; raises `HilError("PlatformIO is not set up; run hil/setup.bat (Windows) or hil/setup.sh")` when missing.
- `build_and_flash(controller: str, m: MotorData, scenario: Scenario, modes: HilModes, *, cache_dir: Path, upload: bool = True, log: list[str] | None = None) -> BuildResult(ok: bool, log: str, firmware_hash: int)` — writes `srm_motor_tables.h` (existing `write_header`) and `hil_config.h` into `<cache_dir>/sil/hil/build/<hash>/`, sets env `SRM_HIL_GEN_DIR` and `SRM_CTRL_DIR` (owner folder or reference folder + common) for `add_sources.py`, runs `pio run -d hil -e emulator -e controller [-t upload]`, cache by source hash like `srmsil.build`.
- `platformio.ini`: envs `emulator` (`platform = teensy`, `board = teensy41`, `framework = arduino`, `build_flags = -DSRM_TABLE_FLOAT -O2`, `extra_scripts = pre:scripts/add_sources.py`) and `controller` (`platform = ststm32`, `board = nucleo_h723zg`, `framework = stm32cube`, `upload_protocol = stlink`, `debug_tool = stlink`). Pin exact platform versions (current release at implementation time, recorded in the file).
- `add_sources.py` adds `src/srmsil/c/plant/*.c`, `hil/common/*.c` to both envs as needed (plant only to `emulator`), the owner/reference controller folder and the generated dir to `controller`, and passes mode `-D` flags from env `SRM_HIL_MODES` (`ad7606,encoder,mcp4922x2`) so CI can compile every mode without Python.
- CI `hil.yml`: on push/PR touching `hil/**`, `src/srmsil/c/**`, `.github/workflows/hil.yml`; Linux; installs PlatformIO into `hil/.runtime` with `hil/setup.sh`; compiles both envs for the mode matrix {ad7606, internal} × {encoder, ad2s1210, both} with the `hysteresis` reference controller and a generated header from `tests/sil/sil_fixtures.analytic_motor`.

- [ ] **Step 1: Failing tests** (`tests/hil/test_hil_build.py`): `test_hil_config_header` (writes defines for given modes; `ad7606` + `ad2s1210` → `HIL_CURRENT_SENSE_AD7606 1`, `HIL_POSITION_AD2S1210 1`, no `HIL_DAC_*`); `test_modes_reject_unknown`; `test_pio_missing_message` (monkeypatched runtime dir); `test_pio_compiles_both_envs` marked `pytest.mark.skipif(no pio)` — compiles without upload.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (both firmwares answer `HIL_HELLO` with `HIL_BUILD_INFO`; Teensy over `Serial` (USB), Nucleo over USART3 VCP at 921 600 baud).
- [ ] **Step 4:** Run `hil\setup.bat`, then the tests → PASS including the compile test. Push the branch only if the coordinator asks; the CI job is checked when the PR opens.
- [ ] **Step 5: Bench (boards attached; if not, report to the coordinator and continue with Task 8):** `build_and_flash(... upload=True)`; both boards answer hello with matching modes. Record in `docs/r8b-hil-results.md` §Bring-up.
- [ ] **Step 6: Commit** `feat(hil): PlatformIO project, isolated runtime, build and flash from Python`.

### Task 8: Emulator firmware core

**Files:**
- Create: `hil/emulator/step.cpp` (200 kHz step timer, plant call), `hil/emulator/gates.cpp` (GPIO1 combined IRQ, edge ring, 64-bit cycle time), `hil/emulator/link.cpp` (USB framing, config/table upload, live stats at 20 Hz, capture ring in DMAMEM + streaming), `hil/emulator/safety.cpp` (RUN/READY), `hil/emulator/emu.h`
- Modify: `hil/emulator/main.cpp`

**Interfaces:**
- Consumes: `srm_plant_*` (Task 1), `srm_gate_avg_*` (Task 3), `hil_proto` (Task 5), pins from `docs/r8b-hil-wiring.md` (gates 14–21 → gate word bits: pin 14 A_u bit 0, 15 B_u bit 1, 16 C_u bit 2, 17 D_u bit 3, 18 A_l bit 8, 19 B_l bit 9, 20 C_l bit 10, 21 D_l bit 11; RUN in 7; READY out 8).
- Interrupt priorities: gates highest, encoder timer (Task 9) next, step timer next, USB lowest.
- Tables in DTCM: `static srm_table_t g_current[180*192], g_torque[180*192];` (capacity constants `EMU_MAX_THETA 180`, `EMU_MAX_PSI 192`); the config's grid must fit or the config is refused with `HIL_ERROR`.
- Capture: ring of `hil_sample_t` in DMAMEM sized to the largest power of two that fits (target ≥ 16 384 samples ≈ 82 ms); `capture_steps ≤ ring` → buffer fully then send; larger → stream while running; a full ring while streaming increments `dropped` and ends the capture with `HIL_CAPTURE_END` carrying `valid = 0`.
- Health in `hil_live_emu_t`; latency = time from the last edge of a step to the DAC/AD7606 output update of that step, measured with the cycle counter (mean).

- [ ] **Step 1: Host test of the step bookkeeping** (`tests/hil/test_hil_emu_ring.py`): the edge ring and window split logic lives in a portable `hil/emulator/edge_ring.c` (no Arduino) — test wrap-around of the 32-bit cycle counter into 64-bit ticks and that edges are assigned to the right window when the step ISR runs late by up to 2 µs.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** the core. **Step 4:** tests PASS and `pio run -e emulator` compiles in every mode.
- [ ] **Step 5: Bench:** with a fixed 20 kHz, 50 % pattern from the Nucleo hello firmware extended by a `HIL_COMMAND` test mode (both gates of phase A toggling), the emulator reports step_max < 4 µs (80 %), 0 overruns, edge jitter < 150 ns, and phase-A current ripple matching the emulator model of Task 4 within 1 %. Record results.
- [ ] **Step 6: Commit** `feat(hil): Teensy emulator core: step loop, gate capture, health, capture streaming`.

### Task 9: Emulator outputs (AD7606, AD2S1210, DACs, encoder)

**Files:**
- Create: `hil/emulator/ad7606_slave.cpp`, `hil/emulator/ad2s1210_slave.cpp`, `hil/emulator/dac.cpp`, `hil/emulator/encoder.cpp`
- Test: `tests/hil/test_hil_encoder_schedule.py` (portable `hil/emulator/enc_sched.c`)

**Interfaces:**
- `enc_sched.c`: `int enc_edges(double theta0, double theta1, uint32_t cpr, double offset, double ecc_amp, int ecc_harm, double t0, double dt, double *times, uint8_t *states, int cap);` — times and A/B quadrature states of every count boundary crossed (both directions), Z at count 0; returns count or −1 if > cap.
- AD7606 slave on LPSPI4 (CONVST pin 5 rising IRQ latches 8 words into the TX FIFO, BUSY pin 6 high for `t_conv`), OUTCFG tri-state when CS high; V1–V4 currents (`sense_v_per_a`), V5–V8 voltages (`volt_divider`, `volt_rc_tau`).
- AD2S1210 slave on LPSPI3 with SAMPLE (9), A0 (22), A1 (23); position/velocity/config per spec §5.6.
- DAC master on LPSPI4 only while RUN is high and the build mode is `internal`; LDAC on 30; CS 24/25 (+28/29).

- [ ] **Step 1: Failing tests:** `test_encoder_edges_constant_speed` (1000 CPR, 1000 rpm, 5 µs: edge count per window equals floor difference; times monotonic; quadrature order A then B for counter-clockwise); `test_encoder_reverse`; `test_encoder_rate_limit` (`srmsil.hil.config.check_encoder_rate(cpr, rpm)` raises above 400 000 edges/s).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** PASS and every mode compiles.
- [ ] **Step 5: Bench (§15 items):** confirm LPSPI4 SDO tri-states with CS high (scope or Tang Nano logic analyser), the highest reliable slave SCK (start 8 MHz, step to 15 MHz, 10 000 transfers without a CRC-checked mismatch), the pin-13 LED effect on SCK edges, and the Teensy GND pads. Record in `docs/r8b-hil-results.md` §Bench checks and set the Nucleo SPI1/SPI3 prescalers to the confirmed clock.
- [ ] **Step 6: Commit** `feat(hil): emulated AD7606, AD2S1210, DAC outputs and encoder`.

### Task 10: Nucleo controller driver

**Files:**
- Create: `hil/controller/srm_hal_stm32.c`, `hil/controller/srm_hal_stm32.h`, `hil/controller/pwm_ahb.c`, `hil/controller/sense_ad7606.c`, `hil/controller/sense_internal.c`, `hil/controller/pos_encoder.c`, `hil/controller/pos_ad2s1210.c`, `hil/controller/link.c`, `hil/controller/README.md`
- Modify: `hil/controller/main.c`
- Test: `tests/hil/test_hil_pwm_compare.py` (portable `hil/controller/pwm_compare.c`)

**Interfaces:**
- `pwm_compare.c`: `void ahb_compare(float duty, int chop_soft, uint16_t arr, uint16_t *ccr_upper, uint16_t *ccr_lower);` — centre-aligned compare values reproducing the SIL carrier rule (`u` on when carrier > 1 − duty; soft: lower always on (`ccr = arr+1`), hard: lower = upper); duty clipped to [0, 1].
- `void srm_hal_stm32_init(srm_hal_t *hal);` reads the generated `hil_config.h` macros and fills every HAL field (incl. the Task 2 voltage fields: `adc_volts_per_count` from the AD7606 range and divider in `ad7606` mode, 0 in `internal` mode).
- TIM1 (upper A–D, PE9/PE11/PE13/PE14) master, TIM8 (lower A–D, PC6/PC7/PC8/PC9) slave, centre-aligned, preload on, no dead time, TRGO at the carrier centre → ADC (internal: ADC1+ADC2 dual, PA3/PB1/PC0/PA4, DMA) or CONVST (PD15) → BUSY EXTI (PF3) → SPI1 DMA (PA5/PA6, CS PD14) → `ctrl_isr()`.
- Encoder: TIM4 PD12/PD13, Z EXTI PG14. AD2S1210: SPI3 PC10/PC11/PC12, FSYNC PD2, SAMPLE PG2, A0 PG3, A1 PD7; `resolver_sincos` returns `round(32767·sin/cos(angle))`.
- RUN PD6 out (raised only after PA5 is an input in `internal` mode and after a successful mode check), READY PD4 EXTI in: falling → all gates off (`set_switches(k,0,0)` for all k and timer outputs forced inactive), live stats report it.
- ISR timing by DWT CYCCNT; overrun when a new trigger arrives while `ctrl_isr` runs.
- Serial link (USART3 VCP, 921 600 baud, DMA): `HIL_PARAM_SET` → `ctrl_param` → `HIL_PARAM_REPLY` with the status; `HIL_COMMAND` → `ctrl_command`; `HIL_LIVE_CTRL` at 20 Hz.

- [ ] **Step 1: Failing tests:** `test_ahb_compare_matches_sil_carrier` (for duty in {0, 0.1, 0.5, 0.9, 1} and both chop modes, the on-time over one period sampled at arr+1 points equals the SIL `srm_conv_step` rule's on-time to one count).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** PASS; `pio run -e controller` compiles in every mode with each reference controller and with `tests/sil/controllers/open_loop`.
- [ ] **Step 5: Bench:** `open_loop` controller (θ 0.1–0.45 rad) spins the emulated analytic motor at fixed 1000 rpm in `ad7606` + `encoder` mode; ISR time reported; 0 ISR overruns; READY pulled low by a Teensy stop turns all gates off within one PWM period (check with the logic analyser). Record.
- [ ] **Step 6: Commit** `feat(hil): Nucleo-H723ZG HAL driver (TIM1/TIM8 AHB PWM, AD7606, internal ADC, encoder, AD2S1210)`.

### Task 11: Python session, transports, capture and compare

**Files:**
- Create: `src/srmsil/hil/transport.py`, `src/srmsil/hil/fake.py`, `src/srmsil/hil/session.py`, `src/srmsil/hil/compare.py`
- Test: `tests/hil/test_hil_session.py`, `tests/hil/test_hil_compare.py`

**Interfaces:**
- `Transport` protocol: `send(type, payload: bytes)`, `recv(timeout: float) -> tuple[int, int, bytes] | None`, `close()`. `SerialTransport(port: str, baud: int)` (lazy `import serial`; a missing pyserial raises `HilError("pyserial is not installed; install the hil extra")`). `discover() -> RigPorts(teensy: str | None, stlink: str | None)` by USB VID/PID (Teensy 0x16C0; ST-LINK 0x0483).
- `FakeRig(motor: MotorData, *, modes=HilModes(), drop_after: int | None = None, mode_mismatch: bool = False) -> tuple[Transport, Transport]` — answers hello/config/params/start/stop/capture; produces live stats and captures from a SIL run of the requested controller (via `srmsil.run.run`); `drop_after` skips one capture packet; `mode_mismatch` reports `internal` on the controller.
- `HilSession(emulator: Transport, controller: Transport)`: `connect() -> RigInfo` (raises `HilError("board modes differ: …")` on a mismatch, before any start — Review Focus 3), `configure(m, scenario, modes)`, `start()`, `stop()`, `set_param(name, value) -> int` (status), `command(mode, value)`, `live() -> LiveStats | None`, `capture(n_steps) -> Capture(result: SimResult, valid: bool, reason: str)`.
- `run_hil(session, m, controller, scenario, *, settle_s=0.2) -> SimResult` with `traces` from a capture of the run window and `summary` computed like the SIL's (second half window), plus `hil: dict` (step_mean_us, step_max_us, overruns, dropped, edge_jitter_ns, latency_us, isr_mean_us, isr_max_us, isr_overruns, valid).
- `compare.matched_scenario(scenario, latency_s: float, modes: HilModes) -> Scenario` — sets `sensors.delay = latency_s + sense_latency(modes)`, where `sense_latency("ad7606") = t_conv + 8·16/f_spi` and `sense_latency("internal") = 0`.
- `compare.compare(hil: SimResult, sil: SimResult) -> Comparison(d_torque_pct, d_irms_pct, d_ripple_pts, passed)`, `passed` = |d_torque| ≤ 3 and |d_irms| ≤ 3 and |d_ripple| ≤ 5; `SimResult.hil["valid"]` False → `passed` False.

- [ ] **Step 1: Failing tests:** `test_connect_refuses_mode_mismatch` (FakeRig `mode_mismatch=True` → `HilError`, and no `HIL_START` was sent); `test_capture_gap_invalid` (`drop_after=3` → `valid False`, `reason` names the missing sequence, traces not filled); `test_set_param_refused_status` (FakeRig returns −2 for `resolver_pole_pairs`); `test_run_hil_on_fake_matches_sil` (FakeRig → compare passes); `test_compare_bounds` (3.1 % → fail, 2.9 % → pass, ripple 5.1 pts → fail); `test_pyserial_missing_message`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(hil): Python session, fake rig, capture and SIL comparison`.

### Task 12: srmweb flash job and live session

**Files:**
- Create: `src/srmweb/hil.py`
- Modify: `src/srmweb/api.py`, `src/srmweb/jobs.py` (`STEPS["hil_flash"] = ("queued", "build", "flash", "saved")`, runner), `src/srmweb/schemas.py`, `src/srmweb/results.py`, `src/srmweb/store.py` only if a kind list lives there, cache size/clear to count `<cache_dir>/sil/hil/`
- Test: `tests/hil/test_hil_web.py`

**Interfaces:**
- `create_app(settings, runner_factory=JobRunner, hil_transports: Callable[[], tuple[Transport, Transport]] | None = None)` — default uses `discover()` + `SerialTransport`; tests pass a `FakeRig`.
- `HilManager` (one session per app): `open(case_id, body: HilOpenIn) -> HilSessionOut`, `close()`, `events()` (SSE generator of live stats, 20 Hz), `param(name, value) -> {"status": int}`, `command`, `start`, `stop`, `capture(n_steps) -> capture_id` (npz + json in `<cache_dir>/sil/hil/`), `compare(capture_id) -> ComparisonOut` (runs the matched SIL through `srmsil.run.run`).
- Routes: `POST /api/cases/{id}/hil/flash` (job), `POST /api/hil/session`, `DELETE /api/hil/session`, `GET /api/hil/session/events`, `POST /api/hil/session/param|command|start|stop|capture`, `GET /api/hil/captures/{capture_id}?n_px=` (decimated like `/jobs/{id}/control`), `GET /api/hil/captures/{capture_id}/compare`. All 403 off loopback (route and manager). A second `POST /api/hil/session` while one is open → 409. `param` returns 200 with the controller's status; −2 → `{"status": -2, "message": "not changeable while running"}` (Review Focus 5).

- [ ] **Step 1: Failing tests:** loopback rule on every route (403 with a non-loopback `Settings.host`); open/close/409; param −2 message; capture then compare on the FakeRig → `passed True`; mode mismatch → 409 with the `HilError` text; cache size counts and clear removes `sil/hil` captures (clear 409 while a session is open).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** PASS; `PYTHONPATH=src python -m pytest -m "not slow" tests/app tests/hil -q` PASS.
- [ ] **Step 5:** Regenerate the API schema: `python -m srmweb.openapi web/openapi.json; cd web; npm run gen:api`.
- [ ] **Step 6: Commit** `feat(web): HIL flash job and live session routes`.

### Task 13: Control tab HIL mode

**Files:**
- Create: `web/src/components/analysis/HilPanel.tsx`, `web/src/components/analysis/HilPanel.test.tsx`, `web/src/lib/hil.ts`
- Modify: `web/src/components/analysis/ControlTab.tsx` (SIL / HIL switch), `web/src/components/analysis/ControlScopes.tsx` (optional overlay series)

**Interfaces:**
- `hil.ts`: typed wrappers over the generated schema for the Task 12 routes and an `EventSource` hook `useHilEvents()`.
- HIL panel: mode selectors (`current_sense`, `position`, `dac` shown only for `internal`), Build & Flash (job stepper + log), board status (from session info), Start/Stop, live numbers (mean torque, ripple, RMS currents, speed, step and ISR health; a red "invalid" chip on any overrun or drop), parameter rows from `GET /api/control/controllers` that send on change and show "refused (not live)" for status −2, Capture (length in ms), scopes with HIL and matched SIL overlaid (`LINE_COLORS`/`LINE_DASHES`, `plotTheme`), comparison pass/fail with the three differences.

- [ ] **Step 1: Failing vitest tests:** switch shows the panel; `dac` selector hidden in `ad7606` mode; a −2 param reply shows "refused (not live)"; an invalid capture shows the invalid chip and no pass badge; `noBlue` still passes.
- [ ] **Step 2: Run** `cd web; npx vitest run` → FAIL. **Step 3: Implement.** **Step 4:** vitest PASS, `npm run build` PASS.
- [ ] **Step 5: Commit** `feat(web): HIL mode in the Control tab`.

### Task 14: Bench acceptance

**Files:**
- Create: `examples/control_hil.py` (CLI: flash, run each reference controller, compare, print the table; `--modes`, `--case` setup file or analytic motor)
- Modify: `docs/r8b-hil-results.md`

- [ ] **Step 1:** With the owner and the rig: evaluated 8/6 case, `ad7606` + `encoder`. For hysteresis, pwm_current and tsf at fixed speed: `run_hil` + `compare` → record mean torque, RMS current, ripple, the three differences, pass/fail, health numbers, ISR times.
- [ ] **Step 2:** Dynamic mode speed step with the speed loop; record the response.
- [ ] **Step 3:** Live θ_on change from the Control tab; record before/after live numbers and a capture.
- [ ] **Step 4:** `ad2s1210` mode: angle error vs true θ within the set resolver errors; record.
- [ ] **Step 5:** `internal` mode only if DACs are fitted; otherwise record "not run: no DACs".
- [ ] **Step 6:** Any failure → systematic debugging, report to the coordinator before changing a tolerance (tolerances are owner decisions).
- [ ] **Step 7: Commit** `docs: R8b bench results`.

### Task 15: Documentation

**Files:**
- Modify: `CLAUDE.md` (new "Control HIL (R8b)" section after "Control SIL (R8a)": layout, modes, setup, commands `hil\setup.bat`, `python examples\control_hil.py`, tests; Commands block), `docs/superpowers/specs/2026-10-20-r8b-control-hil-design.md` (Status: implemented; §16 decisions made during implementation), `src/srmsil/c/controllers/*/README.md` (live parameters)
- Living project doc (Claude Docs, https://claude.ai/code/artifact/7dc85cd6-a7f2-4bfa-8e35-de2604864d37): R8b section (status, results table, decisions) and the whole-project table.

- [ ] **Step 1:** Write the docs. **Step 2:** `python -m pytest -m "not slow" -q` and `cd web; npx vitest run` PASS. **Step 3: Commit** `docs: R8b control HIL in CLAUDE.md and spec`.
