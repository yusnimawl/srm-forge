# R4: end effects (3D fringing correction)

Status: approved by the owner 2026-11-04 (agreed in chat 2026-11-03). Roadmap item R4
(`2026-10-12-roadmap-r1-r10-design.md`). Runs on the LattePanda (16 threads, 30 GB, NGSolve 6.2), not in the cloud.
Branch `r4-end-effects` off main.

## 1. Goal

The 2D model is low on every measured machine, by more than its stated uncertainty:

| Measured case | 2D error | Stated model uncertainty |
|---|---|---|
| TEAM 24 static torque, 7.41 A | −13.1 % | none stated (M5b) |
| TEAM 24 rotor-pole flux | −17.2 % | none stated |
| Krishnan 6/4 T_avg, 10 A | −16.9 % | 3.3 % |
| Krishnan 6/4 T_avg, 20 A | −28.5 % | 6.3 % |

The sign is the same everywhere, which points to one systematic cause: flux outside the 2D plane at the two stack
ends (iron-end fringing). The analytic end-winding hook (`maps/end_winding.py`) covers only the end turns and adds no
torque. Short stacks fringe more and power-dense designs have short stacks, so the error can reorder the search. R4
must be done before R7 (recommender).

R4 builds an offline 3D reference model, checks it against the measurements, fits a geometry-dependent end-effect
correction to 3D runs, and applies that correction to the whole ψ(θ,i)/T(θ,i) map so every downstream user sees one
corrected motor.

**Done when** (roadmap): the measured comparisons fall inside the stated uncertainty, or the remaining gap is stated
in the budget.

## 2. Owner decisions (2026-11-03)

