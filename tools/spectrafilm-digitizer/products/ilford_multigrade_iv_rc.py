"""
Ilford Multigrade IV RC (DeLuxe / Portfolio), a premium quality variable-
contrast resin-coated black-and-white enlarging paper -- the new default
target print paper for every Ilford B&W film built by this project (HP5
Plus, Delta 100 so far -- see main.py), replacing the cross-brand
kodak_polymax_fine_art_grade2 placeholder both films shipped with until now
(no same-brand Ilford paper existed in this schema before this file).

Source: papers/125pixcom/paper/ilford/Multigrade IV RC.pdf (Ilford Fact
Sheet, December 2001). Page 0 has "Spectral sensitivity" (Equal energy,
wedge spectrogram, curves at density 0.5/1.0/1.5) -- digitized ONCE and
shared across all 7 grades, same reasoning as kodak_polymax_fine_art.py
point 1 (a contrast filter changes exposure balance between the paper's two
built-in emulsions, it doesn't change the paper's own intrinsic spectral
response). Page 1 has "Characteristic curves": TWO panels, not one --
grades 00/0/1/2/3 (5 curves, tightly bunched) on the first, grades 4/5 (2
curves) on the second. Caption: "MULTIGRADE IV RC glossy or pearl paper
exposed through filters 00, 0, 1, 2, 3, 4 and 5. Developer: MULTIGRADE
diluted 1+9. Development: 1 minute at 20C/68F" -- one real, fixed
development condition shared by every grade (development_time=[1.0]), same
"grades vary by filter, not by development time" situation as
kodak_polymax_fine_art.py point 2, not a real family for
collapse_to_darktable_pack() to flatten.

Ships as SEVEN separate stocks (ilford_multigrade_iv_rc_grade00,
_grade0..._grade5) -- the page's own ISO-range/paper-speed tables list
exactly these seven ("Filter 00 0 1 2 3 4 5"), the 7 FULL grades of the 12
real MULTIGRADE filters (the other 5 are half-grade steps with no charted
curve of their own, same "ship what's actually charted" choice Polymax made
for its own 7 grades).

CLAUDE.md's "Digitizing a variable-contrast paper whose grade curves
visually braid together" documents the two reusable digitizer_core.py
mechanisms this file leans on (OCR axis calibration + rank-by-x curve
identity) -- read that first if a THIRD Multigrade-family sheet (Warmtone
RC / Cooltone RC, both already in papers/125pixcom/paper/ilford/, both
still unbuilt in THIS schema) or any other visually-braided multi-curve
paper chart shows up. tools/curve_digitizer/ilford_paper.py (a sibling
tool, different output format -- feeds generate_film_looks.py's .cube
pipeline, not darktable's spektrafilm module) solved the identical PDF the
identical way first, 2026-07-06 -- the TECHNIQUE transfers directly (same
region boxes, same rank_at_y values, cross-checked fresh against this
session's own QA overlay rather than assumed correct), the DIGITIZED POINTS
don't: re-digitized fresh here, independently, per this project's own
standard (see kodak_polymax_fine_art.py's own module docstring for why
reuse-across-projects isn't good enough even when the earlier extraction is
real and already QA'd).

Both real problems solved, briefly (full physical/verification reasoning
lives in CLAUDE.md, not repeated here):
1. Axis ticks on both characteristic-curve panels are vector-drawn shapes
   with zero real text -- OCR via ocr_axis_calib (same as Ilford HP5
   Plus's spectral-sensitivity chart).
2. Each panel's grade-number labels sit right where every curve in that
   panel is closest together (a shared near-Dmax shoulder plateau) --
   `assign_traces_by_x_rank(rank_at_y=...)` ranks each extracted trace by
   its own interpolated x at a fixed y sitting in the steep, well-separated
   part of the curves instead of trusting label position at all. Ilford
   also draws every curve in one panel as ONE continuous PDF path,
   pen-jumping (not lifting) from one curve's toe back to the next curve's
   shoulder -- `extract_traces_in_region(..., split_on_x_reversal=True)`
   splits on that jump.

Verified against the QA overlay before shipping (2026-08-03): both panels'
rank order runs 3/2/1/0/00 and 5/4 left-to-right, exactly matching the
printed labels, at every zoom level checked including the tangled
toe-crossing region around density~1.0-1.3 where the human eye alone can't
tell the five curves apart.

Spectral-sensitivity curve labels ("0.5"/"1.0"/"1.5"), unlike the
characteristic-curve grade labels, ARE real upright vector text sitting
right next to their own curve -- but the chart's own y-axis also has a real
"1.0" tick text label elsewhere in the same region, which a plain
label_regex search could match instead of the curve label (find_label_
position returns the first words-list match, not necessarily the nearest
one). label_position_override (exact centers, probed directly from the
page's own word list) sidesteps the ambiguity entirely rather than trying
to out-clever it with a tighter regex.
"""

