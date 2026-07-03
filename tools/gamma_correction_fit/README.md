# gamma-correction-fit

Fits a real, physically-motivated model to each reversal film's and each
direct-print paper's digitized H&D curve (already in `generate_film_looks.py`),
then derives the Jones-corrected reversal-film curve analytically from that
fit. Produces the `*_SPLITGAUSS_FIT` constants and the
`gamma_correct_curve()`/`_split_gauss_*` functions in `generate_film_looks.py`
-- this tool is how those numbers were produced, not something
`generate_film_looks.py` runs at generation time (it stays scipy-free; see
"Why generate_film_looks.py doesn't need scipy" below).

## Why fit a model at all

Two earlier mechanisms were tried directly on the real digitized curve
points and both measurably failed real-world use: rescaling the whole curve
by one scalar over-flattens the toe/shoulder (they're already lower-gamma
than the straight line, so scaling them down *again* by the same factor
starves the print of shadow density reach); rescaling only inside an
arbitrarily-thresholded "straight-line window" fixed that but left local
gamma near grey running 20-40% hotter than the target average, with an
abrupt, physically meaningless kink at the window boundary. See
`generate_film_looks.py`'s own `GAMMA_CORRECT_TARGET` comment block for the
full history (v1-v4) and the measured numbers for each.

## Why this particular model

The physical origin of the H&D curve's toe/straight-line/shoulder shape is
well established in sensitometry: an emulsion is a population of individual
silver-halide grains, each becoming developable once its own quantum catch
crosses its own threshold, and that population has a real, measured spread
of individual grain sensitivities -- J.H. Webb, "Graphical Analysis of
Photographic Exposure and a New Theoretical Formulation of the H and D
Curve," *J. Opt. Soc. Am.* 29, 314-326 (1939), derives the H&D curve from
exactly this picture (primary source paywalled during this research; the
reported finding that Webb's own equation "cannot be integrated
mathematically" is itself consistent with a cumulative-Gaussian origin,
whose integral has no elementary closed form either). The curve's value at
any exposure is therefore a *cumulative distribution* of how many grains
have crossed threshold by that exposure. The standard idealization of a
threshold-crossing process over a population with a roughly log-normal
sensitivity spread is a cumulative Gaussian (normal) distribution plotted
against log exposure.

`split_gaussian_cdf()` fits an *asymmetric* version of that (independent
`sigma_lo`/`sigma_hi` either side of the inflection `x0`), because the toe
and shoulder are, physically, governed by different mechanisms -- grain-
threshold statistics near Dmin, dye/silver exhaustion near Dmax -- with no
reason to share a width, and real emulsions are visibly not symmetric
toe-to-shoulder.

Also used, unchanged, to fit the 6 camera negative films (Portra 400, Ektar
100, Gold 200, Ultramax 400, Superia Reala, Superia X-tra 400) and the 5
`PAPER_LADDER` papers they print onto (`generate_film_looks.py`'s
`NEGATIVE_FILMS`/`_negative_gammacorrect_stage_fn()`) -- added after
real-world use showed negative films rendering *punchier* than the
freshly-corrected reversal films, backwards from the real photographic
hierarchy. Root cause, measured with this same tool: negative films' own
native gamma is correctly low (0.47-0.68), but `PAPER_LADDER`'s own real
gammas run steep (2.5-4.3 across all 5 papers) and had never been checked
against Jones's rule. Same model, same mechanism, `increasing=True` on both
stages instead of `False` (a camera negative and a real print paper both
have density *rising* with exposure, unlike a reversal dye layer).

## What it does

1. `fit_curve()` least-squares fits `split_gaussian_cdf` (via
   `scipy.optimize.curve_fit`) to each reversal/negative film's and each
   direct-print/`PAPER_LADDER` paper's own real digitized curves (3 layers
   each, imported directly from `generate_film_looks.py`). Fit quality is
   checked, not assumed: R² and max residual are printed for every layer
   (all 21 reversal-side layers fit at R² > 0.998, max residual < 0.07
   density units; all 33 negative-side layers at R² > 0.995, max residual
   < 0.1, as of the version these constants were transcribed from).
2. `local_gamma()` is the model's exact analytic derivative (a normal PDF --
   no finite-difference approximation).
3. `stretch_corrected_curve()` rescales the fitted film model's exposure
   axis only, around the film's own real reference-density pivot, by
   whatever factor makes the model's own exact local gamma at the pivot,
   times the paper's own fitted local gamma at its real grey-reproduction
   point, equal `GAMMA_CORRECT_TARGET`. Every fitted density value is kept
   exactly as the model computes it (so the model's own real fitted
   Dmin/Dmax are reached, not truncated) -- only exposure positions are
   relabeled, which is what "lower gamma" physically means (the same
   density change now needs more exposure), and preserves the fitted
   curve's real toe/shoulder shape exactly (a pure horizontal rescale
   can't change relative proportions).
4. `main()` prints fit quality for every layer, then the corrected-curve
   check (grey holds at 0.18, the density reached at the practical floor
   against each paper's own fitted real Dmax -- shortfall is under 0.06
   density units, i.e. well under a tenth of a stop, on every one of the 36
   film x paper x layer combinations checked).

## Why generate_film_looks.py doesn't need scipy

`_norm_cdf()`/`_norm_pdf()` in `generate_film_looks.py` reimplement the
standard normal CDF/PDF using only `math.erf` (stdlib) -- verified here
(and directly, in `generate_film_looks.py`'s own history) to match
`scipy.stats.norm.cdf`/`.pdf` to float precision (~1e-16) across
`[-6, 6]`. The fitting itself (`curve_fit`, a nonlinear least-squares
regression) is the part that actually needs a numerical library; once the
five parameters per layer are fit, evaluating the model and its derivative
at a point is closed-form, and `generate_film_looks.py` only ever needs to
*evaluate*, not re-fit. This mirrors the existing pattern of
`film_paper_filter_data/tools/curve_digitizer/`: a separate, dependency-
heavy, offline tool that *produces* real data, transcribed as plain
constants into the dependency-free main generator, not run at generation
time.

## Usage

```
uv run main.py
```

Re-run this and re-transcribe the printed `*_SPLITGAUSS_FIT` constants into
`generate_film_looks.py` if any of `VELVIA_CURVES`, `KODACHROME64_CURVES`,
`PROVIA100F_CURVES`, `EKTACHROME100D_CURVES`, `RADIANCE_III_CURVES`,
`ILFOCHROME_M_CURVES`, `ILFOCHROME_P_CURVES`, any of the 6
`*_CURVES` in `NEGATIVE_FILMS`, or `PAPER_LADDER` ever change.
