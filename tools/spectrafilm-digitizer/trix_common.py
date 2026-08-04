"""
Shared helpers for the Tri-X family products (kodak_trix400tx.py/_txp.py/_txt.py).

Ships every real, independently-digitized development time as its OWN
single-development-time darktable stock -- no development-time slider, no
collapse_to_darktable_pack() flattening of a real family down to one
representative value (contrast that against kodak_trix400.py's original
single-stock shape, which fit all of D-76's 7/9/11 min as one family and
shipped only the 9 min curve to darktable). Each stock carries
development_time=[t] (n_dev=1) from the start, so there is nothing for
collapse_to_darktable_pack() to flatten on the family axis -- it still runs,
since every stock still needs its log_sensitivity/channel_density/
density_curves widened to 3 columns (still required unconditionally by
darktable's C reader, pack_format 2 or not -- see spektra_profile.py's
module docstring), it just no longer also widens density_curves_model
(unnecessary since darktable's pack-format-2 fix, same reference).
Only one file is written to disk per stock now (`profile.json`, the
collapsed+widened darktable-loadable shape) -- the pre-collapse
`build_source_profile()` shape is kept in memory only, as input to that
widening step and to the external spektrafilm-package validation round-trip.

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

The single-stock digitize/fit/write plumbing this module used to define
directly (`speed_point_x`, `write_raw_and_qa`, `write_single_dev_time_stock`)
moved to stock_io.py 2026-08 once Ilford (ilford_common.py) needed the exact
same shape with none of the Kodak-specific CI/development-time-family bits
below -- re-imported here so nothing in this file's own callers needs to
change.
"""

import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import density_model as dm
from stock_io import ansi_speed_ei, speed_point_x, write_raw_and_qa, write_single_dev_time_stock  # noqa: F401

NORMAL_CI_TARGET = 0.56
NORMAL_CI_TOLERANCE = 0.01

# Per-process worker budget for this module's OWN inner ProcessPoolExecutor,
# set by main.py (before it forks its own, outer per-product-family pool --
# see that module's docstring) to whatever's left of os.cpu_count() once the
# outer pool's own concurrency is accounted for, so the two pooling layers
# can never together oversubscribe the machine. `None` (the default, e.g.
# when a product's own `if __name__ == "__main__": build_all()` block runs
# this file standalone, outside main.py's dispatch) means "no outer pool
# exists to share the budget with" -- fall back to the old os.cpu_count()
# behavior in fit_dev_times_parallel below.
INNER_WORKERS = None


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

    Worker count is capped by module-global INNER_WORKERS when set (main.py's
    outer per-product-family pool sizes this to its own remaining CPU budget
    before dispatch -- see that global's own comment), else by plain
    os.cpu_count() for standalone/interactive use.

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

    budget = INNER_WORKERS if INNER_WORKERS is not None else (os.cpu_count() or 4)
    workers = min(len(dev_times), max(1, budget))
    fits = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_fit_one, dev_t, xs_by_dev[dev_t], ys_by_dev[dev_t], n_layers)
                   for dev_t in dev_times]
        for fut in futures:
            dev_t, fit = fut.result()
            fits[dev_t] = fit
            print(f"  {label} {dev_t:g} min: R^2={fit.r_squared:.5f} max_residual={fit.max_residual:.4f}")

    return {dev_t: (fits[dev_t], base_densities[dev_t]) for dev_t in dev_times}, xs_by_dev, ys_by_dev


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


def ci_label(real_ci, target=NORMAL_CI_TARGET, tolerance=NORMAL_CI_TOLERANCE):
    """`target`/`tolerance` default to Tri-X's own published 0.56 starting-
    point recommendation (every existing caller relies on this default and
    passes neither). Not every film has an unambiguous single published
    "normal" CI to check against -- Kodak Technical Pan's own datasheet
    only ties its EI 25 "pictorial" recommendation to two different
    development times at once (9 and 11 min both read EI 25 on that film's
    own real published table), so no single time can honestly claim the
    tag. Pass `target=None` in that situation to skip the check entirely
    rather than reusing a different film's own target by coincidence."""
    if target is not None and abs(real_ci - target) <= tolerance:
        return f"CI {real_ci:.2f} (normal)"
    return f"CI {real_ci:.2f}"


def ci_from_table(ci_table, dev_time_min):
    """Real Kodak-published CI at dev_time_min, read directly from a
    datasheet's own printed Contrast-Index table ({dev_time_min: ci}, real
    numbers transcribed as-is) -- the table equivalent of real_ci_at, for a
    datasheet that publishes exact CI values as text alongside its
    Characteristic-Curve chart instead of (or in addition to) a separate
    CI-vs-development-time inset chart (Kodak Technical Pan's own
    Technidol panel does this, see products/kodak_techpan.py). No
    interpolation, unlike real_ci_at -- a table only has the discrete
    times it was actually measured/published at, so a dev_time_min not
    present is a real error, not something to estimate."""
    if dev_time_min not in ci_table:
        raise KeyError(f"{dev_time_min} not in published CI table {sorted(ci_table)}")
    return float(ci_table[dev_time_min])


def fmt_time(dev_time_min):
    """7.0 -> '7min', 6.25 -> '6.25min' -- used in both the stock slug
    (dot kept as 'p' there, see callers) and the human-readable name."""
    if dev_time_min == int(dev_time_min):
        return f"{int(dev_time_min)}min"
    return f"{dev_time_min:g}min"


def fmt_time_slug(dev_time_min):
    return fmt_time(dev_time_min).replace(".", "p")
