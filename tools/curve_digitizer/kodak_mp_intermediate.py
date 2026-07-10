"""
Digitizes Kodak motion-picture INTERMEDIATE/DUPLICATING/PRINT stock
datasheets from motionpicture/kodak_2018/ into
consolidated-data/film/motion-picture/{negative,intranegative,intrapositive}/kodak/.

This vendor folder (a 2018-era reprint batch, mostly TI-numbered sheets
re-issued 2015-2016) turned out to hold several GENUINELY NEW products not
covered by the main color-negative/reversal/B&W batches already digitized
from motionpicture/kodak/ -- duplicating stocks, internegative stocks, and
digital-intermediate stocks explicitly referenced (but not digitized) in
this project's own CLAUDE.md (2234/5234 Fine Grain Duplicating Panchromatic
Negative -- the "second real duplicating material" considered and rejected
for generate_film_looks.py's own internegative cascade, see that file's
GAMMA_CORRECT_TARGET comment block).

Same Strategy D (vector_position) template family as kodak_mp.py/
kodak_mp_bw.py -- inline B/G/R or dev-time labels, real signed or
overline-minus x-axis conventions, no new extraction strategy needed, just
per-file box/anchor discovery.

Usage: uv run kodak_mp_intermediate.py
"""

from pathlib import Path

from digitizer_core import (
    ChartSpec, CurveSpec, curves_by_peak_x_with_envelope, digitize_chart, mp_dye_density_curves,
)
from kodak_common import COLOR_NEG_CHAR_LABELS, overline_negative_calib
from product import ProductSpec, digitize_product, run_products_parallel

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")


def fine_grain_duplicating_positive_2366_product():
    """EASTMAN Fine Grain Duplicating POSITIVE Film 2366 -- B&W, 5-curve
    development-time family (12/9/6.5/5/4 min), real inline labels at the
    chart's right edge, well separated. Overline-minus x-axis convention."""
    pdf_stub = "motionpicture/kodak_2018/2366_TI0265.pdf"
    box = (330, 434.3, 570, 655)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=1, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_diffuse_visual",
        curves=[
            CurveSpec("12min", label_position_override=(460, 487.8)),
            CurveSpec("9min", label_position_override=(460, 499.2)),
            CurveSpec("6.5min", label_position_override=(505, 567.2)),
            CurveSpec("5min", label_position_override=(490, 579.5)),
            CurveSpec("4min", label_position_override=(478, 591.1)),
        ],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, monotonic_direction="increasing", min_trace_points=50,
        x_tick_bbox=(340, 624, 555, 642),
        metadata={"developer": "KODAK Developer D-96", "curve_dimension": "development_time",
                  "curve_names": ["12min", "9min", "6.5min", "5min", "4min"]},
    )
    char_chart.x_axis_calib_override = overline_negative_calib(
        PDF_ROOT / pdf_stub, 1, (340, 624, 555, 642), tick_regex=r"-?\d\.0")
    return ProductSpec(
        brand="kodak", product_name="Fine Grain Duplicating Positive (2366)",
        application_area="motion-picture", film_type="intrapositive", medium="bw",
        iso=None, year=2015, layer_order=["density"], source_pdf=pdf_stub, charts=[char_chart],
        digitizer_notes="B&W duplicating positive (print-from-negative intermediate stock), 5-curve "
                         "development-time family, KODAK Developer D-96. Overline-minus x-axis "
                         "convention. No spectral-sensitivity chart on this sheet (duplicating stocks "
                         "print from another film's image, not exposed directly to a scene).",
    )


