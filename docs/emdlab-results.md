# EMDLAB / ANSYS Maxwell 8/6 comparison

## Summary

- srmcore `full` (NGSolve) on the 8/6 benchmark of the EMDLAB paper, 3.6 A on phase A, 30 angles from unaligned to aligned: torque agrees with ANSYS Maxwell within 2.99 % of the Maxwell peak (mean 1.0 %) and with EMDLAB within 3.78 % of the EMDLAB peak (mean 0.6 %). ψ is within 1.57 % of EMDLAB, W within 1.25 % and W′ within 2.55 %.
- The two reference tools differ from each other by up to 3.8 % of the peak torque (`tests/validation/fixtures/emdlab_8_6/README.md`), so srmcore sits inside their spread.
- On the rising edge (θ_tab 7° to 12°) srmcore follows Maxwell (worst 0.12 % of peak) and EMDLAB is off (3.78 %). On the plateau (θ_tab 12.4° to 30°) srmcore follows EMDLAB (worst 1.16 %) and reads up to 2.99 % above Maxwell. The peak torque is 5.372 N·m in srmcore, 5.392 in EMDLAB and 5.305 in Maxwell.
- ψ is above EMDLAB at every angle (+0.28 % to +1.57 %). EMDLAB's own convergence run at θ = −15° puts its ~11k-node mesh 0.45 % low in ψ against its 224k-node mesh, and its sweep mesh has about 8.5k nodes, so part of this offset is EMDLAB's mesh. At −15° srmcore gives ψ 0.40143 Wb against EMDLAB's finest 0.40162 (−0.05 %) and torque 5.352 against 5.360 N·m (−0.16 %).
- What agreement proves: srmcore reproduces two independent 2D tools (a commercial solver and an open-source one) on a published machine. What it does not prove: all three are 2D with the same B-H table, so end effects and material errors are not tested. Agreement with measurement is M5b and M5d.
- Reproduce with `$env:PYTHONPATH="tests"; python examples\emdlab_check.py`. The slow test is `tests/validation/test_emdlab.py`; the machine is `tests/emdlab_machine.py`. The sweep took about 13 s per point on the 4-CPU Claude cloud container (2026-10-30).

## Machine and assumptions

The machine is the paper's Table 3 and EMDLAB's `emdlab_examples_srm86.m`; the dimensions are in the fixture README. Assumed where the tools differ (`emdlab_machine.ASSUMED`):

| Field | Value used | Why |
|---|---|---|
| `stator_pole_taper`, `rotor_pole_taper` | 0 (parallel-sided teeth) | EMDLAB draws constant-width teeth; srmcore's flank runs parallel to the pole axis at taper 0 |
| `slot_liner_thickness` | 0.1 mm | EMDLAB's coil touches the tooth flank |
| `coil_inner_clearance` | 0.1 mm | EMDLAB's coil starts at the bore |
| `fill_factor` | 0.5 | sets resistance only, not ψ or torque |
| shaft | `copper` (vacuum law) | EMDLAB has no shaft and sets A = 0 at r = 10 mm |
| stator and rotor material | `M530_50A` (new library record, grade C) | EMDLAB's M530-50A table, stacking factor 1.0 as EMDLAB uses |
| band | 1392 circumferential divisions | the reference angles are steps of 2π/348; 1392 = 2 × lcm(24, 348) puts each on a band node, finer than the 888 the preset picks |

Angles: θ_tab = 0 is unaligned and 30° is aligned; the srmcore rotor angle is θ_tab − 30°. Torque is positive on the unaligned-to-aligned stroke in all three tools, with no sign change.

## Test limits

| Check | Limit | Worst |
|---|---|---|
| ψ against EMDLAB | 2 % relative | 1.57 % |
| W and W′ against EMDLAB | 3 % relative | 2.55 % (W′ at 11.4°) |
| torque against Maxwell | 5 % of the Maxwell peak | 2.99 % |
| torque against EMDLAB | 5 % of the EMDLAB peak | 3.78 % |
| aligned and unaligned torque | 0.5 % of the Maxwell peak | below 0.001 % |

The torque limit is the upper end of the fixture README's 3 to 5 % suggestion, because the two reference tools differ by 3.8 % from each other. The energy limit is wider than ψ's because W′ integrates ψ over current, so the rising-edge ψ offset is larger in W′.

## Per-angle results

