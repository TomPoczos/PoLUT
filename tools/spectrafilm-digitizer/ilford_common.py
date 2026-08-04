"""
Shared helpers for Ilford black-and-white film products (products/ilford_*.py).

Ilford's pre-2018 fact-sheet template (confirmed so far: HP5 Plus; per
../curve_digitizer/ilford_film.py's own module docstring, also FP4 Plus,
Pan F Plus, Delta 400, XP2 Super) is a genuinely different shape from every
Kodak sheet this tool has handled so far: exactly ONE representative
Characteristic Curve (one developer, one time, one temp, stated to also
cover other formats) -- not a development-time family, and no
Contrast-Index-vs-time chart at all. So there is no bracket to build a
family from, and nothing for trix_common.py's CI-label machinery to attach
-- every Ilford film built from this template becomes exactly ONE
darktable stock (see stock_io.write_single_dev_time_stock, called with a
single dev_time_min straight from the curve's own caption text).

The 2018+ reprints of these same products (e.g. HP5-Plus_201811.pdf) embed
every chart as a flattened raster image, tick numbers included (confirmed
via page.get_images() -- 7-10 embedded images vs. 0 on the matching
pre-2018 sheet) -- a known dead end, see
../curve_digitizer/BLOCKED.md's "Ilford film -- 2018+ reprints" entry.
Always source from the pre-2018 sheet instead: same real product/curve,
just typeset as vector paths + (mostly) real text.

Two charts are needed per film here, unlike ../curve_digitizer/ilford_film.py
(which only digitizes the Characteristic Curve for its own .cube-LUT
pipeline) -- darktable's spektrafilm schema unconditionally requires
log_sensitivity/channel_density too (see CLAUDE.md's exposure_calibration.py
bullet), so the Spectral Sensitivity chart is not optional here:

1. Characteristic Curve -- `characteristic_curve_chart()`, ported from
   ../curve_digitizer/ilford_film.py's `_single_curve_chart`: auto-locates
   the panel from its own "CHARACTERISTIC"/"Relative"/"Density" text rather
   than a hand-picked per-file bbox, with an OCR fallback for any future
   film whose tick digits turn out to be vector-outlined shapes instead of
   real text -- confirmed a real per-file variation in curve_digitizer's
   own version (FP4 Plus/Delta 100/400/XP2 Super need OCR there, HP5 Plus/
   Pan F Plus don't), so don't assume one film's answer for another.
2. Spectral Sensitivity ("wedge spectrogram to tungsten light, 2850K") --
   new here, no curve_digitizer precedent (its own pipeline never needed
   this chart). HP5 Plus's own tick numbers on BOTH axes are vector-
   outlined shapes with zero extractable text (confirmed directly: no text
   span found anywhere near the chart, despite the curve ink itself being
   a real stroked vector path, traceable the normal way) -- OCR required
   (ocr_helpers.ocr_axis_calib). The wavelength (x) row specifically needs
   `whitelist=None` -- see ocr_helpers.py's own docstring for the real
   tesseract quirk this works around (the default digit-only whitelist
   merges this row's tightly-spaced 3-digit ticks into one token).
   `spectral_sensitivity_chart()` still tries real text first (same
   try/except shape as the characteristic-curve locator) in case a future
   Ilford film's spectral chart has real tick text despite its H&D chart
   needing OCR, or vice versa -- confirmed independent per chart on this
   vendor, not a single blanket per-file property.

`build_single_stock_bw_negative()` is the per-product orchestrator: digitize
both charts -> fit the density model (net density, base_density subtracted
per CLAUDE.md's density_model.py bullet) -> calibrate exposure
(exposure_calibration.py, required for every B&W negative film, same as
Tri-X) -> write via stock_io.write_single_dev_time_stock. A new Ilford film
on this same template is meant to need only a thin products/ilford_*.py
supplying its own PDF path/page indices/developer metadata, following
products/ilford_hp5plus.py's shape.
"""

import json
import re

import numpy as np

import fitz
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import canonical_grids as grids
import density_model as dm
import exposure_calibration as ec
import stock_io
from digitizer_core import ChartSpec, CurveSpec, bin_average, count_violations, digitize_chart, fit_axis, \
    isotonic_regression, simplify_to_target