def fine_grain_duplicating_negative_5234_product():
    """EASTMAN Fine Grain Duplicating Panchromatic NEGATIVE Film 2234/5234
    -- explicitly referenced (but never digitized until now) in this
    project's own generate_film_looks.py CLAUDE.md as a real candidate
    duplicating-material stage considered and rejected for the
    internegative cascade. 3-curve dev-time family (12/8/4 min); the real
    "8min" curve could not be reliably isolated from its own small
    fragments (mixed in with a small inset gamma-plot inside the same
    region_bbox) so only 12min/4min are shipped. Spectral-sensitivity
    chart (2 curves, D=0.3/D=1.0 above gross fog) is clean and included."""
    pdf_stub = "motionpicture/kodak_2018/5234_Ti0147.pdf"
    box = (330, 64.8, 570, 283)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=1, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_status_m_blue",
        curves=[
            CurveSpec("12min", label_position_override=(482, 164)),
            CurveSpec("4min", label_position_override=(482, 197.5)),
        ],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, monotonic_direction="increasing", min_trace_points=30,
        x_tick_bbox=(340, 258, 565, 270),
        metadata={"developer": "KODAK Developer D-96", "curve_dimension": "development_time",
                  "curve_names": ["12min", "4min"]},
    )
    char_chart.x_axis_calib_override = overline_negative_calib(
        PDF_ROOT / pdf_stub, 1, (340, 258, 565, 270), tick_regex=r"-?\d\.0")
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=1, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[
            CurveSpec("d0.3_above_gross_fog", label_position_override=(463, 374)),
            CurveSpec("d1.0_above_gross_fog", label_position_override=(460, 424)),
        ],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(330, 314, 570, 485), monotonic_direction=None, min_trace_points=8,
    )
    return ProductSpec(
        brand="kodak", product_name="Fine Grain Duplicating Panchromatic Negative (2234/5234)",
        application_area="motion-picture", film_type="intranegative", medium="bw",
        iso=None, year=2015, layer_order=["density"], source_pdf=pdf_stub,
        charts=[char_chart, spectral_chart],
        digitizer_notes="B&W duplicating negative -- referenced in this project's own "
                         "generate_film_looks.py CLAUDE.md (GAMMA_CORRECT_TARGET comment block) as a "
                         "real candidate duplicating-material stage considered and rejected for the "
                         "internegative cascade; digitized here for the consolidated-data corpus "
                         "regardless (that rejection was about generate_film_looks.py's specific "
                         "cascade design, not about this being uninteresting real data). "
                         "8min curve dropped: its real trace fragments could not be reliably "
                         "separated from a small inset 'Gross Fog vs Development Time' plot sharing "
                         "the same region_bbox. 12min/4min and both spectral curves are clean.",
    )


def digital_separation_2237_product():
    """KODAK VISION3 Digital Separation Film 2237 -- 2 development-time
    families on the SAME page (D-96: 6/8/10/12 min; D-97: 3/4/5/6/7 min),
    both with real, well-separated inline labels at the chart's right
    edge. Real signed x-axis (no overline convention, unlike most other
    products in this module)."""
    pdf_stub = "motionpicture/kodak_2018/2237_TI2659.pdf"
    box1 = (335, 111.8, 570, 318)
    chart1 = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="characteristic_curve_d96",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_digital_exposure_lux_seconds", y_label="density_status_m",
        curves=[
            CurveSpec("12min", label_position_override=(545, 174)),
            CurveSpec("10min", label_position_override=(545, 182.5)),
            CurveSpec("8min", label_position_override=(545, 191)),
            CurveSpec("6min", label_position_override=(545, 206.5)),
        ],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box1, monotonic_direction="increasing", min_trace_points=30,
        metadata={"developer": "KODAK Developer D-96", "curve_dimension": "development_time",
                  "curve_names": ["12min", "10min", "8min", "6min"]},
    )
    box2 = (335, 362, 570, 564)
    chart2 = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="characteristic_curve_d97",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_digital_exposure_lux_seconds", y_label="density_status_m",
        curves=[
            CurveSpec("7min", label_position_override=(545, 382.5)),
            CurveSpec("6min", label_position_override=(545, 389)),
            CurveSpec("5min", label_position_override=(545, 396.5)),
            CurveSpec("4min", label_position_override=(545, 405)),
            CurveSpec("3min", label_position_override=(545, 416)),
        ],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box2, monotonic_direction="increasing", min_trace_points=30,
        metadata={"developer": "KODAK Developer D-97", "curve_dimension": "development_time",
                  "curve_names": ["7min", "6min", "5min", "4min", "3min"]},
    )
    return ProductSpec(
        brand="kodak", product_name="VISION3 Digital Separation Film (2237)",
        application_area="motion-picture", film_type="intrapositive", medium="bw",
        iso=None, year=2015, layer_order=["density"], source_pdf=pdf_stub,
        charts=[chart1, chart2],
        digitizer_notes="B&W digital-separation (archival preservation) film -- exposed via green "
                         "ARRILASER per this sheet's own text, 2 independent development-time "
                         "families on the same page (D-96: 12/10/8/6 min; D-97: 7/6/5/4/3 min), both "
                         "clean with 0 monotonicity violations. Real signed x-axis ticks, no overline "
                         "convention needed.",
    )


