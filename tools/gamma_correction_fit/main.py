#!/usr/bin/env python3
"""Fit a real, physically-motivated model to each reversal film's and each
direct-print paper's digitized H&D curve, then derive the Jones-corrected
reversal-film curve analytically from that fit, instead of the piecewise-
linear window/scalar heuristics tried (and rejected, see git history and
generate_film_looks.py's own GAMMA_CORRECT_TARGET comment) in earlier
rounds.

Why a curve-fit at all, and why this particular model:

The physical origin of the H&D curve's toe/straight-line/shoulder shape is
well established in sensitometry: a photographic emulsion is not one
uniform light-sensitive material -- it's a population of individual silver
halide grains, each of which becomes developable once its own quantum catch
crosses its own threshold, and that population has a real, measured spread
of individual grain sensitivities (see J.H. Webb, "Graphical Analysis of
Photographic Exposure and a New Theoretical Formulation of the H and D
Curve," J. Opt. Soc. Am. 29, 314-326 (1939), which derives the H&D curve
from exactly this grain-sensitivity-distribution picture -- primary source
paywalled, cited via corroborating literature, see papers/masking_research/
README.md). The curve's shape at any exposure is therefore essentially a
*cumulative distribution* of how many grains have crossed threshold by that
exposure -- which is why real H&D curves look like a smoothly saturating
S-shape (a CDF), not an arbitrary hand-drawn curve. The standard, well-
understood idealization of a threshold-crossing process over a population
with a roughly log-normal sensitivity spread is a cumulative Gaussian
(normal) distribution plotted against *log* exposure -- consistent with
Webb's own finding that the resulting equation doesn't integrate to a closed
form (exactly what you'd expect from a Gaussian CDF, whose integral is the
special "erf" function, not an elementary one).

This tool fits an *asymmetric* cumulative-Gaussian ("two-piece"/"split-
normal") model -- same physical picture, but allowing the toe and shoulder
to have independently-fit widths, because they are, physically, governed by
different mechanisms (grain-threshold statistics near Dmin; dye/silver
exhaustion near Dmax) and real emulsions are not symmetric toe-to-shoulder.
Fit via least squares (scipy.optimize.curve_fit) against each curve's real
digitized points; fit quality (R^2, max residual) is reported, not assumed.

Usage: uv run main.py
"""
import sys, os, math
import numpy as np
from scipy.optimize import curve_fit
from scipy.stats import norm

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
import generate_film_looks as gfl


def split_gaussian_cdf(x, x0, d_lo, d_hi, sigma_lo, sigma_hi):
    """D(x) = d_lo + (d_hi - d_lo) * Phi((x-x0)/sigma), sigma = sigma_lo for
    x<x0, sigma_hi for x>=x0. Phi = standard normal CDF. This is continuous
    in value at x0 (Phi(0)=0.5 from either side) but not necessarily in
    slope unless sigma_lo==sigma_hi -- see module docstring for why that's
    an acceptable, standard (split-normal) simplification here."""
    x = np.asarray(x, dtype=float)
    sigma = np.where(x < x0, sigma_lo, sigma_hi)
    return d_lo + (d_hi - d_lo) * norm.cdf((x - x0) / sigma)


