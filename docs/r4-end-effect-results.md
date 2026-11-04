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
