"""
Cross-calibrates a digitized B&W NEGATIVE film's `log_sensitivity` absolute
scale against spektrafilm's own internal exposure convention.

Why this exists: `black_white_filming_exposure_correction()`
(spektrafilm/src/spektrafilm/runtime/services/color_reference.py) returns
exactly `1.0` -- no correction at all -- for any `info.type == "negative"`
B&W film. Unlike the print stage (which auto-normalizes exposure around
whatever density the film's own midgray produces --
`printing.py::_compute_exposure_factor_midgray`), a negative film's own
exposure computation has no such safety net: `raw = integral(reflectance *
illuminant * 10**log_sensitivity)`, with the digitized `log_sensitivity`
array's ABSOLUTE value used directly. A Kodak Spectral-Sensitivity chart's
own units ("reciprocal of exposure in ergs/cm^2 required to produce a
specified density", read off a monochromator spectrograph) have no reason
to already sit on whatever absolute scale spektrafilm's own illuminant
tables (`pack.json`'s `"illuminants"` field) are normalized to.

Confirmed 2026-08-02 as the root cause of a real, reported "image renders
crushed/flat, worse in scan-only mode, same regardless of which paper" bug
-- traced by computing an unshifted Tri-X 400 grey exposure (log_raw ~2.70,
landing at 99.99% up its own density curve, pinned in the flat shoulder --
any real scene's tonal range collapses to nothing there) and comparing
against five independent, already-shipped, presumably-correct profiles
(kodak_doublex -- same channel_model=bw/type=negative as Tri-X, the closest
analog; kodak_portra_400, fujifilm_c200, kodak_ektar_100,
kodak_vision3_250d -- all color negatives, all D55-referenced) computing the
identical flat-0.18-reflectance integration. All five land within 0.03 log10
units of each other (log_raw ~0.72-0.77, mean ~0.743) despite totally
different manufacturers, film types, and spectral sensitivities -- far too
tight a cluster to be coincidence.

This convergence is not incidental -- it follows directly from the runtime's
own documented contract (spektrafilm/src/spektrafilm/README.md): "Input:
linear-light RGB... The scene-referred light is what the physics actually
models" -- the standard scene-referred convention where a properly-exposed
neutral subject renders at ~0.18. Per-profile log_sensitivity calibration
exists precisely so "expose a grey card, get RGB=0.18" means the same thing
regardless of which film is loaded; every correctly-calibrated profile must
therefore reproduce the same grey_log_raw. GREY_TARGET_LOG_RAW below is that
empirically-confirmed value, used to correct any digitized log_sensitivity
whose absolute scale hasn't been independently cross-calibrated (i.e. was
transcribed as-printed from a source chart using its own, different, real
unit system).

Applies to B&W NEGATIVE film stocks only:
- Paper stocks don't need this: the print stage's own
  `_compute_exposure_factor_midgray` normalizes print exposure around
  whatever density the film's midgray actually produces, which cancels out
  a paper's own absolute log_sensitivity scale by construction regardless
  of what it is.
- B&W POSITIVE (reversal) stocks don't go through this same no-op path --
  `black_white_filming_exposure_correction()` does apply a real correction
  when `scan_film and film.info.type == "positive"`; check that function's
  own logic before assuming this module applies to a reversal product.
"""

import numpy as np

