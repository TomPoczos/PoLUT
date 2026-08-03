"""
Shared, vendor-agnostic primitives for digitizing H&D / spectral-sensitivity /
reciprocity charts out of manufacturer PDF datasheets.

Three curve-extraction strategies live here, selected per chart via
ChartSpec.extraction_method:

- "vector_color_fill" (Strategy A): each curve is a distinctly-colored filled
  vector path (Fuji, Polaroid, single-sheet Agfa/Maco). Matches the original
  curve_digitizer approach.
- "vector_stroke_dash" (Strategy B): curves share black/gray ink and are
  distinguished by stroke color/dash-pattern/width instead of fill (Kodak
  still + motion-picture, all print-paper vendors, Rollei/Maco B&W).
- "raster_trace" (Strategy C): the chart is an embedded raster image (JPEG),
  not vector paths (post-2018 Ilford, some Konica) -- traced by color-matching
  pixels in a cropped high-DPI render of the image's placement rect instead of
  walking path vertices.

Everything downstream of "a list of (page_x, page_y) points already in PDF
page-point space" (binning, isotonic regression, RDP simplification, QA
overlay rendering) is identical regardless of which strategy produced them --
that shared machinery is what this module preserves unchanged from the
original tool.
"""

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np


# ---------------------------------------------------------------------------
# Chart/curve description
# ---------------------------------------------------------------------------

@dataclass
class CurveSpec:
    name: str
    # Strategy A (vector_color_fill): match a filled path's fill color.
    fill_rgb: tuple[float, float, float] | None = None
    # Strategy B (vector_stroke_dash): match a stroked path's color/dash/width.
    stroke_rgb: tuple[float, float, float] | None = None
    dash_regex: str | None = None  # matched against d.get("dashes", ""), e.g. r"^\[\] " for solid
    width: float | None = None
    width_tol: float = 0.15
    # Strategy C (raster_trace): match a pixel color in the cropped chart image.
    pixel_rgb: tuple[int, int, int] | None = None
    pixel_tol: int = 24
    # Strategy D (vector_position): identify this curve's own trace, among
    # several same-ink traces in one panel, by the small inline text label
    # printed near it (e.g. "B"/"G"/"R", or "Yellow-\nForming\nLayer") --
    # matched to whichever trace has a point closest to the label's bbox
    # center, not by color/dash/width (there often isn't any to key on).
    label_regex: str | None = None
    # Escape hatch for sheets where the label isn't real extractable text at
    # all (rotated OCR-confirmed labels, or vector-drawn-glyph legends) --
    # a hand-identified (x, y) page-coordinate position used directly in
    # place of a `label_regex` text search. See ocr_helpers.py.
    label_position_override: tuple[float, float] | None = None
    tol: float = 0.05  # color-match tolerance for fill_rgb/stroke_rgb (0..1 scale)


@dataclass
class ChartSpec:
    pdf: str
    page_index: int  # 0-based
    chart_id: str
    x_tick_regex: str
    y_tick_regex: str
    x_label: str
    y_label: str
    curves: list[CurveSpec]
    film_id: str  # output folder + filename prefix (legacy main.py usage only)
    legend_bbox: tuple[float, float, float, float] | None = None
    n_bins: int = 400
    monotonic_direction: str | None = None  # "increasing" / "decreasing" / None
    extraction_method: str = "vector_color_fill"
    # Strategy C only: which embedded image on the page is the chart (index
    # into page.get_images()), and how many times to upsample when rendering
    # the crop for pixel tracing.
    raster_image_index: int = 0
    raster_dpi_scale: float = 4.0
    # Strategy D only (vector_position): several mini-charts sharing one page
    # and one ink color (typical Kodak multi-panel sheets) need both a tick
    # word pre-filter and a plot-region pre-filter to isolate the one panel
    # this ChartSpec targets from its page-mates.
    axis_word_bbox: tuple[float, float, float, float] | None = None
    x_tick_bbox: tuple[float, float, float, float] | None = None  # overrides axis_word_bbox for x if set
    y_tick_bbox: tuple[float, float, float, float] | None = None  # overrides axis_word_bbox for y if set
    region_bbox: tuple[float, float, float, float] | None = None
    # Escape hatch for axes where text-based tick reading can't be trusted at
    # all (e.g. every negative tick but one drawn with the sign as a vector
    # overline, so only a single genuinely-unsigned tick remains -- not
    # enough points for fit_axis to fit a slope from text alone). Each is
    # (slope, intercept) mapping pixel -> data value directly, bypassing
    # fit_axis/tick-text reading entirely for that axis when set.
    x_axis_calib_override: tuple[float, float] | None = None
    y_axis_calib_override: tuple[float, float] | None = None
    min_trace_points: int = 12
    cross_object_merge: bool = False  # see extract_traces_in_region -- opt-in only, verify with QA overlay
    merge_strategy: str = "proximity"  # or "sequential_band", see extract_traces_in_region
    merge_tol_multiplier: int = 6  # see extract_traces_in_region
    strict_chain_merge: bool = False  # see extract_traces_in_region
    split_on_x_reversal: bool = False  # see extract_traces_in_region
    reversal_run_length: int = 5  # see extract_traces_in_region
    # Escape hatch for charts where curve identity varies by END-X position,
    # not end-y (e.g. Ilford Multigrade's grade-number labels, all sitting at
    # nearly the SAME y on a shared shoulder plateau, spread out along x
    # instead) -- assign_traces_to_labels_exclusive's rank-by-y primary
    # strategy can't discriminate labels that are all at the same height.
    # When set (a list of `chart.curves` names in ascending-max-x order),
    # digitize_chart ranks the extracted traces by their own max x instead of
    # doing any label-position matching at all -- see
    # `assign_traces_by_x_rank()`. Mutually exclusive with `label_regex`/
    # `label_position_override` in practice (whichever runs, runs instead of
    # the other), but nothing enforces that; don't set both for one chart.
    rank_assignment_names: list[str] | None = None
    rank_at_y: float | None = None  # see assign_traces_by_x_rank -- page-space y, not calibrated value
    # Strategy E (vector_fill_band) only -- see extract_fill_band_curves().
    # `chart.curves` order = rank order (curves[0] = topmost/highest-value
    # band member, etc).
    fill_band_rgb: tuple[float, float, float] | None = None
    fill_band_tol: float = 0.02
    fill_band_exclude_bboxes: list = field(default_factory=list)
    fill_band_gap: float = 2.0
    fill_band_min_width: float | None = None
    # Free-form per-chart provenance (e.g. {"developer": "D-76", "process":
    # "Large Tank, 20C (68F)", "densitometry": "Diffuse Visual"}) -- for
    # products with several panels of the SAME chart type (e.g. one B&W
    # film's several developer panels), each needs its own real metadata
    # rather than sharing one product-level note. Passed straight through to
    # the output JSON's charts.<chart_id>.metadata by product.py.
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Axis calibration (shared by all 3 strategies)
# ---------------------------------------------------------------------------

