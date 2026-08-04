"""
Kodak Tri-X Pan Professional Film (TXP), ISO 320 -- a separate, distinct
product from TX (see kodak_trix400tx.py's own module docstring), shot as a
professional roll-film stock (not the sheet-film TXT variant, which has its
own separate panel and its own module, kodak_trix400txt.py -- confirmed
real, distinct headers on the source PDF: "KODAK TRI-X PAN PROFESSIONAL
FILM / TXP" on page 10 vs "... / TXT" on page 11, different agitation
methods, different process temperature).

Source: papers/125pixcom/film/kodak/f9-Tri-X_Pan-199906.pdf (Kodak F-9, June
1999), page 10 (index 9): "Characteristic Curves" (HC-110 Developer,
Dilution B, Large tank, 68F/20C, 3.5/6.25/9 min -- printed on the chart as
"3½min"/"6¼min"/"9min", each fraction rendered as separate stacked text
tokens rather than one clean numeric string, so these three curves are
matched by explicit label_position_override coordinates rather than a text
regex) and its own "Contrast-Index Curves" panel (same process, HC-110 line
only digitized here -- see trix_common.py's own module docstring for why
the other developers on that panel, D-76/DK-50/Microdol-X, are NOT
digitized or shipped as stocks: Kodak never published their H&D curve SHAPE
for this film, only their contrast slope, and rescaling a different
developer's curve to match a borrowed CI number is not a real measurement).

TXP has no push-processing section in this datasheet (only TX does, page
6) -- no stock here gets a stops-of-push/pull label, only its own real,
Kodak-published Contrast Index, per trix_common.py's shared convention. The
6.25min/68F stock's real digitized CI (0.563) lands within the "(normal)"
tolerance of Kodak's stated 0.56 target AND matches Kodak's own separate
Manual Processing table's recommended time for this exact developer/tank/
temp combination (6¼min) -- two independent real sources agreeing.

Uses trix_common.py's shared exposure/fitting/writing helpers -- see
kodak_trix400tx.py for the fuller explanation of that shared machinery
(anchor-per-bracket, per-stock single-development-time profiles, no
collapse). TXP has no separate "small tank" Characteristic-Curve panel in
this datasheet (only the CI-vs-time panel shows other tank/developer
combinations, without a charted H&D shape) -- one bracket only.
"""

import types
from pathlib import Path

import numpy as np

import canonical_grids as grids
import exposure_calibration as ec
import trix_common as tc
from digitizer_core import ChartSpec, CurveSpec, digitize_chart
from kodak_helpers import overline_negative_calib, overline_symmetric_calib

PDF_PATH = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom/film/kodak/f9-Tri-X_Pan-199906.pdf")
HERE = Path(__file__).parent.parent
OUT_ROOT = HERE / "outputs" / "film" / "bw" / "negative" / "kodak" / "kodak_trix400" / "txp" / "large_tank_hc110b"

FILM_NAME_PREFIX = "Tri-X Pan Pro 320 (TXP)"
TARGET_PRINT = "kodak_polymax_fine_art_grade2"
N_LAYERS = 3

DEV_TIMES = [3.5, 6.25, 9.0]
REP_IDX = 1  # 6.25 min -- Kodak's own real "normal" time for this developer/tank/temp

DATASOURCE = (
    "Kodak F-9 'KODAK TRI-X Pan and KODAK TRI-X Pan Professional Films' datasheet, "
    "June 1999 (papers/125pixcom/film/kodak/f9-Tri-X_Pan-199906.pdf), page 10 "
    "'Characteristic Curves' (HC-110 Developer Dilution B, Large tank, 68F/20C, "
    "3.5/6.25/9min) and page 9 'Spectral-Sensitivity Curve' ('1.0 + D-min' trace, "
    "shared with kodak_trix400tx.py -- TXP's own datasheet doesn't publish a "
    "separate spectral-sensitivity chart for TXP, only for TX; treated as the same "
    "panchromatic sensitization curve, a real limitation of this source, not assumed "
    "silently -- flagged here for anyone extending this product later). Digitized "
    "independently via this project's own tooling."
)


