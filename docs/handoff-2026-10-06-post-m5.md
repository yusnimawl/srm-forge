# Session handoff: after M5 (2026-10-06)

For the next session. M5 is complete and merged to `main` (tag `v0.4.0`): srmcore 0.4.0 is in `VALIDATED_VERSIONS`, and the 8/6 `full` map earns "EM-validated". Read `CLAUDE.md`, then `docs/validation-report.md`, then this file.

## Start prompt

- `read docs/handoff-2026-10-06-post-m5.md and start the next milestone`

## Release (done 2026-10-06)

- Merged to `main`, tagged `v0.4.0`. The tag's slow suite passed on CI (Linux 59 min, Windows 91 min): https://github.com/yusnimawl/srm-forge/actions/runs/37461180818. Report verdict PASS.
- The `main` push ran two fast jobs (Linux and Windows 3.12), the tag four, as designed.
- For the next release: run the validation campaign on the new version, add it to `VALIDATED_VERSIONS`, regenerate the report (gated evidence from another version reads as stale), tag, record the slow run in `docs/validation/ci.json`.

## Slow suite, measured locally (2026-10-06)

- 52 passed in 38:01 on the laptop (i7-13620H, 8 workers).
- Peak memory 5.1 GB in one process (the `em_validate` end-to-end test, `reference` mesh). GitHub's private runners have 7 GB; if a CI job runs out of memory, the fix is an owner decision.
- Longest tests: `em_validate` end-to-end 574 s, 8/6 screening goldens 255 s, FEMM fixture freshness 94-246 s per machine, mesh property 241 s.
- On a 2-vCPU runner expect several times the local time.

## Results

- Report: `docs/validation-report.md` (PENDING until the tag's slow run is recorded). Evidence JSON in `docs/validation/`, each stamped with the srmcore version; the report marks evidence from another version as stale.
- 8/6 `full` em_validate: every check passes; budget about ±10 % (M19 grade C allowance).
- FEMM: worst error / limit 0.11 (8/6), 0.20 (12/8), 0.09 (24/16).
- Speed budgets (worst case × 1.25): `screening` < 430 s, `full` < 44 min, `full` extras < 31 min. `screening` is now about 5× the old 90 s target because of the 40-angle grid; the optimizer (#6) will feel it.
- Fast suite 658 passed in 9:26 on an idle machine (budget 10 min; little headroom).

## Next after the release

- Revisit the search margin 1.05 (handoff 2026-10-02), then v0b.
- Library: Hiperco stacking factors (0.95) and M43/M19 Js and density are provisional; replace with supplier values.
- gmsh is GPLv2+ and PyMuPDF (dev tool) is AGPL: fine in-house, matters if the tool is ever distributed.

## Process notes

- Long runs: detached PowerShell with ASCII logs and a status file; a Monitor re-armed every 30 min. Pool scripts need the `__main__` guard on Windows.
- A subagent appended to a test file with a shell heredoc once; the rule "edit only with Edit/Write" must stay in every dispatch.
