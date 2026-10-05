# M5b: TEAM Problem 24 comparison

## Summary

- The 2D static torque at 7.41 A is 2.7996 N·m against 3.22 measured: -13.1 %.
- The rotor-pole flux is 3.9069e-04 Wb against 4.72e-04: -17.2 %.
- The model current runs ahead of the measurement by up to +18.6 % between 5 and 50 ms (R 3.09 Ω, 23.1 V); across the R and voltage variants the maximum is 18.1 % to 18.9 % (+18.9 % at R 3.12 Ω with the Table II voltage).
- At steady state the model is low (torque -13.1 %, rotor flux -17.2 %), the sign of the omitted 3D end flux. Early in the rise the sign differs. At 2 ms the measured torque (0.02 N·m) and flux are at the table's rounding limit (±0.005 is ±25 % of 0.02), so the model-high +98 % torque and +61 % flux there mean no more than "model high". From 5 ms on, T(i_meas) runs from -7.5 % at 5 ms through +10.2 % at 10 ms to -13.3 % at 200 ms, settling at -13.1 %. F(i_meas) is high early (+21.1 % at 5 ms, +7.2 % at 10 ms) and low from 20 ms (-2.9 %), settling to -17.2 %. The current at 2 ms is -1.7 %. In a locked-rotor voltage step, eddy currents in the solid steel act like a shorted secondary: the coil current is the magnetising current plus an eddy current proportional to dψ/dt. Early in the rise they make the measured coil current higher and the measured flux and torque lower than the 2D model at the same current; the effect decays with dψ/dt and is zero at steady state. That is consistent with the model current lagging at 2 ms (-1.7 %) and with T(i_meas) and F(i_meas) being high at 2 to 10 ms; the interpolated low-field B-H is a second candidate (see the budget). Neither is established. The model current then runs up to +18.6 % ahead between 5 and 50 ms. Two things are consistent with that lead. First, ∫(V − R·i) dt = ψ_final, so eddy currents that raise the measured current early must leave it below the eddy-free current later: the eddy-free model lags early and leads mid-rise, the observed pattern. Second, the lower 2D ψ_final (omitted 3D end flux; torque -13.1 %, flux -17.2 % at steady state) gives ∫(i_model − i_meas) dt = (ψ_meas − ψ_model)/R > 0, a net lead. The interpolated low-field B-H is a third candidate. None is established; only the 3D end flux explains the steady-state deficit.
- There is no pass/fail gate (owner decision 2026-10-04).
- Reproduce with `python examples\team24_check.py`. The slow test is `tests/validation/test_team24.py`; the model is `tests/team24_fixture.py::team24_problem`.

## Inputs

Source: Allen & Rodger, "Description of TEAM Workshop Problem 24" (compumag.org problem24.pdf), read from the PDF text and by rendering Fig. 1 and Fig. 2. The NGSolve page (ngsolve.github.io/TEAM-problems/TEAM-24) was used only to cross-check numbers.

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
| B-H | 21 points, Table I, H in 1e4 A-t/m; points 1–17 used | Table I |
| Measured i, T | Tables III, IV | Tables III, IV |
| Torque convention | force x 0.268 m | Fig. 7 title |

Read from figures: Fig. 1 hub radius (the 12.7 dimension) and the 21.4 yoke thickness are labels in the image. Geometry choices not in the report: the 3 mm fillets (stated on the NGSolve page) are omitted, the domain ends at the stator outer surface with A = 0 (no outer air), the gap band is r = 51.6..53.2 mm.

Other assumptions: the steel is solid (stacking factor 1) and eddy currents are neglected (spec §2.3). Table V is read as flux per turn, the pole flux: Fig. 8 is titled "SEARCH COIL FLUX (5 TURNS)" but its axis is "ROTOR POLE FLUX (Wb)" and Table V is "rotor pole flux (×10⁻⁴ Wb)", so the 5 turns are taken as a note on the figure. The search coil sits on the rotor pole under the top stator pole, on a chord 8.7 mm from the corner along the flank (Fig. 1). Both rotor poles carry the same flux by symmetry.

## Table I reading

