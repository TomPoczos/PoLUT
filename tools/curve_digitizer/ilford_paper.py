"""
Digitizes Ilford Multigrade variable-contrast paper datasheets
(paper/ilford/*.pdf) into consolidated-data/paper/ilford/black-and-white/.

Confirmed genuinely blocked as of 2026-07-05 (see BLOCKED.md): each sheet's
"Characteristic curves" panel plots all 7 MULTIGRADE filter grades
(00/0/1/2/3/4/5) with per-curve grade numbers visible in the rendered PDF,
but neither the axis ticks nor the grade labels are real extractable text
(zero words returned by a direct search).

RESOLVED 2026-07-06 via OCR (axis ticks) + a NEW rank-assignment mechanism
for curve identity (`digitizer_core.assign_traces_by_x_rank`) -- this
chart's geometry is the MIRROR IMAGE of Fuji's R/G/B case: all 7 grade
labels sit at nearly the same Y (a shared shoulder plateau near Dmax),
spread out along X instead, so `assign_traces_to_labels_exclusive`'s
rank-BY-Y primary strategy can't discriminate them (and the labels
themselves resisted reliable OCR -- small, sitting right on the crossing
curve lines, same problem class as Fuji's rotated inline labels). Physical
justification for the rank order: higher contrast grades are steeper, so
they reach the shoulder at a SMALLER x than lower grades -- confirmed both
by direct visual inspection (grade numbers run in that exact left-to-right
order) and, more rigorously, by cross-checking each grade label's own
precise pixel position against each trace's interpolated x AT THAT SAME Y
(not just eyeballing the whole curve shape, which got one trace wrong on
the first attempt -- see `assign_traces_by_x_rank`'s docstring on why raw
end-x isn't robust and `rank_at_y` is needed instead, picked near the
label row itself, not the curves' shared toe-convergence pivot).

Also needed `extract_traces_in_region(..., split_on_x_reversal=True)`:
Ilford draws all of one chart's curves as ONE continuous PDF path object,
pen-jumping (not lifting) from one curve's toe back to the next curve's
shoulder -- exactly the "pen doesn't lift, x-direction reverses and stays
reversed" pattern that mechanism was built for (f9-Tri-X_Pan.pdf, this same
multi-session project, 2026-07-05).

Usage: uv run ilford_paper.py
"""

from pathlib import Path

import fitz

from digitizer_core import ChartSpec, CurveSpec
from ocr_helpers import ocr_axis_calib
from product import PaperProductSpec, digitize_paper, run_products_parallel

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")


def multigrade_chart(pdf_stub, page_index, names, char_box, x_tick_bbox, y_tick_bbox, rank_at_y,
                      chart_id, x_tick_regex=r"\d", y_tick_regex=r"\d\.\d"):
    pdf_path = PDF_ROOT / pdf_stub
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    x_calib = ocr_axis_calib(page, x_tick_bbox, tick_regex=x_tick_regex, axis="x")
    y_calib = ocr_axis_calib(page, y_tick_bbox, tick_regex=y_tick_regex, axis="y")
    return ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id=chart_id,
        x_tick_regex=x_tick_regex, y_tick_regex=y_tick_regex,
        x_label="relative_log_exposure", y_label="density",
        curves=[CurveSpec(n) for n in names],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=char_box, monotonic_direction="increasing",
        min_trace_points=6, split_on_x_reversal=True, reversal_run_length=5,
        rank_assignment_names=names, rank_at_y=rank_at_y,
        x_axis_calib_override=x_calib, y_axis_calib_override=y_calib,
    )


