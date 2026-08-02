"""
Kodak Tri-X Pan Film (TX), ISO 400/27 deg -- the still-photography camera
negative available in 120/135/70mm (NOT the "Professional" TXP, a separate
ISO 320 product; TX's sensitometry doesn't vary by roll format, so "120
format" only disambiguates which product this is, not a different data set
-- see the project plan's Context section).

Source: papers/125pixcom/film/kodak/f9-Tri-X_Pan-199906.pdf (Kodak F-9, June
1999), page 8 (index 7) "Characteristic Curves" D-76 panel (3 development
times: 7/9/11 min, Large tank, 68F/20C -- the datasheet's own stated
standard condition) and page 9 (index 8) "Spectral-Sensitivity Curve", the
"1.0 + D-min" trace (matches info.log_sensitivity_density_over_min=1.0).

Both charts are Kodak's ~1997-2003-era vector-drawn, black-ink,
inline-label-identified-curve style (digitizer_core.py Strategy D,
vector_position) -- the same style tools/curve_digitizer/kodak_bw.py already
digitizes for every other Kodak B&W sheet in this era. Both axes also need
kodak_helpers.py's overline-minus-sign correction (confirmed against the raw
word positions: the log-exposure axis prints "4.0 3.0 2.0 1.0 0.0 1.0"
left-to-right with no literal minus glyph, and the log-sensitivity axis
prints "3.0 2.0 1.0 0.0 1.0" top-to-bottom the same way).

Exposure-axis calibration note (a real, documented limitation, not silently
assumed correct): the Characteristic Curve chart's "0.0" and the Spectral-
Sensitivity chart's absolute values come from two different classical
sensitometric measurement conventions (a full-spectrum daylight sensitometer
exposure vs. a monochromator spectrograph exposure) that this single 1999
datasheet doesn't cross-calibrate against each other. We anchor the density-
curve family so the representative (9 min) curve's own "density = base +
log_sensitivity_density_over_min" crossing lands at the canonical grid's
logE=0 (spektrafilm's shared exposure axis), and digitize log_sensitivity's
absolute values as printed, unmodified. If a rendered image's overall
exposure placement needs a nudge, that's a single constant offset to
log_sensitivity (equivalently, the module's own exposure_comp_ev control) --
not a curve-shape problem. Flagged again in the printed summary this script
prints, not just here.
"""

from pathlib import Path

import numpy as np

import canonical_grids as grids
import density_model as dm
import exposure_calibration as ec
import spektra_profile as sp
from digitizer_core import ChartSpec, CurveSpec, digitize_chart, render_qa_overlay
from kodak_helpers import overline_negative_calib, overline_symmetric_calib

import fitz

PDF_PATH = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom/film/kodak/f9-Tri-X_Pan-199906.pdf")
HERE = Path(__file__).parent.parent
OUT_DIR = HERE / "outputs" / "film" / "bw" / "negative" / "kodak" / "kodak_trix400"

STOCK = "kodak_trix400"
DEV_TIMES = [7.0, 9.0, 11.0]  # ascending -- collapse-to-pack picks the middle position (9 min)
REPRESENTATIVE_IDX = 1  # index of 9.0 in DEV_TIMES -- the anchor/collapse target
N_LAYERS = 3  # grain-speed sub-layers (fast/mid/slow) per norm_cdfs fit

DATASOURCE = (
    "Kodak F-9 'KODAK TRI-X Pan and KODAK TRI-X Pan Professional Films' datasheet, "
    "June 1999 (papers/125pixcom/film/kodak/f9-Tri-X_Pan-199906.pdf), page 8 "
    "'Characteristic Curves' (D-76, Large tank, 68F/20C, 7/9/11 min) and page 9 "
    "'Spectral-Sensitivity Curve' ('1.0 + D-min' trace). Digitized independently "
    "via this project's own tooling, not derived from spektrafilm's own dataset."
)


def _characteristic_curve_chart():
    region = (31, 40, 290, 285)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=7, chart_id="characteristic_curve_d76",
        x_tick_regex=r"\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_relative", y_label="density_diffuse_visual",
        curves=[
            CurveSpec("7min", label_regex=r"^7$"),
            CurveSpec("9min", label_regex=r"^9$"),
            CurveSpec("11min", label_regex=r"^11$"),
        ],
        film_id="_unused",
        region_bbox=region,
        extraction_method="vector_position",
        monotonic_direction="increasing",
        # 12 (the usual default) is too low here: the "11 min"/"9 min" labels'
        # own tiny leader-line/tick-stub vector fragments have 16 points each
        # and were getting picked up as candidate traces, confusing label
        # assignment (confirmed via a direct extract_traces_in_region() probe --
        # 5 raw traces at min_points=12, only 3 of them real curves at ~192-212
        # points each). 50 cleanly excludes the fragments without threatening
        # any real curve.
        min_trace_points=50,
        metadata={"developer": "D-76", "process": "Large tank, 68F (20C)",
                  "densitometry": "Diffuse visual", "exposure": "Daylight, 1/50 second"},
    )
    chart.x_axis_calib_override = overline_negative_calib(PDF_PATH, 7, region, tick_regex=r"\d\.0")
    return chart


