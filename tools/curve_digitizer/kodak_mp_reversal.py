"""
Digitizes Kodak motion-picture COLOR REVERSAL film datasheets into
consolidated-data/film/motion-picture/reversal/kodak/.

Same "Sensitometric Curves" (Camera Stops top axis + overline LOG EXPOSURE
bottom axis) + "Spectral-Sensitivity Curves" (Yellow-/Magenta-/Cyan-Forming
Layer) template as the color NEGATIVE motion-picture films in kodak_mp.py,
and reuses that file's real signed camera-stops convention -- but density
FALLS with exposure (a genuine reversal film, confirmed against the raw
digitized curve), so `vision_style_product()` itself can't be reused as-is:
that helper hardcodes `monotonic_direction="increasing"` for its
characteristic_curve ChartSpec, which would silently isotonic-project a
real decreasing S-curve down to a near-flat 2-point line (caught this way
on 7280, not by a crash -- confirmed via QA overlay showing the collapse,
then fixed by building the ChartSpec directly instead of through
vision_style_product).

Real per-file gotcha (7280): the characteristic-curve panel's y_tick_regex
(r"\\d\\.0", matching the real DENSITY axis) ALSO matches text in the
LOG EXPOSURE caption row directly below the chart (which prints the same
"4.0"/"2.0"/etc coincidentally) -- both rows sit inside one naturally-sized
region_bbox, so a naive fit_axis call picks up ticks from both rows and
produces a nonsense combined fit. Fixed with an explicit narrow
`y_tick_bbox` restricted to just the real DENSITY column.

Usage: uv run kodak_mp_reversal.py
"""

from pathlib import Path

from digitizer_core import ChartSpec, CurveSpec, curves_by_peak_x_with_envelope, digitize_chart
from kodak_common import (
    COLOR_NEG_CHAR_LABELS, COLOR_NEG_SPECTRAL_LABELS, overline_negative_calib,
)
from product import ProductSpec, digitize_product, run_products_parallel

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")


def ektachrome64t_reversal_product():
    pdf_stub = "motionpicture/kodak/7280-Ektachrome-64t-rev.pdf"
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=1, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d$", y_tick_regex=r"\d\.0",
        x_label="camera_stops", y_label="density_status_a",
        curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_CHAR_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(330, 65.8, 570, 290), monotonic_direction="decreasing",
        y_tick_bbox=(340, 85, 360, 275),
    )
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_SPECTRAL_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(330, 44.8, 570, 235),
    )
    dye_density_chart = ChartSpec(
        pdf=pdf_stub, page_index=3, chart_id="spectral_dye_density",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.\d{1,2}",
        x_label="wavelength_nm", y_label="diffuse_spectral_density",
        # Peak-position identification, not plain label-regex matching -- confirmed
        # (2026-07-10) that Kodak's inline Yellow/Magenta/Cyan labels are close enough in y
        # to trigger the same rotated-identity bug fixed corpus-wide; see
        # curves_by_peak_x_with_envelope's own docstring (digitizer_core.py). Fragmented (7
        # raw path objects for 4 real curves at default settings).
        curves=curves_by_peak_x_with_envelope(PDF_ROOT / pdf_stub, 3, (180, 26, 430, 265),
                                               ["yellow", "magenta", "cyan"], "visual_neutral",
                                               min_trace_points=4, cross_object_merge=True,
                                               merge_strategy="sequential_band"),
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(180, 26, 430, 265),
        min_trace_points=4, cross_object_merge=True, merge_strategy="sequential_band",
    )
    return ProductSpec(
        brand="kodak", product_name="Ektachrome 64T Reversal", application_area="motion-picture",
        film_type="reversal", medium="color", iso=64, year=2005,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[char_chart, spectral_chart, dye_density_chart],
        digitizer_notes="Color reversal motion-picture film (Process E-6), density falls with exposure "
                         "(monotonic_direction='decreasing') -- confirmed against the raw curve, not "
                         "assumed from the negative-film template. Built directly rather than through "
                         "kodak_mp.py's vision_style_product() since that helper hardcodes "
                         "monotonic_direction='increasing'.",
    )


