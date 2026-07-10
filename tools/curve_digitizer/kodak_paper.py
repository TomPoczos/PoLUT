"""
Digitizes Kodak print-paper datasheets (paper/kodak/*.pdf) into
consolidated-data/paper/kodak/<paper-for>/.

Usage: uv run kodak_paper.py
"""

from dataclasses import dataclass
from pathlib import Path

from digitizer_core import ChartSpec, CurveSpec, locate_panel_bboxes
from kodak_common import (
    characteristic_chart, overline_negative_calib, spectral_dye_density_chart,
    PAPER_DYE_DENSITY_LABELS, PAPER_BW_DYE_DENSITY_LABELS, PAPER_DYE_DENSITY_LABELS_ABBREV,
)
from product import PaperProductSpec, digitize_paper, run_products_parallel

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")
DYE_DENSITY_TITLE = r"^Spectral-Dye-Density$"
MIN_DYE_DENSITY_PANEL_HEIGHT = 50


def negative_paper_product(pdf_stub, page_index, paper_name, year, char_box=None, x_axis_calib_override=None,
                            monotonic="increasing", paper_for="color-negative", cross_object_merge=False,
                            merge_strategy="proximity", min_trace_points=12, y_tick_regex=r"\d\.0",
                            strict_chain_merge=False, merge_tol_multiplier=6, x_tick_regex=r"-?\d\.0",
                            dye_density_box=None, skip_dye_density=False, dye_density_cross_object_merge=False,
                            dye_density_labels=PAPER_DYE_DENSITY_LABELS, dye_density_page_index=None,
                            dye_density_curves=None, dye_density_min_trace_points=12,
                            dye_density_merge_strategy="proximity",
                            dye_names_in_peak_x_order=("yellow", "magenta", "cyan")):
    """Single 'Characteristic Curves' panel, R/G/B inline labels (Strategy D),
    same template family as the still-photography film sheets. `char_box`
    overrides the auto-locate for pages where it needs pinning down.
    `x_axis_calib_override`: some sheets (like this one) draw every negative
    tick's minus sign as a vector overline except the rightmost (genuinely
    unsigned) one -- only one trustworthy point remains from text, not
    enough to fit a slope, so the (slope, intercept) has to be computed by
    hand from the ticks' real pixel positions + known-correct signed values
    and passed in directly. `monotonic`: some sheets print their log-exposure
    axis in decreasing left-to-right order (e.g. "3.0 2.0 1.0 0.0"), which
    flips whether density increases or decreases in the file's own
    calibrated data order even though the real paper physics doesn't change
    -- check with monotonic_direction=None first if unsure (see kodak_common
    module docstring / project memory for the general lesson). `cross_object_merge=True`
    for sheets (e.g. Portra/Supra Endura, e4021.pdf) that fragment each curve
    into many tiny separate drawing objects instead of one continuous path.
    `merge_strategy="sequential_band"` (with cross_object_merge=True and a
    lower min_trace_points, e.g. 4) for sheets where the fragmented curves
    ALSO converge tightly somewhere -- proximity-based merging fuses
    different curves there; sequential_band chains each x-band's fragments
    to the nearest-y running curve instead (see extract_traces_in_region)."""
    pdf_path = PDF_ROOT / pdf_stub
    if char_box is None:
        doc_boxes = locate_panel_bboxes(__import__("fitz").open(pdf_path)[page_index], [r"^Characteristic$"])
        char_box = doc_boxes[r"^Characteristic$"]
    charts = [characteristic_chart(pdf_stub, page_index, char_box, monotonic=monotonic, y_tick_regex=y_tick_regex,
                                    x_tick_regex=x_tick_regex)]
    charts[0].cross_object_merge = cross_object_merge
    charts[0].merge_strategy = merge_strategy
    charts[0].min_trace_points = min_trace_points
    charts[0].strict_chain_merge = strict_chain_merge
    charts[0].merge_tol_multiplier = merge_tol_multiplier
    if x_axis_calib_override is not None:
        charts[0].x_axis_calib_override = x_axis_calib_override
    if dye_density_box is None and dye_density_page_index is None and not skip_dye_density:
        try:
            dd_boxes = locate_panel_bboxes(__import__("fitz").open(pdf_path)[page_index],
                                            [r"^Characteristic$", DYE_DENSITY_TITLE])
        except RuntimeError:
            dd_boxes = {}
        dye_density_box = dd_boxes.get(DYE_DENSITY_TITLE)
    if not skip_dye_density and dye_density_box is not None:
        if dye_density_box[3] - dye_density_box[1] >= MIN_DYE_DENSITY_PANEL_HEIGHT:
            dd_page = dye_density_page_index if dye_density_page_index is not None else page_index
            dd_chart = spectral_dye_density_chart(pdf_stub, dd_page, dye_density_box,
                                                   labels=dye_density_labels,
                                                   cross_object_merge=dye_density_cross_object_merge,
                                                   min_trace_points=dye_density_min_trace_points,
                                                   merge_strategy=dye_density_merge_strategy,
                                                   dye_names_in_peak_x_order=dye_names_in_peak_x_order)
            if dye_density_curves is not None:
                # Bypasses the (name, regex) label-lookup path entirely -- some panels'
                # label-text rank order doesn't track curve height at the rank algorithm's
                # shared mean-label-x (e.g. e118.pdf: 3 well-separated peaks where the
                # "Magenta" label sits unusually low relative to its own peak, confirmed via
                # direct extract_traces_in_region + assign_traces_to_labels_exclusive dump --
                # yellow/magenta came back swapped, cyan fine). Caller passes real CurveSpec
                # objects with label_position_override pinned to y-values that encode the
                # CORRECT rank at a shared x, not necessarily the literal label text position
                # (same technique as kodak_mp_reversal.py's h17251 red_cyan/blue_yellow fix).
                dd_chart.curves = dye_density_curves
            charts.append(dd_chart)
    return PaperProductSpec(
        brand="kodak", paper_name=paper_name, paper_for=paper_for, year=year,
        source_pdf=pdf_stub, charts=charts,
        digitizer_notes="RA-4 chromogenic color-negative paper; single 'Characteristic Curves' "
                         "panel, curves ID'd by inline R/G/B labels (Strategy D, vector_position). "
                         "Spectral-Dye-Density (when present) via inline Yellow/Magenta/Cyan labels, "
                         "no 4th Visual-Neutral curve unlike reversal film's version of this panel.",
    )


