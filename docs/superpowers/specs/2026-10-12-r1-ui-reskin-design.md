# R1 — UI reskin and label rename — Design Spec

Status: approved in chat 2026-10-12 (owner). Parent: `2026-10-12-roadmap-r1-r10-design.md` §3 R1. Reference mockup: `docs/r1-mockups/case-page.html` (theme "Graphite").

## 1. Goal

The web app looks clean and black, Scalar-style, with no blue anywhere (chrome and data), and stops claiming more than the evidence shows. Layout and behaviour do not change; R1 is a reskin, not a redesign.

## 2. Decisions (owner, 2026-10-12)

- Theme: Graphite (monochrome; white is the only accent; colour only in data).
- Dark only. The light theme, the `.dark` variant and `ThemeToggle` are removed.
- No blue in data either: |B| uses inferno; case lines use the Graphite palette plus a dash pattern each (colour-blind backup, since blue/orange is no longer available).
- Built on tokens, so later React/shadcn components inherit the theme; a guard test keeps blue out.
- Label "EM-validated" becomes "2D-verified". No srmcore version bump: a bump would drop 0.4.0 from `VALIDATED_VERSIONS` until a new validation campaign and invalidate every cached map, for a display string. The 2026-10-06 validation report stays as history.

## 3. Theme tokens (`web/src/index.css`)

One `:root` block; shadcn tokens map onto these values.

| Token | Value | Use |
|---|---|---|
| `--background` | `#0a0a0a` | page |
| `--card`, `--popover`, `--sidebar` | `#111111` | panels |
| `--muted`, `--secondary`, `--accent` | `#181818` | raised surfaces, hover, active nav |
| `--border`, `--input` | `#232323` | hairlines |
| `--border-strong` (new) | `#333333` | inputs, buttons |
| `--foreground` and every `*-foreground` on dark | `#ededed` | text |
| `--muted-foreground` | `#8a8a8a` | labels |
| `--faint` (new) | `#5c5c5c` | units, axis ticks |
| `--primary` | `#ededed`, `--primary-foreground` `#0a0a0a` | the one accent: primary button, active tab underline, focus |
| `--ring` | `#ededed` | focus ring (3 px, `#ffffff14` halo) |
| `--feasible` / ok | `#9bd88a` | pass, feasible |
| `--warn` (new) | `#e8b04a` | warnings, the j_limit chip dot |
| `--destructive` | `#f2716b` | errors |
| `--radius` | `0.625rem` (cards 10 px, controls 6 px) | |

Fonts: Geist (UI) and Geist Mono (numbers, inputs, axis ticks; `tnum`) from Google Fonts, replacing Fira Sans and Fira Code. Thin borders, no shadows, no gradients.

## 4. Data colours

- **|B| colour map:** `web/src/lib/inferno.ts` (matplotlib inferno, 17 stops, same interface and tests as `viridis.ts`) replaces `viridis` in `fieldGl.ts` and `ColorBar.tsx`; `viridis.ts` and its test are deleted. Flux lines on the field plot: `#ededed` at 0.7 alpha (they must read on every inferno shade; checked on the dark and bright ends).
- **Series palette** (`LINE_COLORS` in `lib/analysis.ts`), in order: `#ededed` white, `#e8b04a` amber, `#9bd88a` green, `#e07fb5` pink, `#f2716b` coral, `#c3a6f0` lavender, `#8a8a8a` grey. Every hue is outside 190–250°.
- **Dash patterns** (`LINE_DASHES`, same index as the colour): solid, dash, dot, dash-dot, long-dash, long-dash-dot, solid thin. Applied wherever cases are overlaid.
- **Plotly template:** one template in `PlotlyPlot.tsx` (transparent paper and plot background, grid `#232323`, zero line `#333333`, tick font Geist Mono 11 px `#5c5c5c`, title and legend font Geist `#8a8a8a`, hover label `#181818`/`#ededed`, colourway = the series palette). No chart sets its own background or font.
- The motor diagram uses `--iron` `#2a2a2a`, `--iron-edge` `#4a4a4a`, coil `#6b4a2b`, the phase-A axis dashed in `--primary`.

## 5. Pages

All pages (`CandidatePage`, `CasePage`, `CasesPage`, `LoginPage`, `NewSearchPage`, `RunPage`, `RunsPage`, `SettingsPage`) and their components are restyled to the mockup:

- App shell: left sidebar nav (brand mark, New search, Runs, Cases, separator, Settings), active item on `--accent`; on phones a horizontal nav row.
- Page header: breadcrumb, title, pill tags (origin, status), actions right-aligned.
- `Banner` is replaced by chips (§6).
- Cards: `--card` with a hairline border; tab bars with an underline on the active tab; inputs in Geist Mono with the unit inside the field; the error state is a red border plus a one-line hint under the field.
- Key numbers as a KPI strip (value in Geist Mono, unit small and muted, label under it).
- Tables: hairline rows, muted headers, numbers right-aligned in Geist Mono.

Every page keeps its current routes, data, behaviour and accessibility attributes (roles, labels, 44 px touch targets).

## 6. Label and chips

- `srmcore.maps.validation.LABEL = "2D-verified"`; module and class docstrings, comments and messages say "2D-verified" where they mean the label. Function and class names (`em_validate`, `EmValidation`) stay: the checks are EM checks.
- Web: `CaseStatus` `"EM-validated"` → `"2D-verified"`; `Banner`, `CaseActions` ("Already 2D-verified"), `CaseTable`, `CasesPage` and the tests follow. Stored cases whose validation carries the old string still count as verified (the UI tests the label's presence, not its text).
- Chips under every result header:
  - `2D-verified · srmcore <version>` (ok dot) when the case carries the label, else `Unvalidated` (no dot);
  - `Peak only · assumes j_limit <N> A/mm²` (warn dot) on run results, candidates and cases, with N the resolved value (the default 20 when unset). Where the API does not return the resolved `j_limit`, it adds it to the response model and `web/src/api/schema.ts` is regenerated.
- Docs that describe the label as it is now (CLAUDE.md, the spec §8.5 wording, `docs/validation-report.md` generator text) say "2D-verified"; dated result documents stay as written.

## 7. Guards and tests

- `web/src/lib/noBlue.test.ts` (Vitest) scans every file under `web/src` except `api/schema.ts`: it fails on Tailwind classes `blue-`, `sky-`, `indigo-`, `cyan-` and on any hex colour (`#rgb`, `#rrggbb`, `#rrggbbaa`) or `rgb()`/`hsl()` literal whose hue is 190–250° with saturation above 15 %. It reports file and line.
- `inferno.test.ts` mirrors the old viridis test (end points, clamping, monotone lightness).
- Existing frontend tests updated for the new strings; `python -m pytest -m "not slow"` passes (label string in Python tests); `npm run build` passes.
- Sign-off: screenshots of every page at desktop and phone width, from the built app, reviewed by the owner.

## 8. Out of scope

New layouts, new features, the output-side inputs and ratio (R7), the options graph axes (R5, R7). They come with their own R steps.
