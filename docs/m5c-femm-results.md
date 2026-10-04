# M5c: FEMM cross-tool comparison

## Summary

- srmcore `full` (NGSolve) agrees with FEMM 4.2 on all three machines far inside spec §8.3: ψ within 0.16 %, torque within 0.60 % relative (where |T| is at least 5 % of the peak at that current) and 0.45 % of peak.
- The largest error / limit ratio is 0.11 (Krishnan 8/6), 0.09 (Jiang 24/16) and 0.20 (synthetic 12/8).
- FEMM's own discretisation estimate (last level change) is up to 0.26 % in ψ and 0.21 % of peak in torque, the same size as the differences, so the remaining difference is at FEMM's mesh noise.
- Reproduce with `python examples\femm_check.py` (needs `PYTHONPATH=tests`). The slow test is `tests/validation/test_femm.py` (5 checks per machine, all pass: Krishnan 104 s, synthetic 12/8 173 s, Jiang 241 s).

## 1. Purpose

FEMM is the reference value. The check shows that an independent tool, with its own mesher, solver and torque method, gets the same ψ and torque as srmcore on the same geometry and the same B-H curve.

What agreement proves: assembly, Newton scheme, flux linkage, Arkkio torque and the moving band reproduce a second 2D magnetostatic solver.

What it does not prove:

- Both tools make the same 2D assumptions: no end effects, no eddy currents, no hysteresis, A = 0 on the stator outer diameter.
- Both tools use the same B-H law, so errors in the material data cancel.
- The Krishnan and Jiang models contain assumed fields (section 2), so this is not a comparison with the published machines. Agreement with real machines is M5b (TEAM 24) and M5d.

## 2. Machines

All three use the `full` mesh preset, default `RegionMaterials` (stator and rotor M19, shaft steel_1010, copper coils) and `outer_air_thickness` 0. The definitions are in `tests/femm_machines.py`.

### Krishnan 8/6

Stated values as in `docs/reference-machines.md` (Krishnan, 8/6 design example, Ch. 2). Fields not in the source:

| Field | Value used | Basis |
|---|---|---|
| `slot_liner_thickness` | 0.5 mm | not in the source |
| `coil_inner_clearance` | 1 mm | not in the source |
| fillets, tapers | 0 | not in the source |
| `fill_factor` | 0.22 | 77 turns x 1.588 mm² = 122 mm² of copper in a 550 mm² coil side; sets resistance only, not ψ or T |
| stator and rotor material | M19 | the book's machine is M43, which is not in the library; the cross-tool check needs only the same law on both sides |

### Jiang 24/16

Stated values as in `docs/reference-machines.md` (turns 15, fill 0.54, stator taper 6°, stator yoke 15 mm, pole arcs 7.0° / 7.2°). Built inside `waive_rules("self_starting")`; the validator flags nothing else.

| Field | Value used | Basis |
|---|---|---|
| `rotor_yoke_thickness` | 45.5 mm | assumed rotor pole height 20 mm (40 x air gap): 91.5 - 26 - 20 mm |
| `rotor_pole_taper` | 5.5° (0.0960 rad) | middle of the thesis's 3-8° sizing range |
| `slot_liner_thickness` | 0.3 mm | not in the source |
| `coil_inner_clearance` | 1 mm | not in the source |
| `stack_length` | 92 mm | 108 mm total minus 16 mm end-turn allowance |
| pole-shoe fillet | dropped | the 1 mm fillet has no topology counterpart |
| stator and rotor material | M19 | the thesis uses 10JNEX900, which is not in the library |

### Synthetic 12/8

`tests/conftest.py` `make_12_8()`: complete geometry, no waivers, no assumed fields.

## 3. FEMM model

Built by `tools/femm_fixtures.py` with pyfemm 0.1.3 on FEMM 4.2.

