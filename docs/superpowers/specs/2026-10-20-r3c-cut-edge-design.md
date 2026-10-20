# R3c: cut-edge build factor for iron loss

Status: design approved in chat 2026-10-20 and waiting for the owner's review of this written spec. Builds on R3
(`2026-10-18-r3-losses-design.md`, branch `r3-iron-loss`, PR #4). Branch `r3c-cut-edge` off `r3-iron-loss`.

## 1. Goal

R3 computes iron loss from catalogue (Epstein) loss data. Real laminations are cut (punched, laser, WEDM), and the
steel near a cut edge loses more. R3c adds this as an **edge band**: each iron element gets a loss multiplier from how
much of it lies near a cut edge, with the parameters per cutting process taken from the literature. Narrow poles and
thin yokes are hit hardest, the factor follows the geometry (DXF iron included), and an optimizer can see it.

Done when the edge-band model, the process input and the one-sided uncertainty row are in, the strip test passes, and
the Materu check and the 8/6 region factors are reported in `docs/r3-loss-results.md`.

## 2. Owner decisions (2026-10-20)

- **Loss only.** Cut-edge damage changes the iron-loss post-processing only. The B-H curve, the flux and torque maps,
  the map hash, the goldens and the 2D-verified chain are unchanged. The B-H data are right for the catalogue
  material; cut-edge permeability loss is a second-order effect on the maps of wide SRM parts (out of scope, §10).
- **Process undecided.** The default is `unspecified`: no change to the nominal loss, and the spread over all processes
  is shown as uncertainty. The user picks a process per case when it is known.
- **Materu is a check, not a calibration.** Nothing is fitted to Materu. Its comparison is reported before and after.
- **Approach A (edge band per element)**, over a width factor per region and a global factor per process.

## 3. Evidence (source: Huynh et al. 2026)

A. T. Huynh et al., "A comprehensive review of electrical steel cutting techniques for electric machine cores",
*Results in Engineering* 32 (2026) 112686, doi:10.1016/j.rineng.2026.112686 (CC BY). It is a review and gives no
edge-damage profile of its own; the profile models are in its refs [38] Steentjes et al. 2014, [56] Elfgen et al.
2017, [65] Gmyrek et al. 2013, [119] Dems et al. 2023, [126] Dems et al. 2022.

- Damaged-zone width (its Table 6): punching 0.5-2.5 mm, laser 0.2-1.5 mm, WEDM ≤ 0.2 mm, AWJ ≤ 0.1 mm; well-controlled
  processes < 1 mm. The microscopy zone of guillotine shearing is 0.17-0.20 mm (its Fig. 14).
- Loss against strip width, relative to a 30 mm strip, 50 Hz:
  - 35WW270 0.35 mm, laser, 1 T: +5.33 % (15 mm), +10.34 % (10 mm), +24.51 % (6 mm).
  - Mechanical, 1 T, 15 mm: NO20 0.2 mm +4.49 %, M400-50A 0.5 mm +10.54 %.
  - M270-50A 0.5 mm, mechanical, 7.5 mm: +20 % at 1.5 T, +50-70 % at 0.1 T.
  - 35WW300 0.35 mm, laser, against an uncut sample, 1.5 T: +22 % (15 mm), +53 % (10 mm).
- The width effect is largest at low B and low frequency (hysteresis-dominated).
- In these data thin gauges are *less* sensitive (NO20 against M400-50A), although the review's text says the
  opposite. There are no cut-edge data for 10JNEX900 or any 0.10 mm grade.
- Machine level: iron-loss ratio about 1.2-1.3 punched and 1.8-2 laser in the PMa-SynRel case studies (narrow
  features, 3-10 mm strip data); WEDM modest.

**The 1/w law.** Loss per unit mass of a strip of width w cut on both edges is well described by
P(w) = P_bulk (1 + a/w). Fitted to the 35WW270 laser data, a = 1.69, 1.64 and 1.96 mm from the 15, 10 and 6 mm
strips (consistent). Mechanical: a = 1.4 mm (NO20 0.2 mm), 3.5 mm (M400-50A 0.5 mm), 2.1 mm (M270-50A at 1.5 T).
A step band of width δ and loss ratio K gives exactly this law with a = 2δ(K - 1).

**Expected size on Materu.** The Materu 6/4 parts are wide (stator pole about 21 mm, rotor pole about 31 mm, stator
yoke 10.5 mm, rotor yoke about 9.3 mm). With a = 2-3.5 mm and the Epstein baseline removed (§4), the factor is about
+3-5 % on the stator poles, +12-19 % on the stator yoke and about 0 on the rotor poles: some +5-15 % in total against
a gap of -18 to -78 % (`docs/r3-loss-results.md`). Cut edges are not the main cause of the Materu gap; the M19 stand-in
for E140 and the subtracted measurement remain the main suspects. The model is added for designs with narrow
features, not to close Materu.

## 4. Model

`srmcore/post/cut_edge.py`, numpy and scipy only, no solver or gmsh imports.

- **Cut edges.** Per mesh part (stator, rotor): the edges of iron triangles that are not shared with another iron
  triangle of the same part. These are the iron boundaries against slot air, the air gap, the outside, the shaft and
  imported hole air; every one of them is a cut edge of the lamination.
- **Band fraction.** For each iron element, the fraction of its area within δ of a cut edge, from 6 fixed interior
  sample points per triangle (a symmetric rule) and the distance to the nearest cut-edge segment. The distance
  uses a KD-tree on points along the cut edges spaced at most δ/8, refined to the exact segment distance on the
  nearest candidates. It is computed once per static mesh and process; it does not depend on angle or current.
- **Multiplier.** For element e:

      m_e = (1 + (K - 1) frac_e) / B0,   K - 1 = a / (2 δ),   B0 = 1 + a_epstein / 0.030 m

  applied to the **hysteresis and excess** loss of the element. Classical eddy loss is a bulk property (σ, thickness)
  and is not changed. The width data are total loss at 50 Hz, where hysteresis dominates; at 0.10 mm the classical
  share is small, so the error of applying a fitted on total loss to hysteresis + excess is small and inside the
  range row.
- **Baseline.** Catalogue data come from 30 mm Epstein strips that already have two cut edges. JFE states its
  10JNEX900 data are as-sheared (`docs/r3-sources.md`), so B0 uses `EPSTEIN_A = 1.4 mm` (the punching nominal). The
  M19 data's preparation is not stated; the same B0 is used and the range row (§6) covers it.
- **Insensitive to δ.** For parts wider than 2δ the total depends only on a; δ only sets where the extra loss sits.
  δ is the least known number in the table, which is why the model is built on a.
- For `unspecified`, m_e = 1 exactly: the nominal result is bit for bit the R3 result.

## 5. Process table

`CUT_PROCESSES` in `srmcore/post/cut_edge.py`. Every value carries its source in a comment.

| Process | a nominal | a range (low, high) | δ | Source |
|---|---|---|---|---|
| `unspecified` (default) | none, m = 1 | WEDM low, laser high | none | owner decision |
| `wedm` | 0.3 mm | 0, 0.7 mm | 0.2 mm | Table 6 (δ); "modest" loss rise, its §7.1; a is a grade C estimate |
| `punching` (punching or shearing) | 1.4 mm | 1.4, 3.5 mm | 0.5 mm | NO20 0.2 mm (nominal, thinnest gauge with data), M400-50A 0.5 mm (high); Table 6 (δ) |
| `laser` | 1.8 mm | 1.6, 5.3 mm | 0.5 mm | 35WW270 width fit (nominal, low), 35WW300 10 mm (high); Table 6 (δ) |

All rows are grade C for 10JNEX900 (no thin-gauge data); the note on every losses result says so. Stacking, joining
(welding, interlocking) and press fits (+10-50 % in its Table 1) are not modelled and are listed as unquantified.

## 6. Inputs, outputs and uncertainty

- **Input.** `Requirements.cut_process: Literal["unspecified", "wedm", "punching", "laser"] = "unspecified"`. Saved in
  setup files (optional field with a default, so older files load). Set in the web Requirements tab as a select.
- **Where it applies.** `srmapp.losses._side_loss` multiplies the hysteresis and excess W/kg of each element by m_e
  before the mass sum. The band fractions come from the static mesh that `stroke_losses` already has, in the same
  iron-element order as the stroke fields. Re-running losses with another process hits the stroke cache.
- **Range.** The loss is linear in a: iron W = S_cl + S_he/B0 + (a / (2δ B0)) S_frac, with S_he the hysteresis +
  excess loss and S_frac the same weighted by frac_e. The low and high a of the process's range therefore cost no
  extra solve. `unspecified` uses the WEDM low and the laser high (with the laser δ for the high and the WEDM δ for
  the low).
- **Output.** `OperatingLoss.cut_edge_rel: tuple[float, float]`: the relative change of the iron loss at the low and
  the high end of the range against the nominal (for example (-0.03, +0.21)). It is one-sided for `unspecified` and is
  kept apart from the symmetric `iron_uncertainty_rel`. `LossResult.cut_process` records the process. The web shows the
  row next to the iron uncertainty ("cut edge -3 / +21 %"), and the region table shows the mean multiplier per region.
- `srmweb` result models get the new fields as optional, so losses stored before R3c still load.

## 7. Checks and reporting

- **Materu (check only).** `examples/materu_losses_check.py --cut-process <p>` recomputes the iron loss from the cached
  strokes for each process, with no new solves when the cache is present (otherwise the full run, about 3 h, which needs
  the owner's go-ahead on the shared laptop). `docs/r3-loss-results.md` gets one table: per row the R3 error, then the
  error for `punching`, `laser` and `wedm`, with the range. Nothing is fitted.
- **8/6 region factors.** For the repo 8/6 on 10JNEX900, the mean multiplier per region (stator pole, stator yoke,
  rotor pole, rotor yoke) per process, and the band fraction per region, in the same results doc.

## 8. Tests

- Strip: a rectangular iron strip meshed at screening density, w = 5, 10 and 30 mm, uniform B. The mean multiplier
  times B0 equals 1 + a/w within 1 % for each process.
- `unspecified` and a = 0 give results identical to R3, bit for bit (hysteresis, excess and classical per region).
- Linearity: the low and high ends of `cut_edge_rel` equal a direct recompute with that a.
- Band fraction is 1 for an element inside the band, 0 far from every edge, and in (0, 1) for an element across
  the band edge.
- Cut edges on the 8/6 screening mesh: the cut-edge length per part matches the outline perimeter within 1 %.
- DXF iron (`ImportedIron`) gives finite factors, with the hole edges counted as cut edges.
- Layering: `srmcore/post/cut_edge.py` imports no gmsh, ngsolve, netgen or skfem (`tests/test_import_rules.py`).

## 9. Version

The PR does not bump versions. Planned merge order: #4 (R3), #5 (R3b), #6 (R8a), then R3c. At merge time srmcore and
srmapp go to 0.7.0, and srmweb and `web/` to the next free number after #6 (0.9.0); the PR body says so. The nominal
result is unchanged unless a process is chosen. `VALIDATED_VERSIONS` is unchanged; a new version joins it only through
the validation report, as before.

## 10. Out of scope

- Cut-edge B-H (permeability) degradation and its effect on flux and torque maps.
- Dependence of the degradation on B and frequency (the data show more at low B and low f); one a per process.
- Stacking, joining (welding, interlocking), press-fit and shrink-fit factors.
- Stress-relief annealing.
- A calibrated factor fitted to any measured machine.
- A thickness dependence of a (no thin-gauge data).
