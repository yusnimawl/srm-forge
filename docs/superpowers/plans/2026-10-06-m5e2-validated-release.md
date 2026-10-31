# M5e2 Validated Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship srmcore 0.4.0 as the first "EM-validated" engine version. This takes six library materials, map identity in `MapResult`, measured speed budgets, a generated validation report, and a CI slow suite.

**Architecture:** Materials are JSON data files plus a reproducible tracing tool. Map identity is a design hash computed in a new `maps/identity.py`, stored on `MapResult` and in HDF5, and checked by `em_validate`. Every comparison script writes a JSON result into `docs/validation/`. `tools/validation_report.py` turns those files into `docs/validation-report.md` with a PASS / PENDING / FAIL verdict. GitHub Actions gets a trimmed push matrix and a tag-triggered slow workflow.

**Tech Stack:** Python 3.12+, numpy, scipy, pydantic, h5py, matplotlib, PyMuPDF (dev only, for the tracing tool), pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-05-m5e2-validated-release-design.md`

## Global Constraints

- Python ≥ 3.12; the fast suite (`python -m pytest -m "not slow"`) must stay under 10 min. Today it takes 9:52, so every new fast test must run in well under a second.
- Import rules (`tests/test_import_rules.py`): `maps` may import anything in srmcore. `materials` may import only `model`. `tools/` and `examples/` are not under the rule, but must not be imported by `src/`.
- SI units everywhere (A/m, T, kg/m³, m).
- Material records: every value without a source is listed in `provisional_fields`, and its `*_source` string contains `PROVISIONAL` (enforced by `tests/materials/test_material_library.py::test_provisional_fields_match_provisional_sources`).
- Comments describe the code as it is, with no task or plan history.
- **Hard rule for every implementer:** edit files only with the Edit/Write tools. Never rewrite a file with a shell script (sed, printf, heredoc redirection). Write your report to the report file named in your dispatch.
- Windows: any script that uses the process pool needs an `if __name__ == "__main__":` guard.
- `srmcore.materials` exports nothing. Import from `srmcore.materials.library`, `.schema` or `.bh`.
- Examples that import `conftest`, `femm_machines` or `krishnan_6_4` need `PYTHONPATH=tests`.

## Review Focus

1. **An HDF5 map file from 0.3.0 (no `design_hash`/`preset` attrs)**: `cached_map` must treat it as a miss and re-solve, not crash. Test in Task 2.
2. **A map of the right design but a different preset** (a screening map passed with the `full` design): `em_validate` must fail both `preset` and `map_identity`. Test in Task 2.
3. **An all-zero-torque map**: `em_validate` must return a failing `map_matches_design` check, not raise `ZeroDivisionError` or emit a numpy warning. Test in Task 2.
4. **A missing input JSON for the report** (for example `ci.json` not written yet): the report must render that row as "missing" and the verdict must not be PASS. The generator must not crash. Test in Task 4.
5. **A library material whose B-H data would fail `process_bh`** (non-monotone points, or Js below the last polarisation): it must be caught by the fast parametrized test, not first at solve time. Test in Task 1.

---

### Task 1: Material library adds

**Files:**
- Create: `src/srmcore/materials/data/10JNEX900.json`, `Hiperco50A.json`, `Hiperco50HS_720C.json`, `Hiperco50HS_740C.json`, `Hiperco50HS_760C.json`, `M43.json`
- Create: `docs/sources/materials/` (5 PDFs, copied from the session scratchpad)
- Create: `tools/digitise_bh.py`
- Modify: `pyproject.toml` (`dev` extra: add `"pymupdf>=1.24"`)
- Modify: `tests/materials/test_material_library.py`

**Interfaces:**
- Produces: `available_materials()` now also lists `10JNEX900`, `Hiperco50A`, `Hiperco50HS_720C`, `Hiperco50HS_740C`, `Hiperco50HS_760C`, `M43`. Task 4's report reads `confidence`, `provenance.source`, `saturation_polarisation`, `stacking_factor`, `digitisation_error` and `provisional_fields` from each record.

- [ ] **Step 1: Copy the source PDFs**

```powershell
$S = "C:\Users\<user>\AppData\Local\Temp\claude\D--y-srm-designer\57cd2d0a-19aa-4b6c-9986-9e77d5f072d6\scratchpad"
New-Item -ItemType Directory -Force docs\sources\materials
Copy-Item "$S\f2e-001.pdf" docs\sources\materials\jfe_f2e-001_magnetic_property_curves.pdf
Copy-Item "$S\f1e-002.pdf" docs\sources\materials\jfe_f1e-002_super_core.pdf
Copy-Item "$S\021-10.pdf"  docs\sources\materials\jfe_technical_report_21_p46_jnsf.pdf
Copy-Item "$S\h50a.pdf"    docs\sources\materials\carpenter_hiperco_50a_E199.pdf
Copy-Item "$S\hs.pdf"      docs\sources\materials\carpenter_hiperco_50hs_E198.pdf
```

If the scratchpad is gone, download them again:
- `https://www.jfe-steel.co.jp/en/products/electrical/catalog/f2e-001.pdf`
- `https://www.jfe-steel.co.jp/en/products/electrical/catalog/f1e-002.pdf`
- `https://www.jfe-steel.co.jp/en/research/report/021/pdf/021-10.pdf`
- `https://f.hubspotusercontent20.net/hubfs/7407327/carpenter_electrification/Resources/Datasheets/Hiperco_50A_Alloy_(E199).pdf`
- `https://www.carpenterelectrification.com/hubfs/Resources/Datasheets/Hiperco_50_HS_Alloy_(E198).pdf`

- [ ] **Step 2: Write the failing tests** (append to `tests/materials/test_material_library.py`)

```python
import numpy as np

from srmcore.materials.bh import process_bh

NEW = ("10JNEX900", "Hiperco50A", "Hiperco50HS_720C", "Hiperco50HS_740C", "Hiperco50HS_760C", "M43")


def test_m5e2_materials_are_in_the_library():
    assert set(NEW) <= set(available_materials())


@pytest.mark.parametrize("name", [n for n in available_materials() if n != "copper"])
def test_soft_magnetic_record_processes_and_reproduces_its_points(name):
    """Every soft-magnetic record passes the B-H pipeline and its fit goes through every data point."""
    m = load_material(name)
    curve, report = process_bh(m.bh, m.stacking_factor, m.saturation_polarisation)
    assert report.knot_max_relative_error < 1e-9
    b_eff = m.stacking_factor * np.asarray(m.bh.b) + (1 - m.stacking_factor) * 4e-7 * np.pi * np.asarray(m.bh.h)
    np.testing.assert_allclose(curve.h_of_b(b_eff), m.bh.h, rtol=1e-9)


@pytest.mark.parametrize("name", [n for n in available_materials() if n != "copper"])
def test_digitised_grade_b_records_state_their_digitisation_error(name):
    m = load_material(name)
    if m.confidence == "B":
        assert m.digitisation_error is not None and m.digitisation_error > 0


def test_m5e2_record_values():
    jnex = load_material("10JNEX900")
    assert (jnex.confidence, jnex.saturation_polarisation, jnex.stacking_factor, jnex.density) == ("B", 1.80, 0.90, 7490.0)
    assert jnex.digitisation_error == 0.025 and len(jnex.bh.h) == 32 and jnex.thickness == 0.0001
    a = load_material("Hiperco50A")
    assert (a.confidence, a.saturation_polarisation, a.digitisation_error) == ("B", 2.40, 0.015)
    assert a.bh.b[-6:] == (2.12, 2.19, 2.23, 2.27, 2.28, 2.30)
    assert "stacking_factor" in a.provisional_fields
    rows = {"720C": (1.82, 1.99, 2.15, 2.23, 2.29), "740C": (1.90, 2.03, 2.18, 2.23, 2.29),
            "760C": (1.93, 2.07, 2.19, 2.23, 2.30)}
    for suffix, b in rows.items():
        hs = load_material(f"Hiperco50HS_{suffix}")
        assert hs.confidence == "C" and hs.bh.h == (800.0, 1600.0, 4000.0, 8000.0, 16000.0) and hs.bh.b == b
        assert "no data below 800 A/m" in hs.provenance.source
    m43 = load_material("M43")
    assert m43.confidence == "C" and len(m43.bh.h) == 47 and m43.stacking_factor == 0.98
```