import json
import types
from pathlib import Path

import numpy as np

import canonical_grids as grids
import density_model as dm
import spektra_profile as sp
import stock_io
from digitizer_core import ChartSpec, CurveSpec, digitize_chart, render_qa_overlay
from ocr_helpers import ocr_axis_calib

import fitz

PDF_PATH = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom/paper/ilford/Multigrade IV RC.pdf")
HERE = Path(__file__).parent.parent
OUT_ROOT = HERE / "outputs" / "paper" / "bw" / "ilford"

GRADES = ["grade00", "grade0", "grade1", "grade2", "grade3", "grade4", "grade5"]
DEVELOPMENT_TIME = [1.0]  # 1 min, MULTIGRADE developer 1+9, 20C/68F -- the one real shared condition
N_LAYERS = 3

DATASOURCE_TEMPLATE = (
    "Ilford 'MULTIGRADE IV RC' Fact Sheet, December 2001 "
    "(papers/125pixcom/paper/ilford/Multigrade IV RC.pdf), page 2 'Characteristic curves', "
    "{panel} panel (OCR-calibrated axes -- vector-drawn tick shapes, no real tick text; curve "
    "identity via digitizer_core.assign_traces_by_x_rank -- see module docstring) and page 1 "
    "'Spectral sensitivity' (Equal energy, real vector text throughout, shared across all 7 "
    "grades). Digitized independently via this project's own tooling (fresh in this session, "
    "not reused from tools/curve_digitizer's earlier pass at the same PDF)."
)

# --- Characteristic-curve panels (page index 1) -----------------------------------------
# Region/tick-bbox/rank_y values cross-checked fresh against this session's own QA overlay
# (see module docstring) -- not blindly copied from tools/curve_digitizer/ilford_paper.py,
# even though they land on the same real panel geometry (one real PDF, one real layout).
CHAR_PAGE_INDEX = 1
PANEL1_REGION = (370, 338, 500, 430)      # grades 3, 2, 1, 0, 00
PANEL1_X_TICK_BBOX = (310, 428, 490, 445)
PANEL1_Y_TICK_BBOX = (500, 320, 535, 410)
PANEL1_RANK_Y = 350.0                     # page-space y, in the steep/well-separated region
PANEL1_NAMES = ["grade3", "grade2", "grade1", "grade0", "grade00"]  # ascending max-x order

PANEL2_REGION = (390, 485, 495, 575)      # grades 5, 4
PANEL2_X_TICK_BBOX = (325, 573, 490, 586)
PANEL2_Y_TICK_BBOX = (498, 478, 520, 533)
PANEL2_RANK_Y = 530.0
PANEL2_NAMES = ["grade5", "grade4"]

PANEL1_ID = "characteristic_curve_grades_00_to_3"
PANEL2_ID = "characteristic_curve_grades_4_5"
GRADE_TO_PANEL = {**{g: PANEL1_ID for g in PANEL1_NAMES}, **{g: PANEL2_ID for g in PANEL2_NAMES}}


