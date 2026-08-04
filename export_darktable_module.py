#!/usr/bin/env python3
"""Export all data needed by darktable's `filmemulation` IOP module -- a
live, native port of this project's cascade math (see darktable's own
plan/commit history for the module) -- into one consolidated JSON manifest.

This is a two-repo pipeline: this script (run here, in PoLUT, since it needs
to import generate_film_looks.py and tools/gamma_correction_fit/main.py
directly) produces the manifest; a separate generator in the darktable repo
turns the manifest into src/external/ static C arrays. Nothing in this
script writes into the darktable tree.

New physics performed here (mechanical, not new science): generate_film_looks.py
itself never gamma-corrects TRIX_DEV7, any Polymax grade, or
INTERNEGATIVE_II_CURVES -- those routes have no existing split-Gaussian fit,
because the offline .cube generator never needed a live/continuous gamma
target for them. darktable's gamma (punchiness) slider is meant to work the
same way (PoLUT's own Jones system-gamma mechanism) across every route,
including B&W and the reversal-internegative route, so this script fits
those three materials too -- reusing tools/gamma_correction_fit/main.py's own
already-validated fit_curve() unchanged, the identical procedure already
applied to the ~20 other materials in this project, not a new model.

Usage (needs numpy+scipy -- reuse tools/gamma_correction_fit's own venv):
  tools/gamma_correction_fit/.venv/bin/python3 export_darktable_module.py > /tmp/filmemulation_manifest.json
"""
import sys, os, json

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools", "gamma_correction_fit"))

import generate_film_looks as gfl  # noqa: E402
import main as fit_tool            # noqa: E402  (tools/gamma_correction_fit/main.py)


def curve_to_list(curve):
    xs, ys = gfl._sc(curve)
    return [[x, y] for x, y in zip(xs, ys)]


def sens_to_list(sens):
    ks = sorted(sens)
    return [[k, sens[k]] for k in ks]


_MIN_R2 = 0.98


def fit_and_report(name, curve):
    params, r2, maxres = fit_tool.fit_curve(curve)
    print(f"[fit] {name:34s} R2={r2:.5f}  max_resid={maxres:.4f}  "
          f"x0={params[0]:+.3f} d_lo={params[1]:.3f} d_hi={params[2]:.3f} "
          f"sig_lo={params[3]:.3f} sig_hi={params[4]:.3f}", file=sys.stderr)
    if r2 < _MIN_R2:
        raise SystemExit(f"fit quality too low for {name}: R2={r2:.5f} < {_MIN_R2}")
    return [float(v) for v in params]


manifest = {}

# ---------------------------------------------------------------------------
# Spectral upsampling coefficient table (Jakob & Hanika 2019). Adobe RGB
# only -- the darktable module always converts pipe RGB into Adobe RGB (the
# one reference gamut this table + every sensitivity/HK calculation below is
# defined against) before running the cascade, then converts back, exactly
# like lut3d.c already does for its "application color space" dropdown.
# ---------------------------------------------------------------------------
with open(os.path.join(_ROOT, "spectral_upsampling_tables", "adobergb.json")) as f:
    manifest["spectral_table"] = json.load(f)

manifest["wavelengths"] = list(gfl._SPECTRAL_WAVELENGTHS)
manifest["d65"] = [gfl.D65[wl] for wl in gfl._SPECTRAL_WAVELENGTHS]
manifest["grey"] = gfl.GREY
manifest["gamma_correct_target_default"] = gfl.GAMMA_CORRECT_TARGET
manifest["hk_max_mul"] = gfl.HK_MAX_MUL
manifest["adobergb_gamma"] = gfl._AG
manifest["adobergb_rgb2xyz"] = gfl._MA_INV_ADOBE

# ---------------------------------------------------------------------------
# B&W -- Tri-X 400 + Polymax paper grades 0-5 + 6 Wratten filters (including
# a "no filter" entry). New fits: TRIX_DEV7 and each Polymax grade.
# ---------------------------------------------------------------------------
manifest["trix"] = {
    "sensitivity": sens_to_list(gfl.TRIX_SENS),
    "curve": curve_to_list(gfl.TRIX_DEV7),
    "ref_d": gfl.TRIX_DEV7_REF_D,
    "fit": fit_and_report("TRIX_DEV7", gfl.TRIX_DEV7),
}