def color_print_2383_product():
    """KODAK VISION Color Print Film 2383 -- a positive PRINT film (not a
    camera negative), Process ECP-2D. Real signed x-axis, standard B/G/R
    inline labels."""
    pdf_stub = "motionpicture/kodak_2018/2383_ti2397.pdf"
    box = (60, 64.8, 300, 290)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=4, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_status_a",
        curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_CHAR_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, monotonic_direction="increasing", min_trace_points=8,
    )
    dd_box = (315, 26, 570, 258)
    dye_density_chart = ChartSpec(
        pdf=pdf_stub, page_index=5, chart_id="spectral_dye_density",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.\d{1,2}",
        x_label="wavelength_nm", y_label="diffuse_spectral_density",
        curves=curves_by_peak_x_with_envelope(PDF_ROOT / pdf_stub, 5, dd_box,
                                               ["yellow", "magenta", "cyan"], "visual_neutral"),
        film_id="_unused", extraction_method="vector_position",
        region_bbox=dd_box,
    )
    return ProductSpec(
        brand="kodak", product_name="VISION Color Print Film (2383)",
        application_area="motion-picture", film_type="intrapositive", medium="color",
        iso=None, year=2015,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[char_chart, dye_density_chart],
        digitizer_notes="Color release-print film (Process ECP-2D), not a camera negative -- prints "
                         "directly from an internegative or digital intermediate for theatrical "
                         "projection. Clean, real signed x-axis, standard inline B/G/R labels. "
                         "Spectral-Dye-Density uses the reversal-film 4-curve convention (Yellow/"
                         "Magenta/Cyan/Visual Neutral, no D-min composite) -- a print film like a "
                         "reversal original has no camera-exposure D-min concept.",
    )


def color_internegative_2273_product():
    """KODAK Color Internegative Film 2273/3273, ESTAR Base -- a DIFFERENT
    real internegative stock from INTERNEGATIVE_II_CURVES (EASTMAN Color
    Internegative II Film 5272/7272) already used throughout
    generate_film_looks.py's own reversal-print cascade. Real signed
    x-axis, standard B/G/R inline labels."""
    pdf_stub = "motionpicture/kodak_2018/5273_ti2655.pdf"
    box = (60, 506, 300, 720)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_status_m",
        curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_CHAR_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, monotonic_direction="increasing", min_trace_points=8,
    )
    dd_box = (40, 183, 300, 411)
    dye_density_chart = ChartSpec(
        pdf=pdf_stub, page_index=3, chart_id="spectral_dye_density",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.\d{1,2}",
        x_label="wavelength_nm", y_label="diffuse_spectral_density",
        curves=mp_dye_density_curves(PDF_ROOT / pdf_stub, 3, dd_box),
        film_id="_unused", extraction_method="vector_position",
        region_bbox=dd_box,
    )
    return ProductSpec(
        brand="kodak", product_name="Color Internegative Film (2273/3273, ESTAR Base)",
        application_area="motion-picture", film_type="intranegative", medium="color",
        iso=None, year=2015,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[char_chart, dye_density_chart],
        digitizer_notes="Real internegative duplicating stock, Process ECN-2 -- a DIFFERENT product "
                         "from EASTMAN Color Internegative II Film 5272/7272 "
                         "(INTERNEGATIVE_II_CURVES, already used throughout generate_film_looks.py's "
                         "own reversal-print cascade). Clean, real signed x-axis, standard inline "
                         "B/G/R labels. Spectral-Dye-Density uses the motion-picture-negative 5-curve "
                         "convention (d_min/midscale_neutral/Yellow/Magenta/Cyan).",
    )


def high_contrast_positive_5363_product():
    """EASTMAN High Contrast Positive Film 5363 -- B&W, 4-curve
    development-time family (8/6/3.5/2 min), real inline labels on the
    LEFT side of the chart (unusual for this vendor group) plus a clean
    single-curve spectral-sensitivity chart. Real signed x-axis (no
    overline convention)."""
    pdf_stub = "motionpicture/kodak_2018/5363_ti2167.pdf"
    box = (50, 381.8, 300, 600)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=1, chart_id="characteristic_curve",
        x_tick_regex=r"\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_diffuse_visual",
        curves=[
            CurveSpec("8min", label_position_override=(115, 472)),
            CurveSpec("6min", label_position_override=(112, 486)),
            CurveSpec("3.5min", label_position_override=(148, 531)),
            CurveSpec("2min", label_position_override=(130, 546)),
        ],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, monotonic_direction="increasing", min_trace_points=30,
        metadata={"developer": "KODAK Developer D-97", "curve_dimension": "development_time",
                  "curve_names": ["8min", "6min", "3.5min", "2min"]},
    )
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=1, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec("sensitivity", label_position_override=(425, 90))],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(330, 43.8, 570, 220.6), monotonic_direction=None, min_trace_points=8,
        y_axis_calib_override=(-0.02679497429096888, 4.559712334555213),
    )
    return ProductSpec(
        brand="kodak", product_name="High Contrast Positive (5363)",
        application_area="motion-picture", film_type="intrapositive", medium="bw",
        iso=None, year=2015, layer_order=["density"], source_pdf=pdf_stub,
        charts=[char_chart, spectral_chart],
        digitizer_notes="B&W high-contrast print/positive film. All 4 development-time curves "
                         "converge to nearly the same Dmax (~2.9-3.0) near the shoulder -- confirmed "
                         "via QA overlay as a real characteristic of this high-contrast material, not "
                         "a mislabeling artifact. Spectral-sensitivity chart's single curve uses the "
                         "overline-minus y-axis convention (handled via explicit y_axis_calib_override).",
    )


