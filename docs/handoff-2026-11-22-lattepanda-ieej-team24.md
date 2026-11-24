# Handoff 2026-11-22: LattePanda runs for IEEJ SRM2 and the TEAM 24 low-field fill

**Done:** runs 1 to 3 on 2026-11-23 (8c96db5), run 4 on 2026-11-24 (36fff0e). Results are in `docs/ieej-srm2-results.md`, `docs/m5b-team24-results.md` and `docs/r4-end-effect-results.md`.

For the LattePanda (owner or a session there). Four runs, all on branch `ccr-ae0b0426-2aybo8`. The cloud session
that wrote this does the docs, the tracker and the PR when the results come back.

## Rules

- Start only when the current LattePanda job has finished. Run these one at a time: they compete for memory, and
  a parallel run makes every timing on the machine wrong.
- Use a separate worktree, so the checkout of any other job does not change under it.
- Run under `systemd-run --user`. A session restart kills every process the session started, `nohup` ones too.
- Do not overwrite `docs/validation/r4_g1.json` or `docs/validation/team24.json`, and do not change
  `MEASURED_GAP` or `VALIDATED_VERSIONS`. These runs write new evidence files only.

## Setup (once)

`MAIN` is the main checkout with the `.venv`. Change the path if it is not `~/srm-forge`.

```bash
MAIN=~/srm-forge
cd $MAIN && git fetch origin ccr-ae0b0426-2aybo8
git worktree add ../srm-forge-ieej origin/ccr-ae0b0426-2aybo8
WT=$(realpath ../srm-forge-ieej)
```

`PYTHONPATH=src:tests` below makes Python load the worktree's code, not the main checkout's editable install.

## The runs

| # | What | Output | Time (estimate) | Peak memory |
|---|---|---|---|---|
| 1 | IEEJ SRM2 at `full`, library 10JNEX900 (stacking 0.9), 16 positions x 5 currents, 8 workers | `docs/validation/ieej_srm2_full.json` | about 15 min | about 12 GB (8 workers; screening workers took 0.7 GB each) |
| 2 | IEEJ SRM2 at `full`, stacking 1.0, 50/150/250 A, one process | `docs/validation/ieej_srm2_full_sf1.json` | about 1 h | under 2 GB |
| 3 | R4 G1 on the TEAM 24 curve with the low-field gap filled: `nominal` and `slab` only | `docs/validation/r4_g1_diez_webb.json` | about 10 min | 11.5 GB |
| 4 | Optional, after you see run 3: all 16 G1 runs on the filled curve (the full gate) | same file, extended | about 4 h (done 2026-11-24: 4 h 17 min) | 29 GB (`mesh_fine`; needs `MemoryMax=27G` and swap) |

The times are scaled from the cloud screening run (IEEJ) and from the 2026-11-05 G1 run (`r4_g1.json`: 3.9 h,
`mesh_fine` 23.7 GB), not measured for these exact runs.

Runs 1 to 3 as one queued unit:

```bash
systemd-run --user --unit=ieej-team24 --collect -p WorkingDirectory=$WT -p MemoryMax=22G -p OOMPolicy=continue \
  --setenv=PYTHONPATH=src:tests bash -c "
  $MAIN/.venv/bin/python examples/ieej_srm2_check.py --preset full --workers 8 --json docs/validation/ieej_srm2_full.json &&
  $MAIN/.venv/bin/python examples/ieej_srm2_check.py --preset full --stacking 1.0 --workers 1 --currents 50,150,250 --json docs/validation/ieej_srm2_full_sf1.json;
  $MAIN/.venv/bin/python tools/end3d/g1_team24.py --low-field diez_webb --keys nominal,slab --json docs/validation/r4_g1_diez_webb.json"
```

Watch with `systemctl --user is-active ieej-team24` and `journalctl --user -u ieej-team24 -f`. G1 with `--keys`
ends with "G1 INCOMPLETE" and exit code 2: that is expected, because the gate needs all 16 runs.

Run 4, if run 3 is worth it (same JSON; the two finished runs are reused). `mesh_fine` peaks at 29 GB, so the cap is 27 GB with swap allowed (a 22 GB cap kills it):

```bash
systemd-run --user --unit=g1-diez-webb --collect -p WorkingDirectory=$WT -p MemoryMax=27G -p OOMPolicy=continue \
  --setenv=PYTHONPATH=src:tests $MAIN/.venv/bin/python tools/end3d/g1_team24.py --low-field diez_webb \
  --json docs/validation/r4_g1_diez_webb.json
```

## What to look at

- Checked in the cloud before handoff: SRM2 meshes at `full` (328 072 nodes, 52 s) and the aligned 250 A point solves in 44 s with ψ 0.4986 Wb against 0.4985 at `screening`.
- Run 1: the tables at the end of the journal. At `screening` the unaligned ψ was within 0.19 %, the aligned ψ
  −4.76 % and the torque up to −6.46 % of the IEEJ peak (`docs/ieej-srm2-results.md`). `full` should move these by
  about 1 point at most; a larger change means the screening mesh is not converged on this machine.
- Run 2: the same table with stacking 1.0. At `screening` it was +4.36 % aligned ψ and +7.66 % torque.
- Run 3: torque and flux of `nominal` against the measured 3.22 N·m and 4.72e-4 Wb. On Table I as printed, G1 had
  2.842 N·m (−11.7 %) and 4.33e-4 Wb (−8.3 %). In 2D the fill raised the torque by 9.9 % and the rotor-pole flux by
  5.0 %, so expect the 3D values near 3.1 N·m and 4.5e-4 Wb if the effect carries over. mufem's 3D on its filled
  curve gives 3.15 N·m at 0.15 s.
- Run 4 only if run 3 lands near the measurement: it gives the full budget on the filled curve, so the gate can be
  read again.

## When done

Commit only the new JSON files on the branch and push:

```bash
cd $WT && git switch -c ccr-ae0b0426-2aybo8 --track origin/ccr-ae0b0426-2aybo8 2>/dev/null || git switch ccr-ae0b0426-2aybo8
git add docs/validation/ieej_srm2_full.json docs/validation/ieej_srm2_full_sf1.json docs/validation/r4_g1_diez_webb.json
git commit -m "LattePanda: IEEJ SRM2 full runs, G1 nominal and slab on the filled TEAM 24 curve"
git push origin ccr-ae0b0426-2aybo8
```

Then tell a cloud session "LattePanda runs pushed". It updates `docs/ieej-srm2-results.md`,
`docs/m5b-team24-results.md` and `docs/r4-end-effect-results.md`, tracker rows 1e and 1d, and the project doc, and
opens the PR. Remove the worktree after the merge: `git worktree remove ../srm-forge-ieej`.

## Why these runs

- IEEJ SRM2 (tracker 1e): a 2D cross-tool check on an 18/12 traction machine against the IEEJ TR 1589 maps. The
  screening run says the geometry is right and the residual is the iron curve; `full` separates the mesh error from
  that.
- TEAM 24 low-field fill (tracker 1d): Table I has no B-H point between 0 and 4000 A/m, and the fixture reads it as
  a straight line. Filled with the Diez–Webb form, the 2D static torque moves from −13.1 % to −4.5 %
  (`docs/m5b-team24-results.md`, "Low-field B-H fill"). If the 3D G1 moves the same way, much of R4's 11.7 % gap and
  of `MEASURED_GAP` (17 to 19 % in every 2D-verified budget) comes from the B-H table, not from end effects. Changing
  the budget is an owner decision after these runs.
