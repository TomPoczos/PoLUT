"""
Digitizes Konica color negative/reversal film datasheets (film/konica/*.pdf)
into consolidated-data/film/photography/{negative,reversal}/konica/.

Konica's own standard template packs "SPECTRAL SENSITIVITY" (left) and
"CHARACTERISTIC CURVES" (right) side by side on one page, under a combined
"SPECTRAL SENSITIVITY·CHARACTERISTIC CURVES" heading -- both charts use
inline "R"/"G"/"B" labels (not Kodak's "Yellow-/Magenta-/Cyan-Forming Layer"
wording for the spectral chart), same Strategy D (vector_position) as every
other vendor in this project. The x-axis on the Characteristic Curves panel
uses the same vector-overline minus-sign convention as ~1997-2003-era Kodak
sheets (see kodak_common.overline_negative_calib) -- ticks read "3.0 2.0 1.0
0.0 1.0" left-to-right, the first three meaning -3.0/-2.0/-1.0.

The Spectral Sensitivity panel's y-axis is NOT a normal multi-tick axis --
Konica draws a single vertical bracket (two small arrowheads + a connecting
line) labeled "1.0" to indicate "this span = 1 log-unit of relative speed,"
with no absolute zero anywhere on the chart (confirmed: only one numeric
y-axis label exists on the whole panel). `_relative_speed_calib()` finds
that bracket's own pixel span directly from the page's vector drawings and
calibrates against it, picking the bracket's own top/bottom as the 1.0/0.0
reference points -- an arbitrary zero, same honest-fallback spirit as
`density_midpoint()` elsewhere in this project: not fabricated data, just a
relative scale with no natural origin, exactly as Konica's own chart
presents it.

Usage: uv run konica.py
"""

from pathlib import Path

import fitz

from digitizer_core import ChartSpec, CurveSpec, digitize_chart
from kodak_common import COLOR_NEG_CHAR_LABELS, overline_negative_calib
from ocr_helpers import ocr_axis_calib, ocr_overline_negative_calib
from product import ProductSpec, digitize_product, run_products_parallel

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")

# Konica's spectral-sensitivity panel labels curves "R"/"G"/"B" directly,
# same glyphs (not wording) as the Characteristic Curves panel -- unlike
# Kodak's spectral panel, which spells out "Yellow-/Magenta-/Cyan-Forming
# Layer" instead of reusing "B"/"G"/"R".
KONICA_SPECTRAL_LABELS = COLOR_NEG_CHAR_LABELS


def _relative_speed_calib(pdf_path, page_index, region_bbox):
    """Finds the Spectral-Sensitivity panel's "1.0" scale-bracket (a vertical
    line, sometimes bundled together with unrelated gridline/tick segments
    into one combined drawing object -- so this checks individual line
    ITEMS, not each drawing's overall bounding rect, which can be much wider
    than the bracket itself once other segments are merged in) and returns
    (slope, intercept) treating the line's own top/bottom pixel
    y-coordinates as the 1.0/0.0 relative-speed reference points."""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    drawings = page.get_drawings()
    doc.close()
    x0, y0, x1, y1 = region_bbox
    candidates = []
    for d in drawings:
        for item in d["items"]:
            if item[0] != "l":
                continue
            p0, p1 = item[1], item[2]
            if abs(p0.x - p1.x) > 1.0:
                continue  # not a vertical segment
            if not (x0 <= p0.x <= x1 and y0 <= min(p0.y, p1.y) and max(p0.y, p1.y) <= y1):
                continue
            if abs(p1.y - p0.y) > 25:
                candidates.append((min(p0.y, p1.y), max(p0.y, p1.y)))
    if not candidates:
        raise RuntimeError(f"no relative-speed bracket line found in {region_bbox}")
    top, bottom = max(candidates, key=lambda c: c[1] - c[0])
    slope = (0.0 - 1.0) / (bottom - top)
    intercept = 1.0 - slope * top
    return float(slope), float(intercept)