manifest["filters"] = {"NoFilter": None}
for name, transmission in gfl.FILTERS.items():
    manifest["filters"][name] = sens_to_list(transmission)

manifest["polymax_grades"] = {}
for name, grade in gfl.LOOKS:  # [("ExtraSoft","0"), ..., ("Hard","5")]
    curve = gfl.POLY[grade]
    manifest["polymax_grades"][name] = {
        "curve": curve_to_list(curve),
        "fit": fit_and_report(f"POLY[{grade}]({name})", curve),
    }

# ---------------------------------------------------------------------------
# EASTMAN Color Internegative II (the reversal internegative-route's middle
# stage). New fit here too, so the gamma slider works on that route.
# ---------------------------------------------------------------------------
manifest["internegative"] = {
    "sensitivity": [sens_to_list(s) for s in gfl.INTERNEGATIVE_II_SENS],
    "curves": [curve_to_list(c) for c in gfl.INTERNEGATIVE_II_CURVES],
    "lad_aim": list(gfl.INTERNEGATIVE_II_LAD_AIM),
    "fit": [fit_and_report(f"INTERNEGATIVE_II L{i}", c)
            for i, c in enumerate(gfl.INTERNEGATIVE_II_CURVES)],
}

# ---------------------------------------------------------------------------
# Reversal (slide) films -- own curve/sensitivity + already-existing
# SPLITGAUSS fit (used by the direct-print route; the internegative route
# uses the internegative's own fit above instead, per the project's own
# invariant that the internegative route is currently uncorrected in
# generate_film_looks.py -- darktable's live gamma slider applies its
# correction to whichever stage sits directly upstream of the paper, i.e.
# the internegative for that route, the film itself for the direct-print
# route).
# ---------------------------------------------------------------------------
_REVERSAL_FILMS = [
    ("velvia", "Velvia 50", gfl.VELVIA_SENS, gfl.VELVIA_CURVES, gfl.VELVIA_REF_D, gfl.VELVIA_SPLITGAUSS_FIT),
    ("kodachrome64", "Kodachrome 64", gfl.KODACHROME64_SENS, gfl.KODACHROME64_CURVES, gfl.KODACHROME64_REF_D, gfl.KODACHROME64_SPLITGAUSS_FIT),
    ("provia100f", "Fuji Provia 100F", gfl.PROVIA100F_SENS, gfl.PROVIA100F_CURVES, gfl.PROVIA100F_REF_D, gfl.PROVIA100F_SPLITGAUSS_FIT),
    ("ektachrome100d", "Kodak Ektachrome 100D", gfl.EKTACHROME100D_SENS, gfl.EKTACHROME100D_CURVES, gfl.EKTACHROME100D_REF_D, gfl.EKTACHROME100D_SPLITGAUSS_FIT),
]
manifest["reversal_films"] = {}
for key, label, sens, curves, refd, fit in _REVERSAL_FILMS:
    manifest["reversal_films"][key] = {
        "label": label,
        "sensitivity": [sens_to_list(s) for s in sens],
        "curves": [curve_to_list(c) for c in curves],
        "ref_d": list(refd),
        "fit": [[float(v) for v in row] for row in fit],
    }

# ---------------------------------------------------------------------------
# Direct-print papers (reversal, no internegative) -- real material names.
# ---------------------------------------------------------------------------
_DIRECT_PRINT_LABELS = {
    "RadianceIII": "Kodak Ektachrome Radiance III",
    "IlfochromeM": "Ilfochrome Micrographic M",
    "IlfochromeP": "Ilfochrome Micrographic P",
}
manifest["direct_print_papers"] = {}
for look in gfl.DIRECT_PRINT_LOOKS:
    manifest["direct_print_papers"][look] = {
        "label": _DIRECT_PRINT_LABELS[look],
        "curves": [curve_to_list(c) for c in gfl.DIRECT_PRINT_PAPERS[look]],
        "fit": [[float(v) for v in row] for row in gfl.DIRECT_PRINT_PAPER_FIT[look]],
    }