def _spectral_sensitivity_chart():
    region = (272, 40, 604, 290)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=8, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[
            CurveSpec("1.0+Dmin", label_position_override=(471.5, 164.5)),
        ],
        film_id="_unused",
        region_bbox=region,
        extraction_method="vector_position",
        monotonic_direction=None,  # real peak shape, not a monotonic material property
        min_trace_points=10,
        metadata={"developer": "D-76", "process": "68F (20C)",
                  "densitometry": "Diffuse visual", "effective_exposure": "1.4 seconds",
                  "density_over_min": 1.0},
    )
    chart.y_axis_calib_override = overline_symmetric_calib(PDF_PATH, 8, region, tick_regex=r"\d\.0")
    return chart


def _write_raw_and_qa(chart, result, out_dir):
    out_dir_raw = out_dir / "raw"
    out_dir_qa = out_dir / "qa"
    out_dir_raw.mkdir(parents=True, exist_ok=True)
    out_dir_qa.mkdir(parents=True, exist_ok=True)

    qa_path = out_dir_qa / f"{chart.chart_id}_qa_overlay.png"
    doc = fitz.open(PDF_PATH)
    render_qa_overlay([(chart, result["_qa_results"], result["_qa_calib"], doc[chart.page_index])], qa_path)
    doc.close()

    raw_out = dict(result)
    raw_out["qa_overlay_png"] = qa_path.name
    for k in ("_qa_results", "_qa_calib", "_qa_page_number"):
        raw_out.pop(k, None)
    import json
    (out_dir_raw / f"{chart.chart_id}.json").write_text(json.dumps(raw_out, indent=2))
    return qa_path


def _speed_point_x(points, base_density, criterion=1.0):
    """Interpolate the digitized (log_exposure, density) points to find the
    log_exposure at density = base_density + criterion. Points are already
    monotonic-increasing in density (enforced at digitization time)."""
    xs = np.array([p[0] for p in points])
    ys = np.array([p[1] for p in points])
    order = np.argsort(ys)
    return float(np.interp(base_density + criterion, ys[order], xs[order]))


