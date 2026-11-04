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

### Swept mesh (Task 6b), 2026-11-04

Same case (full TEAM 24 half model, 7.41 A, nonlinear steel, H(curl) order 2), on the swept prism mesh with condensed BDDC. Data: `docs/validation/r4_g0_swept.json`. A level is h_gap / h_iron / h_end / h_mid in mm.

| Level (mm) | Prisms | Layers | Free DOFs | Solve (s) | Newton | Torque (N·m) | ψ (Wb-turns) | Rotor-pole flux (Wb) |
|---|---|---|---|---|---|---|---|---|
| 1.5 / 10 / 2 / 8 | 75 420 | 18 | 1 711 242 | 540 | 7 | 2.84246 | 0.50307 | 4.3273e-4 |
| 1.2 / 8 / 1.5 / 6 | 140 760 | 24 | 3 202 278 | 2257 | 7 | 2.84101 | 0.50304 | 4.3273e-4 |
| 1.0 / 7 / 1.2 / 5 | 179 699 | 23 | 4 089 610 | 2473 | 7 | 2.84073 | 0.50306 | 4.3270e-4 |
| 0.8 / 6 / 1.0 / 4 | 260 350 | 25 | 5 931 208 | – | – | skipped (over the 4.2 M DOF cap) | | |

- The levels agree to 0.06 % in torque and 0.01 % in ψ and flux, so the coarsest level is already mesh-converged for these quantities at this current. G1's mesh row measures this formally.
- Peak RSS is the process maximum, so the later levels inherit earlier peaks: 11.5 GB after level 1 (1.7 M DOFs), 31.2 GB (all RAM, swapping) during level 2. About 6.5 GB per million DOFs; one process per level would give per-level peaks.
- Gate: one solve fits in RAM up to about 3 M DOFs. The script's sweep estimate (finest converged level × 336 solves) is 231 h, over the 168 h limit; at the coarsest level, which agrees with the finest within 0.06 %, it is 50 h. Controller ruling R20: the gate is read at the coarsest level that agrees with the finest within 0.1 %; with that reading G0 is met.
- Coarse 3D against measurement, for orientation only (G1 decides): torque 2.841 N·m against 3.22 measured (−11.8 %; 2D −13.1 %), rotor-pole flux 4.327e-4 Wb against 4.72e-4 (−8.3 %; 2D −17.2 %).

## G2 slab against 2D

Verdict: pass. Every row converged; psi within 0.35 % and torque within 0.15 % of the machine's peak torque, signed, against limits of 0.5 % and 1 %. Script `tools/end3d/g2_slab.py`, data `docs/validation/r4_g2.json`. The 3D model is the swept prism slab (a stack half with its end face at z = depth/2 on a Dirichlet face, so coil sides run straight); 2D references are the srmcore `full` mesh solved with the NGSolve adapter (8/6) and the fixture mesh (TEAM 24). One mesh level, no refinement was needed: 8/6 h_gap/h_iron/h_end/h_mid 1 / 3 / 4 / 12 mm; TEAM 24 1 / 4 / 1 / 3 mm. Each solve ran in its own process under a 20 GB cap.

| Machine | Angle (rad) | Current (A) | psi 2D | psi 3D | psi rel | T 2D (N·m) | T 3D (N·m) | T rel peak | Free DOFs | Solve (s) | Peak RSS (GB) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 8/6 | 0 (aligned) | 20 | 0.32030 | 0.32045 | 0.045 % | -3.7e-5 | -0.0137 | 0.110 % | 1 504 006 | 302 | 4.3 |
| 8/6 | 0.2618 (half overlap) | 20 | 0.19518 | 0.19540 | 0.114 % | -12.436 | -12.455 | 0.153 % | 1 521 961 | 272 | 4.3 |
| 8/6 | 0.5236 (unaligned) | 20 | 0.07236 | 0.07243 | 0.098 % | 1.5e-4 | -6.4e-6 | 0.001 % | 1 509 676 | 159 | 4.2 |
| TEAM 24 | locked rotor | 7.41 | 0.36760 | 0.36890 | 0.352 % | 2.7996 | 2.8007 | 0.037 % | 1 260 964 | 106 | 5.5 |

- Signs agree with 2D: motoring torque is negative at 0 < theta < pi/N_r in the srmcore sign convention (counter-clockwise positive, phase A excited from aligned), and psi is positive.
- Torque rel peak is |T3D - T2D| / peak |T2D| of the machine's rows. The 8/6 aligned and unaligned torques are numerically zero in both models; the 3D aligned residual (-0.014 N·m, 0.11 % of peak) is the Arkkio shell noise on a prism mesh.
- The TEAM 24 psi gap (0.35 %) is the largest; a missing or doubled factor would show as 100 %, so the gap is discretisation (not refined further, since the gate holds).

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
