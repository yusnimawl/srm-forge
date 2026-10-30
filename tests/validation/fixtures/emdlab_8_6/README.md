# EMDLAB / ANSYS Maxwell 8/6 SRM benchmark

Reference data for a cross-tool check of srmcore against the 8/6 SRM benchmark of the EMDLAB paper:
Jamali-Fard, Mirsalim, Sharifi, Majlesi, "EMDLAB: An open-source finite element package for
electromagnetic analysis of electrical machines", SoftwareX 32 (2025) 102446,
doi:10.1016/j.softx.2025.102446. Repo: https://github.com/EMDLAB-Package/emdlab-win64 (GPL-3.0).

Generated 2026-10-30 with MATLAB R2026b by `docs/emdlab-data/export_emdlab_8_6.m`. The slow test
`tests/validation/test_emdlab.py` reads them; results are in `docs/emdlab-results.md`. Background is in
`docs/emdlab-srm-reference.md`.

## Files

| file | source | content |
|---|---|---|
| `maxwell_8_6_torque.csv` | ANSYS Maxwell, shipped as `examples/switched-reluctance-machine/srm-te-maxwell.tab` | static torque, 30 angles, 3.6 A on phase A |
| `emdlab_8_6_sweep.csv` | EMDLAB, run here (the shipped static-torque example) | per angle: ψ, W, W′, torque by Arkkio, MST and co-energy derivative, node count |
| `mesh_convergence_m15deg.csv` | EMDLAB, run here (`bench_emdlab_srm86.m`) | ψ and Arkkio torque at θ = −15° on four mesh sizes |
| `m530_50a_bh.csv` | EMDLAB `materials/emdlab_mlib_es_M530_50A.m` | the B-H table EMDLAB uses (H A/m, B T), 199 points + origin |

Angles: `theta_tab_deg` is Maxwell's axis (0 = unaligned, 30 = aligned).
`rotor_deg_from_aligned = theta_tab_deg − 30` is the rotor angle with phase A aligned at 0, which
matches the srmcore convention (phase A aligned at θ = 0, positive counter-clockwise). Check the
sign of torque on the first comparison. Torque is positive on the unaligned → aligned stroke.

## Machine (paper Table 3 and the example script)

| quantity | value | srmcore field (SI) |
|---|---|---|
| poles | 8 / 6, 4 phases | `n_stator_poles=8`, `n_rotor_poles=6`, `n_phases=4` |
| stator OD / bore | 125 / 74 mm | `stator_outer_diameter=0.125` |
| air gap | 0.5 mm | `air_gap=0.0005`, `rotor_outer_diameter=0.073` |
| shaft | 20 mm | `shaft_diameter=0.020` |
| stack | 70 mm | `stack_length=0.070` |
| stator pole arc | 17.1° at the bore (tooth width 11.0 mm, parallel-sided) | `stator_pole_arc=radians(17.1)` |
| rotor pole arc | 19.8° at the rotor OD (tooth width 12.55 mm, parallel-sided) | `rotor_pole_arc=radians(19.8)` |
| stator / rotor yoke | 7.7 / 7.53 mm | `stator_yoke_thickness=0.0077`, `rotor_yoke_thickness=0.00753` |
| turns | 278 per coil, two coils per phase in series, 1 path | `turns_per_pole=278` |
| current | 3.6 A, phase A only | |
| steel | M530-50A, no stacking factor | not in the material library yet |

Phase A coils sit on the stator poles at 0° and 180° with opposite polarity: zones `sca11`(+),
`sca21`(−), `sca15`(−), `sca25`(+).

## Differences to settle before comparing (assumptions)

* **Pole sides**: EMDLAB's `emdlab_g2d_lib_srm1` draws parallel-sided teeth (constant width). Confirm
  that srmcore `*_pole_taper = 0` means parallel sides [inferred from `topology/radial.py`].
* **Coil**: EMDLAB's coil fills the whole half slot between the tooth side and the slot centre-line,
  with no liner or clearance. srmcore places the coil by `fill_factor`, `slot_liner_thickness` and
  `coil_inner_clearance`. At fixed ampere-turns this mainly moves where the current density sits,
  a small effect. Use the smallest values the validator accepts, and record them as assumed, as
  the FEMM fixtures do.
* **Shaft**: EMDLAB does not model a shaft. Its inner rotor boundary at r = 10 mm is a free
  boundary with A = 0, so no flux enters the shaft. srmcore meshes a shaft region. Use a
  non-magnetic shaft material, or accept a small difference.
* **Outer boundary**: both use A = 0 at the stator OD.
* **Material**: add `M530-50A` from `m530_50a_bh.csv` with stacking factor 1.0, or use it only in the
  test fixture. The table's original source is not stated in EMDLAB.
* **EMDLAB mesh**: about 8.1–9.0k nodes, 2 air-gap layers, and a random DistMesh, so the node count
  changes at each angle. Arkkio and MST agree to about 1% with each other.
* **Co-energy torque**: the first and last rows are one-sided differences. Ignore them.

## Agreement seen so far

* EMDLAB Arkkio vs Maxwell: mean |ΔT| 0.076 N·m (1.4 % of the 5.31 N·m Maxwell peak), worst
  0.20 N·m (3.8 %) at θ_tab = 10.3° on the rising edge.
* The paper's energy check at an "arbitrary position" (EMDLAB W 0.6457 J, W′ 0.7956 J; Maxwell
  0.6365 J, 0.7953 J) matches this sweep near θ_tab ≈ 15° (rotor −15°), the position of
  `emdlab_examples_srm86.m` [inferred].

## Suggested check (like `tests/validation/test_femm.py`)

Build the design above, solve phase A at 3.6 A on the 30 angles with the `full` preset, and compare
Arkkio torque against `maxwell_8_6_torque.csv` and ψ, W, W′ against `emdlab_8_6_sweep.csv`. Use
tolerances relative to the peak torque, around 3–5 % (two independent tools, and EMDLAB's mesh is
coarse), tighter at the plateau, and looser on the rising edge where the curves are steepest.
