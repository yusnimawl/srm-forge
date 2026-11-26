# Continuous conduction in the drive model (Bike motor v1, part 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Implementers: Sonnet. Reviewers (spec and code, after each task and at the end): Opus.

**Goal:** The drive envelope accepts strokes whose phase flux does not die away before the next turn-on. Such a
stroke is solved as the periodic steady state of the stroke. High-speed power above the single-pulse limit is then
no longer under-predicted. The check is Kiyota 2014 Table III (b) (113 N·m at 8700 r/min) and the Fig. 16 points at
59 and 99 kW (13 900 r/min), which have no stroke today.

**Done when:** continuous-conduction strokes are in `srmapp.drive.envelope`, the Kiyota (b), 59 kW and 99 kW points
have strokes and are recorded, every single-pulse result is unchanged (proof below), merged to main with CI green.

**Architecture:** all changes are in `src/srmapp/drive/envelope.py`. The stepping loop of `_simulate` moves into a
new `_run`, which takes a start flux per stroke and also returns the end flux and a current-limit flag. `_simulate`
stays the single pulse from zero flux, with the same outputs. A new `_strokes` runs `_simulate` once, then solves the
periodic steady state of every stroke that `_simulate` rejects. `envelope`, `min_copper_stroke` and `fixed_stroke`
call `_strokes`. srmcore does not change.

**Sources:** finding 2 of the Kiyota section in `docs/r3-loss-results.md` (2026-11-18), roadmap spec §0 item 2.2
(`docs/superpowers/specs/2026-10-12-roadmap-r1-r10-design.md`), and the core spec §11 rows of 2026-11-26 (bike target: 300 V,
170 A peak, up to 20 000 r/min, full power from 50 to 150 km/h).

## Global constraints

- srmcore unchanged: no edit under `src/srmcore/`, `ENGINE_REVISION` unchanged, `python tools/engine_digest.py`
  passes. No map, overlap, stroke or field cache key changes (the stroke cache key already hashes the coil currents).
- Worktree `/home/server/srm-forge-cc`, branch `drive-continuous-conduction`. Run Python as
  `PYTHONPATH=src:tests /home/server/srm-forge/.venv/bin/python` (the shared venv imports the main checkout otherwise).
- Long runs (over about 10 min) go through `systemd-run --user --unit=NAME --collect -p WorkingDirectory=... ...`,
  one heavy job at a time on the LattePanda (check `systemctl --user list-units --state=active` first).
- `tests/app/envelope_reference.py` is a frozen copy: do not edit it.
- Comments explain the code as it is. No plan history in comments.
- Prose in docs follows `docs/writing-plan.md`.

## Diagnosis (2026-11-26, prototype in /tmp, not committed)

### How a stroke is built today

1. `_tables` samples phase A over one rotor pole pitch: 181 angles (180 steps, aligned at 0 and at the pitch,
   unaligned at half) and 121 currents from 0 to the current limit.
2. `_stroke_pairs` gives 7935 (turn-on, turn-off) pairs. Turn-on has 80 points in 0.25 to 0.80 of the pitch. Turn-off
   has 80 points in 0.45 to 0.995, continued at the same spacing to 1.25 (116 points), so the flux tail runs past
   aligned.
3. `_simulate` runs each pair from zero flux for exactly one period: +V up to turn-off with the hysteresis clip at the
   limit flux ψ(θ, I_lim), then −V, the flux floored at 0. A stroke is valid when its end flux is at most 1 % of its
   peak.

### Why continuous conduction is impossible today

Every stroke starts at zero flux, and the 1 % end test rejects any stroke whose flux is still up at the next turn-on.
When the dwell is more than about half the period, the −V interval is too short to bring the flux to zero. At Kiyota
(b) `_simulate` rejects 2553 of the 7935 pairs. Those are the strokes the drive needs above the single-pulse limit.

### The periodic steady state

Let F(p) be the end flux after one period that starts at turn-on with flux p, and G(p) = F(p) − p.

