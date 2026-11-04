# R4 end-effect results

Spec: `docs/superpowers/specs/2026-11-03-r4-end-effects-design.md`.

## G0 cost spike

Run 2026-11-04 on the LattePanda (16 threads, 30 GB RAM, NGSolve 6.2.2608): the full TEAM 24 half model at 7.41 A, nonlinear steel, H(curl) order 2, CG with BDDC, gap_maxh = maxh / 8. Data: `docs/validation/r4_g0.json`.

| maxh (mm) | gap_maxh (mm) | Elements | Free DOFs | Mesh (s) | Solve (s) | Newton | Peak RSS (GB) | Result |
|---|---|---|---|---|---|---|---|---|
| 4.0 | 0.5 | 6 324 053 | 32 602 447 | 1328 | – | – | – | skipped (over the 12 M DOF cap) |
| 12.0 | 1.5 | 556 958 | 2 863 501 | 41 | 583 | 6 | 14.5 | converged: torque 2.828 N·m, rotor-pole flux 4.313e-4 Wb |
| 9.0 | 1.125 | 1 149 775 | 5 918 310 | 108 | 4049 | 1 | 30.3 | not converged; RAM exhausted, the solve swapped |
| 7.0 | 0.875 | – | – | – | – | – | – | not reached (run stopped at its 2 h limit) |

The 4 mm level is from a first run with the plan's default levels (4, 2.8, 2 mm), stopped after it was skipped.

Gate G0 (spec §4): **not met.** One solve fits in RAM only up to about 3 M DOFs, at a mesh too coarse to be converged. Memory, not time, is the limit: about 5 GB per million DOFs. The coarse-mesh values are no evidence for G1 (measured 3.22 N·m and 4.72e-4 Wb; 2D 2.80 N·m). Per the spec the sweep is shrunk and R4a is re-planned; the owner is told.

### Swept mesh cross-check

The swept prism model (`tools/end3d/swept.py`, `team24_swept_model`) was compared with the tetrahedral model for linear steel (mu_r 1000) at 5 A. The slab agrees to 0.6 % (psi), 0.1 % (torque) and 0.7 % (rotor-pole flux) at the coarse setting, and to 0.16 %, 0.003 % and 0.2 % at the finest (swept 1 / 1.5 mm, tetrahedral 3 / 0.8 mm), both converging from opposite sides. The full model differs by +0.7 to +1.0 % in psi and torque (+1.2 to +1.5 % in rotor-pole flux) at every affordable resolution:

| swept (h_gap, h_iron, h_end, h_mid mm) | tetrahedral (maxh, gap mm) | psi swept / tet (Wb) | torque swept / tet (N·m) |
|---|---|---|---|
| 3, 9, 3, 10 | 10, 3 | 0.3689 / 0.3654 | 1.534 / 1.519 |
| 2, 6, 2, 10 | 7, 2 | 0.3696 / 0.3663 | 1.531 / 1.520 |
| 2, 5, 2, 8 (end air 0.25) | 7, 2 | 0.3690 / 0.3664 | 1.533 / 1.520 |
| – | 12, 1.5 | – / 0.3649 | – / 1.513 |
| – | 9, 1.2 (not converged) | – / 0.3671 | – / 1.520 |

Attribution: the tetrahedral model is under-resolved, the swept one is not wrong. The energy split by region shows no outlier (about 43 % in the gap shell over the stack, 26 % in the end air). In the tetrahedral model the stack energies of coil_0 and coil_1 differ by 1.8 % although the problem is symmetric (swept: 0.01 %). With a fixed J the co-energy of a conforming solve rises with refinement, so a less resolved solve is bounded from below; every tetrahedral psi (0.3649 to 0.3671) is below every swept psi (0.3689 to 0.3697) and rises with refinement. The swept values change by 0.2 % between resolutions and by 0.02 % when the layers are refined. The slow test therefore asserts swept >= tetrahedral and within +2 % for psi and torque in the full model.

Memory at the level h_gap 1.5, h_iron 12, h_end 3, h_mid 12 mm (full, nonlinear 7.41 A, 65 654 prisms, 1.53 M DOFs, far-field layers growing to 4 h_mid): BDDC 10.45 GB and 413 s; BDDC with static condensation 9.67 GB and 393 s (the default; psi 0.50309 Wb and torque 2.8427 N·m equal to 1e-12); `hcurlamg` gave no result within 560 s. The earlier layout (spacing capped at h_mid) had 77 240 prisms, 1.75 M DOFs and 10.8 GB.

## G2 slab against 2D

Not run yet.

## G1 TEAM 24 3D against measurement

Not run yet.

## G3 (R4b)

Not run yet.

## G4 (R4b)

Not run yet.

## G5 (R4b)

Not run yet.

## Fitted constants (R4b)

Not run yet.

## Ranking bias (R4b)

Not run yet.