def konica_style_product(pdf_stub, page_index, product_name, iso, year, film_type="negative",
                          char_box=None, spec_box=None, skip_spectral=False, min_trace_points=6,
                          monotonic="increasing", char_labels=COLOR_NEG_CHAR_LABELS):
    """Locates the "CHARACTERISTIC" word on the panel sub-header line (the
    SECOND occurrence of that word on the page -- the first is always part
    of the combined "SPECTRAL SENSITIVITY·CHARACTERISTIC CURVES" section
    title higher up the page) and builds both panel boxes relative to it,
    since the panels' vertical position on the page varies file-to-file
    (depends on how much text precedes them) but their own internal layout
    (column split, panel height) is consistent. Pass char_box/spec_box
    explicitly for sheets where this auto-detection doesn't apply."""
    pdf_path = PDF_ROOT / pdf_stub
    if char_box is None or spec_box is None:
        doc = fitz.open(pdf_path)
        page = doc[page_index]
        words = page.get_text("words")
        doc.close()
        char_words = [w for w in words if w[4] == "CHARACTERISTIC"]
        spectral_words = [w for w in words if w[4] == "SPECTRAL"]
        if len(char_words) < 2 or len(spectral_words) < 2:
            raise RuntimeError(f"{pdf_stub}: expected 2 CHARACTERISTIC/SPECTRAL word hits, "
                                f"got {len(char_words)}/{len(spectral_words)} -- pass char_box/spec_box explicitly")
        hdr = char_words[1]
        split_x, hdr_y0 = hdr[0], hdr[1]
        if char_box is None:
            char_box = (split_x - 15, hdr_y0 - 5, split_x + 170, hdr_y0 + 172)
        if spec_box is None:
            spec_box = (spectral_words[1][0] - 20, hdr_y0 - 5, split_x - 5, hdr_y0 + 185)

    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
        x_label="log_exposure_lux_seconds", y_label="density_status_m",
        curves=[CurveSpec(n, label_regex=r) for n, r in char_labels],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=char_box, monotonic_direction=monotonic, min_trace_points=min_trace_points,
    )
    char_chart.x_axis_calib_override = overline_negative_calib(pdf_path, page_index, char_box)

    charts = [char_chart]
    if not skip_spectral:
        spec_chart = ChartSpec(
            pdf=pdf_stub, page_index=page_index, chart_id="spectral_sensitivity",
            x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
            x_label="wavelength_nm", y_label="relative_speed_log_arbitrary_zero",
            curves=[CurveSpec(n, label_regex=r) for n, r in KONICA_SPECTRAL_LABELS],
            film_id="_unused", extraction_method="vector_position",
            region_bbox=spec_box, monotonic_direction=None,
        )
        spec_chart.y_axis_calib_override = _relative_speed_calib(pdf_path, page_index, spec_box)
        charts.append(spec_chart)

    return ProductSpec(
        brand="konica", product_name=product_name, application_area="photography",
        film_type=film_type, medium="color", iso=iso, year=year,
        layer_order=[n for n, _ in char_labels],
        source_pdf=pdf_stub, charts=charts,
        digitizer_notes="Konica standard 2-panel 'SPECTRAL SENSITIVITY·CHARACTERISTIC CURVES' "
                         "template, curves ID'd by inline R/G/B labels (Strategy D, vector_position). "
                         "Characteristic Curves x-axis uses the vector-overline minus-sign convention "
                         "(see kodak_common.overline_negative_calib). Spectral-Sensitivity y-axis has "
                         "no absolute zero on the source chart (a single '1.0' scale bracket, not a "
                         "multi-tick ruler) -- calibrated against that bracket's own pixel span, "
                         "arbitrary zero, not fabricated data."
                         + (" Spectral-Sensitivity panel not present/not captured for this sheet."
                            if skip_spectral else "")
                         + (" Characteristic Curves panel: only "
                            + "/".join(n for n, _ in char_labels)
                            + " captured -- the other layer(s)' curves fragment into short "
                              "disconnected path pieces near the toe (where all 3 converge) and "
                              "aren't reliably separable, not shipped rather than guessed."
                            if len(char_labels) < 3 else ""),
    )