- The printed header reads "(×10⁴ A-t/m)" and Fig. 3's H axis runs 0–4.0 ×10⁵ A/m. So H = 4 000 … 396 340 A/m.
- The earlier reading (400 … 39 634 A/m, from the NGSolve page) was 10× too soft. It gave +6.4 % torque.
- With the corrected reading, J = B − μ0·H rises to 1.979 T at point 17 (240 kA/m), then reads 1.979, 1.979, 1.977, 1.974 T at points 18–21. The dip is up to 5 mT, at the digitisation level of the table.
- `process_bh` needs J non-decreasing, so points 18–21 are dropped. The used table ends at point 17, 2.281 T.
- Js = 2.0 T is assumed (above the 1.979 T at point 17).

## Results

Default mesh: 15051 nodes, 29935 triangles. Locked rotor, 7.41 A.

| Quantity | Model | Measured | Error |
|---|---|---|---|
| Torque, Arkkio | 2.7996 N·m | 3.22 | -13.1 % |
| Torque, virtual work | 2.7996 N·m | 3.22 | -13.1 % |
| ψ | 0.36760 Wb-turns | | |
| Rotor-pole flux, pole 1 | 3.9069e-04 Wb | 4.72e-04 | -17.2 % |
| Rotor-pole flux, pole 2 | 3.9063e-04 Wb | | |
| Peak iron \|B\| | 2.29 T | | |

Peak iron |B| depends on the mesh (2.29 T on the default mesh, 2.50 T at mesh ×0.5). The overlapping pole corner is a field singularity (no fillet).

Solver agreement, NGSolve vs skfem: max|dA|/max|A| 4.8e-13, torque relative difference 4.3e-15.

Locked-rotor current rise and the quantities at that current. T in N·m, F in 1e-4 Wb. T(t) and F(t) use the model current at time t. T(i_m) and F(i_m) use the model at the measured current, which removes the time-axis error. Deviations in %.

| t/s | i meas | i model | dev % | T meas | T(t) | dev % | T(i_m) | dev % | F meas | F(t) | dev % | F(i_m) | dev % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.002 | 0.91 | 0.895 | -1.7 | 0.02 | 0.038 | +91.4 | 0.040 | +97.9 | 0.29 | 0.460 | +58.5 | 0.467 | +61.2 |
| 0.005 | 1.80 | 2.023 | +12.4 | 0.17 | 0.199 | +17.3 | 0.157 | -7.5 | 0.77 | 1.051 | +36.4 | 0.933 | +21.1 |
| 0.010 | 2.95 | 3.472 | +17.7 | 0.39 | 0.599 | +53.6 | 0.430 | +10.2 | 1.44 | 1.823 | +26.6 | 1.543 | +7.2 |
| 0.015 | 3.82 | 4.529 | +18.6 | 0.68 | 1.030 | +51.5 | 0.728 | +7.1 | 1.99 | 2.391 | +20.2 | 2.010 | +1.0 |
| 0.020 | 4.49 | 5.308 | +18.2 | 0.96 | 1.424 | +48.3 | 1.012 | +5.5 | 2.44 | 2.809 | +15.1 | 2.370 | -2.9 |
| 0.030 | 5.45 | 6.310 | +15.8 | 1.48 | 2.023 | +36.7 | 1.503 | +1.5 | 3.11 | 3.340 | +7.4 | 2.885 | -7.2 |
| 0.040 | 6.05 | 6.854 | +13.3 | 1.90 | 2.392 | +25.9 | 1.858 | -2.2 | 3.58 | 3.623 | +1.2 | 3.203 | -10.5 |
| 0.050 | 6.45 | 7.146 | +10.8 | 2.24 | 2.602 | +16.2 | 2.115 | -5.6 | 3.91 | 3.773 | -3.5 | 3.413 | -12.7 |
| 0.060 | 6.71 | 7.302 | +8.8 | 2.48 | 2.718 | +9.6 | 2.292 | -7.6 | 4.14 | 3.852 | -7.0 | 3.548 | -14.3 |
| 0.070 | 6.91 | 7.384 | +6.9 | 2.68 | 2.780 | +3.7 | 2.432 | -9.3 | 4.31 | 3.894 | -9.7 | 3.652 | -15.3 |
| 0.080 | 7.04 | 7.427 | +5.5 | 2.82 | 2.813 | -0.2 | 2.525 | -10.5 | 4.43 | 3.916 | -11.6 | 3.719 | -16.1 |
| 0.090 | 7.15 | 7.450 | +4.2 | 2.93 | 2.830 | -3.4 | 2.605 | -11.1 | 4.52 | 3.927 | -13.1 | 3.775 | -16.5 |
| 0.100 | 7.22 | 7.462 | +3.4 | 3.02 | 2.840 | -6.0 | 2.657 | -12.0 | 4.58 | 3.933 | -14.1 | 3.811 | -16.8 |
| 0.120 | 7.31 | 7.472 | +2.2 | 3.11 | 2.847 | -8.5 | 2.724 | -12.4 | 4.65 | 3.938 | -15.3 | 3.856 | -17.1 |
| 0.140 | 7.36 | 7.475 | +1.6 | 3.17 | 2.849 | -10.1 | 2.762 | -12.9 | 4.69 | 3.939 | -16.0 | 3.882 | -17.2 |
| 0.160 | 7.38 | 7.475 | +1.3 | 3.19 | 2.850 | -10.7 | 2.777 | -13.0 | 4.71 | 3.940 | -16.4 | 3.892 | -17.4 |
| 0.180 | 7.40 | 7.476 | +1.0 | 3.21 | 2.850 | -11.2 | 2.792 | -13.0 | 4.72 | 3.940 | -16.5 | 3.902 | -17.3 |
| 0.200 | 7.40 | 7.476 | +1.0 | 3.22 | 2.850 | -11.5 | 2.792 | -13.3 | 4.72 | 3.940 | -16.5 | 3.902 | -17.3 |
| 0.240 | 7.41 | 7.476 | +0.9 | 3.22 | 2.850 | -11.5 | 2.800 | -13.1 | 4.72 | 3.940 | -16.5 | 3.907 | -17.2 |
| 0.300 | 7.41 | 7.476 | +0.9 | 3.22 | 2.850 | -11.5 | 2.800 | -13.1 | 4.72 | 3.940 | -16.5 | 3.907 | -17.2 |

