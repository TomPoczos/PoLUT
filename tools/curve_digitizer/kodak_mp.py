"""
Digitizes Kodak motion-picture film datasheets (motionpicture/kodak/*.pdf)
into consolidated-data/film/motion-picture/{negative,reversal}/kodak/.

Different template from the still-photography sheets (kodak_still.py):
the "characteristic curve" equivalent is titled "Sensitometric Curves" and
its x-axis is CAMERA STOPS (small integers, -8..8), not LOG EXPOSURE
directly -- Strategy D (vector_position) still applies, just with an
integer tick regex instead of the "N.0" one still-photography sheets use.

Usage: uv run kodak_mp.py
"""

import re
from pathlib import Path

import fitz
import numpy as np

from digitizer_core import ChartSpec, CurveSpec, curves_by_peak_x, locate_panel_bboxes, mp_dye_density_curves
from kodak_common import (
    COLOR_NEG_CHAR_LABELS, COLOR_NEG_SPECTRAL_LABELS, get_panel_bboxes,
    MP_DYE_DENSITY_LABELS, MP_DYE_DENSITY_LABELS_2CURVE, PAPER_DYE_DENSITY_LABELS,
)
from product import ProductSpec, digitize_product, run_products_parallel

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")
PANEL_TITLES = [r"^Sensitometric$", r"^Spectral$", r"^Granularity$"]


def _unsigned_camera_stops_calib(pdf_stub, page_index, tick_bbox):
    """Some older (Vision2-era, ~2005-2006) sheets print the Sensitometric
    Curves panel's negative camera-stops ticks WITHOUT a minus sign at all
    (e.g. "10.0 8.0 6.0 4.0 2.0 0.0 2.0 4.0 6.0" -- the same unsigned value
    literally repeated on both sides of "0.0"), unlike the bare-signed-
    integer ticks ("-8 -7 ... 0 ... 8") every other sheet in this file uses.
    A plain text-based fit can't disambiguate two ticks reading the same
    value at two different pixel positions. Finds the "0.0" tick's own
    pixel position and negates every tick to its left; pass the result as
    `x_axis_calib_override`, bypassing fit_axis's text-based reading
    entirely for this axis (same escape-hatch pattern as
    kodak_common.overline_negative_calib, for a different root cause)."""
    doc = fitz.open(PDF_ROOT / pdf_stub)
    page = doc[page_index]
    words = page.get_text("words")
    doc.close()
    cands = []
    for x0, y0, x1, y1, text, *_ in words:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if tick_bbox[0] <= cx <= tick_bbox[2] and tick_bbox[1] <= cy <= tick_bbox[3] and re.fullmatch(r"\d+\.0", text):
            cands.append((cx, float(text)))
    if len(cands) < 2:
        raise RuntimeError(f"only {len(cands)} unsigned camera-stop ticks found in {tick_bbox}")
    cands.sort()
    zero_x = min(x for x, v in cands if v == 0.0)
    corrected = [(-v if x < zero_x - 1 else v) for x, v in cands]
    pixels = [c[0] for c in cands]
    slope, intercept = np.polyfit(pixels, corrected, 1)
    return float(slope), float(intercept)


