"""
Kodak Professional Polymax Fine-Art Paper (F Surface) -- a variable-contrast,
fiber-base black-and-white enlarging paper. Chosen as Tri-X 400's print
paper after pruning every color paper in papers/125pixcom/paper/kodak/ and
every B&W paper that's either a specialty product (sepia-tone, contact-print
speed, rapid-stabilization, laser-printer) or explicitly superseded by
Kodak's own datasheet (Polycontrast III RC points to Polymax II RC /
Polycontrast IV RC as its replacement). Also the same paper this project's
own generate_film_looks.py already pairs with Tri-X (the POLY dataset
feeding build_trix_cascade()).

Source: papers/125pixcom/paper/kodak/g24.pdf (Kodak G-24, June 2005), page 5
(index 4) "CURVES". Real page layout (confirmed by reading word positions
directly, NOT assumed from the panel titles' reading order): two columns --
left column has "characteristic_curve_filterset1" (grades #1/#3/#5, y~105-325)
stacked directly above "characteristic_curve_filterset2" (grades #0/#2/#4,
y~330-560); right column has "characteristic_curve_filterset3" (#-1 and "No
Filter", y~100-325) stacked above "Spectral-Sensitivity Curves" (y~330-560,
THREE density criteria D-min+0.3/+0.6/+1.6). All three characteristic-curve
panels share one real, fixed development condition (KODAK PROFESSIONAL
DEKTOL Developer 1:2, 90 sec, 20C/68F) -- filter grade, not development
time, is what varies between them.

Every curve here -- all 7 real POLYMAX grades (-1..5) plus the spectral
sensitivity trace -- is digitized fresh from the PDF via this project's own
digitizer_core.py/kodak_helpers.py pipeline in this file, with its own QA
overlay, the same standard every curve in kodak_trix400.py meets. (An
earlier version of this file reused already-digitized points for grade 2
from an earlier PoLUT corpus pass, consolidated-data/paper/kodak/
black-and-white/kodak_polymaxfineartpaper_2005.json -- confirmed, on
inspection, to be a real extraction rather than fabricated data, but
re-digitized from the source PDF directly anyway so every number in this
project's own output is independently verifiable in this project, not
inherited from a prior pass.)

Ships as SEVEN separate stocks (kodak_polymax_fine_art_grademinus1,
_grade0..grade5), one per real POLYMAX filter grade -- "no filter" (the
paper's baseline response before any contrast filter) is also real,
digitized, and QA'd here (see FILTERSET3_CURVES) but not shipped as an
eighth stock, since it isn't a real print-grade choice a photographer would
select. Each grade goes through the identical digitize -> fit -> assemble
pipeline. Real precedent for shipping process variants of one physical
stock as separate stock entries already exists in the pack
(kodak_portra_800 / _push1 / _push2). This is NOT a development_time family
(see point 2 below) -- there is no other way to expose "pick a grade" in
the current schema, so each grade is its own profile a user picks from the
paper dropdown directly, closer to how a real darkroom printer selects a
physical filter than morphing one fixed curve via `print_contrast` would be.

Every grade's own output folder is fully self-contained: alongside its own
characteristic-curve fit, it gets its own copy of whichever source panel's
raw digitization + QA overlay it came from, AND a copy of the spectral
sensitivity raw + QA overlay (digitized once -- see point 1 below -- then
copied into all 7 grade folders), so nothing in one grade's folder depends
on reaching into a sibling grade's folder to be understood or verified.

Two things that don't vary per grade:

1. Spectral sensitivity is digitized ONCE and reused across all 7 grades,
   not once per grade: a Polymax filter changes contrast by selectively
   exposing the paper's two built-in emulsion layers differently, it
   doesn't change the paper's own intrinsic spectral response, so there is
   exactly one real Spectral-Sensitivity curve for this whole product line.
   This datasheet's own three density criteria are D-min+0.3/+0.6/+1.6,
   none of which is the film convention's usual 1.0. Rather than force a
   mismatch, every grade declares log_sensitivity_density_over_min=0.6 and
   digitizes that curve specifically -- 0.6 is also the real ISO 6:1993
   standard paper-speed criterion (density 0.60 above base+fog), so it's
   the historically-correct choice for a print paper's own speed point, not
   just "the closest available option." reference_illuminant is TH-KG3 (a
   tungsten-halogen enlarger lamp SPD, the same convention every real paper
   profile in the pack already uses), not D55 -- paper is exposed by the
   enlarger, not daylight.

2. No genuine multi-grade "family" is built, for any grade. darktable's
   development_time mechanism (see spektra_profile.py's
   collapse_to_darktable_pack docstring) is real MINUTES OF DEVELOPMENT
   (print_development_min in spektrafilm.c, UI-labeled "development time",
   " min" suffix) -- but this paper's 7 curves all share one real, fixed
   development condition and differ by filter/contrast grade instead, a
   physically different variable with no dedicated field in the current
   schema. Stuffing grade numbers into development_time would mislabel them
   as minutes in darktable's own UI. development_time is set to [1.5] (90
   sec, the one real shared condition, in the minutes unit the schema
   actually expects) for every grade -- a real value, not a proxy for grade.

Unlike kodak_trix400.py, no exposure_calibration.py cross-calibration step
is needed here: the print stage's own midgray auto-normalization
(spektrafilm's printing.py::_compute_exposure_factor_midgray) cancels out a
paper's absolute log_sensitivity scale regardless of what it is -- that
correction is specifically why paper stocks don't need this, see
exposure_calibration.py's own module docstring for the full reasoning.
"""