1. F is non-decreasing: the flux equation is monotone in its start value, and the clip and the zero floor are
   monotone. Its slope is in [0, 1]: the resistance makes the sensitivity decay, and the clip and the floor set it
   to 0. So G is non-increasing, and strictly decreasing for R > 0.
2. For a rejected stroke G(0) = F(0) > 0.
3. The current at turn-on must not pass the limit, so p ≤ cap = ψ(θ_on, I_lim). If G(cap) > 0, no admissible periodic
   state exists and the stroke stays invalid. Otherwise one root lies in [0, cap].
4. The drive started from rest converges to the smallest root (p ← F(p) from 0 rises monotonically). With R > 0 the
   root is unique, so the solve gives the state the drive reaches.

### The current limit

With flux left at turn-on, the current near unaligned is about ψ/L_u and can pass the limit while −V is applied.
Today the table stops at I_lim and `np.interp` clips the current there without a flag. Rule for periodic strokes: at
every step ψ − (V + R·i)/ω·Δθ ≤ ψ_lim(θ_k+1), that is, even full negative voltage holds the current at the limit.
A stroke that breaks the rule is invalid. The rule also keeps ψ inside the table, so inside the map range.

### Prototype results

Kiyota 18/12, `full` map at the 16.3 mm stator yoke from `/home/server/srm-forge/cache-kiyota`, end winding at image
factor 1.5, 650 V, 97.8 mΩ at 20 °C taken to 75 °C, current limits k/8 x 300 A as in `min_copper_stroke`.

| Point | r/min | Torque needed N·m | Single-pulse best N·m | Best with periodic strokes N·m | Least-copper stroke at the torque, RMS A | Measured RMS A |
|---|---|---|---|---|---|---|
| III (b) | 8700 | 113 | 55.6 | 145.9 | 136.7, continuous | 130 |
| Fig. 16, 59 kW | 13 900 | 40.6 | 20.7 | 94.8 | 61.6, continuous | not given |
| Fig. 16, 99 kW | 13 900 | 68.3 | 20.7 | 94.8 | 111.7, continuous | not given |
| III (a) | 2768 | 209 | | | 128.2, single pulse, unchanged | 137 |
| III (c) | 7500 | 36 | | | 34.2, single pulse, unchanged | 35.4 |

1. At (b) the least-copper stroke needs 5 % more RMS current than measured, inside the 10 to 15 % accuracy target.
   The 2D model gives more torque per ampere than the 3D machine (R4), so the gap is on the expected side.
2. Fig. 16 points 14.7 to 30.0 kW keep their single-pulse stroke with the same RMS current as the 2026-11-18 table
   (18.4, 21.0, 24.9, 25.4, 33.3 A). At the 15.5 mm yoke the 30.0 kW point, which had no stroke, gets a continuous one
   (38.3 A).
3. Drive grid 361/160/160 against 181/80/80: the best torque does not move (145.92 N·m at (b), 94.77 against 94.78 at
   13 900 r/min). The least-copper RMS moves 1.0 % at (b), 0.0 % at 59 kW and 3.5 % at 99 kW.
4. Root solver: Illinois regula falsi on [0, cap] at a tolerance of 1e-6 of the largest limit flux needs at most
   22 iterations, with no stroke left unconverged. A tolerance of 1e-4 moves the least-copper RMS by 0.2 %, 1e-3 by
   2.4 %, so the plan keeps 1e-6. Newton with the exact sensitivity of the discrete stroke needs 6 to 9 iterations
   and is 1.5x faster at the Kiyota high-speed points, but no faster on the 8/6 scan sample (3.2x against 2.7x over
   single pulse). The plan uses Illinois: it needs no derivative code.
5. Equality: a start flux of 0 gives `_simulate`'s numbers bit for bit (1000, 8700 and 13 900 r/min). Every pair that
   `_simulate` accepts keeps its numbers bit for bit.
