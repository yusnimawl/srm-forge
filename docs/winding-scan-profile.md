# Winding scan profile (tracker row 8c)

`srmapp.turns.choose_turns` scans every allowed winding with the drive envelope. Profiled 2026-11-17 on the 8/6
screening case of `tests/conftest.make_8_6` (1 kW, 3.2 N·m, 3000 to 6000 rpm; density mode, or wire mode with one
6 mm round wire at 100 A), cloud container with 4 cores, map from the cache. The LattePanda times are in the last
section.

## Where the time went

| Mode | Windings | Old code | Per winding |
|---|---|---|---|
| density | 1000 (paths 1 and 2, 500 turns each) | 1506 s | 1.5 s |
| wire | 159 | 213 s | 1.3 s |

cProfile of 60 density windings under the old code (80 s): 99 % of the time is `drive.envelope._simulate`, run
for 12 speeds per winding; 43 % of the total is `np.interp` inside it (three calls per step), the rest is
elementwise arithmetic on all 7935 (turn-on, turn-off) pairs at all 324 steps although each pair is only active
for 181 of them. 13 % more is `_stroke_waveforms`, which re-simulates the chosen stroke for the waveforms the scan
never reads. Building the PCHIP tables is 0.3 %. The map is not touched by the scan, so the 45 s map and the scan
share nothing. The wire mode was timed but not profiled separately; its per-winding cost matches density mode.

## Fixes (results unchanged, bit for bit)

1. `_simulate` sorts the pairs by turn-on and advances only the strokes running at each step (a contiguous slice).
2. The end torque of one step is the start torque of the next, so one of three interpolations goes (not at the
   table wrap, where row n and row 0 may differ in the last bit).
3. `envelope(waveforms=False)` skips the trace pass; the scan uses it.
4. Windings with the same (turn ratio, resistance, current limit, RMS limit) share one envelope: N turns on one
   path and 2N on two are the same drive. 250 of the 1000 density windings are such twins.
5. `choose_turns(workers=...)` runs the distinct envelopes in a process pool (fewer than `MIN_PARALLEL_JOBS` = 16
   stay in process). `evaluate_stage2(scan_workers=...)`; the case and search paths pass their `workers`.
6. `choose_turns(progress=, cancel=)`; `ScanCancelled` becomes status `cancelled` in `evaluate_stage2`. The
   evaluate job reports the winding step as drive evaluations done and a time left counted from the start of
   that step.

## Measured, same case and machine

| Mode | Old | New, 1 worker | New, 4 workers |
|---|---|---|---|
| density, 1000 windings | 1506 s | 438 s (3.4x) | 112 s (13.4x) |
| wire, 159 windings | 213 s | 76 s (2.8x) | 22 s (9.5x) |

The old runs shared the 4 cores with a second job and a test run, so the old times are if anything high; the
new ones ran alone. Equality: the full `scan` tuple (every `ScanPoint`), the chosen winding, `feasible`, and every
envelope and waveform array of the chosen winding equal the old output exactly in both modes and with 1 and 4
workers (`tests/app/test_app_scan_equality.py` checks the simulation, subsets of the scan and the pool against a
frozen copy of the old code, `tests/app/envelope_reference.py`).

## Not done

- A further cut is possible by sharing the pulse phase between strokes with the same turn-on (the state before
  turn-off is the same for every turn-off). Left out: more code for a smaller gain than 1 to 5.

## LattePanda (i5-1340P, 16 logical CPUs), 2026-11-18

`python examples/scan_timing.py` times the span the web evaluate job records in `scan_times`: from the complete map
to the chosen winding, through `srmapp.case.evaluate_design`, on the same case. Winding "fixed" is the winding that
"auto" chose. The default worker count is half the logical CPUs, 8 here (the web layer's default too).

| Mode | Winding | Windings scanned | 1 worker | 8 workers |
|---|---|---|---|---|
| density | auto | 1000 (750 distinct drives) | 239 s | 57.2 s |
| density | fixed | 1 | 0.8 s | 0.8 s |
| wire | auto | 12 | 3.8 s | 3.8 s |
| wire | fixed | 1 | 0.8 s | 0.8 s |

A drive envelope costs 0.32 s in both modes. The wire case scans 12 windings, not the 159 of the cloud run above:
one 6 mm wire at 100 A gives 12 windings on this machine with the peak-density cap and without it, so the cloud
run used a setup this page does not fully state. Fewer than `MIN_PARALLEL_JOBS` (16) evaluations stay in process,
so its 8-worker time equals the 1-worker time. Density 1 worker ran 239 s, 246 s and 257 s over three runs.

`SCAN_BUDGET_S` in `srmweb/cases.py` (the estimate before any scan was timed) is the measured time x 1.25, the rule
of the M5e2 speed budgets. The 2026-11-18 values were "auto" 72 s and "fixed" 1 s; from 2026-11-27 they are in
the next section.

## With continuous conduction (srmapp 0.10.0, LattePanda, 2026-11-27)

The 2026-11-18 table above is the single-pulse drive. Strokes the single-pulse simulation rejects now go through a
periodic-steady-state search, so the density scan is about 6x slower. Same case, machine and command
(`python examples/scan_timing.py`; `docs/validation/scan_timing_cc.json`):

| Mode | Winding | 1 worker | 8 workers | Before (1 / 8 workers) |
|---|---|---|---|---|
| density | auto | 1770.7 s | 363.3 s | 239 s / 57.2 s |
| density | fixed | 6.4 s | 6.4 s | 0.8 s |
| wire | auto | 5.8 s | 5.8 s | 3.8 s |
| wire | fixed | 1.5 to 1.6 s | 1.5 to 1.6 s | 0.8 s |

The wire windings are single pulse apart from a few strokes, so their time moved little (3.8 s to 5.8 s auto).

`SCAN_BUDGET_S` is now "auto" 454.1 s (363.3 s x 1.25, density at 8 workers) and "fixed" 8.0 s (6.4 s x 1.25).
