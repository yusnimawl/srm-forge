# TEAM Problem 24 feasibility check

Answer: **yes, TEAM 24 can be set up and solved by the 2D engine.** Both solvers agree to machine precision,
static torque is +6.4 % above measurement, and the current rise follows the measured shape but is
faster early (eddy currents are not modelled). Reproduce with `python examples\team24_check.py [size_scale]`;
the model is `tests/team24_fixture.py::team24_problem`.

## Inputs used

Source: Allen & Rodger, "Description of TEAM Workshop Problem 24" (compumag.org problem24.pdf), read
from the PDF text and by rendering Fig. 1 and Fig. 2. The NGSolve page (ngsolve.github.io/TEAM-problems/TEAM-24)
was used only to cross-check numbers.

| Quantity | Value | Source |
|---|---|---|
| Stator outer diameter | 209.0 mm | Fig. 1 |
| Stator yoke thickness | 21.4 mm (yoke inner radius 83.1 mm, derived) | Fig. 1; 83.1 also on the NGSolve page |
| Stator pole tip circle | Ø107.5 mm | Fig. 1 |
| Stator pole width | 27.8 mm (parallel sides), poles at +y and -y | Fig. 1 |
| Rotor tip circle | Ø102.1 mm (air gap 2.7 mm) | Fig. 1 |
| Rotor pole width | 25.4 mm (parallel sides), two poles | Fig. 1 |
| Shaft | Ø50.8 mm, non-magnetic (modelled as air) | Fig. 1, text |
| Rotor hub | radial 12.7 mm from the shaft, so outer radius 38.1 mm | Fig. 1 (the 12.7 dimension) |
| Axial length | 25.4 mm | Fig. 1 |
| Rotor position | locked 22 deg from the stator poles, poles overlap slightly | text, NGSolve page (-22 deg) |
| Coils | two, 350 turns each, in series, 3.09 ohm total | Fig. 2, text |
| Coil section | 24 x 17 mm (24 build in x, 17 along y), hole 34 mm across the pole | Fig. 2 |
| Coil position | midplane 63.0 mm from the shaft centre | Fig. 2 |
| Step voltage | 23.1 V | text, Table II |
| B-H | 21 points, Table I (below) | Table I |
| Measured i, T | Tables III, IV | Tables III, IV |
| Torque convention | force x 0.268 m | Fig. 7 title |

B-H (H in A/m, B in T): the points in Table I, entered in `H_TABLE`/`B_TABLE`.

Read from figures: Fig. 1 hub radius (the 12.7 dimension) and the 21.4 yoke thickness are labels in the
image. Geometry choices not in the report: the 3 mm fillets (stated on the NGSolve page) are omitted, the
domain ends at the stator outer surface with A = 0 (no outer air), the gap band is r = 51.6..53.2 mm.

## Unit ambiguity in Table I

The PDF text extraction of Table I has a garbled H column header ("10^4") and Fig. 3's axis says x10^5.
The values 400, 801, ..., 39634 A/m (from the NGSolve page and the digits in the PDF) were used. Reading
the column as x10^4 would give H = 4000..396340 A/m and a polarisation J = B - mu0 H that decreases at the
top of the table, which no steel does; the 400..39634 reading has J rising to 2.42 T. This is a judgement
the owner may want to confirm against the printed table.

## Assumptions the report does not settle

- Saturation polarisation for the tail beyond 2.472 T: 2.6 T (assumed). Corner elements exceed the table:
  peak |B| in iron is 2.79 T (default mesh) to 3.09 T (finer mesh), i.e. the sharp overlapping pole
  corner (no fillet) is a field singularity. Torque does not move with it (below).
- Steel is solid (stacking factor 1); eddy currents neglected (spec section 2.3).
- 3D end effects (axial length 25.4 mm, coil overhang, leakage outside the stator) are not in a 2D model.

## Solver agreement (7.41 A, default mesh: 15 051 nodes, 29 935 triangles)

