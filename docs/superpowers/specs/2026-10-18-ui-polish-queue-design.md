# UI polish: SRM logo, motor spinner and job-queue stepper — Design Spec

Status: approved in chat 2026-10-18 (owner), from a mockup (8/6 logo, morphing spinner, two-job queue). Not an R step; it sits between R2 and R3.

## 1. Goal

Long jobs (a `full` map takes about 36 minutes, a validation about an hour) must show where they are: which jobs are queued, in what order, which step each is on, and how long is left. The app gets a logo that says what it is, and its loading states use that logo.

## 2. Decisions (owner, 2026-10-18)

- Style stays Graphite: white on near-black, no blue (the `noBlue` guard applies), no new dependencies.
- Logo: a simple 8/6 SRM outline (stator ring with 8 inward poles, rotor with 6 poles, a shaft hole), solid `currentColor`. It replaces the plain circle in the sidebar header and is the favicon.
- Spinner: the same motor, stator turning clockwise and rotor counter-clockwise, the pole counts morphing 6/4 → 8/6 → 12/8 every few seconds. With `prefers-reduced-motion` it holds still. It replaces the text-only loading states (case, charts, field mesh, frames).
- Queue and stepper: a queue panel on the Runs page and a stepper on the case page, after the 21st.dev "stepper" pattern: one row per step with a done, active or waiting marker joined by a line.
- Steps per job kind:
  - `evaluate`: Queued → Mesh built → Mapping (points done/total, elapsed, time left) → Choosing the winding → Saved
  - `validate`: Queued → Map (cache) → Checks and budget → Saved
  - `animate`: Queued → Frames (n/total) → Saved
  - `search`: Queued → Sampling → Designs (n/total, with map points) → Pareto set → Saved
- A queued job shows its place in its lane and an estimated start (the time left of the jobs ahead, from the same estimate the case page already uses).
- A run report as one HTML file is added to the roadmap after R3 (R3b), not built here.

## 3. Server

- `Reporter.progress` gains `step: str` (one of the kind's step ids) and `steps: list[str]` set at job start. The job runner sets the step at each phase change it already reports through `message`.
- `JobOut` gains `queue_position: int | None` (1 = next in its lane; None when running or final) and `lane: "main" | "quick"`.
- `progress.eta_s` for mapping: (elapsed / points done) × points left, once 5 % of the points are done; None before.
- No store schema change: progress is already stored as JSON.

## 4. Web

- `web/src/components/brand/SrmLogo.tsx` (props: size, title) and `SrmSpinner.tsx` (props: size, label for screen readers); one shared geometry helper in `web/src/lib/srmGlyph.ts` (pole rectangles for given Ns/Nr, unit tested).
- `web/public/favicon.svg` from the same geometry; `index.html` links it.
- `web/src/components/run/JobStepper.tsx` (steps from `JobOut.progress.steps`, the current `step`, the mapping bar and times) and `web/src/components/run/QueuePanel.tsx` (active and queued jobs, newest last, with position and estimated start).
- Steppers are live through the existing SSE `useJobEvents`.

## 5. Tests

- Server: steps and step ids for every job kind, queue positions with two lanes, eta None before 5 %.
- Web (vitest): `srmGlyph` pole geometry; stepper marks done/active/waiting from a progress object; queue panel ordering and positions; spinner renders a still frame under reduced motion; `noBlue` stays green.
- Visual check on `srmweb-smoke` with a queued and a running job, screenshot.
