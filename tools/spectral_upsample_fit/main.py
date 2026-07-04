#!/usr/bin/env python3
"""Fit Jakob & Hanika (2019) spectral-upsampling coefficient tables — one per
LUT-module application colour space this project supports (Adobe RGB, PQ
Rec.2020) — against this project's own CIE/D65/primary-matrix data, and bake
them to `spectral_upsampling_tables/<colorspace>.json` for
`generate_film_looks.py` to consume at generation time.

Why this exists (Ticket 16, tasks/16-fixed-rgb-weights-no-spectral-reconstruction.md):

`_weights()`/`layer_weights()` in generate_film_looks.py currently collapse
each colour film's real digitized spectral sensitivity curve against D65 and
a FIXED per-layer (R,G,B) weight triple, computed once. Per-pixel exposure is
then just `R*wr + G*wg + B*wb` — mathematically equivalent to assuming every
photographed colour is exactly a linear-light mixture of the three RGB
primaries' own spectral power distributions. Real reflectance spectra are not
linear combinations of three narrow-band primaries, and a real film's
spectral sensitivity is not colorimetric, so two real-world colours that are
metamers under the CIE 1931 observer (same RGB triple) can and do expose real
film differently — a real, physically documented effect this project's fixed-
weight model cannot represent by construction. See the pixls.us "spektrafilm
tech discussions" thread (discuss.pixls.us/t/spektrafilm-tech-discussions/
57512/8, and posts 1-2/6/9/11/12) for the field measuring exactly this
mismatch for real film (Portra 400 among others) using a smooth per-
chromaticity reflectance-reconstruction model instead of a fixed weight
matrix. That thread's own algorithm (`hanatos2025`) is unpublished, in-
progress forum work, not a citable method — this tool implements its stable,
published, peer-reviewed predecessor instead: Jakob, W., & Hanika, J. (2019).
"A Low-Dimensional Function Space for Efficient Spectral Upsampling."
Computer Graphics Forum, 38(2), 147-155. doi:10.1111/cgf.13626 (saved at
papers/spectral_upsampling/jakob_hanika_2019_spectral_upsampling.pdf; see
that folder's README for the full research trail, including the reference
C++ implementation at github.com/mitsuba-renderer/rgb2spec studied directly
to confirm this project's understanding of the algorithm's exact math before
using colour-science's independent Python port of the same method here).

What the algorithm does, briefly: for a given RGB tristimulus value, find
three polynomial coefficients (c0, c1, c2) such that the "sigmoid spectrum"
R(lambda) = 1/2 + U/(2*sqrt(1+U^2)), U = c0*lambda^2 + c1*lambda + c2,
reproduces that RGB value (in CIELAB, minimizing perceptual error) when
integrated against the CIE observer and a reference illuminant. This is a
smooth, low-parameter, physically-motivated reflectance model (see the
paper's own justification and generate_film_looks.py's GAMMA_CORRECT_TARGET
comment block for this project's general preference for fitted physical
models over ad hoc heuristics) that, unlike a coarser reconstruction, varies
continuously across the whole gamut with no "solution domain" discontinuities
(see the spektrafilm thread, post #12, contrasting this against otsu2018's
PCA-based upsampler on exactly this point). Because solving this per pixel
at generation time would be far too slow (and would need scipy, which
generate_film_looks.py deliberately does not depend on — see its own "Why
generate_film_looks.py doesn't need scipy" precedent in
tools/gamma_correction_fit/README.md), the coefficients are precomputed once
here over a modest 3D grid and baked to a lookup table that
generate_film_looks.py interpolates with pure stdlib arithmetic, exactly the
way tools/gamma_correction_fit/ bakes *_SPLITGAUSS_FIT constants instead of
shipping scipy.optimize.curve_fit at generation time.

Why the CMFS/illuminant/primaries are built from generate_film_looks.py's own
data instead of colour-science's bundled datasets: this project already hand-
maintains its own CIE 1931 2-degree observer + D65 tables (400-700nm, 10nm
steps — CIE/D65 dicts) and its own Adobe RGB / Rec.2020 primary matrices
(_MA_ADOBE/_MA_INV_ADOBE, _MA_REC2020/_MA_INV_REC2020), used by every other
calculation in the file (hk_mul(), layer_exposure_grid(), trix_exposure_grid()). Using a
different CMFS/illuminant/primaries dataset here (even a very close one)
would make the baked table subtly inconsistent with the domain
generate_film_looks.py actually integrates sensitivity curves over at
runtime -- so this tool imports generate_film_looks.py directly and builds
colour-science's CMFS/illuminant/RGB_Colourspace objects from those same
dicts/matrices, not from colour.MSDS_CMFS/SDS_ILLUMINANTS/RGB_COLOURSPACE_*.

Usage:
  uv run main.py                       # both colour spaces, size 16 (default)
  uv run main.py --size 24             # higher resolution, longer runtime
  uv run main.py --colorspace adobergb # just the committed default
"""
import sys, os, json, time, argparse
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
import generate_film_looks as gfl

