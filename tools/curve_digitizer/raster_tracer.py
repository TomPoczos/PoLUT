"""
Traces curves out of an embedded RASTER chart image (not vector paths) --
for the Fuji "Characteristic Curves" panels confirmed (2026-07-05/06) to be
embedded CCITTFaxDecode bitonal scans, not vector paths (see BLOCKED.md).

Unlike Strategy A/B/C's color- or dash-regex-keyed matching (which read
real PDF drawing-object metadata), there is no metadata here at all -- only
pixels. The approach:

1. `load_ink_mask()` pulls the embedded image as a boolean ink array
   (confirmed genuinely bitonal -- exactly {0, 255} -- so no thresholding
   ambiguity).
2. `detect_gridlines()` finds gridline rows/columns via row/column ink
   FRACTION (a real gridline spans nearly the whole plot width/height, so
   its row/column ink fraction is high; a curve merely crossing that row/
   column at one point is not) -- confirmed clean on Velvia 50 (2026-07-06):
   exactly the 7 expected horizontal + ~14 vertical gridline positions, no
   false positives.
3. `build_scan_mask()` excludes gridline rows/cols and text/legend blobs
   (connected components on the gridline-deleted ink, kept only if narrow
   -- text glyphs are compact, curves are wide) from a scan mask used for
   tracing.
4. `trace_curves()` walks the scan mask column-by-column with a classic
   multi-object-tracking approach (nearest-active-trace continuation) --
   NOT global connected-components. This distinction matters: an earlier
   attempt tried deleting gridline pixels then reconnecting via
   morphological closing, but the kernel size needed to bridge a
   gridline-crossing gap (2026-07-06, confirmed on Velvia 50) is
   indistinguishable from the spacing between genuinely separate curves in
   their overlap region -- any kernel large enough to fix one problem
   causes the other (fuses distinct curves). Column-scan avoids this
   entirely: it only needs LOCAL continuity from one column to the next,
   so skipping a gridline column (or a column with no ink at all) and
   continuing from the last real reading needs no reconnection step, and
   never risks fusing two curves that happen to pass near each other.

Confirmed and accepted going in (2026-07-06, see conversation with user):
for a real stretch of these charts, multiple curves run visually
coincident (confirmed on Velvia 50: R/G/B are only separated in the toe,
otherwise touch/overlap for most of the frame) -- connected components
there is ONE blob, not three, no matter how it's sliced. `trace_curves()`
does not attempt dash-pattern disambiguation to split that blob (that
would need skeletonization, deliberately not pursued -- see conversation);
where N traces converge to fewer than N distinct pixel-clusters, they
collapse onto a single shared trace for that stretch, the same accepted
approximation already used for Ilford CooltoneRC's near-identical grade
4/5 curves. This means MOST of the digitized curve's overlapping region
is one shared trace duplicated across all N output curves, and only the
separated (usually toe or shoulder) region carries real per-curve
distinction -- honest, not silently wrong, and flagged in
`digitizer_notes` at the call site.
"""

import numpy as np
from scipy import ndimage


def load_ink_mask(page, image_index=0):
    """Returns (ink: bool ndarray[h,w], placement_rect) for the
    image_index-th embedded image on `page`. `ink[y,x]` True means
    foreground (curve/gridline/text) ink, confirmed via direct pixel-value
    check that these scans are genuinely bitonal (exactly {0,255}), not
    thresholded here."""
    images = page.get_images(full=True)
    if not images:
        raise RuntimeError("page has no embedded images")
    if image_index >= len(images):
        raise RuntimeError(f"page only has {len(images)} embedded image(s), index {image_index} requested")
    xref = images[image_index][0]
    rects = page.get_image_rects(xref)
    if not rects:
        raise RuntimeError(f"image xref {xref} has no placement rect on this page")
    doc = page.parent
    pix = __import__("fitz").Pixmap(doc, xref)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    uniq = np.unique(arr)
    if not set(uniq.tolist()) <= {0, 255}:
        raise RuntimeError(f"expected a bitonal image (values {{0,255}}), got {uniq.tolist()[:10]}")
    ink = arr == 255
    return ink, rects[0]


