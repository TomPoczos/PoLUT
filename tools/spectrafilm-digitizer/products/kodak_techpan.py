"""
Kodak Technical Pan Film (2415/6415) -- Kodak's slowest, finest-grained B&W
still film, a variable-contrast panchromatic stock with extended red
sensitivity (uniform out to ~690nm, confirmed on its own digitized
Spectral-Sensitivity chart below -- the real physical trait behind its
famous "lightens red/flesh tones" darkroom reputation).

Source: papers/125pixcom/film/kodak/p255-2003_06.pdf (Kodak P-255, June
2003 -- the discontinuance-notice edition; confirmed to still carry every
chart this product needs, same as the two earlier P-255 editions also on
disk (2000_02, 2001_05) -- picked the most recent per this project's
never-mix-editions rule).

Ships exactly TWO real Characteristic-Curve brackets, deliberately narrower
than this datasheet's full 11-panel spread (an earlier version of this
product shipped all 11 -- DEKTOL, D-19, D-19 1:2, HC-110 Dil B/D/F, D-76,
VERSAMAT 885/641, DURAFLO RT -- see git history if any of the removed ones
are needed again):

- **KODAK TECHNIDOL Liquid** (page 10, 5/7/9/11min, Daylight 1/25 second)
  -- the one developer Kodak's own text calls out by name for pictorial use
  ("Technical Pan Film is Kodak's slowest and finest-grained black-and-white
  film for pictorial photography (when developed in KODAK TECHNIDOL Liquid
  Developer)"). Real Contrast Index AND Exposure Index come directly from a
  printed table on this panel (not a digitized inset curve) -- see
  tc.ci_from_table and EI_TABLE/the ANSI-speed cross-check below.
- **HC-110 Dilution B** (page 9, 4/6/8/12min, Daylight 1/25 second) -- the
  one other bracket on this datasheet that's both a real daylight exposure
  AND a real tank-development process (not a continuous machine line).

**Why the other nine were removed.** Six of this datasheet's eleven H&D
panels (DEKTOL, D-19, D-19 1:2, HC-110 Dil D, HC-110 Dil F, D-76) were shot
under Tungsten light, not Daylight -- irrelevant to a photographer shooting
real daylight scenes, which is this product's actual use case. The
remaining three (VERSAMAT 885, VERSAMAT 641, DURAFLO RT) are continuous
roller-transport machine-line processors, industrial lab equipment nobody
runs at home in a tank, not tank development -- also out of scope. Keeping
only the two real Daylight/tank-development brackets leaves a smaller but
honestly-scoped product: every stock this file ships represents a real
photographer's actual daylight/tank-development choice, not an artifact of
"we had the data so we shipped it."

**A related, genuinely separate issue this removal surfaces: reciprocity
failure.** Three of the six removed Tungsten brackets (D-19, D-19 1:2,
HC-110 Dil F) were tested at a full 1-SECOND exposure -- 25x longer than
the more typical 1/25s used elsewhere on this same datasheet. This
datasheet's own "Adjustments for Long and Short Exposures" table (page
index 2) states this film needs a real -10% development adjustment at 1
second (its stated "no adjustment needed" band is 1/100s to 1/10s only) --
meaning those three removed brackets' curves are measurably more contrasty
than what the same developer would give a real snapshot-duration exposure,
a confound independent of the tungsten-vs-daylight spectral question. The
same page also has a continuous "Changes in Speed and Contrast Due to
Long- and Short-Exposure Adjustments" graph (chart F002_0195AC, specific
to HC-110 Dilution D, 8 min -- but reciprocity is fundamentally an
exposure/latent-image property, not a developer one, and this is the one
reciprocity characterization this datasheet publishes for the whole film,
presented in the same file-wide "compensate for the reciprocity
characteristics of this film" framing as the coarse table) -- digitized
directly (not just read off the coarse table) to check the two brackets
THIS file actually keeps: at each one's own real 1/25s test exposure, the
real curve shows Speed Shift = +0.0098 log10 units and Contrast-Index
Shift = -0.0490 -- both negligible (the shallow near-zero region of the
curve, consistent with the coarse table's "None" entries bracketing 1/25s
between its 1/100s and 1/10s rows). Technidol and HC-110 Dilution B need
no reciprocity correction, confirmed against real digitized data, not
merely assumed from the coarse table's granularity.

Real, published Contrast Index per development time comes directly from a
printed table on the Technidol panel (not a separate CI-vs-time inset
graph digitized for its curve shape, though the panel also has one --
Kodak prints the exact numbers as text: 5min=0.48, 7min=0.58, 9min=0.64,
11min=0.70) -- see tc.ci_from_table's own docstring for why this is the
table equivalent of trix_common.py's real_ci_at, added as a shared,
reusable helper rather than one-off parsing local to this file. HC-110
Dilution B's own real CI/EI come from that panel's own dual-axis
(solid CONTRAST INDEX / dashed EXPOSURE INDEX) inset instead -- digitized
as two separate single-curve ChartSpec passes over the same region (see
_dual_inset()), each with its own y_tick_bbox isolating that curve's own
axis, because digitize_chart only supports one y-axis calibration per
chart and this is a real two-y-axis chart. Curve identity (which extracted
trace is the solid CI line vs. the dashed EI line) was confirmed via each
trace's own real stroke dash-pattern metadata (page.get_cdrawings()'s
"dashes" field -- unambiguous ground truth, not a position guess).

No stock gets a "(normal)" tag: Kodak's own text (page index 7, "Other
KODAK Developers" section) states plainly that Contrast Index "depends
primarily on the developer, temperature, dilution, and processing
technique," i.e. Kodak itself declines to name one universal "normal" CI
for HC-110 Dilution B, unlike Tri-X's own stated 0.56 starting-point
recommendation -- tc.ci_label(real_ci, target=None) is used throughout.
Technidol's own pictorial recommendation ("for pictorial applications, use
EI 25/15 degrees and process in KODAK TECHNIDOL Liquid Developer") maps to
EI 25 on the SAME published table for both the 9min AND 11min rows at
once, so no single development time there can honestly claim to be THE
normal/starting-point time either.

**Label-to-curve assignment: text-position matching is NOT reliable on
every panel and was not trusted blindly.** HC-110 Dilution B's four curves
were labeled using each curve's own real LEADER-LINE TOUCH POINT rather
than each text label's own bbox center --
`extract_traces_in_region(..., min_points=2)` surfaces the short
near-horizontal leader-line segments Kodak draws from each text label to
its own curve as their own tiny 2-point traces; the endpoint far from the
text (the one actually touching the curve) was matched against each
candidate H&D curve by direct point interpolation, confirmed to land
within a fraction of a point of the real curve, not a close-enough guess.
(This project's own removed D-19/D-19-1:2/HC-110-Dil-D/F/D-76 brackets are
where the failure mode that motivated this technique was first found --
see git history: HC-110 Dilution F's three curves came out cyclically
backwards using naive label-center matching, because that panel's curves
were tightly bunched. HC-110 Dilution B here was digitized with the
touch-point technique from the start and independently re-verified against
its own render_qa_overlay() output.)

Representative development time for HC-110 Dilution B's shared
exposure-axis anchor (REP_IDX -- see trix_common.py's fit_dev_times_parallel):
6 min, "middle-ish" of a 4-point bracket, absent a better anchor -- same
convention kodak_trix400tx.py's own T-MAX bracket uses. Technidol's own
REP_IDX=9min instead rests on a real citation: this datasheet's own Filter
Factor table footnote (page index 1) states "Based on a 1/25-second
exposure and development in KODAK TECHNIDOL Liquid Developer for 9 minutes
at 68 F (20 C)" -- Kodak's own real de facto reference condition for
Technidol-processed Tech Pan elsewhere in this same publication.

Spectral sensitivity (page index 8, "Spectral-Sensitivity Curves", chart
F002_0194AC) is digitized ONCE and reused by both brackets regardless of
developer -- log_sensitivity is a property of the film's own emulsion, not
the developer, exactly as kodak_trix400tx.py already reuses one
D-76-processed spectral curve across its D-76 AND T-MAX brackets. Two real
density criteria are plotted ("0.3 above D-min" and "1.0 above D-min"),
processed in KODAK HC-110 Developer (Dilution D) -- a third, different
developer than either H&D bracket above, not a mismatch to fix (see this
project's CLAUDE.md "exposure axis isn't cross-calibrated between two
charts" note). The "1.0 above D-min" criterion is used for consistency
with log_sensitivity_density_over_min=1.0, the same criterion every other
Kodak product in this project uses.

**Tri-X and T-Max were checked for the same reciprocity confound, found
clean.** Every Tri-X (TX/TXP/TXT) bracket is exposed at Daylight, 1/50
second -- inside Tri-X's own real published "no adjustment" band (its own
F-9 datasheet's reciprocity table, page index 1, brackets 1/100s and 1/10s
both "None"/"None"/"None"; 1/50s falls between them). T-Max 100's own H&D
charts don't state an exposure duration at all ("Exposure: Daylight", no
fraction given, per f4016_tmax_100-2018.pdf page index 7) -- but T-Max's
own reciprocity table (same file, page index 1) has an even WIDER
"no adjustment" band (1/1000s to 1/10s, Kodak's own "Improved reciprocity
at long and short exposure times" design claim for this film), and no
evidence points to an outlier test duration the way Tech Pan's own "1
second" tungsten brackets did. Neither product needed a code change.
"""

