# Writing plan: wiki, project doc rewrite, academic writing

This is a living list. Every session that does writing work updates it in the same session: tick what is done, add what is new, and keep the Notion wiki's "Open work" list the same as this one.

## Documents

| Document | Where | State |
| --- | --- | --- |
| Wiki | Notion page "srm-forge wiki", https://app.notion.com/p/41c7b4b6b24e810391f0e009e0b0abdb | 12 pages plus the hub (written in Claude Docs on 2026-10-29 and 2026-10-30, End effects on 2026-11-06, Thermal on 2026-11-17; moved to Notion on 2026-11-18, with the Progress and Roadmap tabs as the "srm-forge progress" page under it); owner review open |
| Project history | Notion page "SRM design tool — how it was built", https://app.notion.com/p/41d7b4b6b24e813abe64e25e25d1cae8 | History only; the rewrite was closed 2026-11-11; moved from Claude Docs on 2026-11-19 (the Claude Docs copy, https://claude.ai/code/artifact/7dc85cd6-a7f2-4bfa-8e35-de2604864d37, is a read-only archive with the figures) |
| Dissertation-style project report | Google Docs | Connectors connected 2026-10-29, not started |
| Paper | Google Docs, or LaTeX later for submission | After the report |

The wiki explains the tool as it is now. The project doc keeps the history (what was decided, when, and why). The specs in `docs/superpowers/specs/` stay authoritative. When a wiki page and a spec disagree, the spec wins and the page gets fixed.

## Open work

### Wiki tabs

- [x] Overview: what the tool is, packages, where it stands
- [x] Architecture: srmcore layers, import rules, package layering, and a drawing of the pipeline
- [x] Solve and maps: mesh pipeline, presets, one solve, map building, map products
- [x] Validation: M5a to M5e2, the 2D-verified label, the uncertainty budget, material grades, the EMDLAB / Maxwell row
- [x] EMDLAB comparison: the accuracy check and the ranked list of features to port, and what not to copy
- [x] Search: `srmapp` stages, winding choice, limits and margin
- [x] Web tool: cases, jobs and lanes, tabs, export and import, chips, security
- [x] Losses: iron loss, cut edge, copper loss, efficiency map, the open Materu finding
- [x] Control: the controller contract, SIL, HIL, the comparison, known limits
- [x] Thermal: what R5a and R5b do now, gates V1 to V6 and their results, what is open (R5c to R5e) (2026-11-17)
- [x] Thermal and Web tool pages and the hub updated for R5c and R5d: the Thermal tab, chips, options graph, evaluate estimate, versions (2026-11-22)
- [x] Step reports: `docs/reports/` with a template and one page per merged roadmap step, R1 to R5d, R6d, R8a, R8b (2026-11-22)
- [x] Roadmap: merged items and a drawing of the six items ahead (moved to Notion, "srm-forge progress", 2026-11-18)
- [x] Commands
- [x] Glossary
- [x] End effects: the 3D reference model, gate G1 and the measured gap in the budget (added 2026-11-06)
- [x] Move the wiki from Claude Docs to Notion (2026-11-18)
- [x] Move the project doc from Claude Docs to Notion (2026-11-19)
- [ ] Owner review of all pages

### Project doc rewrite

Closed 2026-11-11 without the rewrite (owner, tracker review). The doc stays history only, and the report retells the same content in the style rules. A section is fixed only when the report quotes it. New entries still follow the style rules.

### Academic writing

- [x] Connect the Google Docs and Google Drive connectors (2026-10-29).
- [ ] Dissertation-style report, with a status per chapter kept here once the chapter list is fixed. Chapters on M1 to M5, R1 to R3 and R8 can start now, and the results chapters wait for R5. Draft outline: abstract, introduction, background on SRMs, method (geometry, mesh, solver, maps), validation, losses, control, results, discussion, references.
- [ ] Paper: pick the venue, then cut the report down to the venue's format. A journal or conference submission likely needs LaTeX and a `.bib` file.

## Style rules

All prose in the wiki, the project doc and the reports follows two guides:

- no-ai-slop, https://github.com/petergyang/no-ai-slop (`skills/no-ai-slop/SKILL.md`)
- ASD-STE100 skill, STE-flavored mode, https://github.com/danyuchn/asd-ste100-skill (`SKILL.md`, `references/writing-rules.md`)

What that means in practice:

1. Lead each section with its point: the result, the number, the date.
2. Use active voice and simple tenses. Write "the solver converged", not "convergence has been achieved".
3. Keep sentences under about 25 words and paragraphs under about 6 sentences.
4. Use no semicolons. Write two sentences.
5. Give one meaning to each word, and keep that word. Do not rotate synonyms for the same thing.
6. Give numbers, units, names and dates instead of adjectives. Cut "robust", "leverage", "seamless", "pivotal" and the other words on the no-ai-slop list.
7. Cut binary contrasts ("not X, but Y"), colon reveals, puffery, recap endings and "it is worth noting".
8. Keep technical terms, code names and units exactly as they are. STE fixed vocabulary does not apply.
9. Use em dashes rarely, at most one or two in a long page.
10. Use a table for items compared on several attributes, and a numbered list for steps.