def _characteristic_curve_chart(panel_id):
    if panel_id == PANEL1_ID:
        region, x_tick_bbox, y_tick_bbox, rank_y, names = (
            PANEL1_REGION, PANEL1_X_TICK_BBOX, PANEL1_Y_TICK_BBOX, PANEL1_RANK_Y, PANEL1_NAMES)
    else:
        region, x_tick_bbox, y_tick_bbox, rank_y, names = (
            PANEL2_REGION, PANEL2_X_TICK_BBOX, PANEL2_Y_TICK_BBOX, PANEL2_RANK_Y, PANEL2_NAMES)

    doc = fitz.open(PDF_PATH)
    page = doc[CHAR_PAGE_INDEX]
    x_calib = ocr_axis_calib(page, x_tick_bbox, tick_regex=r"\d", axis="x")
    y_calib = ocr_axis_calib(page, y_tick_bbox, tick_regex=r"\d\.\d", axis="y")
    doc.close()

    return ChartSpec(
        pdf=str(PDF_PATH), page_index=CHAR_PAGE_INDEX, chart_id=panel_id,
        x_tick_regex=r"\d", y_tick_regex=r"\d\.\d",
        x_label="relative_log_exposure", y_label="density",
        curves=[CurveSpec(n, qa_source="points_dense") for n in names],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction="increasing", min_trace_points=6,
        split_on_x_reversal=True, reversal_run_length=5,
        rank_assignment_names=names, rank_at_y=rank_y,
        x_axis_calib_override=x_calib, y_axis_calib_override=y_calib,
        metadata={"developer": "MULTIGRADE (1+9)", "process": "Tray, 1 min, 20C (68F)",
                  "densitometry": "Reflection", "panel": panel_id},
    )


_CHARACTERISTIC_CURVE_CACHE = {}


def _get_panel_result(panel_id):
    if panel_id not in _CHARACTERISTIC_CURVE_CACHE:
        chart = _characteristic_curve_chart(panel_id)
        result = digitize_chart(chart, PDF_PATH)
        _CHARACTERISTIC_CURVE_CACHE[panel_id] = (chart, result)
    return _CHARACTERISTIC_CURVE_CACHE[panel_id]


def _write_panel_raw_and_qa(panel_id, out_dir):
    """Writes (or, if already written for this panel, copies) this panel's raw JSON + QA
    overlay into out_dir/raw and out_dir/qa -- every grade folder that draws from this panel
    gets its own copy, same convention as kodak_polymax_fine_art.py."""
    chart, result = _get_panel_result(panel_id)
    raw_path = out_dir / "raw" / f"{panel_id}.json"
    qa_path = out_dir / "qa" / f"{panel_id}_qa_overlay.png"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    qa_path.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(PDF_PATH)
    render_qa_overlay([(chart, result["_qa_results"], result["_qa_calib"], doc[chart.page_index])], qa_path)
    doc.close()

    raw_out = dict(result)
    raw_out["qa_overlay_png"] = qa_path.name
    for k in ("_qa_results", "_qa_calib", "_qa_page_number"):
        raw_out.pop(k, None)
    raw_path.write_text(json.dumps(raw_out, indent=2))


# --- Spectral sensitivity (page index 0, shared across all 7 grades) --------------------
SPECTRAL_PAGE_INDEX = 0
SPECTRAL_REGION = (300, 601, 530, 754)
SPECTRAL_X_TICK_BBOX = (310, 738, 500, 756)
SPECTRAL_Y_TICK_BBOX = (498, 625, 530, 715)
# Real, upright vector text sits right next to each curve (unlike the characteristic-curve
# panels above) -- but a real Y-AXIS "1.0" tick lives elsewhere in the same region, so
# label_position_override (exact centers, probed directly from page.get_text("words")) is
# used instead of label_regex; see module docstring.
SPECTRAL_CURVES = [
    ("d0_5", (451.4, 626.8)),
    ("d1_0", (451.4, 641.8)),
    ("d1_5", (451.4, 662.0)),
]
# Multigrade's sheet doesn't publish a spectral-sensitivity curve at the real ISO 6846 0.60
# paper-speed criterion (see stock_io.PAPER_SPEED_CRITERION) -- only 0.5/1.0/1.5. 1.0 is picked
# here as the closest available digitized curve; this is just documentation of which
# log_sensitivity shape was used and doesn't need to match the characteristic-curve exposure
# anchor below (stock_io.paper_speed_point_x(), the real 0.6 criterion) -- a paper's absolute
# log_sensitivity scale cancels out of the print render regardless of value (see
# stock_io.PAPER_SPEED_CRITERION's own comment), so this criterion choice has no rendering
# consequence, unlike the exposure anchor's.
SPECTRAL_DENSITY_CRITERION = "d1_0"


