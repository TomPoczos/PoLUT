"""
Traces curves out of an embedded RASTER chart image (not vector paths) --
copied from ../curve_digitizer/raster_tracer.py (built there 2026-07-05/06
for Fuji's CCITTFaxDecode bitonal "Characteristic Curves" scans, see that
project's BLOCKED.md) and extended here 2026-08-03 for Ilford Delta 100
Professional, whose Characteristic Curve panel is a genuinely different
raster sub-case: an anti-aliased 8-bit DeviceGray render (256 distinct
sample values, NOT byte-exact {0,255}) rather than a bitonal fax scan, and
a single un-fused trace (no Fuji-style multi-curve coincidence problem) with
its own distinct artifact -- minor/unlabeled tick-mark stubs projecting a
short distance inward from the frame border, see `build_scan_mask`. Same
"only pixels, no PDF drawing-object metadata" situation and same overall
column-scan design as the original; the two additions below are real,
independently-motivated generalizations, not a fork -- if a genuine bug is
found in the parts shared with curve_digitizer's copy, fix it there too so
the two don't drift needlessly (same policy this project's digitizer_core.py
copy already documents).

1. `load_ink_mask()` pulls the embedded image as a boolean ink array. The
   original bitonal-only version hard-asserted exactly {0, 255} (true for
   Fuji's CCITT scans, no thresholding ambiguity there); Delta 100's own
   image is NOT byte-exact bitonal but IS effectively bitonal in practice
   (confirmed by histogram, 2026-08-03: 91.3% of pixels sit above 224,
   6.7% below 32, only ~2% in the 32-224 anti-aliasing transition band --
   a real bimodal ink/background split, not continuous tone). `threshold`
   (default 128) is only consulted when the image ISN'T byte-exact
   bitonal, so Fuji's existing exact-match behavior (and its "no
   thresholding ambiguity" guarantee) is unchanged for files already
   confirmed bitonal.
2. `detect_gridlines()` finds gridline rows/columns via row/column ink
   FRACTION (a real gridline spans nearly the whole plot width/height, so
   its row/column ink fraction is high; a curve merely crossing that row/
   column at one point is not) -- confirmed clean on Velvia 50 (2026-07-06):
   exactly the 7 expected horizontal + ~14 vertical gridline positions, no
   false positives.
3. `build_scan_mask()` excludes gridline rows/cols and two distinct kinds
   of non-curve ink from the scan mask `trace_curves` walks:
   - Text/legend blobs: connected components on the gridline-deleted ink,
     kept only if narrow AND short (`text_max_width`/`text_max_height` --
     text glyphs are compact in both dimensions; width alone is NOT enough
     since a steep near-vertical curve segment is also narrow but can be
     very tall, confirmed on Sensia 100 wrongly deleting real curve ink
     this way when only width was checked).
   - Minor/unlabeled gridline tick-mark stubs (`frame_bounds`/
     `tick_stub_max_thickness`/`border_touch_tol`, new 2026-08-03, Ilford
     Delta 100): short marks that project a little way INTO the plot from
     the frame border at regular intervals, common in this chart style,
     but too short to span the whole plot (so `detect_gridlines`'s
     whole-span fraction threshold correctly leaves them alone) and often
     too TALL to be caught by the text-size filter above (confirmed: a
     ~60px-tall, 1px-wide stub at Delta 100's own frame top survives
     `text_max_height=30` the same way a steep curve segment would, so
     tightening that filter isn't safe either). Distinguished instead by a
     property text-size filtering can't use: a tick stub always TOUCHES
     the frame border on one end (checked with `border_touch_tol`, needed
     because the border itself is several pixels thick post-gridline-
     deletion -- the stub's own bbox starts right after the deleted band,
     not exactly at the raw ftop/fbottom/fleft/fright value) and is thin
     in at least one dimension (`tick_stub_max_thickness`) -- a real curve
     trace only touches the frame border at its own true first/last data
     point, if at all. Confirmed on Delta 100: two stray points (one at
     each end of the trace, at the frame's top and bottom-right corners)
     were exactly this artifact, silently corrupting the traced curve's
     toe and shoulder before this filter existed -- see QA overlay
     comparison in the product's own build history. `frame_bounds`
     defaults to `None` (no tick-stub filtering) so existing Fuji-style
     callers that already pre-clip to the frame after calling this
     function are unaffected.
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
for a real stretch of Fuji's charts, multiple curves run visually
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
`digitizer_notes` at the call site. Not relevant to Delta 100's own
single-trace (`n_curves=1`) case, which has no coincidence problem at all,
but preserved here since `trace_curves` itself is unmodified and this is
still the right way to read its behavior on a future multi-curve file.
"""

