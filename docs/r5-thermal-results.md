# R5 thermal and rotor stress results

This file holds the results of the R5a validation gates V1 to V6. V1 passed in tests/thermal. V6 is below and it passed on the revised model. V3 is recorded below (not reproduced exactly). V0 is complete (docs/r5-sources.md section 9). V2 is recorded below: it does not pass. V4 is recorded below: it passes. V5 has no separate gate (see the thermal mesh note).

## V1: solver against closed forms (tests/thermal)

| Case | Test | Measured error | Gate |
|---|---|---|---|
| Slab, uniform heat, Robin ends | `test_slab_uniform_heat_robin_ends` | 2.7e-15 of the rise on the centre row (all nodes 2.0e-3, the diagonal split tilts the end columns) | 1e-9 on the centre row |
| Annulus, uniform heat | `test_annulus_uniform_heat` | 9.0e-4 of the rise | 1e-3 |
| Manufactured solution, order | `test_manufactured_solution_second_order` | L2 7.64e-3 (8 x 8) and 1.91e-3 (16 x 16), ratio 3.99 | ratio over 3 |
| Lumped RC step, 200 steps over one time constant | `test_lumped_rc_step` | 9.2e-4 of the final rise | 5e-3 |
| Time step order (first) | `test_time_step_is_first_order` | error ratio 1.99 for 50 against 100 steps | 1.8 to 2.2 |
| Adiabatic element heating | `test_adiabatic_element_heating` | node balance to 1e-9 relative, stored energy to 1e-9 | 1e-9 |

## V6: analytic rotor stress against a 2D elastic FE

Verdict: PASS on the box of docs/r5-sources.md section 5, commit 92b3fcc, constants unchanged since 55ac728. The held-out list (1447 designs: every corner of the box, the corners of its taper 0 plane, rays from the centre to every face and joint limit, face points and interior points) was committed at 37303cd before any FE on it, and its FE at 82e32a1 with no change to box or constants. Pass rule, unchanged: FE converged to under 2 % over the last two levels, bore and root within 15 % of the FE, analytic peak not more than 5 % below the FE peak. Tip growth is held to the same 15 %.

What the pass covers: every design that reads `ok`, that is, inside the box with its joint limits, boundary included, for 10JNEX900-like elastic data (nu 0.25 to 0.36 checked) and any size. What it does not cover: pole counts other than 4, 6, 8, 12, 16; taper beyond +-1.5 degrees; fillets under 0.025 or over 0.2 of the pole width; yokes under 0.55 of the tip chord; designs that read `no_fillet` or `kt_out_of_range` (no safety factor is given there); and points between those tested, which no finite set proves. The first box passed four Latin hypercube rounds and failed at its corners; this one was chosen with corner lattices and passed its own corners.

Tip growth: the analytic growth reads up to 9.4 % low on the lattice and 7.8 % low on the held-out set, and 10.2 % low on the first sweep. Low growth is the unsafe sign for the gap: the rotor grows more than computed. R5b carries it as a budget row. `gap_closure` has no range check: its rim relief `_BORE_RIM_RELIEF` is applied to any design, inside the box or not.

Old box record, superseded: model commit f7f2702, FE code the same at b41f2bc.

### FE reference

Half-pole sector, curved P2 mesh, recovered stress (method in docs/r5-sources.md section 5). The first FE did not converge because the static mesh has straight facets on a concave fillet and the peak was one quadrature point at a small re-entrant corner.

Convergence on the 8/6, 12000 rpm, element size r/n, in MPa:

| n | Dofs | Bore | Root | Peak position on the fillet |
|---|---|---|---|---|
| 10 | 2238 | 15.317 | 27.323 | 0.62 |
| 20 | 3708 | 15.320 | 27.314 | 0.60 |
| 40 | 6686 | 15.318 | 27.319 | 0.59 |
| 80 | 13012 | 15.317 | 27.315 | 0.59 |
| 160 | 26034 | 15.317 | 27.315 | 0.59 |

P3 elements at n = 40 give bore 15.317 and root 27.315 on the 8/6, and 26.077 and 53.574 on the 12/8. Worst change between n = 40 and n = 80 over the 1382 sweep designs inside the box: root under 0.08 %, bore under 0.05 %. The sector agrees with the whole-rotor FE: bore 15.32 against 15.18, tip 1.077 against 1.076 um (8/6, `reference`). The annulus closed-form checks pass, at 1 % on the old helper and 0.01 % on the sector. Position runs from 0 at the flank end of the fillet to 1 at the rim end.

### What the root stress is made of

12000 rpm, MPa. The load split solves pole mass and yoke mass alone.

| Machine | Whole | Pole mass alone | Yoke mass alone | Pole peak at | Yoke peak at | Whole peak at | Nominal | Rim hoop, pole load | Rim hoop, yoke |
|---|---|---|---|---|---|---|---|---|---|
| 8/6 | 27.32 | 22.95 | 5.06 | 0.52 | 0.80 | 0.59 | 6.60 | 6.65 | 1.94 |
| 12/8 | 53.58 | 44.70 | 9.87 | 0.57 | 0.81 | 0.63 | 10.47 | 13.01 | 3.66 |

The hypothesis holds in part. The peak is not on the flank but past the middle of the fillet towards the rim: the rim stress and ring bending matter as much as the pole tension. The two load cases peak at different places, so the sum of the peaks is above the whole (0.1 to 13 % over the sweep). The published Kt with pitch as the wide section does not fit the pole term on any scale: with it the best form scatters by +-16 %, against under +-9 % for the form used.

### Results at 12000 rpm

Reference machines, no part in any fit. MPa and um, FE at n = 80:

| Machine | FE bore | FE root | FE tip | Analytic bore | Analytic root | Analytic tip | Bore | Root | Tip | Peak | Convergence root, bore | Peak at |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8/6 | 15.32 | 27.32 | 1.077 | 16.26 | 28.78 | 1.094 | +6.2 % | +5.4 % | +1.6 % | +5.4 % | 0.01, 0.00 % | fillet 0.59 |
| 12/8 | 26.08 | 53.57 | 2.502 | 27.80 | 57.09 | 2.560 | +6.6 % | +6.6 % | +2.3 % | +6.6 % | 0.01, 0.00 % | fillet 0.63 |
| 24/16 | 58.90 | 135.71 | 8.230 | 60.52 | 146.24 | 8.423 | +2.8 % | +7.8 % | +2.3 % | +7.8 % | 0.01, 0.01 % | fillet 0.71 |

`stress_concentration` now reads 4.36, 5.45 and 8.24: it is root stress over nominal with the ring stress in it, not a pure fillet factor.

Present box, analytic against FE, worst errors:

| Set | Designs | Root | Bore | Tip | Peak | Convergence root, bore |
|---|---|---|---|---|---|---|
| Lattice (chose the box, seen) | 16 338 | -3.44 to +12.87 % | -3.97 to +14.36 % | -9.40 to +11.20 % | -3.44 % | 0.09, 0.08 % |
| Held out, all | 1447 | -3.44 to +11.81 % | -3.52 to +13.29 % | -7.77 to +10.76 % | -3.44 % | 0.08, 0.05 % |
| Held out, corners | 160 | -3.44 to +11.31 % | -3.50 to +13.20 % | -7.35 to +10.76 % | -3.44 % | |
| Held out, taper 0 corners | 80 | -3.07 to +10.58 % | -2.89 to +13.29 % | -6.96 to +9.78 % | -3.07 % | |
| Held out, boundary rays | 300 | -2.95 to +11.81 % | -3.52 to +13.12 % | -7.36 to +9.67 % | -2.95 % | |
| Held out, faces | 300 | -3.01 to +10.82 % | -1.03 to +11.45 % | -7.77 to +10.15 % | -3.01 % | |
| Held out, interior | 607 | -2.64 to +11.35 % | -2.19 to +13.02 % | -6.88 to +9.20 % | -2.64 % | |

Held out by pole count:

| N_r | Designs | Root | Bore | Tip | Peak |
|---|---|---|---|---|---|
| 4 | 287 | -2.30 to +10.62 % | -3.52 to +5.71 % | -7.77 to +7.59 % | -1.53 % |
| 6 | 365 | -1.67 to +10.31 % | +1.94 to +13.20 % | -7.35 to +8.68 % | -1.67 % |
| 8 | 315 | -3.44 to +11.81 % | +0.54 to +13.29 % | -2.17 to +10.76 % | -3.44 % |
| 12 | 254 | -1.64 to +11.41 % | -1.33 to +10.66 % | -0.12 to +9.08 % | -1.64 % |
| 16 | 226 | -3.01 to +11.18 % | -3.04 to +10.83 % | +0.13 to +8.96 % | -3.01 % |

The FE peak is on the fillet or the bore in every held-out design. Margins left on the held-out set: 1.6 points on the low side, 1.7 on the high side (bore); on the lattice 1.0 and 0.6.

The first box (LHS rounds, docs/r5-sources.md section 5), kept as record:

| Set | Designs | Root | Bore | Tip | Peak |
|---|---|---|---|---|---|
| Derived (rounds 1, 2) | 668 | -3.14 to +14.42 % | -3.31 to +13.19 % | -10.22 to +12.88 % | -3.31 % |
| Round 3 | 297 | -3.54 to +13.22 % | -1.41 to +12.64 % | -6.58 to +10.93 % | -3.54 % |
| Round 4 | 414 | -3.33 to +13.21 % | -0.77 to +14.29 % | -8.34 to +12.27 % | -3.07 % |

### First run (failed)

This is the record of the first run: the old model, nominal stress x Kt, against the whole-rotor FE. It failed because the root FE was not converged (faceted fillet, quadrature peak) and because nominal x Kt leaves out the rim stress and ring bending, which make up about a third of the root peak or more.

Code run: commit 1856e4c (test helper `tests/post/rotor_elastic_fe.py`, test `tests/post/test_rotor_stress_fe.py`).

The FE is plane stress, P2 triangles, the `rotor_iron` elements of the static mesh, body force rho w^2 r, free bore, three rigid-body DOFs pinned. Material 10JNEX900 (rho 7490 kg/m3, E 200 GPa, nu 0.33), speed 12000 rpm for both sides. The FE helper is checked first on a plain annulus against the closed-form hoop stress and rim growth (within 1 %).

The Kt source (Pilkey via AmesWeb) is grade C. This gate is its check.

Stresses in MPa (peak von Mises in the FE), growth in micrometres.

| Machine | Preset | FE bore | FE root | FE tip growth | Analytic bore | Analytic root | Analytic tip growth |
|---|---|---|---|---|---|---|---|
| 8/6 (Kt 2.55) | screening | 15.01 | 24.57 | 1.069 | 15.99 | 16.83 | 1.112 |
| 8/6 | full | 15.04 | 25.71 | 1.073 | 15.99 | 16.83 | 1.112 |
| 8/6 | reference | 15.18 | 26.48 | 1.076 | 15.99 | 16.83 | 1.112 |
| 12/8 (Kt 2.67) | screening | 25.53 | 48.16 | 2.481 | 27.51 | 28.01 | 2.607 |
| 12/8 | full | 25.65 | 47.61 | 2.491 | 27.51 | 28.01 | 2.607 |
| 12/8 | reference | 25.95 | 52.17 | 2.500 | 27.51 | 28.01 | 2.607 |

Errors at `reference` (analytic against FE):

| Machine | Bore | Root | Tip growth | Analytic peak against FE peak |
|---|---|---|---|---|
| 8/6 | +5.3 % | -36.4 % | +3.3 % | -36.4 % |
| 12/8 | +6.0 % | -46.3 % | +4.3 % | -47.3 % |

FE convergence, `full` to `reference`: 8/6 bore 0.9 %, root 3.0 %; 12/8 bore 1.2 %, root 9.6 %. The limit is 2 %.

The FE peak sits at the pole root fillet in every case (root peak above bore peak). The bore peak is on the shaft bore.

Verdict of that run: FAIL. Bore and tip growth pass the 15 % rule. The root stress fails it by a wide margin, the analytic peak is 36 to 47 % below the FE peak, and the root FE value is not converged to 2 %. The analytic root stress, the nominal pole stress times Kt, is low against the FE. Nothing in the model, Kt or the limits was changed.

## V3: winding conductivity against Marquez-Fernandez 2018

Verdict: the Milton formula (Eq. (6), xi 0.324, copper 300 W/(m K), resin 1 W/(m K)) reproduces the printed value at fill 0.37 within 0.8 % and does not reproduce it at fill 0.47. Nothing was fitted. Hand check and source: docs/r5-sources.md section 8. Tests pin the computed values within 0.5 %.

| Fill | Printed (W/(m K)) | Computed | Difference | xi | Measured-agreement value |
|---|---|---|---|---|---|
| 0.37 | 2.41 | 2.430 | +0.8 % | 0.324 (cited) | 3.0 |
| 0.47 | 3.11 | 3.439 | +10.6 % | not cited | 3.85 |

The paper gives xi for fill 0.37 only. Solving for xi gives 0.304 (0.37) and 0.195 (0.47); these are derived here, not in the paper. The measured-agreement values are about 24 % above the Milton ones; the paper reports no temperature error as a number. Handling (spec section 8 V3: revise the band, not the measured values): no cited xi exists for other fills (search repeated 2026-11-17, docs/r5-sources.md 6.8). The `cross_wire` row of `srmapp.cooling.ROWS` now carries the error: the nominal is Milton with xi 0.324 at every fill (the cited value, carried over; the note in `Coefficients.notes` names the +10.6 % error at fill 0.47) and the unfavourable end is the Hashin-Shtrikman value. Band at fill 0.47, resin 1 W/(m K), copper 300: HS 2.75, nominal 3.44, printed Milton 3.11 (inside the band), measured-agreement 3.85. Band at fill 0.37: HS 2.16, nominal 2.43, printed 2.41, measured-agreement 3.0. Before this change the nominal at fill 0.47 was HS and the row had no width there. The measured values only widen the band.

