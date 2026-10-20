# R8a — Control SIL — Design Spec

Status: implemented on branch r8-control-sil (2026-10-20).
Roadmap: `2026-10-12-roadmap-r1-r10-design.md` §3 R8. R8 is split into **R8a** (this spec: software-in-the-loop on the PC) and **R8b** (two-board hardware-in-the-loop, own spec later).

## 1. Goal

The owner writes motor-control code as portable C behind a small HAL. The tool runs that code against a simulated SRM drive built from an evaluated case (converter, PWM, sensors, ADC, time-domain motor model from the maps), shows scopes in the web UI, and checks that the same C files compile for the target MCU.

Done when: a reference controller runs in the simulation from the web UI on an evaluated case, and the same controller file compiles for Cortex-M7 with `-Wall -Werror`.

## 2. Decisions (owner, 2026-10-19)

| # | Decision |
|---|---|
| D1 | No existing owner HAL. R8a defines `srm_hal.h` (grblHAL style: a struct of function pointers the driver fills). |
| D2 | Target family STM32H7 (Cortex-M7, double-precision FPU). Owner's boards: Nucleo-H723ZG, Arduino GIGA R1 and Portenta H7 Lite (both STM32H747), Teensy 4.0 and 4.1 (iMXRT1062). |
| D3 | R8 split: R8a PC SIL (this spec), R8b HIL: one board runs the controller, another runs the motor model in real time, wired together. Recommended for R8b: Nucleo-H723ZG as controller (ST-LINK debugger, TIM1/TIM8 with hardware dead time, 16-bit ADCs), Teensy 4.1 as motor emulator (600 MHz, fastest loop) plus a quad SPI DAC breakout for the current signals (Teensy has no DAC). A Teensy 4.x as controller is an option for the R8b spec (FlexPWM, hardware quadrature decoder; 12-bit ADC, no on-board debugger). |
| D4 | The motor model, converter and sensors are portable C, so the same model code runs on the R8b emulator board. The controller C is unchanged between the PC sim, R8b and a real inverter. |
| D5 | The owner's controller is a folder on disk. The web UI takes the folder path; the server compiles it with the `ziglang` pip package (no system compiler needed) and runs it. Same from Python. |
| D6 | Mechanics: fixed speed and dynamic (inertia, friction, load torque that can step). |
| D7 | Reference controllers: hysteresis, PWM current, TSF. No reference HFI estimator in R8a; a test proves the model's small-signal response matches L_inc from the map, so owner HFI code works in the sim. |
| D8 | Approach: the whole simulation core is C (approach 1 of 3). Python builds one shared library from the sim core and the controller, loads it with `ctypes` in a child process, passes the tables and reads the traces back. |

## 3. Out of scope

R8b (firmware, real HAL drivers, wiring); a reference HFI controller; mutual coupling between phases (the stored maps excite one phase; results say so); DC-link capacitor and bus dynamics (ideal bus); winding temperature (R constant per run); ripple optimisation and tuned-table export (R9); iron loss in the time domain (R3).

## 4. Layout and layering

New package `src/srmsil/` (version follows srmweb). It imports `srmapp` and `srmcore` public modules; `srmweb` imports it; neither `srmcore` nor `srmapp` imports it (extend `tests/app/test_app_layering.py`). It must not import gmsh, ngsolve, netgen or skfem.

```
src/srmsil/
  c/
    srm_hal.h            HAL the controller sees
    srm_ctrl.h           functions a controller must provide
    sim/                 sim core: motor, converter, sensors, scheduler, trace buffers, ctypes entry points
    controllers/         reference controllers: hysteresis/, pwm_current/, tsf/ (one folder each, same shape as an owner folder)
  build.py               zig compile (host shared library, target check), build cache keyed by source hash
  tables.py              motor tables from an Evaluation; srm_motor_tables.h writer
  scenario.py            frozen Pydantic models: Scenario, ConverterSettings, SensorSettings, AdcSettings
  run.py                 run(...) -> SimResult, child-process isolation, decimation
```

New optional extra `sil` = `ziglang` (pinned); the `web` extra includes it. srmcore is unchanged.

## 5. HAL and controller contract

All C is C99, no dynamic allocation, no OS calls, `float` for controller-side maths (single-precision FPU paths on M7 are fastest; the sim core may use `double`).

`srm_hal.h`:

```c
typedef enum { SRM_CHOP_HARD, SRM_CHOP_SOFT } srm_chop_t;

typedef struct {
    uint8_t  n_phases;
    float    pwm_hz;              /* PWM carrier; ctrl_isr runs once per period */
    float    isr_hz;              /* ctrl_isr rate (= pwm_hz unless the scenario sets a faster sampled loop) */
    uint8_t  adc_bits;
    float    adc_amps_per_count;  /* nominal scale; real gain/offset errors are not visible to the controller */
    int32_t  adc_offset_counts;   /* nominal zero-current reading */
    uint32_t encoder_cpr;         /* counts per mechanical revolution, 0 when no encoder */
    void     (*set_switches)(uint8_t phase, bool upper, bool lower);   /* direct gate control */
    void     (*set_pwm)(uint8_t phase, float duty, srm_chop_t mode);   /* duty 0..1; timer adds dead time */
    uint16_t (*adc_read)(uint8_t channel);                             /* channel = phase for currents */
    uint32_t (*encoder_count)(void);
    void     (*resolver_sincos)(int16_t *s, int16_t *c);               /* raw signed ADC counts */
    uint32_t (*micros)(void);
} srm_hal_t;
```

