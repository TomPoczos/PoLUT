"""
Digitizes Kodak motion-picture datasheets found in motionpicture/kodak/lab/
into consolidated-data/film/motion-picture/{intrapositive,intranegative}/kodak/.

This folder's name suggested "lab/processing docs, probable out-of-scope"
in earlier session notes -- that guess was WRONG, confirmed by actually
opening the files: it holds 5 real product datasheets (with real embedded
vector charts), not lab-chemistry documentation. 4 are genuinely new
products; `lab_h12383t.pdf` is an older (2004/2005) printing of the same
"2383" VISION Color Print Film already digitized from the newer 2015
kodak_2018/2383_ti2397.pdf sheet in kodak_mp_intermediate.py, so it is
NOT re-digitized here (see BLOCKED.md's duplicates section).

Same Strategy D (vector_position) template family as kodak_mp.py/
kodak_mp_bw.py/kodak_mp_intermediate.py.

Usage: uv run kodak_mp_lab.py
"""

from pathlib import Path

from digitizer_core import ChartSpec, CurveSpec, curves_by_peak_x_with_envelope, digitize_chart
from kodak_common import (
    COLOR_NEG_CHAR_LABELS, COLOR_NEG_SPECTRAL_LABELS, DYE_DENSITY_LABELS,
    overline_negative_calib,
)
from product import ProductSpec, digitize_product, run_products_parallel

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")


def exr_color_intermediate_5244_product():
    """EASTMAN EXR Color Intermediate Film 2244/5244/7244 -- predecessor to
    the VISION Color Intermediate 5242 (kodak_mp_intermediate.py). Overline
    x-axis, clean B/G/R inline labels."""
    pdf_stub = "motionpicture/kodak/lab/h15244.pdf"
    box = (310, 398.7, 570, 620)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=1, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_status_m",
        curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_CHAR_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, monotonic_direction="increasing", min_trace_points=8,
        x_tick_bbox=(340, 589, 545, 610),
    )
    char_chart.x_axis_calib_override = overline_negative_calib(
        PDF_ROOT / pdf_stub, 1, (340, 589, 545, 610), tick_regex=r"-?\d\.0")
    dye_density_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="spectral_dye_density",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.\d{1,2}",
        x_label="wavelength_nm", y_label="diffuse_spectral_density",
        curves=[CurveSpec(n, label_regex=r) for n, r in DYE_DENSITY_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(55, 25, 295, 265),
    )
    return ProductSpec(
        brand="kodak", product_name="EXR Color Intermediate Film (2244/5244/7244)",
        application_area="motion-picture", film_type="intrapositive", medium="color",
        iso=None, year=1998,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[char_chart, dye_density_chart],
        digitizer_notes="Color intermediate stock, Process ECN-2 -- predecessor to VISION Color "
                         "Intermediate Film 5242 (kodak_mp_intermediate.py's vision_color_"
                         "intermediate_5242_product). Overline-minus x-axis convention. "
                         "Spectral-Dye-Density uses the still-photography-negative 2-curve convention "
                         "(Minimum/Midscale, no separate Y/M/C) -- confirmed against the real panel "
                         "labels, not assumed from the other motion-picture intermediate/print films "
                         "in this file.",
    )


def fine_grain_release_positive_5302_product():
    """EASTMAN Fine Grain Release Positive Film 5302/7302 -- B&W release
    print film, 5-curve development-time family (9/7/5/3.5/2 min). Real
    gotcha: label text sits to the right of each curve's own endpoint with
    a gap, and the 5 real curves terminate at DIFFERENT x (less-developed
    stock needs more exposure to reach a given density, so its curve
    extends further right) -- anchoring on each trace's own real endpoint
    (found via direct trace inspection) rather than the label text
    position itself was needed to get correct assignment; anchoring on
    label position directly scrambled the 5 curves' identities."""
    pdf_stub = "motionpicture/kodak/lab/H-1-5302.pdf"
    box = (60, 44.8, 300, 255)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_diffuse_visual",
        curves=[
            CurveSpec("9min", label_position_override=(189.3, 79.0)),
            CurveSpec("7min", label_position_override=(195.6, 77.8)),
            CurveSpec("5min", label_position_override=(206.4, 74.4)),
            CurveSpec("3.5min", label_position_override=(217.9, 79.0)),
            CurveSpec("2min", label_position_override=(234.0, 88.3)),
        ],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, monotonic_direction="increasing", min_trace_points=30,
        x_tick_bbox=(75, 231, 295, 251),
        metadata={"developer": "KODAK Developer D-97", "curve_dimension": "development_time",
                  "curve_names": ["9min", "7min", "5min", "3.5min", "2min"]},
    )
    char_chart.x_axis_calib_override = overline_negative_calib(
        PDF_ROOT / pdf_stub, 2, (75, 231, 295, 251), tick_regex=r"-?\d\.0")
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[
            CurveSpec("d0.3_above_gross_fog", label_position_override=(175.5, 353)),
            CurveSpec("d1.0_above_gross_fog", label_position_override=(175.5, 361)),
        ],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(60, 285.8, 300, 458), monotonic_direction=None, min_trace_points=8,
        y_axis_calib_override=(-0.02675902839736549, 8.817887518993393),
    )
    return ProductSpec(
        brand="kodak", product_name="Fine Grain Release Positive (5302/7302)",
        application_area="motion-picture", film_type="intrapositive", medium="bw",
        iso=None, year=1997, layer_order=["density"], source_pdf=pdf_stub,
        charts=[char_chart, spectral_chart],
        digitizer_notes="B&W release-print film, 5-curve development-time family. Curve identity "
                         "anchored on each real trace's own endpoint position (found via direct "
                         "extract_traces_in_region inspection), not the nearby label text position -- "
                         "anchoring on label position directly assigned curves in scrambled order "
                         "(caught by computing each curve's average slope and finding it didn't "
                         "monotonically track development time as expected).",
    )


