"""
Fits a spektrafilm-compatible `density_curves_model` ("norm_cdfs": a sum of
`n_layers` scaled normal CDFs) to a digitized H&D (density vs. log-exposure)
curve, and evaluates that fitted model on darktable's canonical 256-point
log_exposure grid.

Model, confirmed against the reference evaluator
(`spektrafilm/src/spektrafilm/utils/morph_curves.py`, `_evaluate_channel_density`
/ `_layer_cdf`, `profile_type="negative"` so no sign flip):

    D(logE) = sum_i  amplitudes[i] * Phi((logE - centers[i]) / sigmas[i])

Physically, each layer is one grain-speed sub-population's threshold-crossing
distribution (fast/mid/slow) -- the same "cumulative Gaussian over grain
threshold statistics" idealization PoLUT's own
`tools/gamma_correction_fit/` uses for its split-Gaussian model, generalized
here to a sum of `n_layers` *symmetric* CDFs instead of one asymmetric
toe/shoulder blend, matching what every other real profile in the pack uses.

The model must be fit against NET density -- digitized density minus that
curve's own base+fog density -- NOT the raw absolute digitized values.
`base_density` is a separate profile field the render pipeline adds back on
top of whatever this model produces: `compute_density_spectral()`
(spektrafilm/src/spektrafilm/model/develop.py) computes
`density_spectral = (density_cmy . channel_density) + base_density`, a plain
addition applied *after* `density_curves`/`density_curves_model` is
evaluated. Confirmed against the real shipped `kodak_trix.json`: its
`density_curves` asymptotes toward ~0 at the low-density end, not toward its
own `base_density` (0.2156) -- if the array already included base+fog, that
asymptote would approach 0.2156 instead. An earlier version of this file
fit directly against raw absolute density and shipped profiles that
double-counted base_density (baked into the fitted curve's own asymptote,
then added again downstream) -- confirmed as the root cause of a real,
reported "image renders far too dark, even worse with the print stage
skipped" bug (2026-08-02) once traced through `compute_density_spectral`;
every caller now must pass `density - base_density`, not raw `density`, as
this module's fitting target. In practice this still means one layer's
center often sits early enough (relative to the visible exposure range)
that it's already close to fully saturated across the whole curve,
contributing an effectively-constant
"already-fogged" offset -- exactly the fast/early-threshold grain population
story, not a fitting trick.
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import curve_fit
from scipy.stats import norm


@dataclass
class NormCdfsFit:
    centers: np.ndarray    # (n_layers,)
    amplitudes: np.ndarray  # (n_layers,)
    sigmas: np.ndarray      # (n_layers,)
    r_squared: float
    max_residual: float


def _model(x, *params, n_layers):
    centers = np.asarray(params[0:n_layers])
    log_amps = np.asarray(params[n_layers:2 * n_layers])
    log_sigmas = np.asarray(params[2 * n_layers:3 * n_layers])
    amps = np.exp(log_amps)
    sigmas = np.exp(log_sigmas)
    total = np.zeros_like(x, dtype=float)
    for i in range(n_layers):
        total += amps[i] * norm.cdf((x - centers[i]) / sigmas[i])
    return total


def fit_norm_cdfs(log_exposure, density, n_layers=3, n_restarts=6, seed=0):
    """Fit the sum-of-normal-CDFs model to digitized (log_exposure, density)
    points. Tries a few randomized initializations (real photographic H&D
    data is smooth/well-behaved, but a 9-parameter nonlinear fit can still
    land in a mediocre local optimum from a single init) and keeps the best
    by R^2 on the actual digitized points.

    Centers and sigmas are bounded to stay within a generous multiple of the
    real digitized exposure range. Without this, curve_fit has a second way
    to fit an early-saturating "constant offset" layer besides the intended
    one (a center placed well before the data with an ordinary sigma): push
    BOTH center and sigma out to huge, near-equal values instead, so their
    ratio (and hence the CDF's argument) stays near zero across the entire
    visible range -- a degenerate near-constant-0.5*amplitude layer that
    fits the total curve just as well but isn't a genuine grain-speed
    sub-population (confirmed: first pass produced sigmas ~1e8-1e11 against
    a data range of ~4, one "layer" doing nothing but mimicking a constant).
    Bounding sigma to a modest multiple of the data range forces every layer
    to actually behave like a threshold-crossing population within or near
    the visible curve, which is the physical story this model is for."""
    x = np.asarray(log_exposure, dtype=float)
    y = np.asarray(density, dtype=float)
    order = np.argsort(x)
    x, y = x[order], y[order]

    x_range = x.max() - x.min()
    y_range = max(y.max() - y.min(), 1e-3)
    rng = np.random.default_rng(seed)

    center_lo, center_hi = x.min() - 2 * x_range, x.max() + 2 * x_range
    sigma_lo, sigma_hi = 0.02, 3 * x_range
    lower = np.concatenate([np.full(n_layers, center_lo), np.full(n_layers, -20.0),
                             np.full(n_layers, np.log(sigma_lo))])
    upper = np.concatenate([np.full(n_layers, center_hi), np.full(n_layers, 20.0),
                             np.full(n_layers, np.log(sigma_hi))])

    best = None
    for attempt in range(n_restarts):
        if attempt == 0:
            # First layer anchored well before the visible data -- an
            # already-saturated "fast" population carrying the base/fog
            # offset, as described above -- then two more spread across the
            # visible toe->shoulder range.
            centers0 = np.array([
                x.min() - 0.6 * x_range,
                x.min() + 0.35 * x_range,
                x.min() + 0.75 * x_range,
            ][:n_layers])
            amps0 = np.full(n_layers, y_range / max(n_layers - 1, 1))
            amps0[0] = max(y.min(), 1e-2)
            sigmas0 = np.full(n_layers, max(x_range / (1.5 * n_layers), 0.05))
        else:
            centers0 = x.min() - 0.6 * x_range + rng.uniform(0, 1.6 * x_range, n_layers)
            amps0 = rng.uniform(y_range / (3 * n_layers), y_range, n_layers)
            sigmas0 = rng.uniform(0.05, x_range / n_layers, n_layers)
        centers0 = np.clip(centers0, center_lo, center_hi)
        sigmas0 = np.clip(sigmas0, sigma_lo, sigma_hi)

        p0 = np.concatenate([centers0, np.log(amps0), np.log(sigmas0)])
        try:
            # maxfev=5000, not 40000: measured directly across every real
            # curve in this project (Tri-X's 14 development-time curves,
            # Polymax's 7 grades). At maxfev=40000, a restart whose random
            # init lands in a bad region doesn't converge to something
            # DIFFERENT/better given more budget -- it just grinds toward
            # the same optimum other restarts already reach, sometimes
            # burning 15-20s and tens of thousands of evaluations to get
            # there (confirmed on Kodak Tri-X D-76 9min: two of six restarts
            # took 15-20s each, the other four converged to the identical
            # best R^2 in under half a second). A first attempt at
            # maxfev=500 seemed to confirm this (D-76 stayed at identical
            # R^2, ~19x faster) but was NOT safe in general: TXP's 3.5min
            # curve failed on all 6 restarts at 500 (every restart there
            # genuinely needs more budget, not just the unlucky ones), while
            # succeeding cleanly on all 6 at 5000 with the same R^2 as
            # 40000. 5000 is the value that held up across every real curve
            # tested, not just the one that happened to be easy -- don't
            # drop it further without re-measuring against curves harder
            # than D-76's, and don't raise it back toward 40000 without
            # re-confirming the slow restarts are still just redundant, not
            # rescuing a curve nothing else converges on. RuntimeError is
            # still caught and skipped below, so a failed restart costs
            # nothing but time.
            popt, _ = curve_fit(
                lambda x_, *p: _model(x_, *p, n_layers=n_layers),
                x, y, p0=p0, bounds=(lower, upper), maxfev=5000,
            )
        except RuntimeError:
            continue

        fitted = _model(x, *popt, n_layers=n_layers)
        residuals = y - fitted
        ss_res = float(np.sum(residuals ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
        max_resid = float(np.max(np.abs(residuals)))

        if best is None or r2 > best.r_squared:
            centers = popt[0:n_layers]
            amps = np.exp(popt[n_layers:2 * n_layers])
            sigmas = np.exp(popt[2 * n_layers:3 * n_layers])
            best = NormCdfsFit(centers=centers, amplitudes=amps, sigmas=sigmas,
                                r_squared=r2, max_residual=max_resid)

    if best is None:
        raise RuntimeError("norm_cdfs fit failed to converge on every restart")
    return best


def evaluate_total(fit: NormCdfsFit, x_grid: np.ndarray) -> np.ndarray:
    total = np.zeros_like(x_grid, dtype=float)
    for c, a, s in zip(fit.centers, fit.amplitudes, fit.sigmas):
        total += a * norm.cdf((x_grid - c) / s)
    return total


def evaluate_layers(fit: NormCdfsFit, x_grid: np.ndarray) -> np.ndarray:
    """Returns shape (len(x_grid), n_layers) -- each layer's own partial
    density contribution, summing (axis=1) to evaluate_total()."""
    n_layers = len(fit.centers)
    layers = np.zeros((len(x_grid), n_layers), dtype=float)
    for i, (c, a, s) in enumerate(zip(fit.centers, fit.amplitudes, fit.sigmas)):
        layers[:, i] = a * norm.cdf((x_grid - c) / s)
    return layers