def fit_axis(words, tick_regex, axis, bbox=None, auto_cluster=True, cluster_tol=6):
    """axis: 'x' or 'y'. Returns (slope, intercept) mapping pixel coordinate
    -> data value, fit by least squares over all tick labels matched by
    tick_regex (robust to any single mis-picked token). `bbox`, if given,
    restricts candidate words to those centered inside it -- needed on
    multi-panel pages where more than one mini-chart shares a tick format
    (e.g. several panels each having a "0.0" tick).

    If `auto_cluster` is set (default), candidates are further narrowed to
    the single largest cluster sharing (nearly) the same coordinate on the
    OTHER axis -- real tick labels for one axis all sit in one row (constant
    y, for x-axis ticks) or one column (constant x, for y-axis ticks), so
    this rejects stray same-format numbers elsewhere on the page/panel (e.g.
    the other axis's own ticks, when both axes happen to use the same
    "N.0"-style format) without needing a hand-tuned bbox that separates them.
    """
    candidates = []  # (px, other_coord, val)
    for x0, y0, x1, y1, text, *_ in words:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if bbox is not None and not (bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]):
            continue
        # Some PDFs (confirmed on several Fuji sheets) print the negative
        # tick's minus sign as a real Unicode en-dash/minus (U+2013/U+2212),
        # not ASCII hyphen -- neither `tick_regex` (written with a plain "-")
        # nor Python's float() recognize those, so every negative tick would
        # otherwise silently vanish from the candidate pool (not raise; it
        # just leaves too few candidates, surfacing as a confusing "only
        # found N tick labels" error pointing nowhere near the real cause).
        # Normalizing here is safe: no legitimate tick text uses these
        # characters for anything other than a minus sign.
        text_norm = text.replace("–", "-").replace("−", "-")
        if not re.fullmatch(tick_regex, text_norm):
            continue
        try:
            val = float(text_norm)
        except ValueError:
            continue
        px, other = (cx, cy) if axis == "x" else (cy, cx)
        candidates.append((px, other, val))

    if not candidates:
        raise RuntimeError(f"only found 0 tick labels matching {tick_regex!r}"
                            + (f" within bbox {bbox}" if bbox else ""))

    if auto_cluster and len(candidates) > 2:
        order = sorted(range(len(candidates)), key=lambda i: candidates[i][1])
        clusters, cur = [], [order[0]]
        for i in order[1:]:
            if abs(candidates[i][1] - candidates[cur[-1]][1]) <= cluster_tol:
                cur.append(i)
            else:
                clusters.append(cur)
                cur = [i]
        clusters.append(cur)
        best = max(clusters, key=len)
        candidates = [candidates[i] for i in best]

        # A same-row neighboring panel's own axis numbers can coincidentally
        # share this panel's tick-row height (grid layouts often align rows),
        # slipping through the check above. Two failure shapes seen in
        # practice: (a) an interloper far away in pixel space (a big gap), or
        # (b) an interloper pixel-CLOSE to a real tick -- e.g. the y-axis's
        # own "0.0" label sits near the x-axis row's leftmost tick, since
        # both axes cross near the same corner -- which a pure gap check
        # doesn't catch (the gap to it looks unremarkable) but which is
        # obviously wrong once you look at the local slope (value-per-pixel)
        # it implies. Filter on local slope consistency instead of gap size:
        # real ticks form one arithmetic progression, so consecutive pairs
        # should all imply nearly the same slope; keep the longest run of
        # points consistent with the median pairwise slope.
        if len(candidates) > 2:
            by_px = sorted(candidates, key=lambda c: c[0])
            pair_slopes = []
            for i in range(len(by_px) - 1):
                dpx = by_px[i + 1][0] - by_px[i][0]
                if dpx > 0:
                    pair_slopes.append((by_px[i + 1][2] - by_px[i][2]) / dpx)
            if pair_slopes:
                med_slope = sorted(pair_slopes)[len(pair_slopes) // 2]
                tol = max(abs(med_slope) * 0.4, 1e-6)
                segments, cur = [[by_px[0]]], 0
                for i in range(len(by_px) - 1):
                    dpx = by_px[i + 1][0] - by_px[i][0]
                    local_slope = (by_px[i + 1][2] - by_px[i][2]) / dpx if dpx > 0 else float("inf")
                    if abs(local_slope - med_slope) > tol:
                        segments.append([])
                    segments[-1].append(by_px[i + 1])
                candidates = max(segments, key=len)

    pixels = [c[0] for c in candidates]
    values = [c[2] for c in candidates]
    if len(pixels) < 2:
        raise RuntimeError(f"only found {len(pixels)} tick labels matching {tick_regex!r} after clustering")
    slope, intercept = np.polyfit(pixels, values, 1)

    # A merged-in second tick column/row (e.g. a neighboring panel's ticks
    # that weren't excluded by bbox/clustering) fits a wrong-but-plausible
    # single line through both -- the giveaway is that the *residuals* from
    # that single fit are large relative to the tick spacing, even though
    # `auto_cluster`/gap-trimming didn't reject it as a separate group. This
    # doesn't raise (a real caller may have deliberately mixed something),
    # but it's loud on purpose -- this exact failure mode produced a real,
    # silently-wrong-by-10x calibration before this check existed.
    if len(pixels) >= 3:
        predicted = [slope * p + intercept for p in pixels]
        resid = [abs(pr - v) for pr, v in zip(predicted, values)]
        step = abs(values[1] - values[0]) if values[0] != values[1] else 1.0
        if max(resid) > 0.4 * max(abs(v) for v in values if v != 0):
            print(f"  CALIBRATION WARNING: tick fit for {tick_regex!r} has large residuals "
                  f"{[round(r, 3) for r in resid]} against ticks {list(zip([round(p,1) for p in pixels], values))} "
                  f"-- possible merged/contaminated tick columns from two different panels")
    return slope, intercept, list(zip(pixels, values))


def in_bbox(pt, bbox):
    if bbox is None:
        return False
    x0, y0, x1, y1 = bbox
    return x0 <= pt.x <= x1 and y0 <= pt.y <= y1


# ---------------------------------------------------------------------------
# Strategy A: vector, curves distinguished by fill color
# ---------------------------------------------------------------------------

def extract_curve_points_by_fill(page, fill_rgb, tol, legend_bbox):
    pts = []
    for d in page.get_drawings():
        fill = d.get("fill")
        if fill is None or any(abs(fill[i] - fill_rgb[i]) > tol for i in range(3)):
            continue
        for item in d["items"]:
            for p in item[1:]:
                if hasattr(p, "x") and not in_bbox(p, legend_bbox):
                    pts.append((p.x, p.y))
    return pts


# ---------------------------------------------------------------------------
# Strategy B: vector, curves distinguished by stroke color/dash/width
# ---------------------------------------------------------------------------

def extract_curve_points_by_stroke(page, stroke_rgb, tol, dash_regex, width, width_tol, legend_bbox,
                                    region_bbox=None):
    """`region_bbox` (optional, page-space (x0,y0,x1,y1)): restricts matched
    points to this region. Unlike Strategy D's `extract_traces_in_region`,
    color/dash/width alone were assumed sufficiently distinctive on their
    own -- true for every Kodak chart so far, since each one is the only
    chart on its page using that ink style. Confirmed false on Fuji's
    reversal-film template (Velvia 100 etc, 2026-07-05): plain black,
    width~1.0, dash=[] also matches gridlines/frame elements AND unrelated
    drawings elsewhere on the SAME page (e.g. the Spectral Sensitivity
    panel two inches over uses the same generic black ink) -- without a
    region restriction, points from a completely different chart bleed
    into this one. Defaults to None (no restriction) so every existing
    Kodak ChartSpec keeps its current behavior unchanged."""
    pts = []
    for d in page.get_drawings():
        color = d.get("color")
        if color is None or any(abs(color[i] - stroke_rgb[i]) > tol for i in range(3)):
            continue
        if dash_regex is not None and not re.search(dash_regex, d.get("dashes", "") or ""):
            continue
        if width is not None:
            dw = d.get("width")
            if dw is None or abs(dw - width) > width_tol:
                continue
        for item in d["items"]:
            for p in item[1:]:
                if not hasattr(p, "x") or in_bbox(p, legend_bbox):
                    continue
                if region_bbox is not None and not in_bbox(p, region_bbox):
                    continue
                pts.append((p.x, p.y))
    return pts


# ---------------------------------------------------------------------------
# Strategy C: raster, curves distinguished by traced pixel color
# ---------------------------------------------------------------------------

def locate_raster_chart_rect(page, image_index=0):
    """Returns the page-space Rect where the image_index-th embedded image on
    this page is placed, plus its xref. Raises if the page has no images or
    the index is out of range."""
    images = page.get_images(full=True)
    if not images:
        raise RuntimeError("page has no embedded images")
    if image_index >= len(images):
        raise RuntimeError(f"page only has {len(images)} embedded image(s), index {image_index} requested")
    xref = images[image_index][0]
    rects = page.get_image_rects(xref)
    if not rects:
        raise RuntimeError(f"image xref {xref} has no placement rect on this page")
    return rects[0], xref


def extract_curve_points_from_raster(page, clip_rect, pixel_rgb, pixel_tol, dpi_scale, legend_bbox, stride=1):
    """Traces pixels matching pixel_rgb (0..255 ints) within clip_rect (page
    coordinates) by rendering a cropped high-DPI pixmap, and returns matching
    pixel centers converted back into page-point coordinates -- the same
    coordinate space fit_axis() calibrates against, so downstream code doesn't
    need to know these points came from a raster instead of a vector path."""
    mat = fitz.Matrix(dpi_scale, dpi_scale)
    pix = page.get_pixmap(matrix=mat, clip=clip_rect)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    r, g, b = pixel_rgb
    mask = (
        (np.abs(arr[:, :, 0].astype(int) - r) <= pixel_tol)
        & (np.abs(arr[:, :, 1].astype(int) - g) <= pixel_tol)
        & (np.abs(arr[:, :, 2].astype(int) - b) <= pixel_tol)
    )
    ys, xs = np.nonzero(mask)
    if stride > 1:
        xs, ys = xs[::stride], ys[::stride]
    page_x = clip_rect.x0 + xs / dpi_scale
    page_y = clip_rect.y0 + ys / dpi_scale
    pts = []
    for px, py in zip(page_x, page_y):
        p = fitz.Point(px, py)
        if not in_bbox(p, legend_bbox):
            pts.append((px, py))
    return pts


# ---------------------------------------------------------------------------
# Strategy E: vector, curves drawn as many small FILLED polygon fragments (a
# bold-ink outline) rather than a single stroked path -- one fragment per
# curve per narrow x-slice ("band"), confirmed (Ilford Ortho Plus, 2026-07-07)
# via direct item dump: each fragment traces up one side of a thick ribbon
# and back down the other (a closed quad outline around a segment of the
# real curve), not a centerline. extract_traces_in_region (Strategy D) only
# follows stroked paths and finds nothing here except gridlines/frame.
# ---------------------------------------------------------------------------

def extract_fill_band_curves(page, fill_rgb, tol, region_bbox, exclude_bboxes, n_curves, band_gap=2.0,
                              min_fragment_width=None):
    """Collects filled-polygon drawings matching fill_rgb whose CENTER falls
    inside region_bbox and outside every box in exclude_bboxes (typically
    vector-drawn gamma-value legend text sitting inside the same plot area --
    these render as filled letterform shapes too, indistinguishable from
    curve ink by color alone, so must be excluded by position), sorts by
    left edge (x0), and greedily groups into "bands" wherever consecutive
    fragments' x0 are within band_gap of each other (real bands are ~20pt
    wide with ~20pt gaps between them; band members' x0 sit within ~1pt of
    each other, confirmed by direct inspection -- band_gap's default is
    deliberately far below the real inter-band gap, not a delicate
    tuning knob).

    `min_fragment_width` (optional): an additional, more robust filter than
    exclude_bboxes alone -- confirmed (Ilford Ortho Plus High Contrast
    panel, 2026-07-07) that real curve-band fragments are consistently wide
    (~18-20pt, one x-slice of ribbon) while label GLYPH fragments are all
    narrow (<10pt, a single character), even where a label sits close
    enough to a curve that a position-only exclude_bbox would need to be
    drawn so tight it risks clipping a real curve fragment that happens to
    pass through the same small area (confirmed: one real curve fragment
    was being silently dropped this way before this filter was added, only
    caught via QA overlay showing the curve stop short of its real end).
    When set, any fragment narrower than this (by x1-x0) is dropped before
    exclude_bboxes/banding, regardless of position.

    Within each band, fragments are ranked by mean-y ascending (smaller y =
    higher on the page = higher value on every chart in this project so
    far) and assigned to the n_curves output lists by that rank -- caller's
    chart.curves order must match this rank order (curves[0] = topmost).
    Returns a list of n_curves point-lists, each holding ALL of its
    fragments' own vertices (not reduced to one point per fragment) -- the
    two rails of each fragment's ribbon outline get collapsed into a
    centerline downstream by the ordinary bin_average() x-binning already
    used to smooth noisy stroke traces, no separate rail-averaging logic
    needed."""
    fills = []
    for d in page.get_drawings():
        if d.get("type") != "f":
            continue
        fill = d.get("fill")
        if fill is None or any(abs(fill[i] - fill_rgb[i]) > tol for i in range(3)):
            continue
        r = d["rect"]
        if min_fragment_width is not None and (r.x1 - r.x0) < min_fragment_width:
            continue
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        if not (region_bbox[0] <= cx <= region_bbox[2] and region_bbox[1] <= cy <= region_bbox[3]):
            continue
        if any(bx0 <= cx <= bx2 and by0 <= cy <= by2 for (bx0, by0, bx2, by2) in exclude_bboxes):
            continue
        pts = [(p.x, p.y) for item in d["items"] for p in item[1:] if hasattr(p, "x")]
        if not pts:
            continue
        fills.append((r.x0, sum(p[1] for p in pts) / len(pts), pts))
    fills.sort(key=lambda f: f[0])
    bands = []
    for f in fills:
        if bands and f[0] - bands[-1][-1][0] < band_gap:
            bands[-1].append(f)
        else:
            bands.append([f])
    curves = [[] for _ in range(n_curves)]
    for band in bands:
        band_sorted = sorted(band, key=lambda f: f[1])
        for rank, f in enumerate(band_sorted[:n_curves]):
            curves[rank].extend(f[2])
    return curves


# ---------------------------------------------------------------------------
# Strategy D: vector, several same-ink curves in one panel distinguished by
# position (connected-path identity) + a nearby inline text label, not color
# ---------------------------------------------------------------------------

def _flatten_path_item(item, samples_per_unit_length=0.25, min_samples=2, max_samples=64):
    """Returns an item's real points ON the path, in drawing order. For a
    cubic Bezier segment (PyMuPDF's own item shape: `("c", p0, p1, p2,
    p3)` -- start, ctrl1, ctrl2, end), evaluates the true parametric curve
    instead of returning the 4 raw tuple entries as-is: p1/p2 are CONTROL
    points, generally NOT on the actual curve, and treating them as literal
    traced samples silently corrupts the curve's shape wherever it's
    genuinely drawn as a Bezier arc.

    Confirmed as a real bug (2026-08-03) on Ilford HP5 Plus's
    Characteristic Curve: unlike most Kodak charts (drawn as long,
    finely-segmented polylines -- 200+ raw "l" points for a single curve),
    this chart is drawn as just 3 long cubic Bezier segments. The QA
    overlay visibly cut a corner through the toe -- traced back to a
    control point (the curve's 2nd Bezier segment's own ctrl1, sitting
    well off the true curve, close to the segment's start density) getting
    appended as if it were a real digitized point. Every other item type
    ("l", "re", ...) is returned unchanged -- this only ever adds real
    curve samples, never removes or moves existing ones, so it's a strict
    improvement with no regression risk for polyline-drawn curves (a
    straight "l" segment's own true shape already IS its 2 endpoints).

    Sample COUNT scales with the segment's own size (its control-polygon
    length |p0-p1|+|p1-p2|+|p2-p3|, a standard cheap upper bound on true
    arc length) rather than a fixed count per segment -- a real, shipped
    regression on the very first attempt (a flat n_bezier_samples=16)
    broke Kodak Tri-X's own D-76 11min curve: some chart's small
    decorative marks (confirmed: 4-segment closed loops ~1-1.5 page-units
    across, almost certainly a bullet/tick glyph near a label) went from 4
    raw points/segment (16 total, safely below that chart's own
    min_trace_points=50 filter) to 16 samples/segment (64 total) under a
    flat sample count, crossing the threshold and getting picked up as a
    spurious candidate curve, corrupting the real curve-to-label
    assignment -- exactly the "small fragment mistaken for a real trace"
    failure mode this project's own CLAUDE.md already documents from
    before Bezier support existed at all. Scaling samples by the
    segment's own real length keeps a tiny decoration at (or near)
    min_samples while a long curve segment (HP5 Plus's are 20-100+ page
    units) still gets properly densely sampled -- the same size-implies-
    density relationship a hand-drawn polyline already has for free."""
    raw = [p for p in item[1:] if hasattr(p, "x")]
    if item[0] != "c" or len(raw) != 4:
        return raw
    p0, p1, p2, p3 = raw
    poly_len = (math.hypot(p1.x - p0.x, p1.y - p0.y)
                + math.hypot(p2.x - p1.x, p2.y - p1.y)
                + math.hypot(p3.x - p2.x, p3.y - p2.y))
    n = max(min_samples, min(max_samples, round(poly_len * samples_per_unit_length) + 1))
    out = []
    for i in range(n):
        t = i / (n - 1)
        mt = 1 - t
        x = mt**3 * p0.x + 3 * mt**2 * t * p1.x + 3 * mt * t**2 * p2.x + t**3 * p3.x
        y = mt**3 * p0.y + 3 * mt**2 * t * p1.y + 3 * mt * t**2 * p2.y + t**3 * p3.y
        out.append(fitz.Point(x, y))
    return out


def extract_traces_in_region(page, region_bbox, min_points=12, stroke_rgb=None, tol=0.15, continuity_tol=1.5,
                              cross_object_merge=False, merge_strategy="proximity", merge_tol_multiplier=6,
                              strict_chain_merge=False, split_on_x_reversal=False, reversal_run_length=5):
    """Returns a list of distinct curve traces (each a list of (x,y) page-space
    points) confined to region_bbox, filtering out short chart-furniture
    drawings (axis frame, tick marks, gridlines, legend swatches) via a
    minimum vertex-count threshold.

    Most of these multi-panel monochrome charts draw each curve as its own
    PDF drawing object, but some (seen on older Kodak sheets, e.g. Gold
    100/200's single-page-per-speed layout) draw several curves as ONE
    object -- the pen jumps from one curve's end to the next curve's start
    without lifting. Splitting purely by drawing-object identity would then
    merge unrelated curves into one trace, so each object's own item sequence
    is further split wherever consecutive segments don't join up (a gap
    bigger than `continuity_tol`), which is what a real pen-lift/jump reads
    as positionally.

    `split_on_x_reversal` (opt-in): handles a DIFFERENT fusion mechanism,
    confirmed on f9-Tri-X_Pan.pdf's TXP/HC-110 panel (the "6.25min" curve):
    two curves whose toes happen to converge at nearly the same point can
    get drawn as one truly continuous path -- the pen finishes curve A
    shoulder-to-toe, then, because there's no real position gap at that
    shared point, continues straight into curve B toe-to-shoulder without a
    lift. `continuity_tol` alone can't catch this (there IS no gap to
    detect); what's detectable is that the path's x-direction of travel
    reverses and STAYS reversed -- real characteristic curves are drawn
    monotonically in x, so a sustained reversal (`reversal_run_length`
    consecutive same-sign deltas in the new direction, filtering out
    single-point digitization noise near a flat toe) means a second curve
    has started. Not a safe default: some genuinely single curves could
    have an intentional local x reversal (none seen in this corpus so far,
    but not provably impossible), so this stays opt-in per file."""
    x0, y0, x1, y1 = region_bbox
    raw_subtraces = []
    for d in page.get_drawings():
        color = d.get("color")
        if color is None:
            continue
        if stroke_rgb is not None and any(abs(color[i] - stroke_rgb[i]) > tol for i in range(3)):
            continue
        cur, prev_end = [], None
        pending_sign = 0  # sign of x-travel accumulated in `cur` so far, once established
        run_sign, run_len = 0, 0  # tracks a candidate direction reversal in progress
        for item in d["items"]:
            pts = _flatten_path_item(item)
            if not pts:
                continue
            if prev_end is not None and (abs(pts[0].x - prev_end[0]) > continuity_tol
                                          or abs(pts[0].y - prev_end[1]) > continuity_tol):
                if cur:
                    raw_subtraces.append(cur)
                cur = []
                pending_sign, run_sign, run_len = 0, 0, 0
            for p in pts:
                if prev_end is not None and split_on_x_reversal:
                    dx = p.x - prev_end[0]
                    s = 1 if dx > 1e-6 else (-1 if dx < -1e-6 else 0)
                    if s != 0:
                        if pending_sign == 0:
                            pending_sign = s
                        elif s != pending_sign:
                            if s == run_sign:
                                run_len += 1
                            else:
                                run_sign, run_len = s, 1
                            if run_len >= reversal_run_length:
                                split_at = len(cur) - (run_len - 1)
                                if split_at > 0 and cur[:split_at]:
                                    raw_subtraces.append(cur[:split_at])
                                cur = cur[split_at:]
                                pending_sign, run_sign, run_len = s, 0, 0
                        else:
                            run_sign, run_len = 0, 0
                cur.append((p.x, p.y))
                prev_end = (p.x, p.y)
        if cur:
            raw_subtraces.append(cur)

    # Some PDFs draw one curve as several separate drawing objects rather
    # than one continuous path (or one object with internal subpaths, the
    # case just handled above) -- e.g. a short segment per grid interval.
    # OPT-IN ONLY (cross_object_merge=True): repeatedly merge any two
    # fragments whose endpoints nearly touch, regardless of which drawing
    # object they came from, before filtering by size. NOT safe as a
    # default -- a purely proximity-based merge also happily fuses two
    # DIFFERENT curves' fragments where they happen to converge (e.g. a
    # toe/shoulder where several curves nearly touch), which silently wiped
    # out correct results on Royal Gold 400/200 and others when tried as
    # the default. Only enable this for a specific file after confirming
    # (via QA overlay) it actually needs it.
    merged = list(raw_subtraces)
    if cross_object_merge and merge_strategy == "proximity":
        # Restrict merge candidates to fragments already (mostly) inside
        # this panel's own bbox -- a real page can have 50+ raw drawing
        # fragments total (axis ticks, other panels' curves, chart borders),
        # and running the union-find over ALL of them let a chain distance
        # match transitively bridge two truly-unrelated in-panel curves
        # through some THIRD fragment outside the panel entirely (confirmed
        # on e4030.pdf: two separate, already-complete Endura curves got
        # silently fused this way even after the same-endpoint-pair checks
        # below were tightened, because the actual bridge wasn't a direct
        # pair between them but a transitive one through an out-of-panel
        # fragment). Filtering to in-panel fragments first removes those
        # irrelevant bridges without changing anything for charts that
        # don't have this problem.
        # NOTE: the size floor here is deliberately much lower than
        # min_points -- min_points is the POST-merge threshold (a real
        # curve's own many tiny fragments, e.g. Elite Color 200/400's ~40
        # pieces, are each individually far smaller than min_points and only
        # exceed it once merged). This floor only needs to reject true
        # single/near-single-point noise (stray dashes, artifacts), not
        # legitimate small fragments awaiting merge -- confirmed regression
        # when this was first set to min_points: it excluded every one of
        # Elite Color's own curve fragments from merge candidacy entirely.
        # ONLY applied when strict_chain_merge is also on: restricting to
        # in-panel fragments is itself a behavior change from the original
        # unrestricted scan, and confirmed (Elite Color 200/400) that when
        # combined with the size floor it can still drop legitimate
        # candidates in ways the original scan didn't -- keep both the
        # in-panel restriction and the chain-only/x-disjoint restrictions
        # bundled under the one opt-in flag rather than risk the default
        # (lenient, unrestricted) path for every file that already works.
        if strict_chain_merge:
            in_panel_idx = [
                i for i, tr in enumerate(merged)
                if len(tr) >= 4
                and len([p for p in tr if x0 <= p[0] <= x1 and y0 <= p[1] <= y1]) >= 0.8 * len(tr)
            ]
        else:
            in_panel_idx = list(range(len(merged)))
    if cross_object_merge and merge_strategy == "proximity":
        # Single-pass union-find by endpoint proximity (any of the 4
        # start/end combinations), O(n^2) once -- downstream code
        # (bin_average, in digitize_chart) sorts every trace's points by x
        # before use, so merge order within a group doesn't matter, only
        # which fragments belong together. (A previous version restarted an
        # O(n^2) scan after every single merge, effectively O(n^3) --
        # measured multi-minute runtime on files with ~40 fragments.)
        merge_tol = continuity_tol * merge_tol_multiplier
        n = len(merged)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        endpoints = [(tr[0], tr[-1]) for tr in merged]
        # `strict_chain_merge=True` (opt-in, see extract_traces_in_region's
        # own parameter) adds two restrictions confirmed necessary on the
        # Endura display-material papers (e4030/e4034/e4047), each of which
        # splits one dye layer into exactly 2 large x-disjoint fragments
        # (which SHOULD merge) while the other 2 layers are already-complete
        # single fragments spanning the FULL x-range:
        # (1) reject merging two fragments whose x-ranges substantially
        #     overlap -- a real split-in-two curve's fragments are x-disjoint
        #     by construction, so requiring this targets "these are
        #     sequential pieces of one curve" specifically;
        # (2) only the two "chain" endpoint combinations (one fragment's END
        #     meeting the other's START) count, not start-start/end-end --
        #     two distinct PARALLEL curves on the same chart commonly START
        #     near each other and END near each other (confirmed: two
        #     already-complete, unrelated Endura curves shared a start point
        #     ~1.7pt apart and an end point ~1.5pt apart purely because both
        #     span the same x-range with a similar y-offset, not because
        #     they're fragments of one curve).
        # NOT the default: Elite Color 200/400 and Ektapan's own ~20-45
        # tiny same-curve fragments sometimes have slightly overlapping
        # x-ranges (adjacent segments' endpoints don't land at exactly the
        # same x), and confirmed regressed to near-total non-merging when
        # strict_chain_merge's restrictions were tried as the unconditional
        # default -- keep this opt-in per file, only where confirmed needed.
        x_ranges = [(min(p[0] for p in tr), max(p[0] for p in tr)) for tr in merged]
        for ii in range(len(in_panel_idx)):
            i = in_panel_idx[ii]
            sa, ea = endpoints[i]
            xi0, xi1 = x_ranges[i]
            for jj in range(ii + 1, len(in_panel_idx)):
                j = in_panel_idx[jj]
                sb, eb = endpoints[j]
                xj0, xj1 = x_ranges[j]
                if strict_chain_merge:
                    overlap = min(xi1, xj1) - max(xi0, xj0)
                    smaller_width = min(xi1 - xi0, xj1 - xj0)
                    if smaller_width > 0 and overlap > 0.5 * smaller_width:
                        continue
                chain_match = (math.hypot(ea[0] - sb[0], ea[1] - sb[1]) <= merge_tol
                               or math.hypot(eb[0] - sa[0], eb[1] - sa[1]) <= merge_tol)
                symmetric_match = (not strict_chain_merge and (
                    math.hypot(sa[0] - sb[0], sa[1] - sb[1]) <= merge_tol
                    or math.hypot(ea[0] - eb[0], ea[1] - eb[1]) <= merge_tol))
                if chain_match or symmetric_match:
                    union(i, j)

        groups = {}
        for i in range(n):
            groups.setdefault(find(i), []).append(i)
        merged = [sum((merged[i] for i in idxs), []) for idxs in groups.values()]
    elif cross_object_merge and merge_strategy == "sequential_band":
        # For sheets where several curves are BOTH heavily fragmented AND
        # converge tightly somewhere in their range (confirmed on
        # paper/kodak/e4021.pdf's Portra/Supra Endura panels: ~50 fragments,
        # 3 curves, each ~9px wide, R/G/B converging hard near the shoulder)
        # -- there, proximity-based union-find fuses different curves'
        # fragments right where they're closest, corrupting the result
        # (confirmed: only 1 of 3 curves survived). Fragments here are
        # already naturally grouped into narrow x-bands (one fragment per
        # curve per band, since the source PDF drew each curve as a chain of
        # tiny same-width segments) -- within each band, chain each fragment
        # to whichever curve's running trace has the CLOSEST mean-y so far
        # (nearest-neighbor continuation, not absolute proximity), which
        # tracks smoothly through a near-convergence because it's a LOCAL
        # comparison against each chain's own trajectory, not a global
        # distance threshold blind to which curve is which.
        bands = {}
        for tr in merged:
            if len(tr) < min_points:
                continue  # noise fragment (a stray dot/vertex) -- would spawn a bogus extra chain
            inside = [p for p in tr if x0 <= p[0] <= x1 and y0 <= p[1] <= y1]
            if len(inside) < 0.8 * len(tr):
                continue  # outside this panel's box entirely -- would corrupt band grouping
            band_x = round(min(p[0] for p in inside))
            bands.setdefault(band_x, []).append(inside)
        band_keys = sorted(bands)
        if not band_keys:
            merged = []
        else:
            chains = [[frag] for frag in bands[band_keys[0]]]
            for k in band_keys[1:]:
                frags = bands[k]
                frag_y = [sum(p[1] for p in f) / len(f) for f in frags]
                chain_y = [sum(p[1] for p in ch[-1]) / len(ch[-1]) for ch in chains]
                pairs = sorted(
                    ((abs(cy - fy), ci, fi) for ci, cy in enumerate(chain_y) for fi, fy in enumerate(frag_y)),
                )
                used_c, used_f = set(), set()
                for _, ci, fi in pairs:
                    if ci in used_c or fi in used_f:
                        continue
                    chains[ci].append(frags[fi])
                    used_c.add(ci)
                    used_f.add(fi)
                for fi in range(len(frags)):
                    if fi not in used_f:
                        chains.append([frags[fi]])
            merged = [sum(ch, []) for ch in chains]
    traces = []
    for sub in merged:
        if sub is None or len(sub) < min_points:
            continue
        inside = [p for p in sub if x0 <= p[0] <= x1 and y0 <= p[1] <= y1]
        if len(inside) < 0.8 * len(sub):
            continue
        traces.append(inside)
    return traces


def find_label_position(words, label_regex, bbox=None):
    """Returns the (cx, cy) center of the first text word matching
    label_regex (optionally restricted to words centered inside bbox), or
    None if not found. Multi-line labels (e.g. "Yellow-\\nForming\\nLayer")
    are matched one line/word at a time -- pass a regex matching just one of
    the lines (the one closest to the curve is usually enough)."""
    for x0, y0, x1, y1, text, *_ in words:
        if bbox is not None:
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if not (bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]):
                continue
        if re.search(label_regex, text):
            return ((x0 + x1) / 2, (y0 + y1) / 2)
    return None