import types
from pathlib import Path

import numpy as np

import canonical_grids as grids
import density_model as dm
import exposure_calibration as ec
import trix_common as tc
from digitizer_core import ChartSpec, CurveSpec, digitize_chart
from kodak_helpers import overline_negative_calib, overline_symmetric_calib

PDF_PATH = Path("/home/tom/Pictures/LUTs/PoLUT/papers/125pixcom/film/kodak/p255-2003_06.pdf")
HERE = Path(__file__).parent.parent
OUT_ROOT = HERE / "outputs" / "film" / "bw" / "negative" / "kodak" / "kodak_techpan"

FILM_NAME_PREFIX = "Technical Pan (2415/6415)"
TARGET_PRINT = "kodak_polymax_fine_art_grade2"
N_LAYERS = 3

DATASOURCE = (
    "Kodak P-255 'KODAK PROFESSIONAL Technical Pan Film' datasheet, June 2003 "
    "(papers/125pixcom/film/kodak/p255-2003_06.pdf). Characteristic-Curve panels: "
    "page 10 top-left Technidol (F002_0193AC, incl. printed CI/EI table) and page 8 "
    "HC-110 Dilution B (F002_0185AC). Spectral-Sensitivity: page 9, '1.0 above D-min' "
    "trace, KODAK HC-110 Developer Dilution D, chart F002_0194AC. Reciprocity check: "
    "page 3, 'Adjustments for Long and Short Exposures' table and 'Changes in Speed "
    "and Contrast Due to Long- and Short-Exposure Adjustments' graph (F002_0195AC) -- "
    "confirmed negligible shift at both brackets' own 1/25s exposure, see module "
    "docstring. Digitized independently via this project's own tooling."
)


