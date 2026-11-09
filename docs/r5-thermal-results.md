# R5 thermal and rotor stress results

This file holds the results of the R5a validation gates V1 to V6. V1 passed in tests/thermal. V6 is below and it passed on the revised model. V3 is recorded below (not reproduced exactly). V0, V2, V4 and V5 are pending.

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

The paper gives xi for fill 0.37 only. Solving for xi gives 0.304 (0.37) and 0.195 (0.47); these are derived here, not in the paper. The measured-agreement values are about 24 % above the Milton ones; the paper reports no temperature error as a number. Handling (spec section 8 V3: revise the band, not the measured values): the nominal winding conductivity is Milton where xi is cited (fill 0.37) and the Hashin-Shtrikman lower bound elsewhere; the band's upper end covers 3.0 and 3.85. The measured values only widen the band.

## First rating (8/6 screening, test fixture)

Source: `tests/app/test_thermal_rate.py` (slow), real 8/6 screening map, default placeholder cooling, 160 degC limit (class H). This is a test fixture. It is not a validation: no measured thermal case exists, the cooling is placeholder, and the map is `screening`.

Inputs: peak 3.0 Nm at 628 W, base 2000 rpm, max 6000 rpm, 400 V bus, 24 turns at 20 A, continuous power 100 W, only the base and max speeds rated (`n_speeds=1`), iron loss x2 in the rated set.

| Speed | Set | Continuous (Nm) | Peak (Nm) | Hot spot (degC) |
|---|---|---|---|---|
| 2000 rpm | nominal | 3.245 | 3.416 (envelope) | 158.8 |
| 6000 rpm | nominal | 3.184 | 3.354 (envelope) | 159.0 |
| 2000 rpm | rated | 2.340 | 3.105 | 159.3 |
| 6000 rpm | rated | 2.223 | 3.049 | 158.7 |

Hot-spot values are at the continuous (nominal) or peak (rated) torque. Budget shares, in K of hot-spot rise at the rated continuous torque:

| Row | 2000 rpm | 6000 rpm |
|---|---|---|
| iron | 0.76 | 2.70 |
| em_torque | 7.67 | 6.47 |
| cross_wire | 0 | 0 |
| liner | 16.6 | 15.4 |
| contact | 5.76 | 6.31 |
| air_gap | 0 | 0 |
| cooling_h | 0.07 | 0.08 |
| lamination_k | 2.70 | 2.87 |
| thermal_mesh, end_winding_model | 0 | 0 |

29 strokes were solved. The liner row dominates: the liner takes its plain conductivity over the full band and no coil-to-liner contact is assumed. The hot spot is within 1.5 K of the limit at every limit-bound speed (the bracket stops at 1 % of the torque). Run time: 569 s for the module on the bench host.

## R5b: the R5a open list, item by item

- Liner band 76 % yoke band: done in R5b. `thermal_network.py` gives the band the plain `k_liner` over its full geometric width and assumes no coil-to-liner contact (errs hot; ratings read low if the real slot has resin contact). Owner may decide contact later.
- Liner classification cost: not an issue at the single-case rating (done once per rating). A KD-tree prefilter moves to R7 if it runs per candidate.
- Backward Euler under-predicts a heating rise: done in R5b. `rate_speed` doubles the step count until the final hot spot changes by under 0.1 K (`STEP_TOL_K`) or the step cap is reached.
- Temperature-dependent h needs a solver rebuild: not needed. Natural convection is evaluated at an assumed 80 degC surface and forced convection at the film temperature of the inlet; the small unsigned error is stated in the rating notes.
- `gap_closure` non-optional `MechanicalData`: done in R5b. `rate` checks `mechanical is None` first and notes that there is no gap closure.
- No iron specific heat, expansion or through-stack conductivity: iron capacity is zero (a note says so; steady results are unaffected); the 10JNEX900 gap entries have centrifugal growth only. Through-stack conductivity comes from the cited lamination value (18.6 W/(m K), band in `K_LAMINATION`). Sourcing the rest moves to R5c.
- Six FE-derived constants need the owner's yes: moved to the owner list below.
- Search candidates read `no_fillet`: moved to the owner list below (before R5c).
- Kiyota 18/12 V6: R5e.

## Open for R5c and later

- Owner: the cooling concept (jacket, spray, shaft oil, slot oil). Defaults are placeholders: ambient 40 degC, housing 8 mm, jacket 4 x 20 mm, 4 passes, 9 L/min of 50/50 water-glycol at 65 degC.
- Owner: the contact gap and resin conductivity (cited nominals 0.03 mm and 1.0 W/(m K), unfavourable 0.08 mm and 0.6) and any placeholder in the table of docs/r5-sources.md section 7.
- Owner: oil property data (specific heat, conductivity, viscosity) for end spray and shaft oil. Both are refused until cited; the spray h band stays recorded. Slot oil runs with water-glycol only.
- Owner: the six FE-derived rotor-stress constants, and `rotor_fillet_radius` for search candidates (all read `no_fillet` now).
- Owner: whether the peak starts from the required continuous torque (the current reading) or from the rated continuous state. The second reading makes the peak about equal to the continuous rating.
- R6: a re-rate with new cooling needs new strokes. Spec section 10 promised cached strokes and thermal solves only; R5b does not meet that. R6 needs a loss-against-torque reuse design.
- V4 and V5 rows: pending (no measured continuous case; the continuous rating has no measured check).
- Romanazzi air-gap correlation: recorded, unresolved, not coded. The air-gap and end-space rows have zero width until a second cited route exists.
- Jacket Re below 1e4 (laminar or transitional): refused; the laminar Nu source is not read.
- Idoughi 2011 (xi against fill factor): not read; Milton stays at fill 0.37 only.
- Web: no route, job kind or tab for ratings yet.
- Kiyota 18/12 V6: R5e.