Sensitivity of the current rise (max |dev| % for t ≥ 5 ms; dev % at 20 ms; current at 300 ms):

| R, V | max \|dev\| % | dev % at 20 ms | i at 300 ms |
|---|---|---|---|
| 3.09 Ω, 23.1 V | 18.6 | +18.2 | 7.476 A |
| 3.12 Ω, 23.1 V | 18.1 | +17.7 | 7.404 A |
| 3.12 Ω, Table II voltage | 18.9 | +18.5 | 7.404 A |

Sensitivity of the static point:

| Change | Torque | vs default | ψ | Peak iron \|B\| |
|---|---|---|---|---|
| Js 1.98 T | 2.7996 N·m | +0.000 % | 0.36760 | 2.29 T |
| Js 2.05 T | 2.7996 N·m | -0.000 % | 0.36760 | 2.29 T |
| mesh ×0.5 | 2.7995 N·m | -0.004 % | 0.36857 | 2.50 T |

The Js effect is < 1e-6 (only 4 corner elements above the table at 7.41 A on the default mesh).

Regression pins in the slow test: torque 2.7996 N·m, ψ 0.3676 Wb-turns (relative 1e-3).

## Uncertainty budget

| Entry | Static torque | Current rise | Rotor-pole flux | Basis |
|---|---|---|---|---|
| 3D end flux | dominant, model low; not quantified in 2D; end turns add no torque (see the M5d section) | lower 2D inductance → model fast; the M5d end-winding hook (6.6–13.1 mH) cuts the mid-rise lead from +18.6 % to +8.1 % | dominant, model low; not quantified in 2D; end turns add no rotor flux | axial length 25.4 mm is about 9× the 2.7 mm gap |
| Eddy currents (σ = 4.54 MS/m, solid steel) | 0 at steady state; early: measured lower at a given current → model high at i_meas | measured higher early, lower later → model lags early, leads mid-rise; out of scope (§2.3) | 0 at steady state; early: measured lower at a given current → model high at i_meas | steady state has no eddy currents |
| R 3.09 vs 3.12 Ω | none | max \|dev\| 18.6 % to 18.1 % (t ≥ 5 ms); i at 300 ms 7.476 to 7.404 A | none | computed |
| Voltage overshoot (Table II vs 23.1 V) | none | max \|dev\| 18.1 % to 18.9 % (t ≥ 5 ms, R 3.12 Ω) | none | computed |
| Js 1.98–2.05 T | < 1e-6 (only 4 corner elements above the table) | not computed | not computed | computed |
| Mesh (scale 0.5) | -0.004 % | ψ +0.26 % (affects the current rise) | not computed | computed |
| Table rounding (2 decimals) | ±0.005/3.22 = ±0.16 % on final torque | ±0.005/i (±0.55 % at 0.91 A) | ±0.005/4.72 = ±0.11 % on the final value | arithmetic |
| Table I reading / B-H | measured EN9 curve, annealed; no grade or tolerance given | same | same | Table I |
| Low-field B-H | not quantified | Table I has no point between 0 and 1.413 T (at 4000 A/m); μr ≈ 300–390 along the first segment is interpolated; affects the early current rise | same; affects the early rows | not quantified |
| Search-coil position | not applicable | not applicable | Table V assumed flux per turn; chord 8.7 mm from the corner along the flank | Fig. 1 |

