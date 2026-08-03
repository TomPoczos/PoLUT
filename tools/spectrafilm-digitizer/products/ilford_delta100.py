"""
Ilford Delta 100 Professional, ISO 100/21, B&W still-camera negative film.

Source: papers/125pixcom/film/ilford/Delta_100-200209.pdf (Ilford "Fact
Sheet", September 2002) -- NOT the 2018 reprint (Delta-100_201811.pdf) the
same folder also has, which is explicitly named in
../curve_digitizer/BLOCKED.md's "Ilford film -- 2018+ reprints" entry
(confirmed here too: 3/1/0/3/0/0 embedded raster images across its 6 pages,
vs. 0 on every page of this 2002 sheet).

Same single-representative-curve template as ilford_hp5plus.py: Delta 100's
own Characteristic Curve panel is captioned "100 DELTA Professional rollfilm
developed in ILFORD ID-11 stock for 8 1/2 minutes at 20C/68F with
intermittent agitation. This curve is also representative of the 35mm and
sheet film formats." -- one developer, one time, one temp, no
Contrast-Index-vs-time bracket, so this ships as exactly ONE darktable
stock, same as HP5 Plus.

UNLIKE HP5 Plus (and unlike every other film on this template --
curve_digitizer/ilford_film.py confirms FP4 Plus/Pan F Plus/Delta 400/XP2
Super all use real vector strokes), Delta 100's Characteristic Curve panel
on BOTH the 2002 and 2018 sheets is an embedded RASTER image with zero
vector paths -- confirmed via page.get_drawings()/get_cdrawings() (only the
white background fill and page border overlap the panel region) and
page.get_images() (a DeviceGray Image XObject whose placement rect matches
the panel exactly). This is a real, pre-existing, independently-documented
blocker: curve_digitizer/ilford_film.py already found and excluded this
same file for the same reason (see its own comment above the Delta 400
entry in its PRODUCTS list). Digitized here via
ilford_common.characteristic_curve_points_raster() (char_extraction="raster"
below) -- raster_tracer.py's column-scan pixel tracer, ported from
curve_digitizer/raster_tracer.py (built there for Fuji's bitonal CCITT
scans) and extended for this file's own two real artifacts: an
anti-aliased (not byte-exact bitonal) grayscale render, and minor
unlabeled tick-mark stubs projecting inward from the frame border that
briefly corrupted the traced toe/shoulder before being filtered -- see
raster_tracer.py's own module docstring for the full story. The Spectral
Sensitivity chart (page 0) is real vector data and uses the normal
char_extraction="vector" path on its own -- confirmed independently, not
assumed from the Characteristic Curve panel's own raster status (this
project's own experience already shows a chart's vector-vs-raster/
OCR-vs-real-text properties are per-panel, not a single blanket per-file
property).

target_print reuses kodak_polymax_fine_art_grade2, same cross-brand
reasoning as ilford_hp5plus.py (no same-brand Ilford paper built for this
schema yet).
"""

from pathlib import Path

import ilford_common as ic

PDF_PATH = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom/film/ilford/Delta_100-200209.pdf")
HERE = Path(__file__).parent.parent
OUT_DIR = HERE / "outputs" / "film" / "bw" / "negative" / "ilford" / "ilford_delta100"

STOCK = "ilford_delta100"
NAME = "Ilford Delta 100 Professional — ID-11 stock, 8.5min, 20C"
TARGET_PRINT = "kodak_polymax_fine_art_grade2"
DEV_TIME_MIN = 8.5

DATASOURCE = (
    "Ilford '100 Delta Professional' Fact Sheet, September 2002 "
    "(papers/125pixcom/film/ilford/Delta_100-200209.pdf), page 4 "
    "'Characteristic Curve' (ID-11 stock, 8.5min, 20C/68F, EI 100/21) -- "
    "an embedded raster image, digitized via raster_tracer.py's column-scan "
    "pixel tracer, not vector-path extraction -- "
    "and page 1 'Spectral Sensitivity' (wedge spectrogram to tungsten light, "
    "2850K, real vector paths). Digitized independently via this project's "
    "own tooling."
)


def build():
    """main.py's PRODUCTS interface expects build() -> (source_profile,
    pack_profile), a 2-tuple -- same convention as ilford_hp5plus.build()."""
    source_profile, pack_profile, _out_dir = ic.build_single_stock_bw_negative(
        pdf_path=PDF_PATH, char_page_index=3, spectral_page_index=0,
        stock=STOCK, name=NAME, target_print=TARGET_PRINT,
        dev_time_min=DEV_TIME_MIN, datasource=DATASOURCE, out_root=OUT_DIR,
        char_extraction="raster",
    )
    return source_profile, pack_profile


if __name__ == "__main__":
    source_profile, pack_profile = build()
    print(f"wrote {STOCK} -> {OUT_DIR / STOCK}")
