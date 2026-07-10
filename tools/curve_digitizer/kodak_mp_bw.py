"""
Digitizes Kodak motion-picture BLACK-AND-WHITE film datasheets into
consolidated-data/film/motion-picture/negative/kodak/ (medium="bw").

Different template from the color VISION/EXR sheets (kodak_mp.py): the
chart is titled "Sensitometric Curve(s)" (singular for a single
representative curve, plural for a development-time family) with a plain
"DENSITY" y-axis (Status M Blue densitometry, one channel, not B/G/R
layers), and a "Spectral-Sensitivity Curves" panel plotting 1-2 curves at
different reference densities above fog (not dye layers).

Usage: uv run kodak_mp_bw.py
"""

from pathlib import Path

import fitz

from digitizer_core import ChartSpec, CurveSpec, digitize_chart
from product import ProductSpec, digitize_product, run_products_parallel

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")


def double_x_product():
    """EASTMAN DOUBLE-X Negative Film 5222/7222. Both chart titles ("Sensi-
    tometric Curve"/"Spectral-Sensitivity Curves") render with each letter
    as its own text run (confirmed: `page.get_text("words")` returns "S",
    "e", "n", ... separately) -- harmless for extraction (box coordinates
    below are hand-derived from real word positions, not the title text
    itself), but means `locate_panel_bboxes` can't be used for this file.
    Both charts' axis tick numbers are ALSO not real text at all (zero
    words found in either tick region) -- OCR'd via `ocr_helpers` (the
    horizontal wavelength row OCRs fine with the standard psm=11 path; the
    vertical, widely-spaced single-digit DENSITY/LOG SENSITIVITY columns
    needed a custom psm=6 call, since psm=11's "sparse text" assumption
    reads a tall column of isolated digits poorly -- confirmed by testing
    both directly against the same crop).
    Spectral-Sensitivity Curves' curve identity ("D=0.3 Above Gross Fog"/
    "D=1.0 Above Gross Fog") has no extractable label text either, AND the
    D=1.0 curve is drawn as a dashed line rendered via many small FILL
    fragments (color=None, hundreds of items), not a stroked path --
    confirmed via page.get_drawings() -- the same fill-based-ink
    limitation already hit on Ilford Ortho Plus's Pictorial/High Contrast
    panels. Only D=0.3 (a real stroked path, confirmed) is captured;
    D=1.0 is skipped, not chased further.
    """
    pdf_stub = "motionpicture/kodak/5222-Double-X.pdf"
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.00", y_tick_regex=r"\d",
        x_label="log_exposure_lux_seconds", y_label="density_status_m_blue",
        curves=[CurveSpec("density", label_position_override=(270, 150))],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(36, 140, 300, 317),
        x_axis_calib_override=(0.0267942, -5.42793301),
        y_axis_calib_override=(-0.02231042, 6.83720949),
        monotonic_direction="increasing", min_trace_points=8,
    )
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d",
        x_label="wavelength_nm", y_label="log_sensitivity_d0.3_above_gross_fog",
        curves=[CurveSpec("sensitivity", label_position_override=(400, 200))],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(330, 140, 580, 317),
        x_axis_calib_override=None, y_axis_calib_override=(-1 / 36.185, 3 - 167.875 * (-1 / 36.185)),
        monotonic_direction=None, min_trace_points=8,
    )
    # x-axis (wavelength) OCRs fine with the standard helper -- do it here
    # (needs the open page) rather than hand-computing like the y-axis.
    from ocr_helpers import ocr_axis_calib
    doc = fitz.open(PDF_ROOT / pdf_stub)
    page = doc[2]
    spectral_chart.x_axis_calib_override = ocr_axis_calib(page, (345, 310, 580, 322), tick_regex=r"\d{3}", axis="x")
    doc.close()

    return ProductSpec(
        brand="kodak", product_name="Double-X", application_area="motion-picture",
        film_type="negative", medium="bw", iso=250, year=1999,
        layer_order=["density"], source_pdf=pdf_stub, charts=[char_chart, spectral_chart],
        digitizer_notes="B&W negative film, single representative Sensitometric Curve (Status M Blue) "
                         "+ Spectral-Sensitivity (D=0.3 Above Gross Fog only, see this module's own "
                         "docstring for why D=1.0 isn't captured). Both charts' tick text is OCR'd "
                         "(zero real extractable tick words in either), the chart titles are also "
                         "letter-spaced (each character its own text run) so locate_panel_bboxes "
                         "couldn't be used -- boxes are hand-derived from real body-text word positions.",
    )


