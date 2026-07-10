"""
Digitizes Fuji still-photography film datasheets (film/fuji/*.pdf) into
consolidated-data/film/photography/{negative,reversal}/fuji/.

Different situation from Kodak: most Fuji sheets' "Characteristic Curves"
panel is monochrome, dash-pattern-distinguished (not distinct color fills,
despite the plan's original assumption) -- same Strategy D (vector_position)
as Kodak, with real inline "Red"/"Green"/"Blue" TEXT labels (not single
letters). But confirmed (2026-07-05) this only works for a SUBSET of the
corpus: of 22 individual color datasheets checked, only 8 originally had
both real vector curves AND real extractable tick/label text -- the other
14 split into three categories (see BLOCKED.md's history for the original
diagnosis):
  - 6 files: the Characteristic Curves panel is an embedded RASTER IMAGE,
    not vector paths (same problem class as post-2018 Ilford sheets) --
    Velvia 50, Provia 100F, RTP II, Sensia 100, Superia 100, Superia 200.
    Still blocked -- not handled here (see BLOCKED.md).
  - 9 files: real vector curve paths exist, but the axis ticks and R/G/B
    labels are vector-drawn shapes with no embedded font text at all (same
    blocker class as Ilford Multigrade). RESOLVED 2026-07-05 via OCR
    (`ocr_helpers.py`, tesseract) for axis calibration on every one of the
    9, plus one of two different curve-identity mechanisms depending on
    template: `fuji_ocr_product` (rank-order, using the empirically-verified
    Fuji house convention -- negative films run Blue>Green>Red by density,
    reversal films run the reverse -- for Pro 400H/800Z/160C/160S, Superia
    Reala/X-tra 800) or `fuji_ocr_dash_reversal_product` (Strategy B
    dash-pattern matching, since these curves are position-ambiguous but
    style-disambiguated -- solid/dash/dash-dot -- for Velvia 100, Sensia
    200/400). All 9 now digitized below.
Only the 6 raster-image files remain blocked (see BLOCKED.md) -- category 1
("do the clean files") from the original 2026-07-05 survey.

Usage: uv run fuji_still.py
"""

from pathlib import Path

import fitz

from digitizer_core import ChartSpec, CurveSpec, curves_by_peak_x
from ocr_helpers import ocr_axis_calib
from product import ProductSpec, digitize_product, run_products_parallel

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")


_FULL_WORD_LABELS = [r"^Red$", r"^Green$", r"^Blue$"]
_SINGLE_LETTER_LABELS = [r"^R$", r"^G$", r"^B$"]

# Fuji's "Spectral Dye Density Curves" panel comes in the same 2 shapes as Kodak's: reversal
# (chrome) films plot 3 curves (bare Yellow/Magenta/Cyan, no 4th Visual-Neutral composite --
# confirmed absent on every Fuji reversal sheet checked, unlike Kodak's version of this panel);
# negative films plot 2 curves (Minimum Density/Mid-scale Density, same D-min/midscale-neutral
# convention as Kodak's negative-film version). Real inline text labels on both -- but the
# reversal (3-curve) shape needs fuji_reversal_dye_density_chart's peak-x identity fix, not
# plain label-regex matching; see that function's own docstring for why.
FUJI_DYE_DENSITY_LABELS_NEGATIVE = [("d_min", r"^Minimum$"), ("midscale_neutral", r"^Mid-scale$")]


def fuji_dye_density_chart(pdf_stub, page_index, panel_bbox, labels):
    return ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="spectral_dye_density",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="diffuse_spectral_density",
        curves=[CurveSpec(name, label_regex=regex) for name, regex in labels],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=panel_bbox,
    )


def fuji_reversal_dye_density_chart(pdf_stub, page_index, panel_bbox):
    # Fuji prints "Yellow  Magenta  Cyan" as one horizontal row, so plain label-regex
    # matching mismatches curve identity -- see curves_by_peak_x's own docstring
    # (digitizer_core.py) for the full story; confirmed broken this way on every one of the
    # 5 Fuji reversal sheets with this panel (Astia 100F, Velvia 100F, T64, Provia 400F,
    # Provia 400X).
    curves = curves_by_peak_x(PDF_ROOT / pdf_stub, page_index, panel_bbox,
                               ["yellow", "magenta", "cyan"])
    return ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="spectral_dye_density",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="diffuse_spectral_density",
        curves=curves,
        film_id="_unused", extraction_method="vector_position",
        region_bbox=panel_bbox,
    )