def csuper400_product():
    """Centuria Super 400 (csuper400.pdf) -- the chart page (page 1) has
    real vector drawings (1683 of them) but ZERO real text objects anywhere
    on the page, even though it renders visually identical to the other
    Centuria Super sheets (confirmed: body text on the OTHER pages of this
    same file IS real/extractable, so this is a per-page font-outlining
    quirk, not a corpus-wide raster/scan problem) -- previously logged in
    BLOCKED.md as a third, distinct failure mode from both "embedded raster
    image" and "graphs referenced by figure code only". Unlike those two,
    this one turned out fully recoverable: the curve ink itself is real
    stroked vector paths (Strategy D still finds exactly 3 clean traces),
    it's only the TEXT (panel titles, axis ticks, R/G/B labels) that's
    unextractable, so this needed OCR for (a) finding the panel's own
    position on the page at all (no "CHARACTERISTIC"/"SPECTRAL" text to
    search for, unlike konica_style_product's auto-detect) and (b) axis
    calibration -- but curve IDENTITY still comes from each trace's own
    endpoint position (label_position_override), not OCR, using the same
    real physical convention verified across every other Konica product
    (B highest density/top, G middle, R lowest/bottom on the char curve;
    B/G/R left-to-right by wavelength on the spectral chart).

    Also surfaced a real, generalizable OCR bug (fixed in ocr_helpers.py,
    2026-07-07): this file's y-axis tick row genuinely has no minus sign
    anywhere (unlike the x-axis, an overline-convention row), but
    `ocr_axis_calib` was trusting a spuriously-OCR'd leading "-" merged in
    from the small perpendicular tick-mark dash strokes sitting right next
    to the digit text, silently negating the whole axis. Also surfaced
    that an evenly-spaced overline-convention tick row is genuinely
    ambiguous for a residual-minimizing brute-force sign search (multiple
    sign assignments fit equally well) -- `ocr_overline_negative_calib`
    applies the known "negate all but the rightmost" convention directly
    instead of searching, sidestepping the ambiguity."""
    pdf_stub = "film/konica/csuper400.pdf"
    pdf_path = PDF_ROOT / pdf_stub
    doc = fitz.open(pdf_path)
    page = doc[1]
    char_x_calib = ocr_overline_negative_calib(page, (390, 775, 580, 790), tick_regex=r"\d\.\d", axis="x")
    char_y_calib = ocr_axis_calib(page, (390, 655, 415, 780), tick_regex=r"\d\.\d", axis="y")
    spec_x_calib = ocr_axis_calib(page, (200, 798, 395, 812), tick_regex=r"\d{3}", axis="x", zoom=10.0)
    doc.close()
    spec_y_calib = _relative_speed_calib(pdf_path, 1, (200, 637, 225, 827))

    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=1, chart_id="characteristic_curve",
        x_tick_regex=r"\d\.\d", y_tick_regex=r"\d\.\d",
        x_label="log_exposure_lux_seconds", y_label="density_status_m",
        curves=[
            CurveSpec("blue_yellow_forming_layer", label_position_override=(541.6, 665.0)),
            CurveSpec("green_magenta_forming_layer", label_position_override=(541.6, 681.7)),
            CurveSpec("red_cyan_forming_layer", label_position_override=(541.97, 694.18)),
        ],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(389.5, 637, 574.5, 814), monotonic_direction="increasing", min_trace_points=6,
        x_axis_calib_override=char_x_calib, y_axis_calib_override=char_y_calib,
    )
    spec_chart = ChartSpec(
        pdf=pdf_stub, page_index=1, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.\d",
        x_label="wavelength_nm", y_label="relative_speed_log_arbitrary_zero",
        curves=[
            CurveSpec("blue_yellow_forming_layer", label_position_override=(263.8, 696.8)),
            CurveSpec("green_magenta_forming_layer", label_position_override=(295.5, 695.5)),
            CurveSpec("red_cyan_forming_layer", label_position_override=(331.0, 695.3)),
        ],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=(200, 637, 395, 827), monotonic_direction=None, min_trace_points=6,
        x_axis_calib_override=spec_x_calib, y_axis_calib_override=spec_y_calib,
    )
    return ProductSpec(
        brand="konica", product_name="Centuria Super 400", application_area="photography",
        film_type="negative", medium="color", iso=400, year=None,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[char_chart, spec_chart],
        digitizer_notes="Konica standard 2-panel template, but this specific page has NO real "
                         "extractable text at all (title, axis ticks, and R/G/B labels are all "
                         "vector-drawn/outlined, unlike every other Konica sheet in this corpus, where "
                         "at least the R/G/B labels are real text) -- panel position and axis "
                         "calibration via OCR (ocr_helpers), curve identity via each trace's own "
                         "endpoint position and the same real B>G>R (density) / B<G<R (wavelength) "
                         "convention verified across every other Konica product, not OCR. Verified via "
                         "QA overlay.",
    )