def ektachrome_daylight_7239_product():
    """EASTMAN EKTACHROME Film (Daylight) 7239 -- another reversal color
    film, same overall template as 7280 but with an overline-minus x-axis
    (kodak_common.overline_negative_calib) rather than real signed camera
    stops. Real gotcha: 2 stray/duplicate tick candidates (one "0.0" from
    a different row, one stray point) sit inside a naive tick-search bbox
    and must be excluded via a tight x_tick_bbox, same lesson as 5263 in
    kodak_mp.py."""
    from kodak_common import overline_negative_calib
    pdf_stub = "motionpicture/kodak/h15239.pdf"
    char_box = (42, 44.8, 300, 255)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_status_a",
        curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_CHAR_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=char_box, monotonic_direction="decreasing", min_trace_points=8,
        x_tick_bbox=(76, 240, 290, 253),
    )
    char_chart.x_axis_calib_override = overline_negative_calib(
        PDF_ROOT / pdf_stub, 2, (76, 240, 290, 253), tick_regex=r"-?\d\.0")
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_SPECTRAL_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(330, 44.8, 570, 235),
        y_axis_calib_override=(-0.026461482228128226, 3.6437461028132554),
    )
    return ProductSpec(
        brand="kodak", product_name="Ektachrome Daylight (7239)", application_area="motion-picture",
        film_type="reversal", medium="color", iso=160, year=1996,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[char_chart, spectral_chart],
        digitizer_notes="Color reversal motion-picture film (Process VNF-1), density falls with "
                         "exposure. Overline-minus x-axis convention on the characteristic curve "
                         "(kodak_common.overline_negative_calib); spectral chart's y-axis also uses "
                         "the overline convention (handled via explicit y_axis_calib_override). "
                         "spectral_dye_density panel NOT included: unlike h17251's inline-label panel, "
                         "this one uses a boxed dash-pattern legend (Strategy D's rank-by-y label "
                         "matching produces systematically wrong assignments, confirmed via QA overlay) "
                         "-- same failure mode as 5277 (kodak_mp.py) and 7267_zh_CN below.",
    )