- **Geometry.** From `build_outline(design.machine)`: stator outer circle, stator inner boundary, coil sides; rotor boundary and shaft circle rotated by the angle. One FEMM document per point, built from scratch. Planar, millimetres, depth = stack length.
- **Angle.** Each angle is snapped to the band pitch of the `full` static mesh, so FEMM and srmcore use the identical angle.
- **Air gap.** Two construction circles at 1/3 and 2/3 of the gap.
  - Air-gap-element model (primary torque): both circles carry an air-gap boundary, the middle third is `<No Mesh>`, torque from `mo_gapintegral`.
  - Meshed-gap model (ψ and cross-check torque): the whole gap meshed, torque from the weighted stress tensor on rotor iron and shaft. The fixture's ψ is the meshed-gap value.
- **B-H.** FEMM gets `library_law(name).h_of_b` (the effective, stacked srmcore law including the tail towards Js) sampled at about 320 points from 0 to 4 T, with LamFill 1. Both tools therefore solve with the same law, and the stacking factor is applied once.
- **B-H probe.** After one solve, FEMM's B and H at about 80 iron elements are compared with `h_of_b` (air elements skipped). Limit 0.1 %.
- **Circuits.** One series circuit per phase; each coil-side block carries turns `sign x turns_per_pole`; only phase A carries current.
- **Boundary.** A = 0 on the stator outer diameter.
- **Mesh.** Level L: gap element g/(3 x 2^L), iron 1.5 mm / 2^L, slot air 3 mm / 2^L (iron and slot air scaled by bore radius / 50.3 mm for machines other than the Krishnan 8/6), smartmesh off, minimum angle 30°, precision 1e-9. Torque from the air-gap element is positive counter-clockwise, as in srmcore. ψ is `mo_getcircuitproperties` (Wb-turns, both poles, stack included), the same quantity as `PointResult.psi`.
- **FEMM error estimate.** The fixture keeps the finest level F and level F - 1. The estimate per point is |X_F - X_(F-1)|. The generator fails if, at any point, the ψ change exceeds 0.5 % or the torque change exceeds 0.5 % of the peak torque at that current, or if F < 1.

| Machine | FEMM level | Nodes per point | Gap / iron / slot-air element (mm) | B-H probe max deviation | Worst FEMM error estimate: ψ / torque (% of peak) |
|---|---|---|---|---|---|
| Krishnan 8/6 | 2 | about 308k | 0.042 / 0.375 / 0.75 | 0.037 % (80 samples) | 0.187 % / 0.184 % |
| Synthetic 12/8 | 2 | about 367k | 0.025 / 0.375 / 0.75 | 0.007 % (79 samples) | 0.177 % / 0.211 % |
| Jiang 24/16 | 2 | about 338k | 0.042 / 0.686 / 1.37 | 0.028 % (79 samples) | 0.255 % / 0.199 % |

Jiang's level was set by a one-point timing run: probe plus one point (four solves) took 29.6 min on one worker at level 2, under the 30 min per point rule for the next level.

## 4. Points and tolerance rule

- **Angles.** Fractions (0, 4, 8, 15, 22, 28, 30) / 30 of the unaligned angle π/Nr, each snapped to the band pitch. The 2° fraction of an earlier trial was replaced by 4°: at 2° the rotor and stator pole corners coincide on the Krishnan 8/6 ((βr - βs)/2), and that point converges slowest in both tools.
- **Currents.** (0.4, 1.7, 3.9) x i_k with the knee current i_k = 1.5 T x g / (μ0 x N_pole), rounded to 2 significant figures: linear, rated, deep saturation.

| Machine | i_k | Currents (A) |
|---|---|---|
| Krishnan 8/6 | 7.75 A | 3.1, 13, 30 |
| Synthetic 12/8 | 12 A | 4.8, 20, 47 |
| Jiang 24/16 | 40 A | 16, 68, 160 |