The last call to `set_switches` or `set_pwm` for a phase wins. `srm_ctrl.h` (the controller provides):

```c
void ctrl_init(const srm_hal_t *hal);
int  ctrl_param(const char *name, float value);   /* 0 = accepted, -1 = unknown name; called before ctrl_init */
void ctrl_command(srm_cmd_mode_t mode, float value); /* SRM_CMD_TORQUE (N·m) or SRM_CMD_SPEED (rad/s) */
void ctrl_isr(void);    /* after each ADC conversion, at isr_hz */
void ctrl_slow(void);   /* 1 kHz: speed loop, supervision */
```

Motor data for controllers comes from a generated `srm_motor_tables.h` (machine constants, aligned angle per phase, ψ(θ,i), T(θ,i) and the inverse i(θ,T) on fixed grids, as `static const float` arrays). The sim adds the case's header to the include path; the owner can download it for firmware.

## 6. Simulation core (C)

**Motor.** State ψ_k per phase. ψ̇_k = v_k − R·i_k with i_k = i(θ_k, ψ_k) and T_k = T(θ_k, ψ_k) by bilinear lookup; θ_k = θ − aligned offset of phase k, wrapped to one rotor pole pitch. Tables come from `Evaluation.map` (chosen turns, end winding included) and `Evaluation.winding.resistance`; the inverse i(θ,ψ) is built in `srmsil.tables` on a fine uniform grid (PCHIP in current, periodic spline in angle, as `srmapp.drive.envelope._tables`), and its round-trip error is reported with the run.

**Mechanics.** Fixed speed: θ advances at ω. Dynamic: J·ω̇ = ΣT_k − B·ω − T_load(t), with T_load a constant plus an optional step at a given time.

**Converter (asymmetric half-bridge per phase).** Upper and lower switch states come from the gate commands after turn-on delay and dead time. Both on → v = V_dc − 2·V_sw; one on → freewheel v = −(V_sw + V_d); both off with i > 0 → v = −(V_dc + 2·V_d); both off with i = 0 → v = 0. ψ is clamped at 0 when the diodes stop conducting, so current never goes negative. `set_pwm` drives the switches from a centre-aligned carrier: hard chopping toggles both switches, soft chopping toggles the upper and keeps the lower on. Ideal DC bus.

**Time.** Fixed step dt (default 0.5 µs), Heun integration. PWM edges, ADC samples and ISR calls fall on the dt grid. The ISR runs at the ADC sample instant (carrier centre); its gate outputs apply after `compute_delay` (default one PWM period, as on real hardware with shadow registers). `ctrl_slow` runs every 1 ms.

**Sensors.** Encoder: CPR, angle offset, eccentricity error (amplitude, harmonic). Resolver: sin/cos amplitude mismatch, phase error, ADC quantisation. Current ADC per phase: sensor gain (V/A), range, bits, offset and gain error, Gaussian noise σ (counts), first-order RC anti-alias filter, sample instant. A seeded RNG makes runs repeatable.

**Outputs.** Traces at a stored rate (default every step up to a cap; otherwise strided): t, θ, ω, per phase i, ψ, v, gate states, ADC reading in amps, and total torque. Summary: mean torque, peak-to-peak ripple % of mean, RMS phase current, copper loss, mean electrical power, and the round-trip error of the inverse table.

## 7. Python API

- `srmsil.build.host_library(controller_dir) -> Path`: compiles sim core + controller (+ case header dir at run time via `-I`) into a shared library in `<cache_dir>/sil/`, cached by a hash of all sources and compiler flags.
- `srmsil.build.target_check(controller_dir, header_dir) -> TargetCheck(ok, compiler, log)`: compiles HAL + controller for Cortex-M7 with `-Wall -Wextra -Werror -O2`. Uses `arm-none-eabi-gcc -mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard` when it is on PATH, else `zig cc -target thumb-linux-musleabihf -mcpu=cortex_m7` (compile-only stand-in for libc headers); the result names the compiler used.
- `srmsil.tables.motor_tables(evaluation) -> MotorTables`, `write_header(tables, path)`.
- `srmsil.run.run(evaluation, controller, scenario, *, cache_dir, timeout_s=300) -> SimResult`. `controller` is a reference name (`"hysteresis"`, `"pwm_current"`, `"tsf"`) or a folder path. The library is loaded and run in a spawned child process; a crash, a non-zero `ctrl_param` result or a timeout becomes a `SimError` with the message; the parent never loads owner code.
- `SimResult`: traces (numpy), summary, scenario, controller name and source hash, compiler log, `decimate(n_px)` (min/max per bucket so PWM ripple peaks survive).

