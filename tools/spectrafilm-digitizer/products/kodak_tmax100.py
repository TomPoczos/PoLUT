"""
Kodak Professional T-MAX 100 Film (100TMX) -- medium-speed panchromatic
black-and-white camera negative.

Source: papers/125pixcom/film/kodak/f4016_tmax_100-2018.pdf (Kodak F-4016,
Revised 6-18 -- the earliest available edition that still carries a real,
vector-drawn Characteristic Curves panel; the 2016 edition of this same
publication number dropped that panel from its own "IMAGE STRUCTURE" page
entirely, confirmed by text search before this file was chosen). Page index
7 ("IMAGE STRUCTURE" / "Characteristic Curves") carries both the Spectral
Sensitivity Curves chart AND all three real Characteristic-Curve panels on
one page (a different layout from Tri-X's own F-9 sheet, which spreads
D-76/T-MAX across two side-by-side panels on one page and puts Spectral
Sensitivity on the next page -- confirmed directly by probing this page's
own word/tick geometry rather than assumed from that precedent). Ships
every real, independently-digitized development time from all three
brackets as its own separate darktable stock (same rationale as
kodak_trix400tx.py / trix_common.py's own module docstring -- no
development-time slider):

- D-76, Small Tank, 20C (68F): 6 / 7.5 / 10 min
- KODAK PROFESSIONAL T-MAX RS Developer and Replenisher, Large Tank,
  20C (68F): 8 / 10.5 / 13 / 15 min
- KODAK PROFESSIONAL T-MAX Developer, Small Tank, 20C (68F): 6 / 7 / 10 / 12
  min

All three panels' curve counts matched their real curve counts exactly on
direct probe (extract_traces_in_region(), min_points=12: 3/4/4 traces for
3/4/4 real curves) -- unlike Tri-X's own T-MAX panel on the F-9 sheet, none
of these three needed split_on_x_reversal; each curve is already its own
PDF path object here. Every curve has a real, clean inline "<N> min" label
(digit and unit as separate text words -- label_regex matches just the
digit word, same convention as kodak_trix400tx.py's D-76/T-MAX panels) with
no cross-panel collisions (each bracket's own digit set is unique within
its own region_bbox). Every resulting curve-to-label assignment was
re-verified against the rendered QA overlay against the source page image
before being trusted, per this project's own standing lesson (see this
project's own CLAUDE.md "hardest one" case) that a clean R^2 fit is not
proof of a correct assignment.

Exposure-axis calibration note (same real, documented limitation as
kodak_trix400tx.py): the Characteristic Curve panels and the Spectral-
Sensitivity chart use two different classical sensitometric exposure
conventions this one datasheet doesn't cross-calibrate. Each bracket (D-76,
T-MAX RS, T-MAX) is anchored independently, using its OWN representative
(middle) curve's own "density = base + log_sensitivity_density_over_min"
crossing at canonical logE=0 -- none reuses another bracket's anchor, since
they are three genuinely different real charts/processes, not points on one
curve family. log_sensitivity (the "1.0 greater than D-min" Spectral-
Sensitivity trace, D-76/68F) is digitized once and cross-calibrated once via
exposure_calibration.py, shared by every stock in this file regardless of
developer -- same convention as Tri-X's "1.0+Dmin" trace
(log_sensitivity_density_over_min=1.0).

Contrast Index (page index 8, "Contrast Index Curves"): initially scoped
OUT of this file (see git history) because the position-based matching this
project's other CI panels use (rank-by-x / label-proximity, the same
machinery kodak_trix400tx.py's own CI charts use) can't reliably tell apart
this sheet's Small Tank panel -- SEVEN developers' CI curves (D-76,
D-76 1:1, T-MAX, T-MAX RS, XTOL, XTOL 1:1, HC-110(B)) converging and
crossing repeatedly right through the CI range our real stocks occupy, the
same tangled shape that produced a confidently-wrong, still-clean-R^2 label
assignment on kodak_polymax_fine_art.py's own filterset panels (see this
project's CLAUDE.md). That reasoning was right about *position*-based
matching, but incomplete: every curve on this page is real vector ink
carrying its own dash pattern (and, where two curves share a dash pattern,
its own stroke width) exactly matching its legend entry's own line sample
-- confirmed by directly probing `page.get_drawings()` for each legend
swatch's own stroke object (found immediately to the left of its label
text) and reading its `dashes`/`width` fields, rather than eyeballing the
rendered line style. That is real, distinguishing data position-based
matching can't see, so Strategy B (`vector_stroke_dash`, `dash_regex`+
`width`/`width_tol` on each `CurveSpec`) resolves it unambiguously even
through the crossing region -- no ranking, no proximity guess. Two real
wrinkles, both confirmed programmatically before trusting the result, not
assumed:
- D-76 and XTOL 1:1 (Small Tank panel) share the exact same dash array
  (`[6.4777 3.2388]`) -- Kodak's own chart distinguishes them by stroke
  width alone (0.72 vs 1.08), confirmed by reading both curves' and both
  legend swatches' own `width` field directly, not by eye.
- T-MAX (Small Tank, solid) and T-MAX RS (Small Tank, fine-dashed) run
  almost coincident for their whole length, close enough that at a glance
  they look like one line with a stray dash artifact -- dash pattern still
  cleanly separates them (`dash=[]` vs `dash=[3.2388 1.6194]`).
Every extracted curve's data-space endpoints were cross-checked against
the visually-identified target curve (independently marked on the rendered
page) before being trusted -- see `_ci_smalltank_chart()`/
`_ci_largetank_chart()`'s own comments for the exact dash/width values and
the endpoint cross-check. Only the 3 curves this file's brackets actually
need are digitized (D-76 + T-MAX from the Small Tank panel, T-MAX RS from
the Large Tank panel) -- the other 4 real curves on these two panels
(D-76 1:1, XTOL, XTOL 1:1, HC-110(B)) are out of scope, not attempted.
"""

