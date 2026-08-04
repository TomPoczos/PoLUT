"""
Digitizes Kodak/etc. datasheets into darktable spektrafilm module profiles.

Usage:
    uv run main.py                          # build every product below
    uv run main.py --only kodak_trix400tx_d76_9min      # build one (or more) by stock slug
    uv run main.py --only kodak_polymax_fine_art_grade2 kodak_polymax_fine_art_grade3

Each product exposes build() -> (source_profile, pack_profile) and an OUT_DIR, following
products/kodak_trix400tx.py's pattern -- see that module's own docstring for the digitize ->
fit -> assemble -> write pipeline shape. Two module shapes are supported: a single-stock
module (build()/OUT_DIR at module level, one stock per file) and a multi-stock module for a
closely-related family sharing one source chart/pipeline (its own
PRODUCTS = {stock_slug: <has .build()/.OUT_DIR>} dict, merged in below --
kodak_polymax_fine_art.py's 7 print-paper grades; kodak_trix400tx.py/_txp.py/_txt.py's real
per-development-time Tri-X stocks, one PRODUCTS entry per real digitized development time,
no development-time slider -- see trix_common.py's own module docstring for why). Adding a
new single stock: write products/<new_stock>.py, add it to PRODUCTS below. Adding a new
family: follow kodak_polymax_fine_art.py's own shape and merge its PRODUCTS dict in the
same way.

Build parallelism: one OS process per FAMILY MODULE (not per stock slug) -- every multi-
stock module's PRODUCTS entries share one digitize+fit pass, cached at module-global scope
(e.g. kodak_trix400tx.py's `_BUILT_CACHE`, populated by whichever stock's .build() runs
first); running two stocks from the SAME family in two different processes would just redo
that shared pass twice, not actually parallelize anything real. The real independent unit
of work is the family module -- 11 of them for the full default build, a close-to-exact
match for a typical dev box's core count -- so that's what gets one process each here,
capped at os.cpu_count() so this can never oversubscribe. Confirmed by direct observation
that the previous fully-sequential main() (one product at a time, in one process) pegged a
single core throughout, with other cores spiking only briefly during a family's OWN inner
ProcessPoolExecutor call (trix_common.fit_dev_times_parallel) -- i.e. the family-module
loop itself, not any single product's own fitting step, was the real bottleneck.

trix_common.INNER_WORKERS is sized here (before the outer pool is created, so it's
inherited by every forked worker -- see that global's own comment) to whatever's left of
os.cpu_count() once the outer pool's own per-job share is accounted for, so the two
parallelism layers (this module's outer per-family pool, and fit_dev_times_parallel's own
inner per-development-time pool inside 5 of these families) can never together run more
OS processes than there are cores, not just each individually staying under the cap.
"""

import argparse
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

from products import (
    ilford_delta100,
    ilford_delta400,
    ilford_fp4plus,
    ilford_hp5plus,
    ilford_multigrade_iv_rc,
    kodak_polymax_fine_art,
    kodak_techpan,
    kodak_tmax100,
    kodak_trix400tx,
    kodak_trix400txp,
    kodak_trix400txt,
)
import trix_common
import validate_external

PRODUCTS = {
    **kodak_trix400tx.PRODUCTS,
    **kodak_trix400txp.PRODUCTS,
    **kodak_trix400txt.PRODUCTS,
    **kodak_tmax100.PRODUCTS,
    **kodak_techpan.PRODUCTS,
    **kodak_polymax_fine_art.PRODUCTS,
    **ilford_multigrade_iv_rc.PRODUCTS,
    ilford_hp5plus.STOCK: ilford_hp5plus,
    ilford_delta100.STOCK: ilford_delta100,
    ilford_fp4plus.STOCK: ilford_fp4plus,
    ilford_delta400.STOCK: ilford_delta400,
}
# Re-registered here (see products/ilford_delta100.py's own docstring):
# earlier in this session Delta 100 looked genuinely blocked -- its
# Characteristic Curve panel has zero vector paths on any available
# datasheet -- until raster_tracer.py's column-scan pixel tracer (ported
# from curve_digitizer/raster_tracer.py, built there for Fuji's bitonal
# scans) was extended here to handle this file's own real artifacts
# (anti-aliased, not byte-exact bitonal; minor tick-mark stubs off the
# frame border). ilford_common.build_single_stock_bw_negative's new
# char_extraction="raster" path is the reusable seam for any FUTURE film
# on this project whose Characteristic Curve panel turns out to be raster
# too -- check that first before assuming a new blocker needs its own
# bespoke pipeline.