def detect_gridlines(ink, frac_threshold=0.5, row_sample_x_range=None, col_sample_y_range=None):
    """Returns (grid_rows, grid_cols): 1-D index arrays of rows/columns
    whose ink fraction exceeds `frac_threshold` -- a real gridline spans
    nearly the whole plot, a curve crossing it at one point does not.
    Confirmed clean (no false positives, all real gridlines found) on
    Velvia 50's Characteristic Curves panel, 2026-07-06.

    `row_sample_x_range`/`col_sample_y_range`: optional (lo, hi) image-pixel
    slices to compute the ink fraction from, instead of the WHOLE image
    width/height. Confirmed necessary on Superia 100 (2026-07-06): a real
    gridline is only 1-2px thick, but measuring ink fraction across the
    FULL width/height means curves that happen to run close to parallel
    with that gridline for a stretch add their own ink to nearby rows,
    inflating the detected gridline to look 4-5px thick -- confirmed by
    comparing full-width fraction against a fraction measured only in a
    curve-free strip (e.g. past the frame's rightmost real curve data, or
    a density band no curve reaches), which showed the true gridline is
    much thinner. Deleting the inflated band removes real curve ink
    wherever the curve's own gradual slope keeps it within that band for
    several columns, producing a false flat plateau/kink where the
    tracer loses and re-acquires the trace. Pick a sample range known to
    be curve-free for the specific file (verify first), not blindly."""
    if row_sample_x_range is not None:
        lo, hi = row_sample_x_range
        row_frac = ink[:, lo:hi].mean(axis=1)
    else:
        row_frac = ink.mean(axis=1)
    if col_sample_y_range is not None:
        lo, hi = col_sample_y_range
        col_frac = ink[lo:hi, :].mean(axis=0)
    else:
        col_frac = ink.mean(axis=0)
    grid_rows = np.where(row_frac > frac_threshold)[0]
    grid_cols = np.where(col_frac > frac_threshold)[0]
    return grid_rows, grid_cols


def build_scan_mask(ink, grid_rows, grid_cols, text_max_width=60, text_max_height=30):
    """Builds the mask `trace_curves` scans: `ink` with gridline rows/cols
    and text/legend blobs removed. Text/legend removal: connected
    components on gridline-deleted ink, a component is "text" (removed) if
    BOTH its bounding-box width is under `text_max_width` px AND its height
    is under `text_max_height` px -- text glyphs are compact in both
    dimensions. Width alone is NOT enough: a STEEP (near-vertical) curve
    segment is also narrow in width but can be very TALL, and a width-only
    filter wrongly treats it as text -- confirmed on Sensia 100
    (2026-07-06): the entire steep middle section of the S-curve (several
    fragments up to ~90px tall, all under 60px wide) was silently deleted,
    leaving a real gap in the middle of the trace that looked like a
    tracing failure but was actually this filter being too aggressive.
    Both thresholds need tuning per file's DPI/font size; verify via the
    saved scan-mask image before trusting it blindly on a new file."""
    deleted = ink.copy()
    deleted[grid_rows, :] = False
    deleted[:, grid_cols] = False
    labeled, n = ndimage.label(deleted, structure=np.ones((3, 3)))
    objs = ndimage.find_objects(labeled)
    text_mask = np.zeros_like(ink)
    for i, sl in enumerate(objs, start=1):
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        if w < text_max_width and h < text_max_height:
            text_mask[sl] |= labeled[sl] == i

    grid_row_mask = np.zeros(ink.shape[0], dtype=bool)
    grid_row_mask[grid_rows] = True
    grid_col_mask = np.zeros(ink.shape[1], dtype=bool)
    grid_col_mask[grid_cols] = True

    scan = ink.copy()
    scan[grid_row_mask, :] = False
    scan[:, grid_col_mask] = False
    scan &= ~text_mask
    return scan


def _cluster_column(rows, max_gap=3):
    """Groups a sorted 1-D array of ink row-indices (one image column) into
    clusters, allowing gaps up to `max_gap` px within one cluster (thin
    strokes have small anti-aliasing/skip gaps). Returns a list of cluster
    centroids (float)."""
    if len(rows) == 0:
        return []
    clusters = []
    cur = [rows[0]]
    for r in rows[1:]:
        if r - cur[-1] <= max_gap:
            cur.append(r)
        else:
            clusters.append(cur)
            cur = [r]
    clusters.append(cur)
    return [float(np.mean(c)) for c in clusters]


