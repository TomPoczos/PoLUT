"""
Digitizes Kodak black-and-white film datasheets (film/kodak/*.pdf) into
consolidated-data/film/photography/negative/kodak/ (medium="bw").

Different curve convention from color films: B&W "Characteristic Curves"
panels plot 2-4 curves for ONE developer at different DEVELOPMENT TIMES
(e.g. "11 minutes"/"8 minutes"/"6 minutes"), not R/G/B dye layers. Unlike
color reversal/negative film (one standardized E-6/C-41 process, so one
panel per product is everything), B&W stock is commonly published with
SEVERAL of these panels on the same page -- one per developer a photographer
might reasonably choose (D-76, T-MAX Developer, T-MAX RS, HC-110, DK-50,
XTOL, Microdol-X...), each a genuinely different, real characteristic curve.
An earlier version of this file captured only ONE representative panel per
product ("other developers' panels not captured here") -- confirmed (2026-
07-05, prompted by the user directly) to have silently dropped real data on
most multi-panel sheets (T-Max 400: 2 of 3 panels dropped; Plus-X 125: 1 of
2). Every product here now captures EVERY "Characteristic Curves" panel
found on its product's own page(s), each as its own named chart
(`characteristic_curve_<developer-slug>`) carrying its own real metadata
(developer, process, densitometry, exposure) read off that panel's own text
box -- not shared/guessed from a sibling panel. Still Strategy D
(vector_position); development-time (or developer-name, or
processor-speed) numbers as inline labels instead of B/G/R.

Usage: uv run kodak_bw.py
"""

from dataclasses import dataclass, field
from pathlib import Path

from digitizer_core import ChartSpec, CurveSpec
from kodak_common import overline_negative_calib
from product import ProductSpec, digitize_product, run_products_parallel

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")


@dataclass
class BwPanel:
    """One 'Characteristic Curves' panel -- one developer/process, several
    development-time (or developer-name, or processing-speed) curves.
    `chart_suffix`: short slug for this panel's chart_id, e.g. "d76",
    "tmaxdeveloper", "tmaxrs", "hc110dilb". `process`/`densitometry`/
    `exposure`: real text transcribed from THIS panel's own info box, not
    assumed from a sibling panel on the same page -- different developer
    panels on the same sheet sometimes use different tank/temperature/time
    combinations."""
    chart_suffix: str
    page_index: int
    char_box: tuple
    curves: list  # [(curve_name, label_regex), ...]
    developer: str
    process: str = ""
    densitometry: str = "Diffuse Visual"
    exposure: str = "Daylight"
    monotonic: str = "increasing"
    overline_minus: bool = False
    x_tick_regex: str = r"-?\d\.0"
    min_trace_points: int = 12
    curve_dimension: str = "development_time"  # or "developer" or "processing_speed"
    split_on_x_reversal: bool = False
    pdf_stub_override: str | None = None  # use a different source PDF than the product's default
    cross_object_merge: bool = False  # opt-in, verify with QA overlay -- see extract_traces_in_region


_DIMENSION_NOTE = {
    "development_time": "curves are development-time variants of ONE developer (not R/G/B "
                         "dye layers), inline-labeled by development time in minutes",
    "developer": "curves are the SAME development time across different developers, "
                 "inline-labeled by developer name, not development time",
    "processing_speed": "curves are printer/processor SPEED variants (not R/G/B dye layers, "
                         "not development time), inline-labeled by feet-per-minute; density "
                         "DECREASES with exposure (duplicating stock, like a reversal material)",
}


