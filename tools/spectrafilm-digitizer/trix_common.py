"""
Shared helpers for the Tri-X family products (kodak_trix400tx.py/_txp.py/_txt.py).

Ships every real, independently-digitized development time as its OWN
single-development-time darktable stock -- no development-time slider, no
collapse_to_darktable_pack() flattening of a real family down to one
representative value (contrast that against kodak_trix400.py's original
single-stock shape, which fit all of D-76's 7/9/11 min as one family and
shipped only the 9 min curve to darktable). Each stock's own
profile.spektrafilm.json and profile.darktable.json both carry
development_time=[t] (n_dev=1) from the start, so there is nothing for
collapse_to_darktable_pack() to flatten -- it still runs (every stock needs
the widen-to-3-columns step it also performs) but is a no-op on the family
axis here.

Every stock also carries its own real, Kodak-published Contrast Index
(digitized from that same datasheet's own Contrast-Index-vs-development-time
panel, not approximated from the H&D curve) in both its display name and
metadata. A "(normal)" tag is only attached when that stock's real CI lands
within 0.01 of Kodak's stated CI 0.56 "starting-point recommendation"
target -- never a synthesized or interpolated stops-of-push/pull number
(this datasheet only publishes a push-processing CI target, 0.72 @ 2-stop,
for TX; TXP/TXT have no push section at all, see kodak_trix400tx.py's own
module docstring). Don't add a push/pull label to any stock whose real CI
doesn't land on a Kodak-published anchor -- that would be exactly the
guesswork-dressed-as-science this family's whole design avoids.
"""

import json
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import fitz

import density_model as dm
import spektra_profile as sp
from digitizer_core import render_qa_overlay

NORMAL_CI_TARGET = 0.56
NORMAL_CI_TOLERANCE = 0.01


def speed_point_x(points, base_density, criterion=1.0):
    """Interpolate digitized (log_exposure, density) points to find the
    log_exposure at density = base_density + criterion."""
    xs = np.array([p[0] for p in points])
    ys = np.array([p[1] for p in points])
    order = np.argsort(ys)
    return float(np.interp(base_density + criterion, ys[order], xs[order]))


def _fit_one(dev_t, xs, ys, n_layers):
    """Module-level (picklable) worker for ProcessPoolExecutor -- must stay
    top-level, not a closure/lambda, or it can't cross the process boundary."""
    return dev_t, dm.fit_norm_cdfs(xs, ys, n_layers=n_layers)


def fit_dev_times_parallel(curves_by_dev, dev_times, shift, n_layers, label):
    """Fits every development time's own norm_cdfs model in a separate OS
    process (ProcessPoolExecutor, not threads -- this is CPU-bound
    scipy.optimize work with n_restarts=6 per curve that barely releases the
    GIL, so threads would just add scheduling overhead on top of fully
    serialized execution; same reasoning and same measured lesson as
    ../curve_digitizer/product.py's own run_products_parallel(), which
    found 8 threads SLOWER than sequential but ProcessPoolExecutor a real
    ~3.8x speedup on the same CPU-bound workload).

    Returns {dev_t: (fit, base_density)}, same shape _fit_bracket's callers
    already expect -- QA plotting stays in the calling (main) process
    afterward, not inside the worker, since matplotlib figure rendering
    across a process pool is extra complexity for a step that isn't the
    actual bottleneck here."""
    base_densities = {}
    xs_by_dev = {}
    ys_by_dev = {}
    for dev_t in dev_times:
        points = curves_by_dev[dev_t]
        xs = np.array([p[0] for p in points]) + shift
        ys_absolute = np.array([p[1] for p in points])
        base_density = float(ys_absolute.min())
        base_densities[dev_t] = base_density
        xs_by_dev[dev_t] = xs
        ys_by_dev[dev_t] = ys_absolute - base_density

    workers = min(len(dev_times), os.cpu_count() or 4)
    fits = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_fit_one, dev_t, xs_by_dev[dev_t], ys_by_dev[dev_t], n_layers)
                   for dev_t in dev_times]
        for fut in futures:
            dev_t, fit = fut.result()
            fits[dev_t] = fit
            print(f"  {label} {dev_t:g} min: R^2={fit.r_squared:.5f} max_residual={fit.max_residual:.4f}")

    return {dev_t: (fits[dev_t], base_densities[dev_t]) for dev_t in dev_times}, xs_by_dev, ys_by_dev