def fuji_char_chart(pdf_stub, page_index, char_box, x_tick_regex=r"-?\d\.0",
                     y_tick_regex=r"\d\.[05]", monotonic="decreasing", label_regexes=None,
                     min_trace_points=12):
    """Fuji 'Characteristic Curves' panel -- inline "Red"/"Green"/"Blue" TEXT
    labels on most sheets, but single-letter "R"/"G"/"B" on some (e.g. T64)
    -- pass `label_regexes=_SINGLE_LETTER_LABELS` for those. Strategy D
    (vector_position). `monotonic`: reversal film density falls with
    exposure ("decreasing"); negative film density rises ("increasing").
    `min_trace_points`: lower this (e.g. 8) for sheets whose curves are
    digitized with few vertices -- confirmed on Provia 400F, whose Green/Blue
    traces have only 8 raw points each, below the default 12 floor."""
    label_regexes = label_regexes or _FULL_WORD_LABELS
    return ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="characteristic_curve",
        x_tick_regex=x_tick_regex, y_tick_regex=y_tick_regex,
        x_label="log_exposure_lux_seconds", y_label="density_status_a",
        curves=[CurveSpec("red_cyan_forming_layer", label_regex=label_regexes[0]),
                CurveSpec("green_magenta_forming_layer", label_regex=label_regexes[1]),
                CurveSpec("blue_yellow_forming_layer", label_regex=label_regexes[2])],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=char_box, monotonic_direction=monotonic, min_trace_points=min_trace_points,
    )


def fuji_reversal_product(pdf_stub, page_index, product_name, iso, year, char_box,
                           x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.[05]", label_regexes=None,
                           min_trace_points=12, dye_density_box=None):
    chart = fuji_char_chart(pdf_stub, page_index, char_box, x_tick_regex, y_tick_regex,
                             monotonic="decreasing", label_regexes=label_regexes,
                             min_trace_points=min_trace_points)
    charts = [chart]
    if dye_density_box is not None:
        charts.append(fuji_reversal_dye_density_chart(pdf_stub, page_index, dye_density_box))
    return ProductSpec(
        brand="fuji", product_name=product_name, application_area="photography",
        film_type="reversal", medium="color", iso=iso, year=year,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=charts,
        digitizer_notes="Reversal (chrome) film; 'Characteristic Curves' panel, curves ID'd by "
                         "inline Red/Green/Blue text labels (Strategy D, vector_position). "
                         "Spectral-Dye-Density (when present) via inline Yellow/Magenta/Cyan labels, "
                         "no 4th Visual-Neutral curve on this vendor's version of the panel.",
    )


def fuji_negative_product(pdf_stub, page_index, product_name, iso, year, char_box,
                           x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.[05]", label_regexes=None,
                           min_trace_points=12, dye_density_box=None):
    chart = fuji_char_chart(pdf_stub, page_index, char_box, x_tick_regex, y_tick_regex,
                             monotonic="increasing", label_regexes=label_regexes,
                             min_trace_points=min_trace_points)
    charts = [chart]
    if dye_density_box is not None:
        charts.append(fuji_dye_density_chart(pdf_stub, page_index, dye_density_box,
                                              FUJI_DYE_DENSITY_LABELS_NEGATIVE))
    return ProductSpec(
        brand="fuji", product_name=product_name, application_area="photography",
        film_type="negative", medium="color", iso=iso, year=year,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=charts,
        digitizer_notes="Color negative film; 'Characteristic Curves' panel, curves ID'd by "
                         "inline Red/Green/Blue text labels (Strategy D, vector_position). "
                         "Spectral-Dye-Density (when present) via inline Minimum/Mid-scale Density "
                         "labels, same 2-curve convention as Kodak's negative-film version.",
    )