def locate_panel_bboxes(page, title_regexes, margin=8, content_pad=50, page_rect=None, search_bbox=None):
    """Kodak's multi-panel sheets lay several mini-charts (Characteristic
    Curves, Spectral-Sensitivity Curves, ...) out in a grid on one page, each
    headed by a bold title. Given the set of title regexes expected on this
    page, finds each title's position, clusters them into grid rows/columns,
    and returns {title_regex: (x0, y0, x1, y1)} bboxes running from each
    title's own row/column start to the next row/column's start (or the page
    edge for the last one) -- so every panel's plot area, ticks, and inline
    curve labels fall inside its own bbox and no one else's.
    """
    if page_rect is None:
        page_rect = page.rect
    words = page.get_text("words")
    if search_bbox is not None:
        sx0, sy0, sx1, sy1 = search_bbox
        words = [w for w in words if sx0 <= (w[0] + w[2]) / 2 <= sx1 and sy0 <= (w[1] + w[3]) / 2 <= sy1]
    # A title word can also appear again lower on the page (body text
    # discussing the same chart, a caption, a footnote) -- get_text("words")
    # isn't guaranteed to return matches in top-to-bottom reading order, so
    # picking the first hit can grab a mention far from the real heading.
    # The real heading is reliably the topmost (smallest y0) occurrence.
    positions = {}
    for tregex in title_regexes:
        best = None
        for x0, y0, x1, y1, text, *_ in words:
            if re.search(tregex, text) and (best is None or y0 < best[1]):
                best = (x0, y0, x1, y1)
        if best is not None:
            positions[tregex] = best
    if not positions:
        raise RuntimeError(f"none of {title_regexes} found on page")

    xs = sorted({round(p[0]) for p in positions.values()})
    ys = sorted({round(p[1]) for p in positions.values()})

    def cluster(vals, tol=15):
        clusters = []
        for v in vals:
            if clusters and abs(v - clusters[-1][-1]) <= tol:
                clusters[-1].append(v)
            else:
                clusters.append([v])
        return [sum(c) / len(c) for c in clusters]

    col_starts = cluster(xs)
    row_starts = cluster(ys)

    bboxes = {}
    for tregex, (tx0, ty0, tx1, ty1) in positions.items():
        col_i = min(range(len(col_starts)), key=lambda i: abs(col_starts[i] - tx0))
        row_i = min(range(len(row_starts)), key=lambda i: abs(row_starts[i] - ty0))
        bx0 = col_starts[col_i] - margin
        bx1 = col_starts[col_i + 1] - margin if col_i + 1 < len(col_starts) else page_rect.width - margin
        by0 = ty1  # panel content starts right below its own title
        by1 = row_starts[row_i + 1] - margin if row_i + 1 < len(row_starts) else page_rect.height - margin
        # Widen only the left edge: a panel's own y-axis number labels commonly
        # print a bit left of its title-derived column start. Do NOT widen the
        # right/bottom edges -- a same-row neighbor's tick labels often sit at
        # nearly the same page height, so a right-side pad would pull in the
        # next panel's own axis numbers (this bit us: two side-by-side panels'
        # tick rows can coincide to within a few points vertically).
        bboxes[tregex] = (bx0 - content_pad, by0, bx1, by1)
    return bboxes


