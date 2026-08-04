"""
Digitizes Kodak reversal (slide) film datasheets (film/kodak/*.pdf,
Ektachrome/Kodachrome/Elite Chrome lines) into
consolidated-data/film/photography/reversal/kodak/.

Different neighbor-panel arrangement from the negative-film template
(kodak_still.py): "Characteristic Curves" sits above "Modulation-Transfer
Curves"/"Diffuse rms Granularity" here, with "Spectral-Sensitivity"/
"Spectral-Dye-Density" as the other column, not diagonal to Characteristic
the way the negative template lays them out -- still Strategy D
(vector_position), still B/G/R inline labels on Characteristic. Both
Spectral-Sensitivity and Spectral-Dye-Density panels are real and present
on most of these sheets (confirmed 2026-07-10 -- an earlier version of this
docstring wrongly claimed they weren't). Spectral-Sensitivity is captured
via `spectral_sensitivity_chart_by_peak_x` (kodak_common.py) -- see
SPECTRAL_SENSITIVITY_TITLE's comment below for why it needs peak-x curve
identification, not plain label matching, and why it's opt-in per file
(`skip_spectral_sensitivity=False`) rather than on by default.

Usage: uv run kodak_reversal.py
"""

from pathlib import Path

from digitizer_core import curves_by_peak_x_with_envelope, locate_panel_bboxes
from kodak_common import (
    characteristic_chart, get_panel_bboxes, overline_negative_calib, overline_symmetric_calib,
    spectral_dye_density_chart, spectral_sensitivity_chart_by_peak_x, REVERSAL_DYE_DENSITY_LABELS,
)
from product import ProductSpec, digitize_product, run_products_parallel

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")
CHAR_TITLE = r"(?i)^(characteristic|characterstic)$"  # exact alternation, not a prefix: a loose
# prefix match (e.g. r"^characte") also matches body-text words like "characterized"/
# "characteristics" which can sit ABOVE the real title and get wrongly picked as
# topmost -- this bit e145-Ektachrome_320T_EPJ.pdf. Tolerant of Kodak's own typo
# ("Characterstic", e27) and ALL-CAPS (e88) titles via exact (not prefix) alternation instead.
DYE_DENSITY_TITLE = r"(?i)^Spectral-Dye-Density$"
SPECTRAL_SENSITIVITY_TITLE = r"(?i)^Spectral-Sensitivity$"
# NOTE (2026-07-10): the module docstring used to claim this page template
# never packs a Spectral-Sensitivity/Spectral-Dye-Density panel alongside
# Characteristic -- that was WRONG for at least e8-Ektachrome_64_EPR.pdf
# (confirmed by rendering: real 2x2 grid, Characteristic/Spectral-Sensitivity
# top row, Modulation-Transfer/Spectral-Dye-Density bottom row). Spectral-
# Sensitivity was then left uncaptured for a second reason (still separate
# from the docstring claim above): a first attempt at plain label-regex/rank
# matching was mis-diagnosed as "fragmented, toe/shoulder missing" -- that
# was wrong too. Re-investigated 2026-07-10 (user noticed the QA overlay had
# no Spectral-Sensitivity panel at all and asked why): the 3 raw traces are
# each already complete (confirmed against the rendered page -- each dye
# layer's curve genuinely only spans ~130-200nm before running off the
# printed +/-2.0 LOG SENSITIVITY axis, not a fragmentation artifact), but two
# REAL bugs were hiding behind the "fragmented" misdiagnosis:
# (1) the panel's Magenta-Forming (~550nm peak) and Cyan-Forming (~650nm
#     peak) inline labels sit close enough in y that rank-based label
#     matching silently swaps them -- the exact tied-label-y failure mode
#     `curves_by_peak_x` (digitizer_core.py) was built to fix for the
#     Spectral-Dye-Density panel, just not yet applied here. Fixed via
#     `spectral_sensitivity_chart_by_peak_x` (kodak_common.py), same
#     peak-x-ordering approach (Yellow-Forming < Magenta-Forming <
#     Cyan-Forming, left to right by wavelength -- a real physical
#     invariant, not assumed).
# (2) the LOG SENSITIVITY y-axis prints "2.0 1.0 0.0 1.0 2.0" top-to-bottom
#     -- the bottom half's minus signs are drawn as vector overlines, not
#     text glyphs, so plain tick-text reading treats -1.0/-2.0 as +1.0/+2.0
#     and (confirmed directly) `fit_axis`'s outlier rejection then keeps the
#     wrong (bottom-half, sign-flipped) 3-tick run instead of the correct
#     top-to-bottom 5-tick spread. `overline_symmetric_calib`
#     (kodak_common.py) was written for exactly this shape and already
#     names e8 in its own docstring, but was never actually wired into a
#     call site until now -- passed as `spectral_sensitivity_overline_symmetric=True`.
# Both fixes verified together against the rendered page (peak values and
# peak wavelengths for all 3 layers now match what's printed).
PANEL_TITLES = [CHAR_TITLE, r"(?i)^modulation-transfer$", r"(?i)^diffuse$", r"(?i)^modulation$"]
# Deliberately NOT folded into PANEL_TITLES above: locate_panel_bboxes clusters
# ALL given titles into shared rows/columns, so adding DYE_DENSITY_TITLE to
# that same call can shift row boundaries and silently truncate char_box on
# layouts PANEL_TITLES already handled correctly -- confirmed regression on
# Kodachrome 64/25/200 (e88-2002_03.pdf): char_box's bottom edge moved from
# the page bottom (784) to 274, cutting off the x-axis tick row entirely and
# crashing fit_axis. Looked up via its OWN separate get_panel_bboxes call
# instead (see reversal_product below), so it can never affect char_box.
# Same reasoning applies to SPECTRAL_SENSITIVITY_TITLE -- its own separate
# SPECTRAL_SENSITIVITY_PANEL_TITLES lookup below, not folded in here either.
DYE_DENSITY_PANEL_TITLES = [CHAR_TITLE, DYE_DENSITY_TITLE]
# Row-splitting (top Characteristic/Spectral-Sensitivity vs. bottom
# Modulation-Transfer/Spectral-Dye-Density) needs all 4 titles present in one
# locate_panel_bboxes call -- 2 titles alone (CHAR_TITLE + this one) leaves
# both boxes unbounded on the bottom (confirmed: bottom edge defaults to page
# height, 784, swallowing the Modulation-Transfer/Spectral-Dye-Density row).
SPECTRAL_SENSITIVITY_PANEL_TITLES = [
    CHAR_TITLE, SPECTRAL_SENSITIVITY_TITLE, r"(?i)^modulation-transfer$", DYE_DENSITY_TITLE,
]
MIN_DYE_DENSITY_PANEL_HEIGHT = 50