6. Single-pulse strokes chosen by the envelope with a tail current over the limit: 0 of 300 speeds on the 8/6 sample
   below, 0 at the Kiyota points. So the current-limit rule applies to periodic strokes only (decision D3).

### Run time

Per speed, the periodic solve costs 1.6x (1000 r/min) to 9x (13 900 r/min) the single-pulse pass. Most of it is the
per-step Python overhead of each Illinois pass. On 25 of the 750 distinct drives of the 8/6 screening density "auto"
scan of `docs/winding-scan-profile.md` (3000 to 6000 r/min band, one process): 10.2 s before, 27.6 s after (2.7x).
6 of the 25 envelopes change, at 30 of 300 speeds, none lower, the largest power gain 1.34x. Expected scan time:
57 s to about 155 s at 8 workers, 239 s to about 650 s at 1 worker.

Fast tests with the prototype patched into `_simulate` itself: the drive test files pass except
`test_tail_must_end_before_next_on`, which tests `_simulate`'s single-pulse rule. That rule stays in this plan, so the
test stays as it is. 262 more tests in `tests/app` pass. `tests/app/test_app_turns.py` takes 428 s today and did not
finish in 560 s with the prototype (18 passed, none failed). `test_app_evaluate.py` with `test_app_rated_choice.py`
did not finish in 570 s. So the fast suite gets slower (risk R1), and Task 2 runs the whole of it.

### Mutual coupling (noted, not built)

In continuous conduction every phase carries current at every angle: all 3 phases of the 18/12, and on an 8/6 the
phases overlap far more than in single pulse. The maps hold one excited phase, and the envelope adds the phase
torques with no coupling. Krishnan (Ch 6) says to model the mutual flux once phase currents overlap more than 30 to
40 % of the period. The mutual flux then reaches about 10 % of the phase flux. So continuous strokes carry a coupling
error that is not measured, larger than for single pulse. The loss path solves all phases together
(`srmcore.maps.stroke.stroke_fields`), so the iron loss sees the coupled field. The drive torque and flux do not.
Bike motor v1 part 4 measures the coupling on the winner with the overlap map. This plan only writes the note.

## Design decisions

- **D1.** The periodic solve runs only on the pairs `_simulate` rejects. Every pair `_simulate` accepts keeps its
  numbers. So at each speed the chosen stroke is either the old single-pulse stroke with the old numbers, or a
  periodic stroke with more work (envelope) or less copper (least-copper search).
- **D2.** Illinois regula falsi on [0, cap] per stroke, vectorised over the strokes. `PERIODIC_TOL` = 1e-6 of the
  largest limit flux of the table, `PERIODIC_MAX_ITER` = 60. Converged when |G| ≤ tol or the bracket is narrower than
  tol. A stroke still unconverged after the cap is invalid (the fixture tests assert there is none).
- **D3.** The current-limit rule (above) applies to periodic strokes only. Applying it to single-pulse strokes too is
  more consistent, but it would end the by-construction proof of D1. It changed no chosen stroke in the probes. It is
  an open item.
- **D4.** No switch to turn continuous conduction off. The 2026-11-18 Kiyota JSONs keep the single-pulse numbers, and
  the tests reach the single pulse through `_simulate`.
- **D5.** No new `Envelope` field (the scan does not need one, and `srmweb` ignores extra fields anyway).
  `StrokeTrace` gets `psi_on: float = 0.0`, the flux at turn-on in Wb-turns (0 for a single pulse), for the Kiyota
  table and the tests.

## Proof that single-pulse results are unchanged

1. P1 (tests unchanged): `_simulate` equals the frozen `envelope_reference._simulate` bit for bit
   (`tests/app/test_app_scan_equality.py`, three simulation tests).
2. P2 (new): `_run` with a zero start flux equals `_simulate` bit for bit, with and without the trace.
3. P3 (new): on every pair that `_simulate` accepts, `_strokes` returns `_simulate`'s numbers bit for bit, with start
   flux 0.
