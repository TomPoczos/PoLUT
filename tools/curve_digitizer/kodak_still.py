"""
Digitizes Kodak still-photography film datasheets (film/kodak/*.pdf) into
consolidated-data/film/photography/{negative,reversal}/kodak/.

Usage: uv run kodak_still.py
"""

from pathlib import Path

from digitizer_core import ChartSpec, CurveSpec
from kodak_common import (
    COLOR_NEG_CHAR_LABELS, COLOR_NEG_SPECTRAL_LABELS,
    characteristic_chart, spectral_chart, spectral_dye_density_chart,
    get_panel_bboxes, overline_negative_calib, REVERSAL_DYE_DENSITY_LABELS,
)
from product import ProductSpec, digitize_product, run_products_parallel

PANEL_TITLES_4UP = [
    r"^Characteristic$", r"^(Spectral-Sensitivity|Spectral)$",
    r"^Spectral-Dye-Density$", r"^Modulation$",
]


MIN_DYE_DENSITY_PANEL_HEIGHT = 50  # below this, get_panel_bboxes' auto-locate box is degenerate
                                    # (title clustered into the wrong row, e.g. e29-Pro_100T_PRT.pdf) --
                                    # skip rather than digitize garbage; needs manual bbox like the
                                    # other DEFERRED-list files.


def portra_style_product(pdf_stub, page_index, product_name, iso, year, overline_minus=False,
                          cross_object_merge=False, char_box=None, skip_spectral=False,
                          skip_dye_density=False, dye_density_box=None, dye_density_cross_object_merge=False,
                          dye_density_page_index=None, medium="color"):
    """The e40xx-family 'KODAK PROFESSIONAL ... Film' 2016-revision sheets
    (Portra 400/160/800, Ektar 100) all share one page-3, 4-mini-panel
    'CURVES' template -- verified directly against Portra 400's rendered
    page and QA overlay before trusting this for its siblings.
    `overline_minus=True` for ~1997-2003-era sheets that draw negative-tick
    minus signs as vector overlines instead of text (see
    kodak_common.overline_negative_calib). `cross_object_merge=True` for
    sheets (e.g. e4039-Elite.pdf) that fragment each curve into many tiny
    separate drawing objects instead of one continuous path -- verify with
    a QA overlay before trusting, see extract_traces_in_region's docstring.
    `skip_spectral=True` for chromogenic B&W films (BW400CN, T400CN): they
    still print a C-41-style Characteristic Curve with real B/G/R dye-layer
    curves (this template applies as-is), but their Spectral-Sensitivity
    panel is a single panchromatic curve, not 3 Cyan-/Magenta-/Yellow-Forming
    curves, so spectral_chart's label search would just fail on it.
    `medium="bw"` for those same chromogenic B&W films, whose final image is
    monochrome despite the 3-dye-layer capture. `skip_dye_density=True` when
    the sheet's Spectral-Dye-Density panel isn't usable as-is (e.g. auto-locate
    box degenerate, or a genuinely different curve shape) -- see
    MIN_DYE_DENSITY_PANEL_HEIGHT, this is also auto-skipped when the
    auto-located box is too short to be real. `dye_density_box` overrides
    auto-locate the same way `char_box` does. `dye_density_page_index` overrides which page
    the dye-density box is read from when it isn't the same page as the characteristic
    curve (auto-locate is skipped whenever this is set, since it only searches `page_index`)."""
    pdf_path = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom") / pdf_stub
    boxes = get_panel_bboxes(pdf_path, page_index, PANEL_TITLES_4UP)
    if char_box is None:
        char_box = boxes[r"^Characteristic$"]
    charts = [characteristic_chart(pdf_stub, page_index, char_box)]
    charts[0].cross_object_merge = cross_object_merge
    if overline_minus:
        charts[0].x_axis_calib_override = overline_negative_calib(pdf_path, page_index, char_box)
    spectral_key = r"^(Spectral-Sensitivity|Spectral)$"
    if not skip_spectral and spectral_key in boxes:
        charts.append(spectral_chart(pdf_stub, page_index, boxes[spectral_key]))
    dye_density_key = r"^Spectral-Dye-Density$"
    if dye_density_box is None and dye_density_page_index is None:
        dye_density_box = boxes.get(dye_density_key)
    if not skip_dye_density and dye_density_box is not None:
        if dye_density_box[3] - dye_density_box[1] >= MIN_DYE_DENSITY_PANEL_HEIGHT:
            dd_page = dye_density_page_index if dye_density_page_index is not None else page_index
            dd_chart = spectral_dye_density_chart(pdf_stub, dd_page, dye_density_box)
            dd_chart.cross_object_merge = dye_density_cross_object_merge
            charts.append(dd_chart)
    return ProductSpec(
        brand="kodak", product_name=product_name, application_area="photography",
        film_type="negative", medium=medium, iso=iso, year=year,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=charts,
        digitizer_notes="4-panel 'CURVES' page template (Characteristic/Spectral-Sensitivity/"
                         "Spectral-Dye-Density/MTF), curves ID'd by inline B/G/R or "
                         "Yellow-/Magenta-/Cyan-Forming-Layer labels (Strategy D, vector_position)."
                         + (" Spectral-Sensitivity panel skipped: chromogenic B&W film, that panel "
                            "is a single panchromatic curve, not 3 dye-layer curves." if skip_spectral else ""),
    )


