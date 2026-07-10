"""
Digitizes Ilford black-and-white film datasheets (film/ilford/*.pdf) into
consolidated-data/film/photography/negative/ilford/ (medium="bw").

Only the pre-2018 revisions are used as source PDFs -- confirmed via
`page.get_images()` that every film's 2018+ reprint (e.g. `HP5-Plus_201811.pdf`)
embeds its Characteristic Curve(s) panel as a raster image (7-10 images per
file vs 0 on the matching pre-2018 sheet), the same raster-tracing problem
class as the Fuji "embedded raster image" group in BLOCKED.md -- not
attempted here (2026-07-06 decision: raster tracing is deprioritized, see
BLOCKED.md). The older sheets are real, complete datasheets in their own
right (not superseded data -- same product, same curve), just typeset as
vector paths + real extractable text, so Strategy D (vector_position) works
directly, no OCR/raster work needed.

Two templates found in this vendor, genuinely different from Kodak's:
1. Most films (HP5+, FP4+, Pan F+, Delta 100, Delta 400, XP2 Super) publish
   exactly ONE representative curve per product -- "This curve is also
   representative of the rollfilm/sheet film formats" -- not a family of
   developer/dev-time variants the way Kodak B&W sheets are. No inline label
   at all (there's nothing to disambiguate, only one trace in the region),
   so `CurveSpec.label_position_override` is given a hand-picked anchor
   point near the curve's own shoulder purely to satisfy the Strategy D
   assign-nearest-trace machinery -- verified via QA overlay per file that
   this doesn't accidentally grab a frame/gridline artifact instead.
2. Delta 3200 and Ortho Plus are real exceptions with multiple curves per
   panel: Delta 3200 publishes 2 developer panels (ILFOTEC DD-X, MICROPHEN)
   x 4 real development-time curves each (7/9/12/16 min, real inline text
   labels) -- same shape as Kodak's BwPanel/`curve_dimension=
   "development_time"`. Ortho Plus publishes 3 contrast panels (Pictorial/
   Intermediate/High), each 2 curves labeled by their own gamma value
   ("Ḡ0.70"/"Ḡ0.62" etc, rendered as plain "G0.70" in extractable text) --
   but ONLY the Intermediate panel's own gamma labels AND axis tick numbers
   are real extractable text (Strategy D, vector_position, unchanged).
   Pictorial's and High's curve ink is drawn as many small FILLED quad
   fragments instead of a stroked path (Strategy E, `vector_fill_band` --
   see `digitizer_core.extract_fill_band_curves`), and neither panel has
   real extractable tick or gamma-label text either (OCR via
   `ocr_helpers.ocr_axis_calib`, same mechanism as Ilford Multigrade
   papers) -- see `_ortho_fill_band_chart()` below for the full mechanism
   and gotchas (a real OCR sign-inversion bug this file's own y-axis
   surfaced and got fixed in `ocr_helpers.py`, and a real fragment
   silently dropped by a too-tight label-exclude bbox, fixed by filtering
   on fragment width instead of position).

SFX 200 (all 3 revisions) confirmed NOT to have a Characteristic Curve(s)
chart at all -- it's a short "FACT SHEET" (spectral sensitivity + filter
factors + dev-time nomogram only), not a full datasheet; see BLOCKED.md.

Usage: uv run ilford_film.py
"""

from pathlib import Path

import fitz

from digitizer_core import ChartSpec, CurveSpec, digitize_chart, locate_panel_bboxes, fit_axis
from ocr_helpers import ocr_axis_calib
from product import ProductSpec, digitize_product, run_products_parallel

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")