The two parametrized tests replace nothing; they run once per material (9 records, milliseconds each).

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/materials/test_material_library.py -v`
Expected: `test_m5e2_materials_are_in_the_library` and `test_m5e2_record_values` FAIL (`KeyError: unknown material`). The parametrized tests pass for M19 and steel_1010.

- [ ] **Step 4: Write the six JSON records**

Follow the `M19.json` layout exactly (`kind`, `name`, `grade`, `variant`, `thickness`, `provenance`, `confidence`, `bh`, `stacking_factor`, `stacking_factor_source`, `saturation_polarisation`, `saturation_polarisation_source`, `density`, `density_source`, optional `digitisation_error`, `provisional_fields`). `name` must equal the file stem.

`10JNEX900.json`:
```json
{
  "kind": "soft_magnetic",
  "name": "10JNEX900",
  "grade": "10JNEX900",
  "variant": "JFE Super Core JNEX, 6.5 % Si, as-sheared",
  "thickness": 0.0001,
  "provenance": {
    "source": "JFE Technical Report No. 21 (Mar. 2016) p. 46, Fig. 1 'Direct current magnetization curve', dashed 10JNEX900 curve, pixel-traced with tools/digitise_bh.py from docs/sources/materials/jfe_technical_report_21_p46_jnsf.pdf; 32 points log-spaced from 8 A/m to 20 kA/m (the traced curve above 20 kA/m is flatter than mu0 and is left to the saturation tail). Reads 2 % below the JFE catalogue table (B8 1.261 vs 1.29 T, B25 1.375 vs 1.40 T; f1e-002 p. 4); the 50 Hz catalogue curve (f2e-001 p. 9, 0.5-1.4 T) agrees to 0.0007 T on average.",
    "page": "46",
    "date": "2016-03",
    "method": "DC magnetization curve (published figure)",
    "typical": true
  },
  "confidence": "B",
  "bh": {
    "h": [8.0, 10.3, 13.25, 17.06, 21.96, 28.26, 36.37, 46.81, 60.25, 77.55, 99.82, 128.47, 165.36, 212.83, 273.93, 352.58, 453.8, 584.09, 751.77, 967.61, 1245.4, 1602.95, 2063.15, 2655.48, 3417.85, 4399.1, 5662.07, 7287.63, 9379.88, 12072.8, 15538.86, 20000.0],
    "b": [0.0506, 0.0837, 0.1516, 0.2919, 0.5077, 0.7685, 0.9027, 0.9995, 1.0572, 1.0964, 1.1258, 1.1458, 1.1652, 1.1822, 1.1961, 1.2102, 1.2245, 1.2389, 1.2565, 1.2749, 1.2941, 1.3181, 1.3457, 1.3847, 1.4222, 1.4696, 1.5228, 1.5777, 1.6383, 1.6896, 1.7392, 1.7664]
  },
  "stacking_factor": 0.90,
  "stacking_factor_source": "JFE catalogue f1e-002, product dimensions table: space factor 90 % or more (guaranteed minimum used)",
  "saturation_polarisation": 1.80,
  "saturation_polarisation_source": "JFE catalogue f1e-002 p. 4, sample characteristics table, saturation magnetization 1.80 T",
  "density": 7490.0,
  "density_source": "JFE catalogue f1e-002, product dimensions table, 7.49 g/cm3",
  "digitisation_error": 0.025,
  "provisional_fields": []
}
```

`Hiperco50A.json`: as above, with these values:
- `grade`: `"Hiperco 50A"`
- `variant`: `"0.014 in (0.355 mm) strip, standard magnetic anneal"`
- `thickness`: `0.000355`
- `provenance.source`: `"Carpenter Electrification datasheet Hiperco 50A (E199, v05-20), docs/sources/materials/carpenter_hiperco_50a_E199.pdf: p. 3 DC properties table, 0.014 in strip, standard magnetic anneal (400-16000 A/m); below 400 A/m the four nodes of the p. 4 'Low field DC B v H' H50A curve, read exactly from the PDF vector path with tools/digitise_bh.py (the chart's axis says kA/m but the table shows it is A/m). Chart and table agree within 1.5 %."`
- `provenance.annealed`: `true`; `provenance.anneal_recipe`: `"Carpenter standard magnetic anneal"`; `provenance.typical`: `true`; `provenance.method`: `"ASTM A596 ring, DC"`
- `confidence`: `"B"`
- `bh.h`: `[20.7, 36.5, 51.9, 99.85, 400.0, 800.0, 1600.0, 4000.0, 8000.0, 16000.0]`
- `bh.b`: `[0.128, 0.766, 1.417, 1.766, 2.12, 2.19, 2.23, 2.27, 2.28, 2.30]`
- `stacking_factor`: `0.95`; `stacking_factor_source`: `"PROVISIONAL: the Carpenter datasheet gives no stacking factor; 0.95 is a placeholder until the lamination supplier states one"`
- `saturation_polarisation`: `2.40`; source: `"Carpenter E199 p. 1: magnetic saturation 24 kilogauss"`
- `density`: `8110.0`; source: `"Carpenter E199 p. 2: 8.11 g/cm3"`
- `digitisation_error`: `0.015`
- `provisional_fields`: `["stacking_factor"]`

`Hiperco50HS_720C.json`, `Hiperco50HS_740C.json`, `Hiperco50HS_760C.json`: same layout. Per file:

| file | `variant` | `anneal_recipe` | `bh.b` |
|---|---|---|---|
| `_720C` | `"annealed 720 C / 1 h, yield 99 ksi (683 MPa)"` | `"720 C (1328 F) 1 h, dry hydrogen, cool 100 C/h"` | `[1.82, 1.99, 2.15, 2.23, 2.29]` |
| `_740C` | `"annealed 740 C / 1 h, yield 86 ksi (593 MPa)"` | `"740 C (1364 F) 1 h, dry hydrogen, cool 100 C/h"` | `[1.90, 2.03, 2.18, 2.23, 2.29]` |
| `_760C` | `"annealed 760 C / 4 h, yield 73 ksi (503 MPa)"` | `"760 C (1400 F) 4 h, dry hydrogen, cool 100 C/h"` | `[1.93, 2.07, 2.19, 2.23, 2.30]` |

Common to the three: `grade` `"Hiperco 50HS"`; `thickness` `0.000152`; `bh.h` `[800.0, 1600.0, 4000.0, 8000.0, 16000.0]`; `confidence` `"C"`; `provenance.annealed` `true`; `provenance.typical` `true`; `provenance.method` `"ASTM A596 ring, DC"`; `provenance.source`: `"Carpenter Electrification datasheet Hiperco 50 HS (E198, v05-20) p. 4 typical DC table, docs/sources/materials/carpenter_hiperco_50hs_E198.pdf. Grade C: no data below 800 A/m, so the curve below 800 A/m is the B-H pipeline's interpolation from the origin; no unannealed state (cold-rolled 50HS must be annealed, Carpenter: 704-760 C, before it is magnetically usable)."`; stacking `0.95` provisional (same source text as Hiperco 50A); Js `2.40` (source `"Carpenter E198 p. 1: magnetic saturation 24 kilogauss"`); density `8110.0` (source `"Carpenter E198 p. 2: 8.11 g/cm3"`); no `digitisation_error`; `provisional_fields` `["stacking_factor"]`.

`M43.json`: copy the `M19.json` layout. Use `grade` `"M43"`, `variant` `"FEMM library curve"`, `thickness` `0.000635`, and the 47 points of the FEMM matlib block `"M-43 Steel"` (file `C:\femm42\bin\matlib.dat`, the block starting at the line `<BlockName> = "M-43 Steel"`; `LamFill` 0.98). Write the H values from FEMM's second column, rounded to 6 decimals, and B = 0.0, 0.05, …, 2.30:

```
h = [0.0, 22.815826, 34.292324, 41.691795, 47.276539, 51.943273, 56.12413, 60.058389, 63.894412, 67.734109, 71.654737, 75.720755, 79.991002, 84.523665, 89.380327, 94.629948, 100.353469, 106.649919, 113.645209, 121.505665, 130.459825, 140.835022, 153.121088, 168.08529, 186.986958, 211.991513, 246.99228, 299.274213, 382.882838, 525.155143, 777.592798, 1226.457096, 1979.929758, 3105.52556, 4589.182657, 6410.967497, 8681.339496, 11524.478784, 15121.416504, 19833.366747, 26795.523692, 40064.363461, 66950.843428, 103339.791774, 141054.369267, 181684.219043, 223103.57263]
```

`provenance.source`: `"FEMM 4.2 material library matlib.dat, block \"M-43 Steel\" (47 BH points; d_lam 0.635 mm). Typical catalogue curve; points above about 2.0 T are FEMM's own extrapolation, not measurements."`, `typical` true; `confidence` `"C"`; `stacking_factor` 0.98 with source `"FEMM matlib \"M-43 Steel\" LamFill"`; Js `2.03` with source `"PROVISIONAL: typical room-temperature value for Fe-Si non-oriented steel (Bozorth, Ferromagnetism, 1951); replace with the supplier value (spec §10)"`; density `7650.0` with source `"PROVISIONAL: typical non-oriented Fe-Si value, not checked against a datasheet (spec §10)"`; `provisional_fields` `["saturation_polarisation", "density"]`.

- [ ] **Step 5: Write `tools/digitise_bh.py`** (reproduces the two traced or read curves from the committed PDFs)

```python
r"""Reproduce the traced B-H points of the library records that come from published figures.

  10JNEX900  : dashed curve of JFE Technical Report 21 p. 46 Fig. 1, traced from an 800 dpi render
  Hiperco50A : low-field nodes of the H50A curve on p. 4 of Carpenter E199, read from the PDF vector path

Usage: python tools\digitise_bh.py   (needs the dev extra: PyMuPDF)
"""
import json
from pathlib import Path

