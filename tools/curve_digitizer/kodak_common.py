"""
Shared helpers for Kodak still-photography datasheets (film/kodak/*.pdf):
these pack several mini-charts (Characteristic Curves, Spectral-Sensitivity
Curves, Spectral-Dye-Density Curves, Modulation Transfer Function, sometimes
Reciprocity) onto one page, all in the same black ink, each curve identified
by a small inline label rather than color -- Strategy D (vector_position) in
digitizer_core.py, panel regions auto-located via locate_panel_bboxes().
"""

import re
from pathlib import Path

import fitz
import numpy as np

from digitizer_core import ChartSpec, CurveSpec, curves_by_peak_x, curves_by_peak_x_with_envelope, locate_panel_bboxes

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")

# (curve name, inline-label regex) -- color negative films print "B"/"G"/"R"
# next to the Characteristic Curves and "Yellow-"/"Magenta-"/"Cyan-" (first
# word of "Yellow-\nForming\nLayer" etc.) next to Spectral-Sensitivity.
COLOR_NEG_CHAR_LABELS = [
    ("red_cyan_forming_layer", r"^R$"),
    ("green_magenta_forming_layer", r"^G$"),
    ("blue_yellow_forming_layer", r"^B$"),
]
COLOR_NEG_SPECTRAL_LABELS = [
    ("red_cyan_forming_layer", r"^Cyan-$"),
    ("green_magenta_forming_layer", r"^Magenta-$"),
    ("blue_yellow_forming_layer", r"^Yellow-$"),
]
BW_CHAR_LABEL = [("density", r"^Density$")]  # overridden per-file if the sheet uses a different word

# The Spectral-Dye-Density panel doesn't plot one curve per dye layer --
# it plots overall DIFFUSE spectral density vs wavelength for two reference
# exposures (D-min, and a "midscale neutral" subject), i.e. what all three
# dyes look like together at those two points, not each dye in isolation.
# Confirmed by rendering the panel directly (Portra 400/Ektar 100/Elite
# Color 200/Gold 100&200/Pro Films): always exactly these two curves,
# labeled inline "Minimum Density" / "Midscale Neutral", same single-ink
# Strategy D (vector_position) as the other 3 panels on this page template.
DYE_DENSITY_LABELS = [
    ("d_min", r"^Minimum$"),
    ("midscale_neutral", r"^Midscale$"),
]

# Reversal (slide) film's own Spectral-Dye-Density panel is a DIFFERENT chart
# from the negative-film one above, despite the identical title -- confirmed
# by rendering e8-Ektachrome_64_EPR.pdf's panel directly (user caught this:
# the negative-film 2-curve model does not describe what's on a reversal
# sheet). It plots each dye's OWN normalized spectral absorption curve
# (Yellow/Magenta/Cyan, each normalized to form a visual neutral density of
# 1.0 under a 5000K illuminant -- real per-dye data, not a composite at two
# reference exposures) plus a 4th "Visual Neutral" curve (the sum of all
# three, i.e. what a neutral gray patch's own diffuse density spectrum looks
# like). Bare "Yellow"/"Magenta"/"Cyan" inline labels here (no "-Forming
# Layer" suffix, no trailing hyphen) -- distinct from
# COLOR_NEG_SPECTRAL_LABELS's "Yellow-"/"Magenta-"/"Cyan-" so there's no
# regex collision if both panels are ever read from the same page.
REVERSAL_DYE_DENSITY_LABELS = [
    ("yellow", r"^Yellow$"),
    ("magenta", r"^Magenta$"),
    ("cyan", r"^Cyan$"),
    ("visual_neutral", r"^Visual$"),
]

# Print PAPER's own Spectral-Dye-Density panel (RA-4 color-negative paper,
# e.g. paper/kodak/e140.pdf) is a THIRD distinct shape -- confirmed by
# rendering directly: same bare "Yellow"/"Magenta"/"Cyan" inline labels as
# reversal film's version, but only 3 curves, no 4th "Visual Neutral"
# envelope. Makes physical sense: paper is a reflective print viewed by
# reflection, not a transmissive original with its own "what does a neutral
# patch look like stacked" question the way reversal film's normalization
# convention answers -- there's no equivalent composite curve to plot.
PAPER_DYE_DENSITY_LABELS = [
    ("yellow", r"^Yellow$"),
    ("magenta", r"^Magenta$"),
    ("cyan", r"^Cyan$"),
]