from ocr_helpers import ocr_axis_calib
from raster_tracer import build_scan_mask, detect_gridlines, load_ink_mask, trace_curves


def _find_word(words, regex, topmost=True, rotated_only=False):
    """Returns the (x0, y0, x1, y1) bbox of the first word in
    `page.get_text("words")`'s output matching `regex`, preferring the
    topmost (smallest y0) match on the page -- same convention as
    ../curve_digitizer/ilford_film.py's own `_find`, needed because a
    two-column page layout (this vendor's standard template) can repeat
    common words (e.g. a stray lowercase "density") elsewhere in body text
    below the real chart; picking the topmost occurrence reliably lands on
    the chart's own title/axis-label text instead.

    `rotated_only` (confirmed needed for the Spectral Sensitivity panel,
    not needed for the Characteristic Curve one): this vendor draws a
    y-axis label rotated 90 degrees, so its own word bbox is taller than
    wide -- but the SAME word can also appear upright as part of the
    panel's own title (HP5 Plus: "SPECTRAL SENSITIVITY", the y-axis label
    is literally "Sensitivity" again), which topmost-first would otherwise
    grab instead since the title sits higher on the page. Filtering to
    bbox height > width picks the real rotated axis label specifically."""
    candidates = []
    for x0, y0, x1, y1, text, *_ in words:
        if not re.search(regex, text):
            continue
        if rotated_only and not (y1 - y0) > (x1 - x0):
            continue
        candidates.append((x0, y0, x1, y1))
    if not candidates:
        raise RuntimeError(f"{regex!r} not found in word list (rotated_only={rotated_only})")
    return min(candidates, key=lambda b: b[1]) if topmost else max(candidates, key=lambda b: b[1])


def characteristic_curve_chart(pdf_path, page_index, x_tick_regex=r"^[1234]$", y_tick_regex=r"^[123]\.0$"):
    """Auto-locates and builds the ChartSpec for Ilford's single-curve
    Characteristic Curve panel. The curve's own shoulder (max exposure, max
    density) always sits near the box's own top-right corner on this
    vendor's template (density increases upward = smaller page-y, exposure
    increases rightward) -- anchoring `label_position_override` there
    (rather than a hand-picked per-file point) is safe specifically because
    there is only ever one real trace in the region on this template, so
    nearest-trace matching can't actually confuse it with anything -- the
    anchor only needs to land closer to the real curve than to any frame/
    gridline artifact, not on the curve itself."""
    doc = fitz.open(str(pdf_path))
    page = doc[page_index]
    words_all = page.get_text("words")

    title = _find_word(words_all, r"(?i)^characteristic$")
    caption = _find_word(words_all, r"(?i)^relative$")
    # Case-SENSITIVE on purpose -- a lowercase "density" can show up in
    # ordinary body text elsewhere on the page, which the topmost-match
    # rule would otherwise grab instead of the real axis label.
    density_label = _find_word(words_all, r"^Density$")
    box = (title[0] - 10, title[3], density_label[2] + 15, caption[1])
    tick_box = (box[0], box[1], box[2], box[3] + 15)

    x_axis_calib_override = y_axis_calib_override = None
    try:
        fit_axis(words_all, x_tick_regex, "x", bbox=tick_box)
        fit_axis(words_all, y_tick_regex, "y", bbox=tick_box)
    except RuntimeError:
        x_tick_bbox = (box[0], box[3] - 20, box[2], box[3] + 15)
        y_tick_bbox = (box[2] - 95, box[1], box[2], box[3])
        x_axis_calib_override = ocr_axis_calib(page, x_tick_bbox, tick_regex=r"\d", axis="x")
        y_axis_calib_override = ocr_axis_calib(page, y_tick_bbox, tick_regex=r"\d\.\d", axis="y")
    doc.close()

    anchor_xy = (box[2] - 15, box[1] + 15)
    return ChartSpec(
        pdf=str(pdf_path), page_index=page_index, chart_id="characteristic_curve",
        x_tick_regex=x_tick_regex, y_tick_regex=y_tick_regex,
        x_label="relative_log_exposure", y_label="density_diffuse_visual",
        curves=[CurveSpec("density", label_position_override=anchor_xy)],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, axis_word_bbox=tick_box,
        x_axis_calib_override=x_axis_calib_override, y_axis_calib_override=y_axis_calib_override,
        monotonic_direction="increasing", min_trace_points=8,
    )


