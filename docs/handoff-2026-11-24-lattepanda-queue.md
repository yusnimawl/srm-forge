# Handoff 2026-11-24: LattePanda queue after the 0.8.0 campaign

For the next sessions. Read this, then the Notion progress page ("srm-forge progress"), then act.

## 1. State

- srmcore 0.8.0 is validated: PR #37 (c541366), tag `v0.8.0`, slow run 45065509871 green, report PASS (6e88b4e).
  Every evidence number equals the 0.7.0 campaign's. Tracker row 10q is Done.
- Found and fixed on the way, all merged with CI green:
  - PR #36, srmapp 0.9.1: stage 2 checks the windings whose EM ratio is at least the rated torque factor
    (1 + `TORQUE_FLOOR`) first.
  - PR #38: bench references relabelled to srmcore 0.8.0 (values re-solved unchanged).
  - PR #39, srmsil 0.9.1: the matched SIL runs the rig's float32 inputs (`compare.rig_scenario`). Row 8d is Done.
- Rows 8b and 8d are Done. A dispatched slow run on main after PR #39 (45102111410) is green 3/3.
- Row 8e is Done: PR #40 (82cde40), four slow jobs (validation, web, app, rest), each under 2 h on main run
  45277283558. The full-model 3D TEAM 24 test needs about 14 GB per solve, so it skips below 24 GB of RAM and runs
  on the LattePanda only.
- Scheduled slow runs start hours after their 03:17 UTC slot (11:20 UTC on 2026-11-22).

## 2. LattePanda queue (one heavy job at a time)

1. **Row 8e memory sampling.** Runs as systemd units `memf-*` from the session "What's the next thing". Wait until
   `systemctl --user list-units 'memf-*'` lists nothing active.
2. **IEEJ SRM2 and TEAM 24 runs (row 1d).** The seeded session for this stayed PENDING (the bridge did not
   spawn it), so the session "What's the next thing" runs it: unit `ieej-team24` in worktree `../srm-forge-ieej`,
   queued 2026-11-23 20:04 UTC; it waits until no `memf-*` unit is active, then starts runs 1 to 3. Follow
   `docs/handoff-2026-11-22-lattepanda-ieej-team24.md` on branch `ccr-ae0b0426-2aybo8`, runs 1 to 3 only. Run 4
   (the full 16-run R4 gate, about 4 h, 24 GB) waits for the owner, who decides after seeing run 3. Commit the
   result JSON files to that branch and push. Then send the results to the cloud session "Switched reluctance motor
   validation" (session_01Wzw16YT3vVcHut4teCjihs), which does the docs, the tracker and the PR.
3. **R5e gate V0 (row 10k), a new session, after step 2 is done.** Step 2 is done (8c96db5 on
   `ccr-ae0b0426-2aybo8`, results sent). Session "R5e gate V0: read and record (row 10k)" was created
   2026-11-23 21:17 UTC (session_01Wzw16YqYmkmu3jtyuuY69P) and stays PENDING until the bridge spawns it; open it in
   the app, or start a LattePanda session with this step. V0 is read-and-record only: every input of V2 to
   V4 in `docs/r5-sources.md` with page, figure and digitisation error, and the Kiyota Fig. 7 geometry read off the
   drawing (spec `docs/superpowers/specs/2026-11-05-r5-thermal-stress-design.md` §V0, plan
   `docs/superpowers/plans/2026-11-07-r5a-thermal-stress-core.md` row R5e). No comparison runs before V0 is
   complete. The papers are in `docs/sources/papers/` (git-ignored, IEEE copyright: never commit them).

## 3. Rules for every session

- Long jobs run with `systemd-run --user --unit=NAME ...`; a session restart kills processes the session started.
- In a worktree, run Python with `PYTHONPATH=src` (`src:tests` for examples); the shared `.venv` imports the main
  checkout otherwise.
- Update the Notion tracker, the project doc and the wiki in the same session (CLAUDE.md owner rules).