# Chromogenic B&W paper (Portra B&W/Sepia Paper -- real C-41/RA-4 dye layers
# under the hood, same as chromogenic B&W FILM, but the final image reads
# monochrome/toned) prints only ONE undifferentiated "Diffuse Spectral
# Density" curve on this panel, not 3 dye curves -- confirmed by rendering
# g4006-Portra_BW_Paper.pdf directly, no Yellow/Magenta/Cyan labels exist to
# search for at all. `label_regex` anchors on the nearby "Process:" text
# instead (there's only one real trace in the panel, so any reasonable
# anchor pairs correctly -- no second curve to mismatch against).
PAPER_BW_DYE_DENSITY_LABELS = [
    ("visual_density", r"^Process:$"),
]

# Some older-era papers (e.g. e2446-Digital_III_Color_Paper.pdf) abbreviate
# the Spectral-Dye-Density panel's inline labels to bare single letters
# ("Y"/"M"/"C") rather than the full words -- confirmed via render.
PAPER_DYE_DENSITY_LABELS_ABBREV = [
    ("yellow", r"^Y$"),
    ("magenta", r"^M$"),
    ("cyan", r"^C$"),
]

# Motion-picture negative film's own Spectral Dye Density panel (a FOURTH
# distinct shape, confirmed by rendering motionpicture/kodak/5201-Vision2-
# 50D-tech.pdf) combines both other conventions in ONE chart: the
# negative-film-still-photography 2-curve composite (d_min/midscale_neutral)
# PLUS the reversal/paper-style 3 individual dye curves (Yellow/Magenta/
# Cyan), 5 curves total, no "Visual Neutral" (that's specific to reversal's
# transmissive-original framing). Not every MP sheet labels all 5 -- some
# (e.g. 5245, 5293) only label d_min/midscale_neutral, leaving the 3 dye
# curves genuinely unlabeled; use MP_DYE_DENSITY_LABELS_2CURVE for those
# (verified per-file via render, not assumed).
MP_DYE_DENSITY_LABELS = [
    ("d_min", r"^Minimum$"),
    ("midscale_neutral", r"^Midscale$"),
    ("yellow", r"^Yellow$"),
    ("magenta", r"^Magenta$"),
    ("cyan", r"^Cyan$"),
]
MP_DYE_DENSITY_LABELS_2CURVE = [
    ("d_min", r"^Minimum$"),
    ("midscale_neutral", r"^Midscale$"),
]


def overline_negative_calib(pdf_path, page_index, region_bbox, tick_regex=r"-?\d\.0"):
    """Several ~1997-2003-era Kodak sheets draw the minus sign on negative
    axis ticks as a small vector overline, not a text glyph -- every
    negative tick except the pixel-rightmost (genuinely unsigned) one
    extracts as its bare unsigned value, indistinguishable by text alone
    from a real unsigned tick at a different position (seen so far on
    E-7022 Gold, paper/kodak/e140, and this era's Royal Gold/GA100 sheets).
    Negates every tick except the rightmost-by-pixel and fits (slope,
    intercept) from the corrected values -- pass the result as
    ChartSpec.x_axis_calib_override rather than trusting fit_axis's
    text-based reading for this axis."""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    words = page.get_text("words")
    doc.close()
    candidates = []
    for x0, y0, x1, y1, text, *_ in words:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if not (region_bbox[0] <= cx <= region_bbox[2] and region_bbox[1] <= cy <= region_bbox[3]):
            continue
        if re.fullmatch(tick_regex, text):
            try:
                candidates.append((cx, cy, float(text)))
            except ValueError:
                pass
    if len(candidates) < 2:
        raise RuntimeError(f"only {len(candidates)} tick candidates found in {region_bbox} for overline fix")

    # A wide region_bbox (common when only one panel title was found, so the
    # box defaults to the rest of the page) can catch several unrelated tick
    # rows/columns -- e.g. the y-axis's own density column, a neighboring
    # panel's axis, etc. The real x-axis row is the one sharing a common y
    # AND spanning a wide x-range (a column like the y-axis shares a common x
    # instead, so it has a narrow x-spread). Cluster by y, keep the
    # widest-x-spread cluster.
    by_y = sorted(candidates, key=lambda c: c[1])
    clusters, cur = [], [by_y[0]]
    for c in by_y[1:]:
        if abs(c[1] - cur[-1][1]) <= 6:
            cur.append(c)
        else:
            clusters.append(cur)
            cur = [c]
    clusters.append(cur)
    best = max(clusters, key=lambda cl: max(p[0] for p in cl) - min(p[0] for p in cl))
    if len(best) < 2:
        raise RuntimeError(f"widest tick row only has {len(best)} points in {region_bbox} for overline fix")

    best.sort(key=lambda c: c[0])
    pixels = [c[0] for c in best]
    corrected = [-c[2] for c in best[:-1]] + [best[-1][2]]
    slope, intercept = np.polyfit(pixels, corrected, 1)
    return float(slope), float(intercept)