from pathlib import Path

import numpy as np

import canonical_grids as grids
import exposure_calibration as ec
import trix_common as tc
from digitizer_core import ChartSpec, CurveSpec, digitize_chart
from kodak_helpers import overline_negative_calib, overline_symmetric_calib

import fitz

PDF_PATH = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom/film/kodak/f4016_tmax_100-2018.pdf")
HERE = Path(__file__).parent.parent
OUT_ROOT = HERE / "outputs" / "film" / "bw" / "negative" / "kodak" / "kodak_tmax100"

FILM_NAME_PREFIX = "T-Max 100"
TARGET_PRINT = "kodak_polymax_fine_art_grade2"
N_LAYERS = 3

D76_DEV_TIMES = [6.0, 7.5, 10.0]
D76_REP_IDX = 1  # 7.5 min
TMAXRS_DEV_TIMES = [8.0, 10.5, 13.0, 15.0]
TMAXRS_REP_IDX = 1  # 10.5 min -- middle-ish of a 4-point bracket, same convention as TX's T-MAX bracket
TMAX_DEV_TIMES = [6.0, 7.0, 10.0, 12.0]
TMAX_REP_IDX = 1  # 7 min

DATASOURCE = (
    "Kodak F-4016 'KODAK PROFESSIONAL T-MAX 100 Film' datasheet, Revised 6-18 "
    "(papers/125pixcom/film/kodak/f4016_tmax_100-2018.pdf), page 8 (index 7) "
    "'Characteristic Curves' (D-76 Small Tank 20C/68F 6/7.5/10min; KODAK "
    "PROFESSIONAL T-MAX RS Developer and Replenisher Large Tank 20C/68F "
    "8/10.5/13/15min; KODAK PROFESSIONAL T-MAX Developer Small Tank 20C/68F "
    "6/7/10/12min) and 'Spectral Sensitivity Curves' ('1.0 greater than "
    "D-min' trace, D-76 68F/20C), and page 9 (index 8) 'Contrast Index "
    "Curves' (D-76 and T-MAX traces, Small Tank panel; T-MAX RS trace, "
    "Large Tank panel). Digitized independently via this project's "
    "own tooling."
)