def _hd_chart(page_index, chart_id, region, curves, x_tick_regex=r"\d\.0", min_trace_points=150,
               metadata=None):
    """Shared shape for both Characteristic-Curve panels in this file -- only
    the region/labels/ticks differ; the overline-negative-tick fix (see
    kodak_helpers.py) is needed on both, same Kodak-era quirk as every other
    product in this project."""
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=page_index, chart_id=chart_id,
        x_tick_regex=x_tick_regex, y_tick_regex=r"\d\.0",
        x_label="log_exposure_relative", y_label="density_diffuse_visual",
        curves=curves,
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction="increasing", min_trace_points=min_trace_points,
        metadata=metadata or {},
    )
    chart.x_axis_calib_override = overline_negative_calib(PDF_PATH, page_index, region,
                                                            tick_regex=x_tick_regex)
    return chart


def _dual_inset(out_root, page_index, chart_id_prefix, region, x_tick_bbox, ci_y_tick_bbox,
                 ei_y_tick_bbox, ci_pos, ei_pos, monotonic="increasing", ci_y_tick_regex=r"\d\.\d\d"):
    """Digitizes a dual-axis (solid CONTRAST INDEX / dashed EXPOSURE INDEX)
    inset as two separate single-curve ChartSpec passes over the same
    region_bbox, each with its own y_tick_bbox isolating that curve's own
    axis -- see this module's own docstring for why (digitize_chart only
    fits one y-axis calibration per chart, but this is a real two-y-axis
    chart) and for how ci_pos/ei_pos (each curve's own real trace endpoint,
    not a legend-text guess) were found. Returns (ci_points, ei_points),
    each real (development_time_min, value) pairs. `out_root` is the
    calling bracket's own output dir (e.g. HC110B_OUT), not the module-wide
    OUT_ROOT -- this inset belongs to that one bracket, not the whole
    product, and lands flat in out_root/raw+qa (chart_id_prefix only
    disambiguates filenames, e.g. ci_ei_hc110b_CI_qa_overlay.png), the same
    convention _hd_chart's own H&D curve uses in the same out_root -- not
    its own extra subdirectory, which would split one bracket's QA across
    two places for no reason."""
    ci_chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=page_index, chart_id=f"{chart_id_prefix}_CI",
        x_tick_regex=r"^\d+$", y_tick_regex=ci_y_tick_regex,
        x_label="development_time_min", y_label="contrast_index",
        curves=[CurveSpec("CI", label_position_override=ci_pos)],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction=monotonic, min_trace_points=8,
        x_tick_bbox=x_tick_bbox, y_tick_bbox=ci_y_tick_bbox,
    )
    ci_result = digitize_chart(ci_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, ci_chart, ci_result, out_root)

    ei_chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=page_index, chart_id=f"{chart_id_prefix}_EI",
        x_tick_regex=r"^\d+$", y_tick_regex=r"^\d+$",
        x_label="development_time_min", y_label="exposure_index",
        curves=[CurveSpec("EI", label_position_override=ei_pos)],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction=monotonic, min_trace_points=8,
        x_tick_bbox=x_tick_bbox, y_tick_bbox=ei_y_tick_bbox,
    )
    ei_result = digitize_chart(ei_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, ei_chart, ei_result, out_root)

    return ci_result["curves"]["CI"]["points"], ei_result["curves"]["EI"]["points"]