def write_raw_and_qa(pdf_path, chart, result, out_dir):
    out_dir_raw = out_dir / "raw"
    out_dir_qa = out_dir / "qa"
    out_dir_raw.mkdir(parents=True, exist_ok=True)
    out_dir_qa.mkdir(parents=True, exist_ok=True)

    qa_path = out_dir_qa / f"{chart.chart_id}_qa_overlay.png"
    doc = fitz.open(pdf_path)
    render_qa_overlay([(chart, result["_qa_results"], result["_qa_calib"], doc[chart.page_index])], qa_path)
    doc.close()

    raw_out = dict(result)
    raw_out["qa_overlay_png"] = qa_path.name
    for k in ("_qa_results", "_qa_calib", "_qa_page_number"):
        raw_out.pop(k, None)
    (out_dir_raw / f"{chart.chart_id}.json").write_text(json.dumps(raw_out, indent=2))
    return qa_path


def real_ci_at(ci_curve_points, dev_time_min):
    """Real Kodak-measured CI at dev_time_min, linearly interpolated between
    the digitized points of that developer's own real Contrast-Index-vs-time
    curve. Extrapolation (dev_time_min outside the digitized range) is
    clamped, not projected, by np.interp's own default -- flagged by the
    caller comparing dev_time_min against the curve's real min/max if that
    matters for a given stock."""
    pts = np.array(ci_curve_points)
    order = np.argsort(pts[:, 0])
    return float(np.interp(dev_time_min, pts[order, 0], pts[order, 1]))


def ci_label(real_ci):
    if abs(real_ci - NORMAL_CI_TARGET) <= NORMAL_CI_TOLERANCE:
        return f"CI {real_ci:.2f} (normal)"
    return f"CI {real_ci:.2f}"


def fmt_time(dev_time_min):
    """7.0 -> '7min', 6.25 -> '6.25min' -- used in both the stock slug
    (dot kept as 'p' there, see callers) and the human-readable name."""
    if dev_time_min == int(dev_time_min):
        return f"{int(dev_time_min)}min"
    return f"{dev_time_min:g}min"


def fmt_time_slug(dev_time_min):
    return fmt_time(dev_time_min).replace(".", "p")


def write_single_dev_time_stock(
    *, out_root, stock, name, target_print, densitometer,
    log_sensitivity_density_over_min, reference_illuminant, viewing_illuminant,
    datasource, wavelengths, log_sensitivity, log_exposure,
    base_density_scalar, fit, dev_time_min,
):
    """Writes one fully self-contained single-development-time stock
    (n_dev=1 from the start, not collapsed from a wider family) to
    out_root/<stock>/. `fit` is a density_model.NormCdfsFit already fit on
    this one development time's own net-density points (log_exposure grid
    is grids.LOG_EXPOSURE, the shared canonical grid)."""
    out_dir = out_root / stock
    out_dir.mkdir(parents=True, exist_ok=True)

    total = dm.evaluate_total(fit, log_exposure)                  # (256,)
    layers = dm.evaluate_layers(fit, log_exposure)                # (256,n_layers)
    density_curves = total[:, None]                               # (256,1)
    density_curves_layers = layers[:, :, None]                    # (256,n_layers,1)
    base_density = np.full((81, 1), base_density_scalar)
    density_curves_model = {
        "model_type": "norm_cdfs",
        "centers": fit.centers[None, :],
        "amplitudes": fit.amplitudes[None, :],
        "sigmas": fit.sigmas[None, :],
    }

    info = sp.build_info(
        stock=stock, name=name, type_="negative", support="film", stage="filming",
        use="still", antihalation="strong", target_print=target_print,
        channel_model="bw", densitometer=densitometer,
        log_sensitivity_density_over_min=log_sensitivity_density_over_min,
        reference_illuminant=reference_illuminant, viewing_illuminant=viewing_illuminant,
    )
    source_profile = sp.build_source_profile(
        info=info, datasource=datasource,
        wavelengths=wavelengths, log_sensitivity=log_sensitivity,
        channel_density_value=1.0, log_exposure=log_exposure,
        base_density=base_density, density_curves=density_curves,
        density_curves_layers=density_curves_layers,
        density_curves_model=density_curves_model, development_time=[dev_time_min],
    )
    sp.validate_source_profile(sp._json_safe(source_profile), n_dev_expected=1)
    sp.write_profile(out_dir / "profile.spektrafilm.json", source_profile)

    pack_profile = sp.collapse_to_darktable_pack(source_profile)
    sp.validate_darktable_pack(pack_profile)
    sp.write_profile(out_dir / "profile.darktable.json", pack_profile)

    return source_profile, pack_profile, out_dir