def portra_style_product_manual(pdf_stub, page_index, product_name, iso, year, char_box, spectral_box,
                                 dye_density_box=None, dye_density_page_index=None):
    """Like portra_style_product, but with hand-specified panel boxes -- for
    pages where the generic "Characteristic"/"Spectral-Sensitivity" title
    search is ambiguous (e.g. Portra 800's page has THREE "Characteristic
    Curves" panels -- native EI 800 plus Push 1/Push 2 -- sharing the same
    title text; auto-locate can only ever grab one occurrence per regex and
    isn't guaranteed to grab the native-speed one). Only the native-speed
    curve is captured here; pushed variants are real, separate data left for
    a future pass rather than mislabeled as the base ISO. `dye_density_box`:
    same hand-specified pattern for the Spectral-Dye-Density panel, when
    present on the page (not every push-variant layout has room for one --
    e.g. Portra 800's page replaces it with the Push 1/Push 2 panels
    entirely, confirmed by rendering the page directly)."""
    charts = [characteristic_chart(pdf_stub, page_index, char_box)]
    if spectral_box is not None:
        charts.append(spectral_chart(pdf_stub, page_index, spectral_box))
    if dye_density_box is not None:
        dd_page = dye_density_page_index if dye_density_page_index is not None else page_index
        charts.append(spectral_dye_density_chart(pdf_stub, dd_page, dye_density_box))
    return ProductSpec(
        brand="kodak", product_name=product_name, application_area="photography",
        film_type="negative", medium="color", iso=iso, year=year,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=charts,
        digitizer_notes="Manually-boxed panel (page has multiple same-titled "
                         "Characteristic-Curves panels for different EI push levels; "
                         "only the native/unpushed EI is captured here).",
    )


def add_push_panel(product, pdf_stub, page_index, char_box, chart_suffix, push_label,
                    overline_minus=False, monotonic="increasing", cross_object_merge=False):
    """Appends an additional 'Characteristic Curves / Push N' panel to an
    existing color-negative ProductSpec, as its own chart. Confirmed
    (2026-07-05, prompted by the user directly asking whether negative
    color film had the same multi-panel gap B&W film did) that several
    Kodak color-negative sheets publish real, fully push-processed
    B/G/R characteristic curves alongside the native-speed one -- a
    genuinely different real curve (extended development for uprated
    exposure), same template (Strategy D, inline B/G/R labels), just a
    second/third panel on the same page that a naive single-panel capture
    silently drops. See BLOCKED.md's 'not blocked' section for the full
    list this was confirmed on. `chart_suffix`: e.g. "push1"/"push2".
    `push_label`: real text describing the push level, e.g. "EI 800
    (Push 1)", stored as chart metadata."""
    pdf_path = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom") / pdf_stub
    chart = characteristic_chart(pdf_stub, page_index, char_box, monotonic=monotonic)
    chart.chart_id = f"characteristic_curve_{chart_suffix}"
    chart.cross_object_merge = cross_object_merge
    chart.metadata = {"push_label": push_label}
    if overline_minus:
        chart.x_axis_calib_override = overline_negative_calib(pdf_path, page_index, char_box)
    product.charts.append(chart)
    return product


