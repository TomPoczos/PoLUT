"""
Kodak Tri-X Pan Professional Film (TXP), ISO 320, SHEET-FILM processing
variant -- Kodak's own datasheet labels this "TXT" (a distinct code, not a
typo of TXP): same physical emulsion as kodak_trix400txp.py's roll-film
TXP, but a separate Characteristic-Curve panel with its own real, different
process condition (Large tank, 70F/21C -- vs TXP's 68F/20C -- with
gaseous-burst/tray agitation methods appropriate to sheet film, per page 5's
"Tray and Large-Tank Processing -- Sheets" section). Confirmed as a real,
distinct panel (not a duplicate/typo) by reading the actual page headers:
"KODAK TRI-X PAN PROFESSIONAL FILM / TXP" (page 10) vs "... / TXT" (page 11).

Source: papers/125pixcom/film/kodak/f9-Tri-X_Pan-199906.pdf (Kodak F-9, June
1999), page 11 (index 10): "Characteristic Curves" (HC-110 Developer,
Dilution B, Large tank, 70F/21C, 5.5/7/8.5/10 min -- "5½"/"7"/"8½"/"10min"
on the chart, fractions again split across separate text tokens, matched by
label_position_override) and its own "Contrast-Index Curves" panel.

**The HC-110 label on this panel does NOT sit on/near its own curve** --
unlike TXP's sibling panel, where the "HC-110 (Dil B)" label sits directly
at its curve's own right-edge terminus, TXT's four curves (DK-50/D-76/
HC-110/Microdol-X) start bunched within ~0.05 CI of each other at the
panel's left edge, and the label's naive text-bbox position landed inside
that bunch -- confirmed wrong the first time (the naive override grabbed
the topmost/DK-50 trace, not HC-110) by cross-checking against the actual
real leader-line VECTOR segment (found via page.get_drawings(): a constant-
y horizontal line from (272, 424.4) to (337.7, 424.4) in PDF page-space,
i.e. the label's own leader line, not the label text position). The
override below uses that verified leader-line touch point (337.7, 424.4),
not the label text's own bbox -- see this project's CLAUDE.md for why
close-together curves near a label are exactly the failure mode that's
bitten this pipeline before (kodak_polymax_fine_art.py's filterset panels).

TXT has no push-processing section either (see kodak_trix400txp.py) -- CI-
only labels, no stops-of-push/pull claim. The 7min/70F stock's real
digitized CI (0.561) lands within "(normal)" tolerance of Kodak's 0.56
target and matches Kodak's own Manual Processing table's recommended time
for this exact developer/tank/temp (7min, large tank, HC-110 Dil B, 70F).
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
OUT_ROOT = HERE / "outputs" / "film" / "bw" / "negative" / "kodak" / "kodak_trix400" / "txt" / "large_tank_hc110b"

FILM_NAME_PREFIX = "Tri-X Pan Pro 320 sheet (TXT)"
TARGET_PRINT = "kodak_polymax_fine_art_grade2"
N_LAYERS = 3

DEV_TIMES = [5.5, 7.0, 8.5, 10.0]
REP_IDX = 1  # 7 min -- Kodak's own real "normal" time for this developer/tank/temp

DATASOURCE = (
    "Kodak F-9 'KODAK TRI-X Pan and KODAK TRI-X Pan Professional Films' datasheet, "
    "June 1999 (papers/125pixcom/film/kodak/f9-Tri-X_Pan-199906.pdf), page 11 "
    "'Characteristic Curves' (HC-110 Developer Dilution B, Large tank, 70F/21C, "
    "5.5/7/8.5/10min) and page 9 'Spectral-Sensitivity Curve' ('1.0 + D-min' trace, "
    "shared with kodak_trix400tx.py -- no separate TXT spectral-sensitivity chart "
    "published; same real limitation as kodak_trix400txp.py, flagged there too). "
    "Digitized independently via this project's own tooling."
)


def _hd_chart():
    region = (200, 75, 420, 288)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=10, chart_id="characteristic_curve_txt_hc110",
        x_tick_regex=r"\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_relative", y_label="density_diffuse_visual",
        curves=[
            CurveSpec("5.5min", label_position_override=(376, 230), qa_source="points_dense"),
            CurveSpec("7min", label_position_override=(308, 220), qa_source="points_dense"),
            CurveSpec("8.5min", label_position_override=(325, 200), qa_source="points_dense"),
            CurveSpec("10min", label_position_override=(375, 181), qa_source="points_dense"),
        ],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction="increasing", min_trace_points=50,
        split_on_x_reversal=True, reversal_run_length=5,
        # 7min and 8.5min each lose their last ~5 points (right at the
        # shoulder, next to the chart's own right border) as a separate tiny
        # drawing object -- a real pen lift in the source PDF, not a
        # digitization artifact -- and the two curves' own tail fragments
        # sit closer to EACH OTHER (~3px) than either does to its own true
        # parent curve's endpoint (~7-9px), so plain proximity-based
        # cross_object_merge mismatches or transitively fuses them. Confirmed
        # via digitizer_core.py's extract_traces_in_region(min_points=1)
        # probe: without this, curves' points_dense stopped at log_exposure
        # -0.18/-0.28 instead of reaching the panel's real ~0.0 edge like
        # 5.5min/10min do. merge_strategy="chain_slope" (see that function's
        # own docstring for this exact case) discriminates the two tail
        # fragments correctly by local trajectory instead of raw distance.
        cross_object_merge=True, merge_strategy="chain_slope",
        metadata={"developer": "HC-110 (Dilution B)", "process": "Large tank, 70F (21C)",
                  "densitometry": "Diffuse visual", "exposure": "Daylight, 1/50 second"},
    )
    chart.x_axis_calib_override = overline_negative_calib(PDF_PATH, 10, region, tick_regex=r"\d\.0")
    return chart


def _ci_chart():
    region = (207, 315, 420, 526)
    # Verified real leader-line touch point (see module docstring) -- NOT
    # the "HC-110 (Dil B)" text label's own bbox, which sits in a region
    # where all 4 curves are within ~0.05 CI of each other.
    return ChartSpec(
        pdf=str(PDF_PATH), page_index=10, chart_id="ci_vs_time_txt_hc110",
        x_tick_regex=r"^\d+$", y_tick_regex=r"\d\.\d",
        x_label="development_time_min", y_label="contrast_index",
        curves=[CurveSpec("HC-110", label_position_override=(337.7, 424.4), qa_source="points_dense")],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction="increasing", min_trace_points=20,
        metadata={"developer": "HC-110 (Dilution B)", "process": "Large tank, 70F (21C)"},
    )


def _spectral_sensitivity_chart():
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
                  "note": "shared with TX -- no separate TXT spectral-sensitivity chart published"},
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
                     for t in ("5.5min", "7min", "8.5min", "10min")}

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
        stock = f"kodak_trix400txt_hc110b_{tc.fmt_time_slug(dev_t)}"
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


_STOCK_SLUGS = [f"kodak_trix400txt_hc110b_{tc.fmt_time_slug(t)}" for t in DEV_TIMES]

PRODUCTS = {slug: _make_entry(slug) for slug in _STOCK_SLUGS}


if __name__ == "__main__":
    build_all()