Re-run 2026-11-17 (`milton_k`, `hashin_shtrikman_lower`, python -I): fill 0.37 computed 2.430 against 2.41 (+0.8 %); fill 0.47 computed 3.439 against 3.11 (+10.6 %), unchanged. Tests: `tests/thermal/test_thermal_homogenise.py::test_v3_both_fills_with_the_one_cited_xi`, `tests/app/test_cooling.py::test_cross_wire_band_at_fill_without_cited_xi`. V3 stays "not reproduced exactly" at 0.47; the gap is now stated as a band, not closed.

## V2: our 2-D solver against Faiz 2009 (8/6 stator)

Verdict: V2 does not pass, because no case meets the pass rule at every Fig. 10 or Fig. 9 point, with the printed frame or with the Table V frame. The input difference found is the frame boundary. With the Table V frame, a gap in the shape of the curve remains: up to 4.97 K low between 2 and 105 min; Table VI: only the max-C row passes for `table_v`, the mean-B and min-A rows fail. Nothing was fitted.

Run: 2026-11-24 to 25, LattePanda (i5-1340P), srmcore 0.8.0, JSON committed at 522c7d6 (`docs/validation/r5_v2_faiz.json`). Wall time 56 min 42 s, peak memory 821 MB, for 3 meshes (screening 15751, full 28619, reference 200368 nodes), 2 time steps and 6 input rows. Command, from the repository root:

    systemd-run --user --unit=faiz-v2 --collect -p WorkingDirectory=$PWD -p MemoryMax=24G \
      --setenv=PYTHONPATH=src:tests .venv/bin/python -u examples/faiz_thermal_check.py \
      --json docs/validation/r5_v2_faiz.json

The case is `tests/faiz_8_6.py`. The readings are `docs/validation/r5_v0_readings.json`. Every input has its page and error in docs/r5-sources.md section 9.1, with the corrections of section 9.3.

### Inputs

- Domain (Fig. 2): one 2-D stator with laminations, winding, slot liner, slot wedge and frame. The rotor is not in it. The rotor losses reach the model only through the inside air of Fig. 8.
- Geometry: Table I. Liner 1.0 mm and wedge 2.2 mm (Fig. 11(a)), parallel-sided poles.
- Properties: Table II. Winding conductivity 0.83 W/(m K) (p. 2929).
- Losses: Table IV, spread uniformly inside each part (the paper does not say how): stator pole 5.9 W, stator yoke 10 W, copper 25.0 W, 40.9 W in the domain.
- Bore (pole faces and wedge face): h 70 W/(m2 K) to the inside air. The inside air is the Fig. 8 curve (linear between readings, 20 degC at 0, the slope of the last 10 readings past 119 min, 0.149 K/min) or a constant 20 degC.
- Start: 20 degC everywhere. Ambient 20 degC.
- Frame, two cases. Both join the stator OD to one frame lump through half the shell thickness of aluminium.
  - `printed`: an aluminium shell 5 mm thick (Table II), h 30 W/(m2 K) on its outer cylinder. The 5 mm thickness is an inference from Fig. 12.
  - `table_v`: one lump with C1 5298 J/K and R1 0.57 K/W to ambient (Table V). Reading the R1-C1 node of their network as the frame is an inference.

Differences from their model that the paper lets us see:

1. Slot-centre strip. Our two coil sides in a slot leave a strip one liner thickness wide (1 mm) on the slot centreline, and the strip takes the liner properties (k 0.076 W/(m K)). The paper says the slot is filled with conductors. This is a geometry difference.
2. Winding capacity. The winding takes copper rho c (Table II) over the whole coil area. The paper prints a winding conductivity but no winding capacity, so this is an inference.
3. Frame boundary. Our frame h acts at the frame surface. The "outside air" layer of Fig. 2 is not modelled (the ambiguity in section 9.1).
4. No slot-top fillet (about 1.3 mm in their drawing). The wedge is an arc at the bore radius, not their straight chord.

Pass rule (spec section 8): at every Fig. 10 point (Fig. 8 inside air) and every Fig. 9 constant-air point, |ours - fig| <= fig error + mesh error + time-step error. Ours is the coil maximum on `full` at 15 s steps (backward Euler, 0 to 120 min). Fig. 10 does not say which temperature it shows, so the coil mean is reported beside it. Mesh error is |full - reference| and time-step error is |15 s - 7.5 s| on `full`, per minute.

### Results

Fig. 10 target, Fig. 8 inside air. Coil maximum in degC, difference to the figure in brackets. The error columns are the larger of the two cases.

| Minute | Fig. 10 | `printed` 5 mm | `table_v` | Mesh error (K) | Time-step error (K) |
|---|---|---|---|---|---|
| 1 | 23.82 +- 2.01 | 22.01 (-1.81) pass | 22.00 (-1.82) pass | 0.005 | 0.022 |
| 2 | 27.04 +- 1.00 | 23.72 (-3.32) | 23.69 (-3.35) | 0.007 | 0.033 |
| 5 | 31.70 +- 0.49 | 27.71 (-3.99) | 27.40 (-4.30) | 0.012 | 0.044 |
| 10 | 35.26 +- 0.49 | 32.29 (-2.97) | 30.95 (-4.31) | 0.019 | 0.029 |
| 15 | 37.69 +- 0.30 | 35.75 (-1.94) | 33.13 (-4.56) | 0.022 | 0.017 |
| 25 | 41.11 +- 0.36 | 41.13 (+0.02) pass | 36.27 (-4.84) | 0.021 | 0.016 |
| 29 | 42.32 +- 0.20 | 42.90 (+0.58) | 37.35 (-4.97) | 0.020 | 0.016 |
| 50 | 46.15 +- 0.16 | 49.82 (+3.67) | 42.21 (-3.94) | 0.021 | 0.013 |
| 70 | 48.36 +- 0.18 | 54.15 (+5.79) | 45.94 (-2.42) | 0.022 | 0.009 |
| 89 | 50.01 +- 0.32 | 57.15 (+7.14) | 48.87 (-1.14) | 0.020 | 0.006 |
| 106 | 51.23 +- 0.15 | 59.27 (+8.04) | 51.06 (-0.17) pass | 0.024 | 0.004 |
| 119 | 52.09 +- 0.15 | 60.64 (+8.55) | 52.52 (+0.43) | 0.024 | 0.004 |

Fig. 9 target, constant 20 degC inside air:

