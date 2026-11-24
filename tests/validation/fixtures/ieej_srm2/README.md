# IEEJ public-use SRM "SRM2" (SRM_HV), 18/12

Reference data for a cross-tool check of srmcore against the 2D FEA maps of IEEJ Technical Report 1589.
The machine definition is `tests/ieej_srm2.py`, the comparison script `examples/ieej_srm2_check.py`, the
slow test `tests/validation/test_ieej_srm2.py`, and the results `docs/ieej-srm2-results.md`.

## Source and terms

All five files are copied unchanged from the IEEJ portal "電磁界解析用 公開モータ情報" (public motors
for electromagnetic field analysis), pages *SRM_HV モータ情報* and *SRM_HV 解析結果*:
http://www2.iee.or.jp/~drm/PublicUseMotors/ (actualMotors/SRM/SRM_HV), downloaded 2026-11-22.

The portal's terms of service allow free use and redistribution of its digital data (csv, dxf) when the
source document or the portal URL is cited, and forbid altering the data in a misleading way. The portal's
figures and tables need IEEJ permission for secondary use, so none are copied here; the B-H curve of
10JNEX900 is published on the portal as a figure only.

- Machine: A. Chiba, K. Kiyota, N. Hoshi, M. Takemoto, S. Ogasawara, "Development of a rare-earth-free SR
  motor with high torque density for hybrid vehicles", IEEE Trans. Energy Convers. 30(1), 175–182, 2015,
  doi:10.1109/TEC.2014.2343962 (the portal's [REF2015]; "SRM2" in that paper).
- Maps: IEEJ Technical Report No. 1589 (2025), "High-precision modeling and advanced optimization of
  rotating machines by electromagnetic field analysis" (the portal's [CITE2025]).

Thanks to Raiden Numerics, whose mufem validation case
(https://github.com/Raiden-Numerics/mufem/tree/main/Validations/Electromagnetics/IEEJ_2025_Switched_Reluctance_Motor)
and LinkedIn post pointed us to this data. Their write-up first noted that the torque table is the
half-machine torque. No file of the mufem repository (CC BY-SA 4.0) is copied here.

## Files

| file | content | sha256 (first 12) |
|---|---|---|
| `SRM2_CAD.dxf` | cross-section drawing, mm, one block `SRM2_CAD`, rotor at the unaligned position of phase U | `d5eb9df8655a` |
| `SRM2_Flux-I.csv` | phase-U flux linkage (Wb), rows 0 to 250 A in 10 A steps, columns positions x = 10 to 20 | `2a70db990723` |
| `SRM2_T-position.csv` | torque (N m) on the same grid; the half-machine torque, see below | `990371b8e4ad` |
| `SRM2_torqueUVW.csv` | torque of U, V and W, each alone at 250 A DC, against x | `ca792357f7ec` |
| `SRM2_torque.csv` | torque with ideal rectangular currents, no overlap, at 250 A | `573cfdd6b15a` |

## Conventions

- Positions: x = 10 is unaligned and x = 20 aligned for phase U (torque zero at both ends, ψ rising from 10
  to 20). The 16 columns are 1° apart over half a rotor pole pitch (15°). srmcore angle (phase A aligned at
  0, motoring counter-clockwise) = 1.5 (x − 10) − 15°.
- Torque: the torque from the co-energy of `SRM2_Flux-I.csv` is 1.95 to 2.03 times `SRM2_T-position.csv`
  at the interior positions, so the table is taken as the torque of a half-machine model and doubled.
- Machine (portal spec table, SRM2 column): 18/12, 3 phases, OD 269 mm, axial length 155 mm, core length
  135 mm, 10JNEX900 0.1 mm, 17 turns per pole, DC bus 500 V.
- Geometry read off the drawing: rotor OD 178 mm, air gap 0.5 mm, stator slot bottom r = 116 mm (yoke
  18.5 mm), rotor slot bottom r = 70 mm, shaft r = 35 mm, stator pole half-arc 5.2285° at the bore with
  flanks at 10.000° to the pole axis, rotor pole half-arc 5.5138° at the rotor OD with flanks at 3.001°, no
  fillets, coil sides from r = 90.5 mm to the slot bottom against the pole flank.
- The drawing does not pass `srmcore.topology.dxf_io.read_loops` as it is (it is a partial section with
  construction circles, open contours on y = 0 and one duplicate edge), so `tests/ieej_srm2.py` builds the
  parametric equivalent.