def _single_curve_chart(pdf_stub, page_index, x_tick_regex=r"^[1234]$", y_tick_regex=r"^[123]\.0$"):
    """Shared ChartSpec builder for template 1 (see module docstring):
    exactly one undifferentiated density curve, no inline label, box
    auto-located from the page's own 'CHARACTERISTIC' title text. The
    curve's own shoulder (max exposure, max density) always sits near the
    box's own top-right corner on this vendor's template (density increases
    upward = smaller page-y; exposure increases rightward) -- anchoring
    there instead of a hand-picked per-file point removed a real source of
    mistakes (an earlier hand-guessed anchor for Delta 100 landed in the
    caption text below the chart entirely, producing 0 points silently
    until checked)."""
    import fitz
    from ocr_helpers import ocr_axis_calib
    doc = fitz.open(PDF_ROOT / pdf_stub)
    page = doc[page_index]
    # `locate_panel_bboxes`'s column-clustering assumes 2+ title hits to
    # infer a column boundary from -- with only ONE title on the page (every
    # one of these single-panel sheets) it can degenerate to spanning both
    # page columns or picking an unrelated left edge (confirmed on Delta 400:
    # returned x0=14, x1=587, the full page width, not the real ~72-300
    # single-column chart). Build the box directly instead, from 3 real,
    # always-present words: the "CHARACTERISTIC" title (top), the "Relative"
    # (log exposure) caption (bottom), and the "Density" y-axis label, whose
    # OWN x-position reliably sits just past the chart's right edge on every
    # one of these templates regardless of which page column it's in.
    words_all = page.get_text("words")

    def _find(regex):
        best = None
        for x0, y0, x1, y1, text, *_ in words_all:
            import re as _re
            if _re.search(regex, text) and (best is None or y0 < best[1]):
                best = (x0, y0, x1, y1)
        if best is None:
            raise RuntimeError(f"{regex!r} not found on page {page_index} of {pdf_stub}")
        return best

    title = _find(r"(?i)^characteristic$")
    caption = _find(r"(?i)^relative$")
    # Case-SENSITIVE on purpose: a lowercase "density" shows up in ordinary
    # body text elsewhere on some pages (confirmed on XP2 Super, a sentence
    # discussing exposure), which the topmost-match rule would otherwise
    # grab instead of the real axis label (always capitalized "Density").
    density_label = _find(r"^Density$")
    box = (title[0] - 10, title[3], density_label[2] + 15, caption[1])
    # The row-band boundary from locate_panel_bboxes sometimes lands a few
    # points ABOVE the real tick row's vertical center (confirmed on Pan F
    # Plus: real ticks center at y=434.9, band boundary at y=431.0) --
    # widen just for tick-search purposes, not for the visual region_bbox
    # used for curve tracing (padding that one doesn't matter either, get_
    # drawings-based tracing ignores text, but keep it separate for clarity).
    tick_box = (box[0], box[1], box[2], box[3] + 15)
    words = page.get_text("words")
    x_axis_calib_override = y_axis_calib_override = None
    try:
        fit_axis(words, x_tick_regex, "x", bbox=tick_box)
        fit_axis(words, y_tick_regex, "y", bbox=tick_box)
    except RuntimeError:
        # Real gotcha (2026-07-06): several of these sheets (FP4 Plus,
        # Delta 100, Delta 400, XP2 Super -- confirmed individually, not
        # assumed as a blanket vendor property, since HP5 Plus and Pan F
        # Plus DO have real extractable tick text on the exact same visual
        # template) render their tick digits as vector-drawn glyphs with
        # zero extractable text, same class of problem as the Fuji
        # vector-no-text case OCR already solved -- reuse ocr_axis_calib
        # instead of hand-deriving a gridline-position heuristic. Narrow,
        # tight sub-boxes (not the whole chart box) are required: OCR-ing
        # the whole box at once (title text + curve + gridlines all mixed
        # in) found only 1 spurious candidate in testing.
        x_tick_bbox = (box[0], box[3] - 20, box[2], box[3] + 15)
        y_tick_bbox = (box[2] - 95, box[1], box[2], box[3])
        x_axis_calib_override = ocr_axis_calib(page, x_tick_bbox, tick_regex=r"\d", axis="x")
        y_axis_calib_override = ocr_axis_calib(page, y_tick_bbox, tick_regex=r"\d\.\d", axis="y")
    doc.close()
    anchor_xy = (box[2] - 15, box[1] + 15)
    return ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="characteristic_curve",
        x_tick_regex=x_tick_regex, y_tick_regex=y_tick_regex,
        x_label="relative_log_exposure", y_label="density_diffuse_visual",
        curves=[CurveSpec("density", label_position_override=anchor_xy)],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, axis_word_bbox=tick_box,
        x_axis_calib_override=x_axis_calib_override, y_axis_calib_override=y_axis_calib_override,
        monotonic_direction="increasing", min_trace_points=8,
    )


def bw_single_curve_product(pdf_stub, product_name, iso, year, page_index, developer, process,
                             x_tick_regex=r"^[1234]$", y_tick_regex=r"^[123]\.0$"):
    chart = _single_curve_chart(pdf_stub, page_index, x_tick_regex, y_tick_regex)
    chart.metadata = {"developer": developer, "process": process, "curve_dimension": "single_representative_curve"}
    return ProductSpec(
        brand="ilford", product_name=product_name, application_area="photography",
        film_type="negative", medium="bw", iso=iso, year=year,
        layer_order=["density"], source_pdf=pdf_stub, charts=[chart],
        digitizer_notes="B&W film, Ilford single-curve template: the datasheet publishes exactly ONE "
                         "representative characteristic curve (stated explicitly to also cover other "
                         "formats), not per-developer/dev-time variants -- Strategy D (vector_position) "
                         "with a single unlabeled curve, identified via a hand-picked "
                         "label_position_override anchor near its own shoulder (verified via QA overlay), "
                         "since there is no inline text to disambiguate (nothing to disambiguate FROM).",
    )


