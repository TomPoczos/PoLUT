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

Deliberately NOT digitized: this datasheet's own "Contrast Index Curves"
page (index 8). Unlike Tri-X's F-9 sheet -- one CI-vs-time curve per
developer per panel, cleanly separated -- this sheet's own Small Tank panel
overlays SEVEN developers' CI curves (D-76, D-76 1:1, T-MAX, T-MAX RS,
XTOL, XTOL 1:1, HC-110(B)) in one box, all converging and repeatedly
crossing each other right through the 10-14 min / CI 0.65-0.80 region where
our real D-76 and T-MAX small-tank stocks actually land (confirmed visually
against the rendered page, not assumed). That is exactly the tangled-curve
shape this project's own CLAUDE.md warns produced a confidently wrong,
still-clean-R^2 label assignment on kodak_polymax_fine_art.py's own
filterset panels -- rank-by-x and label-proximity would both be guessing in
the crossing region, with no reliable "check the real separation
numerically" escape hatch the way that fix used, since seven traces are
mutually near-coincident across most of the panel, not just two. Rather
than risk transcribing a wrong CI onto a real stock name, every stock here
is named and tagged by developer + time only, no CI/push-pull label -- a
deliberate scope cut, not an oversight. (The Large Tank panel, top-right,
has only 4 series and looks more separable, but it only covers T-MAX RS of
this file's three brackets, and mixing "CI digitized for one bracket, not
the other two" into one product's stock names would be its own kind of
inconsistency -- left out uniformly instead.)
"""

from pathlib import Path

import numpy as np

import canonical_grids as grids
import density_model as dm
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
    "D-min' trace, D-76 68F/20C). Digitized independently via this project's "
    "own tooling."
)


def _d76_chart():
    region = (320, 40, 550, 270)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=7, chart_id="characteristic_curve_d76_smalltank",
        x_tick_regex=r"\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_relative", y_label="density_diffuse_visual",
        curves=[
            CurveSpec("6min", label_regex=r"^6$"),
            CurveSpec("7.5min", label_regex=r"^7\.5$"),
            CurveSpec("10min", label_regex=r"^10$"),
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
            CurveSpec("8min", label_regex=r"^8$"),
            CurveSpec("10.5min", label_regex=r"^10\.5$"),
            CurveSpec("13min", label_regex=r"^13$"),
            CurveSpec("15min", label_regex=r"^15$"),
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
            CurveSpec("6min", label_regex=r"^6$"),
            CurveSpec("7min", label_regex=r"^7$"),
            CurveSpec("10min", label_regex=r"^10$"),
            CurveSpec("12min", label_regex=r"^12$"),
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
        curves=[CurveSpec("1.0+Dmin", label_position_override=(164.7, 583.0))],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction=None, min_trace_points=10,
        metadata={"developer": "D-76", "process": "68F (20C)",
                  "densitometry": "Diffuse visual", "effective_exposure": "1.4 seconds",
                  "density_over_min": 1.0},
    )
    chart.y_axis_calib_override = overline_symmetric_calib(PDF_PATH, 7, region, tick_regex=r"\d\.0")
    return chart


def _fit_bracket(curves_by_dev, dev_times, rep_idx, label, qa_dir):
    """Same shape as kodak_trix400tx.py's own _fit_bracket -- see that
    module's docstring for the process this mirrors."""
    rep_dev = dev_times[rep_idx]
    rep_points = curves_by_dev[rep_dev]
    rep_base = min(y for _, y in rep_points)
    x_speed_rep = tc.speed_point_x(rep_points, rep_base, criterion=1.0)
    shift = -x_speed_rep

    qa_dir.mkdir(parents=True, exist_ok=True)
    fits, xs_by_dev, ys_by_dev = tc.fit_dev_times_parallel(
        curves_by_dev, dev_times, shift, N_LAYERS, label,
    )
    for dev_t in dev_times:
        fit, _ = fits[dev_t]
        dm.plot_fit_qa(xs_by_dev[dev_t], ys_by_dev[dev_t], fit, grids.LOG_EXPOSURE,
                        title=f"Kodak T-Max 100, {label} {dev_t:g} min (net density, above base)",
                        out_path=qa_dir / f"density_fit_{label.lower().replace('-', '').replace(' ', '')}_{dev_t:g}min.png")
    return fits, shift, rep_dev


def build_all():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    # --- Spectral sensitivity (shared by all three developer brackets) -----
    spec_chart = _spectral_sensitivity_chart()
    spec_result = digitize_chart(spec_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, spec_chart, spec_result, OUT_ROOT / "spectral_sensitivity")
    sens_points = spec_result["curves"]["1.0+Dmin"]["points"]
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

    def _run_bracket(chart_fn, dev_times, rep_idx, label, subdir, dev_key_names):
        chart = chart_fn()
        result = digitize_chart(chart, PDF_PATH)
        tc.write_raw_and_qa(PDF_PATH, chart, result, OUT_ROOT / subdir)
        curves_by_dev = {float(name.replace("min", "")): result["curves"][name]["points"]
                          for name in dev_key_names}
        fits, shift, rep_dev = _fit_bracket(curves_by_dev, dev_times, rep_idx, label,
                                             OUT_ROOT / subdir / "qa")
        for dev_t in dev_times:
            fit, base_density = fits[dev_t]
            stock = f"kodak_tmax100_{subdir.split('_')[-1]}_{tc.fmt_time_slug(dev_t)}"
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

    _run_bracket(_d76_chart, D76_DEV_TIMES, D76_REP_IDX, "D-76",
                 "small_tank_d76", ["6min", "7.5min", "10min"])
    _run_bracket(_tmaxrs_chart, TMAXRS_DEV_TIMES, TMAXRS_REP_IDX, "T-MAX RS",
                 "large_tank_tmaxrs", ["8min", "10.5min", "13min", "15min"])
    _run_bracket(_tmax_chart, TMAX_DEV_TIMES, TMAX_REP_IDX, "T-MAX",
                 "small_tank_tmax", ["6min", "7min", "10min", "12min"])

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