1. **Measurements are a check, never a calibration.** The correction's constants come from 3D runs only. TEAM 24 and
   Krishnan are compared after the fit, with no retuning. (This changes the roadmap's wording "calibrated against the
   3D runs and the measured TEAM 24 and Krishnan data"; update the roadmap R4 bullet to match.)
2. **The 3D model is trusted only after it matches TEAM 24.** Gate G1 (§4) comes first.
3. **If G1 fails, R4 stops there.** Record the finding (end effects are not the main cause), put the measured gap into
   the uncertainty budget as a stated row, and move on to R5. The hunt for the real cause (B-H data, measurement) is a
   new tracker item, not part of R4.
4. **The correction has a physical form** (§5), with a few constants that each mean something and can be checked in
   the 3D field, not a pure curve fit in L/D.
5. **The correction changes the whole map**, as a layer applied after the 2D map, the way `with_end_winding` does:
   drive, losses, SIL/HIL, search and key numbers all read the corrected map. The 2D map, its cache and its
   provenance hash are never changed.
6. **The correction covers the search space.** Its validity range must cover the search generator's design space
   (stack 0.25–1.2 × OD, gap 0.3–0.8 mm, the generator's pole sets), because R7 ranks all of it. A design outside the
   range still gets the correction, clamped at the range edge, flagged "Outside correction range", with the extra
   uncertainty of the clamp in its `end_effect` row; it ranks as corrected. Not correcting it would leave the full
   13–28 % bias, which is worse than a correction stretched past its range.
7. **A measured gap enters the budget conservatively.** If G5 leaves a gap, every design's `end_effect` row gets the
   larger of the TEAM 24 residual and the Krishnan residual, the Krishnan one after removing its 2D-Lu share (about 9
   points of the −28.5 % at 20 A), as a constant fraction on peak torque, La and ψ_max, per quantity. The note names
   which machine set it. Understating uncertainty is the failure the "EM-validated" to "2D-verified" rename was about.

## 3. Non-goals and anti-goals

Non-goals:
- 3D inside the search, the evaluator or the web tool. 3D is an offline calibration and check tool only.
- Eddy currents, transients, mutual coupling between phases, axial-flux machines.
- Changing the iron-loss B fields. End flux runs mostly in air; the iron B stays 2D (checked, not assumed: §4 G3).
- Fixing the Krishnan 2D Lu (coil placement and bore). It is a 2D-geometry issue, not an end effect; it stays a
  stated part of the Krishnan residual (about 9 points of the −28.5 % at 20 A, `docs/m5d-krishnan-results.md`).

Anti-goals (failure even if it "works"):
- Any constant fitted to, or tuned after looking at, the measured TEAM 24 or Krishnan data.
- Old evaluations silently mixed with corrected ones.
- The correction applied outside the geometry range it was fitted on without the user being told (flag and
  uncertainty, decision 6).
- Double counting the end turns: the analytic end-winding hook and the 3D-fitted term must not both carry the
  end-turn flux.

## 4. Evidence chain and gates

| Gate | Check | Pass rule | If it fails |
|---|---|---|---|
| G0 | 3D spike: TEAM 24 on the LattePanda, time and peak RAM per nonlinear solve | one solve fits in RAM; the sweep (§6) fits in about a week of machine time | shrink the sweep (fewer angles or currents, more symmetry), then re-plan; owner told |
| G1 | 3D TEAM 24 static torque and rotor-pole flux at 7.41 A vs measured (3.22 N·m, flux from M5b) | error within the 3D budget: 3D mesh convergence + material (same rows as `UncertaintyBudget`) + table rounding + input rows (3 mm fillets, hub radius and yoke thickness read from figure labels, search-coil position, coil section), each computed by a 3D perturbation run, never estimated | decision 3: stop, record, budget row |
| G2 | 3D discretisation check: a 3D slab with axial boundary conditions that make it 2D-equivalent (no stack ends), vs 2D, on the 8/6 and TEAM 24 | ψ within 0.5 %, torque within 1 % of peak (the M5e1 point-check limits) | the 3D model has a bug; fix before any fit |
| G3 | iron-B check: 3D mid-stack iron \|B\| vs 2D at the key points | p99.9 iron \|B\| within 2 % | iron loss needs an end-zone term: new tracker item, not R4 |
| G4 | correction vs held-out 3D runs (not used in the fit) | ψ and torque within the correction's stated fit residual | revise the form (§5), not the data |
| G5 | corrected 2D vs measured TEAM 24 and Krishnan, no retuning | inside the stated uncertainty, or the gap goes into the budget | gap stated in the budget (Done-when allows it) |

The 3D model includes the coil end turns. The builder defines and documents a method that separates the end-turn
flux linkage from the iron-end fringing in the 3D field (for example, end-region flux linking the end-turn overhang).
The 3D runs then **re-fit the end-winding image factor** (today a fixed 1.5 midpoint), and the correction L_fr is fitted
to 3D − (2D + re-fitted end winding). The image-factor 1-to-2 spread row in the budget is replaced by the residual of
that re-fit, so end-winding uncertainty is counted once (anti-goal on double counting). *(Builder's call, recorded
here; the review asked how end-winding error stays out of L_fr.)*

G2 checks the 3D discretisation only. The 3D slab has no stack ends, so it must equal 2D; a real long stack still
fringes (the Krishnan 6/4 is at L/g = 241 and shows the deficit), so length alone is not a 2D limit. *(Builder's call.)*

G1's input rows are allowed because a gate that fails stops R4 for good; each row must come from a 3D perturbation
run, so the budget cannot be widened by judgement. *(Builder's call.)*

## 5. Correction form

Starting form (to be confirmed or replaced by the 3D runs):

```latex
\psi_{c}(\theta, i) = \psi_{2D}(\theta, i) + L_{ew}\, i + L_{fr}(\theta)\, i, \qquad L_{fr}(\theta) = N^2 P_{end}(\theta)
```

- L_ew is the existing analytic end-winding inductance (unchanged).
- P_end(θ) is the end permeance of the air paths at the two stack ends: pole-face and gap fringing, which depend on
  gap, pole widths, overlap angle and stack-end geometry. Different at aligned and unaligned, so it adds torque:
  T_fr = ½ · dL_fr/dθ · i² (from the co-energy of the added term).
- A term linear in i is what unsaturated air paths give. It grows in relative size as the 2D iron flux saturates,
  which matches the Krishnan trend (La −15 % at 10 A, −22 % at 20 A); this is a guess the 3D runs confirm or reject.
- If the 3D runs show P_end changing with current (end iron saturating), add a second, saturation-dependent term.
  Any added term must have a stated physical meaning.
- Each constant is checked in the 3D field directly (flux leaving the stack ends), not only by the ψ fit.
- The correction has a **validity range** (the swept ranges of each geometry ratio and of the saturation level). The
  range is stored with the constants.

A linear-in-i term with L_fr ∝ N² stays exact under `turns.rescale_turns` and parallel paths, as L_ew does. A
saturation-dependent term may not; if one is needed, the builder states how the turns scan handles it.

## 6. 3D sweep

- Machines: TEAM 24 (G1, G2), the Krishnan 6/4 (as built for M5d), the 8/6 golden, and at least one short-stack
  10JNEX900 search candidate (the owner's lamination, the case that matters most).
- Stack length: at least 4 values per machine spanning the generator's range (0.25–1.2 × OD).
- Geometry: within each radial machine, vary the ratios the correction depends on (gap, stator and rotor pole widths,
  pole sets) so the validity range covers the generator's design space (decision 6). The builder picks the design of
  experiments; G0's timing sets how many points fit.
- Angles: enough between unaligned and aligned to get dL_fr/dθ (at least 7, including both ends); currents: linear,
  mid and saturated (at least 3).
- Some runs are held out for G4 and never enter the fit.

## 7. Where things go

- **3D tool (offline):** `tools/end3d/`, never imported by `src/`. It extrudes the existing 2D outline (same topology
  code, no new CAD path), meshes it, and solves nonlinear 3D magnetostatics with NGSolve. It is a calibration tool,
  not product code, so it is outside the srmcore import rules (the rules still hold inside `src/`).
- **Correction:** `srmcore/maps/end_effect.py` beside `end_winding.py`: the fitted constants, their validity range, a
  function giving L_fr(θ) for a machine, and a `with_end_effect(result, ...)` that adds ψ, energies, L_inc and torque
  after the map. The 2D map, cache and hash are unchanged.
- **Hook sites:** wherever `with_end_winding` is applied today (`srmapp/evaluate.py`, `srmapp/losses.py`), and
  everything that reads the evaluation map (drive, SIL/HIL tables, field ψ rescale).
- **One switch** turns the correction off; the pure 2D (plus end winding) result stays available for comparison.
- **Record on the evaluation:** whether the correction was applied and its version, and whether the design is inside
  the validity range. Old evaluations without the field show as "end effects not corrected".
- **Budget:** the `end_effect` row in `maps/validation.py` changes from "end winding, image factor 1 to 2; iron-end
  fringing not modelled" (peak torque 0 %) to the end-winding re-fit residual plus the correction's fit residual (G4),
  plus the clamp term for designs outside the range (decision 6), plus, if G5 leaves a gap, the measured residual
  (decision 7). Peak torque gets a non-zero entry.
- **Label:** "2D-verified" keeps its meaning (the 2D checks). The corrected map does not make it 3D-verified.
- **Version:** srmcore and srmapp get minor bumps. The new srmcore version is not in `VALIDATED_VERSIONS` until a
  validation campaign on the LattePanda passes; that campaign is a separate tracker item.
- **UI:** a status chip on result views ("End-corrected" / "End effects not corrected" / "Outside correction range"),
  and 2D vs corrected key numbers side by side in the case and run report.

## 8. Ranking bias

Run the same search (fixed requirements, fixed seed, 10JNEX900) with and without the correction. Report how the
Pareto set and the top-N order change against stack length (rank correlation and how many designs enter or leave the
top N). Results in `docs/r4-end-effect-results.md`.

## 9. Open questions for the owner

None. Coverage and the measured-gap rule were settled on 2026-11-03 (decisions 6 and 7).

## 10. Results and records

`docs/r4-end-effect-results.md`: G0 timings, G1–G5 tables, the fitted constants with their validity range and fit
residual, the end-turn share against the hook's image factor, the ranking-bias table. Spec §11 gets the decision
entry; the project doc and the wiki Progress tab are updated in the same session as each merge.