# ---------------------------------------------------------------------------
# 5-rung paper ladder (negative films + reversal internegative route) --
# real material names, NOT the ExtraSoft/Soft/.../ExtraPunchy look-names:
# those look-names describe contrast/punchiness, which is now the live gamma
# slider's job, so the UI must show the real paper instead (per explicit
# user instruction). The look-name is kept only as the internal lookup key.
# ---------------------------------------------------------------------------
_PAPER_LADDER_LABELS = {
    "ExtraSoft": "Fuji Crystal Archive Super Type C",
    "Soft": "Fuji Crystal Archive Pro PDII",
    "Normal": "Kodak Portra Endura",
    "Punchy": "Fuji Crystal Archive DPII",
    "ExtraPunchy": "Kodak Supra Endura",
}
manifest["paper_ladder"] = {}
for look in gfl.COLOR_LOOKS:
    manifest["paper_ladder"][look] = {
        "label": _PAPER_LADDER_LABELS[look],
        "curves": [curve_to_list(c) for c in gfl.PAPER_LADDER[look]],
        "fit": [[float(v) for v in row] for row in gfl.PAPER_LADDER_FIT[look]],
    }

# ---------------------------------------------------------------------------
# Camera color negative films.
# ---------------------------------------------------------------------------
_NEGATIVE_FILMS = [
    ("portra400", "Kodak Portra 400", gfl.PORTRA400_SENS, gfl.PORTRA400_CURVES, gfl.PORTRA400_REF_D, gfl.PORTRA400_SPLITGAUSS_FIT),
    ("ektar100", "Kodak Ektar 100", gfl.EKTAR100_SENS, gfl.EKTAR100_CURVES, gfl.EKTAR100_REF_D, gfl.EKTAR100_SPLITGAUSS_FIT),
    ("gold200", "Kodak Gold 200", gfl.GOLD200_SENS, gfl.GOLD200_CURVES, gfl.GOLD200_REF_D, gfl.GOLD200_SPLITGAUSS_FIT),
    ("ultramax400", "Kodak Ultramax 400", gfl.ULTRAMAX400_SENS, gfl.ULTRAMAX400_CURVES, gfl.ULTRAMAX400_REF_D, gfl.ULTRAMAX400_SPLITGAUSS_FIT),
    ("superiareala", "Fuji Superia Reala", gfl.SUPERIA_REALA_SENS, gfl.SUPERIA_REALA_CURVES, gfl.SUPERIA_REALA_REF_D, gfl.SUPERIA_REALA_SPLITGAUSS_FIT),
    ("superiaxtra400", "Fuji Superia X-tra 400", gfl.SUPERIA_XTRA400_SENS, gfl.SUPERIA_XTRA400_CURVES, gfl.SUPERIA_XTRA400_REF_D, gfl.SUPERIA_XTRA400_SPLITGAUSS_FIT),
]
manifest["negative_films"] = {}
for key, label, sens, curves, refd, fit in _NEGATIVE_FILMS:
    manifest["negative_films"][key] = {
        "label": label,
        "sensitivity": [sens_to_list(s) for s in sens],
        "curves": [curve_to_list(c) for c in curves],
        "ref_d": list(refd),
        "fit": [[float(v) for v in row] for row in fit],
    }

print(json.dumps(manifest), file=sys.stdout)

n_bw_fits = 1 + len(manifest["polymax_grades"]) + 3
print(f"\n[summary] materials fit fresh in this export: TRIX_DEV7 (1) + "
      f"Polymax grades (6) + internegative layers (3) = {n_bw_fits}", file=sys.stderr)
print(f"[summary] reversal films={len(manifest['reversal_films'])} "
      f"negative films={len(manifest['negative_films'])} "
      f"direct-print papers={len(manifest['direct_print_papers'])} "
      f"paper-ladder rungs={len(manifest['paper_ladder'])} "
      f"filters={len(manifest['filters'])}", file=sys.stderr)