def reversal_product(pdf_stub, page_index, product_name, iso, year, print_route=None,
                      char_box=None, overline_minus=False, cross_object_merge=False,
                      monotonic="increasing", strict_chain_merge=False, min_trace_points=12,
                      dye_density_box=None, skip_dye_density=False, dye_density_cross_object_merge=False,
                      dye_density_page_index=None, dye_density_curves=None,
                      dye_density_min_trace_points=12, dye_density_merge_strategy="proximity",
                      spectral_sensitivity_box=None, skip_spectral_sensitivity=True,
                      spectral_sensitivity_page_index=None, spectral_sensitivity_cross_object_merge=False,
                      spectral_sensitivity_min_trace_points=12, spectral_sensitivity_merge_strategy="proximity",
                      spectral_sensitivity_overline_symmetric=False):
    """Single 'Characteristic Curves' panel plus (when present -- not every
    era/template has one, see PANEL_TITLES' note above) a Spectral-Dye-Density
    panel, R/G/B inline labels (Strategy D). `cross_object_merge`:
    some sheets draw one curve as several separate short drawing objects
    rather than one continuous path -- see extract_traces_in_region's own
    docstring for why this isn't a safe default and must be opted into
    per-file after confirming via QA overlay. `monotonic`: whether density
    increases or decreases with exposure IN THIS FILE'S OWN CALIBRATED DATA
    ORDER -- this can differ per file even for the same real physical
    direction (reversal density truly falls with exposure) depending on
    which way that file's x-axis calibration slope points; don't assume
    "increasing" blindly -- run once with monotonic_direction=None first and
    check the printed likely_direction if unsure, then lock it in here.
    `skip_spectral_sensitivity` defaults to True (unlike dye-density, which
    auto-attaches when present) -- SPECTRAL_SENSITIVITY_TITLE's own comment
    above found real per-file bugs (tied-label swap, overline-minus
    miscalibration) behind what looked like a fragmentation problem, so this
    panel is captured only where a file has actually been verified against
    its own rendered page, not turned on corpus-wide by default. Pass
    `skip_spectral_sensitivity=False` (and `spectral_sensitivity_overline_symmetric=True`
    if that file's LOG SENSITIVITY axis has the same unsigned-bottom-half
    tick text e8 does -- check the rendered page, don't assume) once verified."""
    pdf_path = PDF_ROOT / pdf_stub
    if char_box is None:
        boxes = get_panel_bboxes(pdf_path, page_index, PANEL_TITLES)
        char_box = boxes[CHAR_TITLE]
    charts = [characteristic_chart(pdf_stub, page_index, char_box, monotonic=monotonic)]
    charts[0].cross_object_merge = cross_object_merge
    charts[0].strict_chain_merge = strict_chain_merge
    charts[0].min_trace_points = min_trace_points
    if overline_minus:
        charts[0].x_axis_calib_override = overline_negative_calib(pdf_path, page_index, char_box)
    if dye_density_box is None and dye_density_page_index is None and not skip_dye_density:
        try:
            dd_boxes = get_panel_bboxes(pdf_path, page_index, DYE_DENSITY_PANEL_TITLES)
        except RuntimeError:
            dd_boxes = {}
        dye_density_box = dd_boxes.get(DYE_DENSITY_TITLE)
    if not skip_dye_density and dye_density_box is not None:
        if dye_density_box[3] - dye_density_box[1] >= MIN_DYE_DENSITY_PANEL_HEIGHT:
            dd_page = dye_density_page_index if dye_density_page_index is not None else page_index
            dd_chart = spectral_dye_density_chart(pdf_stub, dd_page, dye_density_box,
                                                   labels=REVERSAL_DYE_DENSITY_LABELS,
                                                   cross_object_merge=dye_density_cross_object_merge,
                                                   min_trace_points=dye_density_min_trace_points,
                                                   merge_strategy=dye_density_merge_strategy)
            if dye_density_curves is not None:
                # Bypasses the (name, regex) label-lookup path entirely -- see
                # curves_by_peak_x/curves_by_peak_x_with_envelope in digitizer_core.py for why
                # (Fuji-style tied-label-y panels, or E100G/E100GX's unlabeled Visual-Neutral
                # envelope curve).
                dd_chart.curves = dye_density_curves
            charts.append(dd_chart)
    if not skip_spectral_sensitivity:
        if spectral_sensitivity_box is None and spectral_sensitivity_page_index is None:
            try:
                ss_boxes = get_panel_bboxes(pdf_path, page_index, SPECTRAL_SENSITIVITY_PANEL_TITLES)
            except RuntimeError:
                ss_boxes = {}
            spectral_sensitivity_box = ss_boxes.get(SPECTRAL_SENSITIVITY_TITLE)
        if spectral_sensitivity_box is not None:
            ss_page = spectral_sensitivity_page_index if spectral_sensitivity_page_index is not None else page_index
            ss_chart = spectral_sensitivity_chart_by_peak_x(
                pdf_stub, ss_page, spectral_sensitivity_box,
                ["blue_yellow_forming_layer", "green_magenta_forming_layer", "red_cyan_forming_layer"],
                cross_object_merge=spectral_sensitivity_cross_object_merge,
                min_trace_points=spectral_sensitivity_min_trace_points,
                merge_strategy=spectral_sensitivity_merge_strategy)
            if spectral_sensitivity_overline_symmetric:
                ss_chart.y_axis_calib_override = overline_symmetric_calib(
                    pdf_path, ss_page, spectral_sensitivity_box)
            charts.append(ss_chart)
    return ProductSpec(
        brand="kodak", product_name=product_name, application_area="photography",
        film_type="reversal", medium="color", iso=iso, year=year,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=charts, print_route=print_route,
        digitizer_notes="Reversal-film 'CURVES' page template; Characteristic Curves curves ID'd "
                         "by inline B/G/R labels, Spectral-Dye-Density (when present) by inline "
                         "Yellow/Magenta/Cyan/Visual-Neutral labels, Spectral-Sensitivity (when "
                         "captured) by peak-x-ordered Yellow-/Magenta-/Cyan-Forming-Layer identity "
                         "(Strategy D, vector_position). print_route left null unless the "
                         "datasheet's own text was checked for a stated recommendation.",
    )