from colour.colorimetry import MultiSpectralDistributions, SpectralDistribution
from colour.models import RGB_Colourspace, RGB_to_XYZ, XYZ_to_xy, XYZ_to_Lab
from colour.recovery.jakob2019 import (
    find_coefficients_Jakob2019,
    dimensionalise_coefficients,
    lightness_scale,
)

WAVELENGTHS = list(range(400, 710, 10))  # exactly generate_film_looks.py's own integration domain


def build_cmfs_illuminant():
    """CMFS + illuminant from this project's own CIE/D65 dicts (400-700nm,
    10nm), NOT colour-science's bundled 360-780nm dataset -- see module
    docstring for why this consistency matters."""
    xs = [gfl.CIE[wl][0] for wl in WAVELENGTHS]
    ys = [gfl.CIE[wl][1] for wl in WAVELENGTHS]
    zs = [gfl.CIE[wl][2] for wl in WAVELENGTHS]
    cmfs = MultiSpectralDistributions(
        dict(zip(WAVELENGTHS, zip(xs, ys, zs))),
        name="PoLUT CIE 1931 2-degree observer (400-700nm/10nm)",
    )
    illuminant = SpectralDistribution(
        dict(zip(WAVELENGTHS, [gfl.D65[wl] for wl in WAVELENGTHS])),
        name="PoLUT D65 (400-700nm/10nm)",
    )
    return cmfs, illuminant


def build_colourspace(name, rgb_to_xyz_matrix):
    """RGB_Colourspace from this project's own RGB->XYZ matrix (COLORSPACES[name]
    ['rgb2xyz'] in generate_film_looks.py), not colour-science's own dataset copy
    of "the same" primaries -- see module docstring. Both this project's
    colour spaces use a D65 whitepoint (confirmed: _MA_REC2020's own header
    comment "Rec.2020 (D65)"; Adobe RGB (1998) is D65-native)."""
    m_rgb_to_xyz = np.array(rgb_to_xyz_matrix, dtype=float)
    m_xyz_to_rgb = np.linalg.inv(m_rgb_to_xyz)
    primaries = np.array(
        [XYZ_to_xy(m_rgb_to_xyz[:, i] / m_rgb_to_xyz[1, i]) for i in range(3)]
    )
    whitepoint = np.array([0.3127, 0.3290])  # CIE D65
    return RGB_Colourspace(
        f"PoLUT {name}",
        primaries=primaries,
        whitepoint=whitepoint,
        whitepoint_name="D65",
        matrix_RGB_to_XYZ=m_rgb_to_xyz,
        matrix_XYZ_to_RGB=m_xyz_to_rgb,
    )


def _chroma_vector(l, y1, y2):
    """The permuted (1, y1, y2) chroma vector for "biggest channel" l, matching
    colour.recovery.jakob2019.LUT3D_Jakob2019.generate()'s own construction
    (chromas = concat([ij, roll(ij,1), roll(ij,2)]) for l=0,1,2 respectively)."""
    base = [1.0, y1, y2]
    return [base[(i - l) % 3] for i in range(3)]


def _solve_one(XYZ, colourspace, cmfs, illuminant, coefficients_0):
    Lab = XYZ_to_Lab(XYZ)
    coeffs, _error = find_coefficients_Jakob2019(
        XYZ, cmfs, illuminant, coefficients_0=coefficients_0, dimensionalise=False
    )
    return coeffs