def overline_symmetric_calib(pdf_path, page_index, region_bbox, tick_regex=r"\d\.0"):
    """Reversal film's Spectral-Sensitivity panel (LOG SENSITIVITY axis,
    typically -2.0 to 2.0) has the SAME overline-vector-minus-sign problem as
    overline_negative_calib, but on a Y-axis with real ticks on BOTH sides of
    a real 0.0 -- confirmed on e8-Ektachrome_64_EPR.pdf: prints "2.0 1.0 0.0
    1.0 2.0" top-to-bottom, i.e. the bottom half's minus signs are drawn
    overlines, not text. overline_negative_calib's rule ("negate everything
    except the rightmost tick") doesn't apply here since there's no single
    genuinely-unsigned end -- both extremes print an unsigned-looking value.
    Instead: find the real 0.0 tick's own pixel position (the one genuinely
    unambiguous value on the axis) and negate every OTHER tick on the far
    side of it from the smallest-pixel (top, largest real value) end."""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    words = page.get_text("words")
    doc.close()
    candidates = []
    for x0, y0, x1, y1, text, *_ in words:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if not (region_bbox[0] <= cx <= region_bbox[2] and region_bbox[1] <= cy <= region_bbox[3]):
            continue
        if re.fullmatch(tick_regex, text):
            try:
                candidates.append((cx, cy, float(text)))
            except ValueError:
                pass
    if len(candidates) < 3:
        raise RuntimeError(f"only {len(candidates)} tick candidates found in {region_bbox} for symmetric fix")

    # Keep the narrowest-x-spread (tallest-y-spread) cluster -- the y-axis's
    # own tick column, not a same-format row elsewhere on the page.
    by_x = sorted(candidates, key=lambda c: c[0])
    clusters, cur = [], [by_x[0]]
    for c in by_x[1:]:
        if abs(c[0] - cur[-1][0]) <= 6:
            cur.append(c)
        else:
            clusters.append(cur)
            cur = [c]
    clusters.append(cur)
    best = max(clusters, key=lambda cl: max(p[1] for p in cl) - min(p[1] for p in cl))
    if len(best) < 3:
        raise RuntimeError(f"tallest tick column only has {len(best)} points in {region_bbox} for symmetric fix")

    best.sort(key=lambda c: c[1])  # top (smallest pixel-y) to bottom
    zero_idx = min(range(len(best)), key=lambda i: abs(best[i][2]))
    pixels = [c[1] for c in best]  # pixel-y (vertical axis)
    corrected = [v if i <= zero_idx else -v for i, (_, _, v) in enumerate(best)]
    slope, intercept = np.polyfit(pixels, corrected, 1)
    return float(slope), float(intercept)


def get_panel_bboxes(pdf_path, page_index, titles):
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    boxes = locate_panel_bboxes(page, titles)
    doc.close()
    return boxes


def characteristic_chart(pdf_stub, page_index, panel_bbox, labels=COLOR_NEG_CHAR_LABELS,
                          x_tick_regex=r"-?\d\.0", y_tick_regex=r"\d\.0", monotonic="increasing"):
    return ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="characteristic_curve",
        x_tick_regex=x_tick_regex, y_tick_regex=y_tick_regex,
        x_label="log_exposure_lux_seconds", y_label="density_status_m",
        curves=[CurveSpec(name, label_regex=regex) for name, regex in labels],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=panel_bbox, monotonic_direction=monotonic,
    )


def spectral_chart(pdf_stub, page_index, panel_bbox, labels=COLOR_NEG_SPECTRAL_LABELS,
                    x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0"):
    return ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="spectral_sensitivity",
        x_tick_regex=x_tick_regex, y_tick_regex=y_tick_regex,
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[CurveSpec(name, label_regex=regex) for name, regex in labels],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=panel_bbox,
    )