def delta3200_product():
    """Both panels' tick numbers AND inline dev-time labels are vector-drawn
    glyphs with zero extractable text (confirmed directly: a text search of
    each chart's plot region returns nothing numeric at all -- the "7,9,12,16"
    that DOES turn up in a naive search is the surrounding body-text
    paragraph, "developed in ILFORD ILFOTEC DD-X 1+4 for 7, 9, 12 and 16
    minutes...", not the chart's own inline labels, a real false-positive
    trap caught by checking word y-coordinates against the real chart
    bbox). Ticks: OCR (`ocr_axis_calib`). Curve identity: OCR found "16"/"12"
    directly (real, tight bboxes) but not "9"/"7" (same font, tesseract just
    didn't segment them at the zoom tried) -- extrapolated their positions
    from the confirmed "16"/"12" spacing (evenly spaced inline labels is the
    same convention seen on every other multi-curve Ilford/Kodak dev-time
    chart), then verified the full set via QA overlay before trusting it."""
    pdf_stub = "film/ilford/Delta_3200-200209.pdf"
    page_index = 5
    import fitz
    from ocr_helpers import ocr_axis_calib
    doc = fitz.open(PDF_ROOT / pdf_stub)
    page = doc[page_index]
    ddx_box = (76, 87.3, 313.4, 240.6)
    micro_box = (76, 304, 314.9, 448.6)

    def _panel_calib(box):
        x_tick_bbox = (box[0], box[3] - 20, box[2], box[3] + 10)
        y_tick_bbox = (box[2] - 45, box[1], box[2], box[3])
        x_calib = ocr_axis_calib(page, x_tick_bbox, tick_regex=r"\d", axis="x")
        y_calib = ocr_axis_calib(page, y_tick_bbox, tick_regex=r"\d\.\d", axis="y")
        return x_calib, y_calib

    ddx_x_calib, ddx_y_calib = _panel_calib(ddx_box)
    micro_x_calib, micro_y_calib = _panel_calib(micro_box)
    doc.close()

    # Real OCR-found label midpoints (DD-X panel): 16@123.7, 12@132.5 --
    # spacing 8.8px, extrapolated for 9/7 (see docstring). x~265.7 for all 4.
    ddx_label_y = {"16min": 123.7, "12min": 132.5, "9min": 141.3, "7min": 150.1}
    # Microphen panel's y-calibration has an identical slope to DD-X's (same
    # template, just shifted down), so the same real value maps to a pixel
    # shifted by (ddx_intercept - micro_intercept) / slope -- not assumed,
    # derived from each panel's own real (OCR'd) calibration.
    dy = (ddx_y_calib[1] - micro_y_calib[1]) / ddx_y_calib[0]
    micro_label_y = {name: y + dy for name, y in ddx_label_y.items()}
    label_x = 265.7

    panels = [
        ("ddx", ddx_box, ddx_x_calib, ddx_y_calib, ddx_label_y, "ILFOTEC DD-X", "1+4, 20C (68F)"),
        ("microphen", micro_box, micro_x_calib, micro_y_calib, micro_label_y, "MICROPHEN", "stock, 20C (68F)"),
    ]
    charts = []
    for suffix, box, x_calib, y_calib, label_y, developer, process in panels:
        curves = [CurveSpec(name, label_position_override=(label_x, y)) for name, y in label_y.items()]
        chart = ChartSpec(
            pdf=pdf_stub, page_index=page_index, chart_id=f"characteristic_curve_{suffix}",
            x_tick_regex=r"^[1234]$", y_tick_regex=r"^[123]\.0$",
            x_label="relative_log_exposure", y_label="density_diffuse_visual",
            curves=curves,
            film_id="_unused", extraction_method="vector_position",
            region_bbox=box, x_axis_calib_override=x_calib, y_axis_calib_override=y_calib,
            monotonic_direction="increasing", min_trace_points=8, split_on_x_reversal=True,
            metadata={"developer": developer, "process": process, "curve_dimension": "development_time",
                      "curve_names": list(label_y.keys())},
        )
        charts.append(chart)
    return ProductSpec(
        brand="ilford", product_name="Delta 3200 Professional", application_area="photography",
        film_type="negative", medium="bw", iso=3200, year=2002,
        layer_order=["density"], source_pdf=pdf_stub, charts=charts,
        digitizer_notes="B&W high-speed film (real tested speed EI 1000/31 per this sheet's own text, "
                         "marketed/boxed as EI 3200 -- iso field here uses the box/product-name speed, "
                         "same convention as the product name itself). 2 developer panels (ILFOTEC DD-X, "
                         "MICROPHEN), each with 4 real development-time curves (7/9/12/16 min), inline "
                         "text labels -- same Strategy D pattern as Kodak's development_time BwPanel.",
    )