def fuji_ocr_product(pdf_stub, page_index, product_name, iso, year, film_type, char_box,
                      x_tick_bbox, y_tick_bbox, x_tick_regex=r"-?\d\.\d", y_tick_regex=r"\d\.\d",
                      min_trace_points=6):
    """For the 9 confirmed 'vector curves, but zero extractable tick/label
    text' Fuji sheets (see BLOCKED.md) -- axis calibration comes from OCR
    (`ocr_axis_calib`, tesseract) instead of `fit_axis`'s text search, and
    curve identity comes from RANK ORDER using a real, empirically-verified
    Fuji house convention rather than per-word OCR of the rotated Red/
    Green/Blue labels (which turned out to be unreliable -- systematically
    drops the leading capital, and the labels sit close enough together
    diagonally that a hand-picked crop box for one routinely clips its
    neighbor). Checked across all 7 already-digitized Fuji color films
    (2026-07-05): EVERY negative film shows Blue > Green > Red by density
    (top-to-bottom on the chart) and EVERY reversal film shows the reverse,
    Red > Green > Blue -- no exceptions, so `film_type` alone determines
    the label order; synthetic label positions just need to be in that
    relative order (`assign_traces_to_labels_exclusive`'s rank-order path
    only uses relative order, not the actual coordinates)."""
    cx = (char_box[0] + char_box[2]) / 2
    order = (["blue_yellow_forming_layer", "green_magenta_forming_layer", "red_cyan_forming_layer"]
             if film_type == "negative" else
             ["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"])
    pdf_path = PDF_ROOT / pdf_stub
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    x_calib = ocr_axis_calib(page, x_tick_bbox, tick_regex=x_tick_regex, axis="x")
    y_calib = ocr_axis_calib(page, y_tick_bbox, tick_regex=y_tick_regex, axis="y")
    chart = ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="characteristic_curve",
        x_tick_regex=x_tick_regex, y_tick_regex=y_tick_regex,
        x_label="log_exposure_lux_seconds", y_label="density_status_a",
        curves=[CurveSpec(order[i], label_position_override=(cx, 100 + 50 * i)) for i in range(3)],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=char_box, monotonic_direction=("increasing" if film_type == "negative" else "decreasing"),
        min_trace_points=min_trace_points,
        x_axis_calib_override=x_calib, y_axis_calib_override=y_calib,
    )
    return ProductSpec(
        brand="fuji", product_name=product_name, application_area="photography",
        film_type=film_type, medium="color", iso=iso, year=year,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[chart],
        digitizer_notes="'Characteristic Curves' panel with no extractable tick/label text -- axis "
                         "calibration via OCR (tesseract), curve identity via rank order using the "
                         "verified Fuji house convention (negative: Blue>Green>Red by density; "
                         "reversal: Red>Green>Blue), not per-word OCR of the rotated R/G/B labels.",
    )