def gold_style_product(pdf_stub, page_index, region_bbox, x_tick_bbox, product_name, iso, year, log_h_ref,
                        spectral_box=None, dye_density_box=None):
    """E-7022 Gold 100/200: two single-column characteristic-curve mini-charts
    stacked on one page (one per speed), sharing one Spectral-Sensitivity/
    Spectral-Dye-Density pair off to the side. This era's negative tick labels
    print the minus sign as a small drawn overline, not a text glyph, so
    "-3.0"/"-2.0"/"-1.0" extract as bare "3.0"/"2.0"/"1.0" indistinguishable
    from a real unsigned tick -- x_tick_bbox must be pinned to just the
    right-hand (genuinely unsigned) 0.0/1.0 ticks and let the fit extrapolate
    the rest. Verified against the rendered page + QA overlay for Gold 100/200
    before trusting this pattern for siblings using the same era/template.
    `dye_density_box`: hand-specified (the page's row/column auto-locate
    breaks on this layout -- 2 stacked "GOLD <speed> Film Characteristic
    Curves" titles confuse locate_panel_bboxes' row clustering). Kodak
    publishes ONE combined chart for both speeds here (title says "GOLD 100
    and 200 Films"), so the same panel is attached to BOTH product JSONs
    when given, not treated as speed-specific -- same precedent as the
    Portra 160NC/160VC shared Spectral-Sensitivity chart. Needs
    cross_object_merge=True: both curves are fragmented into 2 drawing
    objects each (confirmed via trace dump), not 1 -- verified via QA
    overlay this recovers the full curves without cross-contamination.
    `spectral_box` deliberately NOT wired up here even though the same page
    has a Spectral-Sensitivity panel too: that panel's fragmentation is far
    denser (48 tiny ~4pt-wide fragments per curve, not 2), and
    cross_object_merge=True on it fused all 3 dye layers into one trace
    (confirmed via QA overlay -- red/green layers lost entirely). Would need
    `merge_strategy="sequential_band"` (the Portra/Supra-Endura pattern)
    properly tuned for this box before it's trustworthy; left as a known gap
    rather than shipping wrong data."""
    charts = [
        ChartSpec(
            pdf=pdf_stub, page_index=page_index, chart_id="characteristic_curve",
            x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0",
            x_label="log_exposure_lux_seconds", y_label="density_status_m",
            curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_CHAR_LABELS],
            film_id="_unused", extraction_method="vector_position",
            region_bbox=region_bbox, x_tick_bbox=x_tick_bbox, monotonic_direction="increasing",
        ),
    ]
    if dye_density_box is not None:
        dd_chart = spectral_dye_density_chart(pdf_stub, page_index, dye_density_box)
        dd_chart.cross_object_merge = True
        charts.append(dd_chart)
    return ProductSpec(
        brand="kodak", product_name=product_name, application_area="photography",
        film_type="negative", medium="color", iso=iso, year=year,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=charts,
        digitizer_notes=f"Two-speeds-per-page 'CURVES' template (E-7022 family); Log H Ref {log_h_ref}; "
                         "x-axis minus signs are drawn overlines, not text -- tick fit pinned to the "
                         "unsigned 0.0/1.0 ticks only. Spectral-sensitivity/dye-density panels on this "
                         "sheet are shared across both speeds (Kodak publishes one combined chart for "
                         "both, not per-speed data) -- the same panel is attached to both Gold 100 and "
                         "Gold 200's JSON when captured.",
    )


