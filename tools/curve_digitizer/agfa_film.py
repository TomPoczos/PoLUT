"""
Digitizes Agfa film datasheets (film/agfa/*.pdf) into
consolidated-data/film/photography/{reversal,negative}/agfa/.

Corpus: 3 files. `agfa_films.pdf` is a multi-product brochure (not yet
split/attempted, see BLOCKED.md). `agfapanapx25.pdf` (APX 25 B&W negative)
is a multilingual (German/English/French/Spanish) datasheet whose one real
chart is an MTF/spectral panel, not a characteristic curve (see BLOCKED.md).
`agfa_scala.pdf` (SCALA 200x PROFESSIONAL, B&W reversal film for the AGFA
SCALA slide process) has 2 real, cleanly vector-extractable charts, both
digitized here.

`agfa_scala.pdf` page 1 ("Density curve"): a reversal film's characteristic
curve (density DECREASES with exposure), with 5 real curves -- Standard
process plus Push 1/2/3 and Pull 1 -- distinguished by DASH PATTERN with a
shared inline legend (Strategy B, vector_stroke_dash), the same mechanism
used for several Kodak B&W dev-time charts, first time seen needed outside
Kodak. Real gotcha: this file's ink color is the same "rich black"
(0.137, 0.122, 0.125) seen elsewhere in this corpus, not pure (0,0,0) --
using pure black with the default tol=0.05 matched zero drawings. A second,
more important gotcha: dash_regex + stroke_rgb alone matched THREE
same-color, same-dash=[] objects for the "Standard" (solid) curve -- the
outer plot frame (width 0.499) and the gridlines (width 0.3, 17 items)
both also have dash=[] and this file's rich-black color, contaminating the
extracted trace until `width=0.998, width_tol=0.05` (matching the real
curve strokes' own width, distinct from both frame and gridline widths)
was added to every CurveSpec. Verified quantitatively, not just visually:
each curve's fitted max density (Pull1 3.12, Push1 2.79, Push2 2.50, Push3
2.22) matches the companion "Contrast/maximum density" chart on the same
page (~3.1/2.75-2.8/2.5/2.2-2.25) to within rounding -- independent
cross-check the same page's own data agrees with itself.

Same page's "Spectral sensitivity" panel (single curve, real tick text,
no label needed) uses the same single-curve template as most Ilford B&W
films -- Strategy D with one label_position_override anchor.

Usage: uv run agfa_film.py
"""

from pathlib import Path

from digitizer_core import ChartSpec, CurveSpec
from product import ProductSpec, digitize_product, run_products_parallel

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")

_RICH_BLACK = (0.13669031858444214, 0.12195010483264923, 0.1252918243408203)


