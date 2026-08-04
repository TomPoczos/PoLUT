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

# Global, hard-capped semaphore -- set by main.py (before it forks its own
# outer per-product-family pool -- see that module's docstring) to
# multiprocessing.Semaphore(cpu_count), shared by literal reference across
# every outer worker, every bracket, and every individual per-dev-time fit
# process this whole run spawns, at any nesting depth. `None` (the default,
# e.g. when a product's own `if __name__ == "__main__": build_all()` block
# runs this file standalone, outside main.py's dispatch) means "no cap
# exists to share" -- fall back to the old os.cpu_count() local-only
# behavior in fit_dev_times_parallel below.
#
# History: this used to be a plain int (INNER_WORKERS) computed once as
# cpu_count // len(jobs) before the outer pool was created, then a live
# multiprocessing.Value + Lock "budget" that callers borrowed from and gave
# back (INNER_BUDGET). Both were replaced (2026-08-04) after two real,
# measured failures:
#   1. A static split badly undersized every inner pool for the WHOLE run
#      just because len(jobs) happened to sit close to cpu_count, and
#      never adapted as sibling jobs of wildly different duration finished
#      -- confirmed directly: the last ~150s of a ~225s full build had only
#      2 of 11 outer jobs left, each still capped at budget=1, 10 of 12
#      cores idle the whole time.
#   2. The live Value+Lock version fixed #1, but its "floor of 1 no matter
#      how negative the counter already is" rule meant EVERY concurrent
#      claimant always got at least 1 worker regardless of true
#      availability -- fine with a handful of claimants, but the claimant
#      count is exactly "how many fit_dev_times_parallel calls happen to be
#      in flight at once," which grows every time a new multi-bracket film
#      or paper is added to this project. Nothing capped the TOTAL number
#      of simultaneously-running fit processes at cpu_count; it only capped
#      each individual claim's own size, so aggregate oversubscription (and
#      the wall-clock cost of the extra context-switching that comes with
#      it) would have kept getting worse as the catalog grows, not just
#      stayed at today's already-nonideal level. Trying to fix this by
#      fanning brackets out concurrently (so each claims a smaller slice at
#      once instead of taking turns) was tried and measured WORSE, not
#      better (162s vs. 149s for the live-budget-only baseline, on the same
#      catalog) -- more concurrent claimants against the same
#      floor-always-wins mechanism just means more, thinner, more
#      overhead-laden slices, not more real throughput.
#
# A real semaphore, acquired once per INDIVIDUAL fit task (inside _fit_one,
# which runs in the actual worker process, not by the caller sizing its own
# pool) rather than once per CALLER, fixes both: it's a hard physical limit
# on how many fits can be EXECUTING at once, GLOBALLY, full stop -- doesn't
# matter whether that's 5 callers or 50 as this project's catalog grows,
# peak concurrent CPU-bound work never exceeds cpu_count, because the OS
# itself won't hand out more than cpu_count semaphore permits at a time. A
# ProcessPoolExecutor can still be created with more workers than permits
# exist (harmless -- the extra worker processes just sit blocked on
# acquire(), consuming ~0 CPU while waiting, not competing for cores), so
# there's no need for any caller-side bookkeeping, borrowing, or giving
# back at all.
FIT_SEMAPHORE = None


def _fit_one(dev_t, xs, ys, n_layers):
    """Module-level (picklable) worker for ProcessPoolExecutor -- must stay
    top-level, not a closure/lambda, or it can't cross the process boundary.
    Acquires FIT_SEMAPHORE around the actual CPU-bound work (not around
    anything in the calling process) so the hard cap applies to work
    genuinely being computed right now, not to how many worker processes
    happen to exist."""
    if FIT_SEMAPHORE is not None:
        with FIT_SEMAPHORE:
            return dev_t, dm.fit_norm_cdfs(xs, ys, n_layers=n_layers)
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

    Pool size here is just a local cap on how many OS processes THIS call
    spins up (never more than it has dev_times for, never more than
    os.cpu_count() since more than that can never all be usefully active at
    once even project-wide) -- it does NOT need to coordinate with sibling
    calls the way the old INNER_BUDGET did, because FIT_SEMAPHORE (see that
    global's own comment) enforces the real, global, project-wide cap at
    the point each individual fit actually runs, not here.

    Returns {dev_t: (fit, base_density)}, same shape _fit_bracket's callers
    already expect."""
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

    workers = min(len(dev_times), max(1, os.cpu_count() or 4))

    fits = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_fit_one, dev_t, xs_by_dev[dev_t], ys_by_dev[dev_t], n_layers)
                   for dev_t in dev_times]
        for fut in futures:
            dev_t, fit = fut.result()
            fits[dev_t] = fit
            print(f"  {label} {dev_t:g} min: R^2={fit.r_squared:.5f} max_residual={fit.max_residual:.4f}")

    return {dev_t: (fits[dev_t], base_densities[dev_t]) for dev_t in dev_times}


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
