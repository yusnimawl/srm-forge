# R3 — Losses and drive tail — Design Spec

Status: approved in chat 2026-10-18 (owner). Parent: `2026-10-12-roadmap-r1-r10-design.md` §3 R3. Core spec items: §1 (losses), §3 (fixed iron mesh for B(t)), §5 (reserved loss fields in the material data).

## 1. Goal

Efficiency at any operating point of an evaluated case, with copper loss (DC and AC) and iron loss from the field waveform in every iron element, and a drive model that lets the flux tail run past aligned. Done when the efficiency map renders on a case and the error against a measured published case (Materu 6/4) is reported with its uncertainty (§9).

## 2. Decisions (owner, 2026-10-18)

- Iron loss runs in a separate `losses` job on an evaluated case. Evaluate keeps today's cost.
- Winding temperature is a case input, default 120 °C, shown on every loss result until R5 computes it. (Today the copper loss uses a fixed 100 °C.)
- Check cases: the measured Materu/Krishnan 6/4 losses (primary), plus one published FEA iron-loss breakdown per region (cross-check; the owner picks from the candidates the literature search finds).
- Iron-loss model: Bertotti three-term on the waveform (hysteresis per reversal, classical eddy, excess), per element and per B component, coefficients fitted to sinusoidal catalogue data. Steinmetz/iGSE (weak on DC bias and minor loops) and Preisach/Jiles–Atherton (needs reversal-curve data nobody publishes for 10JNEX900) are rejected.
- Mechanical loss (friction, windage) is out of scope; results say "excludes friction and windage".
- Cloud for code and literature; the laptop for the Materu runs, the angle-convergence study and the visual check (roadmap §5).

## 3. Material loss data

- New optional `loss` block in the material JSON (the reserved field of core spec §5):
  - `points`: sinusoidal specific loss W/kg at (B peak T, f Hz);
  - `provenance` (source, page, method, date, `typical`);
  - `confidence` grade A/B/C with the same meaning as for B-H;
  - `frequency_range` and `b_range`, the measured ranges; every data point lies inside both.
- 10JNEX900 from the JFE curves in `docs/sources/materials/` (f2e-001 and f1e-002), traced with `tools/digitise_bh.py` or read from tables. M19 from a cited datasheet (for Materu); M19 ships no loss data (test fixture only; EMERF licence). Other materials stay without `loss`; a losses job on such a case is refused with the material named.
- `materials.loss` fits k_h, α (hysteresis k_h·f·B^α), k_e (excess) at load; k_c (classical) is computed from the conductivity and the thickness, σd²/12 per unit volume, not fitted. The fit is least squares on log loss, and the worst relative fit error is kept with the coefficients (`LossModel`). Points outside `frequency_range` are never extrapolated silently (§4).

## 4. Iron loss

`srmcore/post/iron_loss.py`, pure numpy, no solver imports.

- Input: B(t) per element over one rotor pole pitch, uniform in angle, both in-plane components. The stator elements are taken in the stator frame and the rotor elements in the rotor frame. The components are radial and tangential about the machine centre at the element centroid.
- Per component, then summed:
  - **Hysteresis:** the waveform is cut into reversals (turning points with a small hysteresis band against noise). Each half-cycle of swing ΔB adds ½·k_h·(ΔB/2)^α per period, so minor loops add their own share. A DC bias factor (1 + K_DC·|B_dc|^ALPHA_DC) on each loop, with B_dc its mean; K_DC = 1.4664, ALPHA_DC = 3.7955 (grade C). This term is flagged as the least certain.
  - **Classical eddy:** (σd²/12)·⟨(dB/dt)²⟩ with central differences on the periodic waveform.
  - **Excess:** k_e·⟨|dB/dt|^1.5⟩·C, with C the sinusoid normalisation so a sinusoid reproduces the fit.
- A period is flagged `beyond_fit_range` (the value is still reported) when: the fundamental or any harmonic carrying more than 5 % of the eddy loss sits above `frequency_range[1]`; or an element's peak |B| exceeds `b_range[1]`; or more than 5 % of the (area-weighted) loss comes from elements with peak |B| below `b_range[0]`.
- B is the lamination B: the FE B divided by the material's stacking factor.
- Rotor elements have their own period k·tau, not tau: the field in the rotor frame repeats after the symmetry angle k·tau of the field (3·tau for the 8/6, 2·tau for the 6/4, doubled if the winding polarity alternates), so the rotor waveforms are taken over k·tau and the rotor period is k·tau/omega. Stator elements are periodic over tau.
- Output: W per element, summed into stator pole, stator yoke, rotor pole, rotor yoke, with hysteresis, eddy and excess kept apart. The stacking factor and the stack length scale the 2D loss density to W.
- Region split: element regions come from the static mesh; pole and yoke are separated by the radius of the pole root.

## 5. Stroke fields

`srmcore/maps/stroke.py` `stroke_fields(static, design, angles, phase_currents, solver, workers)`:

- Solves at each angle of one rotor pole pitch with every phase carrying its current at that angle. The currents come from one phase's stroke shifted by τ/q per phase.
- Returns iron B per element (n_angles × n_iron × 2) and coil-region B per element, as plain arrays.
- Uses the fixed iron mesh (`mesh_at_angle`), so element ids are stable, and runs in the existing process pool. A non-converged point fails the stroke; there is no filling.
- Default 60 angles snapped to the band pitch. A fast test on the screening 8/6 checks the loss changes by less than 2 % at 120 angles; if it fails, the default rises until it holds.
- Cache: `<cache_dir>/strokes/<hash>.npz`, the hash from the map provenance, the stroke currents and the angle count. Re-running only the loss model (new coefficients) hits the cache.

## 6. Drive tail

`srmapp/drive/envelope.py`:

- A stroke may keep flux past aligned. It is valid when ψ is 0 (≤ 1 % of its peak, as today) before the phase's next turn-on. The simulation runs on the periodic map over one period from turn-on, so the tail sees the negative-torque region.
- Torque, work and RMS current count the whole stroke, tail included. The off-angle search range extends past aligned.
- This changes evaluations and search rankings. `srmapp` goes to 0.6.0, and stored evaluations keep their numbers with the version they were made with.

## 7. Copper loss and the efficiency map

`srmapp/losses.py`:

- **DC:** `series_resistance` at the case's `winding_temperature_c` (`Requirements.winding_temperature_c`, default 120 °C; the existing mean turn length already includes the end turns).
- **AC (wire mode only):**
  - Skin effect in each strand: the round-wire Bessel factor per current harmonic.
  - Proximity: P = π·l·d⁴·ω²·B²/(128·ρ) per strand per harmonic, with B the coil-region field from §5 averaged over each coil side.
  - In density mode (no wire) AC is not computed and the result says so.
- **Operating point:** for each (speed, torque) the stroke with the lowest copper loss that gives the torque. Search over on, off and the current limit on the envelope's grid.
- **Efficiency map:** speeds × torque levels below the envelope, default 6 × 5. η = P / (P + P_cu,DC + P_cu,AC + P_iron). Points between the grid are not interpolated in the stored result; the plot contours the computed points.
- **Uncertainty** on each loss result:
  - the material fit error;
  - the loss-data grade, A 0 %, B 10 %, C 25 % (provisional, as for B-H);
  - the angle-convergence check.
  - Rotational flux at the pole roots and the yoke is listed as unquantified.

## 8. Web

- Job kind `losses` on an evaluated case. Steps: queued, strokes, fields, losses, saved. `eta_s` during fields. Input: grid size (speeds, torque levels). An estimate from the field solve count and recent solve times.
- Result kind `losses` in the results table. The store has no schema change.
- **Losses tab:**
  - an efficiency contour over speed × torque with the envelope edge;
  - the loss split per point (copper DC, copper AC, iron per region) as a stacked bar;
  - B(t) of an element picked on the mesh.
- Chips: "Winding 120 °C", "Excludes friction and windage", and "Unvalidated" until the check passes.
- Losses join the case's key numbers when present.
- `winding_temperature_c` lives on `Requirements` and appears in the case limits form and in setup files through the requirements. The setup schema version does not change; older files import with the default.

## 9. Tests and done

- **Fast tests:**
  - **Fit:** a sinusoid at each data point reproduces the fitted W/kg within the stored fit error.
  - **Hysteresis:** a minor loop adds loss; a DC bias raises the hysteresis term.
  - **Eddy:** zero dB/dt gives zero eddy; doubling f quadruples the classical term.
  - **Range flag:** set beyond the fit range.
  - **Drive tail:**
    - never lowers the best torque at any speed against today's rule;
    - a tail that is not back to 0 before the next turn-on is invalid;
    - at low speed the result equals today's.
  - **Copper:** R(T) linear in T; AC → DC as f → 0; density mode skips AC.
  - **Stroke fields:** the phase-shift symmetry (B of phase B's pole equals phase A's shifted by τ/q) and the cache hit.
  - **Web:** the job steps, the result route, the 422 for a material without loss data, the setup round trip with the temperature, vitest for the tab.
- **Slow tests:** the angle convergence (§5) and the Materu check.
- **Check cases:**
  - Materu 6/4 measured core and copper loss against speed, with M19 loss data, at `reference`. The 2D flux deficit of M5d is reported beside the result, not tuned away.
  - One published FEA iron-loss breakdown per region as a cross-check.
  - Both go in `docs/r3-loss-results.md` with the error and the uncertainty.
- **Done when:**
  - the efficiency map renders on an 8/6 case with 10JNEX900;
  - the Materu comparison is reported with its error and uncertainty;
  - the visual check of the Losses tab passes.

## 10. Versions

srmcore, srmapp, srmweb and `web/` 0.6.0. `"0.6.0"` joins `VALIDATED_VERSIONS` only through the validation report, as for earlier versions. The drive-tail change goes in the release notes.

## 11. Out of scope

- Friction and windage.
- Converter losses (SiC/IGBT).
- Temperature-dependent B-H and loss data.
- Cut-edge degradation.
- Rotational loss measured data.
- Losses inside the search ranking (R7 decides how losses enter the ranking).