def agfa_scala_200x_product():
    pdf_stub = "film/agfa/agfa_scala.pdf"
    page_index = 1

    density_chart = ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="characteristic_curve",
        x_tick_regex=r"^[+-]?\d(\.0)?$", y_tick_regex=r"^[+-]?\d(\.0)?$",
        x_label="log_exposure_lux_seconds", y_label="density_diffuse_visual",
        x_tick_bbox=(20, 695, 275, 720), y_tick_bbox=(20, 563, 63, 700),
        curves=[
            CurveSpec("standard", stroke_rgb=_RICH_BLACK, tol=0.05,
                      dash_regex=r"^\[\] 0$", width=0.998, width_tol=0.05),
            CurveSpec("pull1", stroke_rgb=_RICH_BLACK, tol=0.05,
                      dash_regex=r"^\[ 3\.991 \.998 \.998 \.998 \] 0$", width=0.998, width_tol=0.05),
            CurveSpec("push1", stroke_rgb=_RICH_BLACK, tol=0.05,
                      dash_regex=r"^\[ 3\.991 \.998 \] 0$", width=0.998, width_tol=0.05),
            CurveSpec("push2", stroke_rgb=_RICH_BLACK, tol=0.05,
                      dash_regex=r"^\[ 1\.995 \.998 \] 0$", width=0.998, width_tol=0.05),
            CurveSpec("push3", stroke_rgb=_RICH_BLACK, tol=0.05,
                      dash_regex=r"^\[ \.998 \.998 \] 0$", width=0.998, width_tol=0.05),
        ],
        film_id="_unused", extraction_method="vector_stroke_dash",
        region_bbox=(20, 563, 275, 722), monotonic_direction="decreasing", min_trace_points=4,
        metadata={"curve_dimension": "push_pull_process", "process": "AGFA SCALA process",
                  "curve_names": ["standard", "pull1", "push1", "push2", "push3"]},
    )

    spectral_box = (298, 520.5, 535, 708.5)
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="spectral_sensitivity",
        x_tick_regex=r"^\d00$", y_tick_regex=r"^-?\d(\.0)?$",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec("sensitivity", label_position_override=(spectral_box[2] - 15, spectral_box[1] + 15))],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=spectral_box, monotonic_direction=None, min_trace_points=8,
    )

    return ProductSpec(
        brand="agfa", product_name="Scala 200x Professional", application_area="photography",
        film_type="reversal", medium="bw", iso=200, year=2000,
        layer_order=["density"], source_pdf=pdf_stub, charts=[density_chart, spectral_chart],
        digitizer_notes="B&W reversal film for the AGFA SCALA process. Characteristic curve chart has "
                         "5 real curves (Standard + Push 1/2/3 + Pull 1) distinguished by dash pattern "
                         "with a shared inline legend (Strategy B, vector_stroke_dash) -- first non-Kodak "
                         "file in this corpus needing dash-pattern discrimination. Verified quantitatively "
                         "against the same page's own 'Contrast/maximum density' chart (independent "
                         "cross-check, not just visual QA overlay): fitted max densities match to within "
                         "rounding. Spectral sensitivity chart uses the single-curve template (Strategy D, "
                         "no label needed).",
    )


def agfa_apx25_product():
    """Multilingual (German/English/French/Spanish) datasheet. Page 1 has 4
    real charts: Spectral sensitivity and Density curve (both digitized,
    same single-curve template as Scala's spectral panel), Sharpness (MTF,
    not a tracked chart type, skipped same as every other MTF panel in this
    corpus) and Gamma-time curves (5 developers' contrast vs. development
    time -- real data, but a genuinely different chart shape from
    characteristic_curve/spectral_sensitivity/reciprocity, and 2 of its 5
    curves visually coincide, RODINAL SPECIAL/STUDIONAL LIQUID -- confirmed
    not a rendering artifact, the processing-times table on this same page
    gives both developers identical times at every temperature. Not
    digitized this pass -- real future work if this chart type becomes a
    priority, not attempted here to keep pace with the rest of the vendor
    survey."""
    pdf_stub = "film/agfa/agfapanapx25.pdf"
    page_index = 1

    density_box = (35, 492.5, 290, 645)
    density_chart = ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="characteristic_curve",
        x_tick_regex=r"^[+-]?\d(\.0)?$", y_tick_regex=r"^[+-]?\d(\.0)?$",
        x_label="log_exposure_lux_seconds", y_label="density_diffuse_visual",
        curves=[CurveSpec("density", label_position_override=(density_box[2] - 15, density_box[1] + 70))],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=density_box, monotonic_direction="increasing", min_trace_points=8,
        metadata={"curve_dimension": "single_representative_curve"},
    )

    spectral_box = (35, 76, 290, 285)
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="spectral_sensitivity",
        x_tick_regex=r"^\d00$", y_tick_regex=r"^-?\d(\.0)?$",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec("sensitivity", label_position_override=(spectral_box[2] - 15, spectral_box[1] + 15))],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=spectral_box, monotonic_direction=None, min_trace_points=8,
    )

    return ProductSpec(
        brand="agfa", product_name="APX 25", application_area="photography",
        film_type="negative", medium="bw", iso=25, year=1995,
        layer_order=["density"], source_pdf=pdf_stub, charts=[density_chart, spectral_chart],
        digitizer_notes="B&W negative film, multilingual datasheet (German/English/French/Spanish). "
                         "Single representative characteristic curve (no specific developer identified in "
                         "the chart itself -- the sheet lists 5 developers' speed/time separately) and a "
                         "real spectral sensitivity curve, both the single-curve template (Strategy D, no "
                         "label needed). This sheet's 'Gamma-time curves' panel (5 developers' contrast "
                         "vs. development time) is real data but NOT digitized -- a genuinely different "
                         "chart shape from this project's tracked chart types, and 2 of its 5 curves "
                         "visually coincide (RODINAL SPECIAL/STUDIONAL LIQUID, confirmed real via the "
                         "processing-times table on the same page, not a rendering artifact).",
    )


