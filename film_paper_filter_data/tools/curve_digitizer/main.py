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
"""

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np

HERE = Path(__file__).parent
DATA_ROOT = HERE.parent.parent  # film_paper_filter_data/
REPO_ROOT = DATA_ROOT.parent  # PoLUT/
PDF_DIR = REPO_ROOT / "papers"  # source datasheet PDFs live here, not in film_paper_filter_data


@dataclass
class CurveSpec:
    name: str
    fill_rgb: tuple[float, float, float]
    tol: float = 0.05


@dataclass
class ChartSpec:
    pdf: str
    page_index: int  # 0-based
    chart_id: str
    x_tick_regex: str  # regex a tick-label word must fully match
    y_tick_regex: str
    x_label: str
    y_label: str
    curves: list[CurveSpec]
    film_id: str  # output folder + filename prefix, e.g. "films/color/internegative/kodak_internegative_ii_5272"
    legend_bbox: tuple[float, float, float, float] | None = None  # x0,y0,x1,y1 to exclude
    n_bins: int = 400
    # "increasing"/"decreasing" if this chart is a real monotonic material curve
    # (e.g. density vs. exposure) and small digitization jitter should be
    # resolved by enforcing monotonicity, not preserved. None for charts like
    # spectral sensitivity where a peak/non-monotonic shape is physically real
    # and must NOT be flattened out.
    monotonic_direction: str | None = None


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
            CurveSpec("blue_yellow_forming_layer", (0.0, 0.0, 1.0)),
            CurveSpec("green_magenta_forming_layer", (0.5, 0.5, 0.0)),
            CurveSpec("red_cyan_forming_layer", (1.0, 0.0, 0.0)),
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
            CurveSpec("blue_yellow_forming_layer", (0.0, 0.0, 1.0)),
            CurveSpec("green_magenta_forming_layer", (0.5, 0.5, 0.0)),
            CurveSpec("red_cyan_forming_layer", (1.0, 0.0, 0.0)),
        ],
        film_id="films/color/internegative/kodak_internegative_ii_5272",
        legend_bbox=(150, 449, 253, 490),
    ),
]


def fit_axis(words, tick_regex, axis):
    """axis: 'x' or 'y'. Returns (slope, intercept) mapping pixel coordinate
    -> data value, fit by least squares over all tick labels matched by
    tick_regex (robust to any single mis-picked token)."""
    pixels, values = [], []
    for x0, y0, x1, y1, text, *_ in words:
        if not re.fullmatch(tick_regex, text):
            continue
        try:
            val = float(text)
        except ValueError:
            continue
        px = (x0 + x1) / 2 if axis == "x" else (y0 + y1) / 2
        pixels.append(px)
        values.append(val)
    if len(pixels) < 2:
        raise RuntimeError(f"only found {len(pixels)} tick labels matching {tick_regex!r}")
    slope, intercept = np.polyfit(pixels, values, 1)
    return slope, intercept, list(zip(pixels, values))


def in_bbox(pt, bbox):
    if bbox is None:
        return False
    x0, y0, x1, y1 = bbox
    return x0 <= pt.x <= x1 and y0 <= pt.y <= y1


def extract_curve_points(page, fill_rgb, tol, legend_bbox):
    pts = []
    for d in page.get_drawings():
        fill = d.get("fill")
        if fill is None or any(abs(fill[i] - fill_rgb[i]) > tol for i in range(3)):
            continue
        for item in d["items"]:
            for p in item[1:]:
                if hasattr(p, "x") and not in_bbox(p, legend_bbox):
                    pts.append((p.x, p.y))
    return pts


def isotonic_regression(ys, increasing=True):
    """Pool Adjacent Violators (PAVA): the closest (least-squares) monotonic
    sequence to ys. Used to remove digitization/binning jitter from a curve
    that is a real monotonic material property (H&D density-vs-exposure),
    rather than picking a `start` index to dodge it -- this fixes the whole
    curve, and unlike a `start` workaround, a subsequence of an isotonic
    sequence is still isotonic, so it survives RDP simplification afterward.
    """
    vals = [-v for v in ys] if not increasing else list(ys)
    stack_v, stack_c = [], []  # pooled block value, pooled block point-count
    for v in vals:
        cv, cc = v, 1
        while stack_v and stack_v[-1] > cv:
            pv, pc = stack_v.pop(), stack_c.pop()
            cv = (cv * cc + pv * pc) / (cc + pc)
            cc += pc
        stack_v.append(cv)
        stack_c.append(cc)
    out = []
    for v, c in zip(stack_v, stack_c):
        out.extend([v] * c)
    return [-v for v in out] if not increasing else out


def _perp_dist(p, a, b):
    """Perpendicular distance from point p to line a-b (all (x,y) tuples)."""
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def rdp(points, epsilon):
    """Ramer-Douglas-Peucker polyline simplification. points: list of (x,y)
    already in a normalized (comparable-scale) coordinate space."""
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    max_dist, index = -1.0, -1
    for i in range(1, len(points) - 1):
        d = _perp_dist(points[i], start, end)
        if d > max_dist:
            max_dist, index = d, i
    if max_dist > epsilon:
        left = rdp(points[:index + 1], epsilon)
        right = rdp(points[index:], epsilon)
        return left[:-1] + right
    return [start, end]


def simplify_to_target(xs, ys, target_lo=20, target_hi=30, max_iters=40):
    """Downsample a dense curve to ~target_lo..target_hi points via RDP,
    binary-searching epsilon (in axis-normalized units, so it behaves
    consistently regardless of the curve's actual x/y units/scale).

    This is what turns a smooth-but-noisy 400-point bin-averaged trace into
    the kind of sparse, shape-preserving point set every other curve in
    generate_film_looks.py already uses (~15-40 hand-picked points, denser
    at knees/toes/shoulders, sparse on straight runs) -- and, as a side
    effect, collapses small-scale digitization/binning jitter (which never
    exceeds any reasonable epsilon) into flat runs instead of scattering it
    across many near-duplicate points, which is what was causing spurious
    non-monotonic wobbles in the raw 400-point output.
    """
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    x_span = (x_hi - x_lo) or 1.0
    y_span = (y_hi - y_lo) or 1.0
    norm_pts = [((x - x_lo) / x_span, (y - y_lo) / y_span) for x, y in zip(xs, ys)]

    lo_eps, hi_eps = 1e-5, 0.2
    best = None
    for _ in range(max_iters):
        mid = (lo_eps + hi_eps) / 2
        simplified = rdp(norm_pts, mid)
        n = len(simplified)
        if target_lo <= n <= target_hi:
            best = simplified
            break
        if n > target_hi:
            lo_eps = mid
        else:
            hi_eps = mid
        best = simplified
    # denormalize back to real data coordinates
    out = [(nx * x_span + x_lo, ny * y_span + y_lo) for nx, ny in best]
    return out


def bin_average(xs, ys, n_bins):
    xs = np.array(xs)
    ys = np.array(ys)
    order = np.argsort(xs)
    xs, ys = xs[order], ys[order]
    edges = np.linspace(xs.min(), xs.max(), n_bins + 1)
    idx = np.clip(np.digitize(xs, edges) - 1, 0, n_bins - 1)
    out_x, out_y = [], []
    for b in range(n_bins):
        mask = idx == b
        if not mask.any():
            continue
        out_x.append(xs[mask].mean())
        out_y.append(ys[mask].mean())
    out_x, out_y = np.array(out_x), np.array(out_y)
    # fill any remaining gaps (dash-pattern holes) by linear interpolation
    # back onto a uniform grid spanning the same range
    full_x = np.linspace(out_x.min(), out_x.max(), n_bins)
    full_y = np.interp(full_x, out_x, out_y)
    return full_x, full_y


def render_qa_overlay(page, results, chart, out_path, calib):
    import matplotlib.pyplot as plt

    xs, xi, ys, yi = calib  # data = slope*pixel + intercept -> pixel = (data-intercept)/slope
    pix = page.get_pixmap(matrix=fitz.Matrix(4, 4))
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    fig, ax = plt.subplots(figsize=(pix.width / 200, pix.height / 200), dpi=200)
    ax.imshow(img)
    scale = 4.0  # matrix zoom factor above
    colors = {"blue_yellow_forming_layer": "cyan", "green_magenta_forming_layer": "lime",
              "red_cyan_forming_layer": "magenta"}
    for curve in chart.curves:
        if curve.name not in results:
            continue
        color = colors.get(curve.name, "yellow")
        px, py = results[curve.name]["_px"]
        ax.plot(np.array(px) * scale, np.array(py) * scale, "-", lw=0.5,
                color=color, alpha=0.35, label=f"{curve.name} (raw)")
        simp_x = [p[0] for p in results[curve.name]["points"]]
        simp_y = [p[1] for p in results[curve.name]["points"]]
        simp_px = [(x - xi) / xs for x in simp_x]
        simp_py = [(y - yi) / ys for y in simp_y]
        ax.plot(np.array(simp_px) * scale, np.array(simp_py) * scale, "-o", lw=1.2,
                ms=2.5, color=color, label=f"{curve.name} (simplified, n={len(simp_x)})")
    ax.legend(fontsize=6, loc="upper left")
    ax.axis("off")
    fig.tight_layout(pad=0)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def count_violations(ys, increasing):
    if increasing:
        return sum(1 for i in range(len(ys) - 1) if ys[i] > ys[i + 1])
    return sum(1 for i in range(len(ys) - 1) if ys[i] < ys[i + 1])


def digitize(chart: ChartSpec):
    prefix = DATA_ROOT / chart.film_id  # e.g. .../films/color/internegative/kodak_internegative_ii_5272
    out_dir = prefix.parent
    file_prefix = prefix.name
    doc = fitz.open(PDF_DIR / chart.pdf)
    page = doc[chart.page_index]
    words = page.get_text("words")

    xs, xi, x_ticks = fit_axis(words, chart.x_tick_regex, "x")
    ys, yi, y_ticks = fit_axis(words, chart.y_tick_regex, "y")

    results = {}
    for curve in chart.curves:
        raw = extract_curve_points(page, curve.fill_rgb, curve.tol, chart.legend_bbox)
        if not raw:
            print(f"  WARNING: no points found for {curve.name} (fill={curve.fill_rgb})")
            continue
        pxs, pys = zip(*raw)
        data_x = [xs * p + xi for p in pxs]
        data_y = [ys * p + yi for p in pys]
        bx, by = bin_average(data_x, data_y, chart.n_bins)
        if chart.monotonic_direction is not None:
            by = np.array(isotonic_regression(by, increasing=chart.monotonic_direction == "increasing"))
        simplified = simplify_to_target(bx, by)
        sx = [round(float(x), 4) for x, y in simplified]
        sy = [round(float(y), 4) for x, y in simplified]
        v_inc = count_violations(sy, increasing=True)
        v_dec = count_violations(sy, increasing=False)
        likely_dir = "increasing" if v_inc <= v_dec else "decreasing"
        n_violations = min(v_inc, v_dec)
        results[curve.name] = {
            "points": list(zip(sx, sy)),
            "points_dense": [[round(float(x), 4), round(float(y), 4)] for x, y in zip(bx, by)],
            "n_raw_vertices": len(raw),
            "n_violations": n_violations,
            "likely_direction": likely_dir,
            "_px": (pxs, pys),
        }
        print(f"  {curve.name}: {len(raw)} raw path vertices -> {len(bx)} dense -> "
              f"{len(sx)} simplified points, x range [{bx.min():.3f},{bx.max():.3f}] "
              f"y range [{by.min():.3f},{by.max():.3f}]  "
              f"monotonicity (assuming {likely_dir}): {n_violations} violation(s)")

    out_dir.mkdir(parents=True, exist_ok=True)
    qa_path = out_dir / f"{file_prefix}_{chart.chart_id}_qa_overlay.png"
    render_qa_overlay(page, results, chart, qa_path, calib=(xs, xi, ys, yi))

    out = {
        "source_pdf": chart.pdf,
        "page_index": chart.page_index,
        "chart_id": chart.chart_id,
        "x_label": chart.x_label,
        "y_label": chart.y_label,
        "x_axis_calibration": {"tick_matches": x_ticks, "fit_slope": xs, "fit_intercept": xi},
        "y_axis_calibration": {"tick_matches": y_ticks, "fit_slope": ys, "fit_intercept": yi},
        "curves": {k: {"points": v["points"], "points_dense": v["points_dense"],
                        "n_raw_vertices": v["n_raw_vertices"], "n_violations": v["n_violations"],
                        "likely_direction": v["likely_direction"]}
                   for k, v in results.items()},
        "qa_overlay_png": qa_path.name,
    }
    out_path = out_dir / f"{file_prefix}_{chart.chart_id}.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"  -> {out_path}")
    print(f"  -> {qa_path} (visual QA: extracted curve overlaid on rendered page)")


def main():
    for chart in CHARTS:
        print(f"[{chart.chart_id}] {chart.pdf} page {chart.page_index}")
        digitize(chart)


if __name__ == "__main__":
    main()