def _spectral_sensitivity_chart():
    region = (320, 55, 580, 245)
    chart = ChartSpec(
        pdf=str(PDF_PATH), page_index=8, chart_id="spectral_sensitivity",
        x_tick_regex=r"\d{3}", y_tick_regex=r"\d\.0",
        x_label="wavelength_nm", y_label="log_sensitivity",
        curves=[
            CurveSpec("0.3+Dmin", label_position_override=(444.0, 128.0)),
            CurveSpec("1.0+Dmin", label_position_override=(461.0, 189.0)),
        ],
        film_id="_unused", region_bbox=region, extraction_method="vector_position",
        monotonic_direction=None, min_trace_points=12,
        metadata={"developer": "HC-110 (Dilution D)", "process": "8 min, 68F (20C)",
                  "densitometry": "Diffuse visual",
                  "effective_exposure": "1.4 sec visible, 0.2 sec ultraviolet",
                  "density_over_min": 1.0},
    )
    chart.y_axis_calib_override = overline_symmetric_calib(PDF_PATH, 8, region, tick_regex=r"\d\.0")
    return chart


def _fit_bracket(curves_by_dev, dev_times, rep_idx, label, qa_dir, title_prefix):
    rep_dev = dev_times[rep_idx]
    rep_points = curves_by_dev[rep_dev]
    rep_base = min(y for _, y in rep_points)
    x_speed_rep = tc.speed_point_x(rep_points, rep_base, criterion=1.0)
    shift = -x_speed_rep

    qa_dir.mkdir(parents=True, exist_ok=True)
    fits, xs_by_dev, ys_by_dev = tc.fit_dev_times_parallel(
        curves_by_dev, dev_times, shift, N_LAYERS, label,
    )
    for dev_t in dev_times:
        fit, _ = fits[dev_t]
        dm.plot_fit_qa(xs_by_dev[dev_t], ys_by_dev[dev_t], fit, grids.LOG_EXPOSURE,
                        title=f"{title_prefix} (net density, above base)",
                        out_path=qa_dir / f"density_fit_{label.lower().replace(' ', '')}_{dev_t:g}.png")
    return fits


# ---------------------------------------------------------------------------
# Technidol Liquid Developer -- 5/7/9/11 min, real CI+EI table (no inset digitize)
# ---------------------------------------------------------------------------

TECHNIDOL_OUT = OUT_ROOT / "technidol"
TECHNIDOL_DEV_TIMES = [5.0, 7.0, 9.0, 11.0]
TECHNIDOL_REP_IDX = 2  # 9 min -- Kodak's own real reference condition, see module docstring
TECHNIDOL_CI_TABLE = {5.0: 0.48, 7.0: 0.58, 9.0: 0.64, 11.0: 0.70}
TECHNIDOL_EI_TABLE = {5.0: 16, 7.0: 20, 9.0: 25, 11.0: 25}


