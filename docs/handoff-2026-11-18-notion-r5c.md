# Handoff 2026-11-18: Notion move, R5c in progress

**Done 2026-11-19:** the Notion items are current (R5c Done, rows 10q and the estimate row added), the project doc moved to Notion, and CLAUDE.md points to Notion for all three documents.

For the next session. Read this, then the wiki Progress tab, then act.

## 1. Notion (the owner is moving every doc there)

The owner connected Notion on 2026-11-18. The session that wrote this file could not load the Notion tools (they load
at session start), so the Notion copies were not touched. A new session should:

1. Find the Notion copies of the wiki (Progress tab first) and the project doc "SRM design tool — how it was built".
2. Bring these items up to date there. Each one is already current in Claude Docs, so copy from there:

| Item | State | Where it stands in Claude Docs |
|---|---|---|
| Row 8c: winding scan times on the LattePanda | Done 2026-11-18, PR #32 (b646a17), CI 3/3 | Progress tab row 8c; project doc row 2026-11-18 "Winding scan times…" and the 8c history paragraph |
| Row 10a: Kiyota 10JNEX900 iron-loss check | Done 2026-11-18, PR #33 (5cf5d7c), CI 3/3 | Progress tab row 10a; project doc row "Kiyota 18/12 iron-loss check…" and the Kiyota paragraph |
| Row 10p (new): continuous conduction in the drive model | Not started | Progress tab, row under 10a |
| R5c: ratings replace j_limit | In progress, see section 2 | Progress tab row "R5c" (status not yet changed from Not started) |

3. Ask the owner whether CLAUDE.md's two owner rules (living project doc, progress tracker) should now point to
   Notion, and change them only on a yes.

Claude Docs links: wiki https://claude.ai/artifact/W18pUfnse2MuR1brNdM2VR, project doc
https://claude.ai/code/artifact/7dc85cd6-a7f2-4bfa-8e35-de2604864d37.

## 2. R5c, in progress

- Plan: `docs/superpowers/plans/2026-11-18-r5c-ratings-in-search.md` (6 tasks), spec R5 §5.
- Branch `r5c-ratings` in the LattePanda worktree `.claude/worktrees/bridge-cse_01Wzw16a6nqUM6BmW7xBXmgG`, executed
  subagent-driven. Ledger: `.superpowers/sdd/2026-11-18-r5c-ratings-in-search/progress.md` in that worktree
  (git-ignored; trust it and `git log` over memory). At writing, Task 1 (rating core) was implemented and running its
  slow tests, not yet committed.
- Plan decisions the owner approved ("go", 2026-11-18): a winding is checked at the required torques, not rated to
  its maximum; only the chosen winding gets the full rating. `J_SCREEN` = 40 A/mm² sits in the scan's EM pass, not
  stage 1. srmcore 0.8.0 stays out of `VALIDATED_VERSIONS`.
- Follow-up tracker rows to add when R5c merges: validation campaign for srmcore 0.8.0 (LattePanda); the evaluate
  time estimate does not count the rating (R5d).

## 3. Results this session (already in the repo)

- 8c: density auto 239 s with 1 worker, 57.2 s with 8; wire auto 3.8 s; `SCAN_BUDGET_S` auto 72 s, fixed 1 s;
  R7 spike about 80 h in density mode (`docs/winding-scan-profile.md`, R6d §6).
- 10a: measured iron-and-other over model iron about 3 below 1.5 kHz, 5 to 7 at 2.78 kHz
  (`docs/r3-loss-results.md`). Owner chose `K_IRON_HI` as a frequency curve: 3.2 up to 1.5 kHz, linear to 7.0 at
  2.78 kHz, held above (`srmapp.cooling.k_iron_hi`).
- 10p finding: Kiyota's high-power points need continuous conduction; the drive model only does single pulses.

## 4. Queue after R5c (LattePanda, one job at a time)

R5d (Thermal tab), R5e gates (V0 first; the Kiyota geometry part of V0 is done in `tools/digitise_kiyota.py`),
10p, 10n (salient windage), 1d (TEAM 24 residual, 2 days), R6c timings, then R6, R7.
Row 8b closes when the weekly slow run passes on main (Sunday 2026-11-22).

## 5. LattePanda practice

- Session restarts kill every process the session started, including `setsid nohup` ones. Run long jobs as
  `systemd-run --user --unit=NAME --collect SCRIPT` (survives); watch with `systemctl --user is-active NAME`.
- Background watchers in the session stop at 2 h and on restart; re-arm them.
- The source PDFs in `docs/sources/papers/` are git-ignored; worktrees do not have them (tools take `--papers DIR`).
- Run outputs of this session: `/home/server/srm-forge/runs/` (Kiyota JSON and logs), caches `cache-kiyota/`,
  `cache-timing/` (untracked, safe to delete).

## 6. Waiting on the owner (unchanged)

Lamination supplier data (3), minimum bus voltage (3b), noise check decision (18c), bearing choice (10o), OOM
policy (1c), Losses tab check (5), wiki review (6), measured thermal case (10b).