def _spectral_sensitivity_chart():
    return ChartSpec(
        pdf=str(PDF_PATH), page_index=SPECTRAL_PAGE_INDEX, chart_id="spectral_sensitivity",
        x_tick_regex=r"^\d{3}$", y_tick_regex=r"^[123]\.0$",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec(n, label_position_override=pos,
                           qa_source="points_dense" if n == SPECTRAL_DENSITY_CRITERION else "points")
                for n, pos in SPECTRAL_CURVES],
        film_id="_unused", region_bbox=SPECTRAL_REGION,
        x_tick_bbox=SPECTRAL_X_TICK_BBOX, y_tick_bbox=SPECTRAL_Y_TICK_BBOX,
        extraction_method="vector_position", monotonic_direction=None, min_trace_points=10,
        metadata={"illuminant": "Equal energy (wedge spectrogram)", "density_criteria": "0.5/1.0/1.5"},
    )


_SPECTRAL_SENSITIVITY_CACHE = None


def _get_spectral_sensitivity():
    """Memoized -- digitized once (real PDF extraction), reused/copied across all 7 grade
    builds instead of re-extracting the same chart 7 times."""
    global _SPECTRAL_SENSITIVITY_CACHE
    if _SPECTRAL_SENSITIVITY_CACHE is None:
        chart = _spectral_sensitivity_chart()
        result = digitize_chart(chart, PDF_PATH)
        _SPECTRAL_SENSITIVITY_CACHE = (chart, result)
    return _SPECTRAL_SENSITIVITY_CACHE


def _write_spectral_sensitivity_raw_and_qa(out_dir):
    chart, result = _get_spectral_sensitivity()
    qa_path = out_dir / "qa" / "spectral_sensitivity_qa_overlay.png"
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)
    doc = fitz.open(PDF_PATH)
    render_qa_overlay([(chart, result["_qa_results"], result["_qa_calib"], doc[chart.page_index])], qa_path)
    doc.close()
    raw_out = dict(result)
    raw_out["qa_overlay_png"] = qa_path.name
    for k in ("_qa_results", "_qa_calib"):
        raw_out.pop(k, None)
    (out_dir / "raw" / "spectral_sensitivity.json").write_text(json.dumps(raw_out, indent=2))
    return result


def out_dir(grade):
    return OUT_ROOT / f"ilford_multigrade_iv_rc_{grade}"


