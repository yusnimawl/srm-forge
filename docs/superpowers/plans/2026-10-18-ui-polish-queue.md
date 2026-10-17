# UI Polish (logo, spinner, job queue) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show every queued and running job with its steps, place in line and time left; give the app an SRM logo and a motor-shaped loading spinner.

**Architecture:** The job runner reports a step id and the kind's step list in its existing progress JSON; `JobOut` adds the lane and queue position. The web app renders a `JobStepper` and a `QueuePanel` from that, live through SSE, and draws the logo and spinner from one SVG geometry helper.

**Tech Stack:** Python 3.12 (srmweb, FastAPI), React 19 + TypeScript + Tailwind v4, vitest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-18-ui-polish-queue-design.md`

## Global Constraints

- Graphite theme only: tokens from `web/src/index.css`; no blue anywhere (`web/src/lib/noBlue.test.ts`).
- No new npm or Python dependencies.
- `web/src/api/schema.ts` is regenerated (`python -m srmweb.openapi web/openapi.json; cd web; npm run gen:api`), never hand-edited.
- Step ids, verbatim: evaluate `queued, mesh, mapping, winding, saved`; validate `queued, map, checks, saved`; animate `queued, frames, saved`; search `queued, sampling, designs, pareto, saved`.
- `eta_s` is None until 5 % of the points are done.
- `prefers-reduced-motion`: the spinner shows a still 8/6 frame.
- Comments describe code as it is, never task history.

## Review Focus

1. A job that fails or is cancelled mid-step: the stepper marks that step failed or cancelled, not active forever (Task 1 test `test_failed_job_keeps_its_step`, Task 3 test "failed step").
2. Jobs stored before this change (no `steps` in progress): the UI falls back to the old bar without crashing (Task 3 test "legacy progress").
3. Two lanes at once (an animate job while an evaluate runs): positions count per lane (Task 1 `test_queue_position_per_lane`).
4. Server restart with queued jobs: positions recompute from the store (Task 1 `test_positions_after_restart`).
5. Narrow screens: the queue panel and stepper fit at 375 px (Task 4 visual check).

---

### Task 1: Server — steps, queue position, eta

**Files:** Modify `src/srmweb/jobs.py`, `src/srmweb/schemas.py` (`JobOut`), `src/srmweb/api.py` (job serialisation); regenerate `web/openapi.json` and `web/src/api/schema.ts`. Test: `tests/web/test_job_steps.py`.

**Interfaces — Produces:** `JobOut.lane: Literal["main", "quick"]`, `JobOut.queue_position: int | None`; `progress.steps: list[str]`, `progress.step: str`, `progress.eta_s: float | None` (plus the existing fields).

- [ ] Write failing tests: each job kind starts with its `steps` and `step == "queued"` and passes through its step ids in order (drive with the existing fake/fast runners in tests/web); a failed job keeps the step it failed in and status `failed`; queue positions 1..n per lane, None when running or final; positions after a store reopen; `eta_s` None below 5 % of points, then (elapsed/done)·left.
- [ ] Run → FAIL. Implement. Run `python -m pytest -m "not slow" -q tests/web` → PASS. Regenerate the schema; `cd web; npx tsc -b --noEmit` clean.
- [ ] Commit `feat(web): job steps, lane and queue position`.

### Task 2: Logo, favicon, spinner

**Files:** Create `web/src/lib/srmGlyph.ts` (+ `.test.ts`), `web/src/components/brand/SrmLogo.tsx`, `web/src/components/brand/SrmSpinner.tsx` (+ test), `web/public/favicon.svg`; modify `web/index.html`, `web/src/components/layout/AppShell.tsx:21` (circle → logo), and the text loading states in `CasePage.tsx:31,185`, `CasesPage.tsx:64`, `AnalysisTabs.tsx:57`, `FieldTab.tsx:52`, `AnimationSection.tsx:59,78` (spinner plus the existing text as its label).

**Interfaces — Produces:** `srmGlyph(ns: number, nr: number, poleScale?: number): { stator: Rect[]; rotor: Rect[] }` in a 100×100 viewBox centred at 0 (stator ring r 44 stroke 8, stator poles r 26–41, rotor poles r 0–24, shaft 17 with a 5 hole — the mockup values); `<SrmLogo size? title? />`; `<SrmSpinner size? label />`.

- [ ] Write failing vitest tests: `srmGlyph(8,6)` gives 8 and 6 poles at 45°/60° steps; spinner under reduced motion renders a static 8/6 with no animation frame requests; logo has an accessible title.
- [ ] Implement (requestAnimationFrame, stator +30°/s, rotor −80°/s, 2.4 s per pole set with a 0.2 s shrink/grow morph; stopped when unmounted). `npx vitest run` and `npm run build` → PASS.
- [ ] Commit `feat(web): SRM logo, favicon and motor spinner`.

### Task 3: Job stepper and queue panel

**Files:** Create `web/src/components/run/JobStepper.tsx` (+ test), `web/src/components/run/QueuePanel.tsx` (+ test), `web/src/lib/steps.ts` (+ test: step labels and state per step); modify `web/src/components/case/CaseActions.tsx` (`CaseJobProgress` → `JobStepper`), `web/src/pages/RunsPage.tsx` (queue panel on top).

**Interfaces — Consumes:** Task 1 `JobOut` fields. **Produces:** `stepStates(job: JobOut): {id, label, state: "done"|"active"|"waiting"|"failed"|"cancelled", detail?: string}[]`.

- [ ] Write failing tests: step states for running, queued, done, failed and cancelled jobs; labels from the spec; mapping detail "412 / 960 points · 7 min elapsed · about 9 min left"; legacy progress without `steps` falls back to the old bar; queue panel orders running first, then queued by position, with "starts in about N min".
- [ ] Implement. `npx vitest run`, `npm run build` → PASS.
- [ ] Commit `feat(web): job stepper and queue panel`.

### Task 4: Docs and visual check

- [ ] CLAUDE.md web section: job steps, `lane`/`queue_position`, logo and spinner components. Roadmap already carries R3b (run report).
- [ ] Controller: visual check on `srmweb-smoke` at desktop and 375 px with one running and one queued evaluate; screenshot to the owner.
- [ ] Commit `docs: job steps and brand components`.