| theta_tab (deg) | psi (Wb) | dpsi vs EMDLAB | dW | dW' | T (N m) | T Maxwell | dT / Maxwell peak | T EMDLAB | dT / EMDLAB peak |
|---|---|---|---|---|---|---|---|---|---|
| 0.00 | 0.15376 | +0.68% | +0.67% | +0.69% | +0.0000 | +0.0006 | -0.01% | +0.0000 | +0.00% |
| 1.03 | 0.15422 | +0.66% | +0.66% | +0.67% | +0.0921 | +0.0931 | -0.02% | +0.0900 | +0.04% |
| 2.07 | 0.15563 | +0.77% | +0.76% | +0.77% | +0.1880 | +0.1886 | -0.01% | +0.1834 | +0.08% |
| 3.10 | 0.15804 | +0.71% | +0.70% | +0.71% | +0.2918 | +0.2920 | -0.01% | +0.2867 | +0.09% |
| 4.14 | 0.16157 | +0.74% | +0.73% | +0.74% | +0.4094 | +0.4080 | +0.03% | +0.4001 | +0.17% |
| 5.17 | 0.16638 | +0.79% | +0.78% | +0.80% | +0.5494 | +0.5496 | -0.00% | +0.5366 | +0.24% |
| 6.21 | 0.17278 | +0.85% | +0.85% | +0.86% | +0.7259 | +0.7256 | +0.01% | +0.7048 | +0.39% |
| 7.24 | 0.18124 | +0.96% | +0.95% | +0.97% | +0.9635 | +0.9651 | -0.03% | +0.9336 | +0.55% |
| 8.28 | 0.19256 | +1.24% | +1.22% | +1.27% | +1.3097 | +1.3035 | +0.12% | +1.2444 | +1.21% |
| 9.31 | 0.20821 | +1.34% | +1.25% | +1.43% | +1.8672 | +1.8675 | -0.00% | +1.7614 | +1.96% |
| 10.34 | 0.23068 | +1.57% | +1.12% | +2.01% | +2.8456 | +2.8423 | +0.06% | +2.6416 | +3.78% |
| 11.38 | 0.26170 | +1.27% | -0.02% | +2.55% | +4.2403 | +4.2402 | +0.00% | +4.1002 | +2.60% |
| 12.41 | 0.29867 | +0.93% | -0.27% | +1.93% | +5.0311 | +4.9754 | +1.05% | +5.0935 | -1.16% |
| 13.45 | 0.33870 | +0.75% | -0.42% | +1.62% | +5.2610 | +5.1522 | +2.05% | +5.3008 | -0.74% |
| 14.48 | 0.38029 | +0.54% | -0.42% | +1.31% | +5.3408 | +5.2360 | +1.97% | +5.3494 | -0.16% |
| 15.52 | 0.42275 | +0.49% | -0.52% | +1.36% | +5.3691 | +5.3053 | +1.20% | +5.3852 | -0.30% |
| 16.55 | 0.46565 | +0.42% | -0.63% | +1.29% | +5.3722 | +5.2940 | +1.47% | +5.3918 | -0.36% |
| 17.59 | 0.50873 | +0.38% | -0.62% | +1.16% | +5.3569 | +5.2276 | +2.44% | +5.3672 | -0.19% |
| 18.62 | 0.55170 | +0.31% | -0.52% | +0.94% | +5.3234 | +5.2168 | +2.01% | +5.3162 | +0.13% |
| 19.66 | 0.59405 | +0.28% | -0.51% | +0.88% | +5.2620 | +5.2058 | +1.06% | +5.2535 | +0.16% |
| 20.69 | 0.63425 | +0.29% | -0.44% | +0.83% | +5.1284 | +5.0334 | +1.79% | +5.1480 | -0.36% |
| 21.72 | 0.67114 | +0.31% | -0.39% | +0.80% | +4.8934 | +4.7788 | +2.16% | +4.8676 | +0.48% |
| 22.76 | 0.70490 | +0.36% | -0.28% | +0.80% | +4.5754 | +4.5359 | +0.74% | +4.5561 | +0.36% |
| 23.79 | 0.73450 | +0.34% | -0.27% | +0.75% | +4.1661 | +4.1158 | +0.95% | +4.1420 | +0.45% |
| 24.83 | 0.75813 | +0.29% | -0.36% | +0.71% | +3.6672 | +3.5088 | +2.99% | +3.6601 | +0.13% |
| 25.86 | 0.77495 | +0.48% | -0.01% | +0.80% | +3.1297 | +2.9798 | +2.82% | +3.0893 | +0.75% |
| 26.90 | 0.78599 | +0.40% | -0.17% | +0.75% | +2.5789 | +2.4959 | +1.56% | +2.5651 | +0.26% |
| 27.93 | 0.79296 | +0.30% | -0.35% | +0.68% | +1.8648 | +1.7555 | +2.06% | +1.8741 | -0.17% |
| 28.97 | 0.79624 | +0.39% | -0.12% | +0.68% | +0.6374 | +0.5478 | +1.69% | +0.6820 | -0.83% |
| 30.00 | 0.79696 | +0.47% | +0.00% | +0.74% | +0.0000 | +0.0050 | -0.09% | +0.0000 | +0.00% |