import json
import shutil
import types
from pathlib import Path

import numpy as np

import canonical_grids as grids
import density_model as dm
import spektra_profile as sp
from digitizer_core import (
    ChartSpec, CurveSpec, digitize_chart, render_qa_overlay,
)
from kodak_helpers import overline_symmetric_calib

import fitz

PDF_PATH = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom/paper/kodak/g24.pdf")
HERE = Path(__file__).parent.parent
OUT_ROOT = HERE / "outputs" / "paper" / "bw" / "kodak"

PAGE_INDEX = 4  # printed page 5, "CURVES"
GRADES = ["grademinus1", "grade0", "grade1", "grade2", "grade3", "grade4", "grade5"]
DEVELOPMENT_TIME = [1.5]  # 90 sec, Dektol 1:2, 20C -- the one real shared condition
N_LAYERS = 3

DATASOURCE_TEMPLATE = (
    "Kodak G-24 'KODAK PROFESSIONAL Polymax Fine-Art Paper' datasheet, June 2005 "
    "(papers/125pixcom/paper/kodak/g24.pdf), page 5 'CURVES', {panel} panel. Digitized "
    "independently via this project's own tooling (fresh in this session, not reused from "
    "any prior corpus pass). Spectral-Sensitivity Curve ('D=0.6 above D-min' trace) shared "
    "across all 7 grades (see module docstring -- the paper's spectral response doesn't "
    "vary by filter grade)."
)

# --- Characteristic-curve panels -------------------------------------------------------
# Real page layout confirmed by reading word positions directly (see module docstring) --
# NOT the QA-overlay's own 2-column display grid, which is unrelated to real page position.
FILTERSET1_REGION = (54, 105, 320, 325)   # left column, top: grades #1, #3, #5
FILTERSET2_REGION = (54, 330, 320, 560)   # left column, bottom: grades #0, #2, #4
FILTERSET3_REGION = (339, 100, 604, 325)  # right column, top: #-1 and "No Filter"

# FILTERSET1_CURVES/FILTERSET2_CURVES: the grade names + what looked like clean,
# unambiguous single-token label regexes ("#1", "#3", ...). Kept only for GRADE_TO_PANEL
# and as a record of the first (WRONG) approach -- actual extraction for these two panels
# uses _digitize_panel_by_index() instead (see FILTERSET1_TRACE_GRADE_BY_INDEX's own
# comment for why: clean single-token labels don't save you if the 3 curves are too close
# together at the label's own position for either matching heuristic to discriminate).
FILTERSET1_CURVES = [("grade1", r"^#1$"), ("grade3", r"^#3$"), ("grade5", r"^#5$")]
FILTERSET2_CURVES = [("grade0", r"^#0$"), ("grade2", r"^#2$"), ("grade4", r"^#4$")]
# "#" and "-1" / "No" and "Filter" print as separate text tokens (unlike the clean single-token
# "#N" labels in filterset1/2), so label_regex can't match them -- use label_position_override
# (center of each label's own token span) instead, same escape hatch CurveSpec documents.
FILTERSET3_CURVES = [("grademinus1", (465.0, 218.0)), ("nofilter", (405.0, 236.5))]

