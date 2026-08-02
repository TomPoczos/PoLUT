"""
Kodak-specific PDF-quirk helpers, ported from
`tools/curve_digitizer/kodak_common.py` (same repo, sibling tool) -- kept
separate from `digitizer_core.py` (vendored verbatim, vendor-agnostic) since
these are Kodak-era-specific typesetting workarounds, not general
extraction machinery.
"""

import re

import fitz
import numpy as np


def overline_negative_calib(pdf_path, page_index, region_bbox, tick_regex=r"-?\d\.0"):
    """Several ~1997-2003-era Kodak sheets draw the minus sign on negative
    axis ticks as a small vector overline, not a text glyph -- every
    negative tick except the pixel-rightmost (genuinely unsigned) one
    extracts as its bare unsigned value, indistinguishable by text alone
    from a real unsigned tick at a different position. Negates every tick
    except the rightmost-by-pixel and fits (slope, intercept) from the
    corrected values -- pass the result as ChartSpec.x_axis_calib_override
    rather than trusting fit_axis's text-based reading for this axis."""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    words = page.get_text("words")
    doc.close()
    candidates = []
    for x0, y0, x1, y1, text, *_ in words:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if not (region_bbox[0] <= cx <= region_bbox[2] and region_bbox[1] <= cy <= region_bbox[3]):
            continue
        if re.fullmatch(tick_regex, text):
            try:
                candidates.append((cx, cy, float(text)))
            except ValueError:
                pass
    if len(candidates) < 2:
        raise RuntimeError(f"only {len(candidates)} tick candidates found in {region_bbox} for overline fix")

    by_y = sorted(candidates, key=lambda c: c[1])
    clusters, cur = [], [by_y[0]]
    for c in by_y[1:]:
        if abs(c[1] - cur[-1][1]) <= 6:
            cur.append(c)
        else:
            clusters.append(cur)
            cur = [c]
    clusters.append(cur)
    best = max(clusters, key=lambda cl: max(p[0] for p in cl) - min(p[0] for p in cl))
    if len(best) < 2:
        raise RuntimeError(f"widest tick row only has {len(best)} points in {region_bbox} for overline fix")

    best.sort(key=lambda c: c[0])
    pixels = [c[0] for c in best]
    corrected = [-c[2] for c in best[:-1]] + [best[-1][2]]
    slope, intercept = np.polyfit(pixels, corrected, 1)
    return float(slope), float(intercept)


def overline_symmetric_calib(pdf_path, page_index, region_bbox, tick_regex=r"\d\.0"):
    """Spectral-Sensitivity panel (LOG SENSITIVITY axis) has the SAME
    overline-vector-minus-sign problem as overline_negative_calib, but on a
    Y-axis with real ticks on BOTH sides of a real 0.0 -- prints e.g. "3.0
    2.0 1.0 0.0 1.0" top-to-bottom, i.e. the bottom half's minus signs are
    drawn overlines, not text. Finds the real 0.0 tick's own pixel position
    (the one genuinely unambiguous value) and negates every tick on the far
    side of it from the smallest-pixel (top, largest real value) end."""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    words = page.get_text("words")
    doc.close()
    candidates = []
    for x0, y0, x1, y1, text, *_ in words:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if not (region_bbox[0] <= cx <= region_bbox[2] and region_bbox[1] <= cy <= region_bbox[3]):
            continue
        if re.fullmatch(tick_regex, text):
            try:
                candidates.append((cx, cy, float(text)))
            except ValueError:
                pass
    if len(candidates) < 3:
        raise RuntimeError(f"only {len(candidates)} tick candidates found in {region_bbox} for symmetric fix")

    by_x = sorted(candidates, key=lambda c: c[0])
    clusters, cur = [], [by_x[0]]
    for c in by_x[1:]:
        if abs(c[0] - cur[-1][0]) <= 6:
            cur.append(c)
        else:
            clusters.append(cur)
            cur = [c]
    clusters.append(cur)
    best = max(clusters, key=lambda cl: max(p[1] for p in cl) - min(p[1] for p in cl))
    if len(best) < 3:
        raise RuntimeError(f"tallest tick column only has {len(best)} points in {region_bbox} for symmetric fix")

    best.sort(key=lambda c: c[1])  # top (smallest pixel-y) to bottom
    zero_idx = min(range(len(best)), key=lambda i: abs(best[i][2]))
    pixels = [c[1] for c in best]
    corrected = [v if i <= zero_idx else -v for i, (_, _, v) in enumerate(best)]
    slope, intercept = np.polyfit(pixels, corrected, 1)
    return float(slope), float(intercept)