# D55 illuminant SPD, sampled on the same 81-point 380-780nm/5nm grid as
# canonical_grids.WAVELENGTHS_NM -- copied from darktable's own
# devconfig/spektrafilm/pack.json ("illuminants"."D55"): a real, standard CIE
# tabulated illuminant (not spektrafilm-specific data), at the exact sampling
# this tool's own profiles are built against. Only D55 is embedded since
# every B&W negative film product built so far uses reference_illuminant=D55;
# re-extract the relevant key from a current pack.json if a future product
# needs a different one.
D55_SPD = np.array([
    0.3792826592081565, 0.41130471283820924, 0.4433384066186183, 0.5763969653409493,
    0.7094555240632804, 0.7537113757177554, 0.7979788675225865, 0.8155671347108852,
    0.8331670420495402, 0.8118539267472403, 0.7905291712945844, 0.8934979413460009,
    0.996455071247061, 1.0685541625536938, 1.1406532538603265, 1.1550288395502992,
    1.169404425240272, 1.1662033838923025, 1.1630023425443328, 1.1794498749977185,
    1.1958974074511046, 1.1687758571210345, 1.141642666640608, 1.1567865022540935,
    1.1719303378675792, 1.172023459070429, 1.1721049401229227, 1.167984326896809,
    1.1638637136706955, 1.1884360710727462, 1.213020068625153, 1.2007513501496623,
    1.1884826316741712, 1.1935228167784289, 1.1985630018826865, 1.1812890187540066,
    1.1640150356253267, 1.1478119463294223, 1.1316088570335177, 1.134705137028281,
    1.1378130571734006, 1.1010418221979967, 1.0642822273729489, 1.0816726120051912,
    1.0990513564870772, 1.1032534507656848, 1.107443904893936, 1.1020894357300595,
    1.096734966566183, 1.0747816429942894, 1.0528283194223955, 1.0637817009076298,
    1.0747350823928643, 1.054504501073696, 1.0342739197545279, 1.0427945098153053,
    1.0513034597257263, 1.0724419727726824, 1.0935921259699946, 1.0703467457085567,
    1.047101365447119, 0.9872826327663333, 0.9274522599351918, 0.945855337648428,
    0.9642700555120207, 0.9759334861689865, 0.9875969168259522, 0.9025656184735221,
    0.8175459602714483, 0.8703107618363444, 0.9230755634012404, 0.9562034313151373,
    0.989331299229034, 0.9130184734934376, 0.8366940076074848, 0.72561205275776,
    0.6145184577576788, 0.7491600769284603, 0.883801696099242, 0.8598811871171415,
    0.8359723182853972,
])

GREY_REFLECTANCE = 0.18
# Mean of 5 independent real shipped profiles' own grey_log_raw (see module
# docstring): kodak_doublex 0.749, kodak_portra_400 0.737, fujifilm_c200
# 0.742, kodak_ektar_100 0.744, kodak_vision3_250d 0.744.
GREY_TARGET_LOG_RAW = 0.743


def grey_log_raw(log_sensitivity, wavelengths, illuminant_spd=D55_SPD):
    """log10 of the raw exposure a flat GREY_REFLECTANCE spectrum under
    `illuminant_spd` produces, integrated against `log_sensitivity` (linear
    sensitivity = 10**log_sensitivity, NaN treated as 0). This mirrors
    spektrafilm's own per-pixel `raw = integral(reflectance * illuminant *
    sensitivity)` (filming.py::_rgb_to_film_raw), simplified to a flat/
    neutral reflectance spectrum since a genuinely achromatic scene-linear
    RGB input upsamples to essentially the same flat spectrum any reasonable
    method would produce for the achromatic case -- sufficient for this one
    calibration point, not a substitute for real per-pixel spectral
    upsampling."""
    sens_lin = np.nan_to_num(10.0 ** np.asarray(log_sensitivity, dtype=float))
    light = GREY_REFLECTANCE * illuminant_spd
    raw = np.trapezoid(light * sens_lin, wavelengths)
    return float(np.log10(raw))


def calibrate_negative_film_log_sensitivity(log_sensitivity, wavelengths, illuminant_spd=D55_SPD):
    """Returns (shifted_log_sensitivity, shift_applied, grey_log_raw_before).
    Shifts the whole array by one constant (in log10 units) so
    `grey_log_raw()` lands exactly on GREY_TARGET_LOG_RAW. A uniform
    additive shift is the correct degree of freedom here: what's uncertain
    is the ABSOLUTE calibration (the source chart's own real but unrelated
    unit system), not the RELATIVE spectral shape, which the digitized data
    already carries correctly."""
    before = grey_log_raw(log_sensitivity, wavelengths, illuminant_spd)
    shift = GREY_TARGET_LOG_RAW - before
    shifted = np.asarray(log_sensitivity, dtype=float) + shift
    return shifted, shift, before
