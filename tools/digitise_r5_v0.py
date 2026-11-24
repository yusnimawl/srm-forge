r"""Reproduce the R5 gate V0 figure readings (tracker row 10k): the inputs and targets of gates V2 and V4.

  faiz_fig8  : Faiz et al. 2009, Fig. 8 (inside air temperature rise, p. 2932, 1-bit PNG xref 193), curve h = 30,
               the V2 inside-air input (the paper uses h = 30 W/(m2 K) on the frame for all later results).
  faiz_fig10 : Faiz et al. 2009, Fig. 10 (winding temperature, 2-D and 3-D, p. 2932, xref 92), the 2-D curve,
               the V2 comparison target.
  kiyota_fig7: Kiyota 2014, Fig. 7 (mechanical loss, salient rotor and cylindrical dummy; p. 5716, JPEG xref 138).
  kiyota_fig8: Kiyota, Kakishima and Chiba 2014, Fig. 8 (maximum-power test at 7500 r/min, p. 5716, JPEG xref
               204): the coil-end temperature and the RMS current against time, the V4 load and target.

Axes are least-squares fits to the frame and every gridline; `cal_px` is the largest fit residual. A reading is the
centre of the ink run where the curve crosses a 5-px-wide column; its error is the calibration residual plus half
the run's height, in the axis unit. Where curves overlap (Faiz, early times) the run holds all of them and the
error covers the merged run.

Usage: python tools/digitise_r5_v0.py [--papers DIR] [--json PATH]   (needs the dev extra, PyMuPDF; the PDFs are
       git-ignored, docs/sources/papers/.gitignore, so a fresh checkout passes the folder that holds them)
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pymupdf
from scipy import ndimage

PAPERS = Path(__file__).resolve().parents[1] / "docs" / "sources" / "papers"


def _image(pdf: str, xref: int) -> np.ndarray:
    doc = pymupdf.open(PAPERS / pdf)
    pix = pymupdf.Pixmap(doc.extract_image(xref)["image"])
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)


def _ends(profile: np.ndarray) -> tuple[float, float]:
    """Centres of the first and last frame lines: the rows or columns with at least 80 % of the longest ink run."""
    idx = np.nonzero(profile > 0.8 * profile.max())[0]
    return idx[idx < idx.min() + 15].mean(), idx[idx > idx.max() - 15].mean()


def _axis(profile, lo_px, hi_px, n, v0, v1, win=8):
    """Linear px -> value map fitted to the two frame lines and the n - 1 gridlines between them (each located as
    the ink-weighted centre within `win` px of its nominal place). Returns (slope, offset, residual in px)."""
    px, vals = [lo_px], [v0]
    for k in range(1, n):
        x = lo_px + (hi_px - lo_px) * k / n
        w = np.arange(int(x) - win, int(x) + win + 1)
        p = profile[w].astype(float)
        px.append((w * p).sum() / p.sum())
        vals.append(v0 + (v1 - v0) * k / n)
    px.append(hi_px)
    vals.append(v1)
    a, b = np.polyfit(px, vals, 1)
    return a, b, float(np.max(np.abs(np.polyval([a, b], px) - vals)) / abs(a))


def _runs(mask: np.ndarray, gap: int = 3) -> list[tuple[float, int, int]]:
    idx = np.nonzero(mask)[0]
    if not len(idx):
        return []
    return [(g.mean(), int(g.min()), int(g.max())) for g in np.split(idx, np.nonzero(np.diff(idx) > gap)[0] + 1)]


def _faiz(xref, t_end, y0, y1, ny, legend, pick):
    """One curve of a Faiz 2009 plot (x 0 to t_end min in 6 grid steps, y y0 to y1 degC in ny steps). `legend` is
    the legend box (col0, col1, row0, row1) in px, masked out; `pick(runs)` chooses the curve's run in a column."""
    ink = _image("faiz2009.pdf", xref)[..., 0] > 128            # the 1-bit images store ink as 255
    left, right = _ends(ink.sum(0))
    top, bottom = _ends(ink.sum(1))
    ax, bx, rx = _axis(ink[int(top) + 20:int(bottom) - 20].sum(0), left, right, 6, 0.0, t_end)
    ay, by, ry = _axis(ink[:, int(left) + 20:int(right) - 20].sum(1), bottom, top, ny, y0, y1)
    rows = np.arange(int(top) + 6, int(bottom) - 6)
    grid_rows = [(y0 + (y1 - y0) * k / ny - by) / ay for k in range(1, ny)]
    grid_cols = [(t_end * k / 6 - bx) / ax for k in range(1, 6)]
    pts = []
    for t in np.arange(1.0, t_end, 1.0):
        c = int(round((t - bx) / ax))
        if min(abs(c - g) for g in grid_cols) < 6:
            continue
        col = ink[rows, c - 2:c + 3].any(1)
        keep = np.all([np.abs(rows - g) > 5 for g in grid_rows], axis=0)
        if legend[0] <= c <= legend[1]:
            keep &= (rows < legend[2]) | (rows > legend[3])
        run = pick(_runs(col & keep))
        if run is None:
            continue
        centre, lo, hi = run
        value = ay * (rows[0] + centre) + by
        err = abs(ay) * (ry + (hi - lo) / 2 + 0.5)
        pts.append((round(float(t), 1), round(float(value), 2), round(float(err), 2)))
    return dict(cal_px=dict(x=round(rx, 2), y=round(ry, 2)), min_per_px=round(ax, 4), k_per_px=round(abs(ay), 4),
                points=pts)


