# R8a Control SIL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the owner's portable C motor controller (behind a small HAL) against a simulated SRM drive built from an evaluated case, with scopes in the web UI and a Cortex-M7 compile check.

**Architecture:** New package `src/srmsil/`. The simulation core (motor model from map tables, asymmetric half-bridge converter, PWM, sensors, ADC, scheduler) is portable C in `src/srmsil/c/sim/`. Python compiles it together with a controller folder into one shared library with the `ziglang` pip compiler, runs it in a spawned child process through `ctypes`, and gets numpy traces back. srmweb adds a `control` job, routes and a Control tab.

**Tech Stack:** C99, `ziglang` (zig cc), Python 3.12+ `ctypes`/`multiprocessing`, numpy, scipy, Pydantic, FastAPI, React 19 + Plotly.

**Spec:** `docs/superpowers/specs/2026-10-19-r8a-control-sil-design.md` (read it before any task).

## Global Constraints

- C is C99, no dynamic allocation, no OS calls in controller code or in `srm_hal.h`/`srm_ctrl.h`; controller maths in `float`, sim core may use `double`.
- Layering: `srmsil` imports `srmapp`/`srmcore` public modules only, never `srmweb`, gmsh, ngsolve, netgen, skfem; `srmcore` and `srmapp` never import `srmsil`; `srmweb` may import `srmsil`.
- Owner/controller C is never loaded into the server process or the test-runner process: only into a spawned child (`run.run`). Tests of the C go through `run.run` or through `build.compile_host` + a child.
- Phase convention: phase k (A = 0) is aligned at rotor angle k·ε, ε = 2π/(q·N_r); ψ_k(θ) = ψ_A(θ − k·ε); motoring is counter-clockwise (θ increasing). Electrical angle from unaligned is `srmweb.serialize.electrical_deg_from_unaligned`.
- SI units everywhere in Python and C (rad, s, A, V, Wb, N·m); UI shows rpm and electrical degrees.
- `ziglang==0.16.0` in a new extra `sil`; the `web` extra includes it. srmcore version unchanged.
- Comments explain the code as it is; no plan history. Test file basenames unique (`tests/` has no `__init__.py`); new tests go in `tests/sil/` with names `test_sil_*.py`.
- Run focused tests while iterating; the laptop is busy (16 GB RAM, another long solve). Fast suite only once, at the end (Task 10).
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Web: Graphite theme, no blue (`web/src/lib/noBlue.test.ts`), all plots through `plotTheme` in `web/src/components/PlotlyPlot.tsx`; `web/src/api/schema.ts` is generated, never hand-edited.

## Review Focus

1. A controller folder that does not compile or link (syntax error, missing `ctrl_isr`) → `SimError` carrying the compiler log; the web job fails with that log, no traceback. (Task 1, Task 5)
2. A run that drives current beyond the map (high bus voltage, a runaway loop) → tables extrapolate linearly in ψ and the summary reports `beyond_map_fraction` > 0; no NaN in traces. (Task 3)
3. Standstill: fixed mode at 0 rpm and dynamic mode starting at 0 rpm run without dividing by speed; the motor accelerates in dynamic mode under a torque command. (Task 3, Task 7)
4. A huge request (duration / dt over `MAX_STEPS` = 50 000 000) → rejected before compiling, 422 on the web. Long runs within the limit stride the trace to `TRACE_CAP` = 2 000 000 samples per channel. (Task 3, Task 8)
5. A folder path that does not exist, is a file, or holds no `.c` file → `ValueError` in Python, 422 on the web (after the loopback rule, which gives 403 first on a non-loopback host). (Task 1, Task 8)

---

### Task 1: `srmsil` package, compiler driver, target check