PANELS = {
    "characteristic_curve_filterset1": (FILTERSET1_REGION, FILTERSET1_CURVES),
    "characteristic_curve_filterset2": (FILTERSET2_REGION, FILTERSET2_CURVES),
    "characteristic_curve_filterset3": (FILTERSET3_REGION, FILTERSET3_CURVES),
}
GRADE_TO_PANEL = {grade: panel_id for panel_id, (_, curves) in PANELS.items() for grade, _ in curves}


def _characteristic_curve_chart(panel_id):
    region, curve_specs = PANELS[panel_id]
    curves = []
    for name, label in curve_specs:
        if isinstance(label, str):
            curves.append(CurveSpec(name, label_regex=label))
        else:
            curves.append(CurveSpec(name, label_position_override=label))
    return ChartSpec(
        pdf=str(PDF_PATH), page_index=PAGE_INDEX, chart_id=panel_id,
        x_tick_regex=r"\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="reflection_density",
        curves=curves, film_id="_unused", region_bbox=region,
        extraction_method="vector_position", monotonic_direction="increasing",
        min_trace_points=10,  # clean panel, confirmed via extract_traces_in_region probe:
                               # exactly 3/3/2 real traces at this threshold, no small
                               # label-artifact fragments like kodak_trix400.py's D-76 panel
        metadata={"developer": "Dektol (1:2)", "process": "Tray, 90 sec, 20C (68F)",
                  "densitometry": "Reflection", "filter_set": panel_id},
    )


# ALL THREE characteristic-curve panels' automatic label-to-trace matching (both
# digitizer_core's rank-order AND fallback distance methods) turned out UNRELIABLE here --
# not just filterset1/filterset2. filterset1/filterset2's "#N ———" leader lines terminate
# in a region where the 3 curves sit within a few pixels of each other at every height/x
# tested near the labels (confirmed by direct probing at multiple test points -- differences
# well within extraction noise, and by rendering each panel's raw traces in distinct colors
# for direct visual inspection). filterset3 (grademinus1/"no filter") looked safer --
# its two curves ARE reliably separated at the labels' shared mean-x (~38px apart, a real
# signal, confirmed by direct computation) -- and shipped once on that basis, but was ALSO
# confirmed wrong (both swapped) by the user cross-checking against the real PDF. Take the
# lesson at full strength: a real, non-noise numeric separation between candidate traces is
# NOT sufficient to trust which one is which -- it only rules out one failure mode (ambiguous/
# noisy matching), not "confidently, precisely backwards" (e.g. a leader line the algorithm
# read as pointing to the wrong side, or a rank assumption that doesn't hold for this
# specific label pair). Each trace IS a clean, correctly extracted real curve in all three
# panels (excellent, non-degenerate norm_cdfs fits, R^2>0.999 every time, including for
# every earlier wrong assignment) -- only the label MATCH was wrong, every time. All three
# panels are now assigned by extract_traces_in_region's own return-order INDEX instead,
# corrected via direct manual inspection against the source PDF (2026-08-02, twice), with
# each mapping's point-count fingerprint asserted at digitize time so future drift (e.g. a
# region_bbox edit changing which vector objects get picked up) fails loudly instead of
# silently re-shuffling grades again. **If a future chart on this project ever needs
# automatic label matching again, treat any result -- however clean-looking, however
# numerically separated -- as a hypothesis to independently verify against the real PDF,
# not a conclusion.**
FILTERSET1_TRACE_GRADE_BY_INDEX = {0: "grade5", 1: "grade1", 2: "grade3"}
FILTERSET1_FINGERPRINT = {0: 142, 1: 200, 2: 262}  # n_raw_vertices per trace index
FILTERSET2_TRACE_GRADE_BY_INDEX = {0: "grade4", 1: "grade2", 2: "grade0"}
FILTERSET2_FINGERPRINT = {0: 156, 1: 222, 2: 314}
FILTERSET3_TRACE_GRADE_BY_INDEX = {0: "nofilter", 1: "grademinus1"}
FILTERSET3_FINGERPRINT = {0: 172, 1: 262}
INDEX_BASED_PANELS = {
    "characteristic_curve_filterset1": (FILTERSET1_TRACE_GRADE_BY_INDEX, FILTERSET1_FINGERPRINT),
    "characteristic_curve_filterset2": (FILTERSET2_TRACE_GRADE_BY_INDEX, FILTERSET2_FINGERPRINT),
    "characteristic_curve_filterset3": (FILTERSET3_TRACE_GRADE_BY_INDEX, FILTERSET3_FINGERPRINT),
}


