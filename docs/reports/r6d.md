# R6d: Optimisation research

Merged 2026-11-06, PR #21. Versions after the merge: unchanged (documents only).
Spec: none (roadmap R6d in `docs/superpowers/specs/2026-10-12-roadmap-r1-r10-design.md`). Plan: none. Detailed results `docs/r6d-optimisation-research.md`.

## Goal

Review the literature on SRM design optimisation and recommend the methods R7's spike compares. Done when the review is in `docs/` with cited sources and the R7 spike list follows from it.

## What shipped

- `docs/r6d-optimisation-research.md`: a cited review (problem, literature results, pole-shape and topology optimisation, winding choice and cheaper evaluations, the spike list, a spike review).
- A finding in the code: srmcore uses `stack_length` only as the 2D depth, so stack length can be rescaled after the map like turns. This led to map cost lever 1 (`rescale_stack`, PR #22).
- The R7 decisions in roadmap R7 and core spec sections 10 and 11. No code changed.

## Results

| Check or measurement | Value | Where measured |
| --- | --- | --- |
| Maps in a 10 h night, `screening` | 222 to 318 | LattePanda |
| One map, `screening` / `full` | 113 to 162 s / 694 to 928 s | LattePanda |
| Direct GA on FE, Diao et al. 2020 | about 50 000 samples, 3993 with Kriging and sequential subspaces | cited |
| Multi-objective DE on a 24/16, Tekgun et al. 2022 | from at least 3000 designs to 559 | cited |
| Spike version to build | about 60 h | LattePanda, estimate |

## Decisions

- 2026-11-06, owner: the spike compares the funnel baseline, a GP surrogate with qLogNEHVI, Kriging with NSGA-II on the model, and SMS-EMOA. Plain NSGA-II and NSGA-III are out.
- 2026-11-06, owner: two objectives, continuous and peak kW/kg, with kW/L shown and used as a limit. PyTorch is an optional extra for the spike only.
- 2026-11-06, owner: a full search gets one night (about 220 to 320 `screening` maps) and a quick mode about 1 h.
- 2026-11-06, owner: the DC bus is the 400 V class, with no minimum voltage at low state of charge.
- 2026-11-06, builder: the spike adds a second requirement set, common initial samples, a replay emulator for 20 seeds, a decision rule fixed in advance and an all-pole-set run of the winner (11 weaknesses found in the first sketch).

## Open after this step

- Pole-shape and topology optimisation were left out of R7 (an owner decision, tracker).
- R7 itself, including the live search view the owner asked for.
- The spike grew from about 60 h to about 80 h in density mode once the winding scan was counted (tracker 8c).

## Evidence

Written in a cloud session beside the R4 wrap-up. Merged with Markdown only (9d35b02). CI result: not recorded.