# Contrast Index Curves (page index 8) -- see module docstring for why this
# is now digitized via dash/width matching (Strategy B, vector_stroke_dash)
# rather than the position-based matching (rank-by-x/label-proximity) that
# can't tell apart this page's converging, mutually-crossing curves. Every
# dash array/width below was read directly off each curve's OWN legend
# swatch stroke object (not guessed from the rendered line style) by
# probing page.get_drawings() for the stroke immediately left of each
# legend label's text -- see the two chart-builder functions below for the
# per-curve values and their independent endpoint cross-checks.
_CI_STROKE_RGB = (0.13723964989185333, 0.12156862765550613, 0.1254749298095703)
_CI_DASH_SOLID = r"^\[\] "
# D-76 (Small Tank) and T-MAX RS (Large Tank) share this exact real dash
# array; Small Tank's XTOL 1:1 curve ALSO uses it (confirmed via its own
# legend swatch) but at stroke width 1.08 instead of 0.72 -- width=0.72 +
# width_tol below is what actually disambiguates D-76 from XTOL 1:1 within
# the Small Tank panel, not the dash pattern alone.
_CI_DASH_MEDIUM = r"^\[ 6\.4777 3\.2388 \] "


def _ci_smalltank_chart():
    """Small Tank panel (page index 8, top-left): 7 real developers' CI
    curves overlaid and mutually crossing (D-76, D-76 1:1, T-MAX, T-MAX RS,
    XTOL, XTOL 1:1, HC-110 (B)) -- only D-76 and T-MAX are digitized here,
    the two this file's own brackets need. Region/legend bboxes probed
    directly from this chart's own axis-tick/legend-label word positions
    (page.get_text("words")), not estimated from the rendered image.

    D-76: dash=[6.4777 3.2388], width=0.72 (thin) -- disambiguated from
    XTOL 1:1's identical dash array at width=1.08 by width alone (see
    _CI_DASH_MEDIUM's own comment). Endpoint cross-check: extracted trace
    spans ~6.5-9.3 min / CI 0.56-0.82, matching the visually-identified
    curve's own real ~6.3-9.0 min span (a small overshoot at each end is
    expected -- the trace's own bounding box vs. where the dash pattern
    visibly starts/ends).

    T-MAX: dash=[] (solid), width=0.72 (thin) -- disambiguated from D-76
    (1:1)'s solid curve at width=1.08 by width. T-MAX's own curve runs
    almost coincident with T-MAX RS's (dashed) full length on this panel
    (confirmed independently, not assumed) -- dash pattern still separates
    them cleanly even where visually near-identical. Endpoint cross-check:
    ~7.9-14.7 min / CI 0.56-0.82, matching the visually-identified curve's
    own real ~7.7-14.5 min span.
    """
    region = (40, 70, 270, 300)
    legend = (181, 192, 257, 264)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=8, chart_id="ci_vs_time_smalltank",
        x_tick_regex=r"^\d+$", y_tick_regex=r"\d\.\d",
        x_label="development_time_min", y_label="contrast_index",
        curves=[
            CurveSpec("D-76", stroke_rgb=_CI_STROKE_RGB, tol=0.02,
                      dash_regex=_CI_DASH_MEDIUM, width=0.72, width_tol=0.1),
            CurveSpec("T-MAX", stroke_rgb=_CI_STROKE_RGB, tol=0.02,
                      dash_regex=_CI_DASH_SOLID, width=0.72, width_tol=0.1),
        ],
        film_id="_unused", region_bbox=region, legend_bbox=legend,
        axis_word_bbox=region, extraction_method="vector_stroke_dash",
        monotonic_direction="increasing",
        metadata={"process": "Small Tank, 68F (20C)", "densitometry": "Diffuse Visual"},
    )
    return chart


