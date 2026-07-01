# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-script generator that produces 84 physically-grounded film-emulation 3D LUTs (`.cube` files) for Kodak Tri-X 400 (B&W) and Fuji Velvia 50 (color reversal), intended to replace a raw processor's tone mapper (AgX/filmic/sigmoid) entirely rather than sit downstream of it. See README.md for the full darkroom/color-science rationale, data provenance, and known limitations — that context is not repeated here.

## Commands

```
python generate_film_looks.py                  # regenerate all 84 LUTs at 65^3
python generate_film_looks.py --size 33         # smaller/faster grid for iteration
python generate_film_looks.py --only trix       # regenerate only trix_classic/ + trix_modern/
python generate_film_looks.py --only velvia     # regenerate only velvia_classic/ + velvia_modern/
```

No dependencies beyond the Python 3 standard library (`argparse`, `math`, `os`, `time`). No build step, no test suite, no linter configured — the only "check" is running the generator and confirming it completes without error and diffing/regenerating the output `.cube` files.

The generated `.cube` files under `trix_classic/`, `trix_modern/`, `velvia_classic/`, `velvia_modern/` are committed to git as build artifacts. **After changing any film data or algorithm in `generate_film_looks.py`, regenerate all 84 files and commit them alongside the script change** — don't let the script and the checked-in LUTs drift apart.

## Architecture

Everything lives in `generate_film_looks.py`, structured as one straight pipeline, top to bottom:

1. **Spectral/colorimetric constants** — CIE 1931 2° observer + D65 illuminant tables (`CIE`, `D65`), Adobe RGB primary matrices (`_MA`/`_MA_INV`) and gamma (`_AG`), CIELAB helpers (`_lf`/`_lfi`) feeding `hk_mul()`, the Helmholtz-Kohlrausch exposure-multiplier function (Fairchild & Pirrotta 1991).
2. **Film datasets** — hardcoded digitized curves: `TRIX_SENS`/`TRIX_DEV7` (Kodak Tri-X spectral sensitivity + 7-min dev H&D curve), `POLY` (Polymax Fine-Art paper grades 0–5), `VELVIA_SENS`/`VELVIA_CURVES` (3 independent dye-layer sensitivities + characteristic curves), `FILTERS` (Wratten filter spectral transmission %). These are the ground-truth inputs; treat them as data, not something to "clean up."
3. **Weight computation** — `_weights()` integrates a sensitivity curve (optionally through a Wratten filter) against D65 and the Adobe RGB primary matrix to get an (R,G,B)→exposure weight triple. Tri-X gets one weight triple per filter; Velvia gets one per dye layer via `velvia_layer_weights()`.
4. **Cascade builders** — `_find_anchor()` is the shared "find x where curve y crosses a target density" search both builders use to locate 18% grey: it scans from the well-behaved (non-solarized) end of the curve, clamps to the nearest endpoint if the target density falls outside the digitized range, and raises if the curve isn't monotonic in the region scanned before the crossing rather than silently picking a wrong segment. `build_trix_cascade()` composes the negative curve with a paper grade into a single exposure→reflectance transfer function (anchored so 18% grey lands correctly) using `_find_anchor()` on the non-decreasing print density curve. `build_velvia_layer()` does the equivalent for one reversal dye layer via `_find_anchor()` on its non-increasing density curve, plus a parametric contrast (`VELVIA_GAMMA`) since no real multi-grade reversal print data exists.
5. **LUT writers** — `write_bw_lut()` combines color→exposure via **geometric mean** (`R^wr * G^wg * B^wb`, i.e. log-density-space mixing — physically correct for how film responds to light, and only valid on linear scene-referred data) with optional HK correction, then the Tri-X cascade, writing an achromatic `.cube`. `write_color_lut()` computes each Velvia dye layer's exposure via **arithmetic** weighted sum instead (each layer responds to a narrow spectral band, so geometric cross-channel suppression doesn't apply), then applies each layer's own reversal transfer function to produce RGB output.
6. **`main()`** — parses `--size`/`--output`/`--only`, iterates the classic (no HK) vs modern (HK) variant × filter × look combinations, and writes into the four output directories.

Key invariants to preserve when editing:
- Input/output color space is always Adobe RGB (gamma-encoded in the `.cube`, decoded to linear internally via `adec`/`aenc`). This is deliberate (see README "Why Adobe RGB") — don't switch to sRGB primaries.
- Geometric mean for Tri-X/B&W, arithmetic mean for Velvia's per-layer exposure — these are not interchangeable; the README's "Density-space geometric mean" section explains why each is physically correct for its case.
- `GREY = 0.18` is the anchor point every transfer function is normalized around; both cascade builders search their curve data for the log-exposure that reproduces 18% output via `_find_anchor()`. Several digitized curves are non-monotonic near their tails (Polymax grades 0/1 dip near Dmax; all three Velvia dye layers solarize past their minimum density) — harmless today because the target density sits well before those wobbles, but `_find_anchor()` will raise instead of silently mis-anchoring if new/edited curve data ever puts a non-monotonic wobble before the target crossing.
- `HK_MAX_MUL = 3.0` bounds `hk_mul()`'s exposure multiplier. The Fairchild & Pirrotta (1991) HK formula has no built-in ceiling and was only validated against real Munsell chips (`C*` roughly 6–87); wide-gamut Adobe RGB scene data can reach `C* ≈ 136` and would otherwise extrapolate into 6–7× multipliers on saturated shadows/midtones. See README "Helmholtz-Kohlrausch correction" for how 3.0 was derived from the paper's own measured data. Don't remove or raise this clamp without re-deriving it against the source data.
- File naming (`TriX_<Filter>_<Look>.cube`, `Velvia50_<Look>.cube`) and the `LOOKS`/`FILTER_ORDER` ordering are consumed by nothing else in-repo, but changing them changes the committed output filenames — coordinate with README's file listing if you do.