| Quantity | skfem vs NGSolve relative difference |
|---|---|
| max abs A / max A | 4e-13 |
| psi | 3e-15 |
| energy, co-energy | 7e-15 |
| Arkkio torque | 2e-14 |
| virtual-work torque | 2e-11 |

Required 1e-4; met by about 9 orders of magnitude. Both converge in 6 Newton iterations (1 s and 2 s).
At `size_scale 0.5` (118 495 triangles): same agreement (1e-13), 8 iterations, about 8 s each.

## Static torque at the final current

psi(7.41 A) = 0.4066 Wb-turns.

| | Arkkio | virtual work | measured | deviation |
|---|---|---|---|---|
| default mesh | 3.426 N.m | 3.426 | 3.22 | +6.4 % |
| size_scale 0.5 | 3.425 | 3.425 | 3.22 | +6.4 % |

Arkkio and virtual work agree within 0.01 %; mesh refinement moves torque by 0.03 %. Torque is positive
(counter-clockwise, toward alignment); both poles carry flux in the same direction (checked).

## Current rise

Integrated t(i) = integral of psi'(i)/(V - R i) di on a 18-point locked-rotor psi(i) map (PCHIP), constant
V = 23.1 V, R = 3.09 ohm, then compared with Table III at the table times.

| t (s) | i measured | i model | deviation |
|---|---|---|---|
| 0.002 | 0.91 | 0.80 | -12.5 % |
| 0.005 | 1.80 | 1.83 | +1.8 % |
| 0.010 | 2.95 | 3.21 | +8.9 % |
| 0.020 | 4.49 | 5.04 | +12.3 % |
| 0.030 | 5.45 | 6.09 | +11.7 % |
| 0.050 | 6.45 | 7.03 | +9.0 % |
| 0.100 | 7.22 | 7.45 | +3.2 % |
| 0.200 | 7.40 | 7.47 | +0.9 % |
| 0.300 | 7.41 | 7.47 | +0.8 % |

The model is up to 12 % ahead of the measurement between 10 and 40 ms and settles at V/R = 7.476 A
(the table is truncated at 7.47 A in the script; measured 7.41 A). The early lag in the measurement is what
eddy currents in solid steel would produce, so the sign of the deviation is the expected one.
Torque at the measured time points is off by up to +65 % mid-rise, because torque follows the current
lag (torque vs current at the same current is within about 6 %): compare torque against current, not time.

## Comparison with the NGSolve reference page

The page publishes only the ranges (final current 7.41 A, steady torque 3.22 N.m, rotor flux 4.72e-4 Wb
and B_y 1.26 T); those are the measured end values, not independent computed results, so there is no
computed reference to compare with. Its geometry summary (radii 104.5, 83.1, 53.75 mm, block width 27.8,
fillet 3 mm) matches the dimensions above. Its rotor dimensions ("outer radius 32.15", "inner radius 25.4") do not
match Fig. 1 and were not used.

## What surprised or blocked

- Nothing blocked. The one-pass geometry (Gmsh OCC booleans, fragment for conformity) meshed first time.
- The report's B-H column units are garbled in text (see above).
- The Task 3 checks (Newton, cross-solver, virtual work) work unchanged on a non-SRM topology.
- Not compared: rotor pole flux (Table V, 5-turn search coil) and Hall probe B_y (Table VI), which need
  probe positions and are 3D quantities.

## Is TEAM 24 behaviour reached?

Yes for the magnetostatic scope: the engine reproduces the saturated end state (torque within 6.4 %)
and the qualitative current rise. The rise deviates by about 12 % at worst because eddy currents are outside
the scope.

Proposed criterion for the owner to accept or change in Task 6 (provisional): static torque within 10 % of
measured at 7.41 A, and a current-rise curve that follows the measured shape. Current numbers meet both;
a stricter "current within 10 % at all times" would fail between 10 and 40 ms.