def axis_tick_bboxes(panel_bbox, tick_margin=45):
    """Given a panel's own content bbox (from locate_panel_bboxes), returns
    (x_tick_bbox, y_tick_bbox) sub-regions widened just enough to catch that
    panel's own axis number labels -- which print a bit outside the panel's
    plot frame, in the same direction on every one of these Kodak-style
    charts (numbers below the x-axis, numbers left of the y-axis)."""
    bx0, by0, bx1, by1 = panel_bbox
    x_tick_bbox = (bx0, by1 - tick_margin, bx1, by1 + tick_margin)
    y_tick_bbox = (bx0 - tick_margin, by0 - tick_margin // 2, bx0 + tick_margin, by1)
    return x_tick_bbox, y_tick_bbox


def assign_trace_to_label(traces, label_pos):
    """Returns the index of the trace with the point closest to label_pos --
    used to identify which same-ink path belongs to which curve, since these
    charts print a small label next to each curve instead of color-coding
    them. NOTE: when several curves in the same chart are nearly coincident
    near where their labels point (common near a toe/shoulder where curves
    converge), independently nearest-matching each label can pick the SAME
    trace for two different labels. Prefer assign_traces_to_labels_exclusive
    (used automatically by digitize_chart) when matching multiple labels
    against the same trace set."""
    best_i, best_d = None, float("inf")
    lx, ly = label_pos
    for i, tr in enumerate(traces):
        d = min(math.hypot(px - lx, py - ly) for px, py in tr)
        if d < best_d:
            best_d, best_i = d, i
    return best_i


def _interpolated_y_at_x(trace, x):
    """Linearly interpolates a trace's y value at a given x (trace need not
    be sorted; sorts a copy). Returns None if x is outside the trace's span."""
    pts = sorted(trace, key=lambda p: p[0])
    xs = [p[0] for p in pts]
    if x < xs[0] or x > xs[-1]:
        return None
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if x0 <= x <= x1:
            if x1 == x0:
                return y0
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return pts[-1][1]


def _dedupe_exact_traces(traces, tol=0.5):
    """Drops traces that are point-for-point duplicates of an earlier one in
    the list (same length, same endpoints and midpoint within `tol` pixels).
    Some source PDFs draw a panel's curves TWICE, exactly overlapping (e.g.
    f4012-Portra_400BW.pdf's Spectral-Dye-Density panel -- confirmed via
    direct trace dump: 4 traces extracted, but they were 2 real curves each
    duplicated once, byte-identical bounding boxes and point counts). Left
    undeduped, assign_traces_to_labels_exclusive can resolve two different
    labels to two copies of the SAME curve, silently losing the other real
    curve entirely -- this happened on Portra 400BW's d_min/midscale_neutral
    (both ended up with identical output ranges). No real distinct curve
    should ever be exactly point-for-point identical to another, so this is
    safe to apply unconditionally rather than gating it per-file."""
    kept = []
    for tr in traces:
        is_dup = False
        for seen in kept:
            if len(tr) != len(seen):
                continue
            i_mid, s_mid = tr[len(tr) // 2], seen[len(seen) // 2]
            if (abs(tr[0][0] - seen[0][0]) <= tol and abs(tr[0][1] - seen[0][1]) <= tol
                    and abs(tr[-1][0] - seen[-1][0]) <= tol and abs(tr[-1][1] - seen[-1][1]) <= tol
                    and abs(i_mid[0] - s_mid[0]) <= tol and abs(i_mid[1] - s_mid[1]) <= tol):
                is_dup = True
                break
        if not is_dup:
            kept.append(tr)
    return kept


def assign_traces_to_labels_exclusive(traces, label_positions: dict):
    """Assigns all of a chart's labels against the same trace pool at once,
    never reusing a trace for two labels.

    Primary strategy: RANK ORDER. These datasheets consistently stack a
    chart's inline labels in the same top-to-bottom order as the curves
    they name (e.g. "B" above "G" above "R", matching density order at
    that x) -- but the label TEXT is often offset from its curve by a
    roughly constant amount (a short implicit leader gap), which biases
    absolute-distance matching toward whichever curve is overall closest to
    the whole label cluster (confirmed wrong on e7013-HD400.pdf: all 3
    labels were nearest, in absolute terms, to the same top curve). Ranking
    each label by its own y and each trace by its interpolated y at the
    mean label x sidesteps a constant offset entirely, since rank is
    offset-invariant.
    Traces with no valid interpolation at that x (a short unrelated vector
    fragment -- a tick mark, leader line, etc. -- tucked somewhere its x-span
    doesn't reach the label cluster; confirmed on f10-Ektapan.pdf, two
    ~16-point artifacts) are excluded from the rank pool rather than
    disqualifying rank-matching for the WHOLE chart -- an earlier version
    required *every* trace to interpolate, so one unrelated fragment
    anywhere silently fell back to the offset-biased distance method for
    every label, which is exactly the bug rank-matching exists to avoid.
    Falls back to nearest-any-point distance only if fewer valid-interpolation
    traces remain than there are labels. Returns
    {label_name: trace_index_or_None}."""
    named = [(name, pos) for name, pos in label_positions.items() if pos is not None]
    if len(named) >= 2 and len(traces) >= len(named):
        mean_x = sum(pos[0] for _, pos in named) / len(named)
        trace_ys = [_interpolated_y_at_x(tr, mean_x) for tr in traces]
        valid = [i for i, y in enumerate(trace_ys) if y is not None]
        if len(valid) >= len(named):
            label_order = sorted(range(len(named)), key=lambda i: named[i][1][1])
            trace_order = sorted(valid, key=lambda i: trace_ys[i])
            assigned_label = {named[label_order[k]][0]: trace_order[k] for k in range(len(named))}
            return {name: assigned_label.get(name) for name in label_positions}

    candidates = []  # (distance, label_name, trace_index)
    for name, pos in named:
        lx, ly = pos
        for i, tr in enumerate(traces):
            y_at_x = _interpolated_y_at_x(tr, lx)
            if y_at_x is not None:
                d = abs(y_at_x - ly)
            else:
                d = min(math.hypot(px - lx, py - ly) for px, py in tr)
            candidates.append((d, name, i))
    candidates.sort(key=lambda c: c[0])
    assigned_trace, assigned_label = set(), {}
    for d, name, i in candidates:
        if name in assigned_label or i in assigned_trace:
            continue
        assigned_label[name] = i
        assigned_trace.add(i)
    return {name: assigned_label.get(name) for name in label_positions}


def _interpolated_x_at_y(trace, y):
    """Mirror of `_interpolated_y_at_x` -- linearly interpolates a trace's x
    at a given y (trace need not be sorted; sorts a copy by y). Returns
    None if y is outside the trace's span."""
    pts = sorted(trace, key=lambda p: p[1])
    ys = [p[1] for p in pts]
    if y < ys[0] or y > ys[-1]:
        return None
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if y0 <= y <= y1:
            if y1 == y0:
                return x0
            t = (y - y0) / (y1 - y0)
            return x0 + t * (x1 - x0)
    return pts[-1][0]


def assign_traces_by_x_rank(traces, ordered_names, rank_at_y=None):
    """For charts where curve identity is discriminated by END-X position
    rather than end-y -- confirmed on Ilford Multigrade's grade-curve chart
    (2026-07-06): all 7 grade labels sit at nearly the same y (a shared
    shoulder plateau where every curve reaches near-Dmax), spread out along
    x instead, the mirror image of what
    `assign_traces_to_labels_exclusive`'s rank-by-y primary strategy
    assumes. No label-position matching at all here (the grade-number
    labels are small, sit right on the crossing curve lines, and resisted
    reliable OCR even after Fuji's rotation-search/fuzzy-match approach) --
    physically justified instead: higher contrast grades are steeper, so
    they reach the shoulder plateau at a SMALLER x than lower grades,
    confirmed by direct visual inspection of the rendered chart (labels run
    in the same order as each curve's own max-x). `ordered_names` must
    already be in ascending-max-x-order (i.e. the same left-to-right order
    the real labels appear in).

    `rank_at_y` (recommended over the default): rank by each trace's
    INTERPOLATED x at this fixed y (page-space, pre-calibration) instead of
    raw max-x. Confirmed necessary on Multigrade's own 2-curve grade-4/5
    chart (2026-07-06): both curves converge to an identical shared
    plateau point, so their raw max-x values tied exactly (489.668 to 3
    decimals) -- the correct order only came out because Python's stable
    sort happened to preserve the right original extraction order, not
    because max-x actually discriminated them; a future file could easily
    tie the other way. Pick a y sitting in the STEEP/rising part of the
    curves (where they're visibly separated, before they converge to a
    shared toe or shoulder), not the plateau itself. Falls back to raw
    max-x for any trace where `rank_at_y` falls outside its span."""
    if len(traces) != len(ordered_names):
        raise RuntimeError(f"assign_traces_by_x_rank: {len(traces)} traces but "
                            f"{len(ordered_names)} names -- extraction likely picked up "
                            f"a noise fragment or dropped a real curve, check region_bbox/min_trace_points")
    if rank_at_y is not None:
        keys = [_interpolated_x_at_y(tr, rank_at_y) for tr in traces]
        keys = [k if k is not None else max(p[0] for p in traces[i]) for i, k in enumerate(keys)]
    else:
        keys = [max(p[0] for p in tr) for tr in traces]
    order = sorted(range(len(traces)), key=lambda i: keys[i])
    return {name: order[k] for k, name in enumerate(ordered_names)}


def _keep_widest_traces(traces, n):
    """Drops all but the `n` widest (by x-span) traces -- for dye-density panels whose
    auto-located `region_bbox` runs generously (e.g. defaulting to the page bottom when
    `locate_panel_bboxes` can't find a tight lower boundary) and ends up sweeping in an
    unrelated short fragment from further down the page (confirmed 2026-07-10 on several
    kodak_paper.py sheets, e.g. e19.pdf: 3 real dye curves each spanning the full ~184-unit
    wavelength axis, plus a 4th, unrelated 331-point trace spanning only ~90 units at a
    completely different y). The old plain label-regex matching silently tolerated this (it
    only ever needed to find 3 good candidates among however many traces existed); peak-x
    identification needs an exact count, so extras are filtered out first rather than each
    affected file needing its own hand-tightened box. Only fires when there are MORE than
    `n` traces -- never invents a missing one."""
    if len(traces) <= n:
        return traces
    widths = [max(p[0] for p in t) - min(p[0] for p in t) for t in traces]
    keep_idx = sorted(range(len(traces)), key=lambda i: -widths[i])[:n]
    keep_idx.sort()
    return [traces[i] for i in keep_idx]


def _safe_shared_x(traces, preferred_x):
    """Returns an x guaranteed to fall within EVERY given trace's own x-span, as close to
    `preferred_x` (e.g. the mean of some subset's peak-x's) as that constraint allows.
    `_interpolated_y_at_x` returns None for a trace whose x-span doesn't reach the query x --
    confirmed a real bug (2026-07-10, Kodak Vision3 500T's dye-density panel): one composite
    trace (a still-fragmented fifth-curve remnant, x-span only ~355-415 vs. the other 4's
    ~355-535+) didn't reach `preferred_x`, and the resulting `label_position_override` with a
    None y blew up downstream in assign_traces_to_labels_exclusive with a bare TypeError, not
    a clean error at the point of the actual mistake. Clamping into the intersection of every
    trace's x-range (falling back to `preferred_x` only if traces don't all overlap at all,
    which would indicate a deeper extraction problem, not a shared_x problem) avoids that
    silently or loudly, depending on which is more informative."""
    lo = max(min(p[0] for p in t) for t in traces)
    hi = min(max(p[0] for p in t) for t in traces)
    if lo <= hi:
        return min(max(preferred_x, lo), hi)
    return preferred_x


def curves_by_peak_x(pdf_path, page_index, panel_bbox, names_in_peak_x_order, min_trace_points=12,
                      cross_object_merge=False, merge_strategy="proximity"):
    """Builds CurveSpecs for a chart whose curves have well-separated peaks (each curve's own
    maximum, i.e. minimum page-pixel-y) but whose inline text labels sit on (or very near) one
    shared horizontal row -- e.g. a "Yellow  Magenta  Cyan" dye-density panel printed as one
    text line. `assign_traces_to_labels_exclusive`'s rank-by-label-y primary strategy
    degenerates to whatever a tied (or near-tied) stable-sort produces in this situation and
    silently returns a wrong swapped/rotated curve identity -- confirmed on every Fuji
    reversal-film Spectral-Dye-Density panel (Astia 100F, Velvia 100F, T64, Provia 400F,
    Provia 400X), Kodak's Ektachrome E100G/E100GX shared dye-density panel, AND (2026-07-10,
    discovered via an automated peak-position cross-check after a user-reported visual
    mismatch) the SAME rotated-identity bug on the vast majority of Kodak's own plain
    PAPER_DYE_DENSITY_LABELS/REVERSAL_DYE_DENSITY_LABELS-matched panels corpus-wide (61 of 74
    checked files, across kodak_paper.py/kodak_reversal.py/kodak_mp*.py) -- Kodak's own inline
    Yellow/Magenta/Cyan labels aren't usually EXACTLY tied in y the way Fuji's are, but close
    enough (single-digit-to-low-double-digit point differences) that the same rank-vs-shared-
    mean-x mismatch still fires. Not visually obvious from a QA overlay at a glance -- the
    traces still draw a smooth, plausible-looking curve, just under the wrong name; catching it
    requires tracing a specific curve's color back to its legend entry and checking it lands on
    the SAME page-printed label, not just "three smooth curves in roughly the right place."

    `names_in_peak_x_order` must already be in ascending real-peak-x order (left-to-right on
    the page) -- e.g. for a dye-density panel this is always `["yellow", "magenta", "cyan"]`
    (a real physical invariant: Yellow dye absorbs blue ~440-460nm, Magenta absorbs green
    ~530-560nm, Cyan absorbs red ~630-660nm).

    Fixed two-part: (1) identify each trace's real identity by its own peak x, sorted
    left-to-right to match `names_in_peak_x_order`. (2) Force
    `assign_traces_to_labels_exclusive`'s own rank-by-y step to reproduce that identity
    regardless of where its internal mean_x lands: every returned CurveSpec's
    `label_position_override` shares one x (so the algorithm's mean_x collapses to that same
    x) and its override y is set to that SPECIFIC trace's own real interpolated y AT that x
    (via `_interpolated_y_at_x`, the same helper the algorithm itself uses) -- ranking both
    labels and traces by values computed the same way guarantees a matching rank order by
    construction, unlike using each curve's own (very different-x) peak position directly,
    which is exactly what produces the original bug."""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    traces = extract_traces_in_region(page, panel_bbox, min_trace_points, cross_object_merge=cross_object_merge,
                                       merge_strategy=merge_strategy)
    doc.close()
    n = len(names_in_peak_x_order)
    traces = _keep_widest_traces(traces, n)
    if len(traces) != n:
        raise RuntimeError(f"curves_by_peak_x: expected {n} traces, got {len(traces)}")
    peak_x = [min(t, key=lambda p: p[1])[0] for t in traces]
    order = sorted(range(n), key=lambda i: peak_x[i])  # left-to-right trace index order
    shared_x = _safe_shared_x(traces, sum(peak_x) / n)
    return [CurveSpec(names_in_peak_x_order[rank],
                       label_position_override=(shared_x, _interpolated_y_at_x(traces[i], shared_x)))
            for rank, i in enumerate(order)]


def curves_by_peak_x_with_envelope(pdf_path, page_index, panel_bbox, names_in_peak_x_order, envelope_name,
                                    min_trace_points=12, cross_object_merge=False, merge_strategy="proximity"):
    """Extends `curves_by_peak_x` for a dye-density panel that ALSO plots the "Visual Neutral"
    composite curve (the sum/envelope of all 3 dye curves, forming a real 4th line that peaks
    higher than any individual dye and touches close to each one's own peak) -- confirmed on
    Kodak Ektachrome E100G/E100GX (3 of 4 curves labeled, Visual Neutral unlabeled) and
    Ektachrome 400X/EPL (all 4 unlabeled). A single global peak-x doesn't identify this curve
    the way it does Yellow/Magenta/Cyan, since the envelope has 3 local peaks (one riding atop
    each dye's own peak), not one -- it's identified instead by a different real invariant: it
    never drops as close to zero as the other 3 do away from their own peak (it's a sum of
    non-negative densities, so it can only be pulled down as far as the SMALLEST contributing
    dye at any wavelength, not to near-zero the way a lone dye curve does off its own peak) --
    concretely, the trace with the SMALLEST max page-pixel-y (i.e. never sinks as low in
    density terms) is the envelope; the remaining `len(names_in_peak_x_order)` traces are
    identified by peak-x exactly as `curves_by_peak_x` does. All curves (envelope included)
    get `label_position_override` forced via the same shared-x / real-interpolated-y trick,
    picking up the envelope curve's own real position at that x same as any other."""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    traces = extract_traces_in_region(page, panel_bbox, min_trace_points, cross_object_merge=cross_object_merge,
                                       merge_strategy=merge_strategy)
    doc.close()
    n = len(names_in_peak_x_order)
    traces = _keep_widest_traces(traces, n + 1)
    if len(traces) != n + 1:
        raise RuntimeError(f"curves_by_peak_x_with_envelope: expected {n + 1} traces, got {len(traces)}")
    max_y = [max(p[1] for p in t) for t in traces]
    envelope_idx = min(range(n + 1), key=lambda i: max_y[i])
    remaining = [i for i in range(n + 1) if i != envelope_idx]
    peak_x = {i: min(traces[i], key=lambda p: p[1])[0] for i in remaining}
    order = sorted(remaining, key=lambda i: peak_x[i])  # left-to-right trace index order
    shared_x = _safe_shared_x(traces, sum(peak_x.values()) / n)
    curves = [CurveSpec(names_in_peak_x_order[rank],
                         label_position_override=(shared_x, _interpolated_y_at_x(traces[i], shared_x)))
              for rank, i in enumerate(order)]
    curves.append(CurveSpec(envelope_name,
                             label_position_override=(shared_x, _interpolated_y_at_x(traces[envelope_idx], shared_x))))
    return curves


def mp_dye_density_curves(pdf_path, page_index, panel_bbox, min_trace_points=12, cross_object_merge=False,
                           merge_strategy="proximity", dye_names_in_peak_x_order=("yellow", "magenta", "cyan")):
    """Builds CurveSpecs for Kodak motion-picture negative film's 5-curve Spectral-Dye-Density
    panel: d_min/midscale_neutral (the still-photography-negative 2-curve composite convention)
    PLUS Yellow/Magenta/Cyan (the reversal/paper-style 3 individual dyes), all on one chart --
    see MP_DYE_DENSITY_LABELS' own comment in kodak_common.py. d_min/midscale_neutral's real
    inline labels are reliable (confirmed via QA overlay across many files this session) since
    they sit far apart in y from each other and from the 3 dye labels -- but the 3 dye labels
    among themselves have the SAME tied/near-tied-y bug `curves_by_peak_x` fixes elsewhere,
    confirmed on Vision3 200T/250D, Vision 50D/250D/500T (several sheets) via automated
    peak-position cross-check (2026-07-10).

    Identifies all 5 by SHAPE, not label position, since a mixed hybrid (2 by label + 3 by
    peak-x) risks the same rank-collision the label-position approach already fails at:
    - The 3 dye curves (Yellow/Magenta/Cyan) each drop close to zero density away from their
      own peak -- identified as the 3 traces with the largest max page-pixel-y (lowest density
      reached anywhere on the curve).
    - d_min and midscale_neutral are both composites that stay elevated across the whole
      range (never near zero) -- the remaining 2 traces after removing the dye curves. Of
      those 2, midscale_neutral is always the taller one (it's the response to actual
      midscale-gray exposure, layered on top of the same base fog d_min represents) --
      identified by real peak height (smallest max page-pixel-y = tallest peak).
    - The 3 dye curves are then ordered left-to-right by peak-x same as `curves_by_peak_x`.
    All 5 get `label_position_override` forced via the shared-x / real-interpolated-y trick.

    `dye_names_in_peak_x_order` defaults to the real physical left-to-right order
    (Yellow < Magenta < Cyan) -- override it for a sheet with a CONFIRMED, documented printed
    label swap (e.g. Kodak Vision3 500T/5219, whose own Spectral-Dye-Density panel prints
    "Cyan" on the ~450nm peak and "Yellow" on the ~650nm peak, backwards from every sibling
    VISION3 sheet) so the output preserves what's actually printed rather than silently
    correcting it to the physical convention -- this project's policy is to flag real
    source-document anomalies in code comments, not paper over them (see e4034.pdf's
    Magenta/Cyan swap in kodak_paper.py for the same treatment)."""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    traces = extract_traces_in_region(page, panel_bbox, min_trace_points, cross_object_merge=cross_object_merge,
                                       merge_strategy=merge_strategy)
    doc.close()
    traces = _keep_widest_traces(traces, 5)
    if len(traces) != 5:
        raise RuntimeError(f"mp_dye_density_curves: expected 5 traces, got {len(traces)}")
    max_y = [max(p[1] for p in t) for t in traces]  # larger = drops lower in density
    dye_idx = sorted(range(5), key=lambda i: -max_y[i])[:3]  # 3 traces that sink lowest
    composite_idx = [i for i in range(5) if i not in dye_idx]
    midscale_i, dmin_i = sorted(composite_idx, key=lambda i: max_y[i])  # smaller max_y = taller peak
    peak_x = {i: min(traces[i], key=lambda p: p[1])[0] for i in dye_idx}
    dye_order = sorted(dye_idx, key=lambda i: peak_x[i])  # left-to-right: yellow, magenta, cyan
    shared_x = _safe_shared_x(traces, sum(peak_x.values()) / 3)
    names = list(dye_names_in_peak_x_order)
    curves = [CurveSpec(names[rank], label_position_override=(shared_x, _interpolated_y_at_x(traces[i], shared_x)))
              for rank, i in enumerate(dye_order)]
    curves.append(CurveSpec("d_min",
                             label_position_override=(shared_x, _interpolated_y_at_x(traces[dmin_i], shared_x))))
    curves.append(CurveSpec("midscale_neutral",
                             label_position_override=(shared_x, _interpolated_y_at_x(traces[midscale_i], shared_x))))
    return curves


# ---------------------------------------------------------------------------
# Shared post-processing: binning, monotonicity, simplification
# ---------------------------------------------------------------------------

def isotonic_regression(ys, increasing=True):
    """Pool Adjacent Violators (PAVA): the closest (least-squares) monotonic
    sequence to ys. Used to remove digitization/binning jitter from a curve
    that is a real monotonic material property (H&D density-vs-exposure),
    rather than picking a `start` index to dodge it -- this fixes the whole
    curve, and unlike a `start` workaround, a subsequence of an isotonic
    sequence is still isotonic, so it survives RDP simplification afterward.
    """
    vals = [-v for v in ys] if not increasing else list(ys)
    stack_v, stack_c = [], []  # pooled block value, pooled block point-count
    for v in vals:
        cv, cc = v, 1
        while stack_v and stack_v[-1] > cv:
            pv, pc = stack_v.pop(), stack_c.pop()
            cv = (cv * cc + pv * pc) / (cc + pc)
            cc += pc
        stack_v.append(cv)
        stack_c.append(cc)
    out = []
    for v, c in zip(stack_v, stack_c):
        out.extend([v] * c)
    return [-v for v in out] if not increasing else out


def _perp_dist(p, a, b):
    """Perpendicular distance from point p to line a-b (all (x,y) tuples)."""
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def rdp(points, epsilon):
    """Ramer-Douglas-Peucker polyline simplification. points: list of (x,y)
    already in a normalized (comparable-scale) coordinate space."""
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    max_dist, index = -1.0, -1
    for i in range(1, len(points) - 1):
        d = _perp_dist(points[i], start, end)
        if d > max_dist:
            max_dist, index = d, i
    if max_dist > epsilon:
        left = rdp(points[:index + 1], epsilon)
        right = rdp(points[index:], epsilon)
        return left[:-1] + right
    return [start, end]


def simplify_to_target(xs, ys, target_lo=20, target_hi=30, max_iters=40):
    """Downsample a dense curve to ~target_lo..target_hi points via RDP,
    binary-searching epsilon (in axis-normalized units, so it behaves
    consistently regardless of the curve's actual x/y units/scale)."""
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    x_span = (x_hi - x_lo) or 1.0
    y_span = (y_hi - y_lo) or 1.0
    norm_pts = [((x - x_lo) / x_span, (y - y_lo) / y_span) for x, y in zip(xs, ys)]

    lo_eps, hi_eps = 1e-5, 0.2
    best = None
    for _ in range(max_iters):
        mid = (lo_eps + hi_eps) / 2
        simplified = rdp(norm_pts, mid)
        n = len(simplified)
        if target_lo <= n <= target_hi:
            best = simplified
            break
        if n > target_hi:
            lo_eps = mid
        else:
            hi_eps = mid
        best = simplified
    out = [(nx * x_span + x_lo, ny * y_span + y_lo) for nx, ny in best]
    return out


def bin_average(xs, ys, n_bins):
    xs = np.array(xs)
    ys = np.array(ys)
    order = np.argsort(xs)
    xs, ys = xs[order], ys[order]
    edges = np.linspace(xs.min(), xs.max(), n_bins + 1)
    idx = np.clip(np.digitize(xs, edges) - 1, 0, n_bins - 1)
    out_x, out_y = [], []
    for b in range(n_bins):
        mask = idx == b
        if not mask.any():
            continue
        out_x.append(xs[mask].mean())
        out_y.append(ys[mask].mean())
    out_x, out_y = np.array(out_x), np.array(out_y)
    full_x = np.linspace(out_x.min(), out_x.max(), n_bins)
    full_y = np.interp(full_x, out_x, out_y)
    return full_x, full_y


def count_violations(ys, increasing):
    if increasing:
        return sum(1 for i in range(len(ys) - 1) if ys[i] > ys[i + 1])
    return sum(1 for i in range(len(ys) - 1) if ys[i] < ys[i + 1])


# ---------------------------------------------------------------------------
# QA overlay rendering
# ---------------------------------------------------------------------------

def render_qa_overlay(chart_results, out_path):
    # Built via the Figure/FigureCanvasAgg API directly, NOT pyplot.subplots()/
    # plt.close() -- pyplot keeps a shared global figure-manager registry that
    # isn't safe for concurrent callers (kodak_still.py etc. now run their
    # PRODUCTS list across a process pool, see run_products_parallel). This
    # path only ever touches its own local `fig`/`ax`, never pyplot's global
    # state, so it's safe to call from multiple workers at once.
    #
    # `chart_results` is a list of (chart, results, calib, page) tuples -- ONE PER PRODUCT
    # (not per page): every chart belonging to a given product/paper is drawn as its own
    # subplot in one composite image, each cropped to just THAT chart's own region_bbox (not
    # the whole page). Two earlier designs were tried and rejected: one image per chart_id
    # (confusing -- a page with several real panels produced several images that each looked
    # like most of the page wasn't processed, when it was, just captured in a sibling file);
    # one combined image per PDF page, showing the whole page as background (still confusing
    # when two DIFFERENT products' charts share one page, e.g. Kodak Ektachrome E100G/E100GX
    # -- E100GX's own overlay would show E100G's characteristic-curve panel too, unhighlighted,
    # reading as "this wasn't extracted" when it was just a different product's data). Cropping
    # each subplot to its own chart's region_bbox (plus a margin) means a product's overlay
    # only ever shows what actually belongs to that product, and covers every chart on it
    # regardless of how many source pages or PDFs they're spread across.
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    scale = 4.0
    margin = 8  # PDF points, in the region_bbox's own coordinate space -- kept small since
    # panels on a real page are often packed tightly enough that a wider margin pulls in a
    # neighboring panel's own title/caption text, overlapping this subplot's own title
    default_colors = ["cyan", "lime", "magenta", "orange", "yellow", "white",
                       "deepskyblue", "springgreen", "hotpink", "gold", "khaki", "silver"]
    n = len(chart_results)
    cols = 2 if n > 1 else 1
    rows = (n + cols - 1) // cols
    fig = Figure(figsize=(9 * cols, 7 * rows), dpi=150)
    FigureCanvasAgg(fig)
    for idx, (chart, results, calib, page) in enumerate(chart_results):
        ax = fig.add_subplot(rows, cols, idx + 1)
        xs, xi, ys, yi = calib  # data = slope*pixel + intercept -> pixel = (data-intercept)/slope
        bbox = chart.region_bbox
        if bbox is not None:
            clip = fitz.Rect(bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin) & page.rect
        else:
            clip = page.rect
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        ax.imshow(img)
        for color_i, curve in enumerate(chart.curves):
            if curve.name not in results:
                continue
            color = default_colors[color_i % len(default_colors)]
            px, py = results[curve.name]["_px"]
            px_c = [(x - clip.x0) * scale for x in px]
            py_c = [(y - clip.y0) * scale for y in py]
            ax.plot(px_c, py_c, "-", lw=0.5, color=color, alpha=0.35, label=f"{curve.name} (raw)")
            simp_x = [p[0] for p in results[curve.name]["points"]]
            simp_y = [p[1] for p in results[curve.name]["points"]]
            simp_px = [(x - xi) / xs for x in simp_x]
            simp_py = [(y - yi) / ys for y in simp_y]
            simp_px_c = [(x - clip.x0) * scale for x in simp_px]
            simp_py_c = [(y - clip.y0) * scale for y in simp_py]
            ax.plot(simp_px_c, simp_py_c, "-o", lw=1.2, ms=2.5, color=color,
                    label=f"{curve.name} (simplified, n={len(simp_x)})")
        ax.legend(fontsize=6, loc="upper left")
        ax.set_title(chart.chart_id, fontsize=9, pad=10)
        ax.axis("off")
    fig.tight_layout(pad=2.0, h_pad=3.0, w_pad=2.0)
    fig.savefig(out_path, dpi=150)


# ---------------------------------------------------------------------------
# Generic per-chart digitization (extraction-method-agnostic caller)
# ---------------------------------------------------------------------------

def digitize_chart(chart: ChartSpec, pdf_path: Path) -> dict:
    """Runs axis calibration + curve extraction (whichever strategy
    chart.extraction_method selects) + binning/monotonicity/simplification
    for every curve in `chart`. Returns a dict with the same shape the
    original tool wrote to JSON, plus private `_qa_*` fields the caller uses
    to render a combined-per-page QA overlay (see product.py's _run_charts
    and render_qa_overlay) -- this function no longer renders anything
    itself, since a QA overlay now covers every chart sharing a page, not
    just this one. '_page' (the open fitz.Page) is NOT included -- callers
    needing the page should open the doc themselves; this function opens/
    closes its own doc handle.
    """
    doc = fitz.open(pdf_path)
    page = doc[chart.page_index]
    words = page.get_text("words")

    # vector_position charts pack several panels on one page -- if the caller
    # didn't give an explicit tick-search bbox, default to the panel's own
    # region_bbox rather than silently searching the whole page (which would
    # pick up whichever panel's ticks happen to form the largest cluster).
    default_axis_bbox = chart.axis_word_bbox
    if default_axis_bbox is None and chart.extraction_method == "vector_position":
        default_axis_bbox = chart.region_bbox
    if chart.x_axis_calib_override is not None:
        xs, xi, x_ticks = (*chart.x_axis_calib_override, [])
    else:
        xs, xi, x_ticks = fit_axis(words, chart.x_tick_regex, "x", bbox=chart.x_tick_bbox or default_axis_bbox)
    if chart.y_axis_calib_override is not None:
        ys, yi, y_ticks = (*chart.y_axis_calib_override, [])
    else:
        ys, yi, y_ticks = fit_axis(words, chart.y_tick_regex, "y", bbox=chart.y_tick_bbox or default_axis_bbox)

    raster_clip = None
    if chart.extraction_method == "raster_trace":
        raster_clip, _xref = locate_raster_chart_rect(page, chart.raster_image_index)

    fill_band_curves = None
    if chart.extraction_method == "vector_fill_band":
        if chart.region_bbox is None or chart.fill_band_rgb is None:
            raise ValueError("vector_fill_band requires ChartSpec.region_bbox and fill_band_rgb")
        fill_band_curves = extract_fill_band_curves(
            page, chart.fill_band_rgb, chart.fill_band_tol, chart.region_bbox,
            chart.fill_band_exclude_bboxes, len(chart.curves), chart.fill_band_gap,
            min_fragment_width=chart.fill_band_min_width,
        )

    position_traces = None
    position_assignment = {}
    if chart.extraction_method == "vector_position":
        if chart.region_bbox is None:
            raise ValueError("vector_position requires ChartSpec.region_bbox")
        position_traces = extract_traces_in_region(page, chart.region_bbox, chart.min_trace_points,
                                                    cross_object_merge=chart.cross_object_merge,
                                                    merge_strategy=chart.merge_strategy,
                                                    merge_tol_multiplier=chart.merge_tol_multiplier,
                                                    strict_chain_merge=chart.strict_chain_merge,
                                                    split_on_x_reversal=chart.split_on_x_reversal,
                                                    reversal_run_length=chart.reversal_run_length)
        position_traces = _dedupe_exact_traces(position_traces)
        if chart.rank_assignment_names is not None:
            position_assignment = assign_traces_by_x_rank(position_traces, chart.rank_assignment_names,
                                                            rank_at_y=chart.rank_at_y)
        else:
            label_positions = {
                curve.name: (curve.label_position_override if curve.label_position_override is not None
                             else find_label_position(words, curve.label_regex, bbox=chart.region_bbox))
                for curve in chart.curves
            }
            position_assignment = assign_traces_to_labels_exclusive(position_traces, label_positions)
            for name, pos in label_positions.items():
                if pos is None:
                    print(f"  WARNING: label not found for {name}")

    results = {}
    for curve in chart.curves:
        if chart.extraction_method == "vector_color_fill":
            raw = extract_curve_points_by_fill(page, curve.fill_rgb, curve.tol, chart.legend_bbox)
        elif chart.extraction_method == "vector_stroke_dash":
            raw = extract_curve_points_by_stroke(
                page, curve.stroke_rgb, curve.tol, curve.dash_regex,
                curve.width, curve.width_tol, chart.legend_bbox,
                region_bbox=chart.region_bbox,
            )
        elif chart.extraction_method == "raster_trace":
            raw = extract_curve_points_from_raster(
                page, raster_clip, curve.pixel_rgb, curve.pixel_tol,
                chart.raster_dpi_scale, chart.legend_bbox,
            )
        elif chart.extraction_method == "vector_position":
            idx = position_assignment.get(curve.name)
            raw = position_traces[idx] if idx is not None else []
        elif chart.extraction_method == "vector_fill_band":
            rank = chart.curves.index(curve)
            raw = fill_band_curves[rank] if rank < len(fill_band_curves) else []
        else:
            raise ValueError(f"unknown extraction_method {chart.extraction_method!r}")

        if not raw:
            print(f"  WARNING: no points found for {curve.name} ({chart.extraction_method})")
            continue
        pxs, pys = zip(*raw)
        data_x = [xs * p + xi for p in pxs]
        data_y = [ys * p + yi for p in pys]
        bx, by = bin_average(data_x, data_y, chart.n_bins)
        if chart.monotonic_direction is not None:
            by = np.array(isotonic_regression(by, increasing=chart.monotonic_direction == "increasing"))
        simplified = simplify_to_target(bx, by)
        sx = [round(float(x), 4) for x, y in simplified]
        sy = [round(float(y), 4) for x, y in simplified]
        v_inc = count_violations(sy, increasing=True)
        v_dec = count_violations(sy, increasing=False)
        likely_dir = "increasing" if v_inc <= v_dec else "decreasing"
        n_violations = min(v_inc, v_dec)
        results[curve.name] = {
            "points": list(zip(sx, sy)),
            "points_dense": [[round(float(x), 4), round(float(y), 4)] for x, y in zip(bx, by)],
            "n_raw_vertices": len(raw),
            "n_violations": n_violations,
            "likely_direction": likely_dir,
            "_px": (pxs, pys),
        }
        print(f"  {curve.name}: {len(raw)} raw points ({chart.extraction_method}) -> {len(bx)} dense -> "
              f"{len(sx)} simplified points, x range [{bx.min():.3f},{bx.max():.3f}] "
              f"y range [{by.min():.3f},{by.max():.3f}]  "
              f"monotonicity (assuming {likely_dir}): {n_violations} violation(s)")

    out = {
        "source_pdf": chart.pdf,
        "page_index": chart.page_index,
        "chart_id": chart.chart_id,
        "x_label": chart.x_label,
        "y_label": chart.y_label,
        "x_axis_calibration": {"tick_matches": x_ticks, "fit_slope": xs, "fit_intercept": xi},
        "y_axis_calibration": {"tick_matches": y_ticks, "fit_slope": ys, "fit_intercept": yi},
        "curves": {k: {"points": v["points"], "points_dense": v["points_dense"],
                        "n_raw_vertices": v["n_raw_vertices"], "n_violations": v["n_violations"],
                        "likely_direction": v["likely_direction"]}
                   for k, v in results.items()},
        "qa_overlay_png": None,  # filled in by the caller once it knows the combined-per-page filename
        # Private fields consumed only by the caller's combined-overlay rendering pass
        # (grouped by (chart.pdf, chart.page_index) across every chart sharing a page) --
        # never written to the output JSON, see product.py's _run_charts. Kept alongside
        # `out` rather than returned separately so this function's signature/call sites
        # don't have to change shape.
        "_qa_results": results,
        "_qa_calib": (xs, xi, ys, yi),
        "_qa_page_number": page.number,
    }
    doc.close()
    _sanity_check_chart(chart, out)
    return out


def _sanity_check_chart(chart: ChartSpec, out: dict, min_points=5):
    """Prints a loud warning (doesn't raise -- this runs after the file's
    already written) for signatures of the "vector_position picked the same
    trace for every label" failure mode: near-identical bounding boxes across
    curves that are supposed to be distinct, or suspiciously few simplified
    points. Silent-but-wrong is the expensive failure at this volume -- an
    exception at least stops the batch, this catches the case that doesn't
    raise at all."""
    boxes = {}
    for name, curve in out["curves"].items():
        pts = curve["points"]
        if len(pts) < min_points:
            print(f"  SANITY WARNING: {chart.chart_id}/{name} has only {len(pts)} points (< {min_points})")
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if xs and ys:
            boxes[name] = (min(xs), max(xs), min(ys), max(ys))
    names = list(boxes)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = boxes[names[i]], boxes[names[j]]
            if all(abs(a[k] - b[k]) < 1e-6 for k in range(4)):
                print(f"  SANITY WARNING: {chart.chart_id}/{names[i]} and {names[j]} have identical "
                      f"bounding boxes -- likely the same trace matched to both labels")