_E4024_PDF = PDF_ROOT / "film/kodak/e4024-Ektachrome_E100G.pdf"
_E4024_DYE_DENSITY_BOX = (330, 350, 575, 590)
# This panel's 4 real curves (Yellow/Magenta/Cyan + an unlabeled "Visual Neutral" envelope,
# confirmed via direct render -- the 4th, taller curve riding atop and connecting all 3 dye
# peaks) have only 3 inline labels, all at nearly identical y ("Visual Neutral" isn't labeled
# at all on this file, unlike e8/e130/etc.) -- plain label-regex matching mismatches all 3
# (confirmed via QA overlay: "yellow" grabbed the real Visual-Neutral trace instead), and a
# bare peak-x match doesn't find the envelope either (it has 3 local peaks, not one). Fixed
# via curves_by_peak_x_with_envelope (digitizer_core.py): the envelope is identified by never
# sinking as low as the other 3 (a real invariant -- it's their sum, so it's bounded below by
# whichever single dye is largest at that wavelength), the remaining 3 by peak-x as usual.
# `min_trace_points=4, cross_object_merge=True, merge_strategy="sequential_band"`: this
# panel's curves are heavily fragmented (7 raw path objects for 4 real curves at the default
# settings) -- sequential_band was needed to correctly recombine them into exactly 4, verified
# via QA overlay. This ONE panel is shared by BOTH E100G and E100GX (title says "E100G and
# E100GX Films") -- computed once, attached to both product JSONs, same precedent as Portra
# 160NC/160VC's shared Spectral-Sensitivity chart in kodak_still.py.
_E4024_DYE_DENSITY_CURVES = curves_by_peak_x_with_envelope(
    _E4024_PDF, 4, _E4024_DYE_DENSITY_BOX, ["yellow", "magenta", "cyan"], "visual_neutral",
    min_trace_points=4, cross_object_merge=True, merge_strategy="sequential_band")