def vision_color_intermediate_5242_product():
    """KODAK VISION Color Intermediate Film 5242/2242/3242 -- a real
    intermediate (interpositive/duplicating) stock, predecessor to the
    VISION3 digital-intermediate 5254 below. Overline-minus x-axis."""
    pdf_stub = "motionpicture/kodak_2018/Ti2461.pdf"
    box = (330, 130.8, 570, 352.2)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=3, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_status_m",
        curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_CHAR_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, monotonic_direction="increasing", min_trace_points=8,
        x_tick_bbox=(350, 330, 560, 342),
    )
    char_chart.x_axis_calib_override = overline_negative_calib(
        PDF_ROOT / pdf_stub, 3, (350, 330, 560, 342), tick_regex=r"-?\d\.0")
    return ProductSpec(
        brand="kodak", product_name="VISION Color Intermediate Film (5242/2242/3242)",
        application_area="motion-picture", film_type="intrapositive", medium="color",
        iso=None, year=2016,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[char_chart],
        digitizer_notes="Color intermediate (interpositive/duplicating) stock, Process ECN-2. "
                         "Overline-minus x-axis convention. Predecessor to the VISION3 digital "
                         "intermediate 5254 (vision3_color_digital_intermediate_5254_product) -- that "
                         "sheet's own text explicitly contrasts the two, noting 5254 is NOT designed "
                         "for duplicating purposes the way this film is. Spectral-Dye-Density panel "
                         "(page 4) NOT included: this file uniquely uses a LEGEND BOX (not just inline "
                         "labels) for Cyan/Magenta/Yellow/Midscale-Neutral/Minimum-Density, and the "
                         "legend's own \"Yellow\" text sits earlier in the PDF's internal word order "
                         "than the real inline curve label -- find_label_position returns the first "
                         "match, so it grabbed the legend swatch instead. Tried dropping yellow and "
                         "using label_position_override, but assign_traces_to_labels_exclusive's "
                         "rank-by-y strategy reassigns ALL labels relative to each other, so both fixes "
                         "just moved the mismatch onto a different curve instead of fixing it -- not a "
                         "quick fix, real follow-up work.",
    )


def vision3_color_digital_intermediate_5254_product():
    """KODAK VISION3 Color Digital Intermediate Film 5254/2254 -- optimized
    for ARRILASER/recorder exposure, NOT for duplicating (per this sheet's
    own text, explicitly contrasted with 5242 above). Real signed x-axis,
    clean B/G/R."""
    pdf_stub = "motionpicture/kodak_2018/TI5254.pdf"
    box = (340, 235.8, 570, 450)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_status_m",
        curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_CHAR_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, monotonic_direction="increasing", min_trace_points=8,
    )
    dd_box = (313, 195, 525, 435)
    dye_density_chart = ChartSpec(
        pdf=pdf_stub, page_index=3, chart_id="spectral_dye_density",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.\d{1,2}",
        x_label="wavelength_nm", y_label="diffuse_spectral_density",
        curves=mp_dye_density_curves(PDF_ROOT / pdf_stub, 3, dd_box),
        film_id="_unused", extraction_method="vector_position",
        region_bbox=dd_box,
    )
    return ProductSpec(
        brand="kodak", product_name="VISION3 Color Digital Intermediate Film (5254/2254)",
        application_area="motion-picture", film_type="intrapositive", medium="color",
        iso=None, year=2012,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[char_chart, dye_density_chart],
        digitizer_notes="Digital-intermediate stock exposed via ARRILASER recorder, Process ECN-2 -- "
                         "this sheet's own text explicitly states it is NOT designed for duplicating "
                         "purposes and NOT for white-light (tungsten) exposure, unlike its VISION "
                         "(non-3) predecessor 5242. Clean, real signed x-axis, standard inline labels. "
                         "Spectral-Dye-Density panel labels each curve as two words (\"Yellow Dye\", "
                         "\"Magenta Dye\", \"Cyan Dye\") rather than the bare color name used elsewhere "
                         "in this project -- MP_DYE_DENSITY_LABELS' `^Yellow$`/etc regexes still match "
                         "since \"Dye\" is a separate word token, not part of the same word.",
    )


PRODUCTS = [
    fine_grain_duplicating_positive_2366_product,
    fine_grain_duplicating_negative_5234_product,
    digital_separation_2237_product,
    color_print_2383_product,
    color_internegative_2273_product,
    high_contrast_positive_5363_product,
    vision_color_intermediate_5242_product,
    vision3_color_digital_intermediate_5254_product,
]


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