import numpy as np
import pymupdf
from scipy import ndimage
from scipy.signal import medfilt

SOURCES = Path(__file__).resolve().parents[1] / "docs" / "sources" / "materials"


def jnex_dc_curve() -> tuple[list[float], list[float]]:
    """32 points, log-spaced 8 A/m to 20 kA/m. Axis calibration (pixels of the 800 dpi clip): the H decades
    10 / 100 / 1000 / 10000 A/m at x = 945.5 + 452.67 k; the B gridlines 0.5 T apart at y = 1408.5 - 624.6 (B - 0.5).
    The dashes are the small connected components; the solid JNSF curve is one large component."""
    page = pymupdf.open(SOURCES / "jfe_technical_report_21_p46_jnsf.pdf")[0]
    w, h = page.rect.width, page.rect.height
    pix = page.get_pixmap(dpi=800, clip=pymupdf.Rect(0.06 * w, 0.63 * h, 0.48 * w, 0.87 * h))
    dark = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].max(axis=2) < 110
    x10, dec = 945.5, 452.67
    b_of = lambda y: (1720.8 - y) / 624.6
    h_of = lambda x: 10 ** (1 + (x - x10) / dec)
    x_of = lambda hh: x10 + dec * (np.log10(hh) - 1)
    y_of = lambda bb: 1720.8 - 624.6 * bb
    dark[:, :515] = dark[:, 2605:] = False
    dark[:170] = dark[1703:] = False
    dark[int(y_of(1.95)):int(y_of(1.5)), int(x_of(3)):int(x_of(500))] = False       # "6.5% Si Steel" label
    dark[int(y_of(2.3)):int(y_of(1.81)), int(x_of(400)):int(x_of(25000))] = False   # "New material" label
    lab, n = ndimage.label(dark, structure=np.ones((3, 3)))
    sizes = ndimage.sum(dark, lab, range(1, n + 1))
    keep = np.zeros(n + 1, bool)
    for i, (s, z) in enumerate(zip(ndimage.find_objects(lab), sizes), 1):
        if 150 < z < 4000 and max(s[0].stop - s[0].start, s[1].stop - s[1].start) < 90:
            keep[i] = True
    dash = keep[lab]
    pts = []
    for x in range(515, 2605):
        ys = np.nonzero(dash[:, x])[0]
        if len(ys) and ys.max() - ys.min() <= 40:
            pts.append((h_of(x), b_of(ys.mean())))
    hh, bb = np.array(pts).T
    ok = np.abs(bb - medfilt(bb, 31)) < 0.02
    lh, bb = np.log10(hh[ok]), bb[ok]
    grid = np.logspace(np.log10(8), np.log10(20000), 32)
    b = np.interp(np.log10(grid), lh, bb)
    return [round(float(v), 2) for v in grid], [round(float(v), 4) for v in b]


def hiperco_50a_low_field() -> tuple[list[float], list[float]]:
    """Bezier nodes of the H50A (red, dashed in the legend) curve on p. 4; axis 0-100 A/m from x = 60.71 to
    294.83 pt, 0-2 T from y = 381.07 to 223.92 pt. The first node (H = 0) is the origin and is dropped."""
    page = pymupdf.open(SOURCES / "carpenter_hiperco_50a_E199.pdf")[3]
    for d in page.get_drawings():
        c = d.get("color")
        if c and c[0] > 0.85 and c[1] < 0.05 and len(d["items"]) == 4 and d["rect"].y1 < 400:
            nodes = sorted({(round(p.x, 2), round(p.y, 2)) for it in d["items"] for p in (it[1], it[-1])})
            h = [round((x - 60.71) / (294.83 - 60.71) * 100, 2) for x, _ in nodes[1:]]
            b = [round((381.07 - y) / (381.07 - 223.92) * 2, 3) for _, y in nodes[1:]]
            return h, b
    raise RuntimeError("H50A curve not found on p. 4")


if __name__ == "__main__":
    print(json.dumps({"10JNEX900": jnex_dc_curve(), "Hiperco50A_low_field": hiperco_50a_low_field()}, indent=1))
```

- [ ] **Step 6: Add PyMuPDF to the dev extra and run the tool**

In `pyproject.toml`: `dev = ["pytest>=8.0", "hypothesis>=6.100", "pymupdf>=1.24"]`.

Run: `.venv\Scripts\python tools\digitise_bh.py`
Expected: `10JNEX900` h and b equal the JSON record's values, or differ in the last digit at most (pixel rounding). The Hiperco 50A low-field nodes ≈ h `[20.7, 36.5, 51.9, 99.85]`, b `[0.128, 0.766, 1.417, 1.766]`, within ±0.01 in h and ±0.002 in b. If a value differs more than that, report it; do **not** change the JSON to match without saying so in the report.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/materials -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add src/srmcore/materials/data docs/sources/materials tools/digitise_bh.py pyproject.toml tests/materials/test_material_library.py
git commit -m "feat: library adds 10JNEX900, Hiperco 50A, Hiperco 50HS (720/740/760 C), M43"
```

---

### Task 2: Map identity in `MapResult` and `em_validate`