def spectral_sensitivity_chart_by_peak_x(pdf_stub, page_index, panel_bbox, names_in_peak_x_order,
                                          cross_object_merge=False, min_trace_points=12, merge_strategy="proximity"):
    """Reversal film's own Spectral-Sensitivity panel (Yellow-/Magenta-/Cyan-Forming Layer inline
    labels, LOG SENSITIVITY vs WAVELENGTH) has the same near-tied-label-y problem
    `curves_by_peak_x` was built for on the Spectral-Dye-Density panel (see that function's own
    docstring for the full corpus-wide story) -- confirmed directly on e8-Ektachrome_64_EPR.pdf:
    plain label-regex/rank matching silently swaps the Magenta-Forming (peaks ~550nm) and
    Cyan-Forming (peaks ~650nm) traces (verified against the rendered page: the trace assigned
    "red_cyan_forming_layer" peaked at ~550nm, not ~650nm). Identified by peak-x instead, same
    physical left-to-right invariant as the dye-density panel (Yellow-Forming peaks bluest
    ~420-450nm, Magenta-Forming mid ~550nm, Cyan-Forming reddest ~650nm) -- pass
    `names_in_peak_x_order=["blue_yellow_forming_layer", "green_magenta_forming_layer",
    "red_cyan_forming_layer"]`."""
    pdf_path = PDF_ROOT / pdf_stub
    curves = curves_by_peak_x(pdf_path, page_index, panel_bbox, names_in_peak_x_order,
                               min_trace_points=min_trace_points, cross_object_merge=cross_object_merge,
                               merge_strategy=merge_strategy)
    chart = ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=curves, film_id="_unused", extraction_method="vector_position",
        region_bbox=panel_bbox,
    )
    chart.cross_object_merge = cross_object_merge
    chart.min_trace_points = min_trace_points
    chart.merge_strategy = merge_strategy
    return chart


def spectral_dye_density_chart(pdf_stub, page_index, panel_bbox, labels=DYE_DENSITY_LABELS,
                                x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.[05]",
                                cross_object_merge=False, min_trace_points=12, merge_strategy="proximity",
                                dye_names_in_peak_x_order=("yellow", "magenta", "cyan")):
    # The plain 3-curve (PAPER_DYE_DENSITY_LABELS) and 4-curve (REVERSAL_DYE_DENSITY_LABELS)
    # Yellow/Magenta/Cyan[/Visual-Neutral] shapes use real peak-position identification
    # (curves_by_peak_x / curves_by_peak_x_with_envelope, digitizer_core.py) instead of plain
    # label-regex matching -- confirmed (2026-07-10) that assign_traces_to_labels_exclusive's
    # rank-by-label-y strategy silently mismatches curve identity on the large majority of
    # these panels corpus-wide, not just the handful of exactly-tied-label-y cases first found
    # on Fuji -- see curves_by_peak_x's own docstring for the full story and how this was
    # caught. `dye_names_in_peak_x_order` defaults to the real physical left-to-right order --
    # override it (e.g. paper/kodak/e4034.pdf's confirmed, documented Magenta/Cyan print swap)
    # so a real source-document labeling error gets preserved/flagged rather than silently
    # "corrected" back to the physical convention -- see curves_by_peak_x's own docstring.
    # `cross_object_merge`/`min_trace_points`/`merge_strategy` are threaded into BOTH
    # the identity-determining extraction pass here AND the chart's own later extraction (set
    # as attributes below) -- they must match, or the two passes could find a different number
    # of traces and the label_position_override pairing breaks.
    names = [name for name, _ in labels]
    if names == ["yellow", "magenta", "cyan"]:
        curves = curves_by_peak_x(PDF_ROOT / pdf_stub, page_index, panel_bbox,
                                   list(dye_names_in_peak_x_order),
                                   min_trace_points=min_trace_points, cross_object_merge=cross_object_merge,
                                   merge_strategy=merge_strategy)
    elif names == ["yellow", "magenta", "cyan", "visual_neutral"]:
        dye_order = [n for n in dye_names_in_peak_x_order if n != "visual_neutral"]
        curves = curves_by_peak_x_with_envelope(PDF_ROOT / pdf_stub, page_index, panel_bbox,
                                                 dye_order, "visual_neutral",
                                                 min_trace_points=min_trace_points,
                                                 cross_object_merge=cross_object_merge,
                                                 merge_strategy=merge_strategy)
    else:
        curves = [CurveSpec(name, label_regex=regex) for name, regex in labels]
    chart = ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="spectral_dye_density",
        x_tick_regex=x_tick_regex, y_tick_regex=y_tick_regex,
        x_label="wavelength_nm", y_label="diffuse_spectral_density",
        curves=curves,
        film_id="_unused", extraction_method="vector_position",
        region_bbox=panel_bbox,
        # Real non-monotonic spectral absorption shape (dye-density peaks/
        # dips across the visible range) -- same reasoning as spectral_chart,
        # no isotonic enforcement.
    )
    chart.cross_object_merge = cross_object_merge
    chart.min_trace_points = min_trace_points
    chart.merge_strategy = merge_strategy
    return chart
