"""
Assembles one or more digitized charts (from digitizer_core.digitize_chart)
for a single film/paper product into the consolidated-data/ schema approved
in the plan, and writes the merged JSON + QA overlay PNGs to disk.

One ProductSpec = one film or paper product = one output JSON, holding every
chart type found for it (characteristic_curve/spectral_sensitivity/
reciprocity for film; one or more grade curves for paper) as named entries
under "charts", plus the brand/ISO/year/route metadata the raw
curve_digitizer/ChartSpec model doesn't carry on its own.
"""

import concurrent.futures
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz

from digitizer_core import ChartSpec, digitize_chart, render_qa_overlay

HERE = Path(__file__).parent
REPO_ROOT = HERE.parent.parent
CONSOLIDATED_ROOT = REPO_ROOT / "consolidated-data"
PDF_ROOT = REPO_ROOT / "papers" / "125pixcom"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


@dataclass
class ProductSpec:
    brand: str
    product_name: str
    application_area: str  # "photography" | "motion-picture"
    film_type: str  # "negative" | "reversal" | "intranegative" | "intrapositive" | "instant"
    medium: str  # "color" | "bw"
    iso: int | None
    year: int | str | None  # int, or "unknown-year"
    layer_order: list[str]
    source_pdf: str  # relative to PDF_ROOT
    charts: list[ChartSpec]
    print_route: str | None = None  # reversal film only: "direct-print"/"internegative"/"both"
    intrapositive_route: bool = False  # motion-picture only
    digitizer_notes: str = ""

    def filename_stem(self) -> str:
        parts = [self.brand, _slug(self.product_name)]
        if self.print_route:
            parts.append(self.print_route)
        if self.intrapositive_route:
            parts.append("via-intrapositive")
        parts.append(f"iso{self.iso}" if self.iso else "isounknown")
        parts.append(str(self.year) if self.year else "unknown-year")
        return "_".join(parts)

    def output_dir(self) -> Path:
        return CONSOLIDATED_ROOT / "film" / self.application_area / self.film_type / self.brand


@dataclass
class PaperProductSpec:
    brand: str
    paper_name: str
    paper_for: str  # e.g. "black-and-white", "direct-positive", "color-negative"
    year: int | str | None
    source_pdf: str
    charts: list[ChartSpec]
    digitizer_notes: str = ""

    def filename_stem(self) -> str:
        parts = [self.brand, _slug(self.paper_name), str(self.year) if self.year else "unknown-year"]
        return "_".join(parts)

    def output_dir(self) -> Path:
        return CONSOLIDATED_ROOT / "paper" / self.brand / self.paper_for


def _run_charts(charts, source_pdf, out_dir, stem):
    out_dir.mkdir(parents=True, exist_ok=True)
    charts_out = {}
    results_by_id = {}
    for chart in charts:
        # Each chart opens its OWN `chart.pdf` (not the product-level
        # `source_pdf`) -- almost always the same file (every ChartSpec
        # constructor sets `pdf=pdf_stub` to the product's one source), but
        # this lets one product mix panels from different source PDFs when
        # a panel's real data is only cleanly readable in an alternate/older
        # printing (confirmed needed 2026-07-06: T-Max 100's D-76 panel
        # renders as garbled "PL"/"Q" glyphs in the current f4016_TMax_100
        # -2016.pdf, but the same chart is fully readable in the older,
        # combined f4016-TMAX-2004.pdf).
        pdf_path = PDF_ROOT / chart.pdf
        result = digitize_chart(chart, pdf_path)
        results_by_id[chart.chart_id] = result
        charts_out[chart.chart_id] = {
            "page_index": result["page_index"],
            "x_label": result["x_label"],
            "y_label": result["y_label"],
            "x_axis_calibration": result["x_axis_calibration"],
            "y_axis_calibration": result["y_axis_calibration"],
            "curves": result["curves"],
            "qa_overlay_png": None,  # filled in below once the combined filename is known
        }
        if chart.metadata:
            charts_out[chart.chart_id]["metadata"] = chart.metadata

    if charts:
        # ONE combined overlay per PRODUCT (not per page): every chart belonging to this
        # product is drawn as its own subplot, cropped to just its own region -- never another
        # product's data, even when two products' charts share one PDF page (e.g. Kodak
        # Ektachrome E100G/E100GX's characteristic-curve panels sit on the same page but are
        # two separate products/JSON files) -- see render_qa_overlay's own docstring for the
        # full reasoning. Charts spanning multiple source pages/PDFs (e.g. an off-page
        # dye-density panel) all land in this same one image regardless.
        qa_path = out_dir / f"{stem}_qa_overlay.png"
        open_docs = {}
        chart_results = []
        for chart in charts:
            key = chart.pdf
            if key not in open_docs:
                open_docs[key] = fitz.open(PDF_ROOT / chart.pdf)
            page = open_docs[key][chart.page_index]
            chart_results.append((chart, results_by_id[chart.chart_id]["_qa_results"],
                                   results_by_id[chart.chart_id]["_qa_calib"], page))
        render_qa_overlay(chart_results, qa_path)
        for doc in open_docs.values():
            doc.close()
        for chart in charts:
            charts_out[chart.chart_id]["qa_overlay_png"] = qa_path.name

    return charts_out