- **ψ.** |ψ - ψ_FEMM| <= 2 % of |ψ_FEMM|.
- **Torque.** T_pk(i) is the largest |T_age| over the angles at that current. |T_arkkio - T_age| <= max(tol x |T_age|, 1 % of T_pk(i)). The tolerance tol is 3 % when the angle is between 1/6 and 5/6 of the unaligned angle and the current is at most 1.7 i_k, and 5 % otherwise (§8.3). The 1 % floor exists because the aligned and unaligned torque is numerical noise (1e-4 to 1e-3 N·m) in both tools, so a relative error there is meaningless.
- **FEMM self-consistency.** |T_age - T_wst| <= 1 % of T_pk(i) at every point (air-gap element against weighted stress tensor).

## 5. Results

Worst case per machine (columns of the tables below):

| Machine | ψ error | Torque error, relative (|T| >= 5 % of peak) | Torque error, % of peak | Largest error / limit |
|---|---|---|---|---|
| Krishnan 8/6 | 0.158 % | 0.34 % | 0.330 % | 0.11 |
| Synthetic 12/8 | 0.111 % | 0.60 % | 0.451 % | 0.20 |
| Jiang 24/16 | 0.137 % | 0.42 % | 0.334 % | 0.09 |

Limits are 2 % for ψ, 3 % / 5 % relative for torque, 1 % of peak for the floor. The tables are the output of `examples\femm_check.py`, stored in `docs/m5c-data/femm_check.txt`. Columns: dψ and dT are srmcore minus FEMM; "FEMM err" is the change from FEMM level F - 1 to F; "AGE-WST" is the difference between FEMM's two torque methods in % of peak; "n/a" means |T| is below 5 % of peak, so the relative error is not meaningful.

### Krishnan 8/6 (FEMM level 2, B-H probe 0.037 %)

| deg | i (A) | psi FEMM | dpsi % | FEMM err psi % | T FEMM (N m) | dT % | dT % of peak | tol % | FEMM err T % of peak | AGE-WST % of peak |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.00 | 3.1 | 0.31750 | -0.068% | 0.091% | +0.0001 | n/a | -0.008% | 5% | 0.011% | 0.009% |
| 0.00 | 13 | 0.86279 | -0.034% | 0.030% | +0.0007 | n/a | -0.003% | 5% | 0.005% | 0.004% |
| 0.00 | 30 | 0.98828 | -0.019% | 0.019% | +0.0009 | n/a | -0.001% | 5% | 0.003% | 0.001% |
| 3.98 | 3.1 | 0.29258 | -0.066% | 0.075% | -1.1266 | -0.28% | +0.243% | 5% | 0.013% | 0.007% |
| 3.98 | 13 | 0.84392 | -0.035% | 0.017% | -10.6801 | -0.21% | +0.107% | 5% | 0.014% | 0.013% |
| 3.98 | 30 | 0.97960 | -0.020% | 0.015% | -19.0064 | -0.14% | +0.040% | 5% | 0.049% | 0.009% |
| 7.96 | 3.1 | 0.23766 | -0.072% | 0.098% | -1.2486 | +0.34% | -0.330% | 3% | 0.010% | 0.029% |
| 7.96 | 13 | 0.76620 | -0.032% | 0.040% | -17.3491 | +0.05% | -0.040% | 3% | 0.025% | 0.023% |
| 7.96 | 30 | 0.92872 | -0.041% | 0.039% | -43.2876 | -0.06% | +0.037% | 5% | 0.057% | 0.011% |
| 15.00 | 3.1 | 0.13461 | -0.158% | 0.178% | -1.3012 | -0.14% | +0.142% | 3% | 0.002% | 0.009% |
| 15.00 | 13 | 0.46651 | -0.017% | 0.094% | -21.3934 | -0.15% | +0.153% | 3% | 0.027% | 0.024% |
| 15.00 | 30 | 0.71506 | -0.065% | 0.097% | -64.7446 | -0.16% | +0.163% | 5% | 0.052% | 0.014% |
| 22.04 | 3.1 | 0.04475 | -0.119% | 0.187% | -0.3512 | -0.07% | +0.018% | 3% | 0.184% | 0.036% |
| 22.04 | 13 | 0.18885 | -0.101% | 0.155% | -6.2481 | +0.06% | -0.017% | 3% | 0.146% | 0.035% |
| 22.04 | 30 | 0.43037 | -0.063% | 0.118% | -30.7596 | +0.19% | -0.088% | 5% | 0.132% | 0.021% |
| 27.86 | 3.1 | 0.03513 | -0.102% | 0.114% | -0.0429 | n/a | +0.008% | 5% | 0.007% | 0.007% |
| 27.86 | 13 | 0.14811 | -0.102% | 0.113% | -0.7637 | n/a | +0.009% | 5% | 0.008% | 0.007% |
| 27.86 | 30 | 0.34234 | -0.094% | 0.104% | -4.0754 | -0.15% | +0.010% | 5% | 0.010% | 0.013% |
| 30.00 | 3.1 | 0.03462 | -0.106% | 0.116% | -0.0000 | n/a | +0.002% | 5% | 0.005% | 0.003% |
| 30.00 | 13 | 0.14595 | -0.106% | 0.116% | -0.0004 | n/a | +0.002% | 5% | 0.006% | 0.003% |
| 30.00 | 30 | 0.33739 | -0.099% | 0.104% | -0.0022 | n/a | +0.004% | 5% | 0.008% | 0.005% |

