# Writing plan: wiki, project doc rewrite, academic writing

This is a living list. Every session that does writing work updates it in the same session: tick what is done, add what is new, and keep the Claude Docs wiki's "Open work" list the same as this one.

## Documents

| Document | Where | State |
| --- | --- | --- |
| Wiki | Claude Doc "srm-forge wiki", https://claude.ai/artifact/W18pUfnse2MuR1brNdM2VR | Started 2026-10-29: Overview and Architecture tabs |
| Project history | Claude Doc "SRM design tool — how it was built", https://claude.ai/code/artifact/7dc85cd6-a7f2-4bfa-8e35-de2604864d37 | Rewrite in place not started |
| Dissertation-style project report | Google Docs | Waiting on the Google Drive connector |
| Paper | Google Docs, or LaTeX later for submission | After the report |

The wiki explains the tool as it is now. The project doc keeps the history (what was decided, when, and why). The specs in `docs/superpowers/specs/` stay authoritative. When a wiki tab and a spec disagree, the spec wins and the tab gets fixed.

## Open work

### Wiki tabs

- [x] Overview: what the tool is, packages, where it stands
- [x] Architecture: srmcore layers, third-party import rules, package layering
- [ ] Architecture: a drawn diagram of the M1 pipeline (Design, validator, outline, Gmsh geometry, static mesh, moving band, quality gate)
- [ ] Solve and map pipeline: materials, physics, solvers, post, maps, map products
- [ ] Validation: M5a to M5e2, the 2D-verified label, the uncertainty budget
- [ ] Search: `srmapp` requirements, windings, turns scan, drive envelope, Pareto set
- [ ] Web tool: `srmweb`, `web/`, jobs and lanes, cases, DXF round trip, run report
- [ ] Losses: R3 iron and copper loss, efficiency map, R3c cut edge, the open Materu finding
- [ ] Control: R8a SIL and R8b HIL
- [ ] Roadmap R1 to R10 as a drawn timeline
- [ ] Commands
- [ ] Glossary: SRM, ψ, La, Lu, band, preset, 2D-verified, reference turns

### Project doc rewrite

- [ ] Rewrite in place, one section per edit, with the style rules below. Keep every fact, number, date and decision. Read the doc (`view` since the last rev) first so owner edits are kept.

### Academic writing

- [ ] Connect the Google Drive connector in claude.ai Settings, Connectors. A later session then writes into Google Docs directly.
- [ ] Dissertation-style report: abstract, introduction, background on SRMs, method (geometry, mesh, solver, maps), validation, losses, control, results, discussion, references.
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
