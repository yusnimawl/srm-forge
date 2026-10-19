# Session handoff: after R3 (2026-10-19)

For the next session, which starts the next roadmap step. Read `CLAUDE.md`, then the roadmap `docs/superpowers/specs/2026-10-12-roadmap-r1-r10-design.md`, then this file.

## Start prompt

- `read docs/handoff-2026-10-19-post-r3.md and start R3b (brainstorm the spec first)`

## Where things stand

- **Merged to `main`:** R1 (reskin), R2 (DXF round trip, 0.5.0), the UI polish (logo, spinner, job stepper, queue panel), and the CI trim to Linux 3.12 on `main` and pull requests.
- **R3 (losses, drive tail; 0.6.0):** built on branch `r3-iron-loss`, PR https://github.com/yusnimawl/srm-forge/pull/4, **not merged**. Every task and the whole branch were reviewed; the fast suite passed (1236). The branch also carries two side fixes: live job progress (the stepper's clock and counts tick every second) and a solver fix (a failed UMFPACK factorization is now a non-converged point, not a crash).
- **R3 check:** the Materu 6/4 loss comparison runs on the laptop at the `full` preset (the `reference` mesh has 1.2 M nodes, about 70 h for the map and strokes, and it ran out of memory at 10 workers). Done 2026-10-19 (about 3 h): computed iron loss 18-78 % below the measurement on every row, outside the stated uncertainty on 7 of 10; an earlier turn-on fixes the copper loss but not the iron; the likely cause is the missing manufacturing build factor (owner decision whether to add a calibrated one). Details in `docs/r3-loss-results.md`, raw data in `docs/r3-data/`.
- **Angle convergence:** the slow test `tests/maps/test_stroke_convergence.py` passed (60 vs 120 angles within 2 %). `ANGLE_CONVERGENCE_REL` in `src/srmapp/losses.py` is still the 0.02 placeholder; replace it with the measured change if wanted.
- **Not in `VALIDATED_VERSIONS`:** 0.5.0 and 0.6.0. A validation campaign (`examples/em_validate_8_6.py`, slow suite, `tools/validation_report.py`) on the version that will be tagged is still owed. Run it once for 0.6.0 after R3 merges, not twice.

## Open items before or right after merging PR #4

1. Decide on an iron-loss build factor (the Materu gap is recorded as an open R3 finding; the roadmap R3 boxes are ticked).
2. Bench goldens still pin srmcore 0.5.0 (`bench/srmbench/reference/*.json`, `bench/tests/test_workload.py`). Magnetostatics did not change, so the values should hold: re-run them at 0.6.0, compare, then relabel.
3. Visual check of the Losses tab (desktop and 375 px) on `srmweb-smoke`, and re-evaluate existing cases before running Losses on them (pre-0.6.0 evaluations are refused).
4. Parked minors: a duplicated two-line 0.6.0 check at `src/srmweb/api.py:419-422`; a B(t) vitest uses an 80 ms sleep instead of awaiting; a doubled import in `tests/solvers/test_factorization_failure.py`.
5. Merge with the PR's checks run locally: GitHub Actions is blocked (private repo, free minutes used up, spending limit $0) until the minutes reset or the owner sets a budget.
6. Owner side, still open from R2: the DXF done-check (trim the stator OD arc at the 0° notch in Onshape, re-export, import, evaluate it and its parent, before/after table, validate on `full`).

## Next roadmap step: R3b, run report

From the roadmap (§3 R3b): one self-contained HTML file per case that opens offline and can be emailed. It holds the inputs, outline, key numbers, map plots, the before/after table for DXF cases, losses and efficiency from R3, the validation checks and budget, and the flux animation playing inline. A print layout lets the static parts save as PDF from the browser (a PDF cannot play the animation). Done when one click on an evaluated case gives the file and it renders the same with the server stopped.

- It builds on R3's Losses result, so start from the R3 branch or after the merge.
- Roadmap §5 marks R3b as cloud-suitable (templates and front-end code, little compute). The credit buys model work, not compute: keep test runs short there and do visual checks on the laptop.
- After R3b the roadmap goes to R4 (end effects: 3D NGSolve spot checks, a calibrated correction, laptop only, hours of compute). §5 also suggests R8 (control SIL) as the best use of the cloud credit.

## How the owner works

- Process: superpowers brainstorming (one question at a time, written spec, owner approves) → writing-plans → subagent-driven execution without asking which method.
- Model rules: Haiku for scouting and summarising logs; Sonnet implementers; Opus planner, task reviewers and the final whole-branch review. Always pass the model explicitly.
- Correctness first; no accuracy-for-speed trades without asking (the `full` vs `reference` choice above was the owner's).
- Short, scannable replies (the owner has ADHD). Challenge with reasons when warranted.
- Living project doc: https://claude.ai/code/artifact/7dc85cd6-a7f2-4bfa-8e35-de2604864d37. Update it in every session that changes the project (read `view` since the last rev first; rev 163 at this handoff).
- Pushing `main` after a merge is allowed; never force-push without asking. Commits end with the Co-Authored-By line the session gives.
- A cloud session cannot see local memory: put these rules in its start prompt.

## Gotchas found in this session

- After a version bump, reinstall (`python -m pip install -e ".[dev,ngsolve,web]" --no-deps`), or `tests/maps/test_em_validation.py` fails on stale package metadata.
- The laptop has 16 GB of RAM: a `reference` mesh of the 6/4 takes 150–200 s per solve; keep `reference` runs to about 4 workers.
- The fast suite takes about 28 minutes locally; run focused tests while iterating and the full suite once before merging.
- Examples that use test fixtures need `PYTHONPATH=tests`.
- Loss data carry the lamination thickness they were measured at (`LossData.thickness`); the classical eddy term is scaled to the design's thickness.