def intranegative_reversal_dupe_product(pdf_stub, page_index, char_box, product_name, iso, year,
                                         x_axis_calib_override=None, monotonic="decreasing",
                                         dye_density_page_index=None, dye_density_box=None,
                                         dye_density_labels=REVERSAL_DYE_DENSITY_LABELS):
    """Kodak Ektachrome Duplicating Film EDUPE (e2529): a real intranegative/
    duplicating-stock film_type, not negative or reversal -- it duplicates an
    EXISTING transparency onto itself (density decreases with exposure, like
    a reversal material, but its purpose is duplication not original
    capture). Uses characteristic_chart() directly (not portra_style_product)
    because this sheet's panel titles are "Characteristic Curves, Roll
    Formats" / "..., Sheet Formats", not the standard 4-panel-template title
    set portra_style_product's auto-locate expects -- get_panel_bboxes would
    either fail outright or grab the wrong box."""
    chart = characteristic_chart(pdf_stub, page_index, char_box, monotonic=monotonic)
    if x_axis_calib_override is not None:
        chart.x_axis_calib_override = x_axis_calib_override
    charts = [chart]
    if dye_density_box is not None:
        dd_page = dye_density_page_index if dye_density_page_index is not None else page_index
        charts.append(spectral_dye_density_chart(pdf_stub, dd_page, dye_density_box,
                                                   labels=dye_density_labels))
    return ProductSpec(
        brand="kodak", product_name=product_name, application_area="photography",
        film_type="intranegative", medium="color", iso=iso, year=year,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=charts,
        digitizer_notes="Duplicating film (intranegative): makes a same-size copy of an existing "
                         "transparency, not an original camera exposure. Density decreases with "
                         "exposure like a reversal material. Curves ID'd by inline R/G/B labels "
                         "(Strategy D, vector_position).",
    )