def bw_product(pdf_stub, product_name, iso, year, panels: list[BwPanel]):
    charts = []
    for p in panels:
        panel_pdf_stub = p.pdf_stub_override if p.pdf_stub_override is not None else pdf_stub
        panel_pdf_path = PDF_ROOT / panel_pdf_stub
        chart = ChartSpec(
            pdf=panel_pdf_stub, page_index=p.page_index, chart_id=f"characteristic_curve_{p.chart_suffix}",
            x_tick_regex=p.x_tick_regex, y_tick_regex=r"\d\.0",
            x_label="log_exposure_lux_seconds", y_label="density_diffuse_visual",
            curves=[CurveSpec(name, label_regex=spec) if isinstance(spec, str)
                    else CurveSpec(name, label_position_override=spec) for name, spec in p.curves],
            film_id="_unused", extraction_method="vector_position",
            region_bbox=p.char_box, monotonic_direction=p.monotonic, min_trace_points=p.min_trace_points,
            split_on_x_reversal=p.split_on_x_reversal, cross_object_merge=p.cross_object_merge,
            metadata={
                "developer": p.developer, "process": p.process, "densitometry": p.densitometry,
                "exposure": p.exposure, "curve_dimension": p.curve_dimension,
                "curve_names": [n for n, _ in p.curves],
            },
        )
        if p.overline_minus:
            chart.x_axis_calib_override = overline_negative_calib(panel_pdf_path, p.page_index, p.char_box,
                                                                    tick_regex=p.x_tick_regex)
        charts.append(chart)
    panel_notes = "; ".join(f"{p.chart_suffix} ({_DIMENSION_NOTE[p.curve_dimension]})" for p in panels)
    return ProductSpec(
        brand="kodak", product_name=product_name, application_area="photography",
        film_type="negative", medium="bw", iso=iso, year=year,
        layer_order=["density"],
        source_pdf=pdf_stub, charts=charts,
        digitizer_notes=f"B&W film: every 'Characteristic Curves' panel found for this product "
                         f"is captured as its own chart (Strategy D, vector_position), each with "
                         f"its own real developer/process/densitometry metadata -- {panel_notes}.",
    )