| Minute | Fig. 9 constant | `printed` 5 mm | `table_v` | Mesh error (K) | Time-step error (K) |
|---|---|---|---|---|---|
| 1 | 23.79 +- 1.66 | 22.01 (-1.78) | 22.00 (-1.79) | 0.005 | 0.023 |
| 2 | 27.07 +- 0.89 | 23.69 (-3.38) | 23.66 (-3.41) | 0.009 | 0.036 |
| 5 | 31.60 +- 0.51 | 27.51 (-4.09) | 27.20 (-4.40) | 0.014 | 0.048 |
| 10 | 34.60 +- 0.26 | 31.61 (-2.99) | 30.31 (-4.29) | 0.020 | 0.031 |
| 23 | 38.34 +- 0.16 | 37.79 (-0.55) | 33.80 (-4.54) | 0.021 | 0.021 |
| 30 | 39.25 +- 0.16 | 39.92 (+0.67) | 35.02 (-4.23) | 0.021 | 0.020 |
| 50 | 40.37 +- 0.14 | 43.54 (+3.17) | 37.62 (-2.75) | 0.028 | 0.015 |
| 70 | 40.68 +- 0.14 | 45.16 (+4.48) | 39.37 (-1.31) | 0.025 | 0.009 |
| 91 | 40.74 +- 0.14 | 45.90 (+5.16) | 40.57 (-0.17) pass | 0.025 | 0.005 |
| 119 | 40.74 +- 0.14 | 46.29 (+5.55) | 41.56 (+0.82) | 0.026 | 0.004 |
| steady | 40.7 from about 80 min | 46.47 | 42.84 | | |

Verdict per case. `passes_from_min` is None in every case: no case passes from any minute to the end.

| Case | Target | Points that pass | Where they pass | Worst excess over the allowance |
|---|---|---|---|---|
| `printed` 5 mm | Fig. 10 | 5 of 114 | 1, 24 to 27 min | +8.37 K at 119 min |
| `printed` 5 mm | Fig. 9 constant | 3 of 113 | 25 to 27 min | +5.38 K at 119 min |
| `table_v` | Fig. 10 | 9 of 114 | 1, 106 to 113 min | +4.75 K at 29 min |
| `table_v` | Fig. 9 constant | 8 of 113 | 91 to 98 min | +4.35 K at 23 min |

The `printed` case crosses the figure once, near 25 min, and is 8.55 K high at 119 min. The `table_v` case meets Fig. 10 from 106 to 113 min and ends 0.43 K high at 119 min. In constant air it comes within the allowance of Fig. 9 at 91 min, crosses the figure at about 95 min and keeps rising: 41.56 degC at 119 min and 42.84 degC steady, against their flat 40.7 degC from about 80 min.

Coil mean beside the maximum, 119 min, Fig. 8 air: `printed` 59.00, `table_v` 50.57 degC (Fig. 10 52.09). With the mean, `table_v` is 1.52 K low at 119 min, so the choice of metric does not turn the gate.

Table VI at 120 min, equivalent conductivity, printed to 0.1 K (rounding 0.05 K). The 120 min time is an inference (section 9.1). The pairs are by rank, an inference: our maximum with C (far from the laminations), our mean with B (middle), our minimum with A (near the laminations). Point A is a place and our minimum is the coldest coil node, so the min-A row compares different places.

| Case | Ours max / mean / min (degC) | max - C | mean - B | min - A | Mesh error | Time-step error |
|---|---|---|---|---|---|---|
| `printed` 5 mm | 60.74 / 59.09 / 55.10 | +8.14 | +7.39 | +4.40 | 0.024 | 0.003 |
| `table_v` | 52.62 / 50.68 / 45.89 | +0.02 | -1.02 | -4.81 | 0.023 | 0.004 |

The `table_v` maximum meets C within 0.02 K, inside 0.05 + 0.023 + 0.004 K. Mean against B and min against A do not. The layered-winding column of Table VI (57.5, 71.9, 76.4 degC) is not compared: our winding is the equivalent-conductivity model only.

### The input difference found: the frame

The printed frame cannot reach Fig. 10 at any thickness in their Fig. 12(f) range, 5 to 25 mm. At 25 mm it is still 3.87 K high at 119 min (55.96 degC) and 3.49 K high in the constant-air steady state (44.23 degC). A thicker shell also lowers the early curve, which is already low (39.68 degC at 30 min, 2.88 K under Fig. 10).

The frame lump of their own network (Table V) brings the late state to the figures. At 119 min `table_v` is 0.43 K above Fig. 10, and at 120 min its maximum is 0.02 K above Table VI C. Their 2-D model most likely used that frame, or one close to it (an inference). The paper does not print it as a 2-D input.

### The remaining gap: the shape and the early rise

With the Table V frame, ours is outside the allowance from 2 min to 105 min. The gap is 3.35 K at 2 min, 4.30 K at 5 min, 4.97 K at 29 min, 2.42 K at 70 min, and is inside the allowance from 106 min (still negative to 109 min). In constant air ours is low to about 94 min and then rises past their plateau. Their curves rise faster early and settle sooner.

Early rise. Their Fig. 10 rise in the first minute is 3.82 K (23.82 +- 2.01 degC, so 1.81 to 5.83 K). Ours is 2.00 K. The factor is 1.9, with a range of 0.9 to 2.9, so the Fig. 10 point at 1 min passes. The Fig. 9 point at 1 min misses by 0.10 K. At 2 min their rise is 7.04 +- 1.00 K and ours is 3.69 K: a factor 1.9 (1.6 to 2.2). Adiabatic copper (Table II rho c over our coil area, Table IV copper loss) rises 2.26 K/min, 4.52 K in 2 min. Their 2 min rise is 1.5 to 3.5 K above that.

Hypotheses, not facts. The diagnosis (screening mesh, 30 s steps, not part of the gate, in the plan `docs/superpowers/plans/2026-11-24-r5e-v2-faiz.md`, "Findings from the diagnosis") tried one input at a time on the `table_v` case:

| Change, `table_v` frame | 1 min | 5 | 10 | 30 | 119 min | Result |
|---|---|---|---|---|---|---|
| Fig. 10 (target) | 23.82 | 31.70 | 35.26 | 42.56 | 52.09 | |
| none | 22.0 | 27.3 | 30.8 | 37.6 | 52.5 | late state agrees |
| winding rho c x 0.4 | 23.7 | 30.1 | 32.8 | 38.7 | 53.0 | closes minute 1 only |
| winding rho c x 0.25 | 24.7 | 31.0 | 33.3 | 39.0 | 53.2 | within the error at 1 min, 0.7 K low at 5 min; 10 to 30 min stay 2.0 to 3.6 K low |
| copper loss x 2.4 | 24.7 | 36.8 | 44.1 | 55.3 | 75.6 | 23.5 K high at 119 min, ruled out |
| R1 conductance, `printed` frame capacity | 22.0 | 27.6 | 32.1 | 42.0 | 55.4 | 30 min within 0.6 K, 3.3 K high at 119 min |

Winding capacity alone, loss density alone and frame conductance alone each fail. Their 2-D model most likely differs from the printed inputs in more than one place: the frame boundary, and something that heats the winding faster early. The paper does not let us find which. The copper x 2.4 factor was chosen against the old 1 min reading (25.38 degC, section 9.3).