**Files:**
- Create: `src/srmcore/maps/identity.py`
- Modify: `src/srmcore/maps/run.py` (`MapResult`, `run_map`)
- Modify: `src/srmcore/maps/dataset.py` (`provenance`, `write_map`, `read_map`)
- Modify: `src/srmcore/maps/validation.py` (`em_validate`)
- Test: `tests/maps/test_identity.py` (new), `tests/maps/test_dataset.py`, `tests/maps/test_em_validation.py`

**Interfaces:**
- Produces: `srmcore.maps.identity.design_hash(design: Design) -> str` (16 hex chars). `MapResult.design_hash: str = ""` and `MapResult.preset: str = ""` (the last two fields, after `complete`). An em_validate check named `"map_identity"`.
- Consumes: nothing from Task 1.

- [ ] **Step 1: Write the failing identity test** (`tests/maps/test_identity.py`)

```python
from conftest import make_8_6
from srmcore.maps.identity import design_hash
from srmcore.model.design import Design, MeshSettings, RegionMaterials

D = Design(machine=make_8_6(), mesh=MeshSettings(preset="full"))


def test_design_hash_is_stable_and_short():
    assert design_hash(D) == design_hash(Design.model_validate_json(D.to_json()))
    assert len(design_hash(D)) == 16


def test_design_hash_changes_with_geometry_preset_and_material():
    base = design_hash(D)
    assert design_hash(D.model_copy(update={"machine": D.machine.model_copy(update={"air_gap": 0.00041})})) != base
    assert design_hash(D.model_copy(update={"mesh": MeshSettings(preset="screening")})) != base
    other = D.machine.model_copy(update={"materials": RegionMaterials(stator="M43", rotor="M43")})
    assert design_hash(D.model_copy(update={"machine": other})) != base
```

