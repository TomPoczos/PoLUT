# Spectral upsampling research sources

Gathered while implementing Ticket 16
(`tasks/16-fixed-rgb-weights-no-spectral-reconstruction.md`): replacing
`generate_film_looks.py`'s fixed per-layer `_weights()`/`layer_weights()`
colour-to-exposure triples (which implicitly assume every photographed
colour is a linear-light mixture of the three RGB primaries' own spectral
power distributions) with a real per-pixel spectral reconstruction, so that
each colour film's real digitized spectral sensitivity curve is integrated
against a physically plausible reflectance spectrum instead of against the
display primaries themselves.

## Where this started

The pixls.us "spektrafilm tech discussions" thread
(<https://discuss.pixls.us/t/spektrafilm-tech-discussions/57512/8>, and
posts 1, 2, 6, 9, 11, 12), `arctic` and `hanatos` (spektrafilm/vkdt authors)
measuring metameric mismatch introduced by different spectral-upsampling
algorithms feeding real film sensitivity curves (including Portra 400, a
film this project also has real digitized data for). Their own algorithm
under discussion, `hanatos2025`, is unpublished, in-progress forum work with
no citable paper — Ticket 16 explicitly scoped implementation to its stable,
published, peer-reviewed predecessor instead:

- **jakob_hanika_2019_spectral_upsampling.pdf** — Wenzel Jakob & Johannes
  Hanika, "A Low-Dimensional Function Space for Efficient Spectral
  Upsampling," *Computer Graphics Forum* (Proc. Eurographics) 38(2), 147-155
  (2019). doi:10.1111/cgf.13626. Fetched from the author's own site
  (jo.dreggn.org/home/2019_sigmoid.pdf); this is the paper actually used, in
  full, not a secondary summary.

## Reference implementations studied

Two independent implementations of the same paper were cloned to
`~/code/` and read directly (not just their docs) to confirm this project's
understanding of the exact math before using either as a reference for
`tools/spectral_upsample_fit/`:

- **`~/code/rgb2spec`** (`git@github.com:mitsuba-renderer/rgb2spec.git`) —
  the paper authors' own canonical C++ implementation, used as-is by Mitsuba
  and PBRT. `rgb2spec_opt.cpp` (the offline fitter) confirmed: the sigmoid
  spectral model `R(lambda) = 1/2 + U/(2*sqrt(1+U^2))`, `U = c0*lambda^2 +
  c1*lambda + c2`; the CIELAB-error Levenberg-Marquardt solve; the
  non-linear `smoothstep(smoothstep(x))` lightness axis that concentrates
  table resolution near white/black where coefficients change fastest; and
  the "march outward from the middle lightness step, reusing the previous
  solution as the next starting guess" continuation trick that makes the
  fit tractable. `rgb2spec.c` (the runtime fetch/eval side) confirmed the
  "largest-channel-relative" gamut parameterization (`i_m` = index of the
  largest RGB component; the other two normalized by it) and the trilinear
  interpolation over a table indexed by `(channel, nonuniform-lightness,
  chroma, chroma)` — both reimplemented in pure Python (stdlib only) in
  `generate_film_looks.py`'s own consumption code, matched against this
  reference index-for-index.
- **`~/code/colour`** (`git@github.com:colour-science/colour.git`),
  specifically `colour/recovery/jakob2019.py` — a BSD-3-licensed, tested,
  independent Python/NumPy/SciPy port of the same paper (`sd_Jakob2019`,
  `find_coefficients_Jakob2019`, `LUT3D_Jakob2019`). Verified this matches
  the C++ reference's math exactly (same sigmoid formula, same
  dimensionless-to-wavelength-domain coefficient rescaling, same
  `smoothstep(smoothstep(...))` lightness scale) before choosing to build
  `tools/spectral_upsample_fit/` on top of this library rather than
  hand-porting the C++ Levenberg-Marquardt solver — using a maintained,
  independently-tested implementation of a subtle nonlinear solve is safer
  than a bespoke reimplementation of the fitting side, while the much
  simpler runtime lookup/eval side (no fitting, just interpolation +
  evaluating a closed-form sigmoid) is still reimplemented directly in
  `generate_film_looks.py` to keep that file scipy-free, exactly the
  precedent `tools/gamma_correction_fit/` already set for `*_SPLITGAUSS_FIT`.

Also present in `colour-science` but deliberately not used:
`colour/recovery/otsu2018.py` (the Otsu et al. 2018 PCA-based upsampler the
spektrafilm thread's post #12 explicitly found produces discontinuous
"solution domains" across the chromaticity plane, unlike Jakob-Hanika's
smooth sigmoid family) and `colour/recovery/mallett2019.py` (a different,
unrelated basis-function method, not discussed in the source thread and not
evaluated for this ticket).

## Why the fit uses this project's own CIE/D65/primary data, not colour-science's bundled datasets

`generate_film_looks.py` already hand-maintains its own CIE 1931 2-degree
observer + D65 tables (`CIE`/`D65` dicts, 400-700nm at 10nm) and its own
Adobe RGB (1998) / Rec.2020 primary matrices (`_MA_ADOBE`/`_MA_INV_ADOBE`,
`_MA_REC2020`/`_MA_INV_REC2020`), used by every other calculation in the
file (`_weights()`, `hk_mul()`, `_make_ssf()`). `tools/spectral_upsample_fit/
main.py` builds its `colour.MultiSpectralDistributions`/
`SpectralDistribution`/`RGB_Colourspace` objects directly from those same
dicts/matrices rather than from `colour.MSDS_CMFS`/`SDS_ILLUMINANTS`/
`RGB_COLOURSPACE_ADOBE_RGB1998` — otherwise the baked coefficient table
would be fit against a subtly different observer/illuminant/gamut than the
one `generate_film_looks.py` actually integrates each film's real sensitivity
curve over at runtime, reintroducing a small version of the exact kind of
illuminant/domain mismatch `GAMMA_CORRECT_TARGET`'s own v1-v4 history (see
`papers/masking_research/README.md`) already had to fix once.

## Table resolution and parallelization

The reference C++ tool and `colour-science`'s `LUT3D_Jakob2019.generate()`
both default to a 64^3 table (the published `.coeff` files Mitsuba/PBRT
ship). `tools/spectral_upsample_fit/main.py` uses a smaller size (16 by
default) — the sigmoid-coefficient manifold is low-frequency/smooth by the
paper's own construction (that smoothness is the entire point of the model,
per Jakob & Hanika's own motivation and the spektrafilm thread's explicit
observation that this family avoids "solution domain" discontinuities), so
a coarser grid still interpolates well; see `validate_table()` in that
tool for the actual measured round-trip Delta-E76 and grey-axis-flatness
checks run before a table is accepted, rather than assuming 16 is
sufficient. `colour-science`'s own `generate()` method fits one lightness
column (a full `size`-length march) at a time, serially — this project's
`main.py` reimplements the same per-column continuation logic but farms
each `(channel, chroma_j, chroma_k)` column out to a worker process via
`concurrent.futures.ProcessPoolExecutor`, since the fit is embarrassingly
parallel across columns and this is a one-time offline cost, not something
`generate_film_looks.py` ever re-runs.