### Jiang 24/16 (FEMM level 2, B-H probe 0.028 %)

| deg | i (A) | psi FEMM | dpsi % | FEMM err psi % | T FEMM (N m) | dT % | dT % of peak | tol % | FEMM err T % of peak | AGE-WST % of peak |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.00 | 16 | 0.08597 | -0.084% | 0.129% | -0.0012 | n/a | +0.018% | 5% | 0.199% | 0.007% |
| 0.00 | 68 | 0.25959 | -0.009% | 0.019% | +0.0062 | n/a | -0.011% | 5% | 0.041% | 0.033% |
| 0.00 | 160 | 0.30390 | -0.000% | 0.015% | +0.0011 | n/a | +0.000% | 5% | 0.009% | 0.010% |
| 1.56 | 16 | 0.07548 | -0.061% | 0.120% | -4.0780 | -0.37% | +0.334% | 5% | 0.018% | 0.002% |
| 1.56 | 68 | 0.24506 | +0.017% | 0.029% | -55.8415 | -0.34% | +0.256% | 5% | 0.091% | 0.013% |
| 1.56 | 160 | 0.29849 | +0.008% | 0.029% | -123.3580 | -0.42% | +0.227% | 5% | 0.163% | 0.013% |
| 2.97 | 16 | 0.06231 | -0.070% | 0.147% | -4.3803 | +0.15% | -0.148% | 3% | 0.025% | 0.005% |
| 2.97 | 68 | 0.21175 | +0.045% | 0.054% | -71.4170 | -0.10% | +0.097% | 3% | 0.002% | 0.020% |
| 2.97 | 160 | 0.28351 | +0.019% | 0.069% | -186.9534 | -0.20% | +0.166% | 5% | 0.090% | 0.028% |
| 5.62 | 16 | 0.03617 | -0.137% | 0.255% | -4.5414 | -0.26% | +0.258% | 3% | 0.011% | 0.005% |
| 5.62 | 68 | 0.13129 | +0.082% | 0.081% | -74.9864 | -0.28% | +0.278% | 3% | 0.003% | 0.036% |
| 5.62 | 160 | 0.22583 | +0.056% | 0.112% | -230.1759 | -0.19% | +0.186% | 5% | 0.020% | 0.029% |
| 8.28 | 16 | 0.01571 | +0.016% | 0.194% | -1.1382 | +0.18% | -0.046% | 3% | 0.114% | 0.003% |
| 8.28 | 68 | 0.06699 | +0.025% | 0.184% | -20.7006 | +0.23% | -0.064% | 3% | 0.108% | 0.002% |
| 8.28 | 160 | 0.15599 | +0.057% | 0.145% | -107.3970 | +0.29% | -0.135% | 5% | 0.063% | 0.005% |
| 10.47 | 16 | 0.01311 | -0.008% | 0.199% | -0.1756 | n/a | -0.014% | 5% | 0.015% | 0.004% |
| 10.47 | 68 | 0.05588 | -0.008% | 0.199% | -3.1926 | n/a | -0.015% | 5% | 0.017% | 0.004% |
| 10.47 | 160 | 0.13154 | +0.000% | 0.186% | -17.6679 | +0.34% | -0.026% | 5% | 0.026% | 0.006% |
| 11.25 | 16 | 0.01296 | -0.005% | 0.173% | +0.0000 | n/a | -0.000% | 5% | 0.001% | 0.002% |
| 11.25 | 68 | 0.05524 | -0.005% | 0.173% | +0.0001 | n/a | -0.000% | 5% | 0.001% | 0.002% |
| 11.25 | 160 | 0.13006 | +0.001% | 0.162% | -0.0004 | n/a | +0.000% | 5% | 0.000% | 0.003% |