def vision_style_product(pdf_stub, page_index, product_name, iso, year, film_type="negative",
                          sens_box=None, spec_box=None, spec_page_index=None,
                          x_axis_calib_override=None, y_tick_bbox=None, min_trace_points=12,
                          x_tick_regex=r"-?\d$",
                          dye_density_box=None, dye_density_page_index=None,
                          dye_density_labels=MP_DYE_DENSITY_LABELS, dye_density_cross_object_merge=False,
                          dye_density_min_trace_points=12, dye_density_merge_strategy="proximity",
                          dye_names_in_peak_x_order=("yellow", "magenta", "cyan")):
    """`sens_box`/`spec_box`, if given, override the auto panel-locate --
    these sheets' panels aren't grid-aligned (each mini-chart's title sits at
    a different height depending on how much intro text precedes it on that
    particular page), which breaks locate_panel_bboxes' row/column clustering
    assumption. Falls back to auto-locate when not given.

    `spec_page_index` (defaults to `page_index`): real gotcha found
    2026-07-06 auditing this file -- on several sheets (5207/5219/5260, and
    the 5201/5205/5218 sheets added the same session) the Sensitometric
    Curves panel is on one page and the Spectral-Sensitivity panel is on
    the NEXT page, not the same one. The original single `page_index` for
    both charts silently produced a product with NO spectral_sensitivity
    chart at all for 3 already-shipped products (5207, 5219, 5260) --
    `spec_box or boxes.get(...)` fell through to `None` since `boxes` was
    never populated (both box args were given, skipping auto-locate) and no
    explicit spec_box had been passed either. Fixed by fitting both charts
    independently."""
    pdf_path = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom") / pdf_stub
    spec_page_index = spec_page_index if spec_page_index is not None else page_index
    boxes = {}
    if sens_box is None:
        boxes = get_panel_bboxes(pdf_path, page_index, PANEL_TITLES)
    sens_box = sens_box or boxes[r"^Sensitometric$"]
    charts = [
        ChartSpec(
            pdf=pdf_stub, page_index=page_index, chart_id="characteristic_curve",
            x_tick_regex=x_tick_regex, y_tick_regex=r"\d\.0",
            x_label="camera_stops", y_label="density_status_m",
            curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_CHAR_LABELS],
            film_id="_unused", extraction_method="vector_position",
            region_bbox=sens_box, monotonic_direction="increasing",
            x_axis_calib_override=x_axis_calib_override, y_tick_bbox=y_tick_bbox,
            min_trace_points=min_trace_points,
        ),
    ]
    if spec_box is None and spec_page_index == page_index:
        spec_box = boxes.get(r"^Spectral$")
    if spec_box:
        charts.append(ChartSpec(
            pdf=pdf_stub, page_index=spec_page_index, chart_id="spectral_sensitivity",
            x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
            x_label="wavelength_nm", y_label="log_sensitivity",
            curves=[CurveSpec(n, label_regex=r) for n, r in COLOR_NEG_SPECTRAL_LABELS],
            film_id="_unused", extraction_method="vector_position",
            region_bbox=spec_box,
        ))
    if dye_density_box:
        dd_page = dye_density_page_index if dye_density_page_index is not None else spec_page_index
        dd_pdf_path = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom") / pdf_stub
        dye_names = [n for n, _ in dye_density_labels]
        merge_kwargs = dict(cross_object_merge=dye_density_cross_object_merge,
                             min_trace_points=dye_density_min_trace_points,
                             merge_strategy=dye_density_merge_strategy)
        # The 3-dye portion of every one of this file's dye-density label sets (5-curve
        # MP_DYE_DENSITY_LABELS, 3-curve PAPER_DYE_DENSITY_LABELS) has the SAME
        # tied/near-tied-label-y rotated-identity bug fixed elsewhere in this project --
        # confirmed via automated peak-position cross-check (2026-07-10) on several Vision/EXR
        # sheets using MP_DYE_DENSITY_LABELS. Identified by shape instead of label-regex
        # matching; see mp_dye_density_curves/curves_by_peak_x's own docstrings
        # (digitizer_core.py). MP_DYE_DENSITY_LABELS_2CURVE (bare d_min/midscale_neutral, no
        # dye curves at all) is unaffected -- those 2 labels sit far apart in y and were never
        # part of this bug.
        if dye_names == ["d_min", "midscale_neutral", "yellow", "magenta", "cyan"]:
            dd_curves = mp_dye_density_curves(dd_pdf_path, dd_page, dye_density_box, **merge_kwargs,
                                               dye_names_in_peak_x_order=dye_names_in_peak_x_order)
        elif dye_names == ["yellow", "magenta", "cyan"]:
            dd_curves = curves_by_peak_x(dd_pdf_path, dd_page, dye_density_box,
                                          list(dye_names_in_peak_x_order), **merge_kwargs)
        else:
            dd_curves = [CurveSpec(n, label_regex=r) for n, r in dye_density_labels]
        charts.append(ChartSpec(
            pdf=pdf_stub, page_index=dd_page, chart_id="spectral_dye_density",
            x_tick_regex=r"\d{3}", y_tick_regex=r"-?\d\.\d{1,2}",
            x_label="wavelength_nm", y_label="diffuse_spectral_density",
            curves=dd_curves,
            film_id="_unused", extraction_method="vector_position",
            region_bbox=dye_density_box,
            cross_object_merge=dye_density_cross_object_merge,
            min_trace_points=dye_density_min_trace_points,
            merge_strategy=dye_density_merge_strategy,
        ))
    return ProductSpec(
        brand="kodak", product_name=product_name, application_area="motion-picture",
        film_type=film_type, medium="color", iso=iso, year=year,
        layer_order=["red_cyan_forming_layer", "green_magenta_forming_layer", "blue_yellow_forming_layer"],
        source_pdf=pdf_stub, charts=charts,
        digitizer_notes="'Sensitometric Curves'/'Spectral Sensitivity Curves' panel template "
                         "(VISION2/VISION3 tech data sheets); characteristic-curve x-axis is CAMERA "
                         "STOPS (small integers), not LOG EXPOSURE directly. Strategy D (vector_position), "
                         "curves ID'd by inline B/G/R labels.",
    )