def _middle_or_merged(runs):
    """h = 30 is the middle of three separate curves; one run means the three overlap (its span is the error)."""
    if len(runs) == 3:
        return sorted(runs)[1]
    if len(runs) == 1:
        return runs[0]
    return None


def faiz_fig8() -> dict:
    return _faiz(193, 120.0, 20.0, 65.0, 9, legend=(300, 580, 95, 320), pick=_middle_or_merged)


def faiz_fig10() -> dict:
    """The 2-D curve is the highest; where the 3-D middle-of-motor curve touches it the run holds both."""
    return _faiz(92, 120.0, 20.0, 55.0, 7, legend=(200, 1015, 30, 270), pick=lambda r: min(r) if r else None)


# Kiyota Fig. 8 calibration in px of the 962 x 575 JPEG. x: the bottom-axis tick marks at 0, 5, 10, 15 and 20 s
# (0 s is the centre of the 2-px left frame line). y: the top frame line (250 A), the dotted "75 degrees" line
# (100 A; 75 degC on the right axis) and the bottom frame line (0 A), which the green command trace covers, so the
# frame cannot be found from ink counts.
KIYOTA_X = ((135.5, 0.0), (315.0, 5.0), (495.0, 10.0), (674.0, 15.0), (854.0, 20.0))
KIYOTA_Y = ((474.5, 0.0), (289.0, 100.0), (13.0, 250.0))


def kiyota_fig8() -> dict:
    """Left axis 0 to 250 A and right axis 45 to 120 degC on the same rows (0.3 degC per A). Temperature: the
    dark-red trace (the lighter dashed 'estimated' extension is left out by the colour limits); the spikes of the
    logged signal (one-column drops) are removed by a median over 7 columns. RMS current: the light-blue trace."""
    a = _image("kiyota2014.pdf", 204)[..., :3].astype(float)
    (ax, bx), (ay, by) = (np.polyfit(*zip(*cal), 1) for cal in (KIYOTA_X, KIYOTA_Y))
    rx = max(abs(ax * p + bx - v) for p, v in KIYOTA_X) / ax
    ry = max(abs(ay * p + by - v) for p, v in KIYOTA_Y) / abs(ay)
    red = (a[..., 0] > 150) & (a[..., 1] < 90) & (a[..., 2] < 90)
    blue = (a[..., 2] > 180) & (a[..., 2] - a[..., 0] > 30) & (a[..., 0] > 100)       # light blue, not grey
    temp, cur = [], []
    for t in np.arange(0.0, 20.0 + 1e-9, 0.25):
        c = int(round((t - bx) / ax))
        cols = range(max(c - 3, 138), min(c + 4, 852))
        tr = [np.median(np.nonzero(red[:, k])[0]) for k in cols if red[:, k].any()]
        cr = [np.median(np.nonzero(blue[:, k])[0]) for k in cols if blue[:, k].any()]
        if tr:
            temp.append((round(float(t), 2), round(float(45.0 + 0.3 * (ay * np.median(tr) + by)), 2)))
        if cr:
            cur.append((round(float(t), 2), round(float(ay * np.median(cr) + by), 1)))
    return dict(cal_px=dict(x=round(float(rx), 2), y=round(float(ry), 2)), s_per_px=round(float(ax), 4),
                a_per_px=round(float(abs(ay)), 4), k_per_px=round(float(0.3 * abs(ay)), 4),
                temperature_c=temp, rms_current_a=cur)


def kiyota_fig7() -> dict:
    """Mechanical loss (bearing plus windage) of the test SRM (salient rotor, blue diamonds) and of the
    cylindrical dummy rotor (red squares), Kiyota 2014 Fig. 7 (p. 5716, JPEG xref 138). Calibration: frame lines at
    columns 119 (0 r/min) and 900 (15 000 r/min), rows 398 (0 W) and 12.5 (2500 W); it reproduces the printed
    2.0 kW salient point at 13 900 r/min to 7 W and the printed 980 W difference to 7 W. Markers are the colour
    blobs (dilated twice); the two legend markers left of column 200 are dropped."""
    a = _image("kiyota2014.pdf", 138)[..., :3].astype(int)
    rpm = lambda x: (x - 119.0) / (900.0 - 119.0) * 15000.0
    watt = lambda y: (398.0 - y) / (398.0 - 12.5) * 2500.0
    out = {}
    for name, mask in (("salient", (a[..., 2] - a[..., 0] > 40) & (a[..., 2] > 150)),
                       ("cylindrical", (a[..., 0] - a[..., 2] > 40) & (a[..., 0] > 150))):
        lab, n = ndimage.label(ndimage.binary_dilation(mask, iterations=2))
        pts = []
        for k in range(1, n + 1):
            ys, xs = np.nonzero(lab == k)
            if len(ys) > 30 and xs.mean() > 200:
                pts.append((round(float(rpm(xs.mean()))), round(float(watt(ys.mean())))))
        out[name] = sorted(pts)
    return dict(rpm_per_px=round(15000.0 / 781.0, 2), w_per_px=round(2500.0 / 385.5, 2), **out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers", type=Path, default=PAPERS)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    PAPERS = args.papers
    out = dict(faiz_fig8=faiz_fig8(), faiz_fig10=faiz_fig10(), kiyota_fig8=kiyota_fig8(), kiyota_fig7=kiyota_fig7())
    text = json.dumps(out, indent=1)
    if args.json:
        args.json.write_text(text + "\n")
    print(text)