import numpy as np
from scipy import ndimage


def load_ink_mask(page, image_index=0, threshold=128):
    """Returns (ink: bool ndarray[h,w], placement_rect) for the
    image_index-th embedded image on `page`. `ink[y,x]` True means
    foreground (curve/gridline/text) ink.

    Two cases, distinguished by the image's own actual pixel values, not
    assumed from the source vendor: if the image is byte-exact bitonal
    ({0, 255} only -- true for Fuji's CCITTFaxDecode scans), `ink = arr ==
    255` with no thresholding ambiguity, exactly the original behavior.
    Otherwise (an anti-aliased grayscale render, e.g. Ilford Delta 100's
    own 8-bit DeviceGray panel -- confirmed by histogram to be bimodal,
    not continuous-tone, see module docstring), `ink = arr < threshold`:
    background dominates a real chart image by area (mostly blank paper
    around thin ink lines), so the majority/near-255 cluster is background
    and the minority/near-0 cluster is foreground ink -- verified true on
    Delta 100 (91.3% of pixels > 224) before relying on it, not assumed to
    hold universally; a file where that polarity is reversed would need an
    explicit override, not currently exposed since no such file has been
    seen yet."""
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
    if set(uniq.tolist()) <= {0, 255}:
        ink = arr == 255
    else:
        ink = arr < threshold
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


def build_scan_mask(ink, grid_rows, grid_cols, text_max_width=60, text_max_height=30,
                     frame_bounds=None, tick_stub_max_thickness=8, border_touch_tol=10):
    """Builds the mask `trace_curves` scans: `ink` with gridline rows/cols,
    text/legend blobs, and (when `frame_bounds` is given) minor tick-mark
    stubs removed -- see module docstring for why these are two distinct
    filters, not one. Both run on ONE shared connected-components labeling
    pass over the gridline-ROW-deleted ink (NOT gridline-col-deleted too --
    see below for why that distinction matters, 2026-08-04).

    Text/legend removal: a component is "text" if BOTH its bounding-box
    width is under `text_max_width` px AND its height is under
    `text_max_height` px -- text glyphs are compact in both dimensions.
    Width alone is NOT enough: a STEEP (near-vertical) curve segment is
    also narrow in width but can be very TALL, and a width-only filter
    wrongly treats it as text -- confirmed on Sensia 100 (2026-07-06): the
    entire steep middle section of the S-curve (several fragments up to
    ~90px tall, all under 60px wide) was silently deleted, leaving a real
    gap in the middle of the trace that looked like a tracing failure but
    was actually this filter being too aggressive. Both thresholds need
    tuning per file's DPI/font size; verify via the saved scan-mask image
    before trusting it blindly on a new file.

    The labeling pass deletes gridline ROWS but deliberately leaves
    gridline COLUMNS in place -- confirmed needed on Ilford Delta 100
    (2026-08-04): deleting whole gridline columns before labeling chops
    the curve into a separate connected component between every pair of
    vertical gridlines it crosses. Where two vertical gridlines sit close
    together relative to the curve's local slope, that chopped-off
    fragment can itself be small enough (confirmed: one real 23x18px
    fragment) to satisfy the text-size test above even though it's 100%
    real curve ink -- silently deleting a whole multi-column stretch of
    the actual trace, not text. Leaving columns undeleted for labeling
    keeps the curve as one long, unambiguously-not-text component across
    a vertical-gridline crossing (confirmed: the same stretch measures
    151x108 once its neighboring segments are still attached) while still
    being deleted from the actual scan mask down below, same as before --
    only the classification step changes, not what's ultimately excluded.
    Gridlines themselves are already thin, so this doesn't blind the
    tick-stub check either: a real gridline landing in `objs` below still
    reads as thin-and-border-touching (correctly harmless, since its own
    pixels are removed unconditionally in the final mask construction
    regardless of whether this loop also flags it).

    Tick-stub removal (only when `frame_bounds=(ftop, fbottom, fleft,
    fright)` is given, as returned by `detect_gridlines`'s own
    grid_rows.min()/.max()/grid_cols.min()/.max()): a component is a
    "tick stub" if it's thin (`min(height, width) <= tick_stub_max_thickness`)
    AND touches the frame border (its bbox comes within `border_touch_tol`
    px of ftop/fbottom/fleft/fright -- a generous default because the
    border itself is several pixels thick pre-deletion, so a stub's own
    bbox after gridline-row deletion starts a few pixels short of the
    raw frame-bound value, not exactly at it; confirmed on Delta 100 a
    tolerance of 2px was too tight to catch either of its two real stubs,
    10px caught both cleanly). A component satisfying both the text
    condition and the tick-stub condition is removed either way -- they
    are not mutually exclusive, both are just "not curve ink"."""
    deleted = ink.copy()
    deleted[grid_rows, :] = False
    labeled, n = ndimage.label(deleted, structure=np.ones((3, 3)))
    objs = ndimage.find_objects(labeled)
    remove_mask = np.zeros_like(ink)
    if frame_bounds is not None:
        ftop, fbottom, fleft, fright = frame_bounds
    for i, sl in enumerate(objs, start=1):
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        h = y1 - y0
        w = x1 - x0
        is_text = w < text_max_width and h < text_max_height
        is_tick_stub = False
        if frame_bounds is not None:
            touches_border = (
                y0 <= ftop + border_touch_tol or y1 >= fbottom - border_touch_tol
                or x0 <= fleft + border_touch_tol or x1 >= fright - border_touch_tol
            )
            is_tick_stub = touches_border and min(h, w) <= tick_stub_max_thickness
        if is_text or is_tick_stub:
            remove_mask[sl] |= labeled[sl] == i

    grid_row_mask = np.zeros(ink.shape[0], dtype=bool)
    grid_row_mask[grid_rows] = True
    grid_col_mask = np.zeros(ink.shape[1], dtype=bool)
    grid_col_mask[grid_cols] = True

    scan = ink.copy()
    scan[grid_row_mask, :] = False
    scan[:, grid_col_mask] = False
    scan &= ~remove_mask
    return scan