PRODUCTS = [
    # Years corrected 2026-07-06 to match each sheet's OWN printed date
    # (checked directly, not assumed from memory of the film's release
    # year) -- e.g. 5213's sheet is dated May 2010, not 2007.
    lambda: vision_style_product("motionpicture/kodak/5213-Vision3-200T.pdf", 3, "Vision3 200T", 200, 2010,
                                  sens_box=(300, 60, 604, 340), spec_box=(300, 427, 604, 700),
                                  dye_density_page_index=4, dye_density_box=(49.4, 28.5, 300, 346.6)),
    lambda: vision_style_product("motionpicture/kodak/5207-Vision3-250D.pdf", 2, "Vision3 250D", 250, 2009,
                                  sens_box=(320, 50, 604, 309), spec_page_index=3, spec_box=(300, 25, 604, 245),
                                  dye_density_page_index=3, dye_density_box=(313.9, 316.6, 604, 564.9)),
    # SUSPECTED SOURCE-DOCUMENT ERROR, transcribed as-printed: this sheet's own Spectral Dye
    # Density panel prints "Cyan" on the ~450nm (blue-absorbing) peak and "Yellow" on the
    # ~650nm (red-absorbing) peak -- swapped from the physically-expected convention AND from
    # every sibling VISION3 sheet checked (confirmed via direct text-position dump). Same class
    # of anomaly as paper/kodak/e4034.pdf's Magenta/Cyan swap -- flag before using this file's
    # "yellow"/"cyan" keys downstream, they may be swapped. dye_names_in_peak_x_order below
    # preserves this printed swap rather than letting mp_dye_density_curves' default physical
    # ordering silently "correct" it (2026-07-10: mp_dye_density_curves' default ordering was
    # applied here briefly and DID silently correct it, contradicting this comment's own
    # "transcribed as-printed" intent -- caught before shipping, see that function's own
    # docstring for the general lesson).
    lambda: vision_style_product("motionpicture/kodak/5219-Vision3-500T-tech.pdf", 2, "Vision3 500T", 500, 2007,
                                  sens_box=(320, 50, 604, 309), spec_page_index=3, spec_box=(300, 25, 604, 245),
                                  dye_density_page_index=3, dye_density_box=(314.3, 316.6, 604, 567.0),
                                  # This panel's curves are heavily fragmented (10 raw path
                                  # objects for 5 real curves at default settings).
                                  dye_density_cross_object_merge=True, dye_density_min_trace_points=4,
                                  dye_density_merge_strategy="sequential_band",
                                  dye_names_in_peak_x_order=("cyan", "magenta", "yellow")),
    lambda: vision_style_product("motionpicture/kodak/5203-Vision3-50D-TI5203.pdf", 3, "Vision3 50D", 50, 2011,
                                  sens_box=(300, 60, 604, 340), spec_box=(300, 427, 604, 700),
                                  dye_density_page_index=4, dye_density_box=(52.9, 28.5, 300, 347.6)),
    lambda: vision_style_product("motionpicture/kodak/5260-Vision2-500T.pdf", 2, "Vision2 500T (5260/7260)", 500,
                                  2008, sens_box=(320, 50, 604, 309), spec_page_index=3,
                                  spec_box=(300, 25, 604, 245),
                                  dye_density_page_index=3, dye_density_box=(309.3, 316.7, 604, 571.8)),
    # 5201/5218: this era's Sensitometric panel prints negative camera-stop
    # ticks with NO minus sign ("10.0 8.0 ... 0.0 ... 6.0", the same
    # unsigned value literally repeated on both sides of zero) -- needs
    # _unsigned_camera_stops_calib rather than the default text-based fit,
    # which can't disambiguate one value read at two pixel positions.
    # All 3 (5201/5205/5218): page 3's real "Spectral-Sensitivity Curves"
    # panel is in the LEFT column (title x~104) -- the RIGHT column (title
    # x~377) is a *different* chart, "Spectral Dye-Density Curves", not
    # tracked by this project. An earlier version of this file pointed
    # spec_box at the right column for all 3, which either found zero
    # points or (worse) silently matched the wrong chart's own differently-
    # shaped curves under the same Yellow-/Magenta-/Cyan- label regex
    # names -- always verify which column a same-named-looking panel
    # actually sits in via real word coordinates, not just box math.
    lambda: vision_style_product(
        "motionpicture/kodak/5201-Vision2-50D-tech.pdf", 2, "Vision2 50D", 50, 2005,
        sens_box=(320, 48, 604, 309), spec_page_index=3, spec_box=(35, 379, 275, 600), min_trace_points=8,
        x_axis_calib_override=_unsigned_camera_stops_calib(
            "motionpicture/kodak/5201-Vision2-50D-tech.pdf", 2, (368, 270, 604, 290)),
        dye_density_page_index=3, dye_density_box=(320, 30, 570, 250)),
    # 5205's spectral_sensitivity panel is NOT included, same reason as
    # 5218 below: its Magenta-/Cyan-Forming Layer curves touch/overlap
    # enough that trace assignment mismatched (blue_yellow correctly
    # matched Yellow-Forming Layer, but green_magenta/red_cyan came back
    # as a narrow 30-point fragment and a fused 156-point blend
    # respectively -- confirmed wrong via QA overlay, not just a low point
    # count). characteristic_curve is unaffected.
    lambda: vision_style_product("motionpicture/kodak/5205-Vision2-250D-tech.pdf", 2, "Vision2 250D", 250, 2004,
                                  sens_box=(320, 48, 604, 309), y_tick_bbox=(340, 48, 370, 270),
                                  dye_density_page_index=3, dye_density_box=(315, 60, 570, 300),
                                  dye_density_labels=MP_DYE_DENSITY_LABELS_2CURVE),
    # 5218's spectral_sensitivity panel is NOT included: its 3 curves
    # (Yellow-/Magenta-/Cyan-Forming Layer) touch/overlap heavily around
    # 550-600nm, and `extract_traces_in_region` returns each of the 3 real
    # traces TWICE (6 candidates for 3 curves, all with identical
    # coordinates -- a real duplication in this file's own drawing
    # objects, confirmed by direct inspection, not an extraction bug) --
    # `assign_traces_to_labels_exclusive` matched 2 different labels to the
    # same duplicate trace regardless of anchor position (tried both real
    # label-text matching and hand-placed label_position_override anchors,
    # both failed the same way, flagged by the SANITY WARNING check).
    # The characteristic_curve chart (this product's primary, valuable
    # data) is unaffected and digitizes cleanly. Not chased further --
    # would need a real fix to trace de-duplication or a narrower
    # per-curve region_bbox mechanism this project doesn't have yet.
    lambda: vision_style_product(
        "motionpicture/kodak/5218-Vision2-500T-H-1-5218t.pdf", 2, "Vision2 500T (5218/7218)", 500, 2006,
        sens_box=(320, 48, 604, 309), min_trace_points=8,
        x_axis_calib_override=_unsigned_camera_stops_calib(
            "motionpicture/kodak/5218-Vision2-500T-H-1-5218t.pdf", 2, (320, 270, 604, 290)),
        dye_density_page_index=3, dye_density_box=(315, 26, 570, 280)),

    # --- Pre-VISION2 EXR/VISION-branded predecessors (2026-07-06 pass) ---
    # Same "Sensitometric/Characteristic Curves" + real signed B/G/R inline
    # labels template, just older sheets -- each needed its own box (never
    # grid-aligned across files, confirmed per file) and, for several, the
    # camera-stops axis needed a DIFFERENT tick-reading fix than any other
    # file: real signed ticks (5245/5246/5263/5277/5293), unsigned-
    # duplicated-around-a-real-"0.0"-pivot ticks (5289, `_unsigned_camera_
    # stops_calib`, tick_regex bare-digit not "N.0"), or a genuine "N"
    # glyph standing in for zero (harmless, not a tick candidate either
    # way). Spectral-sensitivity was attempted for 5245 (worked cleanly)
    # but skipped for 5248 (see below) and not chased for the others given
    # the volume of files still remaining in this vendor.
    lambda: vision_style_product("motionpicture/kodak/5245.pdf", 2, "EXR 50D", 50, 2003,
                                  sens_box=(335, 65.8, 522, 300), spec_page_index=3,
                                  spec_box=(35, 392, 275, 610),
                                  dye_density_page_index=3, dye_density_box=(316.2, 26.4, 604, 282.4),
                                  dye_density_labels=MP_DYE_DENSITY_LABELS_2CURVE),
    # 5248's Spectral-Sensitivity Curves chart is NOT included: its 3
    # curves (Yellow-/Magenta-/Cyan-Forming Layer) cross each other in the
    # 450-600nm range and none of the extracted traces reached past 563pt
    # (~600nm) even though the real Cyan-Forming curve visibly extends to
    # ~680nm -- confirmed via direct trace inspection, not just a visual
    # guess; the real curve is apparently split into fragments that don't
    # recombine cleanly here. characteristic_curve (this file's real
    # 3-panel-per-column "EXR 100T" layout, DIFFERENT box position from
    # every other file in this batch -- title top-LEFT not top-right) is
    # unaffected.
    lambda: vision_style_product("motionpicture/kodak/5248.pdf", 2, "EXR 100T", 100, 1998,
                                  sens_box=(55, 44, 290, 262),
                                  dye_density_box=(44.2, 257.8, 300, 501.1),
                                  dye_density_labels=MP_DYE_DENSITY_LABELS_2CURVE),
    # Spectral-Dye-Density panel NOT included: attempted with a box derived from the real
    # title/axis word positions, but the 5 curves' extracted x-ranges came back genuinely
    # mismatched (each curve covering a different, mostly-non-overlapping window instead of
    # all spanning ~350-800nm together) -- confirmed via QA overlay, not just the range check.
    # characteristic_curve is unaffected. Real follow-up work, not chased further given the
    # volume of files remaining in this vendor.
    lambda: vision_style_product("motionpicture/kodak/5246.pdf", 3, "VISION 250D", 250, 2003,
                                  sens_box=(42, 65.8, 290, 290)),
    lambda: vision_style_product("motionpicture/kodak/5263.pdf", 2, "VISION 5263 500T", 500, 2002,
                                  sens_box=(335, 53.4, 570, 295), x_tick_regex=r"\d\.0",
                                  x_axis_calib_override=_unsigned_camera_stops_calib(
                                      "motionpicture/kodak/5263.pdf", 2, (362, 260, 570, 290)),
                                  dye_density_page_index=3, dye_density_box=(314.2, 334.4, 604, 590.0)),
    # Spectral-Dye-Density panel NOT included: unlike every other sheet in this file, this
    # panel's curve labels sit in a boxed legend (dash-pattern-differentiated: "-- -- Yellow",
    # "...." Magenta, "-.-.-" Cyan) rather than as inline text near each curve -- Strategy D's
    # rank-by-y label matching assumes inline labels and produces systematically wrong/rotated
    # assignments here (confirmed via QA overlay). Same failure mode independently confirmed on
    # h15239 (Ektachrome Daylight 7239) and 7267_zh_CN (Kodachrome 25 Movie) in kodak_mp_reversal.py.
    # Needs a dash-pattern-aware strategy (Strategy B, vector_stroke_dash), not attempted here.
    lambda: vision_style_product("motionpicture/kodak/5277.pdf", 3, "VISION 320T", 320, 1996,
                                  sens_box=(42, 395.6, 300, 680)),
    lambda: vision_style_product("motionpicture/kodak/5293.pdf", 2, "EXR 200T", 200, 2003,
                                  sens_box=(60, 403.7, 300, 630),
                                  dye_density_page_index=3, dye_density_box=(315.1, 26.4, 604, 282.8),
                                  dye_density_labels=MP_DYE_DENSITY_LABELS_2CURVE),
    lambda: vision_style_product(
        "motionpicture/kodak/5289_zh_CN.pdf", 1, "VISION 800T", 800, 1999,
        sens_box=(330, 207, 545, 662), x_tick_regex=r"\d$",
        x_axis_calib_override=(0.08673290543870164, -38.41947273240247),
        dye_density_page_index=2, dye_density_box=(53.2, 25.2, 300, 344.6),
        dye_density_labels=PAPER_DYE_DENSITY_LABELS),

    # --- Non-VISION/EXR color negative motion-picture stocks (2026-07-06) ---
    lambda: vision_style_product("motionpicture/kodak/7620.pdf", 2, "PRIMETIME 640T", 640, 1996,
                                  sens_box=(54, 48.4, 300, 325), spec_box=(54, 378.4, 300, 635)),
    # Spectral-Dye-Density panel NOT included: same class of gap as 5246.pdf above -- the 5
    # curves' extracted x-ranges came back mismatched (midscale_neutral/magenta both cut off
    # well short of the other 3 curves' full ~373-790nm span), confirmed via QA overlay.
    # characteristic_curve/spectral_sensitivity unaffected.
    lambda: vision_style_product("motionpicture/kodak/7299-Vision2-HDscan.pdf", 3,
                                  "VISION2 HD Color Scan", 500, 2005,
                                  sens_box=(42, 65.8, 300, 290), spec_page_index=4,
                                  spec_box=(35, 44.8, 300, 235)),
]


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
