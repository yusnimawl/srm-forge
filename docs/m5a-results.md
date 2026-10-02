# M5a results: mesh convergence and grid decisions

Data: `docs/m5a-data/`. The generated study report `docs/m5a-convergence.md` is overwritten by `examples/mesh_convergence.py report`, so the conclusions live here. Spec: `docs/superpowers/specs/2026-10-02-m5a-mesh-convergence-design.md`.

## Mesh presets

`screening` is unchanged. `full` is the screening knobs at `MeshSettings.scale` = 2^(-1/2); `reference` is the screening knobs at scale 0.25. The finest feasible convergence level on the 24/16 was level 4: level 5 (3.2 M nodes) paged on the 16 GB laptop.

Worst mesh error over the 4 designs (8/6, 12/8, 24/16 and a variant), against the extrapolated limit:

| preset | psi | torque (of peak) |
|---|---|---|
| screening | 0.46 % | 0.64 % |
| full | 0.25 % | 0.36 % |
| reference (level 4 scale) | 0.04 % | 0.09 % |

## Angle grid

The torque error of angle interpolation peaks at the pole corners, so the angle grid is clustered there. `GRID_SIZES` (angles, currents): `screening` (40, 8), `full` (48, 20), `reference` (120, 40).

| grid | dense-sweep angle-interpolation torque error (worst design) |
|---|---|
| old, 30 angles | 8.4 % |
| new, 48 angles | 0.68 % |

## Error split on the new `full` preset

Worst over the designs:

| source | error |
|---|---|
| angle grid only, torque | 0.31 % |
| current grid only, torque | 0.05 % |
| band noise, torque RMS | 0.47 % (12/8) |

## Held-out check

`fem_checks` on the new `full` maps (`docs/m5a-data/heldout.jsonl`): worst held-out torque 1.10 % of peak (24/16) at 64 samples, 0.40 % at 16 samples; worst held-out psi 0.12 %. The 16-sample default under-read the worst error by up to 2.8x.

## La

La is read at 5 % of I_max. At equal current `screening` and `full` agree to 0.05 %: the old 2.6-3.0 % screening La error was the definition (a fixed low current), not the mesh.

## 8/6 screening golden (I_max 20 A)

| quantity | before (12 x 8) | after (40 x 8, La at 5 % of I_max) |
|---|---|---|
| la | 0.031684 H | 0.032829 H |
| lu | 0.003581 H | 0.003583 H |
| la/lu | 8.847 | 9.164 |
| peak torque | 12.4247 N m | 12.4247 N m |
| psi_max | 0.320169 Wb | 0.320169 Wb |

Check statuses that changed: `coenergy_torque` warn to pass, `loop_energy` warn to pass, `iron_b_peak` pass to warn.

## Decisions

Owner approved the presets and the angle grid on 2026-10-02.

- Presets: screening knobs, `full` and `reference` as fixed scales of them (above).
- Angle grid: clustered at the pole corners; `GRID_SIZES` screening (40, 8), full (48, 20), reference (120, 40).
- Held-out limits: torque 1.7 % of peak (1.10 % measured x 1.5), 64 samples by default; psi 0.5 % unchanged.
- Fidelity check: La tolerance back to 3 %, same as the other key numbers (the 5 % allowance only covered the old definition).
- Provenance hashes the resolved mesh settings (`scale` included).

## Not done

- Adaptive `reference` preset (energy-error-driven refinement).
- Nested refinement (levels are independent meshes, not nested).
- P2 elements.

## srmapp before/after

Filled in by the controller after the after-run.
