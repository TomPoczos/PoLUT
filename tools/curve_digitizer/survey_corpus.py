"""
Scans a folder of manufacturer PDF datasheets and reports, per file, whether
it contains a real digitizable characteristic-curve / spectral-sensitivity /
reciprocity chart -- and if so, on which page(s), whether that chart is drawn
as vector paths or an embedded raster image, and what color-fill/stroke
clusters exist on that page (the raw material for authoring a ChartSpec).

This narrows several hundred PDFs down to a manifest of real candidates
before any ChartSpec gets hand-authored -- it does NOT auto-author
ChartSpecs, since legend position and exact curve-discriminator values still
vary file to file even within one vendor.

Usage:
    uv run survey_corpus.py [root_dir] [--out manifest.json]
Default root_dir is ../../papers/125pixcom relative to this file.
"""

import argparse
import json
import re
from pathlib import Path

import fitz  # PyMuPDF

HERE = Path(__file__).parent
REPO_ROOT = HERE.parent.parent
DEFAULT_ROOT = REPO_ROOT / "papers" / "125pixcom"

# English + German keywords for the 3 chart types this project cares about.
KEYWORDS = {
    "characteristic_curve": [
        "characteristic curve", "d-log e", "d log e", "sensitometric curve",
        "density vs", "kennlinie", "schwärzungskurve", "gradation",
    ],
    "spectral_sensitivity": [
        "spectral sensitivity", "spektrale empfindlichkeit", "spectral empfindlichkeit",
    ],
    "reciprocity": [
        "reciprocity", "reziprozität", "reziprozitat",
    ],
}

ISO_RE = re.compile(r"\b(?:ISO|EI|DIN)\s*[/\s]?\s*(\d{1,5})\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19[3-9]\d|20[0-3]\d)\b")


def classify_page_text(text: str) -> list[str]:
    low = text.lower()
    hits = []
    for chart_id, kws in KEYWORDS.items():
        if any(kw in low for kw in kws):
            hits.append(chart_id)
    return hits


def sample_colors(page, kind="fill", limit=8):
    seen = []
    for d in page.get_drawings():
        val = d.get(kind)
        if val is None:
            continue
        rounded = tuple(round(v, 2) for v in val)
        if rounded not in seen:
            seen.append(rounded)
        if len(seen) >= limit:
            break
    return seen


def sample_dash_widths(page, limit=8):
    seen = []
    for d in page.get_drawings():
        if d.get("color") is None:
            continue
        key = (d.get("dashes"), round(d.get("width") or 0, 2))
        if key not in seen:
            seen.append(key)
        if len(seen) >= limit:
            break
    return seen


def survey_pdf(path: Path, root: Path) -> dict:
    rel = str(path.relative_to(root))
    entry = {
        "file": rel,
        "vendor_folder": path.parts[len(root.parts)] if len(path.parts) > len(root.parts) else None,
        "candidate": False,
        "pages": [],
        "iso_candidates": [],
        "year_candidates": [],
        "product_name_guess": path.stem,
        "error": None,
    }
    try:
        doc = fitz.open(path)
    except Exception as e:  # noqa: BLE001 -- survey must not crash on a bad PDF
        entry["error"] = f"open failed: {e}"
        return entry

    all_text = []
    try:
        for i, page in enumerate(doc):
            text = page.get_text()
            all_text.append(text)
            hits = classify_page_text(text)
            if not hits:
                continue
            drawings = page.get_drawings()
            images = page.get_images(full=True)
            n_fill_colors = len({tuple(round(v, 2) for v in d["fill"]) for d in drawings if d.get("fill")})
            n_stroke_colors = len({tuple(round(v, 2) for v in d["color"]) for d in drawings if d.get("color")})
            page_entry = {
                "page_index": i,
                "chart_types": hits,
                "n_drawings": len(drawings),
                "n_images": len(images),
                "n_distinct_fill_colors": n_fill_colors,
                "n_distinct_stroke_colors": n_stroke_colors,
                "sample_fill_colors": sample_colors(page, "fill"),
                "sample_stroke_dash_widths": sample_dash_widths(page),
                "likely_vector": len(drawings) > 5,
                "likely_raster_chart": len(images) > 0 and len(drawings) <= 5,
            }
            entry["pages"].append(page_entry)
    finally:
        doc.close()

    entry["candidate"] = len(entry["pages"]) > 0
    full_text = "\n".join(all_text)
    entry["iso_candidates"] = sorted({int(m) for m in ISO_RE.findall(full_text)})
    entry["year_candidates"] = sorted({int(m) for m in YEAR_RE.findall(full_text)})
    if not entry["candidate"]:
        entry["reason"] = "no characteristic-curve/spectral-sensitivity/reciprocity keyword found on any page"
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=str(DEFAULT_ROOT))
    ap.add_argument("--out", default=str(HERE / "corpus_manifest.json"))
    ap.add_argument("--glob", default="**/*.pdf")
    args = ap.parse_args()

    root = Path(args.root)
    pdfs = sorted(root.glob(args.glob))
    print(f"scanning {len(pdfs)} PDFs under {root} ...")
    results = []
    for i, pdf in enumerate(pdfs):
        entry = survey_pdf(pdf, root)
        results.append(entry)
        status = "CANDIDATE" if entry["candidate"] else "skip"
        print(f"[{i+1}/{len(pdfs)}] {status:9s} {entry['file']}")

    n_candidates = sum(1 for r in results if r["candidate"])
    print(f"\n{n_candidates}/{len(pdfs)} files have at least one candidate chart page")

    out_path = Path(args.out)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"-> {out_path}")


if __name__ == "__main__":
    main()
