# Cheatsheet — SRM core loss

## Decision rules
| Situation | Do | Why / source |
|---|---|---|
| Wide f and B range | variable K_e(f,B), α(B), constant K_h | constant coeffs deviate at high B and f (Ch2) |
| Non-sinusoidal B | harmonic sum with B_m=√(Br²+Bt²), or dB/dt-based terms | peak-B Steinmetz is wrong (Ch1, 2, 4) |
| Only stator-pole B(t) known | derive zones by sum/difference; rotor is bipolar | Ch1 |
| Need cheap whole-machine number, f ≥ 200 Hz | FIP (recalibrate C_e, C_h) | 1–4 % vs FEA, but 11 % at 100 Hz (Ch4) |
| Low speed | expect hysteresis > eddy | all papers |
| High speed / heavy load | expect eddy > hysteresis; crossover speed drops with saturation | Ch3 |
| Control changes (single pulse vs chopping) | recompute; loss trend vs speed differs | Ch1 |
| Using FE tools for lamination loss | state θ_h,max and method; uncertainty up to 0.4–3× vs B_harm | Ch3 |
| Thermal | iron loss + copper → thermal FE; stator carries ~77 % of iron loss | Ch2 |

## Numbers
| Item | Value |
|---|---|
| 50W470 | constant fit K_h 0.0287, α 1.61, K_e 0.00027; variable: K_h 0.0287; K_e 2.7e-4 (<1.5 T), 3.6e-4 (>1.5 T), −2e-6/50 Hz; α poly in B |
| M45G29 (<150 Hz) | k_h 5.1e-3, a 1, b 0.71, k_e 7.86e-5 |
| k_cir | 1–3 |
| θ_h | ~30° below knee, <20° at high B (use 20°) |
| Loss split 8/6 | stator yoke 53 %, stator teeth 24 %, rotor 23 % |
| Temperature model error | ≤ 10 %, simulation above test |
| Torrent model vs test | slightly low (no stray/rotational loss) |

## Tells and smells
- Loss ratio between methods far from 1 at high load → saturation/skin effect treated differently.
- Model matches only at one frequency → coefficients are secretly f-dependent.
- A model with no measurement behind it (Ch3, Ch4) → treat as relative, not absolute.

## For srm-designer (R3 losses)
Zone frequencies: stator poles f_base = n·Nr/60 (Ch1). Candidate path: per-element B(t) from the map's field frames → dB/dt → three-term loss (Ch1); validate against the Ch2/Ch3/Ch4 trends. Excess and rotational losses are the known gaps.