### Numerical error

Mesh error |full - reference| is 0.004 to 0.028 K over the four series. Time-step error |15 s - 7.5 s| is 0.002 to 0.048 K, largest at 4 to 5 min. Both are small against the figure errors (0.09 K and up). For a first-order scheme |dt - dt/2| is about half the error of the dt run, and |full - reference| slightly under-estimates the error of `full`, because `reference` has an error of its own. Doubling both terms moves 3 of 454 points to pass (`printed` Fig. 10 at 22 and 23 min, `table_v` Fig. 9 at 99 min) and changes no case verdict.

Energy balance: the JSON does not store it. The fast test `tests/thermal/test_thermal_faiz.py::test_steady_heat_balance` checks it for both frames: in a constant-air steady state the heat to the fixed lumps equals the 40.9 W of losses within 1e-6 relative. The same file checks the part areas against Table I and the load against Table IV.

### Input rows

Change of the coil maximum in K, `full` mesh. The frame rows run on `printed` (nominal 5 mm), the liner and wedge rows on `table_v`.

| Row | 30 min | 60 min | 119 min | Constant-air steady |
|---|---|---|---|---|
| frame 15 mm | -2.10 | -2.63 | -2.49 | -1.21 |
| frame 25 mm | -3.63 | -4.79 | -4.68 | -2.24 |
| liner -1 px (-0.059 mm) | -0.29 | -0.30 | -0.30 | -0.29 |
| liner +1 px (+0.059 mm) | +0.30 | +0.31 | +0.32 | +0.29 |
| wedge -1 px (mesh noise) | -0.02 | -0.02 | -0.02 | -0.04 |
| wedge +1 px (mesh noise) | -0.01 | -0.01 | -0.01 | +0.03 |

A thickness read between two edges carries +-1 px per edge, up to +-0.12 mm. At that width the liner row would be about +-0.6 K, if the effect stays linear (an inference). No input row is near the 3 to 5 K gap. The slot-top fillet row (0 to 1.3 mm, section 9.1), the wedge chord shape and the pole-tip tab were not run.

### What this means for the ratings

V2 does not show our solver wrong. With their frame lump, the 119 min state and Table VI C agree within 0.43 K and 0.02 K, and the mesh and step errors are under 0.05 K. V2 does not show it right either. The shape differs by up to 4.97 K. The most likely cause is an input the paper does not print (a hypothesis). V2 cannot say which model is right, because both are models and no measurement is involved.

If their early rise is the true one, our model of this case reads 3.4 to 5.0 K low from 2 to 29 min after a cold start. That case has a fixed loss and copper rho c over the whole coil. The rating differs in three ways. Its peak lasts 30 s by default (`Requirements.peak_duration_s`). It starts from a warm steady state. Its coil capacity is fill x copper rho c (`srmapp.thermal_network`), which heats faster early: the x 0.4 row above is 0.1, 1.6, 2.5 and 3.9 K low at 1, 5, 10 and 30 min. The rating's peak lies inside the first minute, where V2 cannot tell the curves apart. Load steps of several minutes are where the gap would matter (an inference).

V2 adds no row to the R5 budget. Spec section 7 names no V2 row, and the spec's V2 failure path is to record the input difference and state the gap. This follows the V3 record, where the gap is stated and not fitted away. The `thermal_mesh` row stays 0 (see the thermal mesh note). The `end_winding_model` row is set by V4 (below). The continuous rating still has no measured check. V2 is a code-to-code comparison and does not change that.

## V4: our thermal network against the Kiyota 18/12 peak transient

Verdict: V4 passes. The nominal coil-end peak rise is 39.22 K at `full` against the measured 39.5 +- 0.4 K, so the model reads 0.7 % cold (r = +0.00716). Against the printed 41 K it reads 4.5 % cold (r = +0.0454) and passes only through the resistance row. The band is 36.5 to 42.5 K. The result depends on an iron specific heat carried over from another lamination (see below).

Run: `kiyota-v4b`, 2026-11-27, 57.5 min, LattePanda, commit 1348c0b, srmcore 0.8.0, srmapp 0.11.0, peak RSS 2778 MB. Iron capacity counts the stacking factor (0.90), which moved the peak by +0.02 K against the first run (39.20 K). Command: `$env:PYTHONPATH="src;tests"; python examples\kiyota_thermal_check.py --json docs/validation/r5_v4_kiyota.json`. Record: `docs/validation/r5_v4_kiyota.json`. Case: `tests/kiyota_thermal.py`.

Inputs (sources and errors in `docs/r5-sources.md` 9.2): the Fig. 8 RMS current read off the figure (140.7 A hold, 14 s), uniform start at 51.1 degC, ambient 25 degC (assumed), 573 W mechanical loss (Fig. 7), iron loss 4400 W (Table III (b)) divided by `K_IRON_HI` at 1500 Hz for the nominal set and applied whole in the rated set, uniform over the stator iron. Phase resistance 92.5 mOhm at 20 degC, the winding alone. The paper prints 97.8 mOhm at the terminals and says that 5.3 mOhm of it is coil connections (0.78 m) and terminal wiring (1.68 m in all; 2014 pp. 5714-5715). Eq. (1) gives 4.9 mOhm for 1.68 m, so the winding is 92.5 to 92.9 mOhm. The tool's mean-turn value is 92.6 mOhm. Iron capacity is 438 J/(kg K) x 7490 kg/m3 x 0.90 from the library record (the heat load is per gross stack volume). The quantity compared is the maximum over 0 to 20 s of the hottest end-winding lump above the start temperature. The rating's hot spot (coil sides included) is reported beside it: 39.22 K nominal and 39.82 K rated at `full`, not judged. The rated set leaves the `end_winding_model` row out, because that row carries this gate's own residual.

Results (rise above 51.1 degC, K):

| Preset | Thermal-domain nodes | Nominal | Rated | Wall time (nominal, rated) |
|---|---|---|---|---|
| screening | 73 879 | 39.22 | 39.82 | 27 s, 27 s |
| full | 135 396 | 39.22 | 39.82 | 89 s, 94 s |
| reference | 951 237 | 39.22 | 39.82 | 259 s, 261 s |

Mesh build: 28 s, 53 s and 719 s. The model reaches the peak earlier than the trace. At 10 s it reads 30.5 K against 22.7 K on the trace, and at 14 s 39.1 K against 35.5 K. The trace peaks after the current stops, and the model does not reproduce that lag. A sensor lag is not modelled and a time-matched comparison is out of scope, so the peak is compared and the shape is not.

Numerical error (nominal, K): mesh |full - reference| 0.002, time step |0.05 s - 0.025 s| 0.011, total 0.014. For the rated set the total is 0.011 K.