def plus_x_product():
    """EASTMAN PLUS-X Negative Film 5231/7231. Real extractable text
    throughout (title, ticks, inline dev-time/curve labels) -- a much
    simpler case than Double-X. Sensitometric Curves panel is a 3-curve
    development-time family (4/5/6 min, inline diagonal labels "4 min
    gamma=0.63" etc, split into separate "4"/"min" words by the rotated
    rendering -- label_regex matches just the leading digit word, which
    sits at a distinct, non-colliding position per curve). x-axis uses the
    classic overline-minus convention (ticks read as unsigned "3.0 2.0 1.0
    0.0 1.0", all but the last negated) -- `kodak_common.overline_negative_
    calib`."""
    from kodak_common import overline_negative_calib
    pdf_stub = "motionpicture/kodak/5231-PLUS-X.pdf"
    char_box = (60, 32, 300, 246)
    # Real gotcha: the "6"/"5" inline labels sit diagonally close together
    # (y=127-129, only ~1.7pt apart) right where their own curves are also
    # closest -- label_regex-based nearest-trace matching (and even
    # min_trace_points-filtered rank matching) swapped 6min/5min here
    # (confirmed via QA overlay: max densities came back 5min > 6min,
    # backwards from the real gamma ordering 0.76 > 0.70 > 0.63). Fixed
    # with hand-placed label_position_override anchors at x=225 (near the
    # shoulder, where the 3 curves are maximally separated, not near the
    # labels themselves) -- each anchor's y was read directly off each
    # trace's own interpolated position at that x, not eyeballed.
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_status_m_blue",
        curves=[
            CurveSpec("6min", label_position_override=(225, 115)),
            CurveSpec("5min", label_position_override=(225, 124.5)),
            CurveSpec("4min", label_position_override=(225, 138)),
        ],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=char_box, monotonic_direction="increasing", min_trace_points=150,
        metadata={"developer": "KODAK Developer D-96", "curve_dimension": "development_time",
                  "curve_names": ["6min", "5min", "4min"]},
    )
    char_chart.x_axis_calib_override = overline_negative_calib(
        PDF_ROOT / pdf_stub, 2, char_box, tick_regex=r"-?\d\.0")

    spectral_box = (325, 32, 575, 225)
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[
            CurveSpec("d0.3_above_gross_fog", label_regex=r"^D=0\.3$"),
            CurveSpec("d1.0_above_gross_fog", label_regex=r"^D=1\.0$"),
        ],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=spectral_box, monotonic_direction=None, min_trace_points=8,
    )

    return ProductSpec(
        brand="kodak", product_name="Plus-X", application_area="motion-picture",
        film_type="negative", medium="bw", iso=80, year=1999,
        layer_order=["density"], source_pdf=pdf_stub, charts=[char_chart, spectral_chart],
        digitizer_notes="B&W negative film, 3 development-time curves (4/5/6 min, KODAK Developer D-96) "
                         "-- Strategy D, inline rotated dev-time labels split by the renderer into "
                         "separate digit/'min' words, matched via the leading digit word alone. "
                         "Overline-minus x-axis convention (kodak_common.overline_negative_calib). "
                         "Spectral-Sensitivity Curves has 2 real, fully labeled curves (D=0.3/D=1.0 "
                         "Above Gross Fog), both real extractable text -- no OCR needed at all for "
                         "this file, unlike its Double-X sibling.",
    )


def _reversal_bw_product(pdf_stub, product_name, iso, year, char_box, spec_box, char_anchor,
                          spec_anchor, x_axis_calib_override=None, cross_object_merge=False,
                          char_x_tick_regex=r"-?\d\.0"):
    """Shared template for the two B&W motion-picture REVERSAL (direct
    duplicating/print) stocks in this corpus (7265 PLUS-X Reversal, 7266
    TRI-X Reversal) -- same "Characteristic Curve"/"Spectral Sensitivity
    Curve" shape as the camera-negative B&W films above, but density FALLS
    with exposure (real reversal-process material, confirmed against each
    raw curve, not assumed) and panel placement is NOT consistent between
    the two files (7265: Characteristic left/page3, Spectral right/page3;
    7266: Spectral left/page3, Characteristic right/page2 -- confirmed by
    reading both, not guessed from one). Both files' curves are drawn as
    many small stroke fragments rather than one continuous path, needing
    `cross_object_merge=True` to recombine (7266 only; 7265's fragments
    happened to already merge without it)."""
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=None, chart_id="characteristic_curve",
        x_tick_regex=char_x_tick_regex, y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_diffuse_visual",
        curves=[CurveSpec("density", label_position_override=char_anchor)],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=char_box[1:], monotonic_direction="decreasing", min_trace_points=8,
        x_axis_calib_override=x_axis_calib_override, cross_object_merge=cross_object_merge,
    )
    char_chart.page_index = char_box[0]
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=spec_box[0], chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec("sensitivity", label_position_override=spec_anchor)],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=spec_box[1:], monotonic_direction=None, min_trace_points=8,
        cross_object_merge=True,
    )
    return ProductSpec(
        brand="kodak", product_name=product_name, application_area="motion-picture",
        film_type="reversal", medium="bw", iso=iso, year=year,
        layer_order=["density"], source_pdf=pdf_stub, charts=[char_chart, spectral_chart],
        digitizer_notes="B&W reversal (direct duplicating/print) film -- density falls with exposure "
                         "(increasing=False), confirmed against the raw digitized curve, not assumed "
                         "from the negative-film template above. Single representative curve, no "
                         "development-time or paper-grade family.",
    )