@dataclass
class PaperPanel:
    """One 'Characteristic Curves' panel for a B&W paper -- one developer,
    several contrast-grade/filter-set curves. Papers with several published
    panels (e.g. Polymax II RC's 3 filter-set panels, all the SAME DEKTOL
    developer -- confirmed 2026-07-05, same gap as B&W film's multi-developer
    panels but the varying axis here is filter set, not developer) each get
    their own PaperPanel with real per-panel metadata, not folded into one
    chart or dropped."""
    chart_suffix: str
    page_index: int
    char_box: tuple
    curves: list  # [(curve_name, label_regex), ...]
    developer: str = "DEKTOL (1:2)"
    process: str = ""
    densitometry: str = ""
    exposure: str = ""
    monotonic: str = "increasing"
    overline_minus: bool = True
    y_tick_regex: str = r"\d\.0"
    min_trace_points: int = 12
    split_on_x_reversal: bool = False


def bw_paper_product(pdf_stub, paper_name, year, panels: list[PaperPanel], paper_for="black-and-white"):
    r"""Kodak black-and-white enlarging papers (the g-series: Polymax,
    Kodabromide, Ektalure, Azo, Portra B&W, Panalure, P-MAX Art,
    Polycontrast, etc.) -- a NEW paper_for="black-and-white" category, not
    seen in the color-paper (RA-4) sheets covered by negative_paper_product.
    Each 'Characteristic Curves' panel plots several contrast-grade/filter
    variants (White Light + numbered filters like #1/#3/#5+, or #-1/#1half/
    #3half) of the SAME paper on one chart -- structurally identical to
    bw_product's B&W-film "several curves for one developer" case, just for
    paper instead of film, and (unlike Ilford's Multigrade sheets) Kodak's
    own charts here DO print real extractable inline text labels, so
    Strategy D (vector_position) still applies directly. `panels`: list of
    PaperPanel, one per real panel found on the product's own source
    page(s) -- most papers publish only one, some (filter-set variants)
    publish several, each captured as its own chart rather than only the
    first found."""
    pdf_path = PDF_ROOT / pdf_stub
    charts = []
    for p in panels:
        chart = ChartSpec(
            pdf=pdf_stub, page_index=p.page_index, chart_id=f"characteristic_curve_{p.chart_suffix}",
            x_tick_regex=r"-?\d\.0", y_tick_regex=p.y_tick_regex,
            x_label="log_exposure_lux_seconds", y_label="density",
            curves=[CurveSpec(name, label_regex=regex) for name, regex in p.curves],
            film_id="_unused", extraction_method="vector_position",
            region_bbox=p.char_box, monotonic_direction=p.monotonic, min_trace_points=p.min_trace_points,
            split_on_x_reversal=p.split_on_x_reversal,
            metadata={"developer": p.developer, "process": p.process, "densitometry": p.densitometry,
                      "exposure": p.exposure, "curve_names": [n for n, _ in p.curves]},
        )
        if p.overline_minus:
            chart.x_axis_calib_override = overline_negative_calib(pdf_path, p.page_index, p.char_box)
        charts.append(chart)
    panel_notes = "; ".join(f"{p.chart_suffix} ({p.developer}: {[n for n,_ in p.curves]})" for p in panels)
    return PaperProductSpec(
        brand="kodak", paper_name=paper_name, paper_for=paper_for, year=year,
        source_pdf=pdf_stub, charts=charts,
        digitizer_notes=f"Black-and-white enlarging paper: every 'Characteristic Curves' panel "
                         f"found for this product is captured as its own chart (Strategy D, "
                         f"vector_position), curves ID'd by inline filter/grade labels -- {panel_notes}.",
    )


