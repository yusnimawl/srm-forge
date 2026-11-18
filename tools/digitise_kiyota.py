r"""Reproduce the readings of the Kiyota 18/12 SRM taken from figures (tracker row 10a, R5 gate V0).

  geometry : Kiyota and Chiba 2012, Fig. 7 (iron structure, 780 px embedded JPEG, xref 60 on p. 2306); the outer
             circle is the 264 mm stator diameter. Radii are line centres; pole arcs and tapers are a straight-flank
             fit of the pole half-widths over the clean part of each flank.
  fig16    : Kiyota, Kakishima and Chiba 2014, Fig. 16 (losses at 13 900 r/min, 950 px JPEG, xref 142 on p. 5719);
             the "iron and other electrical losses (Test)" and "copper loss (Test)" diamonds.

Usage: python tools\digitise_kiyota.py [--papers DIR]   (needs the dev extra: PyMuPDF; the PDFs are git-ignored,
       docs/sources/papers/.gitignore, so a fresh checkout passes the folder that holds them)
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import pymupdf
from scipy import ndimage

PAPERS = Path(__file__).resolve().parents[1] / "docs" / "sources" / "papers"
STATOR_OD = 0.264


def _image(pdf: str, xref: int) -> np.ndarray:
    doc = pymupdf.open(PAPERS / pdf)
    pix = pymupdf.Pixmap(doc.extract_image(xref)["image"])
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[..., :3].astype(float)


def _sample(gray, cx, cy, r, th):
    x, y = cx + r * np.cos(th), cy - r * np.sin(th)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return (gray[y0, x0] * (1 - fx) * (1 - fy) + gray[y0, x0 + 1] * fx * (1 - fy)
            + gray[y0 + 1, x0] * (1 - fx) * fy + gray[y0 + 1, x0 + 1] * fx * fy)


def _runs(pos, v, thr=100.0):
    """Intensity-weighted centres of the bright runs of a profile."""
    out, i, m = [], 0, v > thr
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            out.append(float((pos[i:j] * v[i:j]).sum() / v[i:j].sum()))
            i = j
        else:
            i += 1
    return out


def _circle(pts):
    keep = np.ones(len(pts), bool)
    for _ in range(10):
        p = pts[keep]
        s = np.linalg.lstsq(np.c_[2 * p, np.ones(len(p))], (p ** 2).sum(1), rcond=None)[0]
        cx, cy = s[:2]
        r = math.sqrt(s[2] + cx * cx + cy * cy)
        res = np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - r
        keep = np.abs(res) < 3 * max(res[keep].std(), 0.3)
    return cx, cy, r, float(res[keep].std())


def geometry() -> dict:
    gray = _image("kiyota2012.pdf", 60).mean(axis=2)
    pts = []
    for th in np.linspace(0, 2 * np.pi, 1440, endpoint=False):     # outermost line = the 264 mm circle
        r = np.arange(330.0, 389.0, 0.25)
        runs = _runs(r, _sample(gray, 389.7, 389.7, r, th))
        if runs:
            pts.append((389.7 + runs[-1] * math.cos(th), 389.7 - runs[-1] * math.sin(th)))
    cx, cy, r_px, sd = _circle(np.array(pts))
    mm = STATOR_OD / 2 / r_px

    # circles: histogram of line-crossing radii over 3600 rays; the full and partial circles are the peaks
    radii = []
    for th in np.linspace(0, 2 * np.pi, 3600, endpoint=False):
        r = np.arange(5.0, r_px - 2, 0.25)
        radii += [x * mm for x in _runs(r, _sample(gray, cx, cy, r, th))]
    hist, edges = np.histogram(radii, bins=np.arange(0, STATOR_OD / 2, 0.5e-3))
    peaks = [float(np.mean([x for x in radii if e <= x < e + 0.5e-3])) for h, e in zip(hist, edges) if h > 900]

    arrow = math.degrees(math.atan2(cy - 90, 635 - cx)) % 360      # the dimension arrow crosses two gaps

    def widths(radius, slot_radius):
        """Angular widths (deg) of the iron poles at `radius`: gaps between line crossings whose middle has no
        slot-bottom arc at `slot_radius`."""
        th = np.radians(np.linspace(0, 360, 36000, endpoint=False))
        v = _sample(gray, cx, cy, radius / mm, th)
        k = int(np.argmin(v > 100))
        cs = np.sort(np.array(_runs(np.degrees(np.unwrap(np.roll(th, -k))), np.roll(v, -k))) % 360)
        out = []
        for a, b in zip(cs, np.r_[cs[1:], cs[0] + 360]):
            mid, w = (a + b) / 2 % 360, b - a
            near = min(abs((mid - x + 180) % 360 - 180) for x in (arrow, arrow + 180))
            if w < 6 or near < w / 2 + 1:
                continue
            slot = _sample(gray, cx, cy, slot_radius / mm, np.radians(np.linspace(mid - 1, mid + 1, 21))).max() > 100
            if not slot:
                out.append(w)
        return float(np.mean(out))

    def flank(samples, face_radius, outward):
        r = np.array([s for s, _ in samples])
        half = np.radians([w for _, w in samples]) / 2
        x, y = r * np.cos(half), r * np.sin(half)
        k, b = np.polyfit(x, y, 1)
        qa, qb, qc = 1 + k * k, 2 * k * b, b * b - face_radius ** 2
        xf = (-qb + math.sqrt(qb * qb - 4 * qa * qc)) / (2 * qa)
        return 2 * math.atan2(k * xf + b, xf), math.atan(k) * (1 if outward else -1)

    shaft_r, rotor_slot_r, rotor_r, bore_r, stator_slot_r = peaks[0], peaks[1], peaks[2], peaks[3], peaks[4]
    stator = [(r, widths(r, stator_slot_r)) for r in (93e-3, 95e-3, 100e-3, 105e-3, 110e-3, 113e-3)]
    rotor = [(r, widths(r, rotor_slot_r)) for r in (78e-3, 82e-3, 86e-3, 89e-3, 90e-3)]
    s_arc, s_taper = flank(stator, bore_r, True)
    r_arc, r_taper = flank(rotor, rotor_r, False)
    return dict(mm_per_px=mm * 1e3, outer_fit_residual_px=sd, shaft_radius=shaft_r, rotor_slot_radius=rotor_slot_r,
                rotor_radius=rotor_r, bore_radius=bore_r, stator_slot_radius=stator_slot_r,
                stator_pole_arc_deg=math.degrees(s_arc), stator_pole_taper_deg=math.degrees(s_taper),
                rotor_pole_arc_deg=math.degrees(r_arc), rotor_pole_taper_deg=math.degrees(r_taper))


def fig16() -> dict:
    """Axis calibration from the tick marks: x ticks 20 kW apart at 265.5 + 131.6 k px (0 kW at 133.9), y ticks
    1 kW apart at 503.8 - 61.33 y px. Markers are the blobs left after three erosions of the colour mask (the
    double lines vanish); two red diamonds near 22 kW touch and are split by their rows."""
    a = _image("kiyota2014.pdf", 142)
    red = (a[..., 0] > 120) & (a[..., 1] < 90) & (a[..., 2] < 90)
    blue = (a[..., 2] > 110) & (a[..., 0] < 90) & (a[..., 1] < 130)
    kw = lambda x, y: (round((x - 133.9) / 131.6 * 20, 2), round((503.8 - y) / 61.33, 3))
    out = {}
    for name, mask in (("iron_and_other", red), ("copper", blue)):
        lab, n = ndimage.label(ndimage.binary_erosion(mask, iterations=3))
        pts = []
        for k in range(1, n + 1):
            ys, xs = np.nonzero(lab == k)
            if len(ys) < 4:
                continue
            if name == "iron_and_other" and len(ys) > 70:          # the two touching diamonds near 22 kW
                split = ys.min() + (ys.max() - ys.min()) // 2 + 2
                for sel in (ys < split, ys >= split):
                    pts.append(kw(xs[sel].mean(), ys[sel].mean()))
            else:
                pts.append(kw(xs.mean(), ys.mean()))
        out[name] = sorted(pts)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers", type=Path, default=PAPERS)
    PAPERS = ap.parse_args().papers
    print(json.dumps(dict(geometry=geometry(), fig16=fig16()), indent=2))