The 573 W mechanical loss may be counted twice: Table III (b) prints "iron and other losses" 4.4 kW and mechanical 0.7 kW as separate lines, so the 4.4 kW probably leaves it out (an inference: `docs/r5-sources.md` does not say so outright). Either way it moves the nominal peak by +0.007 K (39.210 K without it, 39.216 K with it, `screening`). The bike-gates plan (its D9) reconciles the loss split when that plan lands.

The trace keeps rising about 4 s after the current stops. As an inference, the measured peak is then probably a lower bound of the coil-end peak, and r is most likely the smallest reading.

Input rows (change of the end-lump peak in K, `full` nominal, signed):

| Row | Low | High |
|---|---|---|
| Resistance 92.5 to 97.8 mOhm (94.9 mOhm is the inference with the connections at the coil end: +1.08) | 0 | +2.40 |
| Cold-iron start (copper and end lumps at 51.1, the rest at the ambient) | -2.50 | 0 |
| Iron 0.6 kW (Table III (c)) | -0.10 | 0 |
| Mechanical loss at the end caps | 0 | +0.16 |
| Stator pole arc +-0.3 mm | -0.07 | +0.07 |
| Housing 4 and 16 mm, rotor pole arc, rotor yoke (0.00 each), ambient 40 degC (+0.02) | each at most 0.02 | |

Band: the low end is the nominal 39.22 K at `full` minus the negative rows (-2.68 K), 36.53 K. The high end is the rated set (39.82 K, 0.60 K above the nominal) plus the positive rows (+2.65 K) plus the numerical error (0.01 K), 42.48 K.

Pass rule: the band must reach the target within its reading error, that is low at most target + 0.4 K and high at least target - 0.4 K. For 39.5 K the nominal is 0.28 K below it, inside the 0.4 K reading error, so the trace pass needs no row. For the printed 41 K the high side must reach 40.6 K. The rated set (39.82 K) does not, and the resistance row (+2.40 K) does. The earlier plan risk that V4 passes only through the resistance row is reversed for the trace: the diagnosis had used the terminal resistance, which reads 41.6 K.

Zero-capacity effect: without iron capacity the coil end read 49.2 K nominal (63.3 K rated) at the terminal resistance. With the library specific heat it reads 41.6 K at 97.8 mOhm and 39.2 K at 92.5 mOhm. The iron stores part of the heat in the first seconds. The 438 J/(kg K) is carried over from Faiz 2009 Table II (p. 2928), a lamination of unstated grade, not 10JNEX900 (grade C, owner decision 2026-11-27). The V4 pass depends on it. A measured 10JNEX900 value would move the result.

What this means for the ratings: the peak transient of the end winding reads 0.7 % cold against the measured peak. Call 9 of the plan applies: r > 0, so the `end_winding_model` row is set to r. The rated set divides every end-winding lump capacity by 1 + `END_WINDING_PEAK_RESIDUAL` (0.007159, `srmapp.cooling`). The row moves the peak rating only. Its budget share is 0 K by construction, because shares are steady hot-spot rises. The rating's steady (continuous) side still has no measured check. V4 is one machine, one 14 s pulse, one coil-end sensor of unknown position, and an assumed ambient and housing. Against the owner's 10 to 15 % target: V4 checks copper heating in a 14 s copper-dominated pulse, with the iron loss held at a measured-over-model factor and not predicted (finding 1 of `docs/r3-loss-results.md`). The closed-form adiabatic copper rise alone is 40.60 K (`adiabatic_copper_rise_k` in the JSON), 2.8 % from 39.5 K, and the conduction and cooling rows (cross_wire, liner, contact, air gap, cooling h, lamination k) do not reach the 14 s peak. So V4 does not check the cooling paths, a 30 s peak from warm, or the continuous rating.

## Thermal mesh (no separate gate, owner 2026-11-27)

Verdict: the rating's thermal network changes by at most 0.26 K at `screening` and 0.16 K at `full` against `reference` on the 8/6, under the 0.5 K rating tolerance (`TOL_K`). The `thermal_mesh` row stays 0. A finer thermal mesh runs in the confirm step (roadmap section 0, Bike motor v1 part 7).

Run: planning probe of 2026-11-26, LattePanda, a script in `/tmp` that is not in the repository. The 8/6 with 10JNEX900 laminations of 0.1 mm, 24 turns of one 1.0 mm strand, R from `series_resistance` at 20 degC, the machine's default fill. The network is `build_network` with the placeholder `CoolingSetup()` and coefficients at 2000 r/min. The loads are fixed on every mesh. DC copper is 10 A RMS for the steady state and 20 A RMS for the 30 s peak (`srmapp.thermal.peak_transient`, from that steady state). Iron is 30 W, 0.7 in the stator iron and 0.3 in the rotor iron, uniform per part, times `iron_factor` in the rated set. Two sets: nominal and rated (every row unfavourable). Hot spot in degC:

| Preset | Thermal-domain nodes | Nominal steady | Nominal peak | Rated steady | Rated peak | Wall time |
|---|---|---|---|---|---|---|
| screening | 31 543 | 96.894 | 120.733 | 134.801 | 161.170 | 16 s |
| full | 57 987 | 96.934 | 120.779 | 134.881 | 161.270 | 38 s |
| reference | 405 997 | 96.999 | 120.853 | 135.016 | 161.429 | 313 s |
| screening - reference | | -0.105 | -0.120 | -0.215 | -0.259 | |
| full - reference | | -0.065 | -0.074 | -0.135 | -0.159 | |

Wall times include the mesh. The rating's Illinois (regula falsi) search stops within `TOL_K` = 0.5 K below the limit, or at `BRACKET_REL`, so it stops anywhere in (-0.5, 0] K. A change of this size is inside the rating's stop tolerance. The `screening` preset is not the `full` knobs at a larger scale, so the three levels do not follow one h² line.

Limits:

- 8/6 only. The Kiyota case was not run: its planned steady load (60 A RMS, 1.5 kW iron) ran away above 1000 degC with the placeholder jacket. 30 A with 300 W stator iron gives 99.7 degC.
- Iron capacity was zero at the time. Steady values do not depend on it. The peak values do.
- The reference has an error of its own, so the differences read slightly low (an inference).

## First rating (8/6 screening, test fixture)

Source: `tests/app/test_thermal_rate.py` (slow), real 8/6 screening map, default placeholder cooling, 160 degC limit (class H). This is a test fixture. It is not a validation: no measured thermal case exists, the cooling is placeholder, and the map is `screening`.

Inputs: peak 3.0 Nm at 628 W, base 2000 rpm, max 6000 rpm, 400 V bus, 24 turns at 20 A, continuous power 100 W, only the base and max speeds rated (`n_speeds=1`), iron loss x2 in the rated set. (Recorded before `K_IRON_HI` became the Kiyota frequency curve on 2026-11-18; at these 200 and 600 Hz the rated factor is now 3.2.)

