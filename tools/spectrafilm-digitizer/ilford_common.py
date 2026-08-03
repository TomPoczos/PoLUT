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

import re

import numpy as np

import fitz

import canonical_grids as grids
import density_model as dm
import exposure_calibration as ec
import stock_io
from digitizer_core import ChartSpec, CurveSpec, digitize_chart, fit_axis
from ocr_helpers import ocr_axis_calib


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
        y_tick_bbox = (box[2] - 45, box[1], box[2], box[3])
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
    being cross-calibrated between a stock's two source charts)."""
    out_root.mkdir(parents=True, exist_ok=True)

    char_chart = characteristic_curve_chart(pdf_path, char_page_index, char_x_tick_regex, char_y_tick_regex)
    char_result = digitize_chart(char_chart, pdf_path)
    stock_io.write_raw_and_qa(pdf_path, char_chart, char_result, out_root)
    # points_dense (400 points), not the RDP-simplified `points` (11 for HP5
    # Plus) -- confirmed on HP5 Plus that fitting against the simplified set
    # left a wide (~0.4 log_exposure) gap between two consecutive kept
    # vertices in the toe-to-straight-line transition with nothing
    # constraining the model's shape in between; fit_norm_cdfs happily hit
    # both endpoints exactly (R^2=1.00000) via an unphysical near-step
    # jump instead of the real smooth rise `points_dense` shows is actually
    # there (confirmed by plotting both fits side by side). RDP
    # simplification is a fine lossy representation for QA/plotting, where
    # a human eye fills in the smooth curve between sparse vertices, but
    # not a safe input for an under-constrained multi-parameter model fit
    # with only ~11 points spread over a 4-decade exposure range. Tri-X's
    # own products fit against the simplified set too and haven't shown
    # this failure mode -- but only because their curves simplify to far
    # more points (20-30) spread more evenly across the range, not because
    # the underlying risk doesn't apply there; using the dense set here is
    # strictly more correct and has no real downside (same real digitized
    # curve, just resampled finer off the same vector path).
    points = char_result["curves"]["density"]["points_dense"]

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
