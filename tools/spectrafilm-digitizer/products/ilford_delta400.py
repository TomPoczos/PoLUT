"""
Ilford Delta 400 Professional, ISO 400/27, B&W still-camera negative film.

Source: papers/125pixcom/film/ilford/Delta_400-200209.pdf (Ilford "Fact
Sheet", September 2002) -- NOT the 2018 reprint (Delta-400_201811.pdf) the
same folder also has, which embeds every chart as a flattened raster image
(tick numbers included) and is a known dead end -- see
../curve_digitizer/BLOCKED.md's "Ilford film -- 2018+ reprints" entry and
ilford_common.py's own module docstring. Same real product/curve either
way; the 2002 sheet is just typeset as vector paths + (mostly) real text.

Same single-representative-curve template as ilford_hp5plus.py/
ilford_fp4plus.py: Delta 400's own Characteristic Curve panel is captioned
"DELTA 400 Professional 35mm film developed in ILFORD ID-11 stock for 8
minutes at 24C/75F with intermittent agitation." -- one developer, one
time, one temp, no Contrast-Index-vs-time bracket, so this ships as
exactly ONE darktable stock. Note the development temperature is 24C/75F,
NOT the 20C/68F every other film on this template (HP5 Plus, FP4 Plus,
Delta 100) uses for its own representative curve -- confirmed directly
from the datasheet's own caption text, not assumed from the other films'
convention; the sheet's ISO speed rating (a separate measurement) was
still taken at 20C/68F, same as the others, but the published
Characteristic Curve itself is the 24C/75F one.

Uses char_extraction="vector" (the default): per
../curve_digitizer/ilford_film.py's own module docstring and BLOCKED.md,
Delta 400's Characteristic Curve panel is real vector strokes, same as
HP5 Plus/FP4 Plus/Pan F Plus/XP2 Super -- Delta 100 is the only pre-2018
Ilford sheet confirmed to need raster tracing instead. Delta 400's tick
digits are vector-drawn glyphs with zero extractable text (confirmed via
curve_digitizer's own real-text-then-OCR-fallback path needing the OCR
branch on this file) -- characteristic_curve_chart()'s existing
try/except already covers this, no extra wiring needed here.

target_print is ilford_multigrade_iv_rc_grade2, a same-brand Ilford paper
(products/ilford_multigrade_iv_rc.py), same convention as every other
Ilford film product so far. Grade 2 picked as the "normal" contrast
default.
"""

from pathlib import Path

import ilford_common as ic

PDF_PATH = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom/film/ilford/Delta_400-200209.pdf")
HERE = Path(__file__).parent.parent
OUT_DIR = HERE / "outputs" / "film" / "bw" / "negative" / "ilford" / "ilford_delta400"

STOCK = "ilford_delta400"
NAME = "Ilford Delta 400 Professional — ID-11 stock, 8min, 24C"
TARGET_PRINT = "ilford_multigrade_iv_rc_grade2"
DEV_TIME_MIN = 8.0

DATASOURCE = (
    "Ilford 'Delta 400 Professional' Fact Sheet, September 2002 "
    "(papers/125pixcom/film/ilford/Delta_400-200209.pdf), page 6 "
    "'Characteristic Curve' (ILFORD ID-11 stock, 8min, 24C/75F, EI 400/27) "
    "and page 1 'Spectral Sensitivity' (wedge spectrogram to tungsten light, "
    "2850K). Digitized independently via this project's own tooling."
)


def build():
    """main.py's PRODUCTS interface expects build() -> (source_profile,
    pack_profile), a 2-tuple -- same convention as ilford_hp5plus.build()."""
    source_profile, pack_profile, _out_dir = ic.build_single_stock_bw_negative(
        pdf_path=PDF_PATH, char_page_index=5, spectral_page_index=0,
        stock=STOCK, name=NAME, target_print=TARGET_PRINT,
        dev_time_min=DEV_TIME_MIN, datasource=DATASOURCE, out_root=OUT_DIR,
    )
    return source_profile, pack_profile


if __name__ == "__main__":
    source_profile, pack_profile = build()
    print(f"wrote {STOCK} -> {OUT_DIR / STOCK}")