### Synthetic 12/8 (FEMM level 2, B-H probe 0.007 %)

| deg | i (A) | psi FEMM | dpsi % | FEMM err psi % | T FEMM (N m) | dT % | dT % of peak | tol % | FEMM err T % of peak | AGE-WST % of peak |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.00 | 4.8 | 0.08026 | -0.048% | 0.060% | -0.0000 | n/a | -0.006% | 5% | 0.042% | 0.023% |
| 0.00 | 20 | 0.21244 | -0.028% | 0.010% | -0.0004 | n/a | +0.001% | 5% | 0.019% | 0.016% |
| 0.00 | 47 | 0.24665 | -0.032% | 0.018% | -0.0006 | n/a | +0.000% | 5% | 0.006% | 0.007% |
| 3.04 | 4.8 | 0.07031 | -0.048% | 0.062% | -0.5893 | -0.07% | +0.068% | 5% | 0.020% | 0.002% |
| 3.04 | 20 | 0.20580 | -0.024% | 0.017% | -6.0261 | -0.08% | +0.046% | 5% | 0.060% | 0.002% |
| 3.04 | 47 | 0.24224 | -0.032% | 0.028% | -12.1940 | -0.18% | +0.067% | 5% | 0.077% | 0.003% |
| 6.07 | 4.8 | 0.05666 | -0.061% | 0.089% | -0.6207 | -0.47% | +0.451% | 3% | 0.013% | 0.010% |
| 6.07 | 20 | 0.18399 | -0.018% | 0.050% | -9.2217 | -0.18% | +0.162% | 3% | 0.046% | 0.005% |
| 6.07 | 47 | 0.22367 | -0.036% | 0.051% | -24.2599 | -0.15% | +0.110% | 5% | 0.107% | 0.015% |
| 11.25 | 4.8 | 0.03249 | -0.111% | 0.151% | -0.6408 | -0.06% | +0.063% | 3% | 0.000% | 0.011% |
| 11.25 | 20 | 0.11068 | +0.013% | 0.067% | -10.3893 | -0.10% | +0.105% | 3% | 0.027% | 0.018% |
| 11.25 | 47 | 0.16570 | -0.027% | 0.119% | -33.1710 | -0.13% | +0.130% | 5% | 0.038% | 0.011% |
| 16.43 | 4.8 | 0.00981 | -0.066% | 0.177% | -0.2212 | -0.60% | +0.206% | 3% | 0.211% | 0.055% |
| 16.43 | 20 | 0.04108 | -0.035% | 0.139% | -3.8632 | -0.37% | +0.139% | 3% | 0.120% | 0.055% |
| 16.43 | 47 | 0.09456 | -0.012% | 0.116% | -18.5460 | +0.10% | -0.053% | 5% | 0.041% | 0.053% |
| 21.07 | 4.8 | 0.00727 | -0.090% | 0.137% | -0.0173 | n/a | +0.006% | 5% | 0.011% | 0.005% |
| 21.07 | 20 | 0.03044 | -0.089% | 0.137% | -0.3035 | n/a | +0.007% | 5% | 0.012% | 0.006% |
| 21.07 | 47 | 0.07165 | -0.085% | 0.131% | -1.6816 | -0.19% | +0.010% | 5% | 0.018% | 0.010% |
| 22.50 | 4.8 | 0.00719 | -0.091% | 0.137% | +0.0000 | n/a | -0.000% | 5% | 0.002% | 0.003% |
| 22.50 | 20 | 0.03007 | -0.091% | 0.137% | +0.0001 | n/a | -0.000% | 5% | 0.002% | 0.003% |
| 22.50 | 47 | 0.07077 | -0.087% | 0.132% | +0.0006 | n/a | -0.001% | 5% | 0.004% | 0.006% |

