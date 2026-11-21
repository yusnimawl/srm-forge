# R5d: Thermal tab, run report, options-graph axes

Status: design, 2026-11-21. Parent spec: `docs/superpowers/specs/2026-11-05-r5-thermal-stress-design.md` §5 and §11.
Builds on R5c (PR #34): every stage-2 evaluation can carry a `Rating` (`srmapp.thermal.Rating`).

## 1. Intent

R5c made the search rank designs on rated continuous and peak kW/kg, but the web app shows almost none of the
rating. The owner opens a rated design to answer two questions (owner, 2026-11-21):

1. **What limits it?** At each rated speed: does heat or the EM envelope cap the torque, where is the hot spot, how
   far is the design from the requirement, and what caps the top speed.
2. **How to make it better?** Which uncertain inputs cost the most margin, and where there is thermal headroom left.

R5d answers both from data the rating already computes. Its one new solve is the full rating of a failing case (§4, decision 5).

## 2. Goals, non-goals, anti-goals

Goals:
- A Thermal tab on evaluated cases (desktop and 375 px).
- The full rating stored with each evaluation, plus the rated-set temperature fields in the cache.
- Result chips that describe the rating instead of `j_limit`.
- A Thermal section in the run report (R3b).
- Options-graph axes: rated continuous kW/kg, rated peak kW/kg, rated continuous kW/L, rated peak kW/L.
- The evaluate time estimate counts the strokes and thermal steps.

Non-goals:
- Computing what a design change buys ("end spray −22 K"). That is the R6 what-if tab. End spray, shaft oil and slot
  oil are refused today (`MissingCoolingData`), and a cooling change needs new stroke solves (R6 reuse is open).
- Editing cooling on an evaluated case. Cooling is a case input; changing it makes a new draft case, as today.
- Any change to srmcore, map numbers or rating numbers.

Anti-goals (a failure even if it works):
- A screen that hides which limit binds, or shows a rated number without the requirement next to it.
- Calling budget shares "levers". They are input uncertainties, not design changes.
- A temperature map that suggests the end winding is in the section (it is a lumped node).

## 3. Approaches (owner picked 1, 2026-11-21)

How the tab gets its temperature maps (everything else is stored data):

| | How | Trade-off |
|---|---|---|
| **1. Store at evaluate (chosen)** | `rate` returns the rated-set temperature fields it already solves; the evaluate job writes them with the thermal mesh as one npz in the cache | Tab opens instantly; clearing the cache drops the maps (tab says "re-evaluate to see the map"); numbers stay in SQLite |
| 2. Re-solve on demand | A quick-lane job rebuilds the thermal context and solves one speed | Nothing new stored, but needs the stroke cache and the full thermal setup: tens of seconds to minutes per speed, impossible after a cache clear |
| 3. Fields in SQLite | As 1, but JSON in the result | Bloats the database by several MB per case and slows case lists |

Approach 1 matches how strokes and field frames are cached today.

## 4. Decisions (owner, 2026-11-21)

1. The tab diagnoses: what limits the design, and how to make it better.
2. Show only. Levers that need new solves are R6.
3. Temperature maps are stored at evaluate time (approach 1).
4. **kW/L volume** = π/4 × stator OD² × (stack length + 2 × end-winding overhang). The overhang per end is the
   axial extent of the coil end, taken from the same coil model as the end-winding inductance:
   `maps.end_winding.coil_geometry(machine).build + machine.slot_liner_thickness`. No housing (its dimensions are
   placeholders).
5. **Failing designs (option B):** a single-case evaluate whose windings all fail the thermal check still rates
   `ranked[0]` in full, so the tab shows the same views for a failing case (curves, map, uncertainties), with the ✗
   verdict from its `RequirementCheck`. The evaluation stays infeasible and its rated kW/kg do not enter any Pareto
   front. Search jobs do not: a failing candidate stores its `RequirementCheck` only, and its tab shows the failing
   speed, reason, hot spot at the required torque and the speeds that passed. Cost: one extra rating (minutes) on
   case evaluates that fail; search time unchanged. This is the one place R5d adds a solve; §1's "no new solves"
   holds for everything else.

## 5. What the tab shows

### 5.1 Facts from the code that shape it (checked 2026-11-21)

- The hot spot is the maximum over coil nodes and the end-winding lumps (`thermal_network.py`, `hot_spot=True` on
  end lumps). It is never the rotor. The rotor temperature is its own number (`SpeedRating.rotor_c`).
- Rotor stress is one check at `OVERSPEED` × max speed (`rotor_stress`), giving a safety factor and
  `speed_limit_rpm`. It never limits torque at a rated speed.
- Per speed, the continuous torque is thermally bound when it is below `envelope_nm`, EM bound when it equals it
  (`rate_speed`); the same holds for peak. In the 8/6 fixture the peak is EM bound at every speed.
- `shares` are the hot-spot rise in K when one budget row moves to its unfavourable end, at the rated continuous
  torque. Rows `thermal_mesh` and `end_winding_model` have zero width today.

### 5.2 Layout (desktop)

```
Thermal · rated (every input at its unfavourable end) · class H, limit 160 °C
✗ Short at 6000 r/min: continuous 31 of 34 N·m (−9 %) · binds: heat, slot winding
Speed  | Need cont/peak | Cont | Peak | Binds cont/peak | Hot spot             | Rotor
2000   | 40 / 120       | 48   | 120  | heat / EM       | end winding 160 °C   | 92 °C
6000   | 34 / 70        | 31   | 70   | heat / EM       | slot winding 159 °C  | 118 °C
...
[ Torque vs speed: continuous and peak, nominal→rated band, requirement ]
[ Temperature map @ [6000 ▾] · steady | peak end ]   [ Biggest uncertainties, K (tornado) ]
Rotor: SF 1.9 at 1.2 × max speed · speed limit 13 400 r/min · gap closure 0.09 of 0.40 mm (0.30 mm: …)
Cooling: jacket, 9 L/min water-glycol at 65 °C (placeholder)
▸ Notes (n)
```

- **Verdict line:** from the stored `RequirementCheck` (builder's call, §14), not from comparing rated numbers:
  `rate_speed` returns the feasible end of a 1 % bracket, so a rated torque can sit just below the requirement on a
  design whose check held. ✓ when the check held, with the smallest margin (rated over required, in %) and its
  speed; ✗ with the failing speed and reason (`NO_STROKE` or `HOT_SPOT_ABOVE`), the hot spot at the required
  torque and what binds.
- **Table:** one row per rated speed (base speed plus the n speeds). "Need" from `required_torques`; "–" for
  continuous when no continuous power is required. Binds: "heat" or "EM". At an EM-bound speed the hot-spot cell
  also shows the headroom in K to the limit (a lever that needs no solve: more current or turns would help there).
  Hot-spot locations in plain words ("slot winding, phase A", "end winding").
- **Curves:** continuous and peak torque against speed, nominal and rated as a band, the requirement as a dashed
  line. Plotly, the shared `plotTheme`, no blue.
- **Temperature map:** the stored rated-set field, inferno, °C, outlines of iron and coils. A speed picker defaults
  to the speed with the least margin; a toggle switches steady continuous / end of peak. When the hot spot is an
  end winding, a caption says "hot spot: end winding (lumped, not in this section)" with its °C.
- **Biggest uncertainties:** a one-sided tornado of `shares` (K) at the speed chosen in the map picker (builder's
  call, §14), largest first, rows with zero width left out, a row stored as `BIG_K` (a runaway) shown as a
  labelled "runaway" bar outside the scale,
  `em_torque` kept but labelled "EM torque uncertainty". Plain-word labels per row (liner conductivity, contact gap,
  iron loss band, cooling h, winding conductivity, …). Under it, one rule-based hint for the top row (e.g. "liner
  dominates: a measured liner conductivity or a higher-k liner buys the most margin"); hints live in srmapp, like
  `report.py` findings.
- **Rotor line:** safety factor, check speed, speed limit, stress status in words when not `ok`
  (`no_fillet`, `kt_out_of_range`, …); gap closure for the four `GapClosure` cases against the design's air gap and
  against 0.3 mm (owner, small gaps acceptable).
- **Cooling line:** the `CoolingSetup` summary, "(placeholder)" while `placeholder` is true.
- **Notes:** `Rating.notes` and per-speed notes, collapsed.

### 5.3 Layout (375 px)

Verdict line first. Table with Speed, Cont, Peak, Binds only, the speed column locked; tapping a row opens its
need, hot spot, headroom and rotor temperature. Curves, map and tornado stacked full width. Rotor, cooling and notes
collapsed.

### 5.4 States

- **Not rated** (thermal off, a refusal, or no EM-feasible winding): the tab shows the reason from the evaluation
  notes and nothing else.
- **Failed the check, search candidate** (decision 5): verdict ✗ from the stored `RequirementCheck`, the failing
  speed, reason and hot spot at the required torque, the speeds that passed, and "Make a case and Evaluate for the
  full rating".
- **Rated before R5d** (R5c evaluations, stored as the summary only): table from the summary; curves without the
  nominal band if absent; verdict, map, tornado, rotor and cooling replaced by "Edit, then Evaluate, for full
  detail" (an evaluated case is read-only; Edit makes the draft to evaluate).
- **Map file missing** (cache cleared): the map panel says "re-evaluate to see the map"; everything else shows.

## 6. Chips

Replace "Peak only · assumes j_limit N A/mm²" on rated evaluations with:
- "Rated · class H 160 °C" or "Not thermally rated" (unrated and pre-R5c evaluations keep the j_limit chip text
  they have today, followed by "Not thermally rated").
- "Cooling: jacket (placeholder)" (the cooling kind; "(placeholder)" while `placeholder`).
- "Iron ×3.2–7.0 band" from `srmapp.cooling.k_iron_hi` at the rated speeds' frequencies (the parent spec's ×2.0 is
  superseded by the Kiyota curve, 2026-11-18).

## 7. Run report (R3b)

A Thermal section with static content: verdict, full table, curves, one map (the least-margin speed, steady), the
uncertainties as a table (not a chart), rotor and gap, cooling, notes. "Not run" when the case has no rating, and the
"re-evaluate" texts of §5.4. The map uses the same offscreen render path as the field frames.

## 8. Options graph and tables

- `web/src/lib/candidates.ts` `AXES` gains "Rated continuous (kW/kg)", "Rated peak (kW/kg)", "Rated continuous
  (kW/L)", "Rated peak (kW/L)". Default axes become rated continuous kW/kg (y) against rated peak kW/kg (x), the
  axes the Pareto front is computed on; unrated rows are left out of those axes with a count in the legend.
- The candidate and case tables gain the same four columns.
- `Evaluation` gains `active_volume_l` (decision 4) and `rated_continuous_kw_per_l`, `rated_peak_kw_per_l`. The
  volume helper lives beside `active_mass` in `srmapp.sizing.estimates`.

## 9. Data stored

In SQLite (the evaluation JSON), replacing `serialize.rating_summary` with the full rating:
- Per speed, nominal and rated: `rpm`, `envelope_nm`, `continuous_nm`, `peak_nm`, both hot spots (°C and
  location), `rotor_c`, `rotor_peak_c`, `bore_c`, `bore_peak_c`, `start_nm`, `note`, and the required continuous
  and peak torques.
- `shares` (row, rpm, K), `gap` (the four cases with the air gap), `stress` (status, safety factor, governing part,
  speed limit, check speed, note), `torque_factor`, `limit_c`, `insulation_class`, a cooling summary with its
  `placeholder` flag, `notes`, `srmapp_version`.
- `RatingOut` and `SpeedRatingOut` grow to match; every new field optional so R5c evaluations still load.

Also stored: the `RequirementCheck` of every checked winding (holds, failing speed, reason, hot spots at the
required torques), so the verdict and the failing view need no solve.

In the cache, one npz per rated evaluation under `<cache_dir>/thermal/`, keyed by the job id that produced it plus
the evaluation id (`Evaluation.id` is the design hash for search candidates, so the id alone is not unique across
searches); the stored evaluation records the key (builder's call, §14). The search job writes one per rated
candidate as well as the evaluate job, so a case made from a candidate has its map: the thermal-domain
nodes and triangles, the element kind per triangle, and per rated speed the steady continuous and end-of-peak node
temperatures (float32) plus lump temperatures. Rated set only. The cache size route counts it and the clear route
deletes it, like `strokes/`; `*.tmp.npz` handling as for fields.

`srmapp.thermal.rate` / `rate_context` return the fields (an optional output, so callers that do not want them
pay nothing). Rating numbers must not change: a test compares the R5c fixture's numbers before and after.

## 10. Evaluate estimate

The estimate cannot know in advance whether a case will fail its check; it counts one rating (the common case)
and says "longer if the design fails the thermal check" in its basis text.

`/api/cases/{id}/estimate` adds the strokes and thermal steps when the evaluation will be rated (`thermal` true):
the mean of recent recorded rating times for the preset (a new `rating_times` table, recorded from the job's
strokes-plus-thermal span), else `RATING_BUDGET_S[preset]` = measured × 1.25, measured on the LattePanda for the
8/6 at `screening` and `full` in the plan (the whole 8/6 screening rated evaluation took 629 s, so the screening
budget is under that).

## 11. Versions and layering

srmcore unchanged (no map, cache-key or engine change). srmapp 0.9.0 (`Evaluation` and `rate` outputs grow),
srmweb and `web/` 0.12.0. Layering unchanged: hints and volume in srmapp, serialization and routes in srmweb.

## 12. Done when

- The Thermal tab, chips, report section, axes and estimate are merged to main with CI green.
- Checked in the browser on a rated 8/6 case at desktop and 375 px, including the three states of §5.4.
- The rating-numbers-unchanged test passes; the estimate's rating budget is measured on the LattePanda.
- `docs/r5-thermal-results.md`, the Notion project doc and the tracker (R5d row and the estimate row) updated.

## 13. Left to the builder

- Plotly specifics, component split, test layout.
- Exact plain-word labels for budget rows and hot-spot locations, and the hint texts.
- npz layout details and how the evaluate job hands the fields to the cache.
- The route shape for the map (one route returning the binary field per speed and state, like `frames`).

## 14. Calls made after the builder check (2026-11-21, not yet seen by the owner)

- The verdict comes from the stored `RequirementCheck`, so solver tolerance never shows a passing design as short.
- Search jobs write the temperature npz for every rated candidate (about 1 to 2 MB each; a 24-design search about
  40 MB), so cases made from the Pareto front have maps. The npz key is job id plus evaluation id.
- The uncertainty tornado follows the map's speed picker; the run report uses the least-margin speed.
- kW/L for DXF cases uses the parametric `stator_outer_diameter` and coil model, as the mass and end winding do.