**Files:**
- Create: `src/srmsil/__init__.py` (`__version__` = srmweb's version string), `src/srmsil/build.py`
- Modify: `pyproject.toml` (extra `sil = ["ziglang==0.16.0"]`; `web` extra gains `ziglang==0.16.0`; wheel `packages` gains `src/srmsil`; hatch must ship `src/srmsil/c/**`), `tests/app/test_app_layering.py`
- Test: `tests/sil/test_sil_build.py`

**Interfaces:**
- Produces:
  - `build.CompileError(Exception)` with attribute `log: str`.
  - `build.zig_cc() -> list[str]` = `[sys.executable, "-m", "ziglang", "cc"]`.
  - `build.controller_sources(folder: Path) -> list[Path]`: sorted `*.c` directly in `folder`; `ValueError` if the folder does not exist, is not a directory or has no `.c` file.
  - `build.compile_host(sources: list[Path], include_dirs: list[Path], out_dir: Path) -> Path`: shared library (`.dll` on Windows, `.so` elsewhere) named by a SHA-256 over the compiler version, the flags, every source and every `*.h` in the include dirs (path-independent: content only); returns the cached file if present. Flags: `-shared -O2 -std=c99 -Wall -Wextra -fPIC -DSRM_SIM_BUILD`. Writes to a temp name then renames. Raises `CompileError(log)` on failure.
  - `build.TargetCheck` frozen dataclass `(ok: bool, compiler: str, log: str)`.
  - `build.target_check(sources: list[Path], include_dirs: list[Path]) -> TargetCheck`: compile-only (`-c`, each source to a temp object) with `-std=c99 -O2 -Wall -Wextra -Werror`. Uses `arm-none-eabi-gcc -mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard -mthumb` when `shutil.which("arm-none-eabi-gcc")`, else zig cc `-target thumb-linux-musleabihf -mcpu=cortex_m7`. `compiler` names which one was used.

- [ ] **Step 1: Failing tests** in `tests/sil/test_sil_build.py`:
  - `test_compile_host_builds_and_caches(tmp_path)`: write `add.c` exporting `int add(int,int)` (use `#ifdef _WIN32 __declspec(dllexport) #endif`); `compile_host` twice → same path, second call does not change its mtime; load it **in a spawned child** (helper `_call_in_child(lib, "add", 2, 3)` using `multiprocessing.get_context("spawn")`) → 5.
  - `test_compile_host_error_carries_log(tmp_path)`: a source with a syntax error → `CompileError`, `"error" in exc.log`.
  - `test_cache_key_changes_with_header(tmp_path)`: changing an included header's content gives a different library path.
  - `test_controller_sources_rejects_bad_folders(tmp_path)`: missing path, a file, an empty folder → `ValueError`.
  - `test_target_check_pass_and_fail(tmp_path)`: a clean file using `<math.h>` and `<stdint.h>` → `ok` True; a file with an unused variable → `ok` False and the log names the warning.
  - In `tests/app/test_app_layering.py`: `test_srmsil_layering` — `srmsil` imports none of `srmweb, gmsh, ngsolve, netgen, skfem`; `srmcore` and `srmapp` never import `srmsil`.
- [ ] **Step 2:** `python -m pip install -e ".[dev,ngsolve,web]"`, run `python -m pytest tests/sil/test_sil_build.py tests/app/test_app_layering.py -v` → FAIL (module missing).
- [ ] **Step 3:** Implement `build.py` and the pyproject changes.
- [ ] **Step 4:** Same command → PASS.
- [ ] **Step 5:** Commit `feat(sil): srmsil package, zig compiler driver and target check`.

### Task 2: Motor tables and the controller header

**Files:**
- Create: `src/srmsil/tables.py`, `tests/sil/sil_fixtures.py`
- Test: `tests/sil/test_sil_tables.py`

**Interfaces:**
- Consumes: `srmapp.evaluate.Evaluation`, `MapArrays`; `srmcore.maps.tables.angle_spline`.
- Produces:
  - `tables.MotorData` frozen dataclass: `angles, currents, psi, torque` (np arrays, phase A, as `MapArrays`: angles over one rotor pole pitch, ψ in Wb-turns at the chosen turns with end winding, torque N·m), `resistance: float` (Ω, phase), `n_phases: int`, `n_rotor_poles: int`, `bus_voltage: float` (V). Properties `pole_pitch` (2π/N_r) and `stroke` (pole_pitch / n_phases).
  - `tables.motor_data(evaluation: Evaluation, bus_voltage: float) -> MotorData` and `tables.motor_data_from_json(evaluation: dict, bus_voltage: float) -> MotorData` (the stored evaluation JSON: `map`, `winding.resistance`, `design.machine.n_phases`, `design.machine.n_rotor_poles`). `ValueError` when `map` or `winding` is missing.
  - `tables.SimTables` frozen dataclass on a uniform periodic θ grid `theta_step = pole_pitch / n_theta` (θ_j = j·step, j < n_theta) and uniform ψ grid `psi_step = psi_max / (n_psi − 1)`: `current (n_theta, n_psi)`, `torque (n_theta, n_psi)`, `w_field (n_theta, n_psi)` (∫₀^ψ i dψ′, trapezoid), `psi_max`, `i_max` (top map current), `roundtrip_error` (max |ψ(θ, i(θ,ψ)) − ψ| / psi_max over the grid). Values float64, C-contiguous.
  - `tables.sim_tables(m: MotorData, n_theta: int = 720, n_psi: int = 512) -> SimTables`: ψ(θ,i) and T(θ,i) by PCHIP in current then `angle_spline` in angle (the same construction as `srmapp.drive.envelope._tables`), ψ forced non-decreasing in i; `psi_max` = max ψ at the top current over θ; i(θ,ψ) by `np.interp` per row (ψ above the row's top value: linear extrapolation with the last segment's slope); T(θ,ψ) = T(θ, i(θ,ψ)).
  - `tables.CtrlTables` frozen dataclass: `i_of_t (n_theta_c, n_t)` float32, `t_max`, `i_max`, `l_min`, `l_max` (min/max over θ of ∂ψ/∂i at the lowest nonzero map current, H).
  - `tables.ctrl_tables(m: MotorData, n_theta: int = 180, n_t: int = 64) -> CtrlTables`. Row rule, T_j = j·t_max/(n_t − 1), t_max = max map torque: if max_i T(θ,i) ≤ 0 → 0; else the smallest i on a fine current grid with T(θ,i) ≥ T_j, or the argmax current when T_j exceeds the row maximum.
  - `tables.write_header(m: MotorData, ct: CtrlTables, path: Path) -> None`: writes `srm_motor_tables.h` (include guard `SRM_MOTOR_TABLES_H`) with `#define`s `SRM_N_PHASES, SRM_N_ROTOR_POLES, SRM_POLE_PITCH_RAD, SRM_STROKE_RAD, SRM_I_MAX_A, SRM_T_MAX_NM, SRM_R_OHM, SRM_L_MIN_H, SRM_L_MAX_H, SRM_I_OF_T_N_THETA, SRM_I_OF_T_N_T`, `static const float srm_i_of_t_table[N_THETA][N_T]` (`%.9g`), and `static inline float srm_i_of_t(float theta_phase, float t_nm)` (bilinear; θ wrapped into [0, pole pitch) periodically; t clamped to [0, t_max]). `theta_phase` is the phase's own angle (phase A frame, θ − k·ε).
- `tests/sil/sil_fixtures.py` (shared by later tasks): `analytic_motor(n_phases=4, n_rotor_poles=6, resistance=0.5, bus_voltage=48.0, saturating=True) -> MotorData`. Model: L(θ) = L_u + (L_a − L_u)·(1 + cos(N_r·θ))/2 with L_u = 1 mH, L_a = 8 mH; linear: ψ = L(θ)·i; saturating: ψ = ψ_s·tanh(L(θ)·i/ψ_s), ψ_s = 0.08 Wb. Currents 0..20 A (21 points), angles 48 uniform over the pole pitch. Torque = ∂W′/∂θ at constant i with W′ = ∫ψ di (analytic for the linear case; for the saturating case W′ = ψ_s²/L·ln cosh(L i/ψ_s), differentiate analytically in θ). Phase A aligned at θ = 0.

- [ ] **Step 1: Failing tests** `tests/sil/test_sil_tables.py`:
  - `test_roundtrip_error_small`: `sim_tables(analytic_motor())` → `roundtrip_error < 1e-4`.
  - `test_current_matches_analytic`: at 10 random (θ, i ≤ 20 A) the bilinear lookup of `current` at ψ(θ,i) is within 0.2 % of i (saturating model).
  - `test_extrapolates_beyond_map`: lookup with ψ = 1.1·psi_max gives a current above the row's top current and finite.
  - `test_w_field_linear`: linear model → `w_field` = ψ²/(2L(θ)) within 0.1 %.
  - `test_i_of_t_rules`: at θ in the falling-inductance half (sin(N_r θ) > 0 region gives T < 0 for this model) every entry is 0; at a rising-inductance θ entries are non-decreasing and T(θ, i_of_t) ≈ T_j within 1 % where reachable.
  - `test_motor_data_from_json`: built from a dict shaped like the stored evaluation JSON; missing `winding` → `ValueError`.
  - `test_header_compiles_and_matches(tmp_path)`: write the header, a C file calling `srm_i_of_t` at 5 points exported through a function; `build.compile_host`, call in a child (reuse the helper from Task 1 by moving it into `sil_fixtures.call_in_child(lib, name, *float_args) -> float`) → matches a numpy bilinear lookup within 1e-5 relative.
- [ ] **Step 2:** Run `python -m pytest tests/sil/test_sil_tables.py -v` → FAIL.
- [ ] **Step 3:** Implement `tables.py` and the fixture.
- [ ] **Step 4:** Same command → PASS.
- [ ] **Step 5:** Commit `feat(sil): motor tables, controller header writer, analytic test motor`.

### Task 3: C sim core (motor, mechanics, converter, PWM, scheduler) and the in-process runner

**Files:**
- Create: `src/srmsil/c/srm_hal.h`, `src/srmsil/c/srm_ctrl.h` (exactly as spec §5, plus `float (*vbus_volts)(void);` in `srm_hal_t` — the bus voltage a real driver measures — and `typedef enum { SRM_CMD_TORQUE, SRM_CMD_SPEED } srm_cmd_mode_t;` in `srm_ctrl.h`), `src/srmsil/c/sim/srm_sim.h`, `src/srmsil/c/sim/srm_sim.c` (scheduler, HAL implementation, trace), `src/srmsil/c/sim/srm_motor.c` (table lookup, Heun step), `src/srmsil/c/sim/srm_converter.c` (switch logic, delays, voltages), `src/srmsil/scenario.py`, `src/srmsil/_abi.py` (ctypes mirrors), `src/srmsil/run.py` (in-process part only: `_run_loaded`)
- Test: `tests/sil/test_sil_core.py`, test controllers `tests/sil/controllers/open_loop/open_loop.c`, `tests/sil/controllers/volt_step/volt_step.c`

**Interfaces:**
- Consumes: `tables.SimTables`, `tables.MotorData`, `build.compile_host`.
- Produces:
  - `scenario.ConverterSettings` (frozen, `extra="forbid"`): `v_switch: float = 1.0`, `v_diode: float = 1.0`, `dead_time: float = 0.5e-6`, `turn_on_delay: float = 0.1e-6`, `turn_off_delay: float = 0.2e-6` (V, s).
  - `scenario.Scenario` (frozen, `extra="forbid"`): `mode: Literal["fixed","dynamic"] = "fixed"`, `speed_rpm: float = 1000.0` (fixed speed, or initial speed in dynamic), `duration: float = 0.02`, `dt: float = 0.5e-6`, `command_mode: Literal["torque","speed"] = "torque"`, `command_value: float = 0.0` (N·m or rpm), `inertia: float = 1e-3`, `friction: float = 0.0` (N·m·s/rad), `load: float = 0.0`, `load_step: float = 0.0`, `load_step_time: float = 0.0`, `theta0: float = 0.0`, `bus_voltage: float | None = None` (None → `MotorData.bus_voltage`), `pwm_hz: float = 20000.0`, `isr_hz: float | None = None` (None → `pwm_hz`), `compute_delay: float | None = None` (None → 1/isr_hz), `seed: int = 0`, `params: dict[str, float] = {}`, `converter: ConverterSettings = ConverterSettings()`, `sensors: SensorSettings = SensorSettings()` with only `encoder_cpr: int = 4096` in this task (ideal encoder; Task 4 adds the other sensor fields and `adc`). Validators: all times and rates > 0; `n_steps = round(duration/dt)` ≤ `MAX_STEPS` = 50_000_000 else `ValueError`.
  - C (`srm_sim.h`): `#define SRM_SIM_ABI 1`; `SRM_SIM_API` export macro (dllexport on Windows under `SRM_SIM_BUILD`); structs `srm_sim_config_t` (all scenario numbers as doubles/ints, `n_phases`, `n_rotor_poles`, `resistance`, `bus_voltage`, `trace_stride`, `n_steps`), `srm_sim_tables_t` (`n_theta, n_psi, theta_step, psi_step, const double *current, *torque, *w_field`), `srm_sim_trace_t` (`n_samples`, pointers to caller-owned arrays: `t, theta, omega, torque, encoder` [n], and per phase `i, psi, v, gate_u, gate_l, adc_i` [n × n_phases, phase-major]), `srm_sim_summary_t` (`beyond_map_steps`, `energy_in, energy_mech, energy_copper, w_field_start, w_field_end`). Exports: `int srm_sim_abi(void)`, `size_t srm_sim_sizeof_config(void)` (and one per struct), `int srm_sim_param(const char *name, float value)` (forwards to `ctrl_param`), `int srm_sim_run(const srm_sim_config_t*, const srm_sim_tables_t*, srm_sim_trace_t*, srm_sim_summary_t*)` (0 ok).
  - Sim behaviour, as spec §6: ψ_k state, Heun with v held over the step; θ_k = θ − k·ε wrapped into [0, pole pitch); bilinear on the uniform grids; ψ above psi_max extrapolates linearly from the last two ψ columns and increments `beyond_map_steps`; ψ < 0 after a step → 0 (diode clamp). Converter per phase from effective gates (commanded gates delayed: rising edge by `dead_time + turn_on_delay`, falling edge by `turn_off_delay`, rounded to dt): both on → V_bus − 2·v_switch; exactly one on → −(v_switch + v_diode) while i > 0 else 0; both off → −(V_bus + 2·v_diode) while i > 0 else 0. PWM per phase: centre-aligned triangle c(t) from 0 (t = k/f) to 1 (t = (k+½)/f); upper on when c > 1 − duty; hard chop: lower follows upper; soft chop: lower on. `set_switches` puts the phase in direct mode until the next `set_pwm`. ISR at t = (k+½)/isr_hz; `ctrl_slow` every 1 ms; gate commands made in an ISR take effect `compute_delay` later. Fixed mode: θ = θ0 + ω t. Dynamic: J ω̇ = ΣT − B ω − T_load(t) by Heun with the motor states. Encoder/ADC are ideal in this task (Task 4 adds errors). Energies integrate ∫Σv·i, ∫T·ω, ∫ΣR·i² by the trapezoid rule each step.
  - `run.SimSummary` frozen dataclass: `mean_torque, ripple_pct` (peak-to-peak / |mean| × 100 over the last `summary_window` = last 50 % of the run), `i_rms` (per phase, array), `copper_loss, power_in, power_mech` (means over the window), `beyond_map_fraction`, `energy_error` = |E_in − E_mech − E_cu − ΔW| / max(E_in, tiny), `roundtrip_error` (from `SimTables`).
  - `run.SimResult` frozen dataclass: `traces: dict[str, np.ndarray]` (keys `t, theta, omega, torque, encoder`, and `i, psi, v, gate_u, gate_l, adc_i` shaped (n_phases, n)), `summary: SimSummary`, `scenario: Scenario`, `controller: str`, `source_hash: str`, `compile_log: str`.
  - `run._run_loaded(lib_path: Path, m: MotorData, scenario: Scenario) -> SimResult` — **only ever called inside the child** (Task 5 adds the child wrapper; in this task tests call it through `sil_fixtures.call_in_child`-style spawn helper `run_in_child(fn, *args)`). Checks `srm_sim_abi()` and every `sizeof` against `ctypes.sizeof` first (`RuntimeError` on mismatch); calls `srm_sim_param` for each `scenario.params` (non-zero → `ValueError(f"controller rejected parameter {name!r}")`); `trace_stride = ceil(n_steps / TRACE_CAP)`, `TRACE_CAP = 2_000_000`.
  - `run.sim_library(controller_dir: Path, header_dir: Path, cache_dir: Path) -> Path`: `compile_host(sim sources + controller_sources(controller_dir), [c/, c/sim, header_dir, controller_dir], cache_dir / "sil" / "build")`.
- Test controllers: `open_loop` — params `theta_on`, `theta_off` (rad, phase frame), drives each phase with `set_switches(k,1,1)` inside [θ_on, θ_off) of its own angle (from `encoder_count` → angle), `(0,0)` outside. `volt_step` — keeps phase A with both switches on from t = 0, others off (for the small-signal test).

- [ ] **Step 1: Failing tests** `tests/sil/test_sil_core.py` (all use `analytic_motor`; each run in a spawned child):
  - `test_single_pulse_matches_envelope`: analytic motor (aligned at θ = 0, unaligned at τ/2), fixed 1000 rpm, 48 V, `open_loop` with θ_on = 0.5·τ, θ_off = 0.7·τ (phase frame), `isr_hz = 1e6`, `compute_delay = dt`, `encoder_cpr = 2**20`, ideal converter (all drops and delays 0), `dt = 0.25e-6`, duration 3 electrical periods. Assert the flux of each phase is back to 0 before its alignment, and the mean torque over the last 2 periods is within 1 % of q × the one-phase stroke average from `srmapp.drive.envelope._simulate` on `_Tables` built from the same `MotorData` (read `envelope()` for its angle origin and on/off index convention, and convert the angles accordingly).
  - `test_dt_convergence`: dt 1e-6 vs 0.5e-6 → mean torque and per-phase RMS current within 0.2 %.
  - `test_energy_balance`: linear analytic motor (torque exactly −∂W/∂θ), PWM-free open loop with drops > 0 → `energy_error < 0.005`.
  - `test_small_signal_l_inc`: fixed 0 rpm at θ with a known ∂ψ/∂i, `volt_step` with bus 1 V and drops 0 starting from ψ = 0: initial di/dt over the first 20 µs within 2 % of V/L_inc from the analytic model.
  - `test_diode_clamp_and_voltages`: after turn-off, v = −(V_bus + 2·v_diode) while i > 0, then i = ψ = 0 and v = 0; no negative current anywhere.
  - `test_switch_delays`: with dead_time + turn_on_delay = 2 µs, the first sample of v > 0 is 2 µs (± dt) after the ISR's effective command time.
  - `test_beyond_map_flagged`: bus 400 V, long conduction → `beyond_map_fraction > 0`, all traces finite.
  - `test_standstill_fixed`: fixed 0 rpm runs and gives finite traces.
  - `test_max_steps_rejected`: `Scenario(duration=100.0, dt=1e-6)` → `ValueError`.
  - `test_unknown_param_rejected`: `params={"nope": 1}` → `ValueError` naming it.
- [ ] **Step 2:** `python -m pytest tests/sil/test_sil_core.py -v` → FAIL.
- [ ] **Step 3:** Implement headers, sim C, `_abi.py`, `scenario.py`, `run._run_loaded`, `run.sim_library`, test controllers.
- [ ] **Step 4:** Same command → PASS.
- [ ] **Step 5:** Commit `feat(sil): C simulation core, scenario and in-process runner`.

### Task 4: Sensors and ADC

**Files:**
- Create: `src/srmsil/c/sim/srm_sensors.c`
- Modify: `src/srmsil/c/sim/srm_sim.h`, `srm_sim.c`, `src/srmsil/scenario.py`, `src/srmsil/_abi.py`, `src/srmsil/run.py`
- Test: `tests/sil/test_sil_sensors.py`, test controller `tests/sil/controllers/probe/probe.c` (reads every channel each ISR and leaves gates off; the trace's `adc_i` and `encoder` channels record what the HAL returned)

**Interfaces:**
- Produces:
  - `scenario.SensorSettings` (Task 3 created it with `encoder_cpr: int = 4096`; add): `encoder_offset: float = 0.0` (rad), `encoder_ecc_amp: float = 0.0` (rad), `encoder_ecc_harmonic: int = 1`, `resolver: bool = False`, `resolver_pole_pairs: int = 1`, `resolver_bits: int = 12`, `resolver_gain_mismatch: float = 0.0` (cos amplitude = 1 + mismatch, sin = 1), `resolver_phase_error: float = 0.0` (rad, added to the cos argument).
  - `scenario.AdcSettings`: `bits: int = 12`, `full_scale: float | None = None` (A at the top code; None → 1.25 × `MotorData` top current), `offset_counts: int = 0` (nominal zero-current code, given to the controller in `adc_offset_counts`), `offset_error: float = 0.0` (counts), `gain_error: float = 0.0` (relative), `noise: float = 0.0` (σ, counts, Gaussian), `rc_tau: float = 0.0` (s, first-order filter on the sensed current before sampling; 0 = none).
  - `Scenario` gains `sensors: SensorSettings = SensorSettings()`, `adc: AdcSettings = AdcSettings()`.
  - Behaviour: encoder count = floor((θ_meas mod 2π)·cpr/2π) as uint32 with θ_meas = θ + offset + ecc_amp·sin(h·θ) (and multi-turn wrap kept in a uint32 counter that increments with rotation); resolver sin/cos = round(A·sin(p·θ_meas)), round(A·(1+mismatch)·cos(p·θ_meas + phase_error)), A = 2^(bits−1) − 1; ADC code = clamp(round(offset_counts + offset_error + i_f·(1 + gain_error)/amps_per_count + noise), 0, 2^bits − 1) with amps_per_count = full_scale/(2^bits − 1) and i_f the RC-filtered current, sampled at the ISR instant; RNG = a seeded xorshift64* + Box–Muller in C (deterministic for a seed across platforms). `adc_i` trace = (code − offset_counts)·amps_per_count of the last conversion.

- [ ] **Step 1: Failing tests** `tests/sil/test_sil_sensors.py`:
  - `test_adc_quantisation`: noise 0 → `adc_i` differs from the true sampled current by ≤ ½ LSB, and codes saturate at 2^bits − 1 for currents above full scale.
  - `test_adc_noise_sigma_and_seed`: zero current, offset_counts 2048, noise 3 → sample std of codes within 10 % of 3 over ≥ 10 000 samples; same seed → identical trace; different seed → different.
  - `test_adc_offset_and_gain_error`: constant current → mean reading shifted/scaled as set.
  - `test_rc_filter_step`: after a current step the reading reaches 63 % at τ within one ISR period.
  - `test_encoder_count_and_eccentricity`: fixed speed, ecc 0 → count advances by cpr per revolution; ecc_amp 0.01 rad, harmonic 2 → count − ideal follows 0.01·sin(2θ)·cpr/2π within 1 count.
  - `test_resolver_mismatch`: atan2 of the raw sin/cos recovers p·θ within the expected error envelope for the set mismatch and phase error.
- [ ] **Step 2:** `python -m pytest tests/sil/test_sil_sensors.py -v` → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `python -m pytest tests/sil/test_sil_sensors.py tests/sil/test_sil_core.py -v` → PASS.
- [ ] **Step 5:** Commit `feat(sil): encoder, resolver and ADC models`.

### Task 5: Isolated runs, decimation, public `run`

**Files:**
- Modify: `src/srmsil/run.py`
- Test: `tests/sil/test_sil_run.py`, test controllers `tests/sil/controllers/crash/crash.c` (null write in `ctrl_isr`), `tests/sil/controllers/hang/hang.c` (endless loop in `ctrl_isr`), `tests/sil/controllers/broken/broken.c` (no `ctrl_isr`: link fails)

**Interfaces:**
- Produces:
  - `run.SimError(Exception)` with `log: str` (compile log or child error text).
  - `run.REFERENCE = {"hysteresis", "pwm_current", "tsf"}` and `run.controller_dir(controller: str) -> Path` (reference name → `src/srmsil/c/controllers/<name>`; else the given folder, checked by `build.controller_sources`).
  - `run.run(m: MotorData, controller: str, scenario: Scenario, *, cache_dir: Path, timeout_s: float = 300.0) -> SimResult`: writes the header for `m` (`tables.write_header`) into a temp header dir, `sim_library` (a `CompileError` → `SimError(log)`), then a spawned child runs `_run_loaded` and saves the result to an npz plus a JSON sidecar; the parent waits `timeout_s`, kills the child on timeout (`SimError("timed out after N s")`), maps a non-zero exit code without a result to `SimError("the controller crashed (exit code N)")`, and re-raises a child `ValueError` text as `SimError`. Reference controllers also get `src/srmsil/c/controllers/common` on the include path and its `.c` files in the sources.
  - `run.save(result: SimResult, path: Path)` / `run.load(path: Path) -> SimResult` (npz + JSON for scenario/summary/strings; write to `*.tmp.npz` then rename).
  - `run.decimate(t: np.ndarray, y: np.ndarray, n_px: int) -> tuple[np.ndarray, np.ndarray]`: when `len(t) ≤ 2·n_px` return as is; else per bucket of equal sample count emit the min and the max of `y` in time order of their occurrence, with their times.

- [ ] **Step 1: Failing tests** `tests/sil/test_sil_run.py`:
  - `test_run_open_loop_end_to_end(tmp_path)`: `run(analytic_motor(), str(open_loop_dir), Scenario(duration=0.005, params=...), cache_dir=tmp_path)` returns finite traces; a second identical run reuses the cached library (same `source_hash`).
  - `test_crash_is_sim_error`, `test_hang_times_out` (`timeout_s=5`), `test_link_error_carries_log` (`"ctrl_isr" in exc.log`): each raises `SimError` and the test process is alive afterwards (run a trivial `open_loop` run after each).
  - `test_bad_folder_is_value_error`: missing folder → `ValueError`.
  - `test_save_load_roundtrip(tmp_path)`.
  - `test_decimate_keeps_extremes`: a 1 MHz sawtooth of 1e6 samples decimated to 1000 px keeps global min and max exactly; `n_px` larger than the data returns the input unchanged.
- [ ] **Step 2:** `python -m pytest tests/sil/test_sil_run.py -v` → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Same command → PASS.
- [ ] **Step 5:** Commit `feat(sil): isolated child-process runs, save/load and decimation`.

### Task 6: Reference controllers — common code, hysteresis, PWM current

**Files:**
- Create: `src/srmsil/c/controllers/common/srm_ref.h`, `srm_ref.c`; `src/srmsil/c/controllers/hysteresis/hysteresis.c`, `README.md`; `src/srmsil/c/controllers/pwm_current/pwm_current.c`, `README.md`
- Test: `tests/sil/test_sil_ref_current.py`

**Interfaces:**
- Consumes: `srm_hal.h`, `srm_ctrl.h`, `srm_motor_tables.h` (Task 2 names), `run.run`.
- Produces (`srm_ref.h`, shared by all three reference controllers):
  - `float srm_ref_angle(const srm_hal_t *hal)` (mechanical rad from the encoder, or from the resolver by atan2 / pole pairs when `encoder_cpr == 0`), `float srm_ref_phase_angle(float theta, uint8_t k)` (θ − k·SRM_STROKE_RAD wrapped into [0, pole pitch)), `float srm_ref_el_deg(float theta_phase)` (electrical degrees from unaligned: (θ_phase·N_r·180/π + 180) mod 360), `float srm_ref_current(const srm_hal_t*, uint8_t k)` ((code − offset)·amps_per_count), speed estimate from angle differences in `ctrl_slow` with a first-order filter (param `speed_filter_hz`, default 50), speed PI → torque command (`speed_kp` default 0.05 N·m/(rad/s), `speed_ki` default 0.5, `torque_limit` default SRM_T_MAX_NM, anti-windup by clamping), and a parameter table helper so each controller's `ctrl_param` is a lookup in `{name, float*}` pairs.
  - Window parameters (electrical degrees from unaligned): `theta_on` default 0, `theta_off` default 150.
  - hysteresis: param `band` (A, default 0.05·SRM_I_MAX_A), `soft` (default 1 = soft chopping: lower stays on, upper toggles; 0 = hard), `isr_hz` set by the scenario (the README states 50 kHz is the intended rate). i_ref = `srm_i_of_t(window centre, T_cmd)`. Inside the window: i < i_ref − band/2 → both on; i > i_ref + band/2 → upper off (soft) or both off (hard); outside the window → both off.
  - pwm_current: params `kp` (V/A, default SRM_L_MIN_H·2π·f_bw), `ki` (V/(A·s), default SRM_R_OHM·2π·f_bw), `f_bw` (Hz, default `pwm_hz`/20, applied when kp/ki are not given), soft chopping duty = clamp(v_ref / vbus, 0, 1) via `set_pwm`; integrator clamps at the duty limits; outside the window `set_switches(k, 0, 0)` and integrator reset.
- [ ] **Step 1: Failing tests** `tests/sil/test_sil_ref_current.py` (analytic saturating motor; ideal sensors unless stated):
  - `test_hysteresis_stays_in_band`: 300 rpm, torque command 0.5·t_max, `isr_hz=50e3`: inside each window after the first rise, i stays within i_ref ± band/2 plus one ISR period of rise (max di/dt × 1/isr_hz).
  - `test_pwm_current_tracks_step`: 300 rpm, a torque command; the phase current settles to i_ref within 1 ms of window start and the mean error over the flat part is < 2 % of i_ref.
  - `test_speed_mode_reaches_speed`: dynamic, start 0 rpm, command 500 rpm, J = 1e-4, pwm_current: speed within 5 % of 500 rpm after 0.3 s (mark `slow` if this takes > 20 s on the laptop).
  - `test_reference_controllers_target_check`: `build.target_check` on each folder (+ common, + a header from `analytic_motor`) → `ok`.
  - `test_unknown_param_rejected_by_reference`: `params={"nope": 1}` → `SimError`/`ValueError` naming it.
- [ ] **Step 2:** `python -m pytest tests/sil/test_sil_ref_current.py -v` → FAIL.
- [ ] **Step 3:** Implement; READMEs list each parameter, unit and default.
- [ ] **Step 4:** Same command → PASS.
- [ ] **Step 5:** Commit `feat(sil): reference hysteresis and PWM current controllers`.

### Task 7: TSF reference controller

**Files:**
- Create: `src/srmsil/c/controllers/tsf/tsf.c`, `README.md`
- Test: `tests/sil/test_sil_ref_tsf.py`

**Interfaces:**
- Consumes: `srm_ref.h` (Task 6), `srm_i_of_t`.
- Produces: params `theta_on` (el deg, default 15), `overlap` (el deg, default 30), plus pwm_current's `kp, ki, f_bw`. Share of phase k at its electrical angle φ: s(x) = 3x² − 2x³; rise over [θ_on, θ_on + overlap], 1 until θ_on + stroke_el, fall over [θ_on + stroke_el, θ_on + stroke_el + overlap], 0 elsewhere, with stroke_el = 360/q. Phase torque T_k = s_k·T_cmd; i_ref,k = `srm_i_of_t(θ_phase,k, T_k)`; PWM current loop per phase as in pwm_current; a phase with s = 0 → both switches off.
- [ ] **Step 1: Failing tests** `tests/sil/test_sil_ref_tsf.py`:
  - `test_shares_sum_to_one`: a numpy copy of the share function over a full electrical period sums to 1 at every angle (q = 3 and 4).
  - `test_tsf_lower_ripple_than_hysteresis`: 200 rpm, same torque command (0.3·t_max), pwm 20 kHz for TSF and isr 50 kHz for hysteresis: both means within 10 % of the command, TSF `ripple_pct` < hysteresis `ripple_pct`.
  - `test_tsf_target_check`: compiles for the target.
- [ ] **Step 2:** `python -m pytest tests/sil/test_sil_ref_tsf.py -v` → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Same command → PASS.
- [ ] **Step 5:** Commit `feat(sil): TSF reference controller`.

### Task 8: srmweb — control job and routes

**Files:**
- Modify: `src/srmweb/jobs.py` (`STEPS["control"] = ("queued", "compile", "simulate", "saved")`, `KINDS["control"]`, main lane), `src/srmweb/schemas.py`, `src/srmweb/api.py`, `src/srmweb/results.py` if responses live there
- Test: `tests/web/test_web_control.py`, extend `tests/web_support.py` with `analytic_evaluation()` (an `Evaluation` whose `map` is `analytic_motor()`'s arrays, a winding with `resistance` 0.5, status ok)

**Interfaces:**
- Consumes: `srmsil.tables.motor_data_from_json`, `srmsil.run.run/save/load/decimate/SimError/REFERENCE`, `srmsil.build.target_check`, `srmweb.config.is_loopback`, `srmweb.frames.pack`.
- Produces:
  - `schemas.ControlIn`: `controller: str` (a reference name or an absolute folder path), `scenario: srmsil.scenario.Scenario`. `schemas.ControlRequest`: `case_id`, `motor` (the `MotorData` fields as lists/floats), `controller`, `scenario`.
  - `POST /api/cases/{id}/control` → 201 `{job_id}`. 409 "evaluate this case first" unless the case is evaluated with status ok and a winding (same rule as `field_context`). A non-reference controller: 403 "custom controllers run only when srmweb is bound to a loopback host" unless `is_loopback(settings.host)`; then 422 if the folder is invalid (`build.controller_sources`). Scenario validation errors (incl. `MAX_STEPS`) → 422. `bus_voltage` defaults to the case's `requirements.bus_voltage_v`.
  - Job `run_control_job`: step `compile` then `simulate` (progress message only); calls `run.run(..., cache_dir=settings.cache_dir)`, saves to `<cache_dir>/sil/runs/<job_id>.npz`, returns `{case_id, controller, summary, source_hash, compile_log, run_file}`. `SimError` → job failed with `error` = the message plus the log.
  - `GET /api/jobs/{id}/control?n_px=1500` (n_px 100..10000): binary `pack` with meta `{summary, scenario, controller, n_phases}` and float32 arrays per channel (`t.<name>` and `y.<name>` after `decimate`; per-phase channels named `i.0`, `i.1`, …); 404 if not a done control job, 410 if the run file was cleared.
  - `GET /api/cases/{id}/control/header` → `srm_motor_tables.h` as `text/x-c` attachment.
  - `POST /api/control/target-check` body `{controller, case_id}` → `{ok, compiler, log}` (same 403/422 rules; runs in the request thread, compile-only, no owner code executes).
  - `GET /api/control/controllers` → reference names with their parameter names, units and defaults (parsed once from a `PARAMS` table in `srmsil.run`, which mirrors the READMEs).
  - `cache_files()` also counts `sil/runs/*.npz` and `sil/build/*` (not `*.tmp.*`); clearing deletes them.
  - Regenerate `web/openapi.json` and `web/src/api/schema.ts` (`python -m srmweb.openapi web/openapi.json; cd web; npm run gen:api`).
- [ ] **Step 1: Failing tests** `tests/web/test_web_control.py` (use `make_client`; run jobs synchronously the way existing web job tests do):
  - `test_control_reference_runs`: evaluated analytic case, `hysteresis`, 5 ms → job done; `GET /api/jobs/{id}/control?n_px=500` decodes and has `i.0` with ≤ 1000 points and the summary.
  - `test_control_needs_evaluated_case` (409), `test_custom_folder_refused_off_loopback` (settings host `0.0.0.0` + token → 403), `test_custom_folder_invalid` (loopback, missing folder → 422), `test_scenario_too_long` (422).
  - `test_crashing_controller_fails_job`: the `crash` test controller → job `failed`, error mentions "crashed", server still answers `/api/health`.
  - `test_header_download`, `test_target_check_route`, `test_controllers_list`, `test_cache_counts_and_clears_sil_files`.
- [ ] **Step 2:** `python -m pytest tests/web/test_web_control.py -v` → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `python -m pytest tests/web/test_web_control.py tests/web -q -x` → PASS.
- [ ] **Step 5:** Commit `feat(web): control job, routes and target check`.

### Task 9: Control tab (web UI)

**Files:**
- Create: `web/src/api/control.ts`, `web/src/lib/control.ts`, `web/src/lib/control.test.ts`, `web/src/components/analysis/ControlTab.tsx`, `web/src/components/analysis/ControlTab.test.tsx`
- Modify: `web/src/components/analysis/AnalysisTabs.tsx` (tab "Control" when `showField`), `web/src/lib/steps.ts` if step labels are per kind

**Interfaces:**
- Consumes: Task 8 routes; `decode` from `web/src/lib/fieldWire.ts`; `useJobEvents`; `plotTheme`, `LINE_COLORS`/`LINE_DASHES`; `JobStepper`.
- Produces:
  - `lib/control.ts`: `scopesFromWire(buf) -> { meta, channels: Record<string, {t: Float32Array, y: Float32Array}> }`, `defaultScenario(bus_voltage) -> Scenario`, `scenarioErrors(s) -> Record<string,string>` (mirrors the server limits: positive times, `MAX_STEPS`), unit helpers rpm ↔ rad/s and el deg for display.
  - `ControlTab({caseId, busVoltage})`: controller select (reference names from `/api/control/controllers` plus "Custom folder…" with a path input), parameter inputs with defaults and units, scenario form (mode, speed rpm, duration ms, command mode/value, J, B, load, load step and time; converter/sensors/ADC in a collapsed "Hardware" section), Run (disabled while a control job of this case runs; shows `JobStepper`), then stacked Plotly scopes with shared x axis (phase currents true vs ADC, ψ, torque, speed, gates as step lines), a summary row (mean torque, ripple %, RMS current, copper loss, beyond-map % with a warning chip when > 0, "phases uncoupled" note), a "Check for target" button showing ok/fail with the log in a `<pre>`, and "Download srm_motor_tables.h". Scopes refetch with `n_px` = plot width on zoom (relayout `xaxis.range` → `?n_px=` and a `t0,t1` window is out of scope: refetch full range at higher `n_px` only).
- [ ] **Step 1: Failing tests**: `control.test.ts` — `scopesFromWire` on a packed buffer built in the test, `scenarioErrors` flags duration/dt over `MAX_STEPS` and non-positive values; `ControlTab.test.tsx` — renders the reference list from a mocked fetch, the custom-folder input appears when chosen, Run posts the expected body, a failed job shows its log.
- [ ] **Step 2:** `cd web; npx vitest run src/lib/control.test.ts src/components/analysis/ControlTab.test.tsx` → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `cd web; npx vitest run; npm run build` → PASS, including `noBlue.test.ts`.
- [ ] **Step 5:** Commit `feat(web): Control tab with scopes, target check and header download`.

### Task 10: Docs, versions, full check

**Files:**
- Modify: `CLAUDE.md` (srmsil section: layout, HAL contract, commands, test notes, current state line), `src/srmweb/__init__.py` and `web/package.json` and `srmsil.__version__` → `0.6.0`, `docs/superpowers/specs/2026-10-19-r8a-control-sil-design.md` (status: implemented; note the `vbus_volts` HAL addition and `compute_delay` default of one ISR period)
- Create: `examples/control_sil.py` (runs `hysteresis` and `tsf` on a stored case id or on the analytic motor and prints the summaries)

- [ ] **Step 1:** Update docs and versions; write the example.
- [ ] **Step 2:** `python examples/control_sil.py` → prints two summaries.
- [ ] **Step 3:** Full fast suite once: `python -m pytest -m "not slow"` → all pass; `cd web; npx vitest run; npm run build` → pass.
- [ ] **Step 4:** Commit `docs: R8a control SIL in CLAUDE.md, versions 0.6.0, example`.