def ektachrome_highspeed_7251_product():
    """EASTMAN EKTACHROME High-Speed Daylight Film 7251. Real gotcha: the
    3 characteristic-curve traces (R/G/B) are so close together that a
    naive `assign_traces_to_labels_exclusive` match (even with hand-placed
    label_position_override anchors at the point of maximum separation,
    x=450) still collapses 2 of the 3 -- NOT because of a duplicate-
    drawing-object artifact (checked directly: all 3 traces have distinct,
    real y-values at x=450, unlike the genuine duplication seen on
    5218/kodak_mp.py), but because the assignment logic itself can't
    reliably separate 3 candidates this close. Rather than risk shipping a
    silently-swapped R/G pair (the exact failure mode this session caught
    once already on Plus-X's 6min/5min labels), only the 2 extreme traces
    (red_cyan/top and blue_yellow/bottom, unambiguous by ranking) are
    shipped; green_magenta_forming_layer is dropped for this product only."""
    from kodak_common import overline_negative_calib
    pdf_stub = "motionpicture/kodak/h17251.pdf"
    char_box = (330, 398.8, 570, 620)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_status_a",
        curves=[
            CurveSpec("red_cyan_forming_layer", label_position_override=(450, 491)),
            CurveSpec("blue_yellow_forming_layer", label_position_override=(450, 502.5)),
        ],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=char_box, monotonic_direction="decreasing", min_trace_points=8,
        x_tick_bbox=(345, 595, 565, 610),
    )
    char_chart.x_axis_calib_override = overline_negative_calib(
        PDF_ROOT / pdf_stub, 2, (345, 595, 565, 610), tick_regex=r"-?\d\.0")
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=3, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_SPECTRAL_LABELS],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(330, 147.5, 570, 315),
        y_axis_calib_override=(-0.02646536227953586, 6.9708503838860825),
    )
    dye_density_chart = ChartSpec(
        pdf=pdf_stub, page_index=3, chart_id="spectral_dye_density",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.\d{1,2}",
        x_label="wavelength_nm", y_label="diffuse_spectral_density",
        curves=curves_by_peak_x_with_envelope(PDF_ROOT / pdf_stub, 3, (44, 460, 280, 700),
                                               ["yellow", "magenta", "cyan"], "visual_neutral"),
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(44, 460, 280, 700),
    )
    return ProductSpec(
        brand="kodak", product_name="Ektachrome High-Speed Daylight (7251)",
        application_area="motion-picture", film_type="reversal", medium="color", iso=320, year=2004,
        layer_order=["red_cyan_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[char_chart, spectral_chart, dye_density_chart],
        digitizer_notes="Color reversal motion-picture film (Process VNF-1). "
                         "green_magenta_forming_layer's characteristic_curve trace is NOT included -- "
                         "the 3 real R/G/B traces are too close together for reliable exclusive "
                         "label-to-trace assignment even at their point of maximum separation; only "
                         "the 2 unambiguous extremes (top=R, bottom=B) are shipped. The "
                         "spectral_sensitivity chart's 3 layers are unaffected (well separated) and "
                         "all included. Overline-minus x-axis convention on the characteristic curve. "
                         "spectral_dye_density panel uses real inline labels (unlike 7239/5277/7267's "
                         "dash-pattern legend boxes), so vector_position works directly here.",
    )


def kodachrome25_movie_7267_product():
    """KODACHROME 25 Movie Film (Daylight) / 7267 -- previously blocked
    (BLOCKED.md) as "curves distinguished by line style only, Strategy B
    not built". Strategy B (vector_stroke_dash) WAS built in the meantime
    for the Fuji reversal-film work (fuji_still.py's
    fuji_ocr_dash_reversal_product) -- reused directly here, and this file
    is actually easier than the Fuji case since it has real extractable
    tick text (no OCR needed at all, just fit_axis/x_axis_calib_override
    as normal). Legend: solid=Blue, dash-dot (4 dash values)=Green, dotted
    (2 dash values)=Red on the Characteristic Curves panel; solid=Yellow,
    dash-dot=Magenta, dotted=Cyan on the Spectral-Sensitivity panel (same
    dash-style convention, different color-name meaning per Kodak's own
    legend -- confirmed by reading each legend box directly, not assumed
    shared). Characteristic-curve x-axis uses the overline-minus
    convention; spectral-sensitivity axes are real signed text (verified:
    "-2.0"/"-1.0" render as genuine minus-sign glyphs there, unlike the
    characteristic panel). Both charts verified via QA overlay: all 3
    curves per chart track their real labeled line exactly, 0 violations
    on the characteristic curve (spectral panel's 6-13 violations are the
    normal non-monotonic peak-and-fall shape expected of any spectral
    sensitivity curve, same as every other spectral chart in this
    project)."""
    pdf_stub = "motionpicture/kodak/7267_zh_CN.pdf"
    char_box = (55, 165, 265, 385)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=1, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_status_a",
        curves=[
            CurveSpec("blue_yellow_forming_layer", stroke_rgb=(0, 0, 0), tol=0.05,
                      dash_regex=r"^\[\] ", width=0.72, width_tol=0.1),
            CurveSpec("green_magenta_forming_layer", stroke_rgb=(0, 0, 0), tol=0.05,
                      dash_regex=r"^\[ [\d.]+ [\d.]+ [\d.]+ [\d.]+ \] ", width=0.72, width_tol=0.1),
            CurveSpec("red_cyan_forming_layer", stroke_rgb=(0, 0, 0), tol=0.05,
                      dash_regex=r"^\[ [\d.]+ [\d.]+ \] ", width=0.72, width_tol=0.1),
        ],
        film_id="_unused", extraction_method="vector_stroke_dash",
        region_bbox=char_box, monotonic_direction="decreasing", legend_bbox=(185, 178, 255, 218),
    )
    char_chart.x_axis_calib_override = overline_negative_calib(PDF_ROOT / pdf_stub, 1, char_box)

    spec_box = (55, 388, 295, 600)
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=1, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[
            CurveSpec("blue_yellow_forming_layer", stroke_rgb=(0, 0, 0), tol=0.05,
                      dash_regex=r"^\[\] ", width=0.72, width_tol=0.1),
            CurveSpec("green_magenta_forming_layer", stroke_rgb=(0, 0, 0), tol=0.05,
                      dash_regex=r"^\[ [\d.]+ [\d.]+ [\d.]+ [\d.]+ \] ", width=0.72, width_tol=0.1),
            CurveSpec("red_cyan_forming_layer", stroke_rgb=(0, 0, 0), tol=0.05,
                      dash_regex=r"^\[ [\d.]+ [\d.]+ \] ", width=0.72, width_tol=0.1),
        ],
        film_id="_unused", extraction_method="vector_stroke_dash",
        region_bbox=spec_box, monotonic_direction=None, legend_bbox=(78, 533, 140, 568),
        x_tick_bbox=(55, 573, 295, 588), y_tick_bbox=(50, 388, 70, 580),
    )
    return ProductSpec(
        brand="kodak", product_name="Kodachrome 25 Movie Film (7267)",
        application_area="motion-picture", film_type="reversal", medium="color", iso=25, year=2002,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[char_chart, spectral_chart],
        digitizer_notes="Color reversal motion-picture film, Process K-14. Curves distinguished by "
                         "line style, not position or inline label -- Strategy B (vector_stroke_dash), "
                         "matched by dash-pattern shape (solid/2-value-dotted/4-value-dash-dot), same "
                         "mechanism as Fuji's velvia_100/sensia templates. Real extractable tick text "
                         "on both charts (no OCR needed). Characteristic Curves legend: solid=Blue, "
                         "dotted=Red, dash-dot=Green. Spectral-Sensitivity legend: solid=Yellow, "
                         "dotted=Cyan, dash-dot=Magenta (same dash styles, different per-chart color "
                         "meaning, confirmed by reading each legend box directly). "
                         "spectral_dye_density panel NOT included: also a boxed dash-pattern legend "
                         "(same failure mode as 7239/5277 above) rather than the inline-label style "
                         "vector_position handles -- would need its own Strategy B dash-regex mapping "
                         "worked out for this specific panel, not attempted given remaining corpus scope.",
    )


PRODUCTS = [
    ektachrome64t_reversal_product,
    ektachrome_daylight_7239_product,
    ektachrome_highspeed_7251_product,
    kodachrome25_movie_7267_product,
]


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
