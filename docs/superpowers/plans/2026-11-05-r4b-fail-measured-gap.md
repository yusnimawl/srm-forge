# R4b-fail: Measured Gap in the Budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close R4 after the G1 failure: put the measured gap into every design's `end_effect` budget row, re-run the 8/6 validation so the report shows it, and record the outcome.

**Architecture:** One change in `srmcore/maps/validation.py`: a constant `MEASURED_GAP` is added to the `end_effect` row of `UncertaintyBudget`. The map, its cache, the checks and the label do not change. The correction layer, the sweep, G3, G4, G5 and the ranking bias are not built.

**Tech Stack:** Python 3.12, srmcore, pytest; `examples/em_validate_8_6.py` and `tools/validation_report.py` on the LattePanda.

**Spec:** `docs/superpowers/specs/2026-11-03-r4-end-effects-design.md`, decisions 3 and 7. Results: `docs/r4-end-effect-results.md`, section G1.

**Starts after:** the R4a PR is merged. Work on a new branch from main, `r4b-fail-gap`.

## Fixed values

Decision 7 takes the larger of the TEAM 24 and Krishnan residuals, as a constant fraction per quantity, with the Krishnan torque residual taken after removing its 2D-Lu share. No correction exists, so the residuals are those of the 2D map plus the end-winding term, which is what the budget's `values` hold. They come from data committed before G1 ran. The 3D errors (11.72 %, 8.30 %) are not used, because no design's map is a 3D result.

| Budget key | TEAM 24 | Krishnan 6/4 at 20 A | `MEASURED_GAP` | Set by |
|---|---|---|---|---|
| `peak_torque` | 13.05 % (`static_torque`) | 28.53 − 9.3 = 19.2 % (`T_avg`) | 0.192 | Krishnan 6/4 |
| `la` | 17.23 % (`rotor_flux`) | 15.04 % (`La`, `error_after_pct`) | 0.172 | TEAM 24 |
| `psi_max` | 17.23 % (`rotor_flux`) | 15.04 % (`La`, `error_after_pct`) | 0.172 | TEAM 24 |
| `lu` | not measured | not in decision 7 | 0.0 | none |

- The 9.3 points are `docs/m5d-krishnan-results.md`: 3.9 N·m of 41.6 N·m at 20 A.
- Krishnan's `T_avg` is computed from measured flux linkage, not from a torque sensor. The results section says so.
- `la` is the secant at 5 % of I_max, where the Krishnan error is only 2.0 %. The row is conservative there on purpose: decision 7 asks for a constant fraction and names understating as the failure.

## Global Constraints

- No version bump. srmcore stays 0.7.0 and stays in `VALIDATED_VERSIONS`: the map, solver, checks and label are unchanged, so nothing the validation campaign tested has changed. A bump would drop the 2D-verified label and invalidate every cached map for a budget note.
- The new values are not used as a constraint anywhere. No search, margin or ranking reads the budget (`srmapp` hard limits stay as they are).
- Measurements are a check, never a calibration (decision 1): the map values are not scaled by the gap.
- The row's note names which machine set each value (decision 7).
- Comments describe the code as it is, not task history.
- Fast suite: `python -m pytest -m "not slow"`.

## Review Focus

1. **A constant drifts from its source.** `MEASURED_GAP` must trace to `docs/validation/team24.json` and `krishnan_6_4.json`. Test in Task 1.
2. **The sum double-counts or drops the image-factor term.** The row is the image-factor half-width plus the gap, not one of them. Test in Task 1.
3. **`lu` changes by accident.** Its row must stay the image-factor term only. Test in Task 1.
4. **Evaluations stored before this change keep the old row** in the web store and show peak torque 0 %. Re-validating updates them; the note text tells the two apart. No migration. Stated in the results in Task 3.
5. **A check or report assumes the row is small.** `srmapp/report.py` names the largest row, which becomes `end_effect` for three keys; that is correct. `tools/validation_report.py` must still give PASS. Checked in Task 2.

---

### Task 1: The measured gap in the `end_effect` row

**Files:**
- Modify: `src/srmcore/maps/validation.py` (constants near the top; `end_row` in `em_validate`)
- Modify: `tests/maps/test_em_validation.py:194-195` and add two tests
- Modify: `CLAUDE.md` (Map products item 9: the `end_effect` row)

**Interfaces:**
- Produces: `MEASURED_GAP: dict[str, float]` = `{"la": 0.172, "lu": 0.0, "peak_torque": 0.192, "psi_max": 0.172}`, keyed as `KEYS`.

- [ ] **Step 1: Write the failing tests**