def _ci_largetank_chart():
    """Large Tank panel (page index 8, top-right): 4 real developers' CI
    curves (D-76, T-MAX RS, XTOL, HC-110 (B)) -- only T-MAX RS is digitized
    here. Less crowded than the Small Tank panel (no shared-dash-array
    ambiguity confirmed among these 4), but still matched by dash pattern
    rather than position for the same reason -- consistency with the Small
    Tank panel's own method, not because this panel strictly required it.

    T-MAX RS: dash=[6.4777 3.2388], width=0.72 -- the same real dash array
    as Small Tank's D-76, but panel-scoped via region_bbox so there's no
    cross-panel collision. Endpoint cross-check: extracted trace spans
    ~8.9-16.8 min / CI 0.56-0.82, matching the visually-identified curve's
    own real ~8.7-16.5 min span.
    """
    region = (320, 70, 545, 305)
    legend = (466, 186, 537, 236)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=8, chart_id="ci_vs_time_largetank",
        x_tick_regex=r"^\d+$", y_tick_regex=r"\d\.\d",
        x_label="development_time_min", y_label="contrast_index",
        curves=[
            CurveSpec("T-MAX RS", stroke_rgb=_CI_STROKE_RGB, tol=0.02,
                      dash_regex=_CI_DASH_MEDIUM, width=0.72, width_tol=0.1),
        ],
        film_id="_unused", region_bbox=region, legend_bbox=legend,
        axis_word_bbox=region, extraction_method="vector_stroke_dash",
        monotonic_direction="increasing",
        metadata={"process": "Large Tank, 68F (20C)", "densitometry": "Diffuse Visual"},
    )
    return chart


def _d76_chart():
    region = (320, 40, 550, 270)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=7, chart_id="characteristic_curve_d76_smalltank",
        x_tick_regex=r"\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_relative", y_label="density_diffuse_visual",
        curves=[
            CurveSpec("6min", label_regex=r"^6$", qa_source="points_dense"),
            CurveSpec("7.5min", label_regex=r"^7\.5$", qa_source="points_dense"),
            CurveSpec("10min", label_regex=r"^10$", qa_source="points_dense"),
        ],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction="increasing", min_trace_points=50,
        metadata={"developer": "D-76", "process": "Small Tank, 20C (68F)",
                  "densitometry": "Diffuse visual", "exposure": "Daylight"},
    )
    chart.x_axis_calib_override = overline_negative_calib(PDF_PATH, 7, region, tick_regex=r"\d\.0")
    return chart


def _tmaxrs_chart():
    region = (320, 280, 550, 500)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=7, chart_id="characteristic_curve_tmaxrs_largetank",
        x_tick_regex=r"\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_relative", y_label="density_diffuse_visual",
        curves=[
            CurveSpec("8min", label_regex=r"^8$", qa_source="points_dense"),
            CurveSpec("10.5min", label_regex=r"^10\.5$", qa_source="points_dense"),
            CurveSpec("13min", label_regex=r"^13$", qa_source="points_dense"),
            CurveSpec("15min", label_regex=r"^15$", qa_source="points_dense"),
        ],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction="increasing", min_trace_points=50,
        metadata={"developer": "T-MAX RS", "process": "Large Tank, 20C (68F)",
                  "densitometry": "Diffuse visual", "exposure": "Daylight"},
    )
    chart.x_axis_calib_override = overline_negative_calib(PDF_PATH, 7, region, tick_regex=r"\d\.0")
    return chart


def _tmax_chart():
    region = (320, 510, 550, 730)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=7, chart_id="characteristic_curve_tmax_smalltank",
        x_tick_regex=r"\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_relative", y_label="density_diffuse_visual",
        curves=[
            CurveSpec("6min", label_regex=r"^6$", qa_source="points_dense"),
            CurveSpec("7min", label_regex=r"^7$", qa_source="points_dense"),
            CurveSpec("10min", label_regex=r"^10$", qa_source="points_dense"),
            CurveSpec("12min", label_regex=r"^12$", qa_source="points_dense"),
        ],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction="increasing", min_trace_points=50,
        metadata={"developer": "T-MAX", "process": "Small Tank, 20C (68F)",
                  "densitometry": "Diffuse visual", "exposure": "Daylight"},
    )
    chart.x_axis_calib_override = overline_negative_calib(PDF_PATH, 7, region, tick_regex=r"\d\.0")
    return chart


def _spectral_sensitivity_chart():
    region = (40, 490, 290, 665)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=7, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec("1.0+Dmin", label_position_override=(164.7, 583.0), qa_source="points_dense")],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction=None, min_trace_points=10,
        metadata={"developer": "D-76", "process": "68F (20C)",
                  "densitometry": "Diffuse visual", "effective_exposure": "1.4 seconds",
                  "density_over_min": 1.0},
    )
    chart.y_axis_calib_override = overline_symmetric_calib(PDF_PATH, 7, region, tick_regex=r"\d\.0")
    return chart


