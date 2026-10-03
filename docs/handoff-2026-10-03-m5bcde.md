# Session handoff: M5b–M5e (2026-10-03)

For a fresh Claude Code session working on one of M5b, M5c, M5d or M5e. Read this, then `CLAUDE.md`, then the milestone's section in `docs/m5-roadmap.md`, then the core spec sections it names.

## Start prompt (paste one)

- `read docs/handoff-2026-10-03-m5bcde.md and start M5b`
- `read docs/handoff-2026-10-03-m5bcde.md and start M5c`
- `read docs/handoff-2026-10-03-m5bcde.md and start M5d`
- `read docs/handoff-2026-10-03-m5bcde.md and start M5e`

## What to do in the session
1. Read the milestone's section in `docs/m5-roadmap.md` and the spec sections it names.
2. Brainstorm (`superpowers:brainstorming`). Ask the owner the milestone's "owner decisions first" one at a time, with a recommendation each. A grill by several agents (domain expert, PM, EM engineer) worked well in M5a when the owner asked for it.
3. A cheap throwaway spike (scratchpad) before committing to a design paid off in M5a (it found the La definition bug and the angle-grid error). Offer one when a design choice hinges on numbers.
4. Spec in `docs/superpowers/specs/YYYY-MM-DD-m5x-...-design.md` → `superpowers:writing-plans` → `superpowers:subagent-driven-development` → `superpowers:finishing-a-development-branch`.

## Owner preferences
- Correctness first. Time and compute are not constraints ("no need to worry about time, go ahead with all the resource"); never trade accuracy for speed.
- Short, scannable replies (ADHD). Ponytail mode is active.
- Execution is always subagent-driven: Sonnet implementers, Opus reviewers for judgment-heavy diffs, Opus final whole-branch review. Do not ask which method.
- Feature branch per milestone. Local merge only on the owner's explicit yes; **never push**.

## State of the repo
- `main` (local, not pushed), head `e0a2a21` (M5a merge) + this handoff. srmcore 0.2.0.
- Fast suite: 545 passed in 9:21 (budget < 10 min; little headroom — new fast tests must be tiny or replace others). Slow suite green (28).
- M5a results: `docs/m5a-results.md`; generated study report `docs/m5a-convergence.md`; data `docs/m5a-data/`; study script `examples/mesh_convergence.py run|run-presets|split|report`.
- Presets: `screening` knobs; `full` = scale 2^(-1/2); `reference` = scale 0.25. Grids 40 × 8 / 48 × 20 / 120 × 40, angle grid clustered at the pole corners. La/Lu at 5 % of I_max. Held-out torque limit 1.7 % at 64 samples.
- Open owner items: spec §10 (the three [M5a→M5] items: speed budgets, band noise, `iron_b_peak`) and the table in `docs/m5-roadmap.md`.

## Process notes (learned the hard way)
- Long runs: launch detached (`Start-Process powershell ... -WindowStyle Hidden -PassThru`, `python -u`, ASCII logs via `Out-File -Encoding ascii`); watch with a Monitor that also watches the PID and re-arm every 30 min. `*>>` in PowerShell writes UTF-16 — grep then sees nothing.
- Scripts that use the process pool need an `if __name__ == "__main__":` guard on Windows (spawn).
- A process started before a code change keeps the old code in the parent, but spawned pool workers import the new code. Run long baselines from a separate worktree with `PYTHONPATH=<worktree>\src`.
- Memory: 16 GB laptop. About 1.2–1.6 M nodes (4–6 GB) is the largest single solve that does not page; check `PrivateMemorySize64` against `WorkingSet64`.
- Pool runs compete for CPU: time the fast suite only on an idle machine.
- Subagents have rewritten files with scripts (sed/printf); say it is a hard rule in every dispatch and always require the report file.
- Plan-code pitfalls: `srmcore.materials` exports nothing (import from `srmcore.materials.library`); examples that import `conftest` need `PYTHONPATH=tests`.
- `full` maps take 27–68 min (8 workers); `v0_search.py` defaults take about 9.5 h.