def professional_160_product():
    """Professional 160 (professional_160.pdf) -- a marketing brochure
    (product photos, dark/black-background page theme), not the vendor's
    usual technical-datasheet template, but page 3 has real, genuine
    Characteristic Curves + Spectral Sensitivity charts (confirmed: real
    curve data, not decorative) -- like csuper400.pdf, this page has ZERO
    real extractable text (title/axis ticks/B-G-R labels all vector-drawn),
    but UNLIKE every other Konica product in this module, the 3 curves
    here are distinguished by real, distinct STROKE COLOR (yellow/magenta/
    cyan against the black page background) rather than by black ink +
    position -- confirmed via page.get_drawings() color values matching
    the visually-obvious colors. Strategy B (vector_stroke_dash) by color
    alone (dash_regex=None, matches any dash pattern), same mechanism as
    Kodachrome 25 above just keyed on color instead of dash style.

    Real gotcha: the char curve and spectral panels share the exact same 3
    stroke colors (Konica draws B/G/R the same yellow/magenta/cyan on
    every panel on this page) -- an initial attempt with a region_bbox
    spanning too much of the page (guessed loosely rather than measured)
    silently pulled points from BOTH panels into one curve, producing a
    curve with a long flat spurious tail extending across into the
    neighboring panel's x-range (caught via QA overlay, not a crash or
    warning) -- fixed by reading each panel's own real black-background
    rect from page.get_drawings() directly and using its exact bounds as
    region_bbox, not an eyeballed approximation."""
    pdf_stub = "film/konica/professional_160.pdf"
    pdf_path = PDF_ROOT / pdf_stub
    doc = fitz.open(pdf_path)
    page = doc[3]
    char_x_calib = ocr_overline_negative_calib(page, (120, 225, 355, 245), tick_regex=r"\d\.\d", axis="x")
    char_y_calib = ocr_axis_calib(page, (105, 80, 128, 200), tick_regex=r"\d\.\d", axis="y")
    spec_x_calib = ocr_axis_calib(page, (379, 225, 575, 240), tick_regex=r"\d{3}", axis="x", zoom=10.0)
    doc.close()
    spec_y_calib = _relative_speed_calib(pdf_path, 3, (365, 110, 380, 175))

    curve_specs = [
        ("blue_yellow_forming_layer", (1.0, 0.949, 0.0)),
        ("green_magenta_forming_layer", (0.926, 0.0, 0.548)),
        ("red_cyan_forming_layer", (0.0, 0.681, 0.938)),
    ]
    char_chart = ChartSpec(
        pdf=pdf_stub, page_index=3, chart_id="characteristic_curve",
        x_tick_regex=r"\d\.\d", y_tick_regex=r"\d\.\d",
        x_label="log_exposure_lux_seconds", y_label="density_status_m",
        curves=[CurveSpec(n, stroke_rgb=rgb, tol=0.02, width=0.57, width_tol=0.05) for n, rgb in curve_specs],
        film_id="_unused", extraction_method="vector_stroke_dash",
        region_bbox=(126.5, 59, 345, 229), monotonic_direction="increasing", min_trace_points=8,
        x_axis_calib_override=char_x_calib, y_axis_calib_override=char_y_calib,
    )
    spec_chart = ChartSpec(
        pdf=pdf_stub, page_index=3, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.\d",
        x_label="wavelength_nm", y_label="relative_speed_log_arbitrary_zero",
        curves=[CurveSpec(n, stroke_rgb=rgb, tol=0.02, width=0.57, width_tol=0.05) for n, rgb in curve_specs],
        film_id="_unused", extraction_method="vector_stroke_dash",
        region_bbox=(379, 59, 566, 229), monotonic_direction=None, min_trace_points=6,
        x_axis_calib_override=spec_x_calib, y_axis_calib_override=spec_y_calib,
    )
    return ProductSpec(
        brand="konica", product_name="Professional 160", application_area="photography",
        film_type="negative", medium="color", iso=160, year=None,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=[char_chart, spec_chart],
        digitizer_notes="Marketing brochure (Konica Minolta rebrand era), not the vendor's usual "
                         "datasheet template, but page 3 has real Characteristic Curves + Spectral "
                         "Sensitivity charts. No real extractable text at all on this page -- panel "
                         "position/axis calibration via OCR, but curve identity here uses real, "
                         "distinct STROKE COLOR (yellow/magenta/cyan), not position or dash style, "
                         "confirmed via page.get_drawings() color values. Verified via QA overlay.",
    )