def fuji_ocr_dash_reversal_product(pdf_stub, page_index, product_name, iso, year, char_box,
                                    x_tick_bbox, y_tick_bbox, legend_bbox,
                                    x_tick_regex=r"-?\d\.\d", y_tick_regex=r"\d\.\d",
                                    stroke_rgb=(0, 0, 0), stroke_tol=0.05):
    """For the subset of the 9 OCR-blocked Fuji reversal sheets that use a
    DIFFERENT template from `fuji_ocr_product` -- confirmed on Velvia 100
    (2026-07-05): instead of three separately-positioned inline "Red"/
    "Green"/"Blue" text labels running alongside their own curve, all 3
    R/G/B curves are near-overlapping for most of their range and
    distinguished only by LINE STYLE (solid/dash/dash-dot), with a small
    upright legend box (not rotated, unlike the other template's inline
    labels) mapping each style to its letter. This means curve identity
    doesn't need OCR or rank-order at all -- it's real Strategy B
    (`vector_stroke_dash`, dash-pattern matching), same mechanism as Kodak,
    once `region_bbox` scoping (added 2026-07-05 to
    `extract_curve_points_by_stroke`) keeps it from also matching
    gridlines/frame lines (same dash=[] as the solid R curve) or an
    unrelated same-styled chart elsewhere on the page. Axis ticks still
    need OCR (still no real extractable tick text on this template).
    Confirmed dash-pattern mapping (verified by rendering+reading the
    legend box directly, since the legend's own "R"/"G"/"B" glyphs are
    ALSO not real text): solid dash=[]->R, 2-value dash (e.g. [3 1.5] or
    [3.5 2], the exact numbers vary by file)->G, 4-value dash-dot (e.g.
    [8.999 1.5 2.5 1.5] or [8.999 2 3 2])->B -- matched by NUMBER of dash
    values, not exact numbers, since those vary file-to-file (confirmed
    different between Velvia 100 and Sensia 200). `stroke_rgb`/`stroke_tol`:
    Velvia 100 uses true black (0,0,0); Sensia 200 uses a near-black dark
    gray (0.137, 0.122, 0.125) instead -- check each file's own
    `page.get_drawings()` color rather than assuming pure black."""
    pdf_path = PDF_ROOT / pdf_stub
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    x_calib = ocr_axis_calib(page, x_tick_bbox, tick_regex=x_tick_regex, axis="x")
    y_calib = ocr_axis_calib(page, y_tick_bbox, tick_regex=y_tick_regex, axis="y")
    chart = ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="characteristic_curve",
        x_tick_regex=x_tick_regex, y_tick_regex=y_tick_regex,
        x_label="log_exposure_lux_seconds", y_label="density_status_a",
        curves=[
            CurveSpec("red_cyan_forming_layer", stroke_rgb=stroke_rgb, tol=stroke_tol,
                      dash_regex=r"^\[\] ", width=1.0, width_tol=0.3),
            CurveSpec("green_magenta_forming_layer", stroke_rgb=stroke_rgb, tol=stroke_tol,
                      dash_regex=r"^\[ [\d.]+ [\d.]+ \] ", width=1.0, width_tol=0.3),
            CurveSpec("blue_yellow_forming_layer", stroke_rgb=stroke_rgb, tol=stroke_tol,
                      dash_regex=r"^\[ [\d.]+ [\d.]+ [\d.]+ [\d.]+ \] ", width=1.0, width_tol=0.3),
        ],
        film_id="_unused", extraction_method="vector_stroke_dash",
        region_bbox=char_box, monotonic_direction="decreasing", legend_bbox=legend_bbox,
        x_axis_calib_override=x_calib, y_axis_calib_override=y_calib,
    )
    return ProductSpec(
        brand="fuji", product_name=product_name, application_area="photography",
        film_type="reversal", medium="color", iso=iso, year=year,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[chart],
        digitizer_notes="'Characteristic Curves' panel with no extractable tick/legend text -- axis "
                         "calibration via OCR (tesseract); curve identity via Strategy B dash-pattern "
                         "matching (solid=R, dash=G, dash-dot=B, confirmed by rendering+reading the "
                         "legend box directly), not OCR/rank-order (unlike the other OCR-blocked Fuji "
                         "template, this one's curves are position-ambiguous -- near-overlapping for "
                         "most of the range -- but style-disambiguated, real Strategy B territory). "
                         "Sensia 200/400 specifically: one curve's dash-dot stroke is drawn as two "
                         "disconnected path segments with a real gap where it visually coincides with "
                         "another curve (confirmed via page.get_drawings(), not an extraction bug) -- "
                         "the gap is bridged by a straight interpolation, acceptable since the curves "
                         "are near-identical there anyway and monotonicity is unaffected (0 violations).",
    )