def _digitize_panel_by_index(panel_id):
    from digitizer_core import (
        bin_average, extract_traces_in_region, fit_axis, isotonic_regression,
        simplify_to_target, _dedupe_exact_traces,
    )
    region, _ = PANELS[panel_id]
    trace_grade_by_index, fingerprint = INDEX_BASED_PANELS[panel_id]

    doc = fitz.open(PDF_PATH)
    page = doc[PAGE_INDEX]
    words = page.get_text("words")
    xs, xi, x_ticks = fit_axis(words, r"\d\.0", "x", bbox=region)
    ys, yi, y_ticks = fit_axis(words, r"\d\.0", "y", bbox=region)

    traces = extract_traces_in_region(page, region, min_points=10)
    traces = _dedupe_exact_traces(traces)
    doc.close()

    actual_fingerprint = {i: len(tr) for i, tr in enumerate(traces)}
    assert actual_fingerprint == fingerprint, (
        f"{panel_id}: trace point-counts {actual_fingerprint} no longer match the manually-"
        f"verified fingerprint {fingerprint} -- re-verify the index->grade mapping against "
        f"the source PDF before trusting it, don't assume the old mapping still applies"
    )

    curves = {}
    for i, tr in enumerate(traces):
        name = trace_grade_by_index[i]
        pxs, pys = zip(*tr)
        data_x = [xs * p + xi for p in pxs]
        data_y = [ys * p + yi for p in pys]
        bx, by = bin_average(data_x, data_y, 400)
        by = np.array(isotonic_regression(by, increasing=True))
        simplified = simplify_to_target(bx, by)
        sx = [round(float(x), 4) for x, y in simplified]
        sy = [round(float(y), 4) for x, y in simplified]
        curves[name] = {
            "points": list(zip(sx, sy)),
            "points_dense": [[round(float(x), 4), round(float(y), 4)] for x, y in zip(bx, by)],
            "n_raw_vertices": len(tr), "n_violations": 0, "likely_direction": "increasing",
            "_px": (pxs, pys),
        }

    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=PAGE_INDEX, chart_id=panel_id,
        x_tick_regex=r"\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="reflection_density",
        curves=[CurveSpec(n) for n in trace_grade_by_index.values()],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        metadata={"developer": "Dektol (1:2)", "process": "Tray, 90 sec, 20C (68F)",
                  "densitometry": "Reflection", "filter_set": panel_id,
                  "note": "grade<->trace assignment is manually verified by index, not "
                          "automatic label matching -- see FILTERSET*_TRACE_GRADE_BY_INDEX"},
    )
    return chart, {
        "source_pdf": chart.pdf, "page_index": chart.page_index, "chart_id": chart.chart_id,
        "x_label": chart.x_label, "y_label": chart.y_label,
        "curves": {k: {kk: vv for kk, vv in v.items() if kk not in ("_px",)} for k, v in curves.items()},
        "_qa_results": curves, "_qa_calib": (xs, xi, ys, yi),
    }


_CHARACTERISTIC_CURVE_CACHE = {}


def _get_panel_result(panel_id):
    if panel_id not in _CHARACTERISTIC_CURVE_CACHE:
        if panel_id in INDEX_BASED_PANELS:
            chart, result = _digitize_panel_by_index(panel_id)
        else:
            chart = _characteristic_curve_chart(panel_id)
            result = digitize_chart(chart, PDF_PATH)
        _CHARACTERISTIC_CURVE_CACHE[panel_id] = (chart, result)
    return _CHARACTERISTIC_CURVE_CACHE[panel_id]


