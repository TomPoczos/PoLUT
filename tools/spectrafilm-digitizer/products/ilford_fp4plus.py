"""
Ilford FP4 Plus, ISO 125/22, B&W still-camera negative film.

Source: papers/125pixcom/film/ilford/FP4+-200404.pdf (Ilford "Fact Sheet",
April 2004) -- NOT the 2018 reprint (FP4-Plus_201811.pdf) the same folder
also has, which embeds every chart as a flattened raster image (tick
numbers included) and is a known dead end -- see
../curve_digitizer/BLOCKED.md's "Ilford film -- 2018+ reprints" entry and
ilford_common.py's own module docstring. Same real product/curve either
way; the 2004 sheet is just typeset as vector paths + (mostly) real text.

Same single-representative-curve template as ilford_hp5plus.py: FP4 Plus's
own Characteristic Curve panel is captioned "FP4 Plus rollfilm developed in
ILFORD ILFOTEC HC (1+31) for 8 minutes at 20C/68F with intermittent
agitation. This curve is also representative of the 35mm and sheet film
formats." -- one developer, one time, one temp, no Contrast-Index-vs-time
bracket, so this ships as exactly ONE darktable stock, same as HP5 Plus.

Uses char_extraction="vector" (the default): per
../curve_digitizer/ilford_film.py's own module docstring and BLOCKED.md,
FP4 Plus's Characteristic Curve panel is real vector strokes, same as HP5
Plus/Delta 400/Pan F Plus/XP2 Super -- Delta 100 is the only pre-2018
Ilford sheet confirmed to need raster tracing instead. Confirmed here too
(page 3, char_extraction defaults through fine). Unlike HP5 Plus, FP4
Plus's tick digits are vector-drawn glyphs with zero extractable text
(confirmed via curve_digitizer's own real-text-then-OCR-fallback path
needing the OCR branch on this file) -- characteristic_curve_chart()'s
existing try/except already covers this, no extra wiring needed here.

target_print is ilford_multigrade_iv_rc_grade2, a same-brand Ilford paper
(products/ilford_multigrade_iv_rc.py), same convention as
ilford_hp5plus.py/ilford_delta100.py. Grade 2 picked as the "normal"
contrast default.
"""

from pathlib import Path

import ilford_common as ic

PDF_PATH = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom/film/ilford/FP4+-200404.pdf")
HERE = Path(__file__).parent.parent
OUT_DIR = HERE / "outputs" / "film" / "bw" / "negative" / "ilford" / "ilford_fp4plus"

STOCK = "ilford_fp4plus"
NAME = "Ilford FP4 Plus 125 — ILFOTEC HC (1+31), 8min, 20C"
TARGET_PRINT = "ilford_multigrade_iv_rc_grade2"
DEV_TIME_MIN = 8.0

DATASOURCE = (
    "Ilford 'FP4 Plus' Fact Sheet, April 2004 "
    "(papers/125pixcom/film/ilford/FP4+-200404.pdf), page 4 "
    "'Characteristic Curve' (ILFOTEC HC 1+31, 8min, 20C/68F, EI 125/22) "
    "and page 1 'Spectral Sensitivity' (wedge spectrogram to tungsten light, "
    "2850K). Digitized independently via this project's own tooling."
)


def build():
    """main.py's PRODUCTS interface expects build() -> (source_profile,
    pack_profile), a 2-tuple -- same convention as ilford_hp5plus.build()."""
    source_profile, pack_profile, _out_dir = ic.build_single_stock_bw_negative(
        pdf_path=PDF_PATH, char_page_index=3, spectral_page_index=0,
        stock=STOCK, name=NAME, target_print=TARGET_PRINT,
        dev_time_min=DEV_TIME_MIN, datasource=DATASOURCE, out_root=OUT_DIR,
    )
    return source_profile, pack_profile


if __name__ == "__main__":
    source_profile, pack_profile = build()
    print(f"wrote {STOCK} -> {OUT_DIR / STOCK}")
