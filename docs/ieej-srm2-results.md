# IEEJ SRM2 18/12 comparison

## Summary

- `full` on the LattePanda (2026-11-23, 328 072 nodes) moves every number by less than 0.6 points: aligned ψ −4.75 % and +4.37 %, worst torque −6.52 % and +8.06 % of the IEEJ peak, unaligned ψ within 0.32 %. The screening mesh is converged here, so the residual is the iron curve, not the mesh (section "`full` results").
- srmcore `screening` (NGSolve) on the IEEJ public-use SRM "SRM2" (the 18/12 of Chiba et al. 2015, 10JNEX900), phase A only, at the 16 portal positions from unaligned to aligned and 50 to 250 A, against the 2D FEA maps of IEEJ TR 1589.
- With the library 10JNEX900 (catalogue curve, stacking factor 0.9), the unaligned flux linkage agrees within 0.19 % at every current. The aligned flux linkage is 4.76 % low from 100 A up, the torque is up to 6.46 % of the IEEJ peak low, and the mean stroke torque at 250 A is 244.6 N m against 260.8 (−6.2 %).
- With stacking factor 1.0 (same curve, same mesh) the signs change: aligned ψ +4.36 %, torque up to +7.66 % of the peak, mean torque 279.7 N m (+7.2 %). The unaligned ψ stays within 0.18 %.
- So the geometry and the air path agree, and the residual comes from the iron curve. The portal shows the B-H curve behind its maps as a figure only, so this comparison cannot separate srmcore's error from the curve difference by itself. A scratch run on the portal figure curve (as traced by mufem, stacking factor 1.0) still reads +4.50 % aligned ψ and +7.37 % torque of the peak at 250 A: the figure curve does not explain the gap. mufem's own 2D-equivalent 3D variant on the same traced curve reads +5.3 % aligned ψ and +7.0 % torque at 6°, so two independent codes agree with each other and both read about 5 % above the IEEJ maps. Interpolating between the two srmcore runs, the IEEJ aligned ψ at 250 A matches a stacking factor of about 0.95 (0.946 from the mean torque); the portal does not state one.
- What agreement proves: srmcore reproduces an independent 2D tool on a large, heavily saturated 18/12 traction machine with an exact drawing, inside the spread that the stacking factor alone opens. What it does not prove: the IEEJ maps are 2D FEA, not measurements, and the curve they used is not known exactly.
- Reproduce with `PYTHONPATH=tests python examples/ieej_srm2_check.py [--stacking 1.0]`. The machine is `tests/ieej_srm2.py`, the fixture `tests/validation/fixtures/ieej_srm2` (source, terms and conventions in its README), the slow test `tests/validation/test_ieej_srm2.py`, and the evidence `docs/validation/ieej_srm2_screening.json` and `ieej_srm2_screening_sf1.json`. The screening run took 34 s to mesh (178 256 nodes) and 497 s for 80 solves on 4 workers of the Claude cloud container (2026-11-22).
- Credit: Raiden Numerics' mufem validation case and LinkedIn post pointed us to this data, and their write-up first noted the half-machine torque table.

## Machine and assumptions

The machine and its sources are in the fixture README. Assumed where the portal says nothing (`ieej_srm2.ASSUMED`):

| Field | Value used | Why |
|---|---|---|
| geometry | read off `SRM2_CAD.dxf` | the drawing does not pass `read_loops` as it is (partial section, construction circles, open contours, one duplicate edge); radii and angles are exact to the drawing |
| `stator_pole_taper`, `rotor_pole_taper` | 10.000°, 3.0° | the flank direction against the pole axis in the drawing (rotor 3.0014°) |
| `slot_liner_thickness` | 0.1 mm | the drawing's coil side lies on the pole flank |
| `coil_inner_clearance` | 1.0 mm | coil from r = 90.5 mm, as drawn |
| `fill_factor` | 0.5 | sets resistance only, not ψ or torque |
| shaft | `copper` (vacuum law) | the portal gives no shaft material; the rotor yoke is 35 mm deep, so the shaft carries almost no flux |
| stator and rotor material | `10JNEX900`, stacking factor 0.9 (library) and 1.0 (`--stacking 1.0`) | the curve behind the portal maps is a figure only |
| band | 1440 divisions at `screening` (2160 `full`, 6120 `reference`) | a multiple of 360 puts every 1° portal position on a band node, and of lcm(18, 24) = 72; each is the multiple of 360 nearest to the preset's own choice (1512, 2160, 6048). 720 divisions failed the mesh quality gate (min angle 6.8°) |

