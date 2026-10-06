r"""Reproduce the traced B-H points of the library records that come from published figures.

  10JNEX900  : dashed curve of JFE Technical Report 21 p. 46 Fig. 1, traced from an 800 dpi render
  Hiperco50A : low-field nodes of the H50A curve on p. 4 of Carpenter E199, read from the PDF vector path
  Vacoflux48 : low-field nodes of the VACOFLUX 48 curve on p. 8 of the VAC CoFe brochure, read from the vector path
  10JNHF600, 20JNHF1300 : 50 Hz magnetization curves of JFE catalogue f2e-001 pp. 19 and 29, traced at 400 dpi

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


def vacoflux_48_low_field() -> tuple[list[float], list[float]]:
    """Nodes of the VACOFLUX 48 curve (purple) in Figure 1, p. 8 of the VAC CoFe brochure, between 9 and 300 A/m.
    Axis from the tick-label centres: 0-1600 A/m at x = 86.6-405.3 pt, 0-2.5 T at y = 579.9-383.0 pt."""
    page = pymupdf.open(SOURCES / "vac_cobalt_iron_alloys_vacoflux_vacodur_2021.pdf")[7]
    for d in page.get_drawings():
        c = d.get("color")
        if c and len(d["items"]) > 5 and abs(c[0] - 0.549) < 0.01 and abs(c[1] - 0.478) < 0.01:
            nodes = sorted({(p.x, p.y) for it in d["items"] for p in (it[1], it[-1])})
            pts = [((x - 86.6) / (405.3 - 86.6) * 1600, (579.9 - y) / (579.9 - 383.0) * 2.5) for x, y in nodes]
            pts = [(h, b) for h, b in pts if 9 <= h < 300]
            return [round(h, 1) for h, _ in pts], [round(b, 3) for _, b in pts]
    raise RuntimeError("VACOFLUX 48 curve not found on p. 8")


def jnhf_catalogue_curve(page: int) -> tuple[list[float], list[float]]:
    """32 points, log-spaced 15 A/m to 20 kA/m (the curve end above it flattens below mu0), of the 50 Hz magnetization curve on a JNHF page of JFE catalogue
    f2e-001 (index 18: 10JNHF600, index 28: 20JNHF1300), traced from a 400 dpi render. The plot is rotated: B runs
    2.0 -> 0 T left to right over the outermost grid columns, H runs 10^5 -> 10 A/m top to bottom over the outermost
    grid rows. The legend box (B < 1.25 T, H > 2 kA/m) is masked."""
    pix = pymupdf.open(SOURCES / "jfe_f2e-001_magnetic_property_curves.pdf")[page].get_pixmap(dpi=400)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].astype(int)
    grid = (a[..., 2] - a[..., 0] > 40) & (a[..., 2] > 150)
    cols = np.flatnonzero(grid.sum(0) > 0.9 * grid.sum(0).max())
    rows = np.flatnonzero(grid.sum(1) > 0.9 * grid.sum(1).max())
    c0, c1, r0, r1 = cols[0] + 1, cols[-1] - 1, rows[0] + 1, rows[-1]
    b_of = lambda x: 2.0 * (c1 - x) / (c1 - c0)
    h_of = lambda y: 10 ** (1 + 4 * (r1 - y) / (r1 - r0))
    dark = a.max(axis=2) < 110
    dark[:, :c0 + 3] = dark[:, c1 - 2:] = False
    dark[:r0 + 3] = dark[r1 - 2:] = False
    dark[:int(r1 - (np.log10(2000) - 1) / 4 * (r1 - r0)), int(c1 - 1.25 / 2.0 * (c1 - c0)):] = False
    pts = []
    for y in range(r0 + 3, r1 - 2):
        xs = np.flatnonzero(dark[y])
        if len(xs) and xs.max() - xs.min() <= 40:
            pts.append((h_of(y), b_of(xs.mean())))
    hh, bb = np.array(pts[::-1]).T
    ok = np.abs(bb - medfilt(bb, 31)) < 0.02
    grid_h = np.logspace(np.log10(15), np.log10(20000), 32)
    b = np.interp(np.log10(grid_h), np.log10(hh[ok]), bb[ok])
    return [round(float(v), 2) for v in grid_h], [round(float(v), 4) for v in b]


if __name__ == "__main__":
    print(json.dumps({"10JNEX900": jnex_dc_curve(), "Hiperco50A_low_field": hiperco_50a_low_field(),
                      "Vacoflux48_low_field": vacoflux_48_low_field(),
                      "10JNHF600": jnhf_catalogue_curve(18), "20JNHF1300": jnhf_catalogue_curve(28)}, indent=1))