def _solve_column(args):
    """Solve one (l, j, k) chroma column across the whole lightness axis,
    marching outward from the middle and reusing each solution as the next
    lightness step's starting guess -- the same continuation trick
    LUT3D_Jakob2019.generate() uses (see that class's own comment: "starts
    from somewhere in the middle, similarly to how feedback works in ...
    find_coefficients_Jakob2019"), just farmed out to a worker process per
    (l, j, k) column instead of running serially.
    """
    (l, j, k, size, colourspace_data, cmfs_data, illuminant_data,
     lightness_scale_list) = args

    m_rgb_to_xyz = np.array(colourspace_data["matrix_RGB_to_XYZ"])
    m_xyz_to_rgb = np.array(colourspace_data["matrix_XYZ_to_RGB"])
    colourspace = RGB_Colourspace(
        "worker",
        primaries=np.array(colourspace_data["primaries"]),
        whitepoint=np.array(colourspace_data["whitepoint"]),
        whitepoint_name="D65",
        matrix_RGB_to_XYZ=m_rgb_to_xyz,
        matrix_XYZ_to_RGB=m_xyz_to_rgb,
    )
    cmfs = MultiSpectralDistributions(
        dict(zip(WAVELENGTHS, zip(*cmfs_data))), name="cmfs"
    )
    illuminant = SpectralDistribution(dict(zip(WAVELENGTHS, illuminant_data)), name="illuminant")

    samples = np.linspace(0.0, 1.0, size)
    y1, y2 = samples[j], samples[k]
    chroma = np.array(_chroma_vector(l, y1, y2))
    lightness = np.array(lightness_scale_list)

    L_mid = size // 3
    out = [None] * size

    def solve_at(L, c0):
        RGB = lightness[L] * chroma
        XYZ = RGB_to_XYZ(RGB, colourspace)
        coeffs = _solve_one(XYZ, colourspace, cmfs, illuminant, c0)
        return coeffs

    c_mid = solve_at(L_mid, np.zeros(3))
    out[L_mid] = c_mid
    c0 = c_mid
    for L in reversed(range(L_mid)):
        c0 = solve_at(L, c0)
        out[L] = c0
    c0 = c_mid
    for L in range(L_mid + 1, size):
        c0 = solve_at(L, c0)
        out[L] = c0

    shape = cmfs.shape
    out_dim = [dimensionalise_coefficients(c, shape).tolist() for c in out]
    return l, j, k, out_dim