Angles: portal position x = 10 is unaligned and x = 20 aligned. The srmcore rotor angle is 1.5 (x − 10) − 15°. Torque is positive on the unaligned-to-aligned stroke in both tools.

Torque table: the torque from the co-energy of `SRM2_Flux-I.csv` is 1.95 to 2.03 times `SRM2_T-position.csv` at the interior positions (central differences on the 1° grid), so the table is the torque of a half-machine model. The comparison doubles it.

## Results at 250 A, `screening`

| stroke angle (°) | ψ SF 0.9 (Wb) | ψ SF 1.0 | ψ IEEJ | dψ SF 0.9 | dψ SF 1.0 | T SF 0.9 (N m) | T SF 1.0 | T IEEJ x 2 |
|---|---|---|---|---|---|---|---|---|
| 0 (unaligned) | 0.3085 | 0.3097 | 0.3091 | −0.19 % | +0.18 % | −0.0 | −0.0 | −0.4 |
| 2 | 0.3244 | 0.3279 | 0.3261 | −0.51 % | +0.57 % | 150.4 | 158.6 | 156.2 |
| 4 | 0.3619 | 0.3728 | 0.3667 | −1.29 % | +1.69 % | 329.1 | 368.4 | 345.4 |
| 6 | 0.4060 | 0.4253 | 0.4142 | −2.00 % | +2.66 % | 373.9 | 422.7 | 396.2 |
| 8 | 0.4469 | 0.4763 | 0.4605 | −2.96 % | +3.44 % | 357.9 | 410.1 | 382.8 |
| 10 | 0.4733 | 0.5144 | 0.4940 | −4.19 % | +4.13 % | 306.5 | 361.5 | 331.1 |
| 12 | 0.4893 | 0.5350 | 0.5130 | −4.62 % | +4.29 % | 220.0 | 262.3 | 240.9 |
| 14 | 0.4974 | 0.5449 | 0.5222 | −4.75 % | +4.35 % | 95.0 | 113.9 | 106.2 |
| 15 (aligned) | 0.4985 | 0.5462 | 0.5234 | −4.76 % | +4.36 % | 0.0 | 0.0 | −1.0 |

All 16 positions are in the evidence JSON files.

## Results per current, `screening`

| current (A) | SF | worst dψ | dψ unaligned | dψ aligned | peak T (N m) | peak T IEEJ x 2 | worst dT / IEEJ peak | mean T (N m) | mean T IEEJ |
|---|---|---|---|---|---|---|---|---|---|
| 50 | 0.9 | −3.30 % | +0.13 % | −1.68 % | 56.5 | 57.5 | −5.15 % | 38.2 | 38.2 |
| 100 | 0.9 | −4.46 % | +0.13 % | −4.46 % | 146.3 | 152.4 | −5.39 % | 98.9 | 101.8 |
| 150 | 0.9 | −4.70 % | +0.10 % | −4.70 % | 231.2 | 242.3 | −5.78 % | 155.2 | 162.2 |
| 200 | 0.9 | −4.76 % | −0.01 % | −4.76 % | 306.1 | 323.5 | −6.08 % | 204.1 | 215.6 |
| 250 | 0.9 | −4.76 % | −0.19 % | −4.76 % | 373.9 | 396.2 | −6.46 % | 244.6 | 260.8 |
| 50 | 1.0 | +6.10 % | +0.14 % | +6.10 % | 58.9 | 57.5 | +8.18 % | 40.1 | 38.2 |
| 150 | 1.0 | +4.51 % | +0.13 % | +4.50 % | 255.8 | 242.3 | +7.41 % | 172.7 | 162.2 |
| 250 | 1.0 | +4.36 % | +0.18 % | +4.36 % | 422.7 | 396.2 | +7.66 % | 279.7 | 260.8 |

The mean torque is W′(aligned) − W′(unaligned) over the 15° stroke, for srmcore from its co-energy and for IEEJ from the co-energy of the flux table (the doubled torque table gives 260.0 N m at 250 A).

## `full` results

LattePanda, 2026-11-23 (`docs/validation/ieej_srm2_full.json`, `ieej_srm2_full_sf1.json`): 328 072 nodes, band 2160
divisions; stacking 0.9 on 8 workers (mesh 34 s, 80 solves 548 s), stacking 1.0 in one process (mesh 33 s, 48 solves
1556 s).