### Side note: the book's rated-current inductances

Krishnan and Irwin (Ch. 2, section 2.3.4) give the 8/6 inductances at the rated 13 A: FEA 65.41 / 11.35 mH (aligned / unaligned), analytic 66.79 / 11.38 mH. Their steel is M43. The FEMM fixture here uses M19, so the numbers are not a gate. From the fixture: La = ψ(0°, 13 A) / 13 A = 0.86279 / 13 = 66.4 mH and Lu = ψ(30°, 13 A) / 13 A = 0.14595 / 13 = 11.2 mH. Both are within 2 % of the book's FEA values.

## 6. Deviations explained

- **Size.** Every ψ difference is below 0.16 % and every torque difference below 0.6 % relative or 0.45 % of peak. FEMM's own level-to-level change is up to 0.26 %, so the differences are at FEMM's mesh-noise level and no systematic offset is visible.
- **Largest relative torque errors** fall on the lowest current at mid-stroke or late-stroke angles, where |T| is smallest: synthetic 12/8 at 6.07° and 4.8 A (-0.47 %) and 16.43° and 4.8 A (-0.60 %); Krishnan at 7.96° and 3.1 A (+0.34 %); Jiang at 1.56° and 160 A (-0.42 %, deep saturation). All are below 0.20 of their limit.
- **Largest errors in % of peak.** Synthetic 12/8 6.07° and 4.8 A (0.451 %), Jiang 1.56° and 16 A (0.334 %), Krishnan 7.96° and 3.1 A (0.330 %). Each is below the 1 % floor.
- **Aligned and unaligned angles** (0° and the last angle): torque is numerical noise (at most 0.0062 N·m) in both tools. These points are judged by the floor only, which is why the relative column reads "n/a".
- **Pole-corner coincidence.** On the Krishnan 8/6 the rotor and stator pole corners coincide at (βr - βs)/2 = 2°, the slowest-converging point in both tools. The comparison grid uses 4° (3.98° after snapping) instead.
- **FEMM torque methods.** The air-gap element and the weighted stress tensor agree within 0.06 % of peak at every point of every machine. On a coarse mesh the stress tensor shows spurious torque at symmetric positions; the air-gap element is exactly symmetric, so it is the primary torque.
- **B-H handoff.** FEMM's interpolation of the sampled curve is within 0.037 % of `h_of_b` (probe maxima in section 3), far below the 0.1 % limit.

## 7. How to regenerate

Windows with FEMM 4.2 and pyfemm only (pyfemm is a manual dev install, not a declared dependency). Each machine takes hours.

```powershell
$env:PYTHONPATH="tests"; python tools\femm_fixtures.py <machine> [--level F]   # krishnan_8_6, synth_12_8, jiang_24_16
$env:PYTHONPATH="tests"; python examples\femm_check.py [machine ...]           # comparison tables
```

The fixtures are `tests/validation/fixtures/femm_<machine>.json`. Each holds a provenance block (design JSON and SHA-256, B-H table SHA-256, assumed fields, versions, FEMM level and element sizes, date, git commit) and the points. The slow test recomputes `design_sha256` and `bh_sha256` from `tests/femm_machines.py` and fails with "fixture stale, regenerate with tools/femm_fixtures.py" if either differs, so a change to a machine, to the library curve or to the sampling invalidates the fixtures visibly.

FEMM is not run in CI: it is Windows-only and takes hours per machine. The fixtures are deterministic, so the committed results plus the staleness check give the same protection.
