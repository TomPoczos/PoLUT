"""
Digitizes Fuji "Characteristic Curves" panels confirmed to be embedded
RASTER images (CCITTFaxDecode bitonal scans), not vector paths -- see
BLOCKED.md's "embedded raster image (6 files)" entry. Unlike every other
strategy in this project, there is no PDF drawing-object metadata to key
off at all (no color, no dash array, no stroke width) -- only pixels.
`raster_tracer.py` holds the actual pixel-tracing mechanics (gridline
detection, text/legend filtering, column-scan multi-object tracking); this
module wires that into the same consolidated-data JSON schema and
bin_average/isotonic_regression/RDP post-processing every other product
uses, via a standalone pipeline (not `ChartSpec`/`digitize_chart` -- the
raster case doesn't fit that abstraction's vector-oriented parameters
cleanly enough to be worth forcing, e.g. `region_bbox`/`legend_bbox` are
page-space there but naturally image-pixel-space here).

Real, load-bearing caveat carried into every product's `digitizer_notes`
(2026-07-06, confirmed on Velvia 50, expected to generalize): these charts'
curves run visually COINCIDENT for most of their range (only genuinely
separated in the toe or shoulder) -- connected-component tracing cannot
split a single fused blob into 3 without either (a) skeletonizing and
reading dash-periodicity along the fused ink (deliberately not pursued
this round, see conversation with user) or (b) accepting a shared/merged
trace for the fused stretch, which is what this module does, the same
accepted approximation already used for Ilford CooltoneRC's near-identical
grade 4/5 curves. Only the genuinely-separated region (usually the toe)
carries real per-curve distinction; this is disclosed, not silently wrong.

Curve IDENTITY (which trace is R/G/B): the upright legend text ("R"/"G"/
"B") is itself baked into the raster image and can be OCR'd (confirmed
reliable on Velvia 50 -- unlike Fuji's ROTATED inline labels which OCR
poorly, this legend is small but upright and isolated from curve ink).
Cross-check with a direct visual read of the toe's density ORDER (not just
"which two look close") resolves identity reliably even when two curves
are nearly coincident -- confirmed on Velvia 50 (2026-07-06): G and B look
almost indistinguishable at a glance, but the real toe order (checked
directly against the rendered chart, not assumed) is G > B > (larger gap)
> R, which exactly matched this file's trace1/trace2/trace0 without any
guessing. Don't downgrade a near-coincident pair to "arbitrary/unresolved"
before actually checking the toe order -- that was tried here first and
was wrong to assume; a real, if narrow, visual gap was there to find.

Separately (and NOT resolved by the above): a trace can have a real
COVERAGE gap even once its identity is certain -- if it only becomes
distinguishable from its near-neighbor partway across the frame (confirmed
on Velvia 50's B trace, which isn't separately traceable until well past
the true toe), its recorded extremum is not the curve's real extremum,
just wherever it first split off. This is a genuine, disclosed data-
completeness limitation, independent of the identity question above.

A SECOND, easier raster sub-case exists (confirmed on Provia 100F,
2026-07-06): some files' "Characteristic Curves" panel isn't one single
flattened bitonal image but SEVERAL stacked images at the identical
placement rect -- confirmed via `page.get_images()` showing 4 xrefs at the
same rect, and each one, viewed individually, is either the shared
background (frame/gridlines/axis text/legend text, no curve ink at all)
or exactly ONE curve's own ink and nothing else. This means curve
identity and separation are already resolved AT THE SOURCE -- no
column-scan/multi-object-tracking needed at all, just a direct per-column
centroid read of each individual layer (`digitize_multilayer_raster_chart`/
`multilayer_raster_product`). The SAME coincident-curve limitation still
applies (confirmed on Provia 100F: only the solid/Red layer is a complete
curve; Green/Blue's own separate layers only contain ink where they're
visually distinguishable from Red, empty elsewhere), but at least it's a
property of the source file, not an artifact of the tracing algorithm.
**Real mixup caught and fixed while building this** (2026-07-06): dash
STYLE must be checked against the panel's own rendered LEGEND SWATCHES
directly, not inferred by comparing two extracted layers' dash appearance
to each other from memory -- an initial pass swapped Green and Blue
(assumed dash-dot was Blue based on eyeballing the individual layer images,
when the actual legend showed Green=dash-dot, Blue=plain dash). Always
render and re-check the legend swatch itself for the specific file, not a
recollection of a different file's convention.
"""

import json
from pathlib import Path

import fitz
import numpy as np

from digitizer_core import bin_average, count_violations, isotonic_regression, simplify_to_target
from ocr_helpers import ocr_axis_calib
from product import CONSOLIDATED_ROOT, PDF_ROOT, _slug
from raster_tracer import build_scan_mask, detect_gridlines, load_ink_mask, trace_curves