4. P4 (scan): `test_scan_matches_the_reference_winding_by_winding` keeps its monkeypatch of `drive._simulate`.
   `_strokes` calls `_simulate` through the module global, so the patch reaches the single-pulse pass. The periodic
   layer is the same code on both sides. The test then proves that the scan, with continuous conduction on, matches
   the unoptimised single-pulse code plus the same periodic layer.
5. P5 (envelope, new): with `_strokes` monkeypatched to return the single-pulse pass only, `envelope` gives the old
   numbers. With the real `_strokes`, every speed whose chosen stroke has start flux 0 equals them bit for bit, and
   every other speed has more torque.
6. P6 (LattePanda): the Kiyota rows that stay single pulse equal the 2026-11-18 JSONs exactly, and on the 8/6
   screening case every speed whose chosen stroke is single pulse has the old torque and RMS current exactly.

## Files

- Modify: `src/srmapp/drive/envelope.py` (`_run`, `_simulate`, `_strokes`, constants, `envelope`,
  `min_copper_stroke`, `fixed_stroke`, `_stroke_waveforms`, `_trace`, `StrokeTrace.psi_on`, docstrings).
- Create: `tests/app/test_drive_continuous.py` (fast).
- Modify: `tests/app/test_app_scan_equality.py` (docstring of the module and of `_reference_scan` only).
- Modify: `examples/kiyota_losses_check.py` (conduction and start flux in the JSON and the table).
- Modify: `src/srmapp/__init__.py` (0.10.0), `src/srmweb/cases.py` (`SCAN_BUDGET_S`), `src/srmweb/__init__.py`
  (0.12.1), `tests/web/test_report_route.py` (srmweb version literal).
- Create: `docs/validation/kiyota_single_pulse_16p3.json`, `kiyota_single_pulse_15p5.json` (copies of the 2026-11-18
  run outputs in `/home/server/srm-forge/runs/`), `docs/validation/kiyota_cc_16p3.json`, `kiyota_cc_15p5.json`,
  `docs/validation/scan_timing_cc.json`.
- Modify: `docs/r3-loss-results.md`, `docs/winding-scan-profile.md`, `CLAUDE.md`.
- Create: `docs/reports/bike-v1-2.md` and a row in `docs/reports/README.md`.

---

### Task 1: `_run`, `_simulate` and `_strokes` (about 3 h)

**Files:** `src/srmapp/drive/envelope.py`, `tests/app/test_drive_continuous.py`.

- [ ] `_run(t, omega, volts, r, on, off, psi0, trace=False)`: today's loop with a start flux per pair. `psi0` is
  sorted with the pairs. The start current is `np.interp(psi0, t.psi[on % n], t.current)` where `psi0 > 0`, else 0.
  Trace row 0 holds the start flux and current (zeros when `psi0` is 0, as today). It also returns the end flux and
  `beyond` (bool per pair): true when at some step ψ − (V + R·i)/ω·Δθ > ψ_lim(θ_k+1)·(1 + 1e-9). The extra work in
  the loop must not change ψ, i or the integrals.
- [ ] `_simulate(...)` keeps its signature, outputs and docstring meaning: it calls `_run` with zero start flux and
  computes `valid` as today.
- [ ] `_strokes(t, omega, volts, r, on, off) -> (w_t, w_l, i2, valid, psi0)`: `_simulate` once (through the module
  global, for P4). For the rejected pairs, two `_run` passes on that subset give G at 0 and at cap. Pairs with
  G(cap) > 0 stay invalid. Illinois (D2) runs on the rest. One final `_run` at the roots gives the integrals. A root is
  accepted when converged and not `beyond`. Accepted pairs take the final integrals, `valid` True and their root as
  `psi0`. All other pairs keep `_simulate`'s numbers and `psi0` 0.