def _fit_bracket(curves_by_dev, dev_times, rep_idx, label):
    """Same shape as kodak_trix400tx.py's own _fit_bracket -- see that
    module's docstring for the process this mirrors."""
    rep_dev = dev_times[rep_idx]
    rep_points = curves_by_dev[rep_dev]
    rep_base = min(y for _, y in rep_points)
    x_speed_rep = tc.speed_point_x(rep_points, rep_base, criterion=1.0)
    shift = -x_speed_rep

    fits = tc.fit_dev_times_parallel(
        curves_by_dev, dev_times, shift, N_LAYERS, label,
    )
    return fits, shift, rep_dev


def _run_bracket(chart_fn, dev_times, rep_idx, label, subdir, dev_key_names, log_sensitivity,
                  ci_points):
    """Digitizes + fits + writes ONE developer bracket's stocks. build_all()
    below calls this once per _BRACKETS entry, sequentially -- see that
    list's own comment for why (fanning these out concurrently was tried
    and measured worse; the fix for the real bottleneck is
    fit_dev_times_parallel's own global semaphore, not concurrency here).
    `ci_points` is that bracket's own real digitized Contrast-Index-vs-time
    curve (points_dense, from _ci_smalltank_chart/_ci_largetank_chart) --
    used to tag each stock's name with its own real, interpolated CI, same
    convention as kodak_trix400tx.py's own brackets. Unlike Tri-X's own CI
    charts (whose plotted range fully covers their own H&D bracket's dev
    times -- confirmed by direct comparison), all three of THIS file's real
    plotted CI curves run a bit short of their own H&D bracket's real
    times at one end or both (e.g. Small Tank T-MAX's CI curve starts
    ~7.7min but that bracket's own H&D panel plots real curves down to
    6min) -- these are two independently-drawn Kodak charts with no reason
    to share an exact time range, not a digitization gap. real_ci_at()
    clamps rather than extrapolates outside a curve's own digitized range
    (see its own docstring), so a dev_t outside that range gets skipped
    below rather than tagged with a clamped boundary value dressed up as a
    real Kodak measurement (the clamped value can even coincidentally
    equal CI 0.56 and falsely trigger ci_label's own "(normal)" tag)."""
    chart = chart_fn()
    result = digitize_chart(chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, chart, result, OUT_ROOT / subdir)
    # points_dense, not points -- see SIMPLIFY_TOLERANCE's comment in
    # digitizer_core.py: fitting/interpolation draws from the fullest-fidelity
    # real data, not the RDP-reduced QA/compactness set.
    curves_by_dev = {float(name.replace("min", "")): result["curves"][name]["points_dense"]
                      for name in dev_key_names}
    fits, shift, rep_dev = _fit_bracket(curves_by_dev, dev_times, rep_idx, label)
    ci_xs = [p[0] for p in ci_points]
    ci_lo, ci_hi = min(ci_xs), max(ci_xs)
    written = {}
    for dev_t in dev_times:
        fit, base_density = fits[dev_t]
        stock = f"kodak_tmax100_{subdir.split('_')[-1]}_{tc.fmt_time_slug(dev_t)}"
        if ci_lo <= dev_t <= ci_hi:
            real_ci = tc.real_ci_at(ci_points, dev_t)
            name = f"{FILM_NAME_PREFIX} — {label} {tc.fmt_time(dev_t)}, {tc.ci_label(real_ci)}"
        else:
            # Real Kodak CI curve doesn't cover this dev_t (see this
            # function's own docstring) -- no CI tag rather than a
            # clamped/fabricated one.
            name = f"{FILM_NAME_PREFIX} — {label} {tc.fmt_time(dev_t)}"
        source_profile, pack_profile, out_dir = tc.write_single_dev_time_stock(
            out_root=OUT_ROOT / subdir, stock=stock, name=name,
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


# Each entry: (chart_fn, dev_times, rep_idx, label, subdir, dev_key_names,
# ci_curve_name). ci_curve_name looks up that bracket's own real CI curve in
# build_all()'s ci_points_by_name dict (see the two CI charts above --
# D-76/T-MAX come from the Small Tank panel, T-MAX RS from the Large Tank
# panel). build_all() calls _run_bracket once per entry, sequentially --
# fanning these out concurrently was tried and measured WORSE for overall
# wall-clock (see trix_common.py's FIT_SEMAPHORE comment for the full
# history); the fix for the actual measured bottleneck lives in
# fit_dev_times_parallel's own global semaphore now, not at this level.
_BRACKETS = [
    (_d76_chart, D76_DEV_TIMES, D76_REP_IDX, "D-76",
     "small_tank_d76", ["6min", "7.5min", "10min"], "D-76"),
    (_tmaxrs_chart, TMAXRS_DEV_TIMES, TMAXRS_REP_IDX, "T-MAX RS",
     "large_tank_tmaxrs", ["8min", "10.5min", "13min", "15min"], "T-MAX RS"),
    (_tmax_chart, TMAX_DEV_TIMES, TMAX_REP_IDX, "T-MAX",
     "small_tank_tmax", ["6min", "7min", "10min", "12min"], "T-MAX"),
]


def build_all():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    # --- Spectral sensitivity (shared by all three developer brackets) -----
    spec_chart = _spectral_sensitivity_chart()
    spec_result = digitize_chart(spec_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, spec_chart, spec_result, OUT_ROOT / "spectral_sensitivity")
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

    # --- Contrast Index (shared: Small Tank panel feeds 2 brackets) --------
    ci_smalltank_chart = _ci_smalltank_chart()
    ci_smalltank_result = digitize_chart(ci_smalltank_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, ci_smalltank_chart, ci_smalltank_result,
                         OUT_ROOT / "contrast_index_smalltank")
    ci_largetank_chart = _ci_largetank_chart()
    ci_largetank_result = digitize_chart(ci_largetank_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, ci_largetank_chart, ci_largetank_result,
                         OUT_ROOT / "contrast_index_largetank")
    ci_points_by_name = {
        "D-76": ci_smalltank_result["curves"]["D-76"]["points_dense"],
        "T-MAX": ci_smalltank_result["curves"]["T-MAX"]["points_dense"],
        "T-MAX RS": ci_largetank_result["curves"]["T-MAX RS"]["points_dense"],
    }

    written = {}
    for chart_fn, dev_times, rep_idx, label, subdir, dev_key_names, ci_curve_name in _BRACKETS:
        written.update(_run_bracket(chart_fn, dev_times, rep_idx, label, subdir, dev_key_names,
                                     log_sensitivity, ci_points_by_name[ci_curve_name]))
    return written


def _make_entry(stock, out_dir):
    import types
    return types.SimpleNamespace(build=lambda: _build_one(stock), OUT_DIR=out_dir)


_BUILT_CACHE = {}


def _build_one(stock):
    """main.py's PRODUCTS interface calls .build() per stock slug, but all
    11 T-Max 100 stocks come out of one shared digitize+fit pass (same
    charts). Runs the shared pass once (cached) and returns just the one
    profile pair the caller asked for."""
    if not _BUILT_CACHE:
        _BUILT_CACHE.update(build_all())
    return _BUILT_CACHE[stock]


def _out_dir_for(stock):
    if "_d76_" in stock:
        return OUT_ROOT / "small_tank_d76" / stock
    if "_tmaxrs_" in stock:
        return OUT_ROOT / "large_tank_tmaxrs" / stock
    return OUT_ROOT / "small_tank_tmax" / stock


_STOCK_SLUGS = (
    [f"kodak_tmax100_d76_{tc.fmt_time_slug(t)}" for t in D76_DEV_TIMES]
    + [f"kodak_tmax100_tmaxrs_{tc.fmt_time_slug(t)}" for t in TMAXRS_DEV_TIMES]
    + [f"kodak_tmax100_tmax_{tc.fmt_time_slug(t)}" for t in TMAX_DEV_TIMES]
)

PRODUCTS = {slug: _make_entry(slug, _out_dir_for(slug)) for slug in _STOCK_SLUGS}


if __name__ == "__main__":
    build_all()