def _write_panel_raw_and_qa(panel_id, out_dir):
    """Writes (or, if already written for this panel, copies) this panel's raw JSON + QA
    overlay into out_dir/raw and out_dir/qa -- every grade folder that draws from this
    panel gets its own copy (see module docstring)."""
    chart, result = _get_panel_result(panel_id)
    raw_path = out_dir / "raw" / f"{panel_id}.json"
    qa_path = out_dir / "qa" / f"{panel_id}_qa_overlay.png"

    doc = fitz.open(PDF_PATH)
    render_qa_overlay([(chart, result["_qa_results"], result["_qa_calib"], doc[chart.page_index])], qa_path)
    doc.close()

    raw_out = dict(result)
    raw_out["qa_overlay_png"] = qa_path.name
    for k in ("_qa_results", "_qa_calib", "_qa_page_number"):
        raw_out.pop(k, None)
    raw_path.write_text(json.dumps(raw_out, indent=2))


# --- Spectral sensitivity (shared across all 7 grades) ---------------------------------
SPECTRAL_SENSITIVITY_REGION = (339, 342, 604, 560)
SPECTRAL_SENSITIVITY_MIN_TRACE_POINTS = 150
SPECTRAL_SENSITIVITY_RANK_X_PAGE = 450.0
SPECTRAL_SENSITIVITY_NAMES_BY_LOG_SENS_DESC = ["D0.3+Dmin", "D0.6+Dmin", "D1.6+Dmin"]


def _digitize_spectral_sensitivity_by_rank():
    from digitizer_core import (
        bin_average, extract_traces_in_region, simplify_to_target,
        _dedupe_exact_traces, _interpolated_y_at_x, fit_axis,
    )
    doc = fitz.open(PDF_PATH)
    page = doc[PAGE_INDEX]
    words = page.get_text("words")
    xs, xi, x_ticks = fit_axis(words, r"\d{3}", "x", bbox=SPECTRAL_SENSITIVITY_REGION)
    ys, yi = overline_symmetric_calib(PDF_PATH, PAGE_INDEX, SPECTRAL_SENSITIVITY_REGION, tick_regex=r"\d\.0")

    traces = extract_traces_in_region(page, SPECTRAL_SENSITIVITY_REGION,
                                       SPECTRAL_SENSITIVITY_MIN_TRACE_POINTS)
    traces = _dedupe_exact_traces(traces)
    doc.close()
    if len(traces) != 3:
        raise RuntimeError(f"expected 3 real spectral-sensitivity traces, got {len(traces)}")

    keyed = [(_interpolated_y_at_x(tr, SPECTRAL_SENSITIVITY_RANK_X_PAGE), tr) for tr in traces]
    if any(y is None for y, _ in keyed):
        raise RuntimeError(f"rank_x_page={SPECTRAL_SENSITIVITY_RANK_X_PAGE} falls outside a trace's span")
    keyed.sort(key=lambda t: t[0])  # ascending page-y = descending log sensitivity (see docstring)

    curves = {}
    for name, (_, raw) in zip(SPECTRAL_SENSITIVITY_NAMES_BY_LOG_SENS_DESC, keyed):
        pxs, pys = zip(*raw)
        data_x = [xs * p + xi for p in pxs]
        data_y = [ys * p + yi for p in pys]
        bx, by = bin_average(data_x, data_y, 400)
        simplified = simplify_to_target(bx, by)
        sx = [round(float(x), 4) for x, y in simplified]
        sy = [round(float(y), 4) for x, y in simplified]
        curves[name] = {
            "points": list(zip(sx, sy)),
            "points_dense": [[round(float(x), 4), round(float(y), 4)] for x, y in zip(bx, by)],
            "n_raw_vertices": len(raw), "n_violations": 0, "likely_direction": "n/a (real peak shape)",
            "_px": (pxs, pys),
        }

    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=PAGE_INDEX, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec(n) for n in SPECTRAL_SENSITIVITY_NAMES_BY_LOG_SENS_DESC],
        film_id="_unused", region_bbox=SPECTRAL_SENSITIVITY_REGION,
        extraction_method="vector_position",
        metadata={"developer": "Dektol (1:2)", "process": "Tray, 90 sec, 20C (68F)",
                  "densitometry": "Diffuse visual", "exposure": "2 seconds"},
    )
    return chart, {
        "source_pdf": chart.pdf, "page_index": chart.page_index, "chart_id": chart.chart_id,
        "x_label": chart.x_label, "y_label": chart.y_label,
        "curves": {k: {kk: vv for kk, vv in v.items() if kk not in ("_px",)} for k, v in curves.items()},
        "_qa_results": curves, "_qa_calib": (xs, xi, ys, yi),
    }