PRODUCTS = [
    lambda: konica_style_product("film/konica/VX-S100.pdf", 1, "VX Super 100", 100, None),
    lambda: konica_style_product("film/konica/VX-S200.pdf", 1, "VX Super 200", 200, None),
    lambda: konica_style_product("film/konica/VX-S400.pdf", 1, "VX Super 400", 400, None),
    lambda: konica_style_product("film/konica/VX100Improved.pdf", 1, "VX100 (Improved)", 100, None),
    lambda: konica_style_product("film/konica/csuper100.pdf", 1, "Centuria Super 100", 100, None),
    lambda: konica_style_product("film/konica/csuper200.pdf", 1, "Centuria Super 200", 200, None),
    lambda: konica_style_product("film/konica/csuper800.pdf", 1, "Centuria Super 800", 800, None),
    lambda: konica_style_product("film/konica/csuper1600.pdf", 2, "Centuria Super 1600", 1600, None),
    lambda: konica_style_product("film/konica/chrocen100.pdf", 1, "Chrome Centuria 100", 100, None,
                                  film_type="reversal", monotonic="decreasing",
                                  char_labels=[("blue_yellow_forming_layer", r"^B$")]),
    lambda: konica_style_product("film/konica/chrocen200.pdf", 1, "Chrome Centuria 200", 200, None,
                                  film_type="reversal", monotonic="decreasing",
                                  char_labels=[("blue_yellow_forming_layer", r"^B$")]),
    # R100.pdf: auto-detect fails because "SENSITIVITY•CHARACTERISTIC" (no
    # space around the bullet) fuses into one word token on the combined
    # section-title line, leaving only the real panel sub-header as an
    # exact "CHARACTERISTIC" match -- boxes hand-computed from that word's
    # own position instead.
    lambda: konica_style_product("film/konica/R100.pdf", 1, "Chrome R-100", 100, None,
                                  film_type="reversal", monotonic="decreasing",
                                  char_box=(385.61, 594.72, 570.61, 771.72),
                                  spec_box=(196.23, 594.72, 395.61, 784.72),
                                  char_labels=[("green_magenta_forming_layer", r"^G$"),
                                               ("blue_yellow_forming_layer", r"^B$")]),
    csuper400_product,
    professional_160_product,
]


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