## 8. Reference controllers

All three take `ctrl_command(SRM_CMD_TORQUE, T)`, and in speed mode a PI loop in `ctrl_slow` produces the torque command. Parameters through `ctrl_param` (names listed in each controller's README, with defaults).

- **hysteresis:** per-phase current band around i_ref within the conduction window [θ_on, θ_off]; hard or soft chopping by direct gate control; runs at a fast `isr_hz` (default 50 kHz). i_ref from the torque command via the i(θ,T) table at the window centre.
- **pwm_current:** PI current loop per active phase at the PWM rate (default 20 kHz), anti-windup, duty to `set_pwm`; same window and i_ref rule.
- **tsf:** torque sharing between consecutive phases (cubic sharing function, overlap angle parameter); each phase's torque share → current reference through the i(θ,T) table at the measured angle; PWM current loop as above.

## 9. Web and UI

- Job kind `control` on the main lane, steps queued / compile / simulate / saved; result stored as npz in `<cache_dir>/sil/runs/` (counted and cleared with the cache like `fields/`). Routes: `POST /api/cases/{id}/control` (job), `GET /api/jobs/{id}/control?n_px=…` (decimated traces + summary), `GET /api/cases/{id}/control/header` (download `srm_motor_tables.h`), `POST /api/control/target-check`, `GET /api/control/controllers` (reference names and their parameters).
- A custom folder runs owner C on the server, so it is refused with 403 unless srmweb is bound to a loopback host. Reference controllers are always allowed.
- **Control tab** on evaluated cases: controller (reference dropdown or folder path), parameters, scenario (fixed speed or dynamic: J, B, load and load step, command mode and value, duration), converter / sensor / ADC settings collapsed with defaults; Run; stacked Plotly scopes with shared x zoom (phase currents, ψ, torque, speed, gates, ADC vs true current); summary numbers; target-check status with the log; header download. Graphite theme, no blue, `plotTheme`.

## 10. Verification

All fast-suite tests use small maps and short runs; any longer study is marked slow.

1. Open-loop single pulse at fixed speed (a test controller with fixed θ_on/θ_off, no current limit) against `srmapp.drive.envelope._simulate` on the same tables: mean torque within 1 %, flux zero by alignment in both.
2. Step convergence: dt and dt/2 give mean torque and RMS current within 0.2 %.
3. Energy balance over a run: ∫Σv·i dt = ∫T·ω dt + ∫ΣR·i² dt + ΔW_field within 0.5 %.
4. Small-signal: at fixed θ and bias current, a small voltage step gives di/dt = Δv / L_inc within 2 %, with L_inc from the map's ∂ψ/∂i.
5. Converter: diode clamp (i ≥ 0, ψ ≥ 0), freewheel and demagnetise voltages, dead time and turn-on delay shift edges by the set time.
6. Sensors: ADC quantisation and code range, noise σ, offset/gain error, RC filter step response; encoder count and eccentricity error shape; resolver mismatch.
7. Controllers: hysteresis keeps i within band plus one sample's rise; PWM loop step settles with no steady-state error; TSF gives lower torque ripple than hysteresis at the same mean torque; the speed loop reaches a speed step in dynamic mode.
8. Target check: HAL + each reference controller compile for Cortex-M7 with `-Wall -Wextra -Werror`.
9. Isolation: a controller that segfaults, loops forever or rejects a parameter gives a `SimError` and the parent process lives.
10. Web: route and job tests, the loopback rule, decimation keeps min/max; vitest for the tab; `noBlue` passes.
11. Layering: `srmsil` imports neither gmsh/ngsolve/netgen/skfem nor `srmweb`; `srmcore`/`srmapp` never import `srmsil`.

## 11. Versions

srmweb and `web/` get the next minor version at merge; srmcore is unchanged (no change to `VALIDATED_VERSIONS`). The openapi schema is regenerated.

## 12. Decisions made during implementation

- The HAL has `vbus_volts()`, so a controller reads the bus voltage instead of a compile-time constant.
- `compute_delay` defaults to one ISR period.
- `encoder_count` is single-turn, in [0, cpr).
- `run.run` takes `MotorData`; the web layer builds it from the case.
- The reference controllers take `resolver_pole_pairs` as a parameter (p must divide N_r).
- Speed PI scaling: kp = J·ω_c, ki = kp·ω_c/16; the default gains are tuned for J ≈ 1e-3 kg·m².
- Custom controllers run only on a loopback host, enforced where the job runs as well as at the route.
- The hysteresis command is the per-phase torque at the window centre.
- Versions are not bumped on the branch; srmsil follows the srmweb version and the bump is made at merge.
- R8b note: the simulator's static gate queue (65536 entries, about 2.6 MB) must shrink for an MCU emulator.
- R8b note: the generated `srm_motor_tables.h` defines the i(theta, T) table `static const` per translation unit
  (about 46 KB each); firmware should include it in one .c file or switch to an extern definition.