def _hd_chart():
    region = (186, 75, 410, 290)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=9, chart_id="characteristic_curve_txp_hc110",
        x_tick_regex=r"\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_relative", y_label="density_diffuse_visual",
        curves=[
            CurveSpec("3.5min", label_position_override=(361, 244), qa_source="points_dense"),
            CurveSpec("6.25min", label_position_override=(303, 218), qa_source="points_dense"),
            CurveSpec("9min", label_position_override=(341, 200), qa_source="points_dense"),
        ],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction="increasing", min_trace_points=50,
        split_on_x_reversal=True, reversal_run_length=5,
        metadata={"developer": "HC-110 (Dilution B)", "process": "Large tank, 68F (20C)",
                  "densitometry": "Diffuse visual", "exposure": "Daylight, 1/50 second"},
    )
    chart.x_axis_calib_override = overline_negative_calib(PDF_PATH, 9, region, tick_regex=r"\d\.0")
    return chart


def _ci_chart():
    region = (196, 320, 415, 531)
    # Label sits directly at the curve's own terminus (no separate leader
    # line found near the text bbox) -- confirmed against the QA overlay,
    # unlike TXT's HC-110 label on the sibling panel (see kodak_trix400txt.py).
    return ChartSpec(
        pdf=str(PDF_PATH), page_index=9, chart_id="ci_vs_time_txp_hc110",
        x_tick_regex=r"^\d+$", y_tick_regex=r"\d\.\d",
        x_label="development_time_min", y_label="contrast_index",
        curves=[CurveSpec("HC-110", label_position_override=(420, 290), qa_source="points_dense")],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction="increasing", min_trace_points=20,
        metadata={"developer": "HC-110 (Dilution B)", "process": "Large tank, 68F (20C)"},
    )


def _spectral_sensitivity_chart():
    # Same real chart kodak_trix400tx.py digitizes -- TXP's own datasheet
    # section doesn't publish a separate spectral-sensitivity panel for TXP.
    region = (272, 40, 604, 290)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=8, chart_id="spectral_sensitivity_shared_tx",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec("1.0+Dmin", label_position_override=(471.5, 164.5), qa_source="points_dense")],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction=None, min_trace_points=10,
        metadata={"developer": "D-76", "process": "68F (20C)",
                  "densitometry": "Diffuse visual", "effective_exposure": "1.4 seconds",
                  "density_over_min": 1.0,
                  "note": "shared with TX -- no separate TXP spectral-sensitivity chart published"},
    )
    chart.y_axis_calib_override = overline_symmetric_calib(PDF_PATH, 8, region, tick_regex=r"\d\.0")
    return chart


def build_all():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

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

    hd_chart = _hd_chart()
    hd_result = digitize_chart(hd_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, hd_chart, hd_result, OUT_ROOT)
    # points_dense, not points -- see SIMPLIFY_TOLERANCE's comment in
    # digitizer_core.py: fitting/interpolation draws from the fullest-fidelity
    # real data, not the RDP-reduced QA/compactness set.
    curves_by_dev = {float(t.replace("min", "")): hd_result["curves"][t]["points_dense"]
                     for t in ("3.5min", "6.25min", "9min")}

    rep_dev = DEV_TIMES[REP_IDX]
    rep_points = curves_by_dev[rep_dev]
    rep_base = min(y for _, y in rep_points)
    x_speed_rep = tc.speed_point_x(rep_points, rep_base, criterion=1.0)
    shift = -x_speed_rep

    fits = tc.fit_dev_times_parallel(
        curves_by_dev, DEV_TIMES, shift, N_LAYERS, "HC-110",
    )

    ci_chart = _ci_chart()
    ci_result = digitize_chart(ci_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, ci_chart, ci_result, OUT_ROOT)
    ci_points = ci_result["curves"]["HC-110"]["points_dense"]

    written = {}
    for dev_t in DEV_TIMES:
        fit, base_density = fits[dev_t]
        real_ci = tc.real_ci_at(ci_points, dev_t)
        stock = f"kodak_trix400txp_hc110b_{tc.fmt_time_slug(dev_t)}"
        name = f"{FILM_NAME_PREFIX} — HC-110B {tc.fmt_time(dev_t)}, {tc.ci_label(real_ci)}"
        source_profile, pack_profile, out_dir = tc.write_single_dev_time_stock(
            out_root=OUT_ROOT, stock=stock, name=name,
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


_BUILT_CACHE = {}


def _build_one(stock):
    if not _BUILT_CACHE:
        _BUILT_CACHE.update(build_all())
    return _BUILT_CACHE[stock]


def _make_entry(stock):
    return types.SimpleNamespace(build=lambda: _build_one(stock), OUT_DIR=OUT_ROOT / stock)


_STOCK_SLUGS = [f"kodak_trix400txp_hc110b_{tc.fmt_time_slug(t)}" for t in DEV_TIMES]

PRODUCTS = {slug: _make_entry(slug) for slug in _STOCK_SLUGS}


if __name__ == "__main__":
    build_all()
