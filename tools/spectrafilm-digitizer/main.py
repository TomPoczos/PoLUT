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
"""

import argparse

from products import (
    ilford_delta100,
    ilford_hp5plus,
    ilford_multigrade_iv_rc,
    kodak_polymax_fine_art,
    kodak_trix400tx,
    kodak_trix400txp,
    kodak_trix400txt,
)
import validate_external

PRODUCTS = {
    **kodak_trix400tx.PRODUCTS,
    **kodak_trix400txp.PRODUCTS,
    **kodak_trix400txt.PRODUCTS,
    **kodak_polymax_fine_art.PRODUCTS,
    **ilford_multigrade_iv_rc.PRODUCTS,
    ilford_hp5plus.STOCK: ilford_hp5plus,
    ilford_delta100.STOCK: ilford_delta100,
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", choices=sorted(PRODUCTS), default=None,
                     help="build only these stock slugs (default: all)")
    ap.add_argument("--skip-external-validation", action="store_true",
                     help="skip shelling out to ~/venv-spektrafilm-dev for the "
                          "pre-collapse source-profile authoritative check")
    args = ap.parse_args()

    stocks = args.only or sorted(PRODUCTS)
    for stock in stocks:
        module = PRODUCTS[stock]
        print(f"=== {stock} ===")
        source_profile, _pack_profile = module.build()

        if not args.skip_external_validation:
            report = validate_external.validate_spektrafilm_source_profile(source_profile)
            status = "OK" if report.get("ok") else "FAILED"
            print(f"  external validation (source profile, in-memory): {status} -- {report}")


if __name__ == "__main__":
    main()