(The material case needs Task 1's `M43`. If Task 2 runs first, use `steel_1010` instead.)

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/maps/test_identity.py -v`
Expected: FAIL, `ModuleNotFoundError: srmcore.maps.identity`.

- [ ] **Step 3: Create `src/srmcore/maps/identity.py`, and make `provenance` use it**

```python
"""What identifies the design a map was solved for: the design JSON, its resolved mesh settings and the bytes of
its material files. The map provenance adds the grids, excitation, solver and versions on top."""
import dataclasses
import hashlib
import json

from ..materials import library
from ..mesh.settings import resolve_mesh_settings
from ..model.design import Design


def design_parts(design: Design) -> dict:
    mesh_resolved = json.loads(json.dumps(dataclasses.asdict(resolve_mesh_settings(design.machine, design.mesh))))
    names = sorted(set(design.machine.materials.model_dump().values()))
    materials = {n: hashlib.sha256((library._data_dir() / f"{n}.json").read_bytes()).hexdigest() for n in names}
    return {"design": json.loads(design.to_json()), "mesh_resolved": mesh_resolved, "materials": materials}


def design_hash(design: Design) -> str:
    return hashlib.sha256(json.dumps(design_parts(design), sort_keys=True).encode()).hexdigest()[:16]
```

In `dataset.py` `provenance`, replace the three local computations (`mesh_resolved`, `names`, `materials`) with `parts = design_parts(design)` and build the dict as `{"srmcore": ..., "libraries": ..., **parts, "angles": ..., ...}`. The keys and values must stay identical: `test_dataset.py`'s provenance tests must still pass unchanged. Remove the imports that become unused (`dataclasses`, `library`, `resolve_mesh_settings`), but only if nothing else in `dataset.py` uses them.

- [ ] **Step 4: Run the identity and dataset tests**

Run: `.venv\Scripts\python -m pytest tests/maps/test_identity.py tests/maps/test_dataset.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing `MapResult`, run and dataset tests**

In `tests/maps/test_dataset.py`, extend `_result` to set the new fields, and add an old-file test:

```python
def _result(complete=True):
    rng = np.random.default_rng(0)
    return MapResult(
        ANGLES, CURRENTS, ("A", "B", "C", "D"), "A", rng.random((3, 2, 4)), rng.random((3, 2)),
        rng.random((3, 2)), rng.random((3, 2)), rng.random((3, 2)), rng.random((3, 2, 4)),
        rng.random((3, 2, 8, 2)), rng.random((3, 2)), np.full((3, 2), 7, dtype=np.int32),
        np.full((3, 2), STATUS_OK, dtype=np.int8), np.zeros((3, 2), dtype=bool), complete,
        design_hash="0123456789abcdef", preset="screening")


def test_map_file_without_identity_attrs_is_a_cache_miss(tmp_path):
    r, prov = _result(), _prov()
    path = dataset.store_map(tmp_path, r, prov)
    with h5py.File(path, "a") as f:          # a 0.3.0 file has neither attribute
        del f.attrs["design_hash"], f.attrs["preset"]
    assert dataset.cached_map(tmp_path, prov) is None
```

(Add `import h5py` at the top of the test file if it is missing.) The existing `test_write_read_round_trip` compares every dataclass field, so it now covers the two new fields.

In `tests/maps/test_run.py`, add a test that `run_map` stamps the identity. Find the test there that calls `run_map` with a monkeypatched `map_ordered` and copy its setup; then assert:

```python
    assert result.design_hash == design_hash(design) and result.preset == design.mesh.preset
```

(Import `design_hash` from `srmcore.maps.identity`.) If no such test exists, monkeypatch `run.map_ordered` with `lambda fn, jobs, **kw: [_row() for _ in jobs]`, where `_row()` returns the dict shape of `solve_job` with zeros and `status` `STATUS_OK`. Use `make_8_6()` at `screening` and a 2 × 2 grid with currents `[0.0, 5.0]`; the solver name `"skfem"` is validated but never solves.

- [ ] **Step 6: Run them to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/maps/test_dataset.py tests/maps/test_run.py -v`
Expected: FAIL (`MapResult.__init__() got an unexpected keyword argument 'design_hash'`).

- [ ] **Step 7: Implement the fields, the stamping and the HDF5 attrs**

`run.py`: add at the end of `MapResult`:
```python
    complete: bool
    design_hash: str = ""              # maps.identity.design_hash of the design solved; "" when unknown
    preset: str = ""                   # the design's mesh preset; "" when unknown
```
Extend the class docstring with one sentence: `design_hash` and `preset` identify the design the map was solved for. In `run_map`, pass `design_hash=design_hash(design), preset=design.mesh.preset` to the `MapResult(...)` constructor (import `from .identity import design_hash`). `apply_failure_policy` uses `dataclasses.replace`, which keeps them.

`dataset.py` `write_map`: add `design_hash=result.design_hash, preset=result.preset` to `f.attrs.update(...)`. `read_map`: pass `design_hash=str(f.attrs["design_hash"]), preset=str(f.attrs["preset"])` to `MapResult`. A file without them raises `KeyError`, which `cached_map` already treats as a miss.

- [ ] **Step 8: Run them to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/maps/test_dataset.py tests/maps/test_run.py tests/maps/test_identity.py -v`
Expected: PASS.

- [ ] **Step 9: Write the failing em_validate tests** (in `tests/maps/test_em_validation.py`)

Change `_map()` so the synthetic map belongs to `DESIGN`:

```python
from srmcore.maps.identity import design_hash


def _map():
    return dataclasses.replace(synthetic_map(n_angles=16), design_hash=design_hash(DESIGN), preset="full")
```

Add:

```python
def test_map_of_another_design_fails_identity(monkeypatch):
    _patch(monkeypatch, versions=(version("srmcore"),))
    v = V.em_validate(DESIGN, dataclasses.replace(_map(), design_hash="ffffffffffffffff"))
    c = {c.name: c for c in v.checks}["map_identity"]
    assert v.label is None and c.status == "fail" and "ffffffffffffffff" in c.detail


def test_screening_map_with_full_design_fails_preset_and_identity(monkeypatch):
    _patch(monkeypatch, versions=(version("srmcore"),))
    screening = DESIGN.model_copy(update={"mesh": MeshSettings(preset="screening")})
    r = dataclasses.replace(_map(), design_hash=design_hash(screening), preset="screening")
    status = {c.name: c.status for c in V.em_validate(DESIGN, r).checks}
    assert status["preset"] == "fail" and status["map_identity"] == "fail"


def test_zero_torque_map_fails_map_match_without_raising(monkeypatch):
    _patch(monkeypatch)
    r = _map()
    zero = dataclasses.replace(r, torque_arkkio=np.zeros_like(r.torque_arkkio))
    with np.errstate(all="raise"):
        c = {c.name: c for c in V.em_validate(DESIGN, zero).checks}["map_matches_design"]
    assert c.status == "fail" and "zero peak torque" in c.detail
```

`test_screening_map_is_never_labelled` uses a screening design with a `full` map; it must still fail `preset` and `fem_checks`, and now `map_identity` as well. Leave its assertion (`<=`) as is.

- [ ] **Step 10: Run them to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/maps/test_em_validation.py -v -m "not slow"`
Expected: the three new tests FAIL (no `map_identity` check; `ZeroDivisionError` or a floating-point error).

- [ ] **Step 11: Implement the checks in `em_validate`**

In `validation.py` (import `from .identity import design_hash`):

```python
    expected_hash = design_hash(design)
    n_filled = float(np.sum(result.filled))
    a, i = np.unravel_index(np.argmax(np.abs(result.torque_arkkio)), result.torque_arkkio.shape)
    t_map, t_solve = abs(float(result.torque_arkkio[a, i])), nominal["peak_torque"]
    if t_map == 0.0:
        match_check = Check("map_matches_design", "fail", float("nan"), MAP_MATCH_TOLERANCE,
                            "map has zero peak torque; nothing to compare the design's solve with")
    else:
        match = abs(t_solve - t_map) / t_map if np.isfinite(t_solve) else float("nan")
        match_check = _upper("map_matches_design", match, MAP_MATCH_TOLERANCE,
                             "peak-torque key-point solve on the design's own mesh against the map's value at that grid point")
```

In the `checks` tuple, replace the old `_upper("map_matches_design", ...)` with `match_check`. Replace the `preset` check and add `map_identity` directly after it:

```python
        Check("preset", "pass" if result.preset == own and own in ("full", "reference") else "fail",
              float("nan"), float("nan"),
              f"map preset {result.preset or 'unknown'}, design preset {own}; the label needs full or reference"),
        Check("map_identity", "pass" if result.design_hash == expected_hash else "fail", float("nan"), float("nan"),
              f"map design hash {result.design_hash or 'unknown'}, this design {expected_hash}"),
```

Also check `key_points` and `key_numbers` with an all-zero torque map: `np.argmax` of zeros returns 0, which is fine. Any division in `key_numbers` by peak torque must not raise under `np.errstate(all="raise")`. If one does, guard it the same way and report it.

- [ ] **Step 12: Run the whole maps fast suite**

Run: `.venv\Scripts\python -m pytest tests/maps -m "not slow" -q`
Expected: all PASS. In the slow end-to-end test (`test_em_validate_end_to_end_on_the_8_6_full_mesh`), add `"map_identity"` to the tuple of names asserted `"pass"`. It is not run here.

- [ ] **Step 13: Commit**

```bash
git add src/srmcore/maps/identity.py src/srmcore/maps/run.py src/srmcore/maps/dataset.py src/srmcore/maps/validation.py tests/maps
git commit -m "feat: MapResult carries design hash and preset; em_validate checks map identity and zero-torque maps"
```

---

### Task 3: JSON result files and the speed benchmark

**Files:**
- Modify: `examples/em_validate_8_6.py`, `examples/team24_check.py`, `examples/femm_check.py`, `examples/krishnan_6_4_check.py`
- Create: `examples/speed_budget.py`
- No library code: each example writes its JSON with plain `json.dump`.
- Test: `tests/test_examples_json.py` (new, fast; covers only the pure helper functions below)

**Interfaces (Task 4 reads these exact shapes; every float is a plain Python float, NaN written as `null`):**

`docs/validation/em_validate_8_6.json`
```json
{"engine_version": "0.4.0", "label": null, "material_grades": {"stator": "C", "rotor": "C"},
 "map_s": 1740.0, "validate_s": 420.0,
 "checks": [{"name": "preset", "status": "pass", "value": null, "limit": null, "detail": "..."}],
 "budget": {"keys": ["la", "lu", "peak_torque", "psi_max"],
            "values_2d": {"la": 0.03}, "values": {"la": 0.031},
            "rows": [{"source": "mesh", "rel": {"la": 0.001}, "note": "..."}],
            "total": {"la": 0.1}}}
```
`docs/validation/team24.json`
```json
{"static_torque": {"model": 2.8, "measured": 3.22, "error_pct": -13.1},
 "rotor_flux": {"model": 0.0, "measured": 0.0, "error_pct": 0.0},
 "current_rise_max_dev_pct": {"before": 18.6, "after": 17.3}}
```
`docs/validation/femm.json`
```json
{"krishnan_8_6": {"worst_psi": 0.004, "worst_t_rel": 0.01, "worst_t_peak": 0.003, "ratio": 0.6}}
```
`docs/validation/krishnan_6_4.json`
```json
{"rows": [{"quantity": "La", "unit": "mH", "current": 1.0, "measured": 0.0, "model_2d": 0.0, "model_after": 0.0,
           "error_before_pct": 0.0, "unc_before_pct": 0.0, "error_after_pct": 0.0, "unc_after_pct": 0.0,
           "measurement_stated": false}]}
```
`docs/validation/speed.json`
```json
{"srmcore": "0.4.0", "cpu": "...", "logical_cpus": 16, "workers": 8, "date": "2026-10-06",
 "runs": [{"design": "8_6", "item": "screening", "seconds": 60.0}]}
```
`item` is one of `"screening"`, `"full"`, `"full_extras"`.

- [ ] **Step 1: Write the failing test of the JSON helpers** (`tests/test_examples_json.py`)

Each example gets one pure function that turns its results into the dict above. The test checks the function that has real logic, the `em_validate` serialiser; the others are dict literals built from the printed values.

```python
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from em_validate_8_6 import validation_json  # noqa: E402

from srmcore.maps.checks import Check
from srmcore.maps.validation import KEYS, BudgetRow, EmValidation, UncertaintyBudget


def test_validation_json_is_plain_json_with_nan_as_null():
    one = {k: 1.0 for k in KEYS}
    budget = UncertaintyBudget(one, one, (BudgetRow("mesh", one, "n"),), one)
    v = EmValidation(None, (Check("preset", "pass", math.nan, math.nan, "d"),), budget, "0.4.0",
                     {"stator": "C", "rotor": "C"})
    out = json.loads(json.dumps(validation_json(v, 1.0, 2.0)))
    assert out["checks"][0] == {"name": "preset", "status": "pass", "value": None, "limit": None, "detail": "d"}
    assert out["budget"]["keys"] == list(KEYS) and out["budget"]["rows"][0]["source"] == "mesh"
    assert out["label"] is None and out["map_s"] == 1.0 and out["validate_s"] == 2.0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_examples_json.py -v`
Expected: FAIL (`ImportError: cannot import name 'validation_json'`).

- [ ] **Step 3: Add `validation_json` and `--json` to `examples/em_validate_8_6.py`**

```python
def _num(x: float) -> float | None:
    return None if not math.isfinite(x) else float(x)


def validation_json(v, map_s: float, validate_s: float) -> dict:
    b = v.budget
    return {"engine_version": v.engine_version, "label": v.label, "material_grades": dict(v.material_grades),
            "map_s": map_s, "validate_s": validate_s,
            "checks": [{"name": c.name, "status": c.status, "value": _num(c.value), "limit": _num(c.limit),
                        "detail": c.detail} for c in v.checks],
            "budget": {"keys": list(KEYS),
                       "values_2d": {k: _num(b.values_2d[k]) for k in KEYS},
                       "values": {k: _num(b.values[k]) for k in KEYS},
                       "rows": [{"source": r.source, "rel": {k: _num(r.rel[k]) for k in KEYS}, "note": r.note}
                                for r in b.rows],
                       "total": {k: _num(b.total[k]) for k in KEYS}}}
```

Argument handling in `main()`: `args = sys.argv[1:]`. If `"--json"` is present, the next argument is the output path; remove both, and the remaining optional positional argument is `workers`. At the end of `main()`, when a path was given, write `json.dumps(validation_json(v, t1 - t0, t2 - t1), indent=1)` to it (create the parent directory). Update the module docstring's usage line to `python examples\em_validate_8_6.py [workers] [--json PATH]`.

- [ ] **Step 4: Run the test**

Run: `.venv\Scripts\python -m pytest tests/test_examples_json.py -v`
Expected: PASS.

- [ ] **Step 5: Add `--json PATH` to the other three examples**

Use the same argument rule: `--json PATH` anywhere in `sys.argv`, removed before the existing parsing.
- `team24_check.py`: build the `team24.json` dict from the values it already computes: `t_ark`, `T_MEASURED`, `flux`, `t24.TABLE_ROTOR_FLUX[-1]`, the max of `abs(pct(i_model, TABLE_CURRENT)[1:])` (before), and the same for `i_after` (after). Write it at the end. The script is module-level code; keep it that way, and just read the flag at the top.
- `femm_check.py`: collect `worst` per machine (as computed) into `{name: worst}` and write it at the end.
- `krishnan_6_4_check.py`: in the table loop, append one row dict per printed row with the numbers it prints. Inductances go in mH and torque in N·m, so use the same `f` scale. Each `unc_*_pct` is the model share only (`100 * model / meas`). Set `measurement_stated` to `MEASUREMENT[q] is not None`, and when it is true, add `100 * MEASUREMENT[q]` to the `unc` value, as the printout does.

Check each by running it where it is fast:
- `.venv\Scripts\python examples\team24_check.py --json $env:TEMP\t24.json` (minutes); the file must parse with `json.load`.
- The FEMM and Krishnan scripts take long. Run only `python -c "import ast; ast.parse(open('examples/femm_check.py').read())"` to syntax-check them; the controller runs them in the release step.

- [ ] **Step 6: Write `examples/speed_budget.py`**

```python
r"""Speed benchmark for the §7.2 budgets: cold-cache map times on the 8/6 and 12/8 with 8 workers.

Run on an idle machine:  $env:PYTHONPATH="tests"; .venv\Scripts\python -u examples\speed_budget.py [--json PATH]
Items: screening = build_map + analyse_map (40 x 8); full = the same at 48 x 20; full_extras =
build_overlap_map + fem_checks (64 held-out samples) on the full map.
"""
import datetime
import json
import os
import platform
import sys
import time
from importlib.metadata import version
from pathlib import Path

from conftest import make_8_6, make_12_8
from srmcore.maps import analyse_map, build_map, build_overlap_map
from srmcore.maps.fem_checks import fem_checks
from srmcore.model.design import Design, MeshSettings

WORKERS = 8
I_MAX = {"8_6": 20.0, "12_8": 10.0}          # docs/m5a-data/i_max.json
DESIGNS = {"8_6": make_8_6, "12_8": make_12_8}


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t0


def main() -> None:
    args = sys.argv[1:]
    out_path = Path(args[args.index("--json") + 1]) if "--json" in args else None
    runs = []
    for name, make in DESIGNS.items():
        for preset in ("screening", "full"):
            d = Design(machine=make(), mesh=MeshSettings(preset=preset))
            def job():
                r = build_map(d, I_MAX[name], workers=WORKERS)
                analyse_map(r, d)
                return r
            r, s = timed(job)
            runs.append({"design": name, "item": preset, "seconds": s})
            print(f"{name} {preset}: {s:.0f} s", flush=True)
            if preset == "full":
                _, s = timed(lambda: (build_overlap_map(d, I_MAX[name], workers=WORKERS),
                                      fem_checks(d, r, workers=WORKERS)))
                runs.append({"design": name, "item": "full_extras", "seconds": s})
                print(f"{name} full_extras: {s:.0f} s", flush=True)
    result = {"srmcore": version("srmcore"), "cpu": platform.processor(), "logical_cpus": os.cpu_count(),
              "workers": WORKERS, "date": datetime.date.today().isoformat(), "runs": runs}
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
```

`analyse_map(result, design)` is the signature in `src/srmcore/maps/checks.py`; the 12/8 I_max of 10 A is from `docs/m5a-data/i_max.json`.

- [ ] **Step 7: Syntax-check the benchmark** (the real run is the controller's, about 2–3 h)

Run: `.venv\Scripts\python -c "import ast; ast.parse(open('examples/speed_budget.py').read())"`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add examples tests/test_examples_json.py
git commit -m "feat: JSON results from the validation examples and a speed-budget benchmark"
```

---

### Task 4: Validation report generator

**Files:**
- Create: `tools/validation_report.py`
- Create: `docs/validation/speed_budgets.json` (placeholder values; the controller sets the real ones after the benchmark)
- Test: `tests/test_validation_report.py`

**Interfaces:**
- Consumes: the JSON shapes in Task 3, `docs/m5a-data/heldout.jsonl` (rows with `design`, `n_samples`, `held_out_psi`, `held_out_torque`, `band_radius`), `docs/validation/speed_budgets.json` `{"screening": s, "full": s, "full_extras": s}`, `docs/validation/ci.json` `{"tag": str, "run_url": str, "result": "success" | "failure" | "pending"}`, the material library, and the limits `PSI_TOLERANCE`, `TORQUE_TOLERANCE`, `BAND_RADIUS_TOLERANCE` from `srmcore.maps.fem_checks`.
- Produces: `generate(data_dir: Path, m5a_dir: Path, out_md: Path) -> str` returning `"PASS"`, `"PENDING"` or `"FAIL"`, and writing the markdown plus PNGs into `out_md.parent / "validation"`. CLI: `python tools\validation_report.py` uses `docs/validation`, `docs/m5a-data` and `docs/validation-report.md`, prints the verdict, and exits 1 on FAIL.

Verdict rules:
- **Gated rows:** M5a (64-sample rows: psi ≤ `PSI_TOLERANCE`, torque ≤ `TORQUE_TOLERANCE`, band_radius ≤ `BAND_RADIUS_TOLERANCE`), FEMM (each machine `ratio <= 1`), speed (each run ≤ the budget for its item), CI (`result == "success"`), and EM validation (every check except `engine_version` has status `pass`).
- **Report-only rows:** TEAM 24 and Krishnan. They are printed and never fail the report.
- A gated row whose input file is missing is `missing`. CI `pending` is `pending`.
- Verdict: `FAIL` if any gated row is `fail` or `missing`; else `PENDING` if any is `pending`; else `PASS`.

- [ ] **Step 1: Write the failing tests** (`tests/test_validation_report.py`)

```python
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import validation_report as vr  # noqa: E402

KEYS = ["la", "lu", "peak_torque", "psi_max"]


def _write_inputs(d: Path, m5a: Path, *, ci="success", femm_ratio=0.5, team_err=-13.1, drop=None):
    d.mkdir(parents=True, exist_ok=True)
    m5a.mkdir(parents=True, exist_ok=True)
    one = {k: 0.01 for k in KEYS}
    files = {
        "em_validate_8_6.json": {"engine_version": "0.4.0", "label": None, "material_grades": {"stator": "C", "rotor": "C"},
                                 "map_s": 1.0, "validate_s": 1.0,
                                 "checks": [{"name": "engine_version", "status": "fail", "value": None, "limit": None, "detail": ""},
                                            {"name": "preset", "status": "pass", "value": None, "limit": None, "detail": ""}],
                                 "budget": {"keys": KEYS, "values_2d": one, "values": one,
                                            "rows": [{"source": "mesh", "rel": one, "note": ""}], "total": one}},
        "team24.json": {"static_torque": {"model": 2.8, "measured": 3.22, "error_pct": team_err},
                        "rotor_flux": {"model": 1.0, "measured": 1.0, "error_pct": 0.0},
                        "current_rise_max_dev_pct": {"before": 18.6, "after": 17.3}},
        "femm.json": {"krishnan_8_6": {"worst_psi": 0.004, "worst_t_rel": 0.01, "worst_t_peak": 0.003, "ratio": femm_ratio}},
        "krishnan_6_4.json": {"rows": [{"quantity": "La", "unit": "mH", "current": 20.0, "measured": 1.0, "model_2d": 0.8,
                                        "model_after": 0.85, "error_before_pct": -20.0, "unc_before_pct": 5.0,
                                        "error_after_pct": -15.0, "unc_after_pct": 6.0, "measurement_stated": False}]},
        "speed.json": {"srmcore": "0.4.0", "cpu": "x", "logical_cpus": 16, "workers": 8, "date": "2026-10-06",
                       "runs": [{"design": "8_6", "item": "screening", "seconds": 50.0}]},
        "speed_budgets.json": {"screening": 90.0, "full": 3600.0, "full_extras": 1800.0},
        "ci.json": {"tag": "v0.4.0", "run_url": "https://example.invalid/run", "result": ci},
    }
    for name, data in files.items():
        if name != drop:
            (d / name).write_text(json.dumps(data))
    (m5a / "heldout.jsonl").write_text(json.dumps({"design": "8_6", "n_samples": 64, "held_out_psi": 0.001,
                                                   "held_out_torque": 0.005, "band_radius": 0.002}) + "\n")


def test_all_gated_rows_passing_is_pass(tmp_path):
    _write_inputs(tmp_path / "v", tmp_path / "m")
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "PASS"
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    for heading in ("## Engine", "## Material library", "## M5a", "## M5b", "## M5c", "## M5d",
                    "## EM validation", "## Speed", "## CI"):
        assert heading in text


def test_failing_gated_row_fails_the_report(tmp_path):
    _write_inputs(tmp_path / "v", tmp_path / "m", femm_ratio=1.2)
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "FAIL"


def test_report_only_rows_never_fail_it(tmp_path):
    _write_inputs(tmp_path / "v", tmp_path / "m", team_err=-60.0)
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "PASS"


def test_pending_ci_gives_pending(tmp_path):
    _write_inputs(tmp_path / "v", tmp_path / "m", ci="pending")
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "PENDING"


@pytest.mark.parametrize("drop", ["ci.json", "speed.json", "femm.json", "em_validate_8_6.json"])
def test_missing_gated_input_fails_without_crashing(tmp_path, drop):
    _write_inputs(tmp_path / "v", tmp_path / "m", drop=drop)
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "FAIL"
    assert "missing" in (tmp_path / "report.md").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_validation_report.py -v`
Expected: FAIL (`ModuleNotFoundError: validation_report`).

- [ ] **Step 3: Write `tools/validation_report.py`**

Structure (write it in full; keep each section a small function returning `(markdown: str, statuses: list[str])`):

```python
r"""Validation report (spec §8.6): reads the committed result JSON and writes docs/validation-report.md and its
plots. Regenerate on every version bump before tagging.

Usage: python tools\validation_report.py      (exit code 1 when the verdict is FAIL)
"""
import json
import sys
from importlib.metadata import PackageNotFoundError, metadata, version
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from srmcore.maps.fem_checks import BAND_RADIUS_TOLERANCE, PSI_TOLERANCE, TORQUE_TOLERANCE  # noqa: E402
from srmcore.materials.library import available_materials, load_material  # noqa: E402
from srmcore.materials.schema import SoftMagneticMaterial  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = ("numpy", "scipy", "gmsh", "scikit-fem", "ngsolve", "netgen-mesher", "h5py", "pydantic", "matplotlib")


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _status_cell(s: str) -> str:
    return {"pass": "pass", "fail": "**FAIL**", "missing": "**missing**", "pending": "pending"}[s]


def engine_section() -> str:
    rows = []
    for dist in ("srmcore", *DEPENDENCIES):
        try:
            md = metadata(dist)
            lic = md.get("License-Expression") or md.get("License") or "see package"
            rows.append(f"| {dist} | {version(dist)} | {lic.splitlines()[0][:60]} |")
        except PackageNotFoundError:
            rows.append(f"| {dist} | not installed | |")
    return "## Engine\n\n| Package | Version | Licence |\n|---|---|---|\n" + "\n".join(rows) + "\n"
```

Further functions, each returning `(markdown, statuses)`:
- `material_section()`: a table over `available_materials()` that are `SoftMagneticMaterial`: name, grade (`confidence`), Js, stacking, `digitisation_error` (or "—"), provisional fields, and the first 80 characters of the source. No status.
- `m5a_section(m5a_dir)`: the rows of `heldout.jsonl` with `n_samples == 64`. Each row: design, psi / torque / band_radius in % against the three limits. Status pass if all three are within; `missing` if the file is absent or has no 64-sample rows.
- `team24_section(data)`, `krishnan_section(data)`: report-only tables. Their status list is empty, even when the file is missing (the table then says "not run").
- `femm_section(data)`: one row per machine, `ratio <= 1` → pass. Missing file → `["missing"]`.
- `em_section(data, out_dir)`: the checks table and the budget table (rows × keys in %, plus total). Every check other than `engine_version` contributes its status. It also saves a bar chart `budget.png` of `total` per key. Missing file → `["missing"]`.
- `speed_section(data, budgets)`: one row per run against `budgets[item]`. Missing either file → `["missing"]`.
- `ci_section(data)`: tag, run URL, result. `success` → pass, `failure` → fail, `pending` → pending, missing → missing.
- Plots: `femm.png` (bar of `ratio` per machine with a line at 1.0) and `krishnan.png` (grouped bars of `error_before_pct` and `error_after_pct` per row label `"{quantity} {current:g} A"`), saved into `out_md.parent / "validation"` when their data exist. Each plot closes its figure (`plt.close(fig)`).

`generate(data_dir, m5a_dir, out_md)`:
1. Run every section and collect the statuses.
2. Verdict: `FAIL` if any `fail` or `missing`, else `PENDING` if any `pending`, else `PASS`.
3. Write `# srmcore validation report\n\n**Verdict: {verdict}**` and a bullet list of the failing, missing or pending sections, then the sections in this order: Engine, Material library, M5a, M5b TEAM 24, M5c FEMM, M5d Krishnan 6/4, EM validation (8/6), Speed, CI. Section headings are exactly `## Engine`, `## Material library`, `## M5a mesh convergence`, `## M5b TEAM 24`, `## M5c FEMM`, `## M5d Krishnan 6/4`, `## EM validation (8/6 full)`, `## Speed`, `## CI`.
4. Write with `encoding="utf-8"` and return the verdict.

`if __name__ == "__main__":` call `generate(ROOT / "docs" / "validation", ROOT / "docs" / "m5a-data", ROOT / "docs" / "validation-report.md")`, print the verdict, and `sys.exit(1 if verdict == "FAIL" else 0)`.

- [ ] **Step 4: Write the placeholder budgets file** (`docs/validation/speed_budgets.json`)

```json
{"screening": null, "full": null, "full_extras": null}
```

`speed_section` treats a `null` budget as `missing` (so the real report FAILs until the controller sets the numbers). Add this to the tests:

```python
def test_unset_speed_budget_is_missing(tmp_path):
    _write_inputs(tmp_path / "v", tmp_path / "m")
    (tmp_path / "v" / "speed_budgets.json").write_text(json.dumps({"screening": None, "full": None, "full_extras": None}))
    assert vr.generate(tmp_path / "v", tmp_path / "m", tmp_path / "report.md") == "FAIL"
```

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python -m pytest tests/test_validation_report.py -v`
Expected: PASS, each test well under 1 s (matplotlib import aside). Note the timing in your report.

- [ ] **Step 6: Commit**

```bash
git add tools/validation_report.py docs/validation/speed_budgets.json tests/test_validation_report.py
git commit -m "feat: generated validation report with gated verdict"
```

---

### Task 5: CI workflows

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `.github/workflows/slow.yml`

**Interfaces:** none (YAML only).

- [ ] **Step 1: Rewrite `ci.yml`**

```yaml
name: ci
on:
  push:
    branches: ["**"]
    tags: ["v*"]
  pull_request:
jobs:
  fast:
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, ubuntu-latest]
        python-version: ["3.12", "3.14"]
        # Branch pushes run 3.12 only (free-tier minutes); pull requests and version tags run the full matrix.
        exclude:
          - python-version: ${{ (github.event_name == 'push' && !startsWith(github.ref, 'refs/tags/v')) && '3.14' || 'none' }}
    runs-on: ${{ matrix.os }}
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - if: runner.os == 'Linux'
        run: sudo apt-get update && sudo apt-get install -y libglu1-mesa libxcursor1 libxft2 libxinerama1
      - run: python -m pip install -e ".[dev,ngsolve]"
      - run: python -m pytest -m "not slow" --durations=15