PRODUCTS = [
    lambda: negative_paper_product("paper/kodak/e140.pdf", 4, "Portra III", 2002,
                                    char_box=(60, 45, 290, 265),
                                    x_axis_calib_override=(0.016245884572187286, -4.404155464508592)),
    lambda: negative_paper_product("paper/kodak/e19.pdf", 4, "Ektacolor Edge 7", 1997),
    lambda: negative_paper_product("paper/kodak/e23.pdf", 4, "Ektacolor Royal VII", 1997),
    # dye_density_box given explicitly: locate_panel_bboxes' 2-title clustering (only
    # 'Characteristic' + 'Spectral-Dye-Density' as anchors on this page) returns a real box
    # for the title match but with a degenerate ~1.1pt height (330,44.9,604,46.0) --
    # MIN_DYE_DENSITY_PANEL_HEIGHT correctly rejected it, but silently, so the panel (which
    # genuinely exists, same page, real Yellow/Magenta/Cyan inline labels) was never chased
    # down until now. Manually-derived box from the real title/axis word positions instead.
    lambda: negative_paper_product("paper/kodak/e141.pdf", 5, "Supra III", 2001,
                                    char_box=(46, 55, 270, 275), monotonic="decreasing",
                                    dye_density_box=(325, 25, 535, 265)),
    lambda: negative_paper_product("paper/kodak/e142.pdf", 5, "Ultra III", 2001,
                                    char_box=(46, 55, 270, 275), monotonic="decreasing"),
    lambda: negative_paper_product("paper/kodak/e1766.pdf", 4, "Ektachrome Radiance III Paper", 1999,
                                    char_box=(46, 55, 270, 275), monotonic="decreasing", paper_for="direct-positive"),
    lambda: negative_paper_product("paper/kodak/e2410.pdf", 2, "Ektachrome Radiance III Copy Paper", 1999,
                                    char_box=(340, 55, 555, 275), monotonic="decreasing", paper_for="direct-positive",
                                    dye_density_box=(320, 296, 570, 526)),
    lambda: negative_paper_product("paper/kodak/e4020.pdf", 6, "Ultra Endura", 2008),
    lambda: negative_paper_product("paper/kodak/e4070.pdf", 3, "Endura Premier", 2011,
                                    # Spectral-Dye-Density panel is on the FOLLOWING page (4).
                                    dye_density_page_index=4, dye_density_box=(42, 65, 240, 295)),
    lambda: negative_paper_product("paper/kodak/e4021.pdf", 6, "Portra Endura", 2003,
                                    char_box=(340, 40, 570, 290), monotonic="decreasing",
                                    cross_object_merge=True, merge_strategy="sequential_band", min_trace_points=4,
                                    # Spectral-Dye-Density panel is on the FOLLOWING page (7), shared by
                                    # both Portra Endura and Supra Endura (this sheet's own title covers
                                    # both papers) -- same precedent as Portra 160NC/160VC sharing one
                                    # Spectral-Sensitivity chart in kodak_still.py. box's right edge
                                    # matters here: a first attempt at x=240 (~668nm) silently cut off
                                    # the Cyan curve entirely (its trace extends closer to the real
                                    # 700nm tick than Yellow/Magenta's do) -- confirmed via direct
                                    # extract_traces_in_region dump showing only 2 of 3 real traces
                                    # survived at that width; widened to the real tick range instead.
                                    dye_density_page_index=7, dye_density_box=(46, 25, 270, 325)),
    lambda: negative_paper_product("paper/kodak/e4021.pdf", 6, "Supra Endura", 2003,
                                    char_box=(340, 290, 570, 545), monotonic="decreasing",
                                    cross_object_merge=True, merge_strategy="sequential_band", min_trace_points=4,
                                    dye_density_page_index=7, dye_density_box=(46, 25, 270, 325)),
    lambda: bw_paper_product("paper/kodak/g26.pdf", "Polymax II RC", 2005, [
        PaperPanel("filterset1", 6, (46, 85, 269, 320),
                   [("white_light", r"^White$"), ("grade1", r"^#1$"),
                    ("grade3", r"^#3$"), ("grade5plus", r"^#5\+$")]),
        PaperPanel("filterset2", 6, (40, 340, 300, 556),
                   [("grade0", r"^#0$"), ("grade2", r"^#2$"), ("grade4", r"^#4$")]),
        PaperPanel("filterset3", 6, (340, 340, 570, 556),
                   [("nofilter", r"^White$"), ("grademinus1", r"^#-1$"),
                    ("grade1half", r"^#11$"), ("grade3half", r"^#3$")]),
    ]),
    lambda: bw_paper_product("paper/kodak/g7.pdf", "Polymax Fiber Paper", 1998, [
        PaperPanel("filterset1", 4, (40, 40, 290, 250),
                   [("grade1", r"^#1$"), ("grade3", r"^#3$"), ("grade5", r"^#5$")],
                   overline_minus=False),
        PaperPanel("filterset2", 4, (40, 310, 300, 520),
                   [("grade0", r"^#0$"), ("grade2", r"^#2$"), ("grade4", r"^#4$")],
                   overline_minus=False),
        PaperPanel("filterset3", 4, (330, 40, 570, 250),
                   [("nofilter", r"^No$"), ("grademinus1", r"^#-1$")],
                   overline_minus=False),
    ]),
    lambda: bw_paper_product("paper/kodak/g8.pdf", "Kodabromide Paper", 1999, [
        PaperPanel("main", 2, (40, 40, 290, 260),
                   [("gradeF1", r"^F-1$"), ("gradeF2", r"^F-2$"), ("gradeF3", r"^F-3$"),
                    ("gradeF4", r"^F-4$"), ("gradeF5", r"^F-5$")]),
    ]),
    lambda: bw_paper_product("paper/kodak/g9.pdf", "Ektalure Paper", 1999, [
        PaperPanel("selectolsoft", 2, (40, 60, 290, 290),
                   [("180sec", r"^180$"), ("120sec", r"^120$"), ("90sec", r"^90$")],
                   developer="SELECTOL-SOFT (1:1)"),
        PaperPanel("ektonal", 2, (40, 280, 300, 520),
                   [("180sec", r"^180$"), ("120sec", r"^120$"), ("90sec", r"^90$")],
                   developer="EKTONOL Developer (1:1)"),
        PaperPanel("ektaflo", 2, (335, 40, 570, 252),
                   [("180sec", r"^180$"), ("120sec", r"^120$"), ("90sec", r"^90$")],
                   developer="EKTAFLO Developer, Type 2"),
    ]),
    lambda: bw_paper_product("paper/kodak/g10.pdf", "Azo Paper Grade 2", 2005, [
        PaperPanel("main", 4, (40, 40, 290, 280), [("grade2", r"^Grade$")],
                   developer="Kodak Professional Dektol", overline_minus=False),
    ]),
    lambda: bw_paper_product("paper/kodak/g10.pdf", "Azo Paper Grade 3", 2005, [
        PaperPanel("main", 4, (335, 40, 570, 280), [("grade3", r"^Grade$")],
                   developer="Kodak Professional Dektol", overline_minus=False),
    ]),
    lambda: bw_paper_product("paper/kodak/g24.pdf", "Polymax Fine-Art Paper", 2005, [
        PaperPanel("filterset1", 4, (40, 85, 290, 310),
                   [("grade1", r"^#1$"), ("grade3", r"^#3$"), ("grade5", r"^#5$")],
                   overline_minus=False),
        PaperPanel("filterset2", 4, (40, 340, 300, 545),
                   [("grade0", r"^#0$"), ("grade2", r"^#2$"), ("grade4", r"^#4$")],
                   overline_minus=False),
        PaperPanel("filterset3", 4, (340, 100, 570, 310),
                   [("nofilter", r"^No$"), ("grademinus1", r"^-1$")],
                   overline_minus=False),
    ]),
    lambda: bw_paper_product("paper/kodak/g27.pdf", "Panalure Select RC Paper", 2005, [
        PaperPanel("main", 4, (40, 40, 300, 320), [("density", r"^Exposure:$")], overline_minus=False),
        # NOTE: sanity check flags green_filter/blue_filter as "identical
        # bounding boxes" -- verified false positive (real point sequences
        # differ; the panel's own visual shows G/B genuinely nearly
        # overlapping, same pattern as Kodabrome II RC's gradeF1/gradeF3).
        PaperPanel("rgbresponse", 4, (335, 40, 570, 280),
                   [("red_filter", r"^R$"), ("green_filter", r"^G$"), ("blue_filter", r"^B$")],
                   overline_minus=False),
    ]),
    lambda: bw_paper_product("paper/kodak/g28.pdf", "P-MAX Art RC Paper Grade 2", 2004, [
        PaperPanel("main", 4, (40, 40, 290, 280), [("grade2", r"^Grade$")], overline_minus=False),
    ]),
    lambda: bw_paper_product("paper/kodak/g28.pdf", "P-MAX Art RC Paper Grade 3", 2004, [
        PaperPanel("main", 4, (335, 40, 570, 280), [("grade3", r"^Grade$")], overline_minus=False),
    ]),
    lambda: bw_paper_product("paper/kodak/g2467.pdf", "Digital Black and White Paper", 2005, [
        PaperPanel("main", 2, (46, 140, 290, 350),
                   [("red_laser", r"^R$"), ("green_laser", r"^G$"), ("blue_laser", r"^B$")],
                   overline_minus=False),
    ]),
    lambda: negative_paper_product("paper/kodak/g4006.pdf", 4, "Portra Black and White Paper", 2005,
                                    char_box=(40, 40, 290, 290), paper_for="black-and-white",
                                    x_axis_calib_override=(0.021730825021603083, -4.914455601905991),
                                    dye_density_labels=PAPER_BW_DYE_DENSITY_LABELS),
    lambda: negative_paper_product("paper/kodak/g4019.pdf", 4, "Portra Sepia Black and White Paper", 2005,
                                    char_box=(40, 40, 290, 290), paper_for="black-and-white",
                                    x_axis_calib_override=(0.01632254375097143, -3.562779066835708),
                                    dye_density_labels=PAPER_BW_DYE_DENSITY_LABELS),
    lambda: bw_paper_product("paper/kodak/g4037.pdf", "Polycontrast IV RC Paper (Dektol)", 2005, [
        PaperPanel("dektol", 6, (340, 90, 570, 300),
                   [("white_light", r"^White$"), ("filter1", r"^1$"),
                    ("filter3", r"^3$"), ("filter5plus", r"^5\+$")],
                   overline_minus=False),
        PaperPanel("polymaxrt", 6, (335, 340, 570, 556),
                   [("white_light", r"^White$"), ("filter1", r"^1$"),
                    ("filter3", r"^3$"), ("filter5plus", r"^5\+$")],
                   developer="POLYMAX RT Developer", overline_minus=False),
    ]),
    lambda: negative_paper_product("paper/kodak/e1767.pdf", 4, "Ektachrome Radiance III Select Material", 1999,
                                    char_box=(46, 55, 270, 275), monotonic="decreasing", paper_for="direct-positive"),
    lambda: negative_paper_product("paper/kodak/e2411.pdf", 3, "Ektachrome Radiance III HC Copy Paper", 1999,
                                    char_box=(46, 55, 270, 275), monotonic="decreasing", paper_for="direct-positive"),
    lambda: negative_paper_product("paper/kodak/e2412b.pdf", 3, "Ektachrome Radiance III Clear Display Material", 1999,
                                    char_box=(46, 55, 270, 275), monotonic="decreasing", paper_for="direct-positive"),
    lambda: negative_paper_product("paper/kodak/e2413.pdf", 3, "Ektachrome Radiance III Translucent Display Material",
                                    1999, char_box=(46, 55, 270, 300), monotonic="decreasing",
                                    paper_for="direct-positive", y_tick_regex=r"\d\.\d"),
    lambda: negative_paper_product("paper/kodak/e2412a.pdf", 2, "Ektachrome Radiance III Overhead Material", 1999,
                                    char_box=(46, 470, 270, 700), monotonic="decreasing", paper_for="direct-positive"),
    lambda: negative_paper_product("paper/kodak/e118.pdf", 2, "Digital Paper Type 2976", 1996,
                                    char_box=(46, 55, 290, 275), monotonic="decreasing",
                                    # Same degenerate-auto-locate-box gap as Supra III above.
                                    dye_density_box=(325, 25, 545, 260),
                                    # Rank-based label matching mismatches yellow/magenta here (see
                                    # dye_density_curves' own docstring in negative_paper_product) --
                                    # pinned to y-values that encode each curve's real rank at the
                                    # traces' shared mean-x instead of the literal (misleading) label
                                    # text position. Verified via QA overlay: all 3 track their real
                                    # labeled peak (Yellow ~440nm, Magenta ~550nm, Cyan ~650nm).
                                    dye_density_curves=[
                                        CurveSpec("magenta", label_position_override=(466, 100)),
                                        CurveSpec("cyan", label_position_override=(466, 150)),
                                        CurveSpec("yellow", label_position_override=(466, 200)),
                                    ]),
    lambda: negative_paper_product("paper/kodak/e2446.pdf", 3, "Digital III Color Paper", 2003,
                                    dye_density_box=(36, 344, 270, 570),
                                    dye_density_labels=PAPER_DYE_DENSITY_LABELS_ABBREV,
                                    char_box=(46, 102, 290, 330),
                                    x_axis_calib_override=(0.027872462640879662, -5.931173199937908)),
    lambda: negative_paper_product("paper/kodak/e4002.pdf", 2, "Pro Image II Paper", 2008,
                                    char_box=(340, 370, 570, 600),
                                    # Spectral-Dye-Density panel is on the FOLLOWING page (3),
                                    # stacked below a Spectral-Sensitivity panel.
                                    dye_density_page_index=3, dye_density_box=(40, 312, 250, 555)),
    lambda: negative_paper_product("paper/kodak/e4005.pdf", 4, "Color Metallic Paper", 2003,
                                    char_box=(340, 166, 570, 400),
                                    x_axis_calib_override=(0.021732714848813197, -10.878625431422732),
                                    dye_density_box=(320, 418, 570, 660)),
    lambda: negative_paper_product("paper/kodak/e4014.pdf", 3, "Duraflex Plus Digital Display Material", 2004,
                                    char_box=(46, 55, 290, 290),
                                    x_axis_calib_override=(0.021748513270362452, -4.779942413538983)),
    lambda: negative_paper_product("paper/kodak/e4028.pdf", 6, "Endura Metallic Paper", 2008,
                                    char_box=(46, 60, 290, 290),
                                    x_axis_calib_override=(0.021739181644863558, -5.036866849088614)),
    lambda: negative_paper_product("paper/kodak/e4044.pdf", 6, "Ultra Endura High Definition Paper", 2010,
                                    char_box=(46, 60, 290, 290)),
    # skip_dye_density=True: this sheet's panel titled "Spectral-Dye-Density Curves" is a
    # genuine content/title mismatch in Kodak's own PDF -- confirmed by rendering: the chart
    # under that title is actually the Spectral-Sensitivity chart (Yellow-/Magenta-/Cyan-Forming
    # Layer, LOG SENSITIVITY axis), not a real dye-density panel. No dye-density data exists on
    # this page to extract.
    lambda: negative_paper_product("paper/kodak/e4071.pdf", 3, "Endura Premier Metallic Paper", 2011,
                                    char_box=(335, 60, 570, 290), skip_dye_density=True),
    # dye_density_box: this ONE panel is shared by both Transparency Optical and Clear
    # Optical (same base material's dye set, confirmed by rendering -- same precedent as
    # Portra 160NC/160VC's shared Spectral-Sensitivity chart) -- attached to both products.
    lambda: negative_paper_product("paper/kodak/e4030.pdf", 4, "Endura Transparency Optical Display Material", 2002,
                                    char_box=(46, 75, 290, 300), cross_object_merge=True, min_trace_points=8,
                                    strict_chain_merge=True, x_tick_regex=r"-?\d\.00",
                                    dye_density_box=(335, 82, 570, 300)),
    lambda: negative_paper_product("paper/kodak/e4030.pdf", 4, "Endura Clear Optical Display Material", 2002,
                                    char_box=(46, 390, 290, 545), cross_object_merge=True, min_trace_points=8,
                                    strict_chain_merge=True,
                                    dye_density_box=(335, 82, 570, 300)),
    # SUSPECTED SOURCE-DOCUMENT ERROR, transcribed as-printed rather than silently
    # "corrected": this sheet's own Spectral-Dye-Density panel prints "Cyan" on the
    # ~550nm (green-absorbing) peak and "Magenta" on the ~630nm (red-absorbing) peak --
    # backwards from every other Kodak sheet in this corpus (and backwards from the
    # physically-expected convention: magenta dye absorbs green ~550nm, cyan dye
    # absorbs red ~630nm). Confirmed via direct text-position dump, not a rendering
    # artifact. The "magenta"/"cyan" keys below therefore hold the PRINTED labels,
    # which appear to be swapped relative to the curves' real physical identity --
    # flag before using this file's dye_density data downstream. dye_names_in_peak_x_order
    # preserves this printed swap rather than letting curves_by_peak_x's default physical
    # ordering silently "correct" it (2026-07-10: caught before shipping -- see that
    # function's own docstring for the general lesson).
    lambda: negative_paper_product("paper/kodak/e4034.pdf", 4, "Endura Day/Night Display Material", 2004,
                                    char_box=(340, 55, 570, 275), cross_object_merge=True, min_trace_points=8,
                                    strict_chain_merge=True,
                                    dye_density_box=(320, 305, 570, 545),
                                    dye_names_in_peak_x_order=("yellow", "cyan", "magenta")),
    lambda: negative_paper_product("paper/kodak/e4047.pdf", 4, "Endura Metallic VC Digital Paper", 2009,
                                    char_box=(46, 60, 290, 290), cross_object_merge=True, min_trace_points=8,
                                    strict_chain_merge=True),
    lambda: negative_paper_product("paper/kodak/e143.pdf", 3, "Duraclear Display Material", 1999,
                                    char_box=(40, 60, 290, 297)),
    lambda: negative_paper_product("paper/kodak/e143.pdf", 4, "Duratrans Display Material", 1999,
                                    char_box=(40, 60, 290, 297)),
    lambda: negative_paper_product("paper/kodak/e143.pdf", 5, "Duraflex Print Material", 1999,
                                    char_box=(40, 60, 290, 297)),
    # NOTE: sanity check flags gradeF1/gradeF3 as "identical bounding boxes"
    # -- verified false positive (their actual point sequences differ; both
    # legitimately converge to a very similar Dmax, common across grades on
    # one paper, which is what the box check is catching, not a mislabel).
    lambda: bw_paper_product("paper/kodak/g16.pdf", "Kodabrome II RC Paper", 2005, [
        PaperPanel("main", 3, (340, 50, 570, 300),
                   [("gradeF1", r"^F-1$"), ("gradeF2", r"^F-2$"),
                    ("gradeF3", r"^F-3$"), ("gradeF4", r"^F-4$")],
                   overline_minus=False, y_tick_regex=r"^\d$", min_trace_points=20),
        PaperPanel("main2", 3, (335, 300, 570, 520),
                   [("gradeN1", r"^N-1$"), ("gradeN2", r"^N-2$"),
                    ("gradeN3", r"^N-3$"), ("gradeN4", r"^N-4$")],
                   overline_minus=False, y_tick_regex=r"^\d$", min_trace_points=20),
    ]),
    lambda: bw_paper_product("paper/kodak/g22.pdf", "Ektamax RA Professional Paper (M)", 1997, [
        PaperPanel("main", 2, (40, 40, 300, 290), [("density", r"^Exposure:$")], overline_minus=False),
    ], paper_for="color-negative"),
    lambda: negative_paper_product("paper/kodak/e4031.pdf", 4, "Endura Transparency Digital Display Material", 2006,
                                    char_box=(40, 55, 290, 290), x_tick_regex=r"-?\d\.00",
                                    cross_object_merge=True, strict_chain_merge=True, min_trace_points=8,
                                    dye_density_box=(335, 82, 570, 300)),
    lambda: negative_paper_product("paper/kodak/e4031.pdf", 4, "Endura Clear Digital Display Material", 2006,
                                    char_box=(40, 313, 290, 545), x_tick_regex=r"-?\d\.0",
                                    cross_object_merge=True, strict_chain_merge=True, min_trace_points=8,
                                    dye_density_box=(335, 82, 570, 300)),
    # NOTE: e4038's Transparency panel duplicates e4031's Transparency
    # Digital panel exactly (same figure code F002_0517AC in both source
    # PDFs) -- not re-added here. Its Clear panel uses a DIFFERENT figure
    # (F009_0529AC vs e4031's F009_0518AC) -- a real, distinct product,
    # added below. That panel splits each of its 3 curves into ~10
    # sequential fragments (like Portra Endura); sequential_band gets all 3
    # monotonic and 0-violation, though red/green's toe region is less
    # complete than blue's -- tried several min_trace_points values without
    # a clearly better result, kept the cleanest one found.
    lambda: negative_paper_product("paper/kodak/e4038.pdf", 4, "Endura Clear Display Material", 2006,
                                    char_box=(40, 313, 290, 540), x_tick_regex=r"-?\d\.0",
                                    cross_object_merge=True, merge_strategy="sequential_band", min_trace_points=8,
                                    dye_density_box=(335, 82, 570, 300)),
    lambda: negative_paper_product("paper/kodak/E4042.pdf", 4, "Supra Endura VC Digital Paper", 2008,
                                    char_box=(46, 60, 290, 290),
                                    dye_density_box=(330, 60, 570, 278)),
]


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