_SPECTRAL_SENSITIVITY_CACHE = None


def _get_spectral_sensitivity():
    """Memoized -- digitized once (real PDF extraction), reused/copied across all 7 grade
    builds instead of re-extracting the same chart 7 times."""
    global _SPECTRAL_SENSITIVITY_CACHE
    if _SPECTRAL_SENSITIVITY_CACHE is None:
        _SPECTRAL_SENSITIVITY_CACHE = _digitize_spectral_sensitivity_by_rank()
    return _SPECTRAL_SENSITIVITY_CACHE


def _write_spectral_sensitivity_raw_and_qa(out_dir):
    spec_chart, spec_result = _get_spectral_sensitivity()
    qa_path = out_dir / "qa" / "spectral_sensitivity_qa_overlay.png"
    doc = fitz.open(PDF_PATH)
    render_qa_overlay([(spec_chart, spec_result["_qa_results"], spec_result["_qa_calib"],
                         doc[spec_chart.page_index])], qa_path)
    doc.close()
    raw_out = dict(spec_result)
    raw_out["qa_overlay_png"] = qa_path.name
    for k in ("_qa_results", "_qa_calib"):
        raw_out.pop(k, None)
    (out_dir / "raw" / "spectral_sensitivity.json").write_text(json.dumps(raw_out, indent=2))
    return spec_result


def _speed_point_x(points, base_density, criterion):
    xs = np.array([p[0] for p in points])
    ys = np.array([p[1] for p in points])
    order = np.argsort(ys)
    return float(np.interp(base_density + criterion, ys[order], xs[order]))


def out_dir(grade):
    return OUT_ROOT / f"kodak_polymax_fine_art_{grade}"