def build():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- Characteristic curves (D-76, 7/9/11 min) ---------------------------
    char_chart = _characteristic_curve_chart()
    char_result = digitize_chart(char_chart, PDF_PATH)
    _write_raw_and_qa(char_chart, char_result, OUT_DIR)

    curves_by_dev = {}
    for name, dev_t in zip(("7min", "9min", "11min"), DEV_TIMES):
        curves_by_dev[dev_t] = char_result["curves"][name]["points"]

    # --- Exposure-axis anchor: representative (9 min) curve's own speed point,
    #     applied as one uniform shift to all 3 curves (see module docstring). ---
    rep_dev = DEV_TIMES[REPRESENTATIVE_IDX]
    rep_points = curves_by_dev[rep_dev]
    rep_base = min(y for _, y in rep_points)
    x_speed_rep = _speed_point_x(rep_points, rep_base, criterion=1.0)
    shift = -x_speed_rep

    # --- Fit norm_cdfs per development time, on the shifted exposure axis ---
    fits = {}
    base_densities = {}
    fit_report = {"exposure_anchor": {"representative_dev_min": rep_dev,
                                       "x_speed_kodak_chart": x_speed_rep,
                                       "applied_shift": shift},
                   "curves": {}}
    for dev_t in DEV_TIMES:
        points = curves_by_dev[dev_t]
        xs = np.array([p[0] for p in points]) + shift
        ys_absolute = np.array([p[1] for p in points])
        base_densities[dev_t] = float(ys_absolute.min())
        # Fit NET density (above base) -- compute_density_spectral() (both the
        # Python reference and darktable's spektra_sim.c) adds base_density
        # back on separately; fitting the raw absolute digitized values here
        # would double-count it. See density_model.py's own module docstring.
        ys = ys_absolute - base_densities[dev_t]
        fit = dm.fit_norm_cdfs(xs, ys, n_layers=N_LAYERS)
        fits[dev_t] = fit
        dm.plot_fit_qa(xs, ys, fit, grids.LOG_EXPOSURE,
                        title=f"Kodak Tri-X 400 (TX), D-76 {dev_t:g} min (net density, above base)",
                        out_path=OUT_DIR / "qa" / f"density_fit_d76_{dev_t:g}min.png")
        fit_report["curves"][f"{dev_t:g}min"] = {
            "r_squared": fit.r_squared, "max_residual": fit.max_residual,
            "base_density": base_densities[dev_t],
            "centers": fit.centers.tolist(), "amplitudes": fit.amplitudes.tolist(),
            "sigmas": fit.sigmas.tolist(),
        }
        print(f"  D-76 {dev_t:g} min: R^2={fit.r_squared:.5f} max_residual={fit.max_residual:.4f}")

    density_curves = np.stack([dm.evaluate_total(fits[t], grids.LOG_EXPOSURE) for t in DEV_TIMES], axis=1)
    density_curves_layers = np.stack([dm.evaluate_layers(fits[t], grids.LOG_EXPOSURE) for t in DEV_TIMES], axis=2)
    base_density = np.tile(np.array([base_densities[t] for t in DEV_TIMES]), (81, 1))
    density_curves_model = {
        "model_type": "norm_cdfs",
        "centers": np.stack([fits[t].centers for t in DEV_TIMES], axis=0),
        "amplitudes": np.stack([fits[t].amplitudes for t in DEV_TIMES], axis=0),
        "sigmas": np.stack([fits[t].sigmas for t in DEV_TIMES], axis=0),
    }

    # --- Spectral sensitivity ("1.0 + D-min") --------------------------------
    spec_chart = _spectral_sensitivity_chart()
    spec_result = digitize_chart(spec_chart, PDF_PATH)
    _write_raw_and_qa(spec_chart, spec_result, OUT_DIR)

    sens_points = spec_result["curves"]["1.0+Dmin"]["points"]
    sens_x = np.array([p[0] for p in sens_points])
    sens_y = np.array([p[1] for p in sens_points])
    order = np.argsort(sens_x)
    sens_x, sens_y = sens_x[order], sens_y[order]
    log_sensitivity = np.interp(grids.WAVELENGTHS_NM, sens_x, sens_y)
    out_of_range = (grids.WAVELENGTHS_NM < sens_x.min()) | (grids.WAVELENGTHS_NM > sens_x.max())
    log_sensitivity[out_of_range] = np.nan

    # --- Cross-calibrate log_sensitivity's absolute scale (see exposure_calibration.py's
    #     own module docstring -- this is a real, confirmed, load-bearing fix, not a nicety:
    #     without it, this profile renders a normal scene pinned in the flat shoulder of the
    #     density curve regardless of print paper, since negative-type B&W film gets zero
    #     automatic exposure correction elsewhere in the pipeline). ------------------------
    log_sensitivity, sens_shift, grey_log_raw_before = ec.calibrate_negative_film_log_sensitivity(
        log_sensitivity, grids.WAVELENGTHS_NM,
    )
    print(f"  log_sensitivity calibration: grey landed at log_raw={grey_log_raw_before:.3f} "
          f"before, shifted by {sens_shift:+.3f} log10 units ({sens_shift/np.log10(2):+.2f} stops) "
          f"to reach target {ec.GREY_TARGET_LOG_RAW}")

    # --- Assemble + write both outputs ---------------------------------------
    info = sp.build_info(
        stock=STOCK, name="Kodak Tri-X Pan Film 400 (TX)", type_="negative",
        support="film", stage="filming", use="still", antihalation="strong",
        target_print="kodak_polymax_fine_art_grade2", channel_model="bw", densitometer="diffuse_visual",
        log_sensitivity_density_over_min=1.0, reference_illuminant="D55",
        viewing_illuminant="D50",
    )

    source_profile = sp.build_source_profile(
        info=info, datasource=DATASOURCE,
        wavelengths=grids.WAVELENGTHS_NM, log_sensitivity=log_sensitivity,
        channel_density_value=1.0, log_exposure=grids.LOG_EXPOSURE,
        base_density=base_density, density_curves=density_curves,
        density_curves_layers=density_curves_layers,
        density_curves_model=density_curves_model, development_time=DEV_TIMES,
    )
    sp.validate_source_profile(sp._json_safe(source_profile), n_dev_expected=len(DEV_TIMES))
    sp.write_profile(OUT_DIR / "profile.spektrafilm.json", source_profile)

    pack_profile = sp.collapse_to_darktable_pack(source_profile)
    sp.validate_darktable_pack(pack_profile)
    sp.write_profile(OUT_DIR / "profile.darktable.json", pack_profile)

    fit_report["log_sensitivity_calibration"] = {
        "grey_log_raw_before": grey_log_raw_before, "shift_applied_log10": sens_shift,
        "shift_applied_stops": sens_shift / np.log10(2), "target_grey_log_raw": ec.GREY_TARGET_LOG_RAW,
    }
    (OUT_DIR / "qa" / "fit_report.json").write_text(
        __import__("json").dumps(sp._json_safe(fit_report), indent=2)
    )

    print(f"\nWrote {OUT_DIR / 'profile.spektrafilm.json'}")
    print(f"Wrote {OUT_DIR / 'profile.darktable.json'}")
    print("\nNOTE: exposure-axis calibration between the two source charts is an anchor "
          "convention, not an independently cross-verified absolute calibration -- see "
          "this module's own docstring.")
    return source_profile, pack_profile


if __name__ == "__main__":
    build()