Change the assertion at `tests/maps/test_em_validation.py:195` to:

```python
assert end.rel["peak_torque"] == pytest.approx(V.MEASURED_GAP["peak_torque"])
assert end.rel["la"] == pytest.approx((l2 - l1) / 2 / b.values["la"] + V.MEASURED_GAP["la"])
assert end.rel["lu"] == pytest.approx((l2 - l1) / 2 / b.values["lu"])
assert "Krishnan" in end.note and "TEAM 24" in end.note
```

Add `test_measured_gap_is_the_larger_residual`: read `docs/validation/team24.json` and `krishnan_6_4.json`; with `t = abs(static_torque.error_pct)`, `f = abs(rotor_flux.error_pct)`, `k_la = abs(error_after_pct)` of the La row at 20 A and `k_t = abs(error_after_pct)` of the T_avg row at 20 A:

```python
assert V.MEASURED_GAP["peak_torque"] == pytest.approx(max(t, k_t - 9.3) / 100, abs=5e-4)
assert V.MEASURED_GAP["la"] == V.MEASURED_GAP["psi_max"] == pytest.approx(max(f, k_la) / 100, abs=5e-4)
assert V.MEASURED_GAP["lu"] == 0.0
assert set(V.MEASURED_GAP) == set(V.KEYS)
```

- [ ] **Step 2: Run** `python -m pytest tests/maps/test_em_validation.py -v`. Expected: FAIL, `MEASURED_GAP` not defined.

- [ ] **Step 3: Implement.** Add `MEASURED_GAP` with a one-line comment giving its rule (larger of the TEAM 24 and Krishnan 6/4 residuals of the 2D map, Krishnan torque less its 2D-Lu share). In `em_validate` add it to each key of `end_row`. Note text: `"end winding, image factor 1 to 2; measured gap, not a modelled effect: peak torque 19.2 % (Krishnan 6/4), La and ψ_max 17.2 % (TEAM 24)"`.

- [ ] **Step 4: Run** `python -m pytest tests/maps/test_em_validation.py tests/test_examples_json.py tests/web/test_web_results.py tests/web/test_web_cases.py -q`. Expected: PASS.

- [ ] **Step 5: Update `CLAUDE.md`** item 9 so the rows read: end effect = image factors 1 and 2 plus `MEASURED_GAP`.

- [ ] **Step 6: Commit** `git commit -m "maps: measured gap in the end_effect budget row"`.

### Task 2: Re-run the 8/6 validation

**Files:**
- Modify: `docs/validation/em_validate_8_6.json`, `docs/validation/budget.png`, `docs/validation-report.md`

- [ ] **Step 1: Run** on the LattePanda (about 1 h, in the background): `python examples/em_validate_8_6.py --json docs/validation/em_validate_8_6.json`. Do not change the preset or the design.

- [ ] **Step 2: Run** `python tools/validation_report.py`. Expected: verdict PASS.

- [ ] **Step 3: Check** the report's `end_effect` row against the old one (0.13, 1.16, 0.00, 0.27): la 17.33, lu 1.16, peak_torque 19.20, psi_max 17.47. Every other row must be the same as before to the printed digits, and the checks and label unchanged. Any other difference: stop and report it.

- [ ] **Step 4: Commit** `git commit -m "validation: 8/6 budget with the measured gap"`.

### Task 3: Records and merge

**Files:**
- Modify: `docs/r4-end-effect-results.md` (new section "Measured gap in the budget" after G1; mark G3, G4, G5, Fitted constants and Ranking bias "Not done: G1 failed")
- Modify: `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md` (§11 entry)
- Modify: `docs/superpowers/specs/2026-10-12-roadmap-r1-r10-design.md` (R4 bullets: mark what was built and what was dropped; the "Done when" holds through its second branch)

- [ ] **Step 1: Write the results section:** the Fixed values table above, the new 8/6 totals, the two caveats (`T_avg` source, conservative `la`), and Review Focus 4.

- [ ] **Step 2: Add the §11 entry** with the values and the no-bump reason. Update the roadmap bullets.

- [ ] **Step 3: Commit, push, open the PR,** wait for CI green, merge.

- [ ] **Step 4: Update the wiki and project doc** in the same session: Validation tab (the budget row), Progress tab (R4 and row 1c Done once merged and checked; rows 1a and 1b closed as not needed, with the reason; R5 build unblocked; the roadmap drawing and its count), project doc (R4 section and a milestone table row for each merge).

## After this plan

R5 starts. Tracker rows 1d (cause of the TEAM 24 gap) and 1e (end-winding term against 3D) stay open and are not part of R4.
