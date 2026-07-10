"""
Digitizes H&D / spectral-sensitivity charts out of vector-drawn Kodak/Eastman
PDF datasheets.

Unlike raster/color-tracing digitization, this reads the actual PDF drawing
commands (line and Bezier-curve path points) that make up each plotted curve,
so there is no pixel-resolution ceiling: precision is limited only by how the
original document's plotting software drew the line (Kodak's datasheets place
curves to hundredths of a point). Axis calibration is done the same way -- by
reading the exact bounding boxes of the tick-label text objects, not by eye.

Source PDFs live in the repo-root papers/ folder (reference documents),
alongside things like the Fairchild & Pirrotta HK paper. Digitized results
are written into film_paper_filter_data/ (the actual usable dataset), not
next to the source PDF -- raw references and derived data are kept separate.

Usage: edit CHARTS below to describe each chart to extract, then:
    uv run main.py
Outputs one JSON + one QA overlay PNG per chart, written directly into the
target film's canonical folder under film_paper_filter_data/films/, prefixed
with film_id so multiple charts/films can share a directory without
collisions.

This is the original single-file tool, kept for its existing
film_paper_filter_data/ output. The shared axis-fit/extraction/binning/
simplification/QA-overlay machinery now lives in digitizer_core.py -- see
that module's docstring for the 3 curve-extraction strategies (vector color
fill / vector stroke-dash / raster pixel trace) it added to handle vendors
beyond Kodak's color-fill datasheets. consolidate_corpus.py is the new,
separate entry point for the much larger papers/125pixcom -> consolidated-data
extraction job; it reuses this same digitizer_core.py.
"""

import json
from pathlib import Path

import fitz

from digitizer_core import ChartSpec, CurveSpec, digitize_chart, render_qa_overlay

HERE = Path(__file__).parent
REPO_ROOT = HERE.parent.parent  # PoLUT/
DATA_ROOT = REPO_ROOT / "film_paper_filter_data"
PDF_DIR = REPO_ROOT / "papers" / "specs"  # source datasheet PDFs live here, not in film_paper_filter_data


CHARTS = [
    ChartSpec(
        pdf="kodak_internegative_ii_5272_TI1301.pdf",
        page_index=5,
        chart_id="characteristic_curve",
        x_tick_regex=r"-?\d\.00",
        y_tick_regex=r"[0-3]",
        x_label="log_exposure_lux_seconds",
        y_label="density_status_m",
        curves=[
            CurveSpec("blue_yellow_forming_layer", fill_rgb=(0.0, 0.0, 1.0)),
            CurveSpec("green_magenta_forming_layer", fill_rgb=(0.5, 0.5, 0.0)),
            CurveSpec("red_cyan_forming_layer", fill_rgb=(1.0, 0.0, 0.0)),
        ],
        film_id="films/color/internegative/kodak_internegative_ii_5272",
        legend_bbox=(96, 170, 196, 217),
        monotonic_direction="increasing",  # real H&D curve: density rises with exposure
    ),
    ChartSpec(
        pdf="kodak_internegative_ii_5272_TI1301.pdf",
        page_index=6,
        chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}",
        y_tick_regex=r"-?\d",
        x_label="wavelength_nm",
        y_label="log_sensitivity",
        curves=[
            CurveSpec("blue_yellow_forming_layer", fill_rgb=(0.0, 0.0, 1.0)),
            CurveSpec("green_magenta_forming_layer", fill_rgb=(0.5, 0.5, 0.0)),
            CurveSpec("red_cyan_forming_layer", fill_rgb=(1.0, 0.0, 0.0)),
        ],
        film_id="films/color/internegative/kodak_internegative_ii_5272",
        legend_bbox=(150, 449, 253, 490),
    ),
]


def digitize(chart: ChartSpec):
    prefix = DATA_ROOT / chart.film_id
    out_dir = prefix.parent
    file_prefix = prefix.name
    out_dir.mkdir(parents=True, exist_ok=True)
    qa_path = out_dir / f"{file_prefix}_{chart.chart_id}_qa_overlay.png"

    result = digitize_chart(chart, PDF_DIR / chart.pdf)
    doc = fitz.open(PDF_DIR / chart.pdf)
    render_qa_overlay([(chart, result["_qa_results"], result["_qa_calib"], doc[chart.page_index])], qa_path)
    doc.close()
    result["qa_overlay_png"] = qa_path.name
    for private_key in ("_qa_results", "_qa_calib", "_qa_page_number"):
        result.pop(private_key, None)

    out_path = out_dir / f"{file_prefix}_{chart.chart_id}.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"  -> {out_path}")
    print(f"  -> {qa_path} (visual QA: extracted curve overlaid on rendered page)")


def main():
    for chart in CHARTS:
        print(f"[{chart.chart_id}] {chart.pdf} page {chart.page_index}")
        digitize(chart)


if __name__ == "__main__":
    main()
