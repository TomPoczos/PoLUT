"""
Digitizes Kodak/etc. datasheets into darktable spektrafilm module profiles.

Usage:
    uv run main.py                          # build every product below
    uv run main.py --only kodak_trix400      # build one (or more) by stock slug
    uv run main.py --only kodak_polymax_fine_art_grade2 kodak_polymax_fine_art_grade3

Each product exposes build() -> (source_profile, pack_profile) and an OUT_DIR, following
products/kodak_trix400.py's pattern -- see that module's own docstring for the digitize ->
fit -> assemble -> write pipeline shape. Two module shapes are supported: a single-stock
module (build()/OUT_DIR at module level, one stock per file -- kodak_trix400.py) and a
multi-stock module for a closely-related family sharing one source chart/pipeline (its own
PRODUCTS = {stock_slug: <has .build()/.OUT_DIR>} dict, merged in below --
kodak_polymax_fine_art.py's 7 print-paper grades). Adding a new single stock: write
products/<new_stock>.py, add it to PRODUCTS below. Adding a new family: follow
kodak_polymax_fine_art.py's own shape and merge its PRODUCTS dict in the same way.
"""

import argparse

from products import kodak_polymax_fine_art, kodak_trix400
import validate_external

PRODUCTS = {
    "kodak_trix400": kodak_trix400,
    **kodak_polymax_fine_art.PRODUCTS,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", choices=sorted(PRODUCTS), default=None,
                     help="build only these stock slugs (default: all)")
    ap.add_argument("--skip-external-validation", action="store_true",
                     help="skip shelling out to ~/venv-spektrafilm-dev for the "
                          "profile.spektrafilm.json authoritative check")
    args = ap.parse_args()

    stocks = args.only or sorted(PRODUCTS)
    for stock in stocks:
        module = PRODUCTS[stock]
        print(f"=== {stock} ===")
        module.build()

        if not args.skip_external_validation:
            profile_path = module.OUT_DIR / "profile.spektrafilm.json"
            report = validate_external.validate_spektrafilm_source_externally(profile_path)
            status = "OK" if report.get("ok") else "FAILED"
            print(f"  external validation ({profile_path.name}): {status} -- {report}")


if __name__ == "__main__":
    main()