## End-winding correction (M5d)

An independent check of the analytic end-winding hook (`srmcore.post.end_winding`, M5d). The hook was not tuned on TEAM 24. Geometry: mean overhang span 58 mm (34 mm hole + 24 mm build), build 24 mm, 17 mm along the pole axis, separation 25.4 mm stack + 24 mm build. Both coils in series (2 × 350 turns).

| Image factor | L_end (both coils) |
|---|---|
| 1 (free air, lower bound) | 6.552 mH |
| 2 (against a permeable end face, upper bound) | 13.104 mH |
| Midpoint, used below | 9.828 mH |

ψ at 7.41 A goes from 0.36760 to 0.44043 Wb-turns (+19.8 %). The correction is applied to the locked-rotor map as ψ + L_end·i, and the current rise is recomputed. Deviations in %.

| t/s | i meas | before | dev % | after | dev % |
|---|---|---|---|---|---|
| 0.002 | 0.91 | 0.895 | -1.7 | 0.753 | -17.3 |
| 0.005 | 1.80 | 2.023 | +12.4 | 1.731 | -3.8 |
| 0.010 | 2.95 | 3.472 | +17.7 | 3.041 | +3.1 |
| 0.015 | 3.82 | 4.529 | +18.6 | 4.046 | +5.9 |
| 0.020 | 4.49 | 5.308 | +18.2 | 4.822 | +7.4 |
| 0.030 | 5.45 | 6.310 | +15.8 | 5.891 | +8.1 |
| 0.040 | 6.05 | 6.854 | +13.3 | 6.534 | +8.0 |
| 0.050 | 6.45 | 7.146 | +10.8 | 6.918 | +7.3 |
| 0.060 | 6.71 | 7.302 | +8.8 | 7.147 | +6.5 |
| 0.070 | 6.91 | 7.384 | +6.9 | 7.282 | +5.4 |
| 0.080 | 7.04 | 7.427 | +5.5 | 7.362 | +4.6 |
| 0.090 | 7.15 | 7.450 | +4.2 | 7.409 | +3.6 |
| 0.100 | 7.22 | 7.462 | +3.4 | 7.437 | +3.0 |
| 0.120 | 7.31 | 7.472 | +2.2 | 7.462 | +2.1 |
| 0.140 | 7.36 | 7.475 | +1.6 | 7.471 | +1.5 |
| 0.200 | 7.40 | 7.476 | +1.0 | 7.476 | +1.0 |
| 0.300 | 7.41 | 7.476 | +0.9 | 7.476 | +0.9 |

The mid-rise lead shrinks: the maximum deviation for t ≥ 5 ms falls from +18.6 % (15 ms) to +8.1 % (30 ms), and at 20 ms from +18.2 % to +7.4 %. The lead is not removed. The early points move the other way: at 2 ms the model goes from -1.7 % to -17.3 %, and at 5 ms from +12.4 % to -3.8 %, so the early lag grows (the 2 ms point is also the one most affected by eddy currents and the interpolated low-field B-H). The steady-state current is unchanged (7.476 A, set by V/R). The remaining lead is consistent with the other candidates in the budget (eddy currents, 3D iron fringing). Static torque and rotor-pole flux are unchanged: a constant end inductance adds neither, so their -13 %/-17 % deficit is 3D fringing of the iron, not end turns.

## Not compared

- Hall-probe B_y (Table VI): a point 7.7 mm inside the pole end, a 3D quantity.
- Torque vs time is shown but carries the current-rise time-axis error. T(i_meas) is the meaningful torque comparison.