def plusx_reversal_product():
    return _reversal_bw_product(
        "motionpicture/kodak/7265-PLUS-X-rev.pdf", "PLUS-X Reversal", 50, 2003,
        char_box=(3, 42, 65.8, 300, 295), spec_box=(3, 310, 65.8, 570, 270),
        char_anchor=(90, 90), spec_anchor=(460, 150),
    )


def trix_reversal_product():
    return _reversal_bw_product(
        "motionpicture/kodak/7266-TRI-X-rev.pdf", "TRI-X Reversal", 200, 2003,
        char_box=(2, 340, 135, 570, 365), spec_box=(3, 35, 44.8, 300, 235),
        char_anchor=(400, 160), spec_anchor=(150, 120),
        x_axis_calib_override=(0.0326206215362884, -15.98777756928725),
        cross_object_merge=True, char_x_tick_regex=r"\d\.0",
    )


def plusx_7276_reversal_product():
    """EASTMAN PLUS-X Reversal Film 7276 -- an older catalog number/
    printing of the same nominal PLUS-X Reversal stock as 7265 (different
    measured sheet, digitized as its own real data point, same convention
    used throughout this corpus for other same-name/different-catalog-
    number sheets). Real gotcha: a "Base Density" annotation line+label
    sits inside the chart's own region_bbox and is nearly as long as a
    real trace fragment -- naive extraction grabs it instead of the real
    186-point curve unless the label_position_override anchor is placed
    well clear of it (x=220, mid-curve, not near the legend/annotation)."""
    from kodak_common import overline_negative_calib
    pdf_stub = "motionpicture/kodak/7276.pdf"
    char_box = (42, 257.3, 300, 470)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_diffuse_visual",
        curves=[CurveSpec("density", label_position_override=(220, 400))],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=char_box, monotonic_direction="decreasing", min_trace_points=8,
        x_tick_bbox=(60, 451, 290, 461),
    )
    char_chart.x_axis_calib_override = overline_negative_calib(
        PDF_ROOT / pdf_stub, 2, (60, 451, 290, 461), tick_regex=r"-?\d\.0")
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec("sensitivity", label_position_override=(460, 320))],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(330, 264.6, 570, 470), monotonic_direction=None, min_trace_points=8,
        cross_object_merge=True,
    )
    return ProductSpec(
        brand="kodak", product_name="PLUS-X Reversal (7276)", application_area="motion-picture",
        film_type="reversal", medium="bw", iso=50, year=1999,
        layer_order=["density"], source_pdf=pdf_stub, charts=[char_chart, spectral_chart],
        digitizer_notes="Same nominal product as PLUS-X Reversal (7265) but an older/different "
                         "catalog-numbered sheet -- digitized as its own real measured data point, not "
                         "assumed identical. Overline-minus x-axis convention "
                         "(kodak_common.overline_negative_calib). A 'Base Density' annotation "
                         "line+label sits inside the chart region and must be avoided by the "
                         "label_position_override anchor (placed at the curve's own mid-shoulder, not "
                         "near the annotation).",
    )


def trix_7278_reversal_product():
    """EASTMAN TRI-X Reversal Film 7278 -- same relationship to TRI-X
    Reversal (7266) as 7276 is to PLUS-X Reversal (7265): an older/
    different catalog-numbered sheet for the same nominal stock, digitized
    as its own real data point. DIFFERENT page layout from 7276 (here:
    Sensitometric Curve is its own left-column chart on this page;
    Spectral-Sensitivity is top-right, Modulation-Transfer bottom-right --
    confirmed by reading the page, not assumed from 7276's layout). Same
    overline-minus x-axis convention on the characteristic curve."""
    from kodak_common import overline_negative_calib
    pdf_stub = "motionpicture/kodak/7278.pdf"
    char_box = (60, 298.8, 300, 515)
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_diffuse_visual",
        curves=[CurveSpec("density", label_position_override=(150, 400))],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=char_box, monotonic_direction="decreasing", min_trace_points=8,
        x_tick_bbox=(75, 492, 290, 503),
    )
    char_chart.x_axis_calib_override = overline_negative_calib(
        PDF_ROOT / pdf_stub, 2, (75, 492, 290, 503), tick_regex=r"-?\d\.0")
    spectral_chart = ChartSpec(
        pdf=pdf_stub, page_index=2, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec("sensitivity", label_position_override=(470, 130))],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(330, 44.8, 570, 230), monotonic_direction=None, min_trace_points=8,
    )
    return ProductSpec(
        brand="kodak", product_name="TRI-X Reversal (7278)", application_area="motion-picture",
        film_type="reversal", medium="bw", iso=200, year=1999,
        layer_order=["density"], source_pdf=pdf_stub, charts=[char_chart, spectral_chart],
        digitizer_notes="Same nominal product as TRI-X Reversal (7266) but an older/different "
                         "catalog-numbered sheet, digitized as its own real measured data point. "
                         "Overline-minus x-axis convention (kodak_common.overline_negative_calib). "
                         "Different page layout from its 7276 sibling -- confirmed by reading the page.",
    )


PRODUCTS = [
    double_x_product,
    plus_x_product,
    plusx_reversal_product,
    trix_reversal_product,
    plusx_7276_reversal_product,
    trix_7278_reversal_product,
]


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