def characteristic_curve_points_raster(
    pdf_path, page_index, out_root, *, x_tick_regex=r"\d", y_tick_regex=r"\d\.\d",
    gridline_frac_threshold=0.5, text_max_width=60, text_max_height=30,
    tick_stub_max_thickness=8, border_touch_tol=10, max_y_jump=15, max_gap_columns=8,
    trace_x_range=None, monotonic_direction="increasing",
):
    """Digitizes Ilford's single-curve Characteristic Curve panel when it's
    an embedded RASTER image rather than vector paths -- confirmed needed
    on Ilford Delta 100 Professional, 2026-08-03: unlike every other film
    this template covers (HP5 Plus, and per curve_digitizer/ilford_film.py,
    FP4 Plus/Pan F Plus/Delta 400/XP2 Super), Delta 100's own Characteristic
    Curve panel has ZERO stroked vector paths in the region (confirmed via
    both page.get_drawings() and the lower-level page.get_cdrawings()) --
    just an embedded Image XObject whose placement rect matches the panel
    exactly. This is a genuinely different failure mode from the Bezier-
    flattening bug `extract_traces_in_region` had on HP5 Plus (real vector
    data, mishandled) -- here there was never any vector curve data to
    mishandle in the first place, confirmed by rendering the region at
    300dpi (crisp, not a blurry scan) and checking page.get_xobjects()
    (empty -- the image is embedded directly in the content stream, not
    hidden inside a Form XObject get_drawings() might miss).

    Locates the panel box the same way characteristic_curve_chart() does
    (title/caption/axis-label word search -- real vector text surrounds
    the raster image even though the curve itself doesn't), then traces
    the curve via raster_tracer.py's column-scan pixel tracker instead of
    digitizer_core.extract_traces_in_region. Tick calibration always goes
    through OCR (ocr_axis_calib) unconditionally here, unlike
    characteristic_curve_chart()'s vector-first-then-OCR-fallback shape --
    confirmed on Delta 100 that the tick digits are themselves baked into
    the same raster image as the curve (fit_axis's real-text search finds
    nothing), so there is no vector-text case to try first for this chart.

    Returns (points, qa_png_path): `points` in the same absolute-density
    (x=relative_log_exposure, y=density) units and list-of-tuples shape as
    characteristic_curve_chart() + digitize_chart()'s own
    `result["curves"]["density"]["points"]`, so it's a drop-in replacement
    at build_single_stock_bw_negative()'s own call site."""
    doc = fitz.open(str(pdf_path))
    page = doc[page_index]
    words_all = page.get_text("words")

    title = _find_word(words_all, r"(?i)^characteristic$")
    caption = _find_word(words_all, r"(?i)^relative$")
    density_label = _find_word(words_all, r"^Density$")
    box = (title[0] - 10, title[3], density_label[2] + 15, caption[1])
    x_tick_bbox = (box[0], box[3] - 20, box[2], box[3] + 15)
    y_tick_bbox = (box[2] - 95, box[1], box[2], box[3])
    px_slope, px_intercept = ocr_axis_calib(page, x_tick_bbox, tick_regex=x_tick_regex, axis="x")
    py_slope, py_intercept = ocr_axis_calib(page, y_tick_bbox, tick_regex=y_tick_regex, axis="y")

    ink, rect = load_ink_mask(page, image_index=0)
    img_h, img_w = ink.shape
    x_scale = (rect.x1 - rect.x0) / img_w
    y_scale = (rect.y1 - rect.y0) / img_h
    csx = px_slope * x_scale
    cix = px_slope * rect.x0 + px_intercept
    csy = py_slope * y_scale
    ciy = py_slope * rect.y0 + py_intercept

    grid_rows, grid_cols = detect_gridlines(ink, frac_threshold=gridline_frac_threshold)
    ftop, fbottom = int(grid_rows.min()), int(grid_rows.max())
    fleft, fright = int(grid_cols.min()), int(grid_cols.max())
    scan = build_scan_mask(
        ink, grid_rows, grid_cols, text_max_width=text_max_width, text_max_height=text_max_height,
        frame_bounds=(ftop, fbottom, fleft, fright), tick_stub_max_thickness=tick_stub_max_thickness,
        border_touch_tol=border_touch_tol,
    )
    scan[:ftop + 1, :] = False
    scan[fbottom:, :] = False
    scan[:, :fleft + 1] = False
    scan[:, fright:] = False

    x_range = trace_x_range if trace_x_range is not None else (fleft + 1, fright - 1)
    tr = trace_curves(scan, n_curves=1, x_range=x_range, max_y_jump=max_y_jump,
                       max_gap_columns=max_gap_columns)[0]
    if not tr:
        raise RuntimeError("raster column-scan found no curve trace -- check gridline/tick-stub filtering")

    data_x = [csx * p[0] + cix for p in tr]
    data_y = [csy * p[1] + ciy for p in tr]
    bx, by = bin_average(data_x, data_y, 60)
    by = np.array(isotonic_regression(by, increasing=(monotonic_direction == "increasing")))
    simplified = simplify_to_target(bx, by)
    sx = [round(float(x), 4) for x, y in simplified]
    sy = [round(float(y), 4) for x, y in simplified]
    n_violations = min(count_violations(sy, increasing=True), count_violations(sy, increasing=False))
    points = list(zip(sx, sy))

    qa_dir = out_root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_path = qa_dir / "characteristic_curve_qa_overlay.png"
    extent = [csx * 0 + cix, csx * img_w + cix, csy * img_h + ciy, csy * 0 + ciy]
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.imshow(np.where(ink, 1, 0), cmap="gray", extent=extent, aspect="auto")
    ax.plot(sx, sy, "o-", markersize=3, color="tab:red", label=f"density (n={len(points)})")
    ax.legend(fontsize=8, loc="best")
    ax.set_xlabel("relative_log_exposure")
    ax.set_ylabel("density_diffuse_visual")
    ax.set_title("characteristic_curve (raster_column_scan)")
    fig.savefig(qa_path, dpi=120)
    plt.close(fig)

    raw_dir = out_root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "characteristic_curve.json").write_text(json.dumps({
        "extraction_method": "raster_column_scan",
        "points": points,
        "n_raw_vertices": len(tr),
        "n_violations": n_violations,
        "qa_overlay_png": qa_path.name,
    }, indent=2))

    doc.close()
    print(f"  characteristic_curve (raster_column_scan): {len(tr)} raw points -> "
          f"{len(points)} simplified points, n_violations={n_violations}")
    return points, qa_path


