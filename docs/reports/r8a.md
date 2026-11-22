# R8a: Control software-in-the-loop

Merged 2026-10-20, PR #6. Versions after the merge: srmsil, srmweb and `web/` 0.8.0 (srmcore and srmapp stay 0.6.0).
Spec `docs/superpowers/specs/2026-10-19-r8a-control-sil-design.md`. Plan `docs/superpowers/plans/2026-10-19-r8a-control-sil.md`. Detailed results: none.

## Goal

Run the owner's portable controller C against a simulated SRM drive built from an evaluated case. Done when a reference controller runs in the simulation and the same file compiles for a target.

## What shipped

- `src/srmsil`: HAL (`srm_hal.h`), controller contract (`srm_ctrl.h`), portable C simulation (motor, converter, sensors, scheduler), zig build with a Cortex-M7 target check, `MotorData` from an evaluation.
- Reference controllers: hysteresis, PWM current, TSF.
- Isolation: controller C runs in a spawned child process. A custom folder runs only on a loopback host.
- Web: job kind `control`, routes under `/api/cases/{id}/control` and `/api/control/`, and the Control tab.
- `examples/control_sil.py`.

## Results

| Check or measurement | Value | Where measured |
| --- | --- | --- |
| Single pulse against the existing drive model | within 0.1 % | `tests/sil` |
| Energy balance error | about 1e-5 | `tests/sil` |
| Small-signal di/dt against L_inc | within 2 % | `tests/sil` |
| Ripple at equal mean torque | TSF 28 %, hysteresis 65 % | `tests/sil` |
| Fast suite after the merge | 1356 passed | main with #4 and #5 |
| vitest | 257 passed | same |

## Decisions

- 2026-10-19, owner: the tool defines the HAL (grblHAL style).
- 2026-10-19, owner: motor model, converter and sensors are portable C, so the same code later runs on the emulator board.
- 2026-10-19, owner: the controller is a folder compiled by the `ziglang` pip compiler and run in a child process.
- 2026-10-19, owner: no reference HFI controller in R8a (a test checks the small-signal response against L_inc instead).

## Open after this step

- The hardware loop (R8b, merged 2026-10-29).
- HFI from L_inc is not a reference controller.

## Evidence

Ten tasks, subagent-driven, each reviewed. Reviews caught a wrong multi-turn encoder angle, a speed test hiding a 2x overshoot, conduction windows that could not wrap through 0 deg, an unbounded loop in the TSF interrupt, a ripple comparison not made at equal mean torque and a loopback bypass through job resume. The final review led to one fix wave. After the merge the Control tab was checked in the browser and web and layering pytest passed (306). CI result: not recorded.