# Intermediate panel's own real tick rows -- found by direct inspection,
# not derived from `axis_tick_bboxes`'s generic margin heuristic, which
# assumes ticks sit just past the panel bbox's own edge; here the
# `locate_panel_bboxes` box runs well past the real tick row (all the way
# to the next panel's title) so that assumption doesn't hold.
_ORTHO_INTER_X_TICK_BBOX = (311.8, 465, 587, 485)
_ORTHO_INTER_Y_TICK_BBOX = (480, 330.6, 540, 544)


def _ortho_fill_band_chart(pdf_stub, page_index, chart_id, region_bbox, x_tick_bbox, y_tick_bbox,
                            curve_names, exclude_bboxes=(), min_width=None, band_gap=2.0):
    """Pictorial/High Contrast panels: curve ink is drawn as many small
    FILLED quad fragments (Strategy E, vector_fill_band -- see
    digitizer_core.extract_fill_band_curves' own docstring for the full
    "why" and how the fragment-banding works), not stroked paths at all,
    and neither panel has real extractable tick or gamma-label text (OCR
    needed for both axes -- reusing ocr_helpers.ocr_axis_calib, same
    mechanism built for Ilford Multigrade papers). `min_width` (a fragment
    x1-x0 floor) is the primary, robust way to strip vector-drawn gamma-
    label glyphs (all confirmed <10pt wide) from real curve fragments (all
    confirmed ~18-20pt wide) without risking clipping a real fragment that
    happens to sit close to its own label -- confirmed on High Contrast:
    a position-only exclude_bbox tight enough to spare the real curve
    dropped it anyway once the curve's tail passed back through the same
    small area as its label; min_width doesn't have that failure mode.
    exclude_bboxes is kept as a secondary belt-and-suspenders filter, not
    the primary one."""
    doc = fitz.open(PDF_ROOT / pdf_stub)
    page = doc[page_index]
    x_calib = ocr_axis_calib(page, x_tick_bbox, tick_regex=r"\d", axis="x")
    y_calib = ocr_axis_calib(page, y_tick_bbox, tick_regex=r"\d\.\d", axis="y")
    doc.close()
    return ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id=chart_id,
        x_tick_regex=r"\d", y_tick_regex=r"\d\.\d",
        x_label="relative_log_exposure", y_label="density_diffuse_visual",
        curves=[CurveSpec(n) for n in curve_names],
        film_id="_unused", extraction_method="vector_fill_band",
        region_bbox=region_bbox, monotonic_direction="increasing", min_trace_points=8,
        fill_band_rgb=(0.137, 0.122, 0.125), fill_band_tol=0.02,
        fill_band_exclude_bboxes=list(exclude_bboxes), fill_band_min_width=min_width, fill_band_gap=band_gap,
        x_axis_calib_override=x_calib, y_axis_calib_override=y_calib,
        metadata={"curve_dimension": "developer_contrast_gamma", "curve_names": curve_names},
    )


