"""
Kodak Tri-X Pan Film (TX), ISO 400/27 deg -- the still-photography camera
negative available in 120/135/70mm (NOT the "Professional" TXP/TXT, separate
ISO 320 products with their own datasheet panels -- see
products/kodak_trix400txp.py and products/kodak_trix400txt.py).

Source: papers/125pixcom/film/kodak/f9-Tri-X_Pan-199906.pdf (Kodak F-9, June
1999). Ships every real, independently-digitized development time from BOTH
of TX's own Characteristic-Curve panels as its own separate darktable stock
(see trix_common.py's own module docstring for why -- no development-time
slider, no collapse of a real family down to one representative value):

- page 8 (index 7) left panel: D-76, Large tank, 68F(20C), 7/9/11 min
  (this is the same D-76 bracket the original single-stock kodak_trix400.py
  used, restructured here into 3 separate stocks instead of 1 collapsed one)
- page 8 (index 7) right panel: KODAK T-MAX Developer, Small tank, 75F(24C),
  5/7/9/11 min

Both panels' curves are close together near their shared toe -- the 9min/
11min D-76 traces and, worse, ALL FOUR T-MAX traces turned out to be drawn
as continuous multi-curve PDF path objects (no pen lift between them),
confirmed by direct probing (extract_traces_in_region() at min_points=50
found only 3 traces for T-MAX's 4 real curves, one with ~2x the expected
point count) -- fixed via digitizer_core.py's split_on_x_reversal, which
splits a merged trace wherever its own x-direction sustains a reversal
(exactly what happens where the pen continues from one curve's end straight
into the next curve's start). Every resulting curve-to-label assignment was
re-verified against the rendered QA overlay directly against the source
page image before being trusted -- see kodak_trix400tx_qa_notes below.

Exposure-axis calibration note (same real, documented limitation as the
original kodak_trix400.py -- the Characteristic Curve chart and the
Spectral-Sensitivity chart use two different classical sensitometric
exposure conventions this one 1999 datasheet doesn't cross-calibrate): each
panel (D-76, T-MAX) is anchored independently, using its OWN representative
(middle) curve's own "density = base + log_sensitivity_density_over_min"
crossing at canonical logE=0 -- D-76's anchor is not reused for T-MAX, since
they are two genuinely different real charts/processes, not two points on
one curve family. log_sensitivity (one real Spectral-Sensitivity curve,
shared by both developer brackets since it's a property of the film itself,
not the developer) is digitized once and cross-calibrated once via
exposure_calibration.py, reused by every TX stock in this file regardless
of developer.

Contrast Index: every stock's own real, Kodak-published Contrast Index is
read directly off that panel's own Contrast-Index-vs-development-time curve
(also digitized here, per developer) -- not approximated from the H&D curve
itself. A "(normal)" tag is attached only when a stock's real CI lands
within 0.01 of Kodak's stated 0.56 "starting-point recommendation" target
(confirmed independently against Kodak's own separate Manual Processing
recommended-time table: D-76 9min/68F IS Kodak's own real "normal" time for
this exact developer/tank/temp). Kodak's push-processing section (page 6)
publishes a real CI 0.72 target for a 2-stop push, but only for specific
times (13 min for D-76 large tank at 68F) that are NOT among the three
times actually plotted on the Characteristic-Curve chart (7/9/11 min) --
none of our three real D-76 curves lands close enough to CI 0.72 to
honestly claim a push-stop label, so none of them get one. Don't invent a
stops-of-push number for a curve that doesn't match a real Kodak anchor.
"""

from pathlib import Path

import numpy as np

import canonical_grids as grids
import exposure_calibration as ec
import trix_common as tc
from digitizer_core import ChartSpec, CurveSpec, digitize_chart
from kodak_helpers import overline_negative_calib, overline_symmetric_calib

import fitz

PDF_PATH = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom/film/kodak/f9-Tri-X_Pan-199906.pdf")
HERE = Path(__file__).parent.parent
OUT_ROOT = HERE / "outputs" / "film" / "bw" / "negative" / "kodak" / "kodak_trix400" / "tx"

FILM_NAME_PREFIX = "Tri-X 400 (TX)"
TARGET_PRINT = "kodak_polymax_fine_art_grade2"
N_LAYERS = 3

D76_DEV_TIMES = [7.0, 9.0, 11.0]
D76_REP_IDX = 1  # 9 min
TMAX_DEV_TIMES = [5.0, 7.0, 9.0, 11.0]
TMAX_REP_IDX = 1  # 7 min -- middle-ish of a 4-point bracket, same convention as odd-length brackets