def generate_table(colourspace, cmfs, illuminant, size, print_callable=print):
    colourspace_data = {
        "matrix_RGB_to_XYZ": colourspace.matrix_RGB_to_XYZ.tolist(),
        "matrix_XYZ_to_RGB": colourspace.matrix_XYZ_to_RGB.tolist(),
        "primaries": colourspace.primaries.tolist(),
        "whitepoint": colourspace.whitepoint.tolist(),
    }
    cmfs_data = (
        cmfs.values[:, 0].tolist(),
        cmfs.values[:, 1].tolist(),
        cmfs.values[:, 2].tolist(),
    )
    illuminant_data = illuminant.values.tolist()
    lightness = lightness_scale(size)

    coefficients = np.empty((3, size, size, size, 3))
    tasks = [
        (l, j, k, size, colourspace_data, cmfs_data, illuminant_data, lightness.tolist())
        for l in range(3) for j in range(size) for k in range(size)
    ]
    total = len(tasks)
    done = 0
    t0 = time.time()
    with ProcessPoolExecutor() as pool:
        futures = [pool.submit(_solve_column, t) for t in tasks]
        for fut in as_completed(futures):
            l, j, k, col = fut.result()
            coefficients[l, :, j, k, :] = np.array(col)
            done += 1
            if done % max(1, total // 20) == 0 or done == total:
                elapsed = time.time() - t0
                print_callable(f"  {done}/{total} columns ({elapsed:.0f}s elapsed)")

    return coefficients, lightness


def validate_table(colourspace, cmfs, illuminant, coefficients, lightness, print_callable=print):
    """Sanity checks, not assumed: (1) achromatic RGB must reconstruct a FLAT
    spectrum (required for generate_film_looks.py's grey-anchor invariant --
    see tasks/16-...md's design note: layer_exposure(grey) must equal grey
    exactly for build_print_cascade()'s existing GREY=0.18 anchoring to keep
    working unchanged). (2) round-trip CIE76 Delta-E on a spread of grid-
    aligned and off-grid colours."""
    from colour.recovery.jakob2019 import sd_Jakob2019
    from colour.colorimetry import sd_to_XYZ_integration

    size = coefficients.shape[1]

    def rgb_to_coeffs(rgb):
        rgb = np.clip(np.array(rgb, dtype=float), 0.0, 1.0)
        value_max = np.max(rgb)
        if value_max <= 1e-10:
            return np.array([0.0, 0.0, -8192.0])
        chroma = rgb / value_max
        if np.allclose(rgb, rgb[0]):
            v = rgb[0]
            v = min(max(v, 1e-6), 1 - 1e-6)
            return np.array([0.0, 0.0, (v - 0.5) / math.sqrt(v * (1 - v))])
        i_m = int(np.argmax(rgb))
        # Must match _chroma_vector()'s own convention exactly: for channel l,
        # chroma[(l+1)%3] is stored along axis2 ("j"/y), chroma[(l+2)%3] along
        # axis3 ("k"/x). (An earlier version of this function had these two
        # swapped, copied from colour-science's own RGB_to_coefficients()
        # without re-deriving it against THIS file's _chroma_vector()
        # convention -- caught by the round-trip Delta-E76 check below going
        # to ~190 instead of a few units.)
        y1 = chroma[(i_m + 1) % 3]
        y2 = chroma[(i_m + 2) % 3]
        samples = np.linspace(0.0, 1.0, size)
        xg = np.clip(y2 * (size - 1), 0, size - 1)
        yg = np.clip(y1 * (size - 1), 0, size - 1)
        x0 = int(min(xg, size - 2)); x1 = x0 + 1; tx = xg - x0
        y0 = int(min(yg, size - 2)); y1 = y0 + 1; ty = yg - y0
        zi = int(np.searchsorted(lightness, value_max, side="right") - 1)
        zi = min(max(zi, 0), size - 2)
        tz = (value_max - lightness[zi]) / (lightness[zi + 1] - lightness[zi])

        def at(z, y, x):
            return coefficients[i_m, z, y, x, :]

        c = (
            (at(zi, y0, x0) * (1 - tx) + at(zi, y0, x1) * tx) * (1 - ty)
            + (at(zi, y1, x0) * (1 - tx) + at(zi, y1, x1) * tx) * ty
        ) * (1 - tz) + (
            (at(zi + 1, y0, x0) * (1 - tx) + at(zi + 1, y0, x1) * tx) * (1 - ty)
            + (at(zi + 1, y1, x0) * (1 - tx) + at(zi + 1, y1, x1) * tx) * ty
        ) * tz
        return c

    import math
    print_callable("\n  Grey axis (must reconstruct a flat spectrum):")
    for v in (0.05, 0.18, 0.5, 0.9):
        coeffs = rgb_to_coeffs([v, v, v])
        sd = sd_Jakob2019(coeffs, cmfs.shape)
        spread = float(np.max(sd.values) - np.min(sd.values))
        print_callable(f"    grey={v:.2f}  coeffs={coeffs}  spectrum_spread={spread:.6f}")

    print_callable("\n  Round-trip Delta-E76 on test colours:")
    rng = np.random.default_rng(0)
    max_de = 0.0
    for _ in range(200):
        rgb = rng.random(3)
        coeffs = rgb_to_coeffs(rgb)
        sd = sd_Jakob2019(coeffs, cmfs.shape)
        XYZ_recovered = sd_to_XYZ_integration(sd, cmfs, illuminant) / 100.0
        XYZ_target = RGB_to_XYZ(rgb, colourspace)
        Lab_r = XYZ_to_Lab(XYZ_recovered)
        Lab_t = XYZ_to_Lab(XYZ_target)
        de = float(np.sqrt(np.sum((Lab_r - Lab_t) ** 2)))
        max_de = max(max_de, de)
    print_callable(f"    max Delta-E76 over 200 random RGB samples: {max_de:.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=16)
    ap.add_argument("--colorspace", nargs="+", default=list(gfl.COLORSPACES.keys()))
    ap.add_argument("--output-dir", default=os.path.join(_ROOT, "spectral_upsampling_tables"))
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    cmfs, illuminant = build_cmfs_illuminant()

    for name in args.colorspace:
        cs_def = gfl.COLORSPACES[name]
        print(f"=== {name} ({cs_def['label']}), size={args.size} ===")
        colourspace = build_colourspace(name, cs_def["rgb2xyz"])
        coefficients, lightness = generate_table(colourspace, cmfs, illuminant, args.size)
        validate_table(colourspace, cmfs, illuminant, coefficients, lightness)

        out_path = os.path.join(args.output_dir, f"{name}.json")
        payload = {
            "_comment": (
                "Jakob & Hanika (2019) spectral-upsampling coefficient table, "
                "baked by tools/spectral_upsample_fit/ (Ticket 16). Consumed by "
                "generate_film_looks.py's spectral reconstruction step -- see "
                "that file's own comment for the runtime lookup/eval math."
            ),
            "colorspace": name,
            "wavelengths": WAVELENGTHS,
            "size": args.size,
            "lightness_scale": lightness.tolist(),
            "coefficients": coefficients.tolist(),
        }
        with open(out_path, "w") as f:
            json.dump(payload, f, separators=(",", ":"))
        print(f"  wrote {out_path} ({os.path.getsize(out_path)/1e6:.2f} MB)\n")


if __name__ == "__main__":
    main()