| Speed | Set | Continuous (Nm) | Peak (Nm) | Hot spot at continuous (degC) | Hot spot at peak end (degC) |
|---|---|---|---|---|---|
| 2000 rpm | nominal | 3.225 | 3.416 (envelope) | 158.6 | 123.9 |
| 6000 rpm | nominal | 3.164 | 3.354 (envelope) | 158.5 | 119.5 |
| 2000 rpm | rated | 2.304 | 3.105 (envelope) | 158.3 | 132.7 |
| 6000 rpm | rated | 2.230 | 3.049 (envelope) | 160.0 | 125.9 |

The lamination end faces are adiabatic (no cited through-stack conductivity); an earlier run that linked them to the end space gave continuous 3.245 / 3.184 Nm (nominal) and 2.340 / 2.223 Nm (rated) at 2000 / 6000 rpm, and the same peaks. Budget shares, in K of hot-spot rise at the rated continuous torque:

| Row | 2000 rpm | 6000 rpm |
|---|---|---|
| iron | 0.75 | 2.67 |
| em_torque | 6.80 | 6.58 |
| cross_wire | 0 | 0 |
| liner | 16.9 | 15.8 |
| contact | 5.61 | 6.20 |
| air_gap | 0 | 0 |
| cooling_h | 0.07 | 0.08 |
| lamination_k | 2.69 | 2.88 |
| thermal_mesh, end_winding_model | 0 | 0 |

Re-run 2026-11-27 (srmapp 0.10.1, 10JNEX900 iron capacity 438 J/(kg K) x density; same requirements and cooling, 29 strokes, 542 s rating wall time, 1128 s for the probe with the map):

| Speed | Set | Continuous (Nm) | Peak (Nm) | Hot spot at continuous (degC) | Hot spot at peak end (degC) |
|---|---|---|---|---|---|
| 2000 rpm | nominal | 3.226 | 3.416 (envelope) | 158.5 | 121.3 |
| 6000 rpm | nominal | 3.159 | 3.354 (envelope) | 158.5 | 116.6 |
| 2000 rpm | rated | 2.309 | 3.105 (envelope) | 159.9 | 130.8 |
| 6000 rpm | rated | 2.069 | 3.049 (envelope) | 158.3 | 123.5 |

Budget shares of the re-run, in K of hot-spot rise at the rated continuous torque (the torque differs from the first run at 6000 rpm, so the shares do too):

| Row | 2000 rpm | 6000 rpm |
|---|---|---|
| iron | 1.66 | 5.92 |
| em_torque | 6.79 | 5.78 |
| cross_wire | 0.05 | 0.04 |
| liner | 16.9 | 14.4 |
| contact | 5.62 | 5.82 |
| air_gap | 0 | 0 |
| cooling_h | 0.07 | 0.07 |
| lamination_k | 2.69 | 2.69 |
| thermal_mesh, end_winding_model | 0 | 0 |
| mechanical_loss | 0.01 | 0.08 |

(Source: the `Rating.shares` printed by the probe; the first-run table has no cross_wire value, no mechanical_loss row and shows 0 for cross_wire.) What moved and why:

- Peak-end hot spots fall 2.6 (2000 rpm) and 2.9 K (6000 rpm) in the nominal set and 1.9 and 2.4 K in the rated set. Inference, not isolated: iron now stores heat during the peak transient, which lowers the peak-end hot spot. In the rated set this is the net of the capacity (down) and the higher iron factor (up, `K_IRON_HI` 3.2 and more). The peaks stay at the envelope.
- Steady values do not depend on capacity (the steady solve does not use it). The nominal continuous torques equal the first run within 0.2 % (3.225 to 3.226, 3.164 to 3.159 Nm).
- The first table was recorded 2026-11-09. Four changes to rating inputs landed after it and were not isolated from each other: `K_IRON_HI` as the Kiyota curve (2026-11-18), the continuous-conduction strokes (srmapp 0.10.0), friction and windage heat with the `mechanical_loss` row (2026-11-17, 4d754f1), and the `cross_wire` nominal as Milton with xi 0.324 instead of Hashin-Shtrikman at fill other than 0.37 (2026-11-17, 1cc953b; it moves the nominal set).
- The rated continuous torque at 6000 rpm falls 7 % (2.230 to 2.069 Nm). The shares are taken at that torque, so they follow it at 6000 rpm: em_torque 6.58 to 5.78 K, liner 15.8 to 14.4, contact 6.20 to 5.82, lamination_k 2.88 to 2.69. The iron shares rise (0.75 to 1.66 and 2.67 to 5.92 K) with the iron factor. These changes come from the four input changes above, not from the capacity.
- The 2000 rpm rated continuous torque moves 2.304 to 2.309 Nm (+0.2 %), within the 1 % bracket resolution; no cause is attributed.

The probe's asserts (relations only) passed unchanged.

In the first run 28 strokes were solved. The liner row dominates: the liner takes its plain conductivity over the full band and no coil-to-liner contact is assumed. The hot spot is within 1.5 K of the limit at every limit-bound speed (the bracket stops at 1 % of the torque). Run time of the first run: 550 s for the module on the bench host.

## R5b: the R5a open list, item by item

- Liner band 76 % yoke band: done in R5b. `thermal_network.py` gives the band the plain `k_liner` over its full geometric width and assumes no coil-to-liner contact (errs hot; ratings read low if the real slot has resin contact). Owner may decide contact later.
- Liner classification cost: not an issue at the single-case rating (done once per rating). A KD-tree prefilter is an R5c item, if the rating runs per candidate.
- Backward Euler under-predicts a heating rise: done in R5b. `rate_speed` doubles the step count until the final hot spot changes by under 0.1 K (`STEP_TOL_K`) or the step cap is reached.
- Temperature-dependent h needs a solver rebuild: decided against in R5b, to avoid a solver rebuild per iteration. Natural convection is evaluated at an assumed 80 degC surface and forced convection at the film temperature of the inlet; the small unsigned error is stated in the rating notes.
- `gap_closure` non-optional `MechanicalData`: done in R5b. `rate` checks `mechanical is None` first and notes that there is no gap closure.
- Iron specific heat carried over 2026-11-27 (438 J/(kg K), Faiz 2009, owner decision; srmapp 0.11.0), so iron has capacity (before that it was zero, with a note). Expansion and through-stack conductivity stay open: the 10JNEX900 gap entries have centrifugal growth only. The cited lamination value (18.6 W/(m K), band in `K_LAMINATION`) has no stated direction and is used in-plane only; the lamination end faces are adiabatic (errs hot) until a through-stack value is cited (owner item, tracker 10d). Expansion and through-stack conductivity are on the owner list below (material data, tracker 10d).
- Six FE-derived constants need the owner's yes: moved to the owner list below.
- Search candidates read `no_fillet`: moved to the owner list below (before R5c).
- Kiyota 18/12 V6: R5e.

## Open after R5b

R5c:
- Ratings replace `j_limit` in the winding choice and the search ranking; `Evaluation.rating`; version bump.
- Liner classification KD-tree prefilter, if the rating runs per candidate.

R5d:
- Web: route, job kind and Thermal tab for ratings; run report; options-graph axes. None exist yet.