def _apx_brochure_product(product_name, iso, year, granularity_rms, col_box_x0):
    """Shared builder for the 3 AGFAPAN APX products' mini-panels on
    `film/agfa/agfa_films.pdf` page 9 (a 1998 multi-product 'Range of Films
    PROFESSIONAL' brochure): 3 columns (APX 25/100/400), each with the same
    4 chart types as the standalone `agfapanapx25.pdf` sheet, at the same
    row y-coordinates, just shifted in x by a constant column width
    (~176.1pt) -- confirmed by checking each column's own tick-word
    positions individually, not assumed from spacing alone.
    AGFAPAN APX 25's own mini-panel here is a confirmed duplicate of the
    standalone `agfapanapx25.pdf` sheet (same shape, same source figure) --
    not re-added as a separate product; APX 100 and APX 400 are genuinely
    NEW products, first captured here."""
    pdf_stub = "film/agfa/agfa_films.pdf"
    page_index = 9
    density_box = (col_box_x0, 216.8, col_box_x0 + 159, 308)
    spectral_box = (col_box_x0, 72.6, col_box_x0 + 159, 192)

    density_chart = ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="characteristic_curve",
        x_tick_regex=r"^[+-]?\d(\.0)?$", y_tick_regex=r"^[+-]?\d(\.0)?$",
        x_label="log_exposure_lux_seconds", y_label="density_diffuse_visual",
        curves=[CurveSpec("density", label_position_override=(density_box[2] - 15, density_box[1] + 15))],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=density_box, monotonic_direction="increasing", min_trace_points=8,
        metadata={"curve_dimension": "single_representative_curve"},
    )
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="spectral_sensitivity",
        x_tick_regex=r"^\d00$", y_tick_regex=r"^-?\d(\.0)?$",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec("sensitivity", label_position_override=(spectral_box[2] - 15, spectral_box[1] + 15))],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=spectral_box, monotonic_direction=None, min_trace_points=8,
    )

    return ProductSpec(
        brand="agfa", product_name=product_name, application_area="photography",
        film_type="negative", medium="bw", iso=iso, year=year,
        layer_order=["density"], source_pdf=pdf_stub, charts=[density_chart, spectral_chart],
        digitizer_notes=f"B&W negative film, from the 1998 'AGFA Range of Films PROFESSIONAL' brochure "
                         f"(page 9 of 3, one column per APX speed). Granularity RMS(x1000)={granularity_rms} "
                         f"(REFINAL, 6min, 20C) per this sheet's own text. Same single-curve-template "
                         f"characteristic curve + spectral sensitivity as AGFAPAN APX 25's standalone sheet "
                         f"(agfapanapx25.pdf) -- this product has no standalone datasheet of its own in "
                         f"this corpus, only this brochure panel. This page's 'Sharpness' (MTF) and "
                         f"'Gamma-time curves' panels are not digitized, same reasons as APX 25's "
                         f"standalone sheet.",
    )


def agfa_apx100_product():
    return _apx_brochure_product("APX 100", 100, 1998, 9.0, 201)


def agfa_apx400_product():
    return _apx_brochure_product("APX 400", 400, 1998, 14.0, 377)


PRODUCTS = [
    agfa_scala_200x_product,
    agfa_apx25_product,
    agfa_apx100_product,
    agfa_apx400_product,
]


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