# All raster-pipeline QA overlays (any extraction_method starting "raster_") go
# here, not next to their product JSON -- a dedicated, browsable location for
# visually re-checking every file that used pixel-tracing rather than vector
# path extraction, since this whole class of approach has shown real, easy-to-
# miss failure modes (tilted-gridline over/under-deletion, wrongly-reasoned
# trace-range trimming) that a vector strategy's ChartSpec pipeline doesn't
# have (2026-07-06, user-requested after the Superia 100 investigation).
VERIFICATION_OVERLAY_DIR = CONSOLIDATED_ROOT / "verification" / "curve-shape-overlay"


def digitize_raster_chart(pdf_stub, page_index, image_index, x_tick_bbox, y_tick_bbox,
                           x_tick_regex, y_tick_regex, legend_exclude_image_box,
                           n_curves=3, gridline_frac_threshold=0.15, text_max_width=60,
                           text_max_height=30, monotonic="decreasing", extra_exclude_image_boxes=None,
                           frame_bottom_override=None, trace_x_range=None, max_y_jump=15,
                           max_gap_columns=8, gridline_row_sample_x_range=None,
                           gridline_col_sample_y_range=None):
    """Runs the full raster pipeline for one chart: load image, detect/
    exclude gridlines + text/legend + outer frame, column-scan trace,
    calibrate (OCR, page-space, composed with the image's own placement
    rect into a single image-pixel -> data-value transform), bin/
    isotonic-regress/simplify each trace the same way every vector
    strategy does. Returns (traces_pixel_space, calibrated_results) where
    calibrated_results is a list of `n_curves` dicts shaped like
    digitize_chart's per-curve result (points/points_dense/n_raw_vertices/
    n_violations/likely_direction), in TRACE-INDEX order (0..n_curves-1,
    NOT yet mapped to curve names -- caller assigns identity).

    `extra_exclude_image_boxes`: list of (y0,y1,x0,x1) image-pixel regions
    to blank out BEFORE tracing, in addition to the legend box -- confirmed
    necessary on Sensia 100 (2026-07-06): its "Exposure:/Process:/
    Densitometry:" info-text box sits INSIDE the chart frame (unlike
    Velvia 50's, which didn't overlap real curve-scan columns), and the
    size-based text filter (`text_max_width`/`text_max_height`) can't
    reliably tell a small text glyph apart from a single DASH FRAGMENT of
    a dashed curve -- they're genuinely similar sizes. When a file's
    dashed curves go missing entirely after the size-based filter (not
    just fragmented), that's the likely cause: switch to explicit
    position-based exclusion for the file's own text blocks instead of
    tightening the size thresholds further.

    `frame_bottom_override`: use when `detect_gridlines` finds a spurious
    wide text block (e.g. a title like "Exposure [log H...]" baked into
    the image, sitting below the real frame) and includes it in
    `grid_rows`, pushing `grid_rows.max()` far past the REAL bottom
    gridline -- confirmed on Sensia 100 and Superia 100 (2026-07-06).
    Symptom: a real axis tick label between the true frame bottom and the
    false cluster survives the frame-boundary exclusion and gets traced as
    curve ink. Pass the real bottom gridline row explicitly once you've
    checked `detect_gridlines`'s raw output for an anomalous wide cluster
    like this. `trace_x_range`: use to skip a narrow noisy strip just
    inside the left/right frame border (confirmed on Superia 100: a stray
    high-density point near the left border and a spurious flat run near
    the right border, both from residual pixels near a deleted gridline
    column, not real curve ink) -- verify via QA overlay, don't apply
    preemptively. `max_y_jump`/`max_gap_columns`: a curve can develop a
    fake dip-and-recover kink (not a full identity swap) when a gridline-
    crossing gap exceeds `max_gap_columns` (default 8) -- once a trace's
    `quiet_count` passes that threshold, `active_y` resets to None and the
    NEXT column treats it as a brand-new trace with no continuity check
    at all. Raising `max_gap_columns` bridges a same-length gap as a
    pause instead of an end, but the ROOT CAUSE on Superia 100
    (2026-07-06) turned out to be `gridline_row_sample_x_range`/
    `gridline_col_sample_y_range` (below) -- an inflated gridline-row
    deletion band, not the gap-tolerance itself; fix that first before
    reaching for `max_gap_columns`/`max_y_jump`, which only mask the
    symptom and can trade one artifact for a different one elsewhere.
    `gridline_row_sample_x_range`/`gridline_col_sample_y_range`: passed
    through to `detect_gridlines` (see its own docstring) -- confirmed
    on Superia 100 that measuring gridline ink-fraction across the WHOLE
    image inflates a 1-2px-thick gridline into a false 4-5px band
    wherever a curve runs close to parallel with it, and deleting that
    inflated band silently removes real curve ink for several columns.
    Verify via QA overlay that no two same-direction curves cross or
    kink when the source chart doesn't show one."""
    pdf_path = PDF_ROOT / pdf_stub
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    ink, rect = load_ink_mask(page, image_index=image_index)
    img_h, img_w = ink.shape

    px_slope, px_intercept = ocr_axis_calib(page, x_tick_bbox, tick_regex=x_tick_regex, axis="x")
    py_slope, py_intercept = ocr_axis_calib(page, y_tick_bbox, tick_regex=y_tick_regex, axis="y")
    x_scale = (rect.x1 - rect.x0) / img_w
    y_scale = (rect.y1 - rect.y0) / img_h
    csx = px_slope * x_scale
    cix = px_slope * rect.x0 + px_intercept
    csy = py_slope * y_scale
    ciy = py_slope * rect.y0 + py_intercept

    grid_rows, grid_cols = detect_gridlines(
        ink, frac_threshold=gridline_frac_threshold,
        row_sample_x_range=gridline_row_sample_x_range,
        col_sample_y_range=gridline_col_sample_y_range,
    )
    if text_max_width is not None:
        scan = build_scan_mask(ink, grid_rows, grid_cols, text_max_width=text_max_width,
                                text_max_height=text_max_height)
    else:
        # Position-only exclusion (no size-based text filter at all) --
        # use when the file's dashed curves get wrongly stripped as "text"
        # regardless of threshold tuning (see extra_exclude_image_boxes).
        scan = ink.copy()
        grid_row_mask = np.zeros(ink.shape[0], dtype=bool)
        grid_row_mask[grid_rows] = True
        grid_col_mask = np.zeros(ink.shape[1], dtype=bool)
        grid_col_mask[grid_cols] = True
        scan[grid_row_mask, :] = False
        scan[:, grid_col_mask] = False
    ftop = grid_rows.min()
    fbottom = frame_bottom_override if frame_bottom_override is not None else grid_rows.max()
    fleft, fright = grid_cols.min(), grid_cols.max()
    scan[:ftop + 1, :] = False
    scan[fbottom:, :] = False
    scan[:, :fleft + 1] = False
    scan[:, fright:] = False
    if legend_exclude_image_box is not None:
        y0, y1, x0, x1 = legend_exclude_image_box
        scan[y0:y1, x0:x1] = False
    for y0, y1, x0, x1 in (extra_exclude_image_boxes or []):
        scan[y0:y1, x0:x1] = False

    x_range = trace_x_range if trace_x_range is not None else (fleft + 1, fright - 1)
    raw_traces = trace_curves(scan, n_curves=n_curves, x_range=x_range, max_y_jump=max_y_jump,
                               max_gap_columns=max_gap_columns)
    results = []
    for tr in raw_traces:
        if not tr:
            results.append(None)
            continue
        pxs = [p[0] for p in tr]
        pys = [p[1] for p in tr]
        data_x = [csx * p + cix for p in pxs]
        data_y = [csy * p + ciy for p in pys]
        bx, by = bin_average(data_x, data_y, 60)
        by = np.array(isotonic_regression(by, increasing=(monotonic == "increasing")))
        simplified = simplify_to_target(bx, by)
        sx = [round(float(x), 4) for x, y in simplified]
        sy = [round(float(y), 4) for x, y in simplified]
        v_inc = count_violations(sy, increasing=True)
        v_dec = count_violations(sy, increasing=False)
        likely_dir = "increasing" if v_inc <= v_dec else "decreasing"
        results.append({
            "points": list(zip(sx, sy)),
            "points_dense": [[round(float(x), 4), round(float(y), 4)] for x, y in zip(bx, by)],
            "n_raw_vertices": len(tr),
            "n_violations": min(v_inc, v_dec),
            "likely_direction": likely_dir,
        })
    doc.close()
    return results, (csx, cix, csy, ciy)