| current (A) | SF | worst dψ | dψ unaligned | dψ aligned | peak T (N m) | peak T IEEJ x 2 | worst dT / IEEJ peak | mean T (N m) | mean T IEEJ |
|---|---|---|---|---|---|---|---|---|---|
| 50 | 0.9 | −3.24 % | +0.30 % | −1.64 % | 56.5 | 57.5 | −4.70 % | 38.2 | 38.2 |
| 100 | 0.9 | −4.44 % | +0.30 % | −4.44 % | 146.3 | 152.4 | −5.09 % | 98.9 | 101.8 |
| 150 | 0.9 | −4.68 % | +0.25 % | −4.68 % | 231.2 | 242.3 | −5.59 % | 155.2 | 162.2 |
| 200 | 0.9 | −4.75 % | +0.13 % | −4.75 % | 306.3 | 323.5 | −5.93 % | 204.0 | 215.6 |
| 250 | 0.9 | −4.75 % | −0.07 % | −4.75 % | 374.0 | 396.2 | −6.52 % | 244.5 | 260.8 |
| 50 | 1.0 | +6.14 % | +0.31 % | +6.14 % | 58.9 | 57.5 | +8.06 % | 40.2 | 38.2 |
| 150 | 1.0 | +4.54 % | +0.28 % | +4.51 % | 255.9 | 242.3 | +7.37 % | 172.7 | 162.2 |
| 250 | 1.0 | +4.37 % | +0.32 % | +4.37 % | 422.9 | 396.2 | +7.55 % | 279.6 | 260.8 |

Against `screening`, the largest changes are 0.45 points in worst dT at 50 A (stacking 0.9) and 0.17 points in
unaligned ψ; aligned ψ and the mean torques move by less than 0.1 %. The slow test stays at `screening`.

## The B-H curve

The library 10JNEX900 is the JFE catalogue curve (grade B, stacking factor 0.9 from the catalogue's guaranteed minimum space factor). Against the mufem trace of the portal's B-H figure (CC BY-SA 4.0, used here for these numbers only and not copied into the repository), the library curve at stacking factor 1.0 is 1.9 to 3.1 % higher between 30 and 10 000 A/m, and at stacking factor 0.9 it is 7.2 to 8.3 % lower. The portal curve therefore looks like a material curve with no stacking factor applied.

### Run on the portal figure curve (scratch, not committed)

Same mesh, phase A, 50 and 250 A, 10JNEX900 replaced in-process by the mufem trace of the portal figure (points up to 20 000 A/m, stacking factor 1.0). The run and its JSON stay outside the repository because the trace is CC BY-SA.

| quantity at 250 A | srmcore on the figure curve / IEEJ | mufem without end effects / IEEJ (their README) |
|---|---|---|
| ψ unaligned | 1.002 | 1.027 |
| ψ at 6° | 1.022 | 1.046 |
| ψ at 10° | 1.041 | 1.054 |
| ψ aligned | 1.045 | 1.053 |
| T at 6° | 1.060 | 1.070 |
| T at 10° | 1.088 | 1.062 |
| mean stroke torque (N m) | 278.7 (IEEJ 260.8) | mufem full 3D 264.8 |

At 50 A the figure curve gives +3.87 % aligned ψ and +5.35 % torque of the peak (library curve at stacking factor 1.0: +6.10 % and +8.18 %).

Reading: srmcore and mufem agree within 2.6 points of the IEEJ value at every quantity in the table, and both sit above the IEEJ maps by 4 to 9 % in the aligned half of the stroke. The input behind the IEEJ maps is the likely cause (a stacking factor near 0.95, another curve than the figure, or a modelling detail the portal does not state); srmcore and the IEEJ tool were not shown to disagree on the same inputs.

## Test limits

`tests/validation/test_ieej_srm2.py` (slow) runs `screening` at 250 A with the library material. The limits are regression limits, the screening results above plus margin, not an agreement claim:

| Check | Limit | Screening result |
|---|---|---|
| ψ at unaligned | 1 % | −0.19 % |
| ψ at any position | 6 % | −4.76 % |
| torque at any position, of the IEEJ peak | 8 % | −6.46 % |
| mean stroke torque | 8 % | −6.2 % |
| torque at unaligned and aligned, of the IEEJ peak | 0.5 % | 0.0 % and 0.0 % |

Three fast tests check the fixture: the two tables share one grid, the torque table is the half-machine torque, and the geometry matches the drawing.

## Open

- The curve behind the portal maps: ask IEEJ for the table, or carry the bracket in the validation budget.
- mufem's 3D results for the same machine give ψ and T ratios against 2D with and without end turns; compare them with `tools/end3d` (R4, tracker row 1d).
- The DXF route: clean `SRM2_CAD.dxf` into closed loops and check that the imported iron gives the same map as the parametric design.