def multigrade_product(pdf_stub, paper_name, year, chart1_box, chart1_ticks, chart1_rank_y,
                        chart2_box, chart2_ticks, chart2_rank_y, page_index=1, extra_notes=""):
    """Both Multigrade IV RC-family sheets checked so far (2026-07-06) split
    the 7 grades across 2 panels the same way: grades 00/0/1/2/3 (5 curves,
    tightly bunched) on one chart, grades 4/5 (2 curves, higher-contrast,
    separate panel) on another -- not literally "all 7 on one chart" as
    BLOCKED.md's original (pre-investigation) note assumed."""
    names1 = ["grade_3", "grade_2", "grade_1", "grade_0", "grade_00"]
    names2 = ["grade_5", "grade_4"]
    chart1 = multigrade_chart(pdf_stub, page_index, names1, chart1_box,
                               chart1_ticks[0], chart1_ticks[1], chart1_rank_y,
                               chart_id="characteristic_curve_grades_00_to_3")
    chart2 = multigrade_chart(pdf_stub, page_index, names2, chart2_box,
                               chart2_ticks[0], chart2_ticks[1], chart2_rank_y,
                               chart_id="characteristic_curve_grades_4_5")
    return PaperProductSpec(
        brand="ilford", paper_name=paper_name, paper_for="black-and-white", year=year,
        source_pdf=pdf_stub, charts=[chart1, chart2],
        digitizer_notes="'Characteristic curves' panels (2, grades 00-3 and 4-5) with no "
                         "extractable tick/grade-label text -- axis calibration via OCR (tesseract), "
                         "curve identity via assign_traces_by_x_rank (curves discriminated by shoulder "
                         "X-position, not the usual Y-rank, since all grade labels sit at nearly the "
                         "same height on a shared near-Dmax plateau) rather than OCR/rank-order of the "
                         "grade-number labels themselves (too small and crossed by curve ink to OCR "
                         "reliably). Rank order confirmed both by direct visual inspection and by "
                         "cross-checking each label's own pixel position against each trace's "
                         "interpolated x at that same y." + (" " + extra_notes if extra_notes else ""),
    )


PRODUCTS = [
    lambda: multigrade_product(
        "paper/ilford/Multigrade IV RC.pdf", "Multigrade IV RC", 2001,
        chart1_box=(370, 338, 500, 430), chart1_ticks=((310, 428, 490, 445), (500, 320, 535, 410)),
        chart1_rank_y=350.0,
        chart2_box=(390, 485, 495, 575), chart2_ticks=((325, 573, 490, 586), (498, 478, 520, 533)),
        chart2_rank_y=530.0,
    ),
    lambda: multigrade_product(
        "paper/ilford/WarmtoneRC.pdf", "Multigrade RC Warmtone", 2001,
        chart1_box=(380, 95, 505, 195), chart1_ticks=((340, 195, 500, 205), (515, 90, 540, 165)),
        chart1_rank_y=110.0,
        chart2_box=(390, 240, 498, 340), chart2_ticks=((330, 340, 500, 350), (505, 225, 540, 310)),
        chart2_rank_y=250.0,
    ),
    lambda: multigrade_product(
        "paper/ilford/CooltoneRC.pdf", "Multigrade RC Cooltone", 2001,
        chart1_box=(380, 95, 500, 195), chart1_ticks=((330, 195, 500, 212), (510, 100, 535, 160)),
        chart1_rank_y=115.0,
        chart2_box=(390, 245, 500, 340), chart2_ticks=((325, 338, 495, 352), (495, 235, 530, 310)),
        chart2_rank_y=270.0,
        extra_notes="Grades 4/5 specifically: this paper's own two curves are nearly "
                    "coincident (differ by <0.5pt in page-space at every checked y, versus "
                    "clearly-separated curves on the same panel for Warmtone/standard RC) -- "
                    "confirmed a real, physical property of this material (grade 4 and 5 give "
                    "very similar contrast on Cooltone specifically), not a digitization "
                    "problem. grade_4/grade_5 identity here is the LOWEST-confidence "
                    "assignment in this whole batch -- based on the same steeper-is-smaller-x "
                    "convention as every other chart, but the labels' own leader-line "
                    "geometry is genuinely ambiguous at this separation.",
    ),
]


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
