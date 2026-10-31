# Session handoff: after R8 and the 0.7.0 campaign (2026-10-31)

For the next session. Read `CLAUDE.md`, then the roadmap `docs/superpowers/specs/2026-10-12-roadmap-r1-r10-design.md`, then this file.

## Start prompt

- `read docs/handoff-2026-10-31-post-r8.md and start R4 (brainstorm the spec first)`

## Where things stand

- **Merged to `main`:** R1, R2, R3, R3b, R3c, R8a, R8b, the EMDLAB / Maxwell check (PR #9) and the public-repository change (PR #10, GPL-3.0-or-later, full CI matrix, weekly slow suite).
- **0.7.0 validation campaign (PR #11, branch `validate-0.7.0`):** run on the LattePanda Sigma (i5-1340P, 30 GB, Python 3.14). Every `em_validate` check passes except `engine_version` before the add; FEMM worst error / limit 0.20; EMDLAB unchanged; speed 8/6 `full` 694 s, 12/8 `full` 928 s (budget 2640 s). `VALIDATED_VERSIONS = ("0.4.0", "0.7.0")`. The report reads PENDING: `docs/validation/ci.json` waits for the `v0.7.0` tag's slow run.
- **Cleanup (branch `cleanup-handoff-minors`):** the parked minors from the 2026-10-13 and 2026-10-19 handoffs, the R1 and R8 roadmap ticks and this file.

## To finish 0.7.0

1. Merge PR #11, tag `v0.7.0` on `main`, wait for the `slow` and `ci` tag runs (Windows and Linux).
2. Write the slow run into `docs/validation/ci.json` (`tag`, `run_url`, `result`), run `python tools/validation_report.py` (expect PASS), commit to `main`.

## Still open

- Materu iron-loss gap (computed 18–78 % below measured; the cut-edge factor does not close it): owner decision.
- `ANGLE_CONVERGENCE_REL` (`src/srmapp/losses.py`) is 0.02, the limit the slow test enforces; the measured change was never recorded. Replacing it changes the iron-loss uncertainty: owner decision.
- Owner checks: the R2 Onshape done-check; the Losses tab visual check at desktop and 375 px.
- Provisional Js, density and stacking for M19, M43, Hiperco, Tata, Cogent and VAC; no grade-A supplier data.
- Stage-1 false-drop rate unmeasured.
- Slow-suite peak memory (5.1 GB at 0.4.0) against 7 GB GitHub runners: watch the tag run.
- `tools/validation_report.py` does not check that `ci.json` names the installed version; a stale CI entry reads PASS.
- `docs/validation/emdlab.json` is written but not read by the report.

## Gotchas found in this session

- `tests/validation/test_materu_losses.py` used the `materu_rows` default preset, `reference` (about 70 h, 26 GB); it now passes `screening`. Check the preset of any slow test that calls an example's defaults.
- `pkill -f <name>` also matches the shell that runs it; kill by PID.
- Pytest node ids can hold spaces (parametrize ids); pass files, not `$(cat ids)`.
- The fast suite takes about 28 min on the LattePanda; the slow suite about 4 h plus the campaign examples about 1.5 h.
- `platform.processor()` is empty on Linux; `speed_budget.py` now reads `/proc/cpuinfo`.
- The LattePanda has passwordless sudo through `/etc/sudoers.d/90-claude-setup` (owner choice) and the git identity set globally.
