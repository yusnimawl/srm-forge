# R5 thermal and rotor stress results

This file holds the results of the R5a validation gates V1 to V6. V1 passed in tests/thermal. V6 is below and it failed. V0, V2, V3, V4 and V5 are pending.

## V6: analytic rotor stress against a 2D elastic FE

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

Verdict: FAIL. Bore and tip growth pass the 15 % rule. The root stress fails it by a wide margin, the analytic peak is 36 to 47 % below the FE peak, and the root FE value is not converged to 2 %. The analytic root stress, the nominal pole stress times Kt, is low against the FE. Nothing in the model, Kt or the limits was changed.
