"""M19 total core loss table as test-only data (not shipped in the library).

Source: EMERF, Lamination Steels 3rd ed., AK Steel Di-Max M-19, 0.014 in (29 gauge, 0.36 mm),
typical as-sheared total AC core loss, page 5 of the MIT OCW 6.685 problem set 3 excerpt
(docs/r3-sources.md section 2a). A representative subset of the table.
"""
from srmcore.materials.schema import LossData, LossPoint, Provenance

# W/kg, keyed by frequency in Hz, then peak B in T.
_TABLE = {
    50: {0.1: 0.0176, 0.4: 0.240, 0.7: 0.602, 1.0: 1.09, 1.2: 1.51, 1.5: 2.56},
    100: {0.1: 0.0375, 0.4: 0.555, 0.7: 1.43, 1.0: 2.61, 1.2: 3.63, 1.5: 6.11},
    200: {0.1: 0.0926, 0.4: 1.37, 0.7: 3.61, 1.0: 6.74, 1.2: 9.46, 1.5: 15.8},
    400: {0.1: 0.247, 0.4: 3.60, 0.7: 9.81, 1.0: 18.9, 1.2: 26.9, 1.5: 44.4},
    1000: {0.1: 1.02, 0.4: 14.0, 0.7: 39.1, 1.0: 80.0, 1.2: 120.0},
}
RESISTIVITY_OHM_M = 50e-8   # midpoint of the cited 45 to 55 uOhm cm (ASTM A677 typical, secondary source)


def m19_loss_data() -> LossData:
    points = tuple(LossPoint(b=b, f=float(f), w_per_kg=w) for f, row in _TABLE.items() for b, w in row.items())
    return LossData(
        points=points,
        provenance=Provenance(
            source="EMERF Lamination Steels 3rd ed., AK Steel Di-Max M-19 .014 in (29 ga), total core loss, "
                   "MIT OCW 6.685 ps03 data excerpt",
            page="5", date="2026-10-17", method="tabulated W/kg (subset)", typical=True),
        confidence="C",
        frequency_range=(50.0, 2000.0),
        conductivity=1.0 / RESISTIVITY_OHM_M,
        conductivity_source="ASTM A677 typical resistivity 45 to 55 uOhm cm, midpoint 50 (secondary, typical)",
    )
