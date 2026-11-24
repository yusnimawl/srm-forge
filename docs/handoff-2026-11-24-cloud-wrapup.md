# Handoff 2026-11-24: wrap-up of the cloud session "Switched reluctance motor validation"

The owner decided on 2026-11-24 that one session on the LattePanda does all srm-forge work from now on. This cloud
session (session_01Wzw16YT3vVcHut4teCjihs, 2026-11-22 to 2026-11-24) is closed. This file lists what it leaves
behind. `docs/handoff-2026-11-24-lattepanda-queue.md` still holds the LattePanda queue and the rules; it is not
repeated here.

## 1. Commits on `ccr-ae0b0426-2aybo8` that are not on main

The branch was deleted on GitHub when PR #42 merged, then recreated from main at 2b53b7e (the PR #42 merge).

| Commit | What it does |
|---|---|
| 09c766e | `docs/r4-end-effect-results.md`: the TEAM 24 residual study (tracker 1d) is closed as unexplained (owner, 2026-11-24); the remaining 3D G1 miss stays covered by `MEASURED_GAP`; the image factor stays 1.5, with the reason. |
| (this file) | This wrap-up. |

Nothing else is unmerged. Everything earlier on the branch (IEEJ SRM2, the TEAM 24 low-field fill, `MEASURED_GAP`,
LattePanda runs 1 to 5) is on main through PR #42: merge commit 2b53b7e, main CI run 45398052911 green.

## 2. Notion changes made by this session

### Tracker rows

| Row | Status now | Status note (short) |
|---|---|---|
| 1d, TEAM 24 residual study | In progress | Owner closed it as unexplained, image factor 1.5. Missing: 09c766e merged to main. Then it can be set to Done. |
| 1e, IEEJ SRM2 18/12 | In progress | PR #42 merged, main CI green. Missing: mufem 3D ratios against R4 and `tools/end3d`; DXF cleanup route. |

No other tracker row was changed. No row was set to Done.

### Progress page

- "Work in this order", item 3: the sentence about the owner deciding on the fill was replaced with: the owner
  accepted the fill, PR #42 merged 2026-11-24, and the remaining 1.5 / 1.0 point G1 miss has no measured cause.
- The lead paragraph and the "N of 17 steps merged" board title were not changed: no roadmap step merged.

### Project doc ("SRM design tool — how it was built")

- Milestone table: a new top row dated 2026-11-24 for PR #42 (IEEJ SRM2 check, TEAM 24 fill as the default,
  `MEASURED_GAP` re-derived).
- Paragraph "8/6 budget with the new gap" (LattePanda run 5), later marked "merged 2026-11-24 as 2b53b7e".
- Paragraph "TEAM 24 residual closed as unexplained" (owner decision, commit 09c766e).
- Earlier in the session (2026-11-22 to 2026-11-24) it also wrote or updated the paragraphs on the IEEJ SRM2
  cross-tool check, the TEAM 24 low-field fill and the owner decision on the filled curve. Several of these still say
  "not merged"; PR #42 merged them. The new milestone-table row says so, but the old paragraphs were not edited.

### Wiki

No wiki edits were made.

### Planned but not made

- Row 1d to Done: waits for 09c766e on main.
- Row 1e to Done: waits for its two open sub-items.
- The "not merged" wording in the older project-doc paragraphs (see above).

## 3. Open items

### Work not finished

1. Merge 09c766e (this branch) to main, then set row 1d to Done. It is a docs-only change.
2. Row 1e: the mufem 3D ratios (ψ and T against 2D, with and without end turns) against R4 and `tools/end3d`, and a
   DXF cleanup route. The IEEJ DXF does not pass `read_loops` as it is, so `tests/ieej_srm2.py` builds the machine
   from parameters read off the drawing.
3. R5e gate V2 (Faiz 2009). On 2026-11-24 this session sent the task to the session "What's the next thing"
   (session_01Wzw16ar8JdZpyLLZTJGp8r), at the owner's request. The message was delivered, but nothing confirms the
   session started it. It asked for a comparison script, a JSON under `docs/validation/`, a fast test and results in
   `docs/r5-thermal-results.md`, on that session's own branch, with no PR unless the owner asks. V4, V5 and the
   demonstration follow.
4. The next cloud-type items by tracker rank: continuous conduction in the drive model (rank 17) and the
   salient-rotor windage factor (rank 21). Neither was started.

### Pending owner decisions

- Lamination data for 10JNEX900 (row 3). The owner asked whether mufem's data could replace it: no. mufem's IEEJ SRM
  case has only a B-H curve read off the IEEJ portal figure, and none of the other seven quantities. The repo is
  CC BY-SA and the IEEJ terms need permission for figures, so the curve is not committed.
- The other owner rows on the tracker: terminal OOM policy, minimum DC-bus voltage, noise and vibration check, Losses
  tab visual check, wiki review, a measured continuous thermal case, and bearings and oil.

### Waiting on CI or a PR

Nothing. PR #42 is merged and main CI is green. No PR is open from this branch. No PR is subscribed.

## 4. For the LattePanda session

- The worktree `../srm-forge-ieej` tracks the old `ccr-ae0b0426-2aybo8`. Its tip c0a4c57 is an ancestor of the new
  branch, so `git pull --ff-only` there works. The 2026-11-22 handoff says to remove that worktree after the merge:
  `git worktree remove ../srm-forge-ieej`.
- `docs/handoff-2026-11-22-lattepanda-ieej-team24.md`: runs 1 to 5 are all done. Nothing in it is still to run.
- TEAM 24 uses the filled curve by default everywhere (`low_field="diez_webb"`). `--low-field table` gives Table I as
  printed. Both G1 records are kept: `docs/validation/r4_g1.json` (as printed) and `r4_g1_diez_webb.json` (filled).
  The 2D evidence is `team24.json` (filled) and `team24_table.json` (as printed).
- IEEJ SRM2 conventions are in `tests/validation/fixtures/ieej_srm2/README.md`:
  - The portal torque table is the half-machine torque, so the fixture doubles it.
  - x = 10 is the unaligned position.
  - The srmcore angle is 1.5(x − 10) − 15°.
- The mufem trial runs (the wheel, the IEEJ case and the traced B-H run) were in this session's scratch directory
  only. They are lost when the session is archived. Nothing from them is in the repo.
- To use this session's cross-session messages, the owner confirmed repository trust once. The LattePanda session
  does not need this.