- [ ] Constants `PERIODIC_TOL = 1e-6` and `PERIODIC_MAX_ITER = 60`, each with a one-line why.
- [ ] Fast tests in `tests/app/test_drive_continuous.py` on `map_fixtures.synthetic_map` (under 60 s in total):
  - P2 at 30, 1500 and 9000 r/min on the search grid, with and without trace.
  - P3 at the same speeds.
  - every accepted periodic stroke is periodic: `_run` from its root ends within `PERIODIC_TOL` of the root and
    `beyond` is false.
  - brute force on 5 accepted periodic strokes: p ← F(p) from 0 (up to 2000 periods) ends within 10 x tol of the root
    and the work within 1e-6 relative.
  - a pair with G(cap) > 0 is rejected, and the trace current of an accepted periodic stroke never passes the limit.
  - no stroke reaches `PERIODIC_MAX_ITER` at these speeds.
  - the full-period pulse of `test_tail_must_end_before_next_on` (turn-on 45, turn-off 225, 100 r/min) is rejected
    by `_simulate` (that test stays unedited) and accepted by `_strokes` with the flux at the limit at turn-on (the
    phase is on all the time). Its work is below 1 % of the best stroke's work at that speed (prototype: 1e-5).
- [ ] `python -m pytest tests/app/test_drive_continuous.py tests/app/test_app_scan_equality.py tests/app/test_drive_tail.py`
  passes. Commit.

### Task 2: Envelope, least-copper and fixed strokes (about 2 h)

**Files:** `src/srmapp/drive/envelope.py`, `tests/app/test_drive_continuous.py`.

- [ ] `envelope`, `min_copper_stroke` and `fixed_stroke` call `_strokes`. The RMS limit filter of `envelope` stays
  after it.
- [ ] `_stroke_waveforms(t, omega, volts, r, on, off, psi0=0.0)` and `_trace(..., psi0)` simulate the chosen stroke
  from its root, through `_run` with trace. `StrokeTrace.psi_on` (D5) holds the root.
- [ ] Docstrings: module (single pulse or continuous conduction with a hysteresis limit, no mutual coupling, which
  continuous conduction makes larger), `Envelope`, `StrokeTrace`, `fixed_stroke` (`valid` is false when no periodic
  state keeps the current within the limit). No other public change.
- [ ] Tests:
  - P5 at the speeds of `test_drive_tail.py` and at 12 000 and 40 000 r/min at 100 V.
  - a speed whose chosen stroke is continuous: on the synthetic map at 100 V and 0.1 Ω, 40 000 r/min (prototype:
    3.1x the single-pulse torque, 12 000 r/min stays single pulse). Assert that it is continuous. Then the waveform
    current is above 0 at every sample, q x mean torque equals `env.torque` and the
    RMS of the waveform equals `env.i_rms` (rtol 1e-3, as `test_waveforms_stay_one_period_and_integrate`).
  - `min_copper_stroke` reaches a torque that no single-pulse stroke reaches at that speed, its `psi_on` is above 0
    and its current never passes its limit. `fixed_stroke` at its angles and limit reproduces it (torque and RMS
    within 1e-9 relative, `valid` true).
  - for a single-pulse stroke `psi_on` is 0.
- [ ] `python -m pytest tests/app -m "not slow"` passes. Record its time against main (same machine, same load). Any
  test literal that changes is updated with old and new value and the reason in the commit message. The prototype
  run found none. Commit.

### Task 3: Kiyota example, versions and estimate constant (about 1 h)

**Files:** `examples/kiyota_losses_check.py`, `src/srmapp/__init__.py`, `src/srmweb/__init__.py`,
`tests/web/test_report_route.py`.

- [ ] Kiyota example: each stroke row gets `conduction` ("single pulse" or "continuous", from `psi_on`) and `psi_on`
  in the JSON and a column in the stdout table. Nothing else changes.
- [ ] srmapp 0.9.1 to 0.10.0 (the envelope and every evaluation made after it change). srmweb 0.12.0 to 0.12.1 when
  Task 4 changes `SCAN_BUDGET_S`, and `tests/web/test_report_route.py` takes the new literal. `web/` stays 0.12.0 (no
  frontend change).