# Multi-stock family modules: one shared digitize+fit pass per module,
# fanned out to every stock in its own PRODUCTS dict (see module docstring).
FAMILY_MODULES = [
    kodak_trix400tx, kodak_trix400txp, kodak_trix400txt,
    kodak_tmax100, kodak_techpan,
    kodak_polymax_fine_art, ilford_multigrade_iv_rc,
]
# Single-stock modules: build()/STOCK/OUT_DIR live at module level directly.
SINGLE_STOCK_MODULES = [ilford_hp5plus, ilford_delta100, ilford_fp4plus, ilford_delta400]

# Modules aren't picklable (vanilla pickle has no module-by-reference
# reduction, unlike classes/functions), so a submitted job can't just close
# over one -- pass its name instead and look it up here. Fork-based
# ProcessPoolExecutor (the Linux default this project relies on already,
# see trix_common.INNER_WORKERS) hands each worker a copy-on-write snapshot
# of this dict as it stands at fork time, which is after main() has already
# imported everything above, so every worker's lookup always hits.
_FAMILY_BY_NAME = {m.__name__: m for m in FAMILY_MODULES}
_SINGLE_BY_NAME = {m.__name__: m for m in SINGLE_STOCK_MODULES}


def _build_family(name):
    """Runs in its own worker process: builds every stock this family module
    owns in one shared digitize+fit pass (its own PRODUCTS dict already
    caches that pass at module-global scope -- see main.py's own docstring),
    returns {slug: (source_profile, pack_profile)} for all of them at once."""
    module = _FAMILY_BY_NAME[name]
    return {slug: entry.build() for slug, entry in module.PRODUCTS.items()}


def _build_single(name):
    module = _SINGLE_BY_NAME[name]
    return {module.STOCK: module.build()}


def _validate_one(stock, source_profile, skip):
    if skip:
        return stock, None
    return stock, validate_external.validate_spektrafilm_source_profile(source_profile)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", choices=sorted(PRODUCTS), default=None,
                     help="build only these stock slugs (default: all)")
    ap.add_argument("--skip-external-validation", action="store_true",
                     help="skip shelling out to ~/venv-spektrafilm-dev for the "
                          "pre-collapse source-profile authoritative check")
    args = ap.parse_args()

    requested = set(args.only) if args.only else set(PRODUCTS)

    jobs = []  # [(label, fn, module_name), ...]
    for module in FAMILY_MODULES:
        if requested & set(module.PRODUCTS):
            jobs.append((module.__name__, _build_family, module.__name__))
    for module in SINGLE_STOCK_MODULES:
        if module.STOCK in requested:
            jobs.append((module.__name__, _build_single, module.__name__))

    cpu_count = os.cpu_count() or 1
    outer_workers = min(len(jobs), cpu_count)
    # What's left of the machine's cores per outer job, for that job's own
    # inner ProcessPoolExecutor (trix_common.fit_dev_times_parallel) to use --
    # set before the outer pool is created so forked workers inherit it
    # (see trix_common.INNER_WORKERS's own comment). len(jobs)==1 (e.g. a
    # narrow --only within one family) correctly gets the whole machine.
    trix_common.INNER_WORKERS = max(1, cpu_count // max(1, len(jobs)))

    print(f"Building {len(jobs)} product famil{'y' if len(jobs) == 1 else 'ies'} "
          f"across {outer_workers} process{'es' if outer_workers != 1 else ''} "
          f"({cpu_count} CPUs, inner fit budget {trix_common.INNER_WORKERS}/job)")

    results = {}
    with ProcessPoolExecutor(max_workers=outer_workers) as ex:
        futures = {ex.submit(fn, module_name): label for label, fn, module_name in jobs}
        for fut in as_completed(futures):
            label = futures[fut]
            built = fut.result()
            results.update(built)
            print(f"=== {label}: built {len(built)} stock(s) ===")

    stocks = sorted(requested)
    validate_workers = min(len(stocks), cpu_count) or 1
    with ThreadPoolExecutor(max_workers=validate_workers) as ex:
        futures = [ex.submit(_validate_one, stock, results[stock][0], args.skip_external_validation)
                   for stock in stocks]
        for fut in as_completed(futures):
            stock, report = fut.result()
            if report is None:
                continue
            status = "OK" if report.get("ok") else "FAILED"
            print(f"  {stock} external validation (source profile, in-memory): {status} -- {report}")


if __name__ == "__main__":
    main()