def build_grade(grade):
    OUT_DIR = out_dir(grade)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "raw").mkdir(exist_ok=True)
    (OUT_DIR / "qa").mkdir(exist_ok=True)

    panel_id = GRADE_TO_PANEL[grade]
    _write_panel_raw_and_qa(panel_id, OUT_DIR)
    _, panel_result = _get_panel_result(panel_id)
    points = panel_result["curves"][grade]["points"]

    # --- Characteristic curve fit ---------------------------------------------
    base_density = min(y for _, y in points)
    x_speed = _speed_point_x(points, base_density, criterion=0.6)
    shift = -x_speed

    xs = np.array([p[0] for p in points]) + shift
    # Fit NET density (above base) -- see kodak_trix400.py's comment / density_model.py's
    # own module docstring: compute_density_spectral() adds base_density back separately.
    ys = np.array([p[1] for p in points]) - base_density
    fit = dm.fit_norm_cdfs(xs, ys, n_layers=N_LAYERS)
    dm.plot_fit_qa(xs, ys, fit, grids.LOG_EXPOSURE,
                    title=f"Kodak Polymax Fine-Art Paper, {grade} (Dektol 1:2, 90s, net density)",
                    out_path=OUT_DIR / "qa" / f"density_fit_{grade}.png")
    print(f"  {grade} ({panel_id}): R^2={fit.r_squared:.5f} max_residual={fit.max_residual:.4f}")

    fit_report = {
        "exposure_anchor": {"grade": grade, "panel": panel_id,
                             "x_speed_kodak_chart": x_speed, "applied_shift": shift},
        "note": "no development_time family -- see module docstring; density_over_min=0.6 "
                "(ISO 6:1993 paper speed criterion), not the 1.0 film convention",
        "curves": {
            grade: {
                "r_squared": fit.r_squared, "max_residual": fit.max_residual,
                "base_density": base_density,
                "centers": fit.centers.tolist(), "amplitudes": fit.amplitudes.tolist(),
                "sigmas": fit.sigmas.tolist(),
            }
        },
    }

    density_curves = dm.evaluate_total(fit, grids.LOG_EXPOSURE).reshape(-1, 1)
    density_curves_layers = dm.evaluate_layers(fit, grids.LOG_EXPOSURE)[:, :, None]
    base_density_arr = np.full((81, 1), base_density)
    density_curves_model = {
        "model_type": "norm_cdfs",
        "centers": fit.centers.reshape(1, -1),
        "amplitudes": fit.amplitudes.reshape(1, -1),
        "sigmas": fit.sigmas.reshape(1, -1),
    }

    # --- Spectral sensitivity: shared, copied into this grade's own folder -----
    spec_result = _write_spectral_sensitivity_raw_and_qa(OUT_DIR)
    sens_points = spec_result["curves"]["D0.6+Dmin"]["points"]
    sens_x = np.array([p[0] for p in sens_points])
    sens_y = np.array([p[1] for p in sens_points])
    order = np.argsort(sens_x)
    sens_x, sens_y = sens_x[order], sens_y[order]
    log_sensitivity = np.interp(grids.WAVELENGTHS_NM, sens_x, sens_y)
    out_of_range = (grids.WAVELENGTHS_NM < sens_x.min()) | (grids.WAVELENGTHS_NM > sens_x.max())
    log_sensitivity[out_of_range] = np.nan

    # --- Assemble + write both outputs -----------------------------------------
    stock = f"kodak_polymax_fine_art_{grade}"
    grade_label = grade.replace("grademinus1", "-1").replace("grade", "")
    info = sp.build_info(
        stock=stock, name=f"Kodak Professional Polymax Fine-Art Paper (Grade {grade_label})",
        type_="negative", support="paper", stage="printing", use="still", antihalation="strong",
        target_print=None, channel_model="bw", densitometer="diffuse_visual",
        log_sensitivity_density_over_min=0.6, reference_illuminant="TH-KG3",
        viewing_illuminant="D50",
    )

    source_profile = sp.build_source_profile(
        info=info, datasource=DATASOURCE_TEMPLATE.format(panel=panel_id),
        wavelengths=grids.WAVELENGTHS_NM, log_sensitivity=log_sensitivity,
        channel_density_value=1.0, log_exposure=grids.LOG_EXPOSURE,
        base_density=base_density_arr, density_curves=density_curves,
        density_curves_layers=density_curves_layers,
        density_curves_model=density_curves_model, development_time=DEVELOPMENT_TIME,
    )
    sp.validate_source_profile(sp._json_safe(source_profile), n_dev_expected=1)
    sp.write_profile(OUT_DIR / "profile.spektrafilm.json", source_profile)

    pack_profile = sp.collapse_to_darktable_pack(source_profile)
    sp.validate_darktable_pack(pack_profile)
    sp.write_profile(OUT_DIR / "profile.darktable.json", pack_profile)

    (OUT_DIR / "qa" / "fit_report.json").write_text(json.dumps(sp._json_safe(fit_report), indent=2))

    print(f"  Wrote {OUT_DIR / 'profile.spektrafilm.json'}")
    print(f"  Wrote {OUT_DIR / 'profile.darktable.json'}")
    return source_profile, pack_profile


def _make_entry(grade):
    return types.SimpleNamespace(build=lambda: build_grade(grade), OUT_DIR=out_dir(grade))


# main.py's PRODUCTS-dict interface: {stock_slug: <object with .build() and .OUT_DIR>}.
# Merged into main.py's own PRODUCTS dict rather than one module = one stock, since these
# 7 stocks are close enough variants (same source panels, same spectral sensitivity data,
# same pipeline) to share one file without meaningfully hurting readability -- see module
# docstring for why this is a family of stocks, not a single one with a variant axis.
PRODUCTS = {f"kodak_polymax_fine_art_{grade}": _make_entry(grade) for grade in GRADES}


if __name__ == "__main__":
    for grade in GRADES:
        print(f"=== kodak_polymax_fine_art_{grade} ===")
        build_grade(grade)