- [ ] `python -m pytest tests/web -m "not slow"` passes. Commit.

### Task 4: LattePanda runs (about 3.5 h wall, about 1 h attended)

Run one at a time. Each unit writes its JSON and log. Check every acceptance line before committing.

- [ ] Copy `/home/server/srm-forge/runs/kiyota_full_16p3.json` and `kiyota_full_15p5.json` to
  `docs/validation/kiyota_single_pulse_16p3.json` and `_15p5.json` unchanged.
- [ ] Unit `cc-kiyota` (about 1.5 h, maps cached, about 5 min per new stroke solve):
  `systemd-run --user --unit=cc-kiyota --collect -p WorkingDirectory=/home/server/srm-forge-cc -E PYTHONPATH=src:tests
  sh -c '/home/server/srm-forge/.venv/bin/python -u examples/kiyota_losses_check.py --preset full --cache-dir
  /home/server/srm-forge/cache-kiyota --json docs/validation/kiyota_cc_16p3.json > /tmp/cc-kiyota-16p3.log 2>&1 &&
  /home/server/srm-forge/.venv/bin/python -u examples/kiyota_losses_check.py --preset full --stator-yoke 15.5e-3
  --cache-dir /home/server/srm-forge/cache-kiyota --json docs/validation/kiyota_cc_15p5.json > /tmp/cc-kiyota-15p5.log 2>&1'`.
  Acceptance:
  - (b), Fig. 16 59 kW and 99 kW have a continuous torque stroke at both yokes. (b) has a current stroke with RMS
    within 0.5 % of 130 A (`RMS_TOL`).
  - (a), (c) and Fig. 16 14.7 to 30.0 kW at 16.3 mm, and (a), (c) and 14.7 to 22.4 kW at 15.5 mm, are single pulse,
    and every number in their rows equals the single-pulse JSON exactly (the stroke cache hits, so the currents are
    the same).
  - record the peak current of every new stroke against the 300 A map top, and the measured peak 205 A at (b).
- [ ] Unit `cc-scan` (about 30 min): `examples/scan_timing.py --cache-dir /home/server/srm-forge/cache-timing --json
  docs/validation/scan_timing_cc.json`, same `systemd-run` form. Then `SCAN_BUDGET_S["auto"]` = the measured density
  "auto" time at 8 workers x 1.25 (the rule in `docs/winding-scan-profile.md`). "fixed" likewise if it changed.
- [ ] Unit `cc-86` (about 1 h): evaluate the scan-timing 8/6 screening density case with `thermal=True` (the rated
  evaluation, about 11 min on main) once from `/home/server/srm-forge` (main) and once from the worktree, each
  writing the envelope (speeds, torque, i_rms, waveform current), the chosen winding, `feasible` and the rating to an
  npz under `/tmp/cc-86/` with a throwaway script (not committed). Acceptance: every speed whose chosen stroke is
  single pulse (waveform current 0 somewhere) has torque and RMS current equal to main bit for bit. Every other speed
  has more torque. Record the wall time of the rated evaluation against `RATING_BUDGET_S["screening"]` (1063 s). If
  it is over 1063 s / 1.25, update that budget from the measured time x 1.25 in the same commit as
  `SCAN_BUDGET_S`.
- [ ] Commit the JSONs and the constant changes.

### Task 5: Docs (about 1.5 h)

**Files:** `docs/r3-loss-results.md`, `docs/winding-scan-profile.md`, `CLAUDE.md`, `docs/reports/bike-v1-2.md`,
`docs/reports/README.md`.

- [ ] `docs/r3-loss-results.md`, Kiyota section: rows for (b), 59 kW and 99 kW (stroke, RMS against measured, peak,
  model iron, ratios at both yokes), a "Conduction" column, finding 2 rewritten (continuous conduction is modelled
  from srmapp 0.10.0, the model at the measured RMS current at (b), the 15.5 mm 30 kW row), and the mutual-coupling
  note of this plan. Gaps are stated against the 10 to 15 % accuracy target. Say whether the three new points change
  the K_IRON_HI curve. Changing it is not in this plan.