def _render_qa_overlays(bg_ink, curve_names, results, out_stem, calib):
    """Shared rendering core for both raster QA overlay flavors: given an
    ALREADY-COMPOSITED background ink array (must contain the real curve
    lines, not just frame/gridlines/text -- see each caller for how it
    builds this), renders BOTH:
    (a) one combined PNG with every curve plotted together (the original
        style, `{out_stem}_qa_overlay.png`), and
    (b) one PNG per curve (`{out_stem}_<curve_name>_qa_overlay.png`),
        added 2026-07-06 after (a) alone made it impossible to tell
        whether a curve was really tracked through a visually-converged
        region, since overlapping scatter dots from multiple curves hid
        each other there.
    Both are kept (not one replacing the other, 2026-07-06 follow-up
    request): the combined view is still useful for judging relative
    curve identity/ordering at a glance, while the per-curve views are
    what you check a single curve's own fit against.
    Returns {"combined": Path, "per_curve": {curve_name: Path}}."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    csx, cix, csy, ciy = calib
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    extent = [csx * 0 + cix, csx * bg_ink.shape[1] + cix, csy * bg_ink.shape[0] + ciy, csy * 0 + ciy]

    combined_path = out_stem.parent / f"{out_stem.name}_qa_overlay.png"
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.imshow(np.where(bg_ink, 1, 0), cmap="gray", extent=extent, aspect="auto")
    colors = plt.cm.tab10.colors
    for i, name in enumerate(curve_names):
        r = results.get(name)
        if r is None:
            continue
        pts = r["points"]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], "o-", markersize=3,
                color=colors[i % len(colors)], label=f"{name} (n={len(pts)})")
    ax.legend(fontsize=7, loc="best")
    ax.set_xlabel("data x")
    ax.set_ylabel("data y")
    fig.savefig(combined_path, dpi=110)
    plt.close(fig)

    per_curve_paths = {}
    for name in curve_names:
        r = results.get(name)
        if r is None:
            continue
        fig, ax = plt.subplots(figsize=(9, 7))
        ax.imshow(np.where(bg_ink, 1, 0), cmap="gray", extent=extent, aspect="auto")
        pts = r["points"]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], "o-", markersize=3,
                color="tab:red", label=f"{name} (n={len(pts)})")
        ax.legend(fontsize=8, loc="best")
        ax.set_xlabel("data x")
        ax.set_ylabel("data y")
        curve_out_path = out_stem.parent / f"{out_stem.name}_{name}_qa_overlay.png"
        fig.savefig(curve_out_path, dpi=110)
        plt.close(fig)
        per_curve_paths[name] = curve_out_path

    return {"combined": combined_path, "per_curve": per_curve_paths}


def _qa_overlay_json_field(qa_paths):
    """Converts a `_render_qa_overlays` return value into the JSON-serializable
    shape stored under `charts.characteristic_curve.qa_overlay_png`."""
    return {
        "combined": str(qa_paths["combined"].relative_to(CONSOLIDATED_ROOT)),
        "per_curve": {k: str(v.relative_to(CONSOLIDATED_ROOT)) for k, v in qa_paths["per_curve"].items()},
    }


def render_raster_qa_overlay(pdf_stub, page_index, image_index, curve_names, results, out_stem,
                              calib):
    """Single-layer raster case: the one embedded image already contains
    every curve's own ink (they're not on separate layers), so it's used
    directly as the QA background. See `_render_qa_overlays` for the
    actual rendering (combined + per-curve PNGs) and `out_stem`/return
    convention."""
    doc = fitz.open(PDF_ROOT / pdf_stub)
    page = doc[page_index]
    ink, rect = load_ink_mask(page, image_index=image_index)
    doc.close()
    return _render_qa_overlays(ink, curve_names, results, out_stem, calib)


def raster_product(pdf_stub, product_name, iso, year, film_type, page_index, image_index,
                    x_tick_bbox, y_tick_bbox, legend_exclude_image_box, curve_order,
                    x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0", monotonic="decreasing",
                    extra_notes="", text_max_width=60, text_max_height=30,
                    extra_exclude_image_boxes=None, frame_bottom_override=None, trace_x_range=None,
                    max_y_jump=15, max_gap_columns=8, gridline_row_sample_x_range=None,
                    gridline_col_sample_y_range=None):
    """`curve_order`: list of `n_curves` names in TRACE-index order (i.e.
    curve_order[i] is whichever real curve name trace i was assigned to --
    caller determines this via legend OCR/toe-value inspection BEFORE
    calling, see module docstring; not automatic). Pass
    `text_max_width=None` to disable the size-based text filter entirely
    in favor of `extra_exclude_image_boxes`; see `digitize_raster_chart`'s
    docstring for `frame_bottom_override`/`trace_x_range`/`max_y_jump`/
    `max_gap_columns`/`gridline_row_sample_x_range`/
    `gridline_col_sample_y_range`."""
    n_curves = len(curve_order)
    results, calib = digitize_raster_chart(
        pdf_stub, page_index, image_index, x_tick_bbox, y_tick_bbox,
        x_tick_regex, y_tick_regex, legend_exclude_image_box,
        n_curves=n_curves, monotonic=monotonic, text_max_width=text_max_width,
        text_max_height=text_max_height, extra_exclude_image_boxes=extra_exclude_image_boxes,
        frame_bottom_override=frame_bottom_override, trace_x_range=trace_x_range,
        gridline_row_sample_x_range=gridline_row_sample_x_range,
        gridline_col_sample_y_range=gridline_col_sample_y_range,
        max_y_jump=max_y_jump, max_gap_columns=max_gap_columns,
    )
    named_results = {}
    for name, r in zip(curve_order, results):
        if r is None:
            print(f"  WARNING: no points found for {name}")
            continue
        named_results[name] = r
        pts = r["points"]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        print(f"  {name}: {r['n_raw_vertices']} raw points (raster_column_scan) -> "
              f"{len(pts)} simplified points, x range [{min(xs):.3f},{max(xs):.3f}] "
              f"y range [{min(ys):.3f},{max(ys):.3f}]  n_violations={r['n_violations']}")

    stem = "_".join(["fuji", _slug(product_name), f"iso{iso}", str(year)])
    out_dir = CONSOLIDATED_ROOT / "film" / "photography" / film_type / "fuji"
    out_dir.mkdir(parents=True, exist_ok=True)
    VERIFICATION_OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    qa_stem = VERIFICATION_OVERLAY_DIR / f"{stem}_characteristic_curve"
    qa_paths = render_raster_qa_overlay(pdf_stub, page_index, image_index, curve_order, named_results,
                                         qa_stem, calib)

    doc_out = {
        "source_pdf": pdf_stub,
        "brand": "fuji",
        "product_name": product_name,
        "application_area": "photography",
        "film_type": film_type,
        "medium": "color",
        "iso": iso,
        "year": year,
        "layer_order": ["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        "extraction_method": "raster_column_scan",
        "charts": {
            "characteristic_curve": {
                "page_index": page_index,
                "x_label": "log_exposure_lux_seconds",
                "y_label": "density_status_a",
                "curves": named_results,
                "qa_overlay_png": _qa_overlay_json_field(qa_paths),
            },
        },
        "digitizer_notes": (
            "'Characteristic Curves' panel is an embedded raster image (CCITTFaxDecode bitonal "
            "scan), not vector paths -- traced via raster_tracer.py's column-scan multi-object "
            "tracking (gridline/text/legend exclusion, nearest-active-trace continuation), not "
            "any color/dash-metadata strategy (none exists for a raster image). Curves run "
            "visually coincident for most of the chart's range (only genuinely separated in the "
            "toe/shoulder) -- no dash-pattern disambiguation was attempted for the fused region "
            "(would need skeletonization), so traces that are fused for a stretch share the same "
            "underlying pixel-path there, an accepted approximation, same precedent as Ilford "
            "CooltoneRC's near-identical grade 4/5 curves. Curve identity assigned via legend OCR "
            "cross-checked against each trace's own toe/shoulder separation. " + extra_notes
        ),
    }
    out_path = out_dir / f"{stem}.json"
    out_path.write_text(json.dumps(doc_out, indent=2))
    print(f"-> {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Spliced single-layer raster (unstable 3-slot tracking through a long
# coincident stretch)
# ---------------------------------------------------------------------------

def digitize_spliced_raster_chart(pdf_stub, page_index, image_index, x_tick_bbox, y_tick_bbox,
                                   x_tick_regex, y_tick_regex, legend_exclude_image_box,
                                   toe_merge_image_x, curve_order, monotonic="decreasing",
                                   gridline_frac_threshold=0.15, extra_exclude_image_boxes=None,
                                   merged_x_clip=None):
    """For single-layer files (see module docstring) where running
    `trace_curves` with `n_curves=len(curve_order)` across the WHOLE image
    is unstable, not just fused -- confirmed on Sensia 100 (2026-07-06):
    once 3 trace slots are all real-and-active simultaneously, they can
    lose track of each other (one slot effectively "getting stuck"/going
    quiet early) well BEFORE the curves visually re-diverge, truncating
    real data across ALL curves alike (all 3 curves lost their true
    shoulder/Dmin tail this way, not just the expected merged-region
    duplication). A single trace (`n_curves=1`) across the SAME stretch
    completes cleanly with no such loss -- multi-slot competition, not the
    image data, is the cause.

    Splices two separate traces instead of one 3-slot pass: `n_curves=3`
    ONLY up to `toe_merge_image_x` (image-pixel column, the real
    toe/shoulder region where curves are genuinely separate and 3 slots
    stay stable over a short stretch), then a single `n_curves=1` trace
    for the remainder, reused identically for every name in `curve_order`
    (this is the accepted merged-curve approximation, same precedent as
    Velvia 50/Ilford CooltoneRC -- not new here, just applied via a
    cleaner two-pass trace instead of a single unstable 3-slot one).
    `merged_x_clip`: optional image-x to drop the merged trace beyond (a
    spurious point right at the frame's rightmost edge, e.g. a stray
    frame-corner pixel, confirmed on Sensia 100 -- verify via the QA
    overlay before assuming a new file needs this)."""
    pdf_path = PDF_ROOT / pdf_stub
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    ink, rect = load_ink_mask(page, image_index=image_index)
    img_h, img_w = ink.shape

    px_slope, px_intercept = ocr_axis_calib(page, x_tick_bbox, tick_regex=x_tick_regex, axis="x")
    py_slope, py_intercept = ocr_axis_calib(page, y_tick_bbox, tick_regex=y_tick_regex, axis="y")
    x_scale = (rect.x1 - rect.x0) / img_w
    y_scale = (rect.y1 - rect.y0) / img_h
    csx = px_slope * x_scale
    cix = px_slope * rect.x0 + px_intercept
    csy = py_slope * y_scale
    ciy = py_slope * rect.y0 + py_intercept

    grid_rows, grid_cols = detect_gridlines(ink, frac_threshold=gridline_frac_threshold)
    scan = ink.copy()
    grid_row_mask = np.zeros(ink.shape[0], dtype=bool)
    grid_row_mask[grid_rows] = True
    grid_col_mask = np.zeros(ink.shape[1], dtype=bool)
    grid_col_mask[grid_cols] = True
    scan[grid_row_mask, :] = False
    scan[:, grid_col_mask] = False
    ftop, fbottom = grid_rows.min(), grid_rows.max()
    fleft, fright = grid_cols.min(), grid_cols.max()
    scan[:ftop + 1, :] = False
    scan[fbottom:, :] = False
    scan[:, :fleft + 1] = False
    scan[:, fright:] = False
    if legend_exclude_image_box is not None:
        y0, y1, x0, x1 = legend_exclude_image_box
        scan[y0:y1, x0:x1] = False
    for y0, y1, x0, x1 in (extra_exclude_image_boxes or []):
        scan[y0:y1, x0:x1] = False

    n_curves = len(curve_order)
    merged = trace_curves(scan, n_curves=1, x_range=(fleft + 1, fright - 1))[0]
    if merged_x_clip is not None:
        merged = [p for p in merged if p[0] < merged_x_clip]
    toe_traces = trace_curves(scan, n_curves=n_curves, x_range=(fleft + 1, toe_merge_image_x))
    merged_after = [p for p in merged if p[0] >= toe_merge_image_x]

    results = {}
    for name, toe_tr in zip(curve_order, toe_traces):
        full = toe_tr + merged_after
        if not full:
            results[name] = None
            continue
        data_x = [csx * p[0] + cix for p in full]
        data_y = [csy * p[1] + ciy for p in full]
        bx, by = bin_average(data_x, data_y, 60)
        by = np.array(isotonic_regression(by, increasing=(monotonic == "increasing")))
        simplified = simplify_to_target(bx, by)
        sx = [round(float(x), 4) for x, y in simplified]
        sy = [round(float(y), 4) for x, y in simplified]
        v_inc = count_violations(sy, increasing=True)
        v_dec = count_violations(sy, increasing=False)
        results[name] = {
            "points": list(zip(sx, sy)),
            "points_dense": [[round(float(x), 4), round(float(y), 4)] for x, y in zip(bx, by)],
            "n_raw_vertices": len(full),
            "n_violations": min(v_inc, v_dec),
            "likely_direction": "increasing" if v_inc <= v_dec else "decreasing",
        }
    doc.close()
    return results, (csx, cix, csy, ciy)


def spliced_raster_product(pdf_stub, product_name, iso, year, film_type, page_index, image_index,
                            x_tick_bbox, y_tick_bbox, legend_exclude_image_box, toe_merge_image_x,
                            curve_order, x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
                            monotonic="decreasing", extra_notes="", extra_exclude_image_boxes=None,
                            merged_x_clip=None):
    results, calib = digitize_spliced_raster_chart(
        pdf_stub, page_index, image_index, x_tick_bbox, y_tick_bbox, x_tick_regex, y_tick_regex,
        legend_exclude_image_box, toe_merge_image_x, curve_order, monotonic=monotonic,
        extra_exclude_image_boxes=extra_exclude_image_boxes, merged_x_clip=merged_x_clip,
    )
    for name, r in results.items():
        if r is None:
            print(f"  WARNING: no points found for {name}")
            continue
        pts = r["points"]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        print(f"  {name}: {r['n_raw_vertices']} raw points (raster_column_scan_spliced) -> "
              f"{len(pts)} simplified points, x range [{min(xs):.3f},{max(xs):.3f}] "
              f"y range [{min(ys):.3f},{max(ys):.3f}]  n_violations={r['n_violations']}")

    stem = "_".join(["fuji", _slug(product_name), f"iso{iso}", str(year)])
    out_dir = CONSOLIDATED_ROOT / "film" / "photography" / film_type / "fuji"
    out_dir.mkdir(parents=True, exist_ok=True)
    VERIFICATION_OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    qa_stem = VERIFICATION_OVERLAY_DIR / f"{stem}_characteristic_curve"
    qa_paths = render_raster_qa_overlay(pdf_stub, page_index, image_index, curve_order, results, qa_stem, calib)
    doc_out = {
        "source_pdf": pdf_stub,
        "brand": "fuji",
        "product_name": product_name,
        "application_area": "photography",
        "film_type": film_type,
        "medium": "color",
        "iso": iso,
        "year": year,
        "layer_order": ["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        "extraction_method": "raster_column_scan_spliced",
        "charts": {
            "characteristic_curve": {
                "page_index": page_index,
                "x_label": "log_exposure_lux_seconds",
                "y_label": "density_status_a",
                "curves": {k: v for k, v in results.items() if v is not None},
                "qa_overlay_png": _qa_overlay_json_field(qa_paths),
            },
        },
        "digitizer_notes": (
            "'Characteristic Curves' panel is an embedded raster image, traced via a SPLICED "
            "column-scan: a stable single-trace pass covers the full range (curves run visually "
            "coincident for most of it), and a separate 3-slot pass covers only the toe/shoulder "
            "region where curves are genuinely separate -- running 3 slots across the WHOLE image "
            "at once was tried first and was unstable (lost real data for all 3 curves alike, not "
            "just the expected merged-region duplication), see raster_tracer.py/fuji_raster.py "
            "module docstrings. Curve identity assigned via legend OCR cross-checked against each "
            "trace's own toe/shoulder separation. " + extra_notes
        ),
    }
    out_path = out_dir / f"{stem}.json"
    out_path.write_text(json.dumps(doc_out, indent=2))
    print(f"-> {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Multi-layer raster (several stacked per-curve images at one placement rect)
# ---------------------------------------------------------------------------

def _load_layer_mask(doc, xref):
    pix = fitz.Pixmap(doc, xref)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    uniq = set(np.unique(arr).tolist())
    if not uniq <= {0, 255}:
        raise RuntimeError(f"expected a bitonal layer (values {{0,255}}), got {sorted(uniq)[:10]}")
    return arr == 255


def digitize_multilayer_raster_chart(pdf_stub, page_index, curve_xrefs, x_tick_bbox, y_tick_bbox,
                                      x_tick_regex, y_tick_regex, legend_exclude_image_box=None,
                                      monotonic="decreasing", x_tick_zoom=8.0, y_tick_zoom=8.0):
    """For the "several stacked per-curve images at one rect" sub-case (see
    module docstring) -- `curve_xrefs`: dict {curve_name: xref}, each xref
    already known (via visual inspection, cross-checked against the
    panel's own legend swatches, NOT assumed from another file) to contain
    exactly one curve's own ink and nothing else. No column-scan tracking
    needed -- a straight per-column centroid read of each layer's own ink
    is unambiguous by construction. Returns {curve_name: result_dict} in
    the same shape as `digitize_raster_chart`.

    `x_tick_zoom`/`y_tick_zoom`: OCR render zoom for the tick regions --
    confirmed necessary as a per-file override on RTP II (2026-07-06): the
    default (8.0) mis-signed a tick AND dropped another entirely (missed
    "-2.0" outright), silently fitting a wrong-signed calibration that
    only surfaced as absurd output (all 3 curves collapsed to a 2-point
    flat line at the wrong x/y) -- not an OCR error that raised, so always
    sanity-check the resulting x/y range against the visible chart rather
    than trusting a clean run. Zoom 6.0 recovered the missing tick and
    read the sign correctly for this file."""
    pdf_path = PDF_ROOT / pdf_stub
    doc = fitz.open(pdf_path)
    page = doc[page_index]

    any_xref = next(iter(curve_xrefs.values()))
    rect = page.get_image_rects(any_xref)[0]
    sample = _load_layer_mask(doc, any_xref)
    img_h, img_w = sample.shape

    px_slope, px_intercept = ocr_axis_calib(page, x_tick_bbox, tick_regex=x_tick_regex, axis="x",
                                             zoom=x_tick_zoom)
    py_slope, py_intercept = ocr_axis_calib(page, y_tick_bbox, tick_regex=y_tick_regex, axis="y",
                                             zoom=y_tick_zoom)
    x_scale = (rect.x1 - rect.x0) / img_w
    y_scale = (rect.y1 - rect.y0) / img_h
    csx = px_slope * x_scale
    cix = px_slope * rect.x0 + px_intercept
    csy = py_slope * y_scale
    ciy = py_slope * rect.y0 + py_intercept

    results = {}
    for name, xref in curve_xrefs.items():
        ink = _load_layer_mask(doc, xref)
        if legend_exclude_image_box is not None:
            y0, y1, x0, x1 = legend_exclude_image_box
            ink[y0:y1, x0:x1] = False
        raw = []
        for x in range(ink.shape[1]):
            rows = np.where(ink[:, x])[0]
            if len(rows):
                raw.append((x, float(rows.mean())))
        if not raw:
            results[name] = None
            continue
        data_x = [csx * p[0] + cix for p in raw]
        data_y = [csy * p[1] + ciy for p in raw]
        bx, by = bin_average(data_x, data_y, 60)
        by = np.array(isotonic_regression(by, increasing=(monotonic == "increasing")))
        simplified = simplify_to_target(bx, by)
        sx = [round(float(x), 4) for x, y in simplified]
        sy = [round(float(y), 4) for x, y in simplified]
        v_inc = count_violations(sy, increasing=True)
        v_dec = count_violations(sy, increasing=False)
        results[name] = {
            "points": list(zip(sx, sy)),
            "points_dense": [[round(float(x), 4), round(float(y), 4)] for x, y in zip(bx, by)],
            "n_raw_vertices": len(raw),
            "n_violations": min(v_inc, v_dec),
            "likely_direction": "increasing" if v_inc <= v_dec else "decreasing",
        }
    doc.close()
    return results, (csx, cix, csy, ciy)


def render_multilayer_qa_overlay(pdf_stub, page_index, background_xref, curve_xrefs, results,
                                  out_stem, calib):
    """Same purpose as `render_raster_qa_overlay`. `curve_xrefs`: dict
    {curve_name: xref} (same dict passed to `multilayer_raster_product`).

    The background for context is background_xref OR'd together with
    EVERY curve's own xref layer, not the shared frame/gridline/text
    layer alone -- confirmed necessary (2026-07-06): the shared layer by
    itself has no curve ink at all (each curve's line lives on its own
    separate bitonal image in this file format, see module docstring), so
    using it alone as backdrop meant the QA overlay showed our extracted
    trace against a blank gridline frame with no real curve to visually
    check it against -- silently useless for exactly the thing a QA
    overlay exists to catch. `out_stem`/return value: same convention as
    `render_raster_qa_overlay`."""
    doc = fitz.open(PDF_ROOT / pdf_stub)
    bg = _load_layer_mask(doc, background_xref)
    for xref in curve_xrefs.values():
        bg = bg | _load_layer_mask(doc, xref)
    doc.close()
    return _render_qa_overlays(bg, list(curve_xrefs.keys()), results, out_stem, calib)


def multilayer_raster_product(pdf_stub, product_name, iso, year, film_type, page_index,
                               background_xref, curve_xrefs, x_tick_bbox, y_tick_bbox,
                               legend_exclude_image_box=None, x_tick_regex=r"-?\d\.0",
                               y_tick_regex=r"\d\.0", monotonic="decreasing", extra_notes="",
                               x_tick_zoom=8.0, y_tick_zoom=8.0):
    """`curve_xrefs`: dict in curve-name order, e.g.
    {"red_cyan_forming_layer": 52, "green_magenta_forming_layer": 51,
    "blue_yellow_forming_layer": 53} -- identity determined by comparing
    each xref's own dash style against the panel's real legend swatches
    (see module docstring), not assumed. `x_tick_zoom`/`y_tick_zoom`: see
    `digitize_multilayer_raster_chart` -- always sanity-check the printed
    x/y range against the visible chart, a bad OCR zoom can silently
    mis-calibrate without raising."""
    results, calib = digitize_multilayer_raster_chart(
        pdf_stub, page_index, curve_xrefs, x_tick_bbox, y_tick_bbox,
        x_tick_regex, y_tick_regex, legend_exclude_image_box, monotonic=monotonic,
        x_tick_zoom=x_tick_zoom, y_tick_zoom=y_tick_zoom,
    )
    for name, r in results.items():
        if r is None:
            print(f"  WARNING: no points found for {name}")
            continue
        pts = r["points"]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        print(f"  {name}: {r['n_raw_vertices']} raw points (raster_multilayer) -> "
              f"{len(pts)} simplified points, x range [{min(xs):.3f},{max(xs):.3f}] "
              f"y range [{min(ys):.3f},{max(ys):.3f}]  n_violations={r['n_violations']}")

    stem = "_".join(["fuji", _slug(product_name), f"iso{iso}", str(year)])
    out_dir = CONSOLIDATED_ROOT / "film" / "photography" / film_type / "fuji"
    out_dir.mkdir(parents=True, exist_ok=True)
    VERIFICATION_OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    qa_stem = VERIFICATION_OVERLAY_DIR / f"{stem}_characteristic_curve"
    qa_paths = render_multilayer_qa_overlay(pdf_stub, page_index, background_xref, curve_xrefs,
                                             results, qa_stem, calib)

    doc_out = {
        "source_pdf": pdf_stub,
        "brand": "fuji",
        "product_name": product_name,
        "application_area": "photography",
        "film_type": film_type,
        "medium": "color",
        "iso": iso,
        "year": year,
        "layer_order": ["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        "extraction_method": "raster_multilayer",
        "charts": {
            "characteristic_curve": {
                "page_index": page_index,
                "x_label": "log_exposure_lux_seconds",
                "y_label": "density_status_a",
                "curves": {k: v for k, v in results.items() if v is not None},
                "qa_overlay_png": _qa_overlay_json_field(qa_paths),
            },
        },
        "digitizer_notes": (
            "'Characteristic Curves' panel is SEVERAL stacked embedded raster images at one "
            "placement rect, not one flattened image -- confirmed each xref (other than the "
            "shared background/frame/gridline/text layer) contains exactly one curve's own ink "
            "and nothing else, so curve identity/separation is resolved at the source (no "
            "column-scan tracing needed, just a direct per-column centroid read per layer). "
            "Identity (which xref is R/G/B) determined by matching each layer's dash style "
            "against the panel's own real legend swatches. Curves whose own layer only contains "
            "ink in a portion of the frame (confirmed: only the solid/Red layer is typically "
            "complete) have a real, disclosed coverage gap elsewhere -- not a tracing artifact, "
            "a property of the source file (that curve is only separately drawn where visually "
            "distinguishable from another curve). " + extra_notes
        ),
    }
    out_path = out_dir / f"{stem}.json"
    out_path.write_text(json.dumps(doc_out, indent=2))
    print(f"-> {out_path}")
    return out_path