PRODUCTS = [
    lambda: portra_style_product("film/kodak/e4050_portra_400-2016.pdf", 3, "Portra 400", 400, 2016),
    lambda: portra_style_product("film/kodak/e4051_Portra_160-2016.pdf", 3, "Portra 160", 160, 2016),
    lambda: add_push_panel(
        add_push_panel(
            portra_style_product_manual("film/kodak/e4040_portra_800-2016.pdf", 3, "Portra 800", 800, 2016,
                                         char_box=(57, 55, 373, 290), spectral_box=None,
                                         # CORRECTION: earlier claim that this page's Push 1/Push 2
                                         # panels "replace" the dye-density panel entirely was checked
                                         # against page_index=3 only -- the real Spectral-Dye-Density
                                         # panel is on the FOLLOWING page (4), same off-page-from-char
                                         # pattern confirmed on several other e7xxx/e40xx-era sheets in
                                         # this file (Royal Gold 200, Ultra Max 800, Bright Sun GA100).
                                         dye_density_page_index=4, dye_density_box=(48, 75, 265, 315)),
            "film/kodak/e4040_portra_800-2016.pdf", 3, (40, 300, 373, 510), "push1", "EI 1600 (Push 1)"),
        "film/kodak/e4040_portra_800-2016.pdf", 3, (330, 55, 570, 265), "push2", "EI 3200 (Push 2)"),
    lambda: portra_style_product("film/kodak/e4046_ektar_100-2016.pdf", 3, "Ektar 100", 100, 2016),
    # --- Portra 160NC/160VC/400NC/400VC (e4040-Portra-2009.pdf, pub E-4040,
    # pages 7-10): the pre-reformulation "NC"(Natural Color)/"VC"(Vivid
    # Color) Portra line -- genuinely distinct historical products from the
    # modern single "Portra 400"/"Portra 160" above (confirmed: this old
    # sheet's own 400VC panel shares figure code E4040D, and modern Portra
    # 400's own panel reuses E4040C -- Kodak's later reformulation carried
    # the NC variant's own measured curve forward as the new "Portra 400").
    # 2006/2008/2009 print-date siblings of this file are the same data
    # (confirmed via identical figure codes E4040A-T across all three) --
    # the 2009 file is used as the single authoritative source. Same 4-panel
    # template as the other e40xx-family sheets; NC/VC pairs share one
    # Spectral-Sensitivity chart per Kodak's own figure code (E4040F for
    # 160NC/160VC, E4040G for 400NC/400VC) since color-coupler differences
    # don't change the emulsion's own raw spectral sensitivity -- confirmed
    # not a box-mixup, both panels' own text independently cites the same
    # shared code.
    lambda: portra_style_product("film/kodak/e4040-Portra-2009.pdf", 7, "Portra 160NC", 160, 2009),
    lambda: portra_style_product("film/kodak/e4040-Portra-2009.pdf", 8, "Portra 160VC", 160, 2009),
    lambda: portra_style_product("film/kodak/e4040-Portra-2009.pdf", 9, "Portra 400NC", 400, 2009),
    lambda: portra_style_product("film/kodak/e4040-Portra-2009.pdf", 10, "Portra 400VC", 400, 2009),
    lambda: gold_style_product("film/kodak/E7022-Gold_100_200.pdf", 3, (50, 55, 300, 290), (200, 270, 300, 280),
                                "Gold 100", 100, 2000, 0.84,
                                dye_density_box=(326, 286.69, 604, 784)),
    lambda: gold_style_product("film/kodak/E7022-Gold_100_200.pdf", 3, (50, 311, 300, 546), (200, 526, 300, 536),
                                "Gold 200", 200, 2000, -1.14,
                                dye_density_box=(326, 286.69, 604, 784)),
    lambda: portra_style_product("film/kodak/E7023_max_400-2016.pdf", 3, "Ultra Max 400", 400, 2016),
    lambda: portra_style_product("film/kodak/e4035-100UC_400UC.pdf", 5, "Ultra Color 100UC", 100, 2000),
    lambda: add_push_panel(
        portra_style_product_manual("film/kodak/e4035-100UC_400UC.pdf", 6, "Ultra Color 400UC", 400, 2000,
                                     char_box=(65, 65, 355, 300), spectral_box=(65, 309, 355, 570),
                                     dye_density_box=(336, 309, 604, 784)),
        "film/kodak/e4035-100UC_400UC.pdf", 6, (335, 60, 570, 275), "push1", "EI 800 (Push 1)"),
    lambda: portra_style_product("film/kodak/E7024-Ultra_Max_800.pdf", 2, "Ultra Max 800", 800, 2007,
                                  # Spectral-Dye-Density panel is on the following page (3), same
                                  # off-page-from-char pattern as Portra 800/Royal Gold 200 above.
                                  dye_density_page_index=3, dye_density_box=(48, 75, 265, 315)),
    lambda: portra_style_product("film/kodak/e2328-GA100.pdf", 2, "Bright Sun GA100", 100, 2000, overline_minus=True,
                                  dye_density_page_index=3, dye_density_box=(40, 73, 270, 325)),
    lambda: portra_style_product("film/kodak/e2509-2000_01.pdf", 3, "Royal Gold 400", 400, 2000, overline_minus=True,
                                  dye_density_box=(171.4, 314.5, 412.3, 570.9)),
    # CORRECTION (see feedback memory on verifying doc-comment claims): the earlier "no
    # Density/Dye text at all" claim below was checked against page_index=2 (the
    # characteristic-curve page) only -- this 4-page, single-product PDF's own
    # Spectral-Dye-Density panel is on page 3 (the "NOTICE"/copyright page), same
    # off-page-from-char-box pattern as several other e7xxx-era sheets in this file.
    # 2-curve (Minimum/Midscale) convention, real inline labels.
    lambda: portra_style_product("film/kodak/e7006-2002_03.pdf", 2, "Royal Gold 200", 200, 2002,
                                  overline_minus=True,
                                  dye_density_page_index=3, dye_density_box=(48, 75, 280, 325)),
    lambda: portra_style_product("film/kodak/e29-Pro_100T_PRT.pdf", 3, "Pro 100T PRT", 100, 1999, overline_minus=True,
                                  dye_density_box=(316, 74, 604, 322)),
    # dye_density_cross_object_merge=True: this panel's Minimum Density curve is
    # fragmented into many small (<12pt) drawing objects -- without merging, only
    # two tiny fragments near the "Minimum" label survived min_trace_points
    # filtering, and d_min silently captured that 405-413nm sliver instead of the
    # real 400-700nm curve. Confirmed fixed via QA overlay.
    lambda: portra_style_product("film/kodak/e4039-Elite.pdf", 6, "Elite Color 200", 200, 2000,
                                  cross_object_merge=True, dye_density_cross_object_merge=True),
    # NOTE: y-axis tick fit only found 4 of 5 ticks (missing "4.0"); density
    # baseline comes out ~0.5 units low (slightly negative at the toe where
    # it should read ~0.2-0.3) even though the trace SHAPE/separation is
    # confirmed correct via QA overlay. Small calibration offset, not
    # rechecked further given diminishing returns on this one file.
    lambda: add_push_panel(
        portra_style_product("film/kodak/e4039-Elite.pdf", 7, "Elite Color 400", 400, 2000,
                              cross_object_merge=True, overline_minus=True,
                              char_box=(54, 58, 354, 354),
                              dye_density_box=(320, 261, 604, 496)),
        "film/kodak/e4039-Elite.pdf", 7, (335, 40, 570, 252), "push1", "EI 800 (Push 1)",
        overline_minus=True, cross_object_merge=True),
    lambda: portra_style_product("film/kodak/e7013-HD400.pdf", 4, "High Definition 400", 400, 2000,
                                  char_box=(70, 60, 335, 290),
                                  # dye_density_cross_object_merge=True: the Midscale Neutral trace
                                  # switches from solid to a DASHED line partway across (real source
                                  # style, not an artifact) -- without merging, extraction only
                                  # followed the solid portion (stopped at ~591nm of a 360-760nm
                                  # range), silently dropping the dashed continuation. Confirmed via
                                  # QA overlay this recovers the full curve without corrupting d_min.
                                  dye_density_box=(195.8, 342.7, 435.9, 599.6),
                                  dye_density_cross_object_merge=True),
    lambda: portra_style_product("film/kodak/e7017-HD200.pdf", 4, "High Definition 200", 200, 2000,
                                  char_box=(70, 60, 335, 290), overline_minus=True,
                                  dye_density_box=(194.0, 323.3, 434.6, 577.6)),
    lambda: portra_style_product("film/kodak/e2e-Profoto_100.pdf", 2, "Profoto 100", 100, 1997,
                                  char_box=(70, 60, 335, 290), overline_minus=True),
    lambda: portra_style_product("film/kodak/e26-Vericolor_III.pdf", 3, "Vericolor III Professional", 160, 1996,
                                  char_box=(60, 60, 280, 275), overline_minus=True,
                                  dye_density_cross_object_merge=True),
    lambda: portra_style_product("film/kodak/e2468-Portra_100T.pdf", 4, "Portra 100T", 100, 2003,
                                  char_box=(70, 60, 335, 290), overline_minus=True),
    lambda: portra_style_product("film/kodak/e116-Ektapress.pdf", 4, "Ektapress PJ100", 100, 2000,
                                  char_box=(46, 110, 290, 345), overline_minus=True,
                                  # Auto-located dye_density box's right edge (381) cut off the
                                  # chart before its real ~700nm right tick (at x~406) -- confirmed
                                  # via word-position dump. Also fragmented like other 2000-era
                                  # sheets, hence cross_object_merge.
                                  dye_density_box=(195, 398, 435, 615),
                                  dye_density_cross_object_merge=True),
    lambda: add_push_panel(
        add_push_panel(
            portra_style_product("film/kodak/e116-Ektapress.pdf", 5, "Ektapress PJ400", 400, 2000,
                                  char_box=(46, 110, 290, 350), overline_minus=True,
                                  # Native-speed Spectral-Dye-Density panel is on the FOLLOWING
                                  # page (6), not page 5 -- page 5 holds 2 of this product's 3
                                  # Characteristic Curves panels (native + Push 1) with no room
                                  # left for a dye-density panel; page 6 pairs a
                                  # Spectral-Sensitivity panel (shared across all 3 EI levels,
                                  # single "0.2 above D-min" curve set) with the real
                                  # Spectral-Dye-Density panel, confirmed via direct page-text dump.
                                  dye_density_page_index=6, dye_density_box=(325, 25, 560, 265)),
            "film/kodak/e116-Ektapress.pdf", 5, (330, 110, 570, 345), "push1", "EI 800 (Push 1)",
            overline_minus=True),
        "film/kodak/e116-Ektapress.pdf", 5, (190, 395, 400, 615), "push2", "EI 1600 (Push 2)",
        overline_minus=True),
    lambda: portra_style_product("film/kodak/e2519-2003_05.pdf", 6, "Supra 100", 100, 2000, overline_minus=True,
                                  dye_density_box=(195.4, 325.2, 434.1, 579.7)),
    lambda: add_push_panel(
        portra_style_product("film/kodak/e2519-2003_05.pdf", 7, "Supra 400", 400, 2000,
                              char_box=(46, 50, 290, 295), overline_minus=True,
                              dye_density_box=(320, 296, 558, 548)),
        "film/kodak/e2519-2003_05.pdf", 7, (40, 315, 300, 537), "push1", "EI 800 (Push 1)",
        overline_minus=True),
    # CORRECTION: earlier claim of "no Dye text at all" on Supra 800's own char page (8) was
    # right about that page, but its real Spectral-Dye-Density panel is on the FOLLOWING page
    # (9), stacked below a Spectral-Sensitivity panel -- same off-page pattern confirmed
    # elsewhere in this file, not genuinely absent.
    lambda: add_push_panel(
        add_push_panel(
            portra_style_product("film/kodak/e2519-2003_05.pdf", 8, "Supra 800", 800, 2000,
                                  char_box=(46, 50, 290, 295), overline_minus=True,
                                  dye_density_page_index=9, dye_density_box=(45, 335, 230, 585)),
            "film/kodak/e2519-2003_05.pdf", 8, (200, 325, 435, 550), "push1", "EI 1600 (Push 1)",
            overline_minus=True),
        "film/kodak/e2519-2003_05.pdf", 8, (335, 55, 570, 280), "push2", "EI 3200 (Push 2)",
        overline_minus=True),
    lambda: portra_style_product("film/kodak/e4026-2002_06.pdf", 6, "Royal Supra 200", 200, 2002,
                                  char_box=(46, 50, 290, 295), overline_minus=True,
                                  dye_density_box=(194.0, 325.6, 434.6, 579.9)),
    lambda: portra_style_product("film/kodak/e4029-2003_05.pdf", 6, "Supra 200", 200, 2003,
                                  char_box=(46, 50, 290, 295), overline_minus=True,
                                  dye_density_box=(195.6, 328.2, 433.9, 577.2)),
    lambda: add_push_panel(
        portra_style_product("film/kodak/e4026-2002_06.pdf", 7, "Royal Supra 400", 400, 2002,
                              char_box=(46, 50, 290, 295), overline_minus=True,
                              dye_density_box=(320, 314, 558, 566)),
        "film/kodak/e4026-2002_06.pdf", 7, (40, 320, 290, 545), "push1", "EI 800 (Push 1)",
        overline_minus=True),
    # CORRECTION: same off-page pattern as Supra 800 above -- real Spectral-Dye-Density panel
    # is on the following page (9), not genuinely absent.
    lambda: add_push_panel(
        add_push_panel(
            portra_style_product("film/kodak/e4026-2002_06.pdf", 8, "Royal Supra 800", 800, 2002,
                                  char_box=(46, 50, 290, 295), overline_minus=True,
                                  dye_density_page_index=9, dye_density_box=(45, 75, 235, 325)),
            "film/kodak/e4026-2002_06.pdf", 8, (40, 325, 290, 545), "push1", "EI 1600 (Push 1)",
            overline_minus=True),
        "film/kodak/e4026-2002_06.pdf", 8, (335, 60, 570, 290), "push2", "EI 3200 (Push 2)",
        overline_minus=True),
    lambda: portra_style_product("film/kodak/f4036-BW400CN.pdf", 4, "BW400CN", 400, 2003,
                                  char_box=(340, 45, 560, 280), skip_spectral=True, medium="bw"),
    lambda: portra_style_product("film/kodak/f2350-T400CN.pdf", 5, "T400 CN", 400, 1999,
                                  char_box=(46, 190, 290, 430), overline_minus=True,
                                  skip_spectral=True, medium="bw",
                                  # Page layout here is 3 stacked single-column panels, not the
                                  # standard 2x2 grid -- PANEL_TITLES_4UP's row/column clustering
                                  # produced a box truncated above the WAVELENGTH tick row (crashed
                                  # with "0 tick labels" before this override; confirmed via direct
                                  # render + word-position dump that the real panel runs to y~260).
                                  dye_density_box=(318, 44, 604, 270)),
    lambda: portra_style_product("film/kodak/f4012-Portra_400BW.pdf", 5, "Portra 400BW", 400, 2002,
                                  char_box=(40, 60, 335, 290), overline_minus=True,
                                  skip_spectral=True, medium="bw"),
    lambda: intranegative_reversal_dupe_product(
        "film/kodak/e2529-Ektachrome_EDUPE.pdf", 5, (335, 55, 570, 290), "Ektachrome Duplicating Film EDUPE (Roll)",
        8, 2000, x_axis_calib_override=(0.027872469602715798, -13.624288353554256),
        # Spectral-Dye-Density panel is on the FOLLOWING page (6), stacked below a
        # Modulation-Transfer and a Spectral-Sensitivity panel. This sheet labels its 4th
        # curve bare "Neutral" (not "Visual Neutral" like other reversal-style panels), so
        # REVERSAL_DYE_DENSITY_LABELS' `^Visual$` regex wouldn't match -- overridden with a
        # local label set for this file. Consistent with EDUPE's reversal-like
        # (density-falls-with-exposure) behavior despite being classified
        # film_type="intranegative".
        dye_density_page_index=6, dye_density_box=(198, 300, 405, 555),
        dye_density_labels=[("yellow", r"^Yellow$"), ("magenta", r"^Magenta$"),
                             ("cyan", r"^Cyan$"), ("visual_neutral", r"^Neutral$")]),
    lambda: portra_style_product("film/kodak/le1-2003_04.pdf", 4, "Law Enforcement Film LE100", 100, 2003,
                                  overline_minus=True, dye_density_cross_object_merge=True),
    lambda: portra_style_product("film/kodak/le1-2003_04.pdf", 5, "Law Enforcement Film LE400", 400, 2003,
                                  char_box=(40, 150, 290, 360), skip_spectral=True, overline_minus=True,
                                  # Spectral-Dye-Density panel is on the FOLLOWING page (6), in the
                                  # top half above where LE800's own char curve begins.
                                  dye_density_page_index=6, dye_density_box=(190, 25, 400, 270)),
    lambda: portra_style_product("film/kodak/e182-Pro_Films.pdf", 7, "Pro 100 PRN", 100, 1997, overline_minus=True),
    lambda: portra_style_product("film/kodak/e182-Pro_Films.pdf", 9, "Pro 400 PPF", 400, 1997, overline_minus=True),
    lambda: portra_style_product("film/kodak/e182-Pro_Films.pdf", 10, "Pro 400 MC PMC", 400, 1997, overline_minus=True),
    lambda: portra_style_product("film/kodak/e182-Pro_Films.pdf", 11, "Pro 1000 PMZ", 1000, 1997, overline_minus=True,
                                  # Auto-located box's right edge (372) cut off before the real
                                  # ~700nm tick (at x~391) -- confirmed via word-position dump.
                                  dye_density_box=(170, 314, 420, 540),
                                  dye_density_cross_object_merge=True),
]