```

- [ ] **Step 2: Write `slow.yml`**

```yaml
name: slow
on:
  push:
    tags: ["v*"]
  workflow_dispatch:
jobs:
  slow:
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, ubuntu-latest]
    runs-on: ${{ matrix.os }}
    timeout-minutes: 360
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - if: runner.os == 'Linux'
        run: sudo apt-get update && sudo apt-get install -y libglu1-mesa libxcursor1 libxft2 libxinerama1
      - run: python -m pip install -e ".[dev,ngsolve]"
      - run: python -m pytest -m slow --durations=25
```

- [ ] **Step 3: Validate the YAML syntax**

Run: `.venv\Scripts\python -c "import yaml,sys; [yaml.safe_load(open(p)) for p in sys.argv[1:]]" .github/workflows/ci.yml .github/workflows/slow.yml`
If PyYAML is not installed, use `python -m pip install pyyaml` in the venv for this check only; do not add it to `pyproject.toml`.
Expected: no output. The `exclude` expression is evaluated by GitHub; the controller checks the first real push shows two fast jobs.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows
git commit -m "ci: trimmed push matrix, slow suite on version tags and manual dispatch"
```

---

### Task 6: Version 0.4.0 and docs

**Files:**
- Modify: `pyproject.toml` (`version = "0.4.0"`)
- Modify: `CLAUDE.md` (Current state, Commands, and the Map products item 9 for `map_identity`)
- Modify: `docs/superpowers/specs/2026-09-28-srm-core-engine-design.md` §5.3 (library now holds the M5e2 materials) and §8.6 (report path)