PRODUCTS = [
    # --- Old (pre-2007) T-Max 100/400 formulation (f32-TMAX.pdf, F-32) ----
    # Discontinued: this sheet's own cover page says "These films were
    # replaced by KODAK PROFESSIONAL T-MAX Films" (the modern f4016/f4043
    # lineage above) -- a genuinely different, earlier emulsion generation,
    # not a reprint of the same data (confirmed distinct figure-code prefix,
    # F002_05xx here vs F4016x/F4043x on the modern sheets). f32-199910.pdf
    # and f32-TMAX-200109.pdf are older printings of this same F-32 book
    # (identical page structure/figure codes), not digitized separately --
    # see BLOCKED.md.
    #
    # IMPORTANT lesson (found via QA-overlay inspection, not any automated
    # check -- both cases below reported 0 violations and looked fine
    # numerically despite being wrong): T-Max 100's tmaxrs and duraflort
    # panels (page 14) each only have 2 real separable vector traces for
    # 4 printed curves -- the exclusive nearest-label assignment grabbed
    # the SAME 2 real traces for whichever 2 labels were requested, so
    # asking for "8min"/"6min" silently produced a jagged trace that
    # doesn't track either real line (confirmed visually). Both panels are
    # dropped entirely for T-Max 100 rather than ship a plausible-looking
    # wrong curve. T-Max 400's tmaxdeveloper panel (page 15) has the same
    # 2-real-traces-for-4-labels problem for its own "9min"/"7min"/"5min"
    # trio -- of those, only ONE real trace besides "11min" is unambiguous
    # (confirmed by anchoring on the trace's own endpoint and visually
    # matching it to the real "7 min" line); shipped as "7min" only.
    lambda: bw_product("film/kodak/f32-TMAX.pdf", "T-Max 100 (Pre-2007 Formulation)", 100, 2002, [
        BwPanel("tmaxdeveloper", 14, (55, 55, 290, 285),
                [("11min", r"^11$"), ("9min", r"^9$"), ("7min", r"^7$"), ("5min", r"^5$")],
                developer="T-MAX Developer", process="Small Tank, 75F (24C)", overline_minus=True),
        BwPanel("d76", 14, (55, 295, 290, 520),
                [("12min", r"^12$"), ("10min", r"^10$"), ("8min", r"^8$"), ("6min", r"^6$")],
                developer="D-76", process="Small Tank, 68F (20C)", overline_minus=True),
    ]),
    lambda: bw_product("film/kodak/f32-TMAX.pdf", "T-Max 400 (Pre-2007 Formulation)", 400, 2002, [
        BwPanel("tmaxdeveloper", 15, (45, 55, 270, 285),
                [("11min", (259.12, 123.48)), ("7min", (259.12, 167.30))],
                developer="T-MAX Developer", process="Small Tank, 75F (24C)", overline_minus=True),
        BwPanel("tmaxrs", 15, (320, 55, 545, 285),
                [("12min", r"^12$"), ("10min", r"^10$"), ("8min", r"^8$"), ("6min", r"^6$")],
                developer="T-MAX RS Developer and Replenisher", process="Large Tank, 75F (24C)",
                overline_minus=True),
        BwPanel("d76", 15, (45, 295, 270, 520),
                [("12min", r"^12$"), ("10min", r"^10$"), ("8min", r"^8$"), ("6min", r"^6$")],
                developer="D-76", process="Small Tank, 68F (20C)", overline_minus=True, min_trace_points=4),
        BwPanel("duraflort", 15, (320, 295, 545, 515),
                [("4ft", r"^4$"), ("3ft", r"^3$"), ("2.2ft", r"^2\.2$")],
                developer="DURAFLO RT Developer Replenisher",
                process="KODAK VERSAMAT Film Processor, Model 5",
                curve_dimension="processing_speed", overline_minus=True),
    ]),
    # --- T-Max 400 (f4043_TMax_400-2016.pdf, page 7): 3 panels -----------
    lambda: bw_product("film/kodak/f4043_TMax_400-2016.pdf", "T-Max 400", 400, 2016, [
        BwPanel("d76", 7, (40, 40, 290, 260),
                [("11min", r"^11$"), ("8min", r"^8$"), ("6min", r"^6$")],
                developer="D-76", process="Small Tank, 20C (68F)"),
        BwPanel("tmaxdeveloper", 7, (335, 40, 570, 260),
                [("9min", r"^9$"), ("7min", r"^7$"), ("5min", r"^5$")],
                developer="T-MAX Developer", process="Small Tank, 24C (75F)"),
        BwPanel("tmaxrs", 7, (40, 285, 290, 510),
                [("9min", r"^9$"), ("7min", r"^7$"), ("5min", r"^5$")],
                developer="T-MAX RS Developer and Replenisher", process="Large Tank, 24C (75F)"),
    ]),
    # --- Tri-X 400/320 (f4017-2016.pdf, page 7): confirmed single-panel
    # each (35mm/120/sheets are 3 DIFFERENT panels on the page, not 3
    # developers of the same stock) ---------------------------------------
    lambda: bw_product("film/kodak/f4017-2016.pdf", "Tri-X 400 (35mm)", 400, 2016, [
        BwPanel("d76", 7, (31, 40, 290, 265),
                [("12min", r"^12$"), ("10min", r"^10$"), ("8min", r"^8$"), ("6min", r"^6$")],
                developer="D-76", overline_minus=True),
    ]),
    lambda: bw_product("film/kodak/f4017-2016.pdf", "Tri-X 400 (120-size)", 400, 2016, [
        BwPanel("d76", 7, (31, 305, 290, 530),
                [("12min", r"^12$"), ("10min", r"^10$"), ("8min", r"^8$"), ("6min", r"^6$")],
                developer="D-76", overline_minus=True),
    ]),
    lambda: bw_product("film/kodak/f4017-2016.pdf", "Tri-X 320 TXP (Sheets)", 320, 2016, [
        BwPanel("hc110dilb", 7, (335, 313, 570, 540),
                [("14min", r"^14$"), ("9min", r"^9$"), ("6min", r"^6$"), ("4min", r"^4$")],
                developer="HC-110 (Dil B)", overline_minus=True),
    ]),
    # --- T-Max 100 (f4016_TMax_100-2016.pdf, page 7): 3 stacked panels;
    # D-76 (top) confirmed genuinely blocked IN THIS FILE (legend is literal
    # "PL"/"Q" glyphs -- the actual rendered GLYPHS are corrupted, not just
    # the extractable text, confirmed by zooming in and looking at the
    # pixels -- so OCR can't recover it here either). RESOLVED 2026-07-06:
    # the user pointed out a DIFFERENT, older combined "T-MAX Films" sheet
    # (f4016-TMAX-2004.pdf, 30 pages covering T-Max 100 + T-Max 400
    # together, unlike the 2016 file's single-product 9 pages) has the
    # exact same D-76 chart on page 14 with fully readable, correct text/
    # digits -- confirmed via direct word-dump ("6","7.5","10" all present
    # as real standalone tokens). `BwPanel.pdf_stub_override` (new field)
    # lets this ONE panel source from that older file while T-MAX
    # Developer/RS stay on the newer 2016 file -- verify by re-checking
    # BLOCKED.md's history before assuming a "confirmed blocked" file has
    # no working alternate printing anywhere else in the corpus. -----------
    lambda: bw_product("film/kodak/f4016_TMax_100-2016.pdf", "T-Max 100", 100, 2016, [
        BwPanel("d76", 14, (75, 78, 285, 286),
                [("10min", r"^10$"), ("7.5min", r"^7\.5$"), ("6min", r"^6$")],
                developer="D-76", process="Small Tank; 20C (68F)", overline_minus=True,
                pdf_stub_override="film/kodak/f4016-TMAX-2004.pdf"),
        BwPanel("tmaxrs", 7, (340, 285, 610, 490),
                [("15min", r"^15$"), ("13min", r"^13$"), ("10.5min", r"^10\.5$"), ("8min", r"^8$")],
                developer="T-MAX RS Developer and Replenisher", overline_minus=True),
        BwPanel("tmaxdeveloper", 7, (340, 500, 610, 720),
                [("12min", r"^12$"), ("10min", r"^10$"), ("7min", r"^7$"), ("6min", r"^6$")],
                developer="T-MAX Developer", overline_minus=True),
    ]),
    # --- Tri-X Pan / Tri-X Pan Professional (f9-Tri-X_Pan.pdf): TX (p7,
    # 2 panels: D-76 + T-MAX Developer) and TXP (p9, 1 panel: HC-110) are
    # different products (different ISO/name), not different panels of one
    # product. split_on_x_reversal needed on both TX's T-MAX Developer panel
    # (9min/5min toe-convergence) and TXP's HC-110 panel (6.25min) -- see
    # digitizer_core.extract_traces_in_region's own docstring. -------------
    lambda: bw_product("film/kodak/f9-Tri-X_Pan.pdf", "Tri-X Pan (TX)", 400, 2001, [
        BwPanel("d76", 7, (31, 40, 290, 272),
                [("11min", r"^11$"), ("9min", r"^9$"), ("7min", r"^7$")],
                developer="D-76", process="Large tank, 68F (20C)", overline_minus=True, min_trace_points=20),
        BwPanel("tmaxdeveloper", 7, (335, 40, 570, 272),
                [("11min", r"^11$"), ("9min", r"^9$"), ("7min", r"^7$"), ("5min", r"^5$")],
                developer="T-MAX Developer", process="Small tank, 75F (24C)", overline_minus=True,
                min_trace_points=20, split_on_x_reversal=True),
    ]),
    lambda: bw_product("film/kodak/f9-Tri-X_Pan.pdf", "Tri-X Pan Professional (TXP)", 320, 2001, [
        BwPanel("hc110dilb", 9, (195, 90, 570, 300),
                [("9min", r"^9$"), ("6.25min", r"^6$"), ("3.5min", r"^3$")],
                developer="HC-110 (Dil B)", process="Large tank, 68F (20C)", overline_minus=True,
                split_on_x_reversal=True),
    ]),
    # --- Plus-X 125 (f4018-125PX-2007.pdf, page 6): 2 panels --------------
    lambda: bw_product("film/kodak/f4018-125PX-2007.pdf", "Plus-X 125", 125, 2007, [
        BwPanel("d76", 6, (323, 55, 570, 290),
                [("11min", r"^11$"), ("7min", r"^7$"), ("5min", r"^5$")],
                developer="D-76", process="Small Tank, 20C (68F)", overline_minus=True,
                x_tick_regex=r"-?\d\.[05]"),
        BwPanel("tmaxdeveloper", 6, (323, 328, 570, 535),
                [("11min", r"^11$"), ("7min", r"^7$"), ("6min", r"^6$")],
                developer="T-MAX Developer", process="Small Tank, 20C (68F)", overline_minus=True,
                x_tick_regex=r"-?\d\.[05]"),
    ]),
    lambda: bw_product("film/kodak/f7-Verichrome.pdf", "Verichrome Pan", 125, 1996, [
        BwPanel("d76", 2, (304, 38, 554, 254),
                [("15min", r"^15$"), ("9min", r"^9$"), ("7min", r"^7$")],
                developer="D-76", overline_minus=True),
        BwPanel("hc110dilb", 2, (304, 265, 570, 480),
                [("12min", r"^12$"), ("8min", r"^8$"), ("5min", r"^5$")],
                developer="HC-110 (Dil B)", overline_minus=True, split_on_x_reversal=True),
    ]),
    lambda: bw_product("film/kodak/f10-Ektapan.pdf", "Ektapan", 100, 1997, [
        BwPanel("hc110dilb", 2, (304, 150, 554, 360),
                [("12min", r"^12$"), ("8min", r"^8$"), ("7min", r"^7$"), ("5min", r"^5$")],
                developer="HC-110 (Dil B)", process="Large Tank; 68F (20C)", overline_minus=True),
    ]),
    lambda: bw_product("film/kodak/f16-Commercial.pdf", "Commercial", 6, 1998, [
        BwPanel("dk50", 2, (40, 55, 269, 260),
                [("density", r"^Exposure:$")],
                developer="DK-50", process="Tungsten, 10 seconds", min_trace_points=40),
        BwPanel("hc110dilb", 2, (304, 46, 561, 254),
                [("12min", r"^12$"), ("8min", r"^8$"), ("5min", r"^5$"), ("3min", r"^3$"), ("2min", r"^2$")],
                developer="HC-110 (Dil B)"),
    ]),
    # NOTE: this sheet's x-axis is "REFLECTION DENSITY-ORIGINAL COPY", not
    # log exposure (Copy Film's job is duplicating a reflection original, not
    # responding to scene exposure) -- the digitized x values are still this
    # film's own real transfer characteristic, just the generic
    # "log_exposure_lux_seconds" x_label baked into bw_product doesn't
    # literally describe this one file's axis.
    lambda: bw_product("film/kodak/f17-Copy.pdf", "Copy Film", 6, 1998, [
        BwPanel("hc110dile", 2, (46, 92, 269, 345),
                [("8min", r"^8$"), ("6.5min", r"^6$"), ("5min", r"^5$"), ("4min", r"^4$")],
                developer="HC-110 (Dil E)", monotonic="decreasing"),
    ]),
    lambda: bw_product("film/kodak/f13-HIE.pdf", "HIE High-Speed Infrared", 400, 2000, [
        BwPanel("mixed", 5, (31, 131, 269, 400),
                [("D-19", r"^D-19$"), ("D-76", r"^D-76$"), ("HC-110", r"^HC-110$")],
                developer="mixed (see curve names)", overline_minus=True, curve_dimension="developer"),
    ]),
    # NOTE: same page's "HIE and HSI" header confirms this is a genuinely
    # DIFFERENT sibling product (HSI, likely the sheet-film format vs HIE's
    # roll format), not another panel of the same product -- own product
    # entry, not a BwPanel of the one above.
    lambda: bw_product("film/kodak/f13-HIE.pdf", "HSI High-Speed Infrared (Sheets)", 400, 2000, [
        BwPanel("mixed", 5, (335, 60, 570, 280),
                [("D-19", r"^D-19$"), ("D-76", r"^D-76$"), ("HC-110", r"^HC-110$")],
                developer="mixed (see curve names)", overline_minus=True, curve_dimension="developer"),
    ]),
    lambda: bw_product("film/kodak/f11-Duplicating_SO-132.pdf", "B/W Duplicating SO-132", 5, 1999, [
        BwPanel("dk50viaversamat", 2, (46, 108, 292, 346),
                [("9fpm", r"^9$"), ("6fpm", r"^6$")],
                developer="DK-50 via VERSAMAT", monotonic="decreasing", curve_dimension="processing_speed"),
        BwPanel("d76", 2, (335, 40, 570, 235),
                [("15min", r"^15$"), ("12min", r"^12$"), ("9min", r"^9$")],
                developer="D-76 (1:1)", process="Rotary tube, 68F (20C)", monotonic="decreasing"),
        BwPanel("dektol", 2, (335, 250, 570, 450),
                [("density", r"^Exposure:$")],
                developer="DEKTOL (1:1)", process="Tray, 68F (20C)", monotonic="decreasing", min_trace_points=40),
        BwPanel("xtol", 2, (335, 465, 570, 665),
                [("density", r"^Exposure:$")],
                developer="XTOL (1:2)", process="Small tank, 68F (20C)", monotonic="decreasing", min_trace_points=40),
        BwPanel("dk50", 2, (40, 340, 300, 540),
                [("6min", r"^6$"), ("4min", r"^4$")],
                developer="DK-50", process="Small tank, 68F (20C)", monotonic="decreasing"),
    ]),
    lambda: bw_product("film/kodak/F4001-P3200TMZ-2018.pdf", "T-Max P3200", 1000, 2018, [
        BwPanel("d76", 7, (31, 40, 290, 260),
                [("10min", r"^10$"), ("7.5min", r"^7\.5$"), ("6min", r"^6$")],
                developer="D-76", overline_minus=True),
        BwPanel("tmaxdeveloper", 7, (335, 35, 570, 250),
                [("12min", r"^12$"), ("10min", r"^10$"), ("7min", r"^7$"), ("6min", r"^6$")],
                developer="T-MAX Developer", overline_minus=True),
        BwPanel("tmaxrs", 7, (40, 280, 290, 500),
                [("15min", r"^15$"), ("13min", r"^13$"), ("10.5min", r"^10\.5$"), ("8min", r"^8$")],
                developer="T-MAX RS Developer and Replenisher", overline_minus=True),
    ]),
    lambda: bw_product("film/kodak/f12-Ektagraphic_HC.pdf", "Ektagraphic HC Slide Film", 8, 1998, [
        BwPanel("kodalithsuperrt", 2, (335, 160, 570, 368),
                [("3.25min", r"^3$"), ("2.75min", r"^2$"), ("2.25min", r"^2$")],
                developer="KODALITH Super RT Developer", overline_minus=True),
        BwPanel("d11", 2, (340, 390, 570, 590),
                [("3min", r"^3$"), ("2.5min", r"^1/2$"), ("2min", r"^2$")],
                developer="D-11"),
    ]),
    # --- Plus-X Pan / Plus-X Pan Professional (f8-Plus-X_Pan.pdf): confirmed
    # single-panel each (page 7 / page 9 are different products) ----------
    lambda: bw_product("film/kodak/f8-Plus-X_Pan.pdf", "Plus-X Pan", 125, 1999, [
        BwPanel("hc110dilb", 7, (31, 55, 290, 282),
                [("16min", r"^16$"), ("12min", r"^12$"), ("8min", r"^8$"), ("5min", r"^5$")],
                developer="HC-110 (Dil B)", overline_minus=True),
        BwPanel("tmaxdeveloper", 7, (330, 55, 570, 290),
                [("11min", r"^11$"), ("9min", r"^9$"), ("7min", r"^7$"), ("5min", r"^5$")],
                developer="T-MAX Developer", overline_minus=True, split_on_x_reversal=True),
    ]),
    lambda: bw_product("film/kodak/f8-Plus-X_Pan.pdf", "Plus-X Pan Professional", 125, 1999, [
        BwPanel("hc110dilb", 9, (31, 63, 290, 290),
                [("16min", r"^16$"), ("12min", r"^12$"), ("8min", r"^8$"), ("5min", r"^5$")],
                developer="HC-110 (Dil B)", overline_minus=True),
    ]),
]


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
