"""
Ilford HP5 Plus, ISO 400/27, B&W still-camera negative film.

Source: papers/125pixcom/film/ilford/HP5+-200407.pdf (Ilford "Fact Sheet",
July 2004) -- NOT the 2018 reprint (HP5-Plus_201811.pdf) the same folder
also has, which embeds every chart as a flattened raster image (tick
numbers included) and is a known dead end -- see
../curve_digitizer/BLOCKED.md's "Ilford film -- 2018+ reprints" entry and
ilford_common.py's own module docstring. Same real product/curve either
way; the 2004 sheet is just typeset as vector paths + (mostly) real text.

Ships as exactly ONE darktable stock, not a development-time family:
Ilford's own datasheet publishes exactly one representative Characteristic
Curve -- "HP5 Plus 35mm film developed in ILFORD ILFOTEC HC (1+31) for 6.5
minutes at 20C/68F... also representative of the rollfilm and sheet film
formats" -- and no Contrast-Index-vs-time chart at all, unlike every Kodak
B&W sheet this tool has handled so far. There is no bracket to build a
family from; see ilford_common.py's own module docstring for the full
comparison.

target_print is ilford_multigrade_iv_rc_grade2, a same-brand Ilford paper
(products/ilford_multigrade_iv_rc.py) -- replaces the earlier cross-brand
kodak_polymax_fine_art_grade2 placeholder (cross-brand pairing had real
precedent, e.g. Tri-X itself still uses it, but a same-brand pairing is
strictly better once one exists). Grade 2 picked as the "normal" contrast
default, same convention kodak_polymax_fine_art_grade2 used for Tri-X.
"""

from pathlib import Path

import ilford_common as ic

PDF_PATH = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom/film/ilford/HP5+-200407.pdf")
HERE = Path(__file__).parent.parent
OUT_DIR = HERE / "outputs" / "film" / "bw" / "negative" / "ilford" / "ilford_hp5plus"

STOCK = "ilford_hp5plus"
NAME = "Ilford HP5 Plus 400 — ILFOTEC HC (1+31), 6.5min, 20C"
TARGET_PRINT = "ilford_multigrade_iv_rc_grade2"
DEV_TIME_MIN = 6.5

DATASOURCE = (
    "Ilford 'HP5 Plus' Fact Sheet, July 2004 "
    "(papers/125pixcom/film/ilford/HP5+-200407.pdf), page 5 "
    "'Characteristic Curves' (ILFOTEC HC 1+31, 6.5min, 20C/68F, EI 400/27) "
    "and page 1 'Spectral Sensitivity' (wedge spectrogram to tungsten light, "
    "2850K). Digitized independently via this project's own tooling."
)


def build():
    """main.py's PRODUCTS interface expects build() -> (source_profile,
    pack_profile), a 2-tuple -- trims the out_dir that
    stock_io.write_single_dev_time_stock also returns (same convention as
    every kodak_trix400tx.py/_txp.py/_txt.py stock's own written[stock])."""
    source_profile, pack_profile, _out_dir = ic.build_single_stock_bw_negative(
        pdf_path=PDF_PATH, char_page_index=4, spectral_page_index=0,
        stock=STOCK, name=NAME, target_print=TARGET_PRINT,
        dev_time_min=DEV_TIME_MIN, datasource=DATASOURCE, out_root=OUT_DIR,
    )
    return source_profile, pack_profile


if __name__ == "__main__":
    source_profile, pack_profile = build()
    print(f"wrote {STOCK} -> {OUT_DIR / STOCK}")