R5e:
- V0, V2 and V4 are recorded above and in docs/r5-sources.md section 9. V5 has no separate gate: the thermal mesh note stands, and a finer thermal mesh runs in the confirm step (roadmap section 0). The continuous rating has no measured check.
- Moved out by roadmap section 0 (owner, 2026-11-26): V6 on the Kiyota rotor (Bike motor v1 part 8) and the 8/6 and bench-target demonstrations.

R6:
- A re-rate with new cooling needs new strokes. Spec section 10 promised cached strokes and thermal solves only; R5b does not meet that. R6 needs a loss-against-torque reuse design.

Owner:
- Cooling concept: decided 2026-11-10 (core spec section 11): oil spray on the end windings plus the jacket at high load, the oil cooled into the water loop by a 3D-printed heat exchanger; jacket only at low load. The search default stays jacket only; end spray is an opt-in setup. The cooling placeholders stay as flagged defaults (owner, 2026-11-10; the UI labels them "placeholder cooling"): ambient 40 degC, housing 8 mm, jacket 4 x 20 mm, 4 passes, 9 L/min of 50/50 water-glycol at 65 degC.
- The contact gap and resin conductivity (cited nominals 0.03 mm and 1.0 W/(m K), unfavourable 0.08 mm and 0.6) and any placeholder in docs/r5-sources.md section 7.
- End spray runs with Shell Diala S4 ZX-I since 2026-11-10 (cp from Cragoe 1929, density from the Shell data sheet; docs/r5-sources.md 6.7). Shaft oil stays refused (no cited h). An oil slot channel stays refused: no viscosity curve and no laminar Nu are read. The oil's thermal expansion is not cited, so the spray oil rise reads a few percent low.
- Iron specific heat for 10JNEX900 is carried over from Faiz 2009 (438 J/(kg K), 2026-11-27) until the jystator data arrive. Thermal expansion for 10JNEX900 (tracker 10d) stays open: the stator thermal growth stays absent.
- Rotor stress, decided 2026-11-10 (core spec section 11): the six FE-derived constants are accepted, and search candidates carry a rotor root fillet of 0.05 x the pole width at the root (`generator.ROTOR_FILLET_SHARE`), inside the fit's 0.025 to 0.2 ratio.
- Peak start state: decided 2026-11-10 (core spec section 11): the peak starts from the steady state at the required continuous torque (the current reading).
- Oil choice and the heat exchanger's approach (oil inlet minus water temperature). The oil is Shell Diala S4 ZX-I (owner, 2026-11-10); its cp and k still need a cited source. The approach is a wide band until measured.

Unresolved sources:
- Romanazzi air-gap correlation: recorded, not coded. The air-gap and end-space rows have zero width until a second cited route exists.
- Jacket Re below 1e4 (laminar or transitional): refused; the laminar Nu source is not read.
- Idoughi 2011 (xi against fill factor): not read (unreachable again 2026-11-17); the cited xi is carried to other fills inside the `cross_wire` band.

## R5c

Merged to main 2026-11-19, PR #34 (srmcore and srmapp 0.8.0, srmweb and `web/` 0.11.0): stage 2 checks the EM-feasible windings best-first against the rated hot-spot limit at the required torques, rates the first that holds, and the Pareto front is rated continuous and peak kW/kg. A rated evaluation of the 8/6 screening case took 629 s on the LattePanda (i5-1340P). A rated search rates every EM-feasible design: up to `MAX_THERMAL_CHECKS` (4) requirement checks per design plus one full rating. With no user `j_peak_max`, the wire-mode map range and scan use the 80 A/mm² peak screen `J_PEAK_SCREEN`. `losses.efficiency_map` takes the evaluation's `j_limit` as its RMS limit, so for an evaluation from the search it is now the 40 A/mm² screen `J_SCREEN`. Open: validation campaign for srmcore 0.8.0; the evaluate estimate does not count rating time (R5d).

## R5d

Merged to main 2026-11-22, PR #35 (CI green: fast on 3.12 and 3.14, web; srmapp 0.9.0, srmweb and `web/` 0.12.0, srmcore unchanged at 0.8.0, rating numbers unchanged). Shipped: the Thermal tab on evaluated cases (verdict, speed table, torque curves, temperature map with a steady or peak end and a speed picker, tornado of the budget rows, rotor stress and cooling lines, notes), the chips for rating, cooling and iron band, a Thermal section in the run report, rated continuous and peak kW/kg axes and columns, and an evaluate estimate that counts the rating time (store schema v3, table `rating_times`).

Rating time on the LattePanda (i5-1340P), 8/6 reference case, 2026-11-22, `examples/rating_timing.py` (span from the first thermal callback to the return, so it includes the winding checks):

| Preset | Rating span | Evaluate total | Budget (x 1.25) |
|---|---|---|---|
| screening | 850.0 s | 1070.3 s | 1063 s |
| full | 1631.0 s | 2738.0 s | 2039 s |
| reference | not run | not run | 8155 s (4 x full) |

Files: `docs/validation/r5d_rating_screening.json`, `docs/validation/r5d_rating_full.json`. The budgets are `cases.RATING_BUDGET_S`; they apply only when no rating of that preset has been timed.

Browser check (headless Chromium, 1440 px and 375 px, srmweb with the built frontend):
- Rated 8/6 screening case, 100 W continuous: pass at both widths. Verdict "Meets the requirement", six speed rows, curves, a non-blank temperature map (70 to 99 degC), speed picker changes the map and the tornado, rotor and cooling lines, notes. At 375 px the Speed column stays fixed, a row tap opens its detail and the map renders at 300 x 300 px. The Peak end shows "No peak state at this speed" because every speed is EM-bound; the end toggle changing the map was checked on the failing case.
- Failing case (620 W, class F, no jacket): pass. It fails with NO_STROKE at 1000 r/min ("no stroke reaches the required torque"), shown in red. The HOT_SPOT_ABOVE text was not reached in the browser (raising power alone left the jacket case passing; ambient 60 degC or more refuses the rating); that text is covered by unit tests only.
- Pre-R5d evaluation (summary, check and fields removed, flat rating keys): no crash; the table shows, with "Edit, then Evaluate, for full detail". The Rotor column read "no steady state" for every speed; fixed, a missing value now reads "–" (test in `web/src/lib/thermal.test.ts`).
- Run report exported and opened offline (5 MB, network blocked): Thermal section with verdict, table, curves, temperature map image, uncertainty table, rotor and cooling, notes; no page errors.
- Cache cleared: the map slot says "Re-evaluate to see the map"; table, verdict and plots still render.
- Cases table: the rated kW/kg and kW/L columns are present. The options graph and search were not run in the browser.
- Console: the 404 of the Losses lookup on every case view (existing) and the expected 410 after the cache clear. Not changed: the iron chip reads "Iron x3.2-3.2 band" for a zero-width band.

Fast suite: 1767 passed. Engine digest matches its pin.