def digitize_product(product: ProductSpec) -> Path:
    out_dir = product.output_dir()
    stem = product.filename_stem()
    charts_out = _run_charts(product.charts, product.source_pdf, out_dir, stem)

    doc_out = {
        "source_pdf": product.source_pdf,
        "brand": product.brand,
        "product_name": product.product_name,
        "application_area": product.application_area,
        "film_type": product.film_type,
        "medium": product.medium,
        "iso": product.iso,
        "year": product.year,
        "layer_order": product.layer_order,
        "extraction_method": product.charts[0].extraction_method if product.charts else None,
        "print_route": product.print_route,
        "intrapositive_route": product.intrapositive_route,
        "charts": charts_out,
        "digitizer_notes": product.digitizer_notes,
    }
    out_path = out_dir / f"{stem}.json"
    out_path.write_text(json.dumps(doc_out, indent=2))
    print(f"-> {out_path}")
    return out_path


def _run_product_by_index(module_name, index):
    # Runs in a fresh worker process -- re-imports the vendor script BY NAME
    # (not by pickling its PRODUCTS[index] factory directly) and pulls the
    # entry back out of its own PRODUCTS list there. This is the actual
    # reason `module_name` is threaded through run_products_parallel rather
    # than pickling `factories[index]` itself: PRODUCTS entries are lambdas/
    # closures (often nested, e.g.
    # add_push_panel(add_push_panel(portra_style_product(...)))), and lambdas
    # are never picklable -- pickle can only serialize a callable by
    # module+qualified-name reference, and a lambda's qualname is the
    # unresolvable `<lambda>`. A plain string+int pair sidesteps that
    # entirely. Re-importing by name (rather than relying on fork-inherited
    # parent state) also means this works correctly even if the interpreter
    # ever runs under "spawn" instead of Linux's default "fork".
    import importlib
    module = importlib.import_module(module_name)
    factory = module.PRODUCTS[index]
    product = factory()
    fn = digitize_paper if isinstance(product, PaperProductSpec) else digitize_product
    fn(product)
    name = getattr(product, "product_name", None) or getattr(product, "paper_name", None)
    print(f"[{name}] {product.source_pdf}")
    return name


def run_products_parallel(factories, module_name, max_workers=None):
    """Runs a vendor script's PRODUCTS list (each entry a zero-arg factory
    returning a ProductSpec or PaperProductSpec) across a process pool
    instead of a plain sequential for-loop. `module_name` must be the
    calling script's own importable module name, e.g.
    `run_products_parallel(PRODUCTS, module_name=Path(__file__).stem)`.

    Why processes, not threads: an earlier version of this used
    ThreadPoolExecutor (safe to do -- each factory() call opens its own
    fitz.Document, nothing here shares a PDF Document, ChartSpec, or
    matplotlib Figure across products; render_qa_overlay() was separately
    changed to build its Figure via the Figure/FigureCanvasAgg API directly
    rather than pyplot.subplots()/plt.close(), so it never touches
    matplotlib's shared global figure-manager registry). But measured
    wall-clock on kodak_still.py's then-44-product PRODUCTS list (clean
    start/end timestamps, not estimated) showed 8 threads made the full run
    SLOWER than plain sequential -- 683s threaded vs. 649s at
    max_workers=1 -- and `ps -o pcpu` on the running process during the
    threaded run showed only ~130% CPU, barely above one core out of 12
    available. This work (PyMuPDF drawing/text extraction, numpy
    binning/isotonic-regression/RDP simplification, per-chart QA-overlay
    rasterization) is CPU-bound and mostly pure Python/C-extension code that
    doesn't release the GIL enough for threads to actually run concurrently
    -- so ThreadPoolExecutor only added scheduling/lock overhead on top of
    fully-serialized execution. Real processes (own GIL each) are the only
    way to get genuine multi-core speedup for CPU-bound work in Python --
    this ProcessPoolExecutor version measured 171s on the same 44-product
    list at max_workers=8, a real ~3.8x speedup over the 649s sequential
    baseline, not just "no longer slower."

    This corpus has grown to 40-100+ products per vendor script, each its own
    independent PDF-parse + trace-extraction + QA-overlay-render pipeline
    that used to run one at a time (multi-minute full-script runs, idle CPU
    cores the whole time). One failing product also used to silently abort
    every product listed after it (an uncaught exception partway through the
    PRODUCTS list stopped the whole script, discovered the hard way when a
    T400CN page-layout bug during kodak_still.py's Spectral-Dye-Density
    rollout ate every product after it in list order) -- here, every
    product's exception is caught, collected, and reported together at the
    end instead, so one bad file no longer costs you the rest of the batch.
    """
    errors = []
    workers = max_workers or min(8, os.cpu_count() or 4)
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_run_product_by_index, module_name, i) for i in range(len(factories))]
        for fut in concurrent.futures.as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                errors.append(e)
                print(f"ERROR: {e!r}")
    if errors:
        raise RuntimeError(f"{len(errors)} product(s) failed -- see ERROR lines above")


def digitize_paper(product: PaperProductSpec) -> Path:
    out_dir = product.output_dir()
    stem = product.filename_stem()
    charts_out = _run_charts(product.charts, product.source_pdf, out_dir, stem)

    doc_out = {
        "source_pdf": product.source_pdf,
        "brand": product.brand,
        "paper_name": product.paper_name,
        "paper_for": product.paper_for,
        "year": product.year,
        "extraction_method": product.charts[0].extraction_method if product.charts else None,
        "charts": charts_out,
        "digitizer_notes": product.digitizer_notes,
    }
    out_path = out_dir / f"{stem}.json"
    out_path.write_text(json.dumps(doc_out, indent=2))
    print(f"-> {out_path}")
    return out_path