DATASOURCE = (
    "Kodak F-9 'KODAK TRI-X Pan and KODAK TRI-X Pan Professional Films' datasheet, "
    "June 1999 (papers/125pixcom/film/kodak/f9-Tri-X_Pan-199906.pdf), page 8 "
    "'Characteristic Curves' (D-76 Large tank 68F/20C 7/9/11min; KODAK T-MAX Developer "
    "Small tank 75F/24C 5/7/9/11min) and page 9 'Spectral-Sensitivity Curve' "
    "('1.0 + D-min' trace). Digitized independently via this project's own tooling."
)


def _d76_chart():
    region = (31, 40, 290, 285)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=7, chart_id="characteristic_curve_d76",
        x_tick_regex=r"\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_relative", y_label="density_diffuse_visual",
        curves=[
            CurveSpec("7min", label_regex=r"^7$", qa_source="points_dense"),
            CurveSpec("9min", label_regex=r"^9$", qa_source="points_dense"),
            CurveSpec("11min", label_regex=r"^11$", qa_source="points_dense"),
        ],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction="increasing", min_trace_points=50,
        metadata={"developer": "D-76", "process": "Large tank, 68F (20C)",
                  "densitometry": "Diffuse visual", "exposure": "Daylight, 1/50 second"},
    )
    chart.x_axis_calib_override = overline_negative_calib(PDF_PATH, 7, region, tick_regex=r"\d\.0")
    return chart


def _d76_ci_chart():
    region = (40, 305, 270, 530)
    return ChartSpec(
        pdf=str(PDF_PATH), page_index=7, chart_id="ci_vs_time_d76",
        x_tick_regex=r"^\d+$", y_tick_regex=r"\d\.\d",
        x_label="development_time_min", y_label="contrast_index",
        curves=[CurveSpec("D-76", label_position_override=(166, 413), qa_source="points_dense")],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction="increasing", min_trace_points=20,
        metadata={"developer": "D-76", "process": "Large tank, 68F (20C)"},
    )


def _tmax_chart():
    region = (323, 40, 589, 285)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=7, chart_id="characteristic_curve_tmax_smalltank",
        x_tick_regex=r"\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_relative", y_label="density_diffuse_visual",
        curves=[
            CurveSpec("5min", label_regex=r"^5$", qa_source="points_dense"),
            CurveSpec("7min", label_regex=r"^7$", qa_source="points_dense"),
            CurveSpec("9min", label_regex=r"^9$", qa_source="points_dense"),
            CurveSpec("11min", label_regex=r"^11$", qa_source="points_dense"),
        ],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction="increasing", min_trace_points=50,
        # Kodak drew the 9min/11min traces as one continuous PDF path object
        # (confirmed via extract_traces_in_region() probe: 3 traces found for
        # 4 real curves, one with ~2x the point count of the others) --
        # split_on_x_reversal cuts it where the pen direction reverses,
        # exactly where the merged trace hands off from one curve to the next.
        split_on_x_reversal=True, reversal_run_length=5,
        # 7min separately loses its last ~5 points (right at the shoulder,
        # next to the chart's own right border) as a separate tiny drawing
        # object -- same real pen-lift artifact as kodak_trix400txt.py's
        # HC-110 panel (see digitizer_core.py's extract_traces_in_region
        # docstring, merge_strategy="chain_slope"), confirmed the same way:
        # points_dense stopped at log_exposure -0.11 instead of the panel's
        # real ~0.0 edge like the other 3 curves. chain_slope reattaches it
        # by local trajectory match instead of raw endpoint distance.
        cross_object_merge=True, merge_strategy="chain_slope",
        metadata={"developer": "T-MAX", "process": "Small tank, 75F (24C)",
                  "densitometry": "Diffuse visual", "exposure": "Daylight, 1/50 second"},
    )
    chart.x_axis_calib_override = overline_negative_calib(PDF_PATH, 7, region, tick_regex=r"\d\.0")
    return chart


def _tmax_ci_chart():
    region = (320, 305, 545, 530)
    return ChartSpec(
        pdf=str(PDF_PATH), page_index=7, chart_id="ci_vs_time_tmax_smalltank",
        x_tick_regex=r"^\d+$", y_tick_regex=r"\d\.\d",
        x_label="development_time_min", y_label="contrast_index",
        curves=[CurveSpec("T-MAX", label_position_override=(470, 400), qa_source="points_dense")],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction="increasing", min_trace_points=20,
        metadata={"developer": "T-MAX", "process": "Small tank, 75F (24C)"},
    )


