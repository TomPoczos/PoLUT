"""
Digitizes MACO/Rollei black-and-white film datasheets (film/maco/*.pdf,
film/rollei/*.pdf) into consolidated-data/film/photography/negative/maco/.

Corpus is much smaller than the original plan's German-language assumption
suggested: only 3 files total, and MACO_IR820c_AURA.pdf is actually English
(2004 international "Technical Application" sheet, not German) -- the
German-keyword-localization work anticipated in the plan turned out not to
be needed for this vendor pair.

- `film/maco/MACO_IR820c_AURA.pdf`: ONE real, cleanly-extractable
  characteristic curve (page 6, "Characteristic Curve", single undifferen-
  tiated density curve, same "no inline label needed" shape as most Ilford
  films) -- digitized here. Real gotcha: this sheet's tick text uses EUROPEAN
  COMMA decimals ("0,3", "3,00"), which `digitizer_core.fit_axis`'s bare
  `float(text)` call would silently reject (comma isn't a valid Python float
  separator, caught by that function's own `except ValueError: continue`,
  so it just looks like "no ticks found" rather than an obvious error) --
  handled with a small dedicated comma-to-period fit here rather than
  changing `fit_axis` itself (every other vendor in this corpus uses period
  decimals; not worth a global behavior change for one file).
  The SAME file's page 8 "Spectral sensitivity of infrared films" diagram
  (comparing MACO IR820c/IR750c/Cube 400c against Kodak HIE and Konica) is
  NOT digitized: confirmed via `page.get_images()` it's a single embedded
  raster (JPEG) image, not vector data, and is also a third-party
  comparative diagram (credited "Schroeders Negativ-Praxis") rather than
  the manufacturer's own primary measurement -- same raster-deprioritization
  call as the rest of this session, see BLOCKED.md.
- `film/rollei/Rollei_Infrared.pdf`: has "Characteristic diagram:" and
  "Spectral sensitivity:" labels but both diagrams are embedded as one large
  raster JPEG (confirmed via `page.get_images()`) -- blocked, see BLOCKED.md.
- `film/rollei/Development_Rollei films.pdf`: confirmed a development-time
  TABLE only (bilingual English/Dutch), no chart at all -- out of scope,
  see BLOCKED.md's no-curve-data section.

Usage: uv run maco_rollei_film.py
"""

from pathlib import Path

import fitz
import numpy as np

from digitizer_core import ChartSpec, CurveSpec
from product import ProductSpec, digitize_product, run_products_parallel

PDF_ROOT = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom")


def _comma_axis_calib(page, bbox, tick_regex, axis):
    """Same least-squares tick-fit `fit_axis` does, but tolerant of European
    comma decimals ("0,3" -> 0.3) -- `fit_axis`'s own `float(text)` call
    would otherwise reject every candidate (ValueError, silently caught and
    skipped), surfacing as a confusing "0 ticks found" rather than a clear
    locale problem."""
    x0, y0, x1, y1 = bbox
    candidates = []
    for wx0, wy0, wx1, wy1, text, *_ in page.get_text("words"):
        cx, cy = (wx0 + wx1) / 2, (wy0 + wy1) / 2
        if not (x0 <= cx <= x1 and y0 <= cy <= y1):
            continue
        import re
        if not re.fullmatch(tick_regex, text):
            continue
        try:
            val = float(text.replace(",", "."))
        except ValueError:
            continue
        px = cx if axis == "x" else cy
        candidates.append((px, val))
    if len(candidates) < 2:
        raise RuntimeError(f"only found {len(candidates)} comma-decimal ticks matching {tick_regex!r} in {bbox}")
    pixels = [c[0] for c in candidates]
    values = [c[1] for c in candidates]
    slope, intercept = np.polyfit(pixels, values, 1)
    return float(slope), float(intercept)


def maco_ir820c_product():
    pdf_stub = "film/maco/MACO_IR820c_AURA.pdf"
    page_index = 6
    doc = fitz.open(PDF_ROOT / pdf_stub)
    page = doc[page_index]
    box = (41, 257.3, 292, 474)
    x_tick_bbox = (41, 455, 295, 466)
    y_tick_bbox = (40, 265, 60, 456)
    x_calib = _comma_axis_calib(page, x_tick_bbox, r"\d,\d", axis="x")
    y_calib = _comma_axis_calib(page, y_tick_bbox, r"\d,\d\d", axis="y")
    doc.close()

    chart = ChartSpec(
        pdf=pdf_stub, page_index=page_index, chart_id="characteristic_curve",
        x_tick_regex=r"\d,\d", y_tick_regex=r"\d,\d\d",
        x_label="relative_log_exposure", y_label="density_diffuse_visual",
        curves=[CurveSpec("density", label_position_override=(270, 272))],
        film_id="_unused", extraction_method="vector_position",
        region_bbox=box, x_axis_calib_override=x_calib, y_axis_calib_override=y_calib,
        monotonic_direction="increasing", min_trace_points=8,
        metadata={"developer": "unspecified (gamma 0.65 reference)",
                  "curve_dimension": "single_representative_curve"},
    )

    return ProductSpec(
        brand="maco", product_name="IR820c / IR820c AURA", application_area="photography",
        film_type="negative", medium="bw", iso=100, year=2004,
        layer_order=["density"], source_pdf=pdf_stub, charts=[chart],
        digitizer_notes="B&W infrared film, single representative characteristic curve (gamma 0.65 "
                         "reference, per this sheet's own text) -- same single-curve template as most "
                         "Ilford B&W films. Tick text uses European comma decimals (\"0,3\"/\"3,00\"), "
                         "handled via a dedicated comma-tolerant axis fit (_comma_axis_calib) rather than "
                         "digitizer_core.fit_axis, which would silently reject every comma-decimal "
                         "candidate via its own float() call. This file's separate page-8 spectral-"
                         "sensitivity comparison diagram (vs. Kodak HIE/Konica/other MACO stocks) is a "
                         "raster JPEG, not vector, and not digitized -- see BLOCKED.md.",
    )


PRODUCTS = [
    maco_ir820c_product,
]


def main():
    run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)


if __name__ == "__main__":
    main()