def _technidol_hd_chart():
    region = (55, 15, 295, 245)
    return _hd_chart(
        10, "characteristic_curve_technidol", region,
        curves=[
            CurveSpec("5min", label_position_override=(219.9, 194.15)),
            CurveSpec("7min", label_position_override=(237.0, 181.55)),
            CurveSpec("9min", label_position_override=(183.65, 149.25)),
            CurveSpec("11min", label_position_override=(193.35, 138.45)),
        ],
        metadata={"developer": "KODAK TECHNIDOL Liquid", "process": "Small tank, 68F (20C)",
                  "densitometry": "Diffuse visual", "exposure": "Daylight, 1/25 second"},
    )


def _build_technidol(log_sensitivity):
    hd_chart = _technidol_hd_chart()
    hd_result = digitize_chart(hd_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, hd_chart, hd_result, TECHNIDOL_OUT)
    curves_by_dev = {float(t.replace("min", "")): hd_result["curves"][t]["points"]
                     for t in ("5min", "7min", "9min", "11min")}

    for dev_t in TECHNIDOL_DEV_TIMES:
        points = curves_by_dev[dev_t]
        base = min(y for _, y in points)
        ei_measured = tc.ansi_speed_ei(points, base)
        flag = " <- calibration anchor" if dev_t == TECHNIDOL_DEV_TIMES[TECHNIDOL_REP_IDX] else ""
        print(f"  Technidol {dev_t:g}min EI cross-check: measured={ei_measured:.1f} "
              f"published={TECHNIDOL_EI_TABLE[dev_t]}{flag}")

    fits = _fit_bracket(curves_by_dev, TECHNIDOL_DEV_TIMES, TECHNIDOL_REP_IDX, "Technidol",
                         TECHNIDOL_OUT / "qa", "Kodak Technical Pan, Technidol")

    written = {}
    for dev_t in TECHNIDOL_DEV_TIMES:
        fit, base_density = fits[dev_t]
        real_ci = tc.ci_from_table(TECHNIDOL_CI_TABLE, dev_t)
        stock = f"kodak_techpan_technidol_{tc.fmt_time_slug(dev_t)}"
        name = f"{FILM_NAME_PREFIX} — Technidol {tc.fmt_time(dev_t)}, {tc.ci_label(real_ci, target=None)}"
        source_profile, pack_profile, out_dir = tc.write_single_dev_time_stock(
            out_root=TECHNIDOL_OUT, stock=stock, name=name,
            target_print=TARGET_PRINT, densitometer="diffuse_visual",
            log_sensitivity_density_over_min=1.0, reference_illuminant="D55",
            viewing_illuminant="D50", datasource=DATASOURCE,
            wavelengths=grids.WAVELENGTHS_NM, log_sensitivity=log_sensitivity,
            log_exposure=grids.LOG_EXPOSURE, base_density_scalar=base_density,
            fit=fit, dev_time_min=dev_t,
        )
        print(f"  wrote {stock}: {name}  -> {out_dir}")
        written[stock] = (source_profile, pack_profile)
    return written


# ---------------------------------------------------------------------------
# HC-110 Dilution B -- 4/6/8/12 min
# ---------------------------------------------------------------------------

HC110B_OUT = OUT_ROOT / "hc110_dilb"
HC110B_DEV_TIMES = [4.0, 6.0, 8.0, 12.0]
HC110B_REP_IDX = 1  # 6min -- "middle-ish" of a 4-point bracket, same convention as TX/T-MAX


