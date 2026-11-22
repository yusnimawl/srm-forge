# R8b: Control HIL

Merged 2026-10-29, PR #8. Versions after the merge: srmsil 0.9.0, srmweb and `web/` 0.10.0 (srmcore and srmapp stay 0.7.0).
Spec `docs/superpowers/specs/2026-10-20-r8b-control-hil-design.md`. Plan `docs/superpowers/plans/2026-10-20-r8b-control-hil.md`. Detailed results `docs/r8b-hil-results.md`, wiring `docs/r8b-hil-wiring.md`.

## Goal

Run the owner's controller C unchanged on a Nucleo-H723ZG against a Teensy 4.1 that emulates the SRM drive in real time. Done when each reference controller spins the emulated 8/6 and matches the matched SIL within 3 % (mean torque, RMS current) and 5 points (median ripple).

## What shipped

- `hil/` PlatformIO firmware for both boards and `src/srmsil/hil` (protocol, transport, config, build, session, compare, fake rig).
- A plant shared by the PC SIL and the emulator, and `srm_emu.c`, the PC build of the emulator model that CI compares with the SIL at 1 %.
- Build-time modes: AD7606 or internal current sensing, encoder or AD2S1210 position.
- `srmweb/hil.py`, the HIL routes, job kind `hil_flash` and the HIL mode of the Control tab.
- `examples/control_hil.py` and `examples/hil_emu_selftest.py`. `.github/workflows/hil.yml` compiles both environments.

## Results

| Check or measurement | Value | Where measured |
| --- | --- | --- |
| Hysteresis, valid runs passing the SIL comparison | 25 of 25 | bench, ad7606 + encoder |
| pwm_current and tsf | 11 of 11 each | same |
| ad7606 + ad2s1210, hysteresis | 8 of 8 | bench |
| Emulator clock and step | 912 MHz, 6 us | Teensy 4.1 |
| Buffered capture length | 8192 samples (49 ms) | same |
| Captures lost, Windows host | 3 of 58 re-run captures | bench, 2026-10-24 |
| Captures lost, LattePanda (Linux) | 0 of 1305 | bench, 2026-11-03 |
| Internal current sensing | not run (no DACs) | bench |

## Decisions

- 2026-10-20, owner: Nucleo-H723ZG as controller, Teensy 4.1 as real-time emulator.
- 2026-10-23, owner: 912 MHz instead of 1008 MHz (1008 MHz fails timing), and a 6 us step as the fallback.
- 2026-10-24, builder: ripple is compared as the median over complete strokes, with the sensed-value age jitter in the matched SIL.
- 2026-10-29, builder: captures are capped at the 8192-sample ring (streamed longer captures do not keep up).
- 2026-11-03, owner: the LattePanda is the HIL bench host.

## Open after this step

- Streaming captures longer than 49 ms are unsupported.
- `internal` mode is compiled in CI but not benched.
- Two of 13 dynamic runs gave "no matched SIL scenario", not reproduced.
- pwm_current's step max is 84 to 86 % of the step, above the 80 % warning line.

## Evidence

Bench acceptance on 2026-10-24, then a whole-branch Opus review with one fix round (e586496) and a clean re-review. CI fixes made on the way: a Python 3.12 forward reference, the gmsh libraries in `hil.yml`, a 1e-9 plant golden tolerance, `tests/hil` marked slow, and the fast job timeout raised from 40 to 60 min. The fast suite took 40 min on a busy local machine. CI result for the PR: not recorded.