def _cluster_column(rows, max_gap=3, bridge_rows=None, ink_rows=None,
                     max_bridge_extend=10, max_bridge_fragment_height=18):
    """Groups a sorted 1-D array of ink row-indices (one image column) into
    clusters, allowing gaps up to `max_gap` px within one cluster (thin
    strokes have small anti-aliasing/skip gaps). Returns a list of cluster
    centroids (float).

    `bridge_rows`/`ink_rows` (both required together to enable bridging):
    `bridge_rows` is the set of row-indices `build_scan_mask` deleted as a
    gridline; `ink_rows` is this SAME column's row-index array from the
    ORIGINAL, pre-gridline-deletion ink mask. Confirmed needed on Ilford
    Delta 100 (2026-08-04): where the traced curve crosses a gridline at a
    shallow angle over more than one column, deleting the gridline's
    row-band across the WHOLE column splits what was one continuous
    diagonal stroke into ink fragments that no longer touch under
    `max_gap`. Without bridging, `trace_curves`'s nearest-active-trace
    continuation flips between same-curve fragments column to column,
    producing a real zigzag right at the crossing.

    Each raw fragment is grown outward (`extend()` below), one row at a
    time on each side, through rows that are BOTH in `bridge_rows` (i.e.
    deleted only because they're a gridline, not because they were
    genuinely blank or filtered as text/tick-stub) AND present in
    `ink_rows` (i.e. the ORIGINAL image really did have curve ink there,
    confirmed by direct inspection to be continuous across every real
    crossing checked -- the gap is an artifact of gridline deletion, not a
    real break in the stroke). Growth is capped at `max_bridge_extend`
    rows per side and the grown fragment is discarded back to its
    original bounds if its total height would exceed
    `max_bridge_fragment_height`. Both caps matter for the same reason:
    a column can ALSO contain a large, mostly-vertical ink blob that
    isn't the curve at all -- confirmed on Delta 100 at the column
    immediately next to (not inside) a detected vertical gridline band,
    where partial anti-aliasing bleed produces a genuinely continuous
    ~150px-tall ink run that also happens to pass through the SAME
    gridline's deleted row-band. Growing into real, continuous ink alone
    (no size check) reconnects that blob's two halves into one nonsense
    centroid that lands close enough to the real trace to be silently
    accepted -- confirmed as a real regression from an earlier version of
    this bridge that only checked gap membership. A real curve stroke
    caught mid-crossing is at most ~15px tall in every case measured so
    far, so capping growth rules the blob out without reopening that
    hole. Growing outward independently per fragment (not merely
    re-averaging two already-adjacent fragments) also matters on its own:
    confirmed on Delta 100 that a crossing can leave only ONE surviving
    fragment with no sibling on the other side (the curve's real ink
    beyond the deleted band was itself entirely inside the deleted band
    at that column), which a merge-only approach can't recover at all --
    it needs the same one-sided growth this does.

    After growth, fragments are re-clustered by adjacency (still `max_gap`)
    since two independently-grown fragments can now touch or overlap.
    Falls back to plain `max_gap` clustering, no bridging, if either
    `bridge_rows` or `ink_rows` is omitted."""
    if len(rows) == 0:
        return []
    raw = []
    cur = [rows[0]]
    for r in rows[1:]:
        if r - cur[-1] <= max_gap:
            cur.append(r)
        else:
            raw.append(cur)
            cur = [r]
    raw.append(cur)

    if bridge_rows is None or ink_rows is None:
        return [float(np.mean(c)) for c in raw]

    bridge = set(int(r) for r in bridge_rows)
    ink_set = set(int(r) for r in ink_rows)

    def extend(frag):
        grown = set(frag)
        lo, hi = min(grown), max(grown)
        r, n = lo - 1, 0
        while r in bridge and r in ink_set and n < max_bridge_extend:
            grown.add(r)
            r -= 1
            n += 1
        r, n = hi + 1, 0
        while r in bridge and r in ink_set and n < max_bridge_extend:
            grown.add(r)
            r += 1
            n += 1
        if max(grown) - min(grown) + 1 > max_bridge_fragment_height:
            return set(frag)  # growth made it implausibly thick -- revert
        return grown

    flat = sorted(set().union(*(extend(c) for c in raw)))
    merged = []
    cur = [flat[0]]
    for r in flat[1:]:
        if r - cur[-1] <= max_gap:
            cur.append(r)
        else:
            merged.append(cur)
            cur = [r]
    merged.append(cur)
    return [float(np.mean(c)) for c in merged]