def spectral_sensitivity_chart(pdf_path, page_index, x_tick_regex=r"^\d{3}$", y_tick_regex=r"^\d\.\d$"):
    """Auto-locates and builds the ChartSpec for Ilford's "Wedge spectrogram
    to tungsten light (2850K)" Spectral Sensitivity panel. Same box-from-
    labels shape as characteristic_curve_chart(); OCR fallback confirmed
    actually needed on HP5 Plus (zero real tick text on either axis, unlike
    that same film's Characteristic Curve panel, which has real text on
    both) -- check each new film independently rather than assuming one
    chart's answer predicts the other's."""
    doc = fitz.open(str(pdf_path))
    page = doc[page_index]
    words_all = page.get_text("words")

    title = _find_word(words_all, r"(?i)^spectral$")
    caption = _find_word(words_all, r"(?i)^wavelength$")
    sensitivity_label = _find_word(words_all, r"(?i)^sensitivity$", rotated_only=True)
    box = (title[0] - 10, title[3], sensitivity_label[2] + 15, caption[1])
    tick_box = (box[0], box[1], box[2], box[3] + 15)

    x_axis_calib_override = y_axis_calib_override = None
    try:
        fit_axis(words_all, x_tick_regex, "x", bbox=tick_box)
        fit_axis(words_all, y_tick_regex, "y", bbox=tick_box)
    except RuntimeError:
        x_tick_bbox = (box[0], box[3] - 20, box[2], box[3] + 15)
        # Right edge pulled in a few points from box[2] (box[2] - 4, not
        # box[2] -- widened left edge to box[2] - 49 to compensate) --
        # confirmed needed on Delta 400 (2026-08-04): with the right edge
        # sitting exactly at box[2], tesseract's --psm 11 layout analysis
        # non-monotonically mangled the "0.5" tick (read as bare "0", or
        # "0." with the "5" dropped, depending on OCR zoom) even though the
        # glyph itself renders cleanly and clipping doesn't visibly change
        # -- empirically a boundary-pixel/anti-aliasing sensitivity in
        # tesseract's own segmentation, not a real ambiguity in the source
        # (many other right-edge offsets tried, all >=3pt in from box[2]
        # read both ticks cleanly; box[2] itself and one narrower attempt
        # anchored off the rotated "Sensitivity" label's own x0 both
        # failed). HP5 Plus's OCR happened to read both ticks correctly at
        # the original box[2]-45..box[2] crop regardless, so this wasn't
        # caught there -- re-verified unaffected by this change.
        y_tick_bbox = (box[2] - 49, box[1], box[2] - 4, box[3])
        # whitelist=None: the default digit-only whitelist merges this
        # row's tightly-spaced 3-digit wavelength ticks into one token on
        # HP5 Plus -- see ocr_helpers.py's own docstring.
        x_axis_calib_override = ocr_axis_calib(page, x_tick_bbox, tick_regex=r"\d{3}", axis="x", whitelist=None)
        y_axis_calib_override = ocr_axis_calib(page, y_tick_bbox, tick_regex=r"\d\.\d", axis="y")
    doc.close()

    anchor_xy = (box[2] - 15, box[1] + 15)
    return ChartSpec(
        pdf=str(pdf_path), page_index=page_index, chart_id="spectral_sensitivity",
        x_tick_regex=x_tick_regex, y_tick_regex=y_tick_regex,
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec("sensitivity", label_position_override=anchor_xy)],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, axis_word_bbox=tick_box,
        x_axis_calib_override=x_axis_calib_override, y_axis_calib_override=y_axis_calib_override,
        monotonic_direction=None, min_trace_points=8,
    )