def ortho_plus_product():
    """3 contrast panels, each 2 curves labeled by real gamma value.
    Intermediate: real extractable tick/label text, Strategy D
    (vector_position), unchanged from the original version of this
    function. Pictorial/High Contrast: curve ink is small filled quad
    fragments, not stroked paths -- Strategy E (vector_fill_band), see
    `_ortho_fill_band_chart`'s own docstring. Both previously blocked
    (BLOCKED.md), unblocked 2026-07-07 once Strategy E was built (prompted
    by the user asking for every "blocked because not yet implemented"
    item, explicitly including this one, to be attempted -- excluding
    only genuinely-raster charts)."""
    pdf_stub = "film/ilford/Ortho+-200408.pdf"
    page_index = 2
    doc = fitz.open(PDF_ROOT / pdf_stub)
    page = doc[page_index]
    inter_box = locate_panel_bboxes(page, [r"(?i)^intermediate$"])[r"(?i)^intermediate$"]
    doc.close()

    inter_chart = ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="characteristic_curve_intermediate",
        x_tick_regex=r"^[1234]$", y_tick_regex=r"^[123]\.0$",
        x_label="relative_log_exposure", y_label="density_diffuse_visual",
        curves=[CurveSpec("gamma_1.00", label_regex=r"^G1\.00$"), CurveSpec("gamma_0.80", label_regex=r"^G0\.80$")],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=inter_box, x_tick_bbox=_ORTHO_INTER_X_TICK_BBOX, y_tick_bbox=_ORTHO_INTER_Y_TICK_BBOX,
        monotonic_direction="increasing", min_trace_points=8,
        metadata={"developer": "ILFORD PQ UNIVERSAL", "process": "1+9, 20C (68F), 4min/12min",
                  "curve_dimension": "developer_contrast_gamma", "curve_names": ["gamma_1.00", "gamma_0.80"]},
    )
    pictorial_chart = _ortho_fill_band_chart(
        pdf_stub, page_index, "characteristic_curve_pictorial",
        region_bbox=(300, 100, 486, 240), x_tick_bbox=(300, 236, 490, 252), y_tick_bbox=(486, 100, 520, 240),
        curve_names=["gamma_0.70", "gamma_0.62"],
        exclude_bboxes=[(432, 161, 457, 171), (456, 185, 482, 195)],
    )
    high_contrast_chart = _ortho_fill_band_chart(
        pdf_stub, page_index, "characteristic_curve_high_contrast",
        region_bbox=(300, 565, 486, 700), x_tick_bbox=(300, 700, 490, 716), y_tick_bbox=(486, 565, 520, 700),
        curve_names=["gamma_1.8", "gamma_1.2"], min_width=10, band_gap=6.0,
    )

    return ProductSpec(
        brand="ilford", product_name="Ortho Plus Copy Film", application_area="photography",
        film_type="negative", medium="bw", iso=80, year=2004,
        layer_order=["density"], source_pdf=pdf_stub,
        charts=[inter_chart, pictorial_chart, high_contrast_chart],
        digitizer_notes="B&W orthochromatic copy film. Datasheet publishes 3 contrast panels "
                         "(Pictorial/Intermediate/High Contrast), each 2 curves labeled by real gamma "
                         "value, all 3 now captured. Intermediate: real tick/label text, Strategy D "
                         "(vector_position). Pictorial/High Contrast: curve ink is drawn as many small "
                         "filled quad fragments (a bold line-weight rendering), not stroked paths -- "
                         "Strategy E (vector_fill_band, see digitizer_core.extract_fill_band_curves), "
                         "axis ticks read via OCR (ocr_helpers.ocr_axis_calib, same mechanism as Ilford "
                         "Multigrade papers) since neither panel has real extractable tick or gamma-"
                         "label text either. Both verified via QA overlay before shipping.",
    )


PRODUCTS = [
    lambda: bw_single_curve_product("film/ilford/HP5+-200407.pdf", "HP5 Plus", 400, 2004, 4,
                                     developer="ILFORD ILFOTEC HC", process="1+31, 6.5min, 20C (68F)"),
    lambda: bw_single_curve_product("film/ilford/FP4+-200404.pdf", "FP4 Plus", 125, 2004, 3,
                                     developer="ILFORD ILFOTEC HC", process="1+31, 8min, 20C (68F)"),
    lambda: bw_single_curve_product("film/ilford/PanF+-200407.pdf", "Pan F Plus", 50, 2004, 3,
                                     developer="ILFORD ILFOTEC HC", process="1+31, 4min, 20C (68F)"),
    # Delta 100 Professional (film/ilford/Delta_100-200209.pdf, page 3) is
    # NOT included here: confirmed via page.get_drawings() that its
    # Characteristic Curve panel has ZERO stroked vector paths in the chart
    # region -- the panel is a single embedded raster image (xref 24, rect
    # matches the chart area exactly), unlike every other film in this file
    # (Delta 400/3200, FP4+, HP5+, Pan F+, XP2 Super all use real vector
    # strokes). Same raster-tracing blocker class as the Fuji color group,
    # deprioritized this session -- see BLOCKED.md.
    lambda: bw_single_curve_product("film/ilford/Delta_400-200209.pdf", "Delta 400 Professional", 400, 2002, 5,
                                     developer="ILFORD ID-11", process="stock, 8min, 24C (75F)"),
    lambda: bw_single_curve_product("film/ilford/XP2_Super-200101.pdf", "XP2 Super", 400, 2001, 1,
                                     developer="C-41", process="standard C41 chemicals"),
    delta3200_product,
    ortho_plus_product,
]


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