def exr_color_print_5386_product():
    """EASTMAN EXR Color Print Film 5386/7386/2386/3386. B/G/R identified
    via a shared corner legend box (not per-curve touching labels) -- the
    3 traces came back with distinct, non-overlapping bounding boxes (no
    sanity warning), unlike the similar-looking h17251 case, so accepted
    as correctly matched."""
    pdf_stub = "motionpicture/kodak/lab/h15386.pdf"
    box = (60, 46.4, 300, 253)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_status_a",
        curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_CHAR_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, monotonic_direction="increasing", min_trace_points=8,
    )
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_SPECTRAL_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(330, 44.8, 570, 213),
        y_axis_calib_override=(-0.026759028397365485, 2.315443618433582),
    )
    dd_box = (50, 262, 295, 500)
    dye_density_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="spectral_dye_density",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.\d{1,2}",
        x_label="wavelength_nm", y_label="diffuse_spectral_density",
        curves=curves_by_peak_x_with_envelope(PDF_ROOT / pdf_stub, 2, dd_box,
                                               ["yellow", "magenta", "cyan"], "visual_neutral"),
        film_id="_unused", extraction_method="vector_position",
        region_bbox=dd_box,
    )
    return ProductSpec(
        brand="kodak", product_name="EXR Color Print Film (5386/7386/2386/3386)",
        application_area="motion-picture", film_type="intrapositive", medium="color",
        iso=None, year=1997,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[char_chart, spectral_chart, dye_density_chart],
        digitizer_notes="Color release-print film, Process ECP-2B. B/G/R identified via a shared "
                         "legend box rather than per-curve inline labels -- verified via the 3 "
                         "traces' distinct bounding boxes (no ambiguous-match sanity warning). "
                         "Spectral-Dye-Density uses the reversal/print-film 4-curve convention "
                         "(Yellow/Magenta/Cyan/Visual Neutral), same as VISION Color Print Film 2383 "
                         "in kodak_mp_intermediate.py -- a print film has no camera-exposure D-min.",
    )


def vision_premier_color_print_2393_product():
    """KODAK VISION Premier Color Print Film 2393 -- this sheet's own text
    notes its spectral sensitivity was specifically designed to match
    EXR Color Intermediate Film 5244/2244 (exr_color_intermediate_5244_
    product above) for better direct-print/duplicate-print consistency."""
    pdf_stub = "motionpicture/kodak/lab/lab_h12393t.pdf"
    box = (60, 102.8, 300, 310)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=4, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_status_a",
        curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_CHAR_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, monotonic_direction="increasing", min_trace_points=8,
    )
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=4, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_SPECTRAL_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(60, 416.8, 300, 589),
        y_axis_calib_override=(-0.026722707702995476, 12.304167257013328),
    )
    dd_box = (325, 436, 565, 680)
    dye_density_chart = ChartSpec(
        pdf=pdf_stub, page_index=4, chart_id="spectral_dye_density",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.\d{1,2}",
        x_label="wavelength_nm", y_label="diffuse_spectral_density",
        curves=curves_by_peak_x_with_envelope(PDF_ROOT / pdf_stub, 4, dd_box,
                                               ["yellow", "magenta", "cyan"], "visual_neutral"),
        film_id="_unused", extraction_method="vector_position",
        region_bbox=dd_box,
    )
    return ProductSpec(
        brand="kodak", product_name="VISION Premier Color Print Film (2393)",
        application_area="motion-picture", film_type="intrapositive", medium="color",
        iso=None, year=1998,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[char_chart, spectral_chart, dye_density_chart],
        digitizer_notes="Color release-print film, Process ECP-2B, no rem-jet backing. Clean, real "
                         "signed x-axis, standard inline B/G/R labels on both charts. "
                         "Spectral-Dye-Density uses the reversal/print-film 4-curve convention "
                         "(Yellow/Magenta/Cyan/Visual Neutral), same reasoning as EXR Color Print Film "
                         "5386 above -- a print film has no camera-exposure D-min.",
    )


PRODUCTS = [
    exr_color_intermediate_5244_product,
    fine_grain_release_positive_5302_product,
    exr_color_print_5386_product,
    vision_premier_color_print_2393_product,
]


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