def fit_curve(curve):
    """Fit split_gaussian_cdf to a real digitized curve dict. Returns
    (params, r2, max_abs_resid). Initial guess derived from the real data:
    x0 at the density midpoint's exposure, d_lo/d_hi from real min/max,
    sigma from the overall exposure span."""
    xs = np.array(sorted(curve.keys()))
    ys = np.array([curve[x] for x in xs])
    d_min, d_max = float(ys.min()), float(ys.max())
    decreasing = ys[-1] < ys[0]
    d_lo_guess, d_hi_guess = (d_max, d_min) if decreasing else (d_min, d_max)
    x0_guess = xs[np.argmin(np.abs(ys - (d_min + d_max) / 2))]
    span_guess = (xs[-1] - xs[0]) / 4
    p0 = [x0_guess, d_lo_guess, d_hi_guess, span_guess, span_guess]
    bounds = ([xs[0] - 5, -1, -1, 1e-3, 1e-3], [xs[-1] + 5, 5, 5, 20, 20])
    popt, _ = curve_fit(split_gaussian_cdf, xs, ys, p0=p0, bounds=bounds, maxfev=20000)
    pred = split_gaussian_cdf(xs, *popt)
    resid = ys - pred
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((ys - ys.mean())**2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return popt, r2, float(np.max(np.abs(resid)))


def local_gamma(params, x):
    """Exact analytic |dD/dx| of the fitted split-Gaussian-CDF at x -- the
    derivative of a normal CDF is the normal PDF, no finite-difference
    approximation needed."""
    x0, d_lo, d_hi, sigma_lo, sigma_hi = params
    sigma = sigma_lo if x < x0 else sigma_hi
    return abs((d_hi - d_lo) * norm.pdf((x - x0) / sigma) / sigma)


def stretch_corrected_curve(film_params, downstream_gamma, target, n_samples=81):
    """Horizontal (exposure-axis-only) stretch of the FITTED film model,
    toe (x<x0) and shoulder (x>=x0) by INDEPENDENT factors k_lo/k_hi, each
    chosen so that half's own natural local gamma at the toe/shoulder
    junction x0 (peak/sigma_lo or peak/sigma_hi), times downstream_gamma,
    equals target -- i.e. Jones's rule satisfied on each half's own terms,
    using the film's own real fitted shape (not a straight line, not a
    window-truncated hybrid, and not one shared factor derived from
    whichever half a real-world reference exposure happened to land in --
    see generate_film_looks.py's gamma_correct_curve() docstring for why a
    single shared k measurably failed: every material here has
    sigma_lo != sigma_hi by design, so reusing one half's factor for the
    other over- or under-corrects it). Density values are untouched (so the
    model's own real fitted d_lo/d_hi -- effectively the film's real
    Dmin/Dmax -- are exactly preserved, just reached over a wider, stretched
    exposure range); only exposure positions are relabeled, anchored at the
    model's own x0 (mapping to itself, so the two independently-stretched
    halves stay continuous there).

    Returns a sampled curve dict (n_samples points, densely covering the
    range where the model moves perceptibly, i.e. within a few sigma of
    x0) for generate_film_looks.py's existing dict-based cascade machinery.
    """
    x0, d_lo, d_hi, sigma_lo, sigma_hi = film_params
    peak = abs(d_hi - d_lo) * norm.pdf(0.0)
    k_lo = target / (downstream_gamma * (peak / sigma_lo))
    k_hi = target / (downstream_gamma * (peak / sigma_hi))
    # Sample the ORIGINAL model over a wide range (+/- 8 sigma each side of
    # x0, comfortably covering >99.9999% of the CDF's range), then stretch
    # each half's exposure positions around x0 by its own 1/k.
    xs_orig = np.linspace(x0 - 8 * sigma_lo, x0 + 8 * sigma_hi, n_samples)
    ys = split_gaussian_cdf(xs_orig, *film_params)
    ks = np.where(xs_orig < x0, k_lo, k_hi)
    xs_new = x0 + (xs_orig - x0) / ks
    return {float(xn): float(yn) for xn, yn in zip(xs_new, ys)}


def main():
    films = {
        "velvia": (gfl.VELVIA_CURVES, gfl.VELVIA_REF_D),
        "kodachrome64": (gfl.KODACHROME64_CURVES, gfl.KODACHROME64_REF_D),
        "provia100f": (gfl.PROVIA100F_CURVES, gfl.PROVIA100F_REF_D),
        "ektachrome100d": (gfl.EKTACHROME100D_CURVES, gfl.EKTACHROME100D_REF_D),
    }

    print("=== Fit quality: reversal films (3 layers each) ===")
    film_fits = {}
    for fkey, (curves, refd) in films.items():
        film_fits[fkey] = []
        for li, curve in enumerate(curves):
            params, r2, maxres = fit_curve(curve)
            film_fits[fkey].append(params)
            print(f"{fkey:16s} L{li}  R2={r2:.5f}  max_resid={maxres:.4f}  "
                  f"x0={params[0]:+.3f} d_lo={params[1]:.3f} d_hi={params[2]:.3f} "
                  f"sig_lo={params[3]:.3f} sig_hi={params[4]:.3f}")

    print("\n=== Fit quality: direct-print papers (3 layers each) ===")
    paper_fits = {}
    for look in gfl.DIRECT_PRINT_LOOKS:
        paper = gfl.DIRECT_PRINT_PAPERS[look]
        paper_fits[look] = []
        for li, curve in enumerate(paper):
            params, r2, maxres = fit_curve(curve)
            paper_fits[look].append(params)
            print(f"{look:12s} L{li}  R2={r2:.5f}  max_resid={maxres:.4f}  "
                  f"x0={params[0]:+.3f} d_lo={params[1]:.3f} d_hi={params[2]:.3f} "
                  f"sig_lo={params[3]:.3f} sig_hi={params[4]:.3f}")

    print("\n=== Corrected-curve check: shortfall against paper's real (fitted) Dmax ===")
    target = gfl.GAMMA_CORRECT_TARGET
    for fkey, (curves, refd) in films.items():
        for look in gfl.DIRECT_PRINT_LOOKS:
            paper = gfl.DIRECT_PRINT_PAPERS[look]
            for li in range(3):
                fparams = film_fits[fkey][li]
                pparams = paper_fits[look][li]
                xs0, ys0 = gfl._sc(curves[li])
                na0 = gfl._find_anchor(xs0, ys0, refd[li], increasing=False,
                                        start=gfl._detect_lead_noise_start(curves[li], False))
                # paper's own real operating point: where it reproduces 18% grey
                pxs, pys = gfl._sc(paper[li])
                lhg = gfl._find_anchor(pxs, pys, gfl._grey_target_density(pys),
                                        increasing=False, start=gfl._detect_lead_noise_start(paper[li], False))
                downstream_gamma = local_gamma(pparams, lhg)
                corrected = stretch_corrected_curve(fparams, downstream_gamma, target)
                start = 0
                stages = [(corrected, False, start, refd[li]),
                          (paper[li], False, gfl._detect_lead_noise_start(paper[li], False), None)]
                xfer = gfl.build_print_cascade(stages)
                fdm = min(pys)
                dmax_paper_fit = pparams[1]  # d_lo of paper fit -- decreasing curve, so Dmax sits at LOW exposure
                floor_v = xfer(gfl.GREY * (2**-20))
                d_at_floor = fdm - math.log10(max(floor_v, 1e-15))
                grey_check = xfer(gfl.GREY)
                print(f"{fkey:16s} {look:12s} L{li}  grey={grey_check:.4f}  "
                      f"D_floor={d_at_floor:.3f}  paper_Dmax_fit={dmax_paper_fit:.3f}  "
                      f"shortfall={dmax_paper_fit - d_at_floor:+.3f}  k_gamma_at_pivot={local_gamma(fparams, na0):.3f}")

    # ---------------------------------------------------------------------
    # Negative films (Portra 400 etc.) x PAPER_LADDER -- same treatment,
    # increasing=True on both stages (density rises with exposure for a
    # camera negative and for a real RA-4 print paper, unlike the reversal-
    # film/direct-print-paper case above). Added after real-world use showed
    # negative films (never audited against Jones's rule) running at a
    # *higher* system gamma (~1.4-1.7 measured near grey) than the freshly-
    # corrected reversal direct-print route (~1.0-1.1) -- backwards from the
    # real photographic hierarchy, where reversal stock is the punchier
    # material. Root cause, measured directly: negative films' own native
    # gamma is correctly low (0.47-0.68, exactly the low-native-gamma design
    # every color negative stock uses), but PAPER_LADDER's own real measured
    # gammas are steep (2.5-4.3 across all 5 papers, including "ExtraSoft")
    # -- steep enough that even the lowest-gamma negative film doesn't fully
    # compensate.
    # ---------------------------------------------------------------------
    neg_films = {
        "portra400": (gfl.PORTRA400_CURVES, gfl.PORTRA400_REF_D),
        "ektar100": (gfl.EKTAR100_CURVES, gfl.EKTAR100_REF_D),
        "gold200": (gfl.GOLD200_CURVES, gfl.GOLD200_REF_D),
        "ultramax400": (gfl.ULTRAMAX400_CURVES, gfl.ULTRAMAX400_REF_D),
        "superiareala": (gfl.SUPERIA_REALA_CURVES, gfl.SUPERIA_REALA_REF_D),
        "superiaxtra400": (gfl.SUPERIA_XTRA400_CURVES, gfl.SUPERIA_XTRA400_REF_D),
    }

    print("\n=== Fit quality: negative films (3 layers each) ===")
    neg_film_fits = {}
    for fkey, (curves, refd) in neg_films.items():
        neg_film_fits[fkey] = []
        for li, curve in enumerate(curves):
            params, r2, maxres = fit_curve(curve)
            neg_film_fits[fkey].append(params)
            print(f"{fkey:16s} L{li}  R2={r2:.5f}  max_resid={maxres:.4f}  "
                  f"x0={params[0]:+.3f} d_lo={params[1]:.3f} d_hi={params[2]:.3f} "
                  f"sig_lo={params[3]:.3f} sig_hi={params[4]:.3f}")

    print("\n=== Fit quality: PAPER_LADDER papers (3 layers each) ===")
    ladder_fits = {}
    for look in gfl.COLOR_LOOKS:
        paper = gfl.PAPER_LADDER[look]
        ladder_fits[look] = []
        for li, curve in enumerate(paper):
            params, r2, maxres = fit_curve(curve)
            ladder_fits[look].append(params)
            print(f"{look:12s} L{li}  R2={r2:.5f}  max_resid={maxres:.4f}  "
                  f"x0={params[0]:+.3f} d_lo={params[1]:.3f} d_hi={params[2]:.3f} "
                  f"sig_lo={params[3]:.3f} sig_hi={params[4]:.3f}")

    print("\n=== Corrected negative-film check: shortfall against paper's real (fitted) Dmax ===")
    for fkey, (curves, refd) in neg_films.items():
        for look in gfl.COLOR_LOOKS:
            paper = gfl.PAPER_LADDER[look]
            for li in range(3):
                fparams = neg_film_fits[fkey][li]
                pparams = ladder_fits[look][li]
                xs0, ys0 = gfl._sc(curves[li])
                na0 = gfl._find_anchor(xs0, ys0, refd[li], increasing=True,
                                        start=gfl._detect_lead_noise_start(curves[li], True))
                pxs, pys = gfl._sc(paper[li])
                lhg = gfl._find_anchor(pxs, pys, gfl._grey_target_density(pys),
                                        increasing=True, start=gfl._detect_lead_noise_start(paper[li], True))
                downstream_gamma = local_gamma(pparams, lhg)
                corrected = stretch_corrected_curve(fparams, downstream_gamma, target)
                stages = [(corrected, True, 0, refd[li]),
                          (paper[li], True, gfl._detect_lead_noise_start(paper[li], True), None)]
                xfer = gfl.build_print_cascade(stages)
                floor_v = xfer(gfl.GREY * (2**-20))  # deep scene shadow -> print black
                ceil_v = xfer(gfl.GREY * (2**20))    # deep scene highlight -> print white
                grey_check = xfer(gfl.GREY)
                print(f"{fkey:16s} {look:12s} L{li}  grey={grey_check:.4f}  "
                      f"black={floor_v:.4f}  white={ceil_v:.4f}  "
                      f"k_gamma_at_pivot={local_gamma(fparams, na0):.3f}")


if __name__ == "__main__":
    main()
