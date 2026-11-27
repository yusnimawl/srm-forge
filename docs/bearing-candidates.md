# Bearing candidates for the bike motor (2026-11-27)

Owner choice (core spec §11, 2026-11-27). Web research of the makers' catalogues; each value is marked sourced (with its source) or inferred. The bearing-speed check of Bike motor v1 step 1 reads these limits.

Sources: SKF = SKF Super-precision bearings catalogue 13383_2 EN (skf.com media hub, https://cdn.skfmediahub.skf.com/api/public/0901d19680495562/pdf_preview_medium/Super-precision_bearings_catalogue_-_13383_2_EN_pdf_preview_medium.pdf, product table p.~192 ff., designation system p.196-198, Table 39 p.192). NSK = https://www.nsk.com/engineering/30bnr19htynsump3-apn.html (NSK page for 30BNR19HTYNSUMP3, NOT the exact designation). Distributor (fallback): https://www.skdin.com/products/productid-7005 CD/HCP4A.

| Item | SKF 7005 CD/HCP4A | NSK 30BNR19HTSUMP3 | SKF 7006 CD/HCP4A |
|---|---|---|---|
| Type | angular contact, 15 deg (sourced, SKF) | angular contact, 18 deg (sourced, NSK) | angular contact, 15 deg (sourced) |
| d x D x B mm | 25x47x12 (sourced) | 30x47x9 (sourced, YN variant page) | 30x55x13 (sourced) |
| Balls | Si3N4 hybrid, HC (sourced) | ceramic "H" (inferred; page does not state) | Si3N4 hybrid (sourced) |
| Cage | phenolic, outer-ring centred (sourced, SKF default; skdin agrees) | T = resin (inferred); page lists TYN, not stated | phenolic OR-centred (sourced, SKF default) |
| Precision | P4A = ISO class 4 (sourced) | P3 = ISO 4 dimensions, ISO 2 running (sourced) | P4A (sourced) |
| Mass kg | 0.07 | 0.043 | 0.095 (all sourced) |
| C / C0 kN | 9.56 / 5.2 | 7.90 / 3.90 | 14.3 / 8.0 (sourced) |
| Grease limit r/min | 43 000 | 32 000 | 38 000 |
| Oil-air limit r/min | 67 000 | 37 000 | 56 000 |
| Basis | single bearing, SKF "attainable", no preload suffix (sourced) | single bearing, limiting speed, page shows DB/DF preload EL/L/M (sourced) | as 7005 |
| Reference speed | not given | not given | not given |
| Grease | SKF LGLT 2 "proven" for spindles (sourced, generic) | 0.29 g/bearing; grease type not on page | as 7005 |

## Suffixes
SKF (sourced, catalogue p.196-198): CD = 15 deg high-capacity D design; H(C) = HC, Si3N4 balls (hybrid); P4A = ISO class 4 dimensions and running accuracy; "/HCP4A" read as HC + P4A.
NSK (inferred; no legend found): BNR19 = ROBUST 18 deg ultra-high-speed series; H = ceramic ball; T = resin cage; SU = single universal matching; M = medium preload; P3 = special class. Page found says "YN" after T; owner's designation lacks it, so confirm with NSK.

## Margin (r/min vs limit, single bearing)
- 7005: 20k = 47% grease, 30% oil-air; 24k = 56% / 36%. Good.
- 7006: 20k = 53% / 36%; 24k = 63% / 43%. Good.
- NSK: 20k = 63% / 54%; 24k = 75% / 65%. Adequate, thinnest margin.

## Notes
1. SKF Table 39 (sourced) speed factors for 2-bearing DB sets, 70..D series, preload A/B/C/D (extra light/light/moderate/heavy): 0.81/0.75/0.65/0.40; DF 0.77/0.72/0.61/0.36. Also 3 bearings TBT 0.70/0.63/0.49/0.25.
2. Set at B: 7005 grease 32 250 and oil-air 50 250; 7006 grease 28 500, oil-air 42 000: both still hold 24k. At C: 7006 grease 24 700, only 3% over 24k. At D (heavy): 7005 17 200 and 7006 15 200 fail even 20k on grease.
3. SKF oil-air values must be reduced for oil mist or jet (sourced); grease values assume suitable soft grease and good heat removal.
4. NSK set/preload speed factors not found; M preload set will be below 32 000 grease. NSK page is for the YN variant; speeds "limiting", cage-guidance dependent.
5. Motor use: shaft-end heat from rotor loss and a hybrid ball spin make light preload (A/B or EL/L) advisable; this is engineering judgment (inferred).