def _build_hc110b(log_sensitivity):
    hd_chart = _hd_chart(
        9, "characteristic_curve_hc110b", (325, 28, 560, 278),
        curves=[
            CurveSpec("4min", label_position_override=(477, 206.25)),
            CurveSpec("6min", label_position_override=(484, 195.25)),
            CurveSpec("8min", label_position_override=(489, 183.95)),
            CurveSpec("12min", label_position_override=(497, 173.15)),
        ],
        metadata={"developer": "KODAK HC-110 Developer (Dilution B)", "process": "Small tank, 68F (20C)",
                  "densitometry": "Diffuse visual", "exposure": "Daylight, 1/25 second"},
    )
    hd_result = digitize_chart(hd_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, hd_chart, hd_result, HC110B_OUT)
    curves_by_dev = {float(t.replace("min", "")): hd_result["curves"][t]["points"]
                     for t in ("4min", "6min", "8min", "12min")}

    ci_points, ei_points = _dual_inset(
        HC110B_OUT, 9, "ci_ei_hc110b", (355, 108, 445, 192), (365, 175, 425, 190),
        (355, 115, 385, 175), (420, 125, 445, 175),
        ci_pos=(421.4, 123.3), ei_pos=(421.3, 136.0),
    )

    fits = _fit_bracket(curves_by_dev, HC110B_DEV_TIMES, HC110B_REP_IDX, "HC-110B",
                         HC110B_OUT / "qa", "Kodak Technical Pan, HC-110 Dil B")

    written = {}
    for dev_t in HC110B_DEV_TIMES:
        fit, base_density = fits[dev_t]
        real_ci = tc.real_ci_at(ci_points, dev_t)
        stock = f"kodak_techpan_hc110b_{tc.fmt_time_slug(dev_t)}"
        name = (f"{FILM_NAME_PREFIX} — HC-110 (Dil B) {tc.fmt_time(dev_t)}, "
                f"{tc.ci_label(real_ci, target=None)}")
        source_profile, pack_profile, out_dir = tc.write_single_dev_time_stock(
            out_root=HC110B_OUT, stock=stock, name=name,
            target_print=TARGET_PRINT, densitometer="diffuse_visual",
            log_sensitivity_density_over_min=1.0, reference_illuminant="D55",
            viewing_illuminant="D50", datasource=DATASOURCE,
            wavelengths=grids.WAVELENGTHS_NM, log_sensitivity=log_sensitivity,
            log_exposure=grids.LOG_EXPOSURE, base_density_scalar=base_density,
            fit=fit, dev_time_min=dev_t,
        )
        print(f"  wrote {stock}: {name}  -> {out_dir}")
        written[stock] = (source_profile, pack_profile)
    return written


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

_BRACKET_BUILDERS = [_build_technidol, _build_hc110b]


def build_all():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    spec_chart = _spectral_sensitivity_chart()
    spec_result = digitize_chart(spec_chart, PDF_PATH)
    tc.write_raw_and_qa(PDF_PATH, spec_chart, spec_result, OUT_ROOT)
    sens_points = spec_result["curves"]["1.0+Dmin"]["points"]
    sens_x = np.array([p[0] for p in sens_points])
    sens_y = np.array([p[1] for p in sens_points])
    order = np.argsort(sens_x)
    sens_x, sens_y = sens_x[order], sens_y[order]
    log_sensitivity = np.interp(grids.WAVELENGTHS_NM, sens_x, sens_y)
    out_of_range = (grids.WAVELENGTHS_NM < sens_x.min()) | (grids.WAVELENGTHS_NM > sens_x.max())
    log_sensitivity[out_of_range] = np.nan
    log_sensitivity, sens_shift, grey_before = ec.calibrate_negative_film_log_sensitivity(
        log_sensitivity, grids.WAVELENGTHS_NM,
    )
    print(f"  log_sensitivity calibration: grey landed at log_raw={grey_before:.3f} before, "
          f"shifted by {sens_shift:+.3f} log10 ({sens_shift/np.log10(2):+.2f} stops) "
          f"to reach target {ec.GREY_TARGET_LOG_RAW}")

    written = {}
    for builder in _BRACKET_BUILDERS:
        written.update(builder(log_sensitivity))
    return written


_BUILT_CACHE = {}


def _build_one(stock):
    if not _BUILT_CACHE:
        _BUILT_CACHE.update(build_all())
    return _BUILT_CACHE[stock]


_STOCK_OUT_DIRS = {}
for _t in TECHNIDOL_DEV_TIMES:
    _STOCK_OUT_DIRS[f"kodak_techpan_technidol_{tc.fmt_time_slug(_t)}"] = TECHNIDOL_OUT
for _t in HC110B_DEV_TIMES:
    _STOCK_OUT_DIRS[f"kodak_techpan_hc110b_{tc.fmt_time_slug(_t)}"] = HC110B_OUT


def _make_entry(stock, out_dir):
    return types.SimpleNamespace(build=lambda: _build_one(stock), OUT_DIR=out_dir / stock)


PRODUCTS = {slug: _make_entry(slug, out_dir) for slug, out_dir in _STOCK_OUT_DIRS.items()}


if __name__ == "__main__":
    build_all()
