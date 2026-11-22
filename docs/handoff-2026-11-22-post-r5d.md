# Handoff 2026-11-22: after R5d

For the next session. Read this, then the Notion progress page ("srm-forge progress"), then act.

## 1. State

- R5d (Thermal tab, rating chips, run report Thermal section, rated kW/kg and kW/L axes and columns, the evaluate
  estimate counts the rating) is merged to main: 2026-11-22, PR #35 (6aa5246), CI green 3/3. srmapp 0.9.0, srmweb and
  `web/` 0.12.0, srmcore 0.8.0 (unchanged, not in `VALIDATED_VERSIONS`).
- Docs are current: `CLAUDE.md`, `docs/r5-thermal-results.md` (R5d section), `docs/reports/r5d.md`. Notion tracker
  rows 10j and the estimate row are Done, Roadmap R5d is Done, the project doc and the wiki (Thermal, Web tool, hub) are
  updated.
- New owner rule (2026-11-22, in `CLAUDE.md`): every merged roadmap step gets a one-page report
  `docs/reports/<step>.md` from `docs/reports/TEMPLATE.md`, plus a row in `docs/reports/README.md`. A step is not Done
  until its report is on main. Reports for R1 to R5d, R6d, R8a and R8b exist (backfilled; only `r5d.md` and `r4.md`
  were read line by line).
- In a worktree, run Python tests with `PYTHONPATH=src /home/server/srm-forge/.venv/bin/python -m pytest ...`. The
  shared `.venv` imports the main checkout otherwise. A new worktree also needs `cd web && npm ci`.

## 2. What is next

The next roadmap step is **R5e** (tracker row 10k), the last part of R5. All of it runs on the LattePanda:

1. V0: record every input of V2 to V4 with its page and digitisation error.
2. V2: the air-gap heat transfer against Faiz 2009.
3. V4: the coil-end temperature rise against Kiyota 2014 (41 K in 10 s).
4. V5: thermal mesh convergence.
5. V6 on the Kiyota 18/12 rotor, then the 8/6 and bench-target demonstrations.

Plan reference: `docs/superpowers/plans/2026-11-07-r5a-thermal-stress-core.md`. After R5e, R5 is done and the
roadmap moves to the R6c timings, then R6 (the what-if tab).

Run beside R5e on the LattePanda: the **srmcore 0.8.0 validation campaign** (row 10q). Until it passes, every new map
is "Unvalidated". Long jobs run with `systemd-run --user --unit=NAME --collect ...`, so a session restart does not stop
them.

The owner was asked "Should I start V0?" and has not answered yet.

## 3. Other open items

- Row 8b: closes when a weekly slow run passes on main (Linux). The scheduled run of 2026-11-15 was cancelled, and the
  run of 2026-11-22 had not started at 10:40 WIB. A manual dispatch may be needed.
- Row 10n (cloud): a cited windage factor for a salient rotor.
- Waiting on the owner: OOM policy (1c), 10JNEX900 lamination data (3), minimum bus voltage (3b), noise and vibration
  check (18c), Losses tab visual check (5), wiki review (6).

## 4. Calls made in R5d without the owner (listed in PR #35)

- One `RequirementCheck` is stored per evaluation (the verdict's), not one per checked winding.
- The check-only text is "Edit, then Evaluate, for the full rating".
- `rating_times` records only evaluations whose check held.
- The check-only view counts the passed speeds and does not list their r/min.
- The iron chip text stays verbatim, so an 8/6 to 6000 rpm reads "Iron ×3.2–3.2 band".