def build_single_stock_bw_negative(
    *, pdf_path, char_page_index, spectral_page_index,
    stock, name, target_print, dev_time_min, datasource, out_root,
    log_sensitivity_density_over_min=1.0, n_layers=3,
    char_x_tick_regex=r"^[1234]$", char_y_tick_regex=r"^[123]\.0$",
    char_extraction="vector", char_raster_kwargs=None,
):
    """Digitizes both charts for one Ilford single-curve B&W negative film
    and writes its one darktable stock. `log_sensitivity_density_over_min`
    defaults to 1.0 (this tool's existing convention on every product so
    far, e.g. Kodak Tri-X's own explicitly-labeled "1.0 + Dmin" chart) --
    Ilford's wedge-spectrogram method doesn't publish an explicit density-
    above-base criterion the way Kodak's charts do, so this is a documented
    assumption, not a real datasheet value, for every product built through
    this function. It doesn't materially affect calibration: exposure_
    calibration.py's own grey-target correction re-anchors the overall
    absolute exposure scale regardless of which criterion the source used
    (same reasoning CLAUDE.md already documents for the exposure axis not
    being cross-calibrated between a stock's two source charts).

    `char_extraction`: "vector" (default, characteristic_curve_chart() +
    digitize_chart()'s normal vector-path extraction) or "raster"
    (characteristic_curve_points_raster(), for a film whose Characteristic
    Curve panel is an embedded raster image with zero vector paths to
    extract -- confirmed needed on Ilford Delta 100 Professional, 2026-08-03,
    see that function's own docstring; every other film on this template so
    far uses "vector"). `char_raster_kwargs`: optional dict of extra kwargs
    forwarded to characteristic_curve_points_raster() (e.g. trace_x_range),
    only consulted when char_extraction="raster"."""
    out_root.mkdir(parents=True, exist_ok=True)

    if char_extraction == "vector":
        char_chart = characteristic_curve_chart(pdf_path, char_page_index, char_x_tick_regex, char_y_tick_regex)
        char_result = digitize_chart(char_chart, pdf_path)
        stock_io.write_raw_and_qa(pdf_path, char_chart, char_result, out_root)
        # The RDP-simplified `points` (same convention Tri-X's own products fit
        # against) -- NOT points_dense. An earlier version of this function fit
        # against points_dense instead, working around a real bug that's now
        # fixed at its actual source: digitizer_core.py's extract_traces_in_region
        # was treating Bezier curve control points as literal digitized samples
        # (HP5 Plus's Characteristic Curve is drawn as just 3 long Bezier
        # segments, unlike Kodak's finely-segmented polylines), which silently
        # cut a corner through the toe and left only 11 badly-placed simplified
        # points. Now that extraction properly evaluates the Bezier curve
        # (_flatten_path_item), the simplified set is 22 well-distributed points
        # and fits just as well as the dense set (R^2 0.99997 vs 0.99999,
        # confirmed side by side) -- so there's no more reason to diverge from
        # Tri-X's own convention here.
        points = char_result["curves"]["density"]["points"]
    elif char_extraction == "raster":
        points, _qa_path = characteristic_curve_points_raster(
            pdf_path, char_page_index, out_root, **(char_raster_kwargs or {}),
        )
    else:
        raise ValueError(f"char_extraction must be 'vector' or 'raster', got {char_extraction!r}")

    spec_chart = spectral_sensitivity_chart(pdf_path, spectral_page_index)
    spec_result = digitize_chart(spec_chart, pdf_path)
    stock_io.write_raw_and_qa(pdf_path, spec_chart, spec_result, out_root)
    sens_points = spec_result["curves"]["sensitivity"]["points"]
    sens_x = np.array([p[0] for p in sens_points])
    sens_y = np.array([p[1] for p in sens_points])
    order = np.argsort(sens_x)
    sens_x, sens_y = sens_x[order], sens_y[order]
    log_sensitivity = np.interp(grids.WAVELENGTHS_NM, sens_x, sens_y)
    out_of_range = (grids.WAVELENGTHS_NM < sens_x.min()) | (grids.WAVELENGTHS_NM > sens_x.max())
    log_sensitivity[out_of_range] = np.nan
    log_sensitivity, sens_shift, grey_before = ec.calibrate_negative_film_log_sensitivity(
        log_sensitivity, grids.WAVELENGTHS_NM,
    )
    print(f"  log_sensitivity calibration: grey landed at log_raw={grey_before:.3f} before, "
          f"shifted by {sens_shift:+.3f} log10 ({sens_shift / np.log10(2):+.2f} stops) "
          f"to reach target {ec.GREY_TARGET_LOG_RAW}")

    xs_absolute = np.array([p[0] for p in points])
    ys_absolute = np.array([p[1] for p in points])
    base_density = float(ys_absolute.min())
    x_speed = stock_io.speed_point_x(points, base_density, criterion=log_sensitivity_density_over_min)
    xs = xs_absolute - x_speed
    ys_net = ys_absolute - base_density

    fit = dm.fit_norm_cdfs(xs, ys_net, n_layers=n_layers)
    print(f"  {stock}: R^2={fit.r_squared:.5f} max_residual={fit.max_residual:.4f}")
    qa_dir = out_root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    dm.plot_fit_qa(xs, ys_net, fit, grids.LOG_EXPOSURE,
                   title=f"{name} (net density, above base)",
                   out_path=qa_dir / "density_fit.png")

    return stock_io.write_single_dev_time_stock(
        out_root=out_root, stock=stock, name=name, target_print=target_print,
        densitometer="diffuse_visual",
        log_sensitivity_density_over_min=log_sensitivity_density_over_min,
        reference_illuminant="D55", viewing_illuminant="D50",
        datasource=datasource, wavelengths=grids.WAVELENGTHS_NM,
        log_sensitivity=log_sensitivity, log_exposure=grids.LOG_EXPOSURE,
        base_density_scalar=base_density, fit=fit, dev_time_min=dev_time_min,
    )