def trace_curves(scan_mask, n_curves, x_range=None, max_y_jump=15, max_gap_columns=8, cluster_gap=3):
    """Column-by-column multi-object tracking: maintains up to `n_curves`
    active traces, assigning each column's ink-clusters to whichever active
    trace's last-known y is closest (classic nearest-neighbor
    continuation), starting a new trace for an unclaimed cluster if fewer
    than `n_curves` are currently active, and letting a trace go quiet
    (skipped, not deleted) for up to `max_gap_columns` consecutive columns
    with no matching cluster (dash gaps, or a column that fell entirely on
    a removed gridline) before considering it ended.

    Where multiple traces' clusters have collapsed onto the same shared
    pixel-cluster (curves visually coincident -- confirmed real and common
    in the middle of these charts, see module docstring), every trace
    still active at that column is assigned the SAME cluster; this is the
    accepted merged-curve approximation, not a bug.

    Returns a list of `n_curves` traces, each a list of (x, y) pixel-space
    points (NOT yet calibrated to data units -- caller applies axis
    calibration separately, same convention as extract_traces_in_region)."""
    x0, x1 = x_range if x_range is not None else (0, scan_mask.shape[1])
    traces = [[] for _ in range(n_curves)]
    active_y = [None] * n_curves  # last known y per trace slot
    quiet_count = [0] * n_curves

    for x in range(x0, x1):
        col_rows = np.where(scan_mask[:, x])[0]
        clusters = _cluster_column(col_rows, max_gap=cluster_gap)
        if not clusters:
            for i in range(n_curves):
                if active_y[i] is not None:
                    quiet_count[i] += 1
                    if quiet_count[i] > max_gap_columns:
                        active_y[i] = None
            continue

        unclaimed = list(clusters)
        assigned = {}  # slot -> y
        # Pass 1: EXCLUSIVE greedy assignment (nearest distance first, no
        # cluster reused) -- correct when there are enough distinct
        # clusters for each active trace to get its own.
        pairs = []
        for i in range(n_curves):
            if active_y[i] is None:
                continue
            for cy in unclaimed:
                d = abs(cy - active_y[i])
                if d <= max_y_jump:
                    pairs.append((d, i, cy))
        pairs.sort(key=lambda p: p[0])
        used_slots, used_ys = set(), set()
        for d, i, cy in pairs:
            if i in used_slots or cy in used_ys:
                continue
            assigned[i] = cy
            used_slots.add(i)
            used_ys.add(cy)

        # start new traces for unclaimed clusters, in free slots
        remaining_clusters = [c for c in unclaimed if c not in used_ys]
        free_slots = [i for i in range(n_curves) if active_y[i] is None and i not in used_slots]
        for cy, slot in zip(remaining_clusters, free_slots):
            assigned[slot] = cy
            used_slots.add(slot)

        # (A "Pass 1.5" that force-started any never-yet-active trace by
        # piggybacking on another trace's cluster was tried and reverted,
        # 2026-07-06: confirmed on Velvia 50 it over-merged, corrupting
        # the genuinely-correct R/G separation in the toe, not just
        # filling in the intended G/B gap -- once two slots' active_y
        # values are forced equal, later exclusive-assignment columns kept
        # matching them together even where they should have diverged.
        # Safer to leave a not-yet-distinguishable trace with a real gap
        # in its own data (disclosed in digitizer_notes) than to risk a
        # silently-wrong merge of curves that were actually separate.)

        # Pass 2: NON-exclusive fallback for any trace still unmatched --
        # fewer distinct clusters than active traces means a real merge
        # (curves visually coincident, see module docstring), so let it
        # share whichever cluster is nearest even if another trace already
        # claimed it, rather than starving it into going quiet/ending.
        # This is what keeps a curve's identity alive (as a duplicate of
        # the fused path) through an overlap stretch instead of leaving a
        # gap in its own data for that whole stretch.
        for i in range(n_curves):
            if i in assigned or active_y[i] is None:
                continue
            best = min(unclaimed, key=lambda cy: abs(cy - active_y[i]), default=None)
            if best is not None and abs(best - active_y[i]) <= max_y_jump:
                assigned[i] = best

        for i in range(n_curves):
            if i in assigned:
                traces[i].append((float(x), assigned[i]))
                active_y[i] = assigned[i]
                quiet_count[i] = 0
            elif active_y[i] is not None:
                quiet_count[i] += 1
                if quiet_count[i] > max_gap_columns:
                    active_y[i] = None

    return traces