- [ ] **Step 1: Bump the version and reinstall**

Set `version = "0.4.0"` in `pyproject.toml`, then run `.venv\Scripts\python -m pip install -e ".[dev,ngsolve]"`.
Check: `.venv\Scripts\python -c "from importlib.metadata import version; print(version('srmcore'))"` prints `0.4.0`.

- [ ] **Step 2: Update the goldens provenance if needed**

Run: `.venv\Scripts\python -m pytest tests/maps/test_goldens.py -m slow -q`. If it fails only because the version string is part of a stored hash, follow the regeneration command in its docstring and report it. If anything else differs, stop and report.

- [ ] **Step 3: Docs**

- `CLAUDE.md` Current state: "M5e2 (library adds, map identity, speed budgets, validation report, CI slow suite) is implemented on branch `m5e2-validated-release`; srmcore 0.4.0". Commands: add `python examples\speed_budget.py [--json PATH]`, `python tools\validation_report.py`, `python tools\digitise_bh.py`, and the `--json PATH` options. Map products item 9: add `map_identity` (map design hash equals the design's) and the new `preset` rule (the map's preset must equal the design's).
- Spec §5.3 item 2: "Added in M5e2 (2026-10-05): 10JNEX900 (B), Hiperco 50A (B), Hiperco 50HS at 720/740/760 °C (C), M43 (C); sources in `docs/sources/materials/`."
- Spec §8.6: the report is `docs/validation-report.md`, generated by `tools/validation_report.py`.

- [ ] **Step 4: Full fast suite on an idle machine**

Run: `.venv\Scripts\python -m pytest -m "not slow" --durations=15`
Expected: all PASS, under 10 min. Report the time. If it is over 10 min, stop and report; the owner decides.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml CLAUDE.md docs/superpowers/specs/2026-09-28-srm-core-engine-design.md
git commit -m "chore: srmcore 0.4.0; docs for M5e2"
```

---

### Controller steps (not subagent tasks; long runs and owner gates)

1. **Long runs** (detached, ASCII logs, Monitor plus PID watch; run from a separate worktree with `PYTHONPATH=<worktree>\src` if code may change meanwhile):
   - `python -u examples\em_validate_8_6.py --json docs\validation\em_validate_8_6.json` (~1 h)
   - `PYTHONPATH=tests python -u examples\speed_budget.py --json docs\validation\speed.json` (idle machine, ~2–3 h)
   - `python examples\team24_check.py --json docs\validation\team24.json`
   - `PYTHONPATH=tests python examples\femm_check.py --json docs\validation\femm.json`
   - `PYTHONPATH=tests python -u examples\krishnan_6_4_check.py --json docs\validation\krishnan_6_4.json` (~17 min)
   - `python -m pytest -m slow --durations=25` locally (record the wall time and peak memory in the handoff)
2. **Speed budgets:** budget = max over designs × 1.25, rounded up to the next minute (the next 10 s for screening). Write them to `docs/validation/speed_budgets.json`, spec §7.2's table, and the §11 decision entry (old numbers, date 2026-10-05).
3. **`ci.json`:** `{"tag": "v0.4.0", "run_url": "", "result": "pending"}`.
4. **Report:** `python tools\validation_report.py` must print `PENDING`, with CI the only pending row, and `engine_version` the only failing em_validate check (which is not gated). On anything else, stop and fix or ask the owner.
5. **Validate the version:** `VALIDATED_VERSIONS = ("0.4.0",)` in `maps/validation.py`. Change `test_unvalidated_engine_version_blocks_the_label` to monkeypatch `VALIDATED_VERSIONS` to `()`; `_patch` already does that by default. Re-run `em_validate_8_6.py --json …` (label `EM-validated`) and regenerate the report. Commit.
6. **Opus whole-branch review**, then `superpowers:finishing-a-development-branch` (local merge on the owner's yes, then push `main`).
7. **Tag:** `git tag v0.4.0; git push origin v0.4.0`. Watch both workflows. Record the slow run in `docs/validation/ci.json` (`success` or `failure` plus the URL), regenerate the report, and commit to `main` as docs-only. On failure: open an owner decision (remove "0.4.0" in 0.4.1, or fix forward).
8. **Close M5:** spec §9 M5 row complete, §11 M5e2 entry, `docs/m5-roadmap.md` M5e2 marked done, CLAUDE.md current state, a handoff doc, and the living project doc's M5e2 section (results, budgets, CI link) plus the project table.