def trace_curves(scan_mask, n_curves, x_range=None, max_y_jump=15, max_gap_columns=8, cluster_gap=3,
                  bridge_rows=None, ink=None):
    """Column-by-column multi-object tracking: maintains up to `n_curves`
    active traces, assigning each column's ink-clusters to whichever active
    trace's last-known y is closest (classic nearest-neighbor
    continuation), starting a new trace for an unclaimed cluster if fewer
    than `n_curves` are currently active, and letting a trace go quiet
    (skipped, not deleted) for up to `max_gap_columns` consecutive columns
    with no matching cluster (dash gaps, or a column that fell entirely on
    a removed gridline) before considering it ended.

    `bridge_rows`: forwarded to `_cluster_column()` -- see that function's
    own docstring. Pass the same `grid_rows` array `detect_gridlines()`
    returned for this image so a within-column gap made entirely of
    deleted gridline rows re-fuses into one cluster instead of splitting
    the curve's own ink where it crosses that gridline. `ink`: the full
    ORIGINAL (pre-gridline-deletion) ink mask `scan_mask` was derived
    from, same shape -- also forwarded to `_cluster_column()` (as that
    column's own `ink_rows`) so a bridge recomputes its centroid from the
    real, continuous curve ink rather than the two unevenly-sized
    fragments deletion left behind. Only consulted when `bridge_rows` is
    also given.

    Where multiple traces' clusters have collapsed onto the same shared
    pixel-cluster (curves visually coincident -- confirmed real and common
    in the middle of these charts, see module docstring), every trace
    still active at that column is assigned the SAME cluster; this is the
    accepted merged-curve approximation, not a bug.

    Note for `n_curves=1` callers: a trace that goes fully quiet (exceeds
    `max_gap_columns`) and later re-acquires ink does NOT start a new,
    separate output trace -- there is only ever one slot, so the later
    points are appended onto the SAME list as if continuous. This is
    harmless when the gap is a real mid-curve interruption (e.g. a
    gridline crossing) but will silently splice in an unrelated later
    cluster (a stray mark well past the curve's real end, say) if one
    exists past a long gap -- confirmed on Delta 100 before its own
    tick-stub artifacts were filtered upstream (see `build_scan_mask`).
    Bound `x_range` to the curve's own real extent (verify via QA overlay)
    rather than the full frame if a large spurious gap shows up in the
    output.

    Returns a list of `n_curves` traces, each a list of (x, y) pixel-space
    points (NOT yet calibrated to data units -- caller applies axis
    calibration separately, same convention as extract_traces_in_region)."""
    x0, x1 = x_range if x_range is not None else (0, scan_mask.shape[1])
    traces = [[] for _ in range(n_curves)]
    active_y = [None] * n_curves  # last known y per trace slot
    quiet_count = [0] * n_curves

    for x in range(x0, x1):
        col_rows = np.where(scan_mask[:, x])[0]
        ink_rows = np.where(ink[:, x])[0] if (bridge_rows is not None and ink is not None) else None
        clusters = _cluster_column(col_rows, max_gap=cluster_gap, bridge_rows=bridge_rows, ink_rows=ink_rows)
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