PRODUCTS = [
    lambda: reversal_product("film/kodak/e4024-Ektachrome_E100G.pdf", 4, "Ektachrome E100G", 100, 2003,
                              char_box=(40, 100, 290, 330), monotonic="decreasing",
                              cross_object_merge=True, strict_chain_merge=True, min_trace_points=8,
                              dye_density_box=_E4024_DYE_DENSITY_BOX,
                              dye_density_curves=_E4024_DYE_DENSITY_CURVES,
                              dye_density_cross_object_merge=True, dye_density_min_trace_points=4,
                              dye_density_merge_strategy="sequential_band"),
    lambda: reversal_product("film/kodak/e4024-Ektachrome_E100G.pdf", 4, "Ektachrome E100GX", 100, 2003,
                              char_box=(40, 353, 290, 583), monotonic="decreasing",
                              cross_object_merge=True, strict_chain_merge=True, min_trace_points=8,
                              dye_density_box=_E4024_DYE_DENSITY_BOX,
                              dye_density_curves=_E4024_DYE_DENSITY_CURVES,
                              dye_density_cross_object_merge=True, dye_density_min_trace_points=4,
                              dye_density_merge_strategy="sequential_band"),
    lambda: reversal_product("film/kodak/e8-Ektachrome_64_EPR.pdf", 4, "Ektachrome 64 Professional EPR", 64, 2000,
                              skip_spectral_sensitivity=False, spectral_sensitivity_overline_symmetric=True),
    # This page's real layout is a 2x2 grid (Characteristic top-left, Spectral-Sensitivity
    # top-right, Spectral-Dye-Density bottom-left, Modulation-Transfer bottom-right, confirmed
    # via direct render). Neither char_box nor dye_density_box can be left to
    # get_panel_bboxes' auto-detection here: PANEL_TITLES doesn't include
    # SPECTRAL_SENSITIVITY_TITLE (see that constant's own comment on why it's looked up
    # separately), so the auto-detected char_box's right edge (396.5) runs well past this
    # panel's own real content (drawn-frame bbox maxx=294, confirmed via page.get_drawings())
    # and into Spectral-Sensitivity's column (starts x=346.5) -- and the auto right edge on
    # dye_density_box would be even worse (a separate get_panel_bboxes call over just
    # [char, dye-density] titles returns a box only 66pt wide, missing most of the real panel).
    # Both explicit boxes below were derived from this file's own real text/drawing extents
    # (get_text("words")/get_drawings() over page 4), confirmed via QA overlay to no longer
    # bleed into the neighboring Spectral-Sensitivity/Modulation-Transfer panels -- this was a
    # real bug (2026-07-10): the committed QA overlay showed Spectral-Sensitivity's own title/
    # axis/legend text ghosted into the Characteristic subplot's background, and a sliver of
    # Modulation-Transfer's "RESPONSE (%)" label ghosted into the Dye-Density subplot's.
    lambda: reversal_product("film/kodak/e27-Ektachrome_100_EPN.pdf", 4, "Ektachrome 100 Professional EPN", 100, 2000,
                              char_box=(54, 107, 296, 335),
                              dye_density_box=(48, 350, 290, 572)),
    lambda: reversal_product("film/kodak/e113-Ektachrome_100_plus_EPP.pdf", 4, "Ektachrome 100 Plus Professional EPP", 100, 2000),
    lambda: reversal_product("film/kodak/e130-Ektachrome_64T_EPY.pdf", 4, "Ektachrome 64T Professional EPY", 64, 2007,
                              dye_density_box=(320, 275, 560, 495)),
    lambda: reversal_product("film/kodak/e144-Ektachrome_160T_EPT.pdf", 3, "Ektachrome 160T Professional EPT", 160, 2007,
                              # Spectral-Dye-Density panel is on the FOLLOWING page (4), same
                              # off-page-from-char pattern found across several e1xx-era sheets.
                              dye_density_page_index=4, dye_density_box=(55, 275, 285, 510)),
    # Spectral-Dye-Density panel's 4 curves have NO inline text labels at all (the "Visual"
    # word found nearby is from "Diffuse Visual Densitometry:" caption text, a false
    # positive, not a curve label) -- identified purely by trace shape via
    # curves_by_peak_x_with_envelope instead: Yellow/Magenta/Cyan by peak-x, Visual Neutral
    # by never sinking as low as the other 3 (see that function's own docstring).
    lambda: reversal_product("film/kodak/e161-Ektachrome_400X_EPL.pdf", 4, "Ektachrome 400X Professional EPL", 400, 2000,
                              dye_density_box=(328, 348, 565, 585),
                              dye_density_curves=curves_by_peak_x_with_envelope(
                                  PDF_ROOT / "film/kodak/e161-Ektachrome_400X_EPL.pdf", 4,
                                  (328, 348, 565, 585), ["yellow", "magenta", "cyan"], "visual_neutral")),
    lambda: reversal_product("film/kodak/e163-Ektachrome_E100VS.pdf", 4, "Ektachrome E100VS", 100, 2000,
                              dye_density_box=(48, 356, 320, 594)),
    lambda: reversal_product("film/kodak/e145-Ektachrome_320T_EPJ.pdf", 2, "Ektachrome 320T Professional EPJ", 320, 2007,
                              dye_density_page_index=3, dye_density_box=(42, 290, 270, 522)),
    lambda: reversal_product("film/kodak/e28-Ektachrome_E200.pdf", 4, "Ektachrome E200", 200, 2000),
    lambda: reversal_product("film/kodak/E7014e-Elitechrome_100.pdf", 2, "Elite Chrome 100", 100, 2005,
                              cross_object_merge=True, monotonic="decreasing",
                              dye_density_page_index=3, dye_density_box=(50, 78, 270, 315),
                              # Heavily fragmented (8 raw path objects for 4 real curves at
                              # default settings).
                              dye_density_cross_object_merge=True, dye_density_min_trace_points=4,
                              dye_density_merge_strategy="sequential_band"),
    lambda: reversal_product("film/kodak/e126e-Elitechrome_100ec.pdf", 4, "Elite Chrome 100 EC", 100, 2005,
                              dye_density_box=(48, 322, 320, 559)),
    lambda: reversal_product("film/kodak/e148e-Elite_chrome_200.pdf", 3, "Elite Chrome 200", 200, 2005,
                              overline_minus=True, char_box=(40, 450, 330, 690), monotonic="decreasing",
                              dye_density_page_index=4, dye_density_box=(55, 28, 280, 265)),
    lambda: reversal_product("film/kodak/e149-Elite_chrome_400.pdf", 2, "Elite Chrome 400", 400, 2000,
                              overline_minus=True, monotonic="decreasing",
                              dye_density_page_index=3, dye_density_box=(40, 272, 270, 522)),
    lambda: reversal_product("film/kodak/e147-Ektachrome_P1600_EPH.pdf", 4, "Ektachrome P1600 Professional EPH", 400, 2000,
                              dye_density_box=(320, 290, 560, 510)),
    lambda: reversal_product("film/kodak/e88-2002_03.pdf", 5, "Kodachrome 64", 64, 2002),
    lambda: reversal_product("film/kodak/e88-2002_03.pdf", 4, "Kodachrome 25", 25, 2002, monotonic="decreasing"),
    lambda: reversal_product("film/kodak/e88-2002_03.pdf", 6, "Kodachrome 200", 200, 2002),
]

# DEFERRED:
# - ti2323-Ektachrome_EIR.pdf (Ektachrome Infrared EIR): false-color infrared
#   film plots "Green/Red", "Red/IR", "Blue/Green" ratio curves, not simple
#   per-layer R/G/B density curves -- fundamentally different chart
#   semantics, not a fit for the standard reversal template's label set.


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