- [ ] `docs/winding-scan-profile.md`: a section with the `cc-scan` times against the 2026-11-18 ones.
- [ ] `CLAUDE.md`: the srmapp paragraph ("the drive's flux tail runs past aligned" gains continuous conduction: the
  periodic steady state, the start-flux cap and current-limit rule, `StrokeTrace.psi_on`), the Waveforms paragraph
  (a continuous stroke's current does not return to zero), the "Current state" line for this part, and the versions
  (srmapp 0.10.0, srmweb 0.12.1).
- [ ] `docs/reports/bike-v1-2.md` from `docs/reports/TEMPLATE.md` (Goal, What shipped, Results, Decisions, Open after
  this step, Evidence), and a row in `docs/reports/README.md`. Written after CI is green, in the merge session.
- [ ] Commit.

### Task 6: Reviews, PR and CI (about 1.5 h)

- [ ] Opus final review of the whole branch against this plan (spec and code), fixes by the implementer.
- [ ] Push, open the PR, CI green on the fast suite (3.12 and 3.14). Record the CI fast-suite time against the last
  main run.
- [ ] Controller, not this plan's implementers: merge, the project doc in Notion (section and dated row), the Notion
  tracker (the continuous-conduction row Done only when its "Done when" holds, plus the new open items below), the roadmap row
  for Bike motor v1 part 2.

## Open items this plan leaves (add to the tracker)

1. The current-limit rule on single-pulse strokes (D3).
2. Mutual coupling under continuous conduction: Bike motor v1 part 4 (overlap map on the winner).
3. The Kiyota iron ratios at (b), 59 kW and 99 kW against the K_IRON_HI curve.
4. A web column or chip that says which speeds run in continuous conduction (no owner request yet).

## Out of scope

Mutual coupling in the drive model, any change to srmcore, the SIL and HIL plant, the web UI, a single-pulse switch,
finer default drive grids, and a faster periodic solver (Newton) unless risk R1 makes it necessary.

## Risks

- **R1, run time.** The winding scan gets about 2.7x slower (8/6 sample), the fast suite slower (`test_app_turns.py`
  is 428 s today). If the CI fast job passes the 30 min budget, or the two real search-job web tests pass their
  5400 s wait, stop and report to the controller. Do not cut tests or tolerances silently. Options then: Newton
  (1.5x at high speed), a smaller scan in the slowest fast tests, or a raised wait.
- **R2, steep voltage-limited strokes.** Without the clip, the periodic current follows V·(2·dwell/period − 1)/R, so
  one turn-off step moves it a lot. The grid study above moved the least-copper RMS by up to 3.5 %. Task 4 records the
  Kiyota numbers. A finer default grid is out of scope.
- **R3, results change.** Every evaluation, rating and loss map made from srmapp 0.10.0 can differ at high speed from
  stored ones (more power, new strokes, possibly another winding). The version bump and the report's version check
  say so. Stored evaluations keep their numbers.
- **R4, coupling.** Continuous strokes overstate the accuracy of the single-phase model (see the coupling note). The
  bike search must not trust a continuous-conduction margin below the coupling error until part 4 measures it.

## Hours

| Task | Hours |
|---|---|
| 1. `_run`, `_simulate`, `_strokes` and tests | 3 |
| 2. Envelope, least-copper and fixed strokes | 2 |
| 3. Kiyota example, versions | 1 |
| 4. LattePanda runs (3.5 h wall) | 1 attended |
| 5. Docs | 1.5 |
| 6. Reviews, PR, CI | 1.5 |
| Total | 10 attended, about 13 elapsed |

## Owner decision

None needed to start. The owner may want D3 (current-limit rule on single-pulse strokes too) decided before the bike
search. It changed no chosen stroke in the probes.