PRODUCTS = [
    lambda: fuji_reversal_product("film/fuji/astia_100f_datasheet.pdf", 7, "Astia 100F", 100, 2003,
                                   char_box=(46, 160, 290, 380),
                                   dye_density_box=(305, 495, 540, 640)),
    lambda: fuji_reversal_product("film/fuji/velvia_100f_datasheet.pdf", 7, "Velvia 100F", 100, 2003,
                                   char_box=(46, 105, 290, 300),
                                   dye_density_box=(305, 420, 540, 565)),
    lambda: fuji_reversal_product("film/fuji/t64_datasheet.pdf", 6, "T64", 64, 2003,
                                   char_box=(46, 95, 290, 300), label_regexes=_SINGLE_LETTER_LABELS,
                                   dye_density_box=(303, 430, 540, 572)),
    lambda: fuji_reversal_product("film/fuji/PROVIA400FAF3-066E_1.pdf", 5, "Provia 400F", 400, 2003,
                                   char_box=(46, 85, 290, 310), min_trace_points=6,
                                   dye_density_box=(306, 430, 545, 577)),
    lambda: fuji_reversal_product("film/fuji/Provia_400X_PIB_1007.pdf", 6, "Provia 400X", 400, 2007,
                                   char_box=(46, 95, 290, 300), label_regexes=_SINGLE_LETTER_LABELS,
                                   dye_density_box=(302, 428, 540, 570)),
    # Spectral-Dye-Density panel NOT included on either Superia 1600 or Superia X-tra 400
    # (both same page template): confirmed via page.get_drawings() that the Minimum Density
    # and Mid-scale Density curves are NOT two separate stroked path objects the way every
    # other file in this corpus draws them -- only ONE curve-shaped object exists in the
    # panel region (16 path items, correctly extracts as the real Minimum Density curve, 29
    # points); the Mid-scale Density curve visibly present in the rendered page has no
    # corresponding stroked object at all in this region, at any box width tried. Not a box
    # or label-matching problem -- the real path data for that curve isn't being returned by
    # get_drawings() the way it is for every other file, a deeper extraction gap than this
    # session's scope. Real follow-up work, not chased further.
    lambda: fuji_negative_product("film/fuji/superia_1600_datasheet.pdf", 5, "Superia 1600", 1600, 2003,
                                   char_box=(46, 105, 290, 300), min_trace_points=6),
    lambda: fuji_negative_product("film/fuji/superia_xtra400_datasheet.pdf", 5, "Superia X-tra 400", 400, 2003,
                                   char_box=(46, 105, 290, 300), min_trace_points=6),
    lambda: fuji_ocr_product("film/fuji/pro_400h_datasheet.pdf", 7, "Pro 400H", 400, 2004, "negative",
                              char_box=(46, 90, 290, 300),
                              x_tick_bbox=(60, 250, 290, 265), y_tick_bbox=(40, 95, 90, 240)),
    lambda: fuji_ocr_product("film/fuji/pro_800z_datasheet.pdf", 7, "Pro 800Z", 800, 2004, "negative",
                              char_box=(46, 90, 290, 300),
                              x_tick_bbox=(60, 250, 290, 265), y_tick_bbox=(40, 95, 90, 240)),
    lambda: fuji_ocr_product("film/fuji/pro_160c_datasheet.pdf", 7, "Pro 160C", 160, 2004, "negative",
                              char_box=(46, 90, 290, 300),
                              x_tick_bbox=(65, 285, 290, 296), y_tick_bbox=(60, 95, 90, 285)),
    lambda: fuji_ocr_product("film/fuji/pro_160s_datasheet.pdf", 7, "Pro 160S", 160, 2004, "negative",
                              char_box=(46, 90, 290, 300),
                              x_tick_bbox=(65, 285, 290, 296), y_tick_bbox=(60, 95, 90, 285)),
    lambda: fuji_ocr_product("film/fuji/superia_reala_datasheet.pdf", 3, "Superia Reala", 100, 2000, "negative",
                              char_box=(46, 90, 290, 300),
                              x_tick_bbox=(65, 265, 290, 280), y_tick_bbox=(55, 100, 78, 270)),
    lambda: fuji_ocr_product("film/fuji/superia_xtra800_datasheet.pdf", 3, "Superia X-tra 800", 800, 2003, "negative",
                              char_box=(46, 245, 290, 400),
                              x_tick_bbox=(50, 388, 290, 400), y_tick_bbox=(45, 280, 65, 385)),
    lambda: fuji_ocr_dash_reversal_product("film/fuji/velvia_100_datasheet.pdf", 7, "Velvia 100", 100, 2005,
                                            char_box=(60, 168, 290, 350),
                                            x_tick_bbox=(78, 345, 290, 358), y_tick_bbox=(70, 168, 90, 350),
                                            legend_bbox=(90, 300, 145, 330)),
    lambda: fuji_ocr_dash_reversal_product("film/fuji/sensia_200_datasheet.pdf", 4, "Sensia 200", 200, 2003,
                                            char_box=(65, 100, 285, 290),
                                            x_tick_bbox=(95, 288, 285, 300), y_tick_bbox=(68, 98, 90, 288),
                                            legend_bbox=(85, 240, 140, 280),
                                            stroke_rgb=(0.137, 0.122, 0.125), stroke_tol=0.03),
    lambda: fuji_ocr_dash_reversal_product("film/fuji/sensia_400_datasheet.pdf", 4, "Sensia 400", 400, 2003,
                                            char_box=(75, 105, 285, 290),
                                            x_tick_bbox=(95, 288, 285, 300), y_tick_bbox=(78, 105, 95, 288),
                                            legend_bbox=(90, 240, 145, 280),
                                            stroke_rgb=(0.137, 0.122, 0.125), stroke_tol=0.03),
]

# NOT ADDED: film/fuji/True_Definition_DataSheet.pdf ("FUJICOLOR TRUE
# DEFINITION 400 [CH]") -- confirmed a rebrand of Superia X-tra 400, not a
# distinct product: both datasheets carry the same "[CH]" product code and
# CN-16 process. Its own chart data digitizes cleanly (checked) but values
# are close-not-identical to Superia X-tra 400's, consistent with ordinary
# batch-to-batch variation between two printings of the same base film, not
# a real emulsion difference -- treated as a duplicate, same convention as
# Kodak's duplicate-year files.


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