def _spectral_sensitivity_chart():
    region = (272, 40, 604, 290)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=8, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec("1.0+Dmin", label_position_override=(471.5, 164.5), qa_source="points_dense")],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction=None, min_trace_points=10,
        metadata={"developer": "D-76", "process": "68F (20C)",
                  "densitometry": "Diffuse visual", "effective_exposure": "1.4 seconds",
                  "density_over_min": 1.0},
    )
    chart.y_axis_calib_override = overline_symmetric_calib(PDF_PATH, 8, region, tick_regex=r"\d\.0")
    return chart


def _fit_bracket(curves_by_dev, dev_times, rep_idx, label):
    """Anchors + fits one Characteristic-Curve bracket (a set of curves from
    ONE panel/developer) -- one scipy.optimize.curve_fit call per
    development time, in its own OS process (tc.fit_dev_times_parallel(),
    see its own docstring for why processes not threads). Returns
    {dev_t: (fit, base_density)} plus the applied shift."""
    rep_dev = dev_times[rep_idx]
    rep_points = curves_by_dev[rep_dev]
    rep_base = min(y for _, y in rep_points)
    x_speed_rep = tc.speed_point_x(rep_points, rep_base, criterion=1.0)
    shift = -x_speed_rep

    fits = tc.fit_dev_times_parallel(
        curves_by_dev, dev_times, shift, N_LAYERS, label,
    )
    return fits, shift, rep_dev


def _build_d76_bracket(log_sensitivity):
    """D-76 large tank bracket -- kept as its own function (alongside
    _build_tmax_bracket below) purely for readability; build_all() calls
    both sequentially. Fanning these out concurrently was tried and
    measured WORSE for overall wall-clock (see trix_common.py's
    FIT_SEMAPHORE comment for the full history) -- the two brackets ARE
    fully independent (no shared mutable state beyond the read-only
    log_sensitivity array) but the fix for the actual measured bottleneck
    lives in fit_dev_times_parallel's own global semaphore now, not here."""
    d76_chart = _d76_chart()
    d76_result = digitize_chart(d76_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, d76_chart, d76_result, OUT_ROOT / "large_tank_d76")
    # points_dense throughout this file, not points -- see SIMPLIFY_TOLERANCE's
    # comment in digitizer_core.py: fitting/interpolation should draw from the
    # fullest-fidelity real data available, not the RDP-reduced QA/compactness set.
    d76_curves = {float(t.replace("min", "")): d76_result["curves"][t]["points_dense"]
                  for t in ("7min", "9min", "11min")}
    d76_fits, d76_shift, d76_rep = _fit_bracket(d76_curves, D76_DEV_TIMES, D76_REP_IDX, "D-76")

    d76_ci_chart = _d76_ci_chart()
    d76_ci_result = digitize_chart(d76_ci_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, d76_ci_chart, d76_ci_result, OUT_ROOT / "large_tank_d76")
    d76_ci_points = d76_ci_result["curves"]["D-76"]["points_dense"]

    written = {}
    for dev_t in D76_DEV_TIMES:
        fit, base_density = d76_fits[dev_t]
        real_ci = tc.real_ci_at(d76_ci_points, dev_t)
        stock = f"kodak_trix400tx_d76_{tc.fmt_time_slug(dev_t)}"
        name = f"{FILM_NAME_PREFIX} — D-76 {tc.fmt_time(dev_t)}, {tc.ci_label(real_ci)}"
        source_profile, pack_profile, out_dir = tc.write_single_dev_time_stock(
            out_root=OUT_ROOT / "large_tank_d76", stock=stock, name=name,
            target_print=TARGET_PRINT, densitometer="diffuse_visual",
            log_sensitivity_density_over_min=1.0, reference_illuminant="D55",
            viewing_illuminant="D50", datasource=DATASOURCE,
            wavelengths=grids.WAVELENGTHS_NM, log_sensitivity=log_sensitivity,
            log_exposure=grids.LOG_EXPOSURE, base_density_scalar=base_density,
            fit=fit, dev_time_min=dev_t,
        )
        print(f"  wrote {stock}: {name}  -> {out_dir}")
        written[stock] = (source_profile, pack_profile)
    return written