def build_grade(grade):
    OUT_DIR = out_dir(grade)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "raw").mkdir(exist_ok=True)
    (OUT_DIR / "qa").mkdir(exist_ok=True)

    panel_id = GRADE_TO_PANEL[grade]
    _write_panel_raw_and_qa(panel_id, OUT_DIR)
    _, panel_result = _get_panel_result(panel_id)
    # points_dense, not points -- see SIMPLIFY_TOLERANCE's comment in
    # digitizer_core.py: fitting/interpolation draws from the fullest-fidelity
    # real data, not the RDP-reduced QA/compactness set.
    points = panel_result["curves"][grade]["points_dense"]

    # --- Characteristic curve fit ---------------------------------------------
    base_density = min(y for _, y in points)
    x_speed = stock_io.paper_speed_point_x(points, base_density)
    shift = -x_speed

    xs = np.array([p[0] for p in points]) + shift
    # Fit NET density (above base) -- density_model.py's own module docstring:
    # compute_density_spectral() adds base_density back separately downstream.
    ys = np.array([p[1] for p in points]) - base_density
    fit = dm.fit_norm_cdfs(xs, ys, n_layers=N_LAYERS)
    print(f"  {grade} ({panel_id}): R^2={fit.r_squared:.5f} max_residual={fit.max_residual:.4f}")

    fit_report = {
        "exposure_anchor": {"grade": grade, "panel": panel_id,
                             "x_speed_criterion_0.6": x_speed, "applied_shift": shift},
        "note": "no development_time family -- see module docstring; characteristic-curve "
                "exposure anchor uses stock_io.PAPER_SPEED_CRITERION=0.6 (ISO 6846:1992 / "
                "ANSI PH2.2-1972 real paper-speed criterion, interpolated from the digitized "
                "curve directly -- Multigrade's own sheet only tabulates 0.5/1.0/1.5, but the "
                "full digitized curve isn't limited to those three points). "
                "log_sensitivity_density_over_min=1.0 is a separate, decoupled choice -- see "
                "SPECTRAL_DENSITY_CRITERION's own comment.",
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
    # points_dense (400pt bin-averaged), not points (RDP-simplified) -- this
    # curve gets linearly resampled straight onto the 5nm output grid below,
    # so it needs the dense curve's much finer spacing to avoid chord-cutting
    # through real peaks/troughs; the RDP-reduced set is for QA/compactness,
    # not for being the actual resampling source. See digitizer_core.py's
    # SIMPLIFY_TOLERANCE comment.
    sens_points = spec_result["curves"][SPECTRAL_DENSITY_CRITERION]["points_dense"]
    sens_x = np.array([p[0] for p in sens_points])
    sens_y = np.array([p[1] for p in sens_points])
    order = np.argsort(sens_x)
    sens_x, sens_y = sens_x[order], sens_y[order]
    log_sensitivity = np.interp(grids.WAVELENGTHS_NM, sens_x, sens_y)
    out_of_range = (grids.WAVELENGTHS_NM < sens_x.min()) | (grids.WAVELENGTHS_NM > sens_x.max())
    log_sensitivity[out_of_range] = np.nan

    # --- Assemble + write both outputs -----------------------------------------
    stock = f"ilford_multigrade_iv_rc_{grade}"
    grade_label = grade.replace("grade", "")
    info = sp.build_info(
        stock=stock, name=f"Ilford Multigrade IV RC (Grade {grade_label})",
        type_="negative", support="paper", stage="printing", use="still", antihalation="strong",
        target_print=None, channel_model="bw", densitometer="diffuse_visual",
        log_sensitivity_density_over_min=1.0, reference_illuminant="TH-KG3",
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

    pack_profile = sp.collapse_to_darktable_pack(source_profile)
    sp.validate_darktable_pack(pack_profile)
    sp.write_profile(OUT_DIR / "profile.json", pack_profile)

    (OUT_DIR / "qa" / "fit_report.json").write_text(json.dumps(sp._json_safe(fit_report), indent=2))

    print(f"  Wrote {OUT_DIR / 'profile.json'}")
    return source_profile, pack_profile


def _make_entry(grade):
    return types.SimpleNamespace(build=lambda: build_grade(grade), OUT_DIR=out_dir(grade))


# main.py's PRODUCTS-dict interface: {stock_slug: <object with .build() and .OUT_DIR>}.
# Merged into main.py's own PRODUCTS dict, same shape as kodak_polymax_fine_art.PRODUCTS.
PRODUCTS = {f"ilford_multigrade_iv_rc_{grade}": _make_entry(grade) for grade in GRADES}


if __name__ == "__main__":
    for grade in GRADES:
        print(f"=== ilford_multigrade_iv_rc_{grade} ===")
        build_grade(grade)