# DEFERRED (non-standard layout, needs bespoke handling):
# - e26-Vericolor_III.pdf: long footnote block before the chart shifts the
#   panel position/height significantly off the standard template.
# - e2468-Portra_100T.pdf: tick/label reading order doesn't match the
#   standard template either (single "-?\d\.0" tick cluster found after
#   filtering) -- needs its own hand-inspected bbox, not the generic path.
# - e7017-HD200.pdf, e2e-Profoto_100.pdf: sanity check caught bad output
#   (identical bounding boxes / <5 points) -- these older single-panel
#   sheets don't match the 4-panel template's title/geometry assumptions;
#   need manual bbox inspection like HD400 got (char_box + possibly rank
#   matching, see lesson below).
#
# LESSON: Portra 800 and Ultra Color 400UC BOTH silently grabbed the wrong
# panel on first pass (a pushed-EI "Characteristic Curves" panel instead of
# the native speed) because the page has multiple identically-titled panels
# and topmost-match doesn't reliably pick the "right" one when two titles
# are only ~1pt apart in y. Fixed via portra_style_product_manual() with a
# hand-verified box. RESOLVED 2026-07-05: every Kodak color-negative sheet
# with push variants (Elite Color 400, Ektapress PJ400, Portra 800, Ultra
# Color 400UC, Supra 400/800, Royal Supra 400/800) now has its Push 1/Push 2
# panels captured too, via add_push_panel() appending each as its own chart
# to the base ProductSpec -- not silently dropped anymore. See BLOCKED.md
# (now updated to remove this from the "pending" list).


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