def _build_tmax_bracket(log_sensitivity):
    """T-MAX small tank bracket -- see _build_d76_bracket's own docstring."""
    tmax_chart = _tmax_chart()
    tmax_result = digitize_chart(tmax_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, tmax_chart, tmax_result, OUT_ROOT / "small_tank_tmax")
    tmax_curves = {float(t.replace("min", "")): tmax_result["curves"][t]["points_dense"]
                   for t in ("5min", "7min", "9min", "11min")}
    tmax_fits, tmax_shift, tmax_rep = _fit_bracket(tmax_curves, TMAX_DEV_TIMES, TMAX_REP_IDX, "T-MAX")

    tmax_ci_chart = _tmax_ci_chart()
    tmax_ci_result = digitize_chart(tmax_ci_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, tmax_ci_chart, tmax_ci_result, OUT_ROOT / "small_tank_tmax")
    tmax_ci_points = tmax_ci_result["curves"]["T-MAX"]["points_dense"]

    written = {}
    for dev_t in TMAX_DEV_TIMES:
        fit, base_density = tmax_fits[dev_t]
        real_ci = tc.real_ci_at(tmax_ci_points, dev_t)
        stock = f"kodak_trix400tx_tmax_{tc.fmt_time_slug(dev_t)}"
        name = f"{FILM_NAME_PREFIX} small tank — T-MAX {tc.fmt_time(dev_t)}, {tc.ci_label(real_ci)}"
        source_profile, pack_profile, out_dir = tc.write_single_dev_time_stock(
            out_root=OUT_ROOT / "small_tank_tmax", stock=stock, name=name,
            target_print=TARGET_PRINT, densitometer="diffuse_visual",
            log_sensitivity_density_over_min=1.0, reference_illuminant="D55",
            viewing_illuminant="D50", datasource=DATASOURCE,
            wavelengths=grids.WAVELENGTHS_NM, log_sensitivity=log_sensitivity,
            log_exposure=grids.LOG_EXPOSURE, base_density_scalar=base_density,
            fit=fit, dev_time_min=dev_t,
        )
        print(f"  wrote {stock}: {name}  -> {out_dir}")
        written[stock] = (source_profile, pack_profile)
    return written


_BRACKET_BUILDERS = [_build_d76_bracket, _build_tmax_bracket]


def build_all():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    # --- Spectral sensitivity (shared by both developer brackets) -----------
    spec_chart = _spectral_sensitivity_chart()
    spec_result = digitize_chart(spec_chart, PDF_PATH)
    # points_dense (400pt bin-averaged), not points (RDP-simplified) -- this
    # curve gets linearly resampled straight onto the 5nm output grid below,
    # so it needs the dense curve's much finer spacing to avoid chord-cutting
    # through real peaks/troughs; the RDP-reduced set is for QA/compactness,
    # not for being the actual resampling source. See digitizer_core.py's
    # SIMPLIFY_TOLERANCE comment.
    sens_points = spec_result["curves"]["1.0+Dmin"]["points_dense"]
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
          f"shifted by {sens_shift:+.3f} log10 ({sens_shift/np.log10(2):+.2f} stops) "
          f"to reach target {ec.GREY_TARGET_LOG_RAW}")

    written = {}
    for builder in _BRACKET_BUILDERS:
        written.update(builder(log_sensitivity))
    return written


def _make_entry(stock, out_dir):
    import types
    return types.SimpleNamespace(build=lambda: _build_one(stock), OUT_DIR=out_dir)


_BUILT_CACHE = {}


def _build_one(stock):
    """main.py's PRODUCTS interface calls .build() per stock slug, but all
    7 TX stocks come out of one shared digitize+fit pass (same charts).
    Runs the shared pass once (cached) and returns just the one profile pair
    the caller asked for."""
    if not _BUILT_CACHE:
        _BUILT_CACHE.update(build_all())
    return _BUILT_CACHE[stock]


def _out_dir_for(stock):
    if "_d76_" in stock:
        return OUT_ROOT / "large_tank_d76" / stock
    return OUT_ROOT / "small_tank_tmax" / stock


_STOCK_SLUGS = (
    [f"kodak_trix400tx_d76_{tc.fmt_time_slug(t)}" for t in D76_DEV_TIMES]
    + [f"kodak_trix400tx_tmax_{tc.fmt_time_slug(t)}" for t in TMAX_DEV_TIMES]
)

PRODUCTS = {slug: _make_entry(slug, _out_dir_for(slug)) for slug in _STOCK_SLUGS}


if __name__ == "__main__":
    build_all()
