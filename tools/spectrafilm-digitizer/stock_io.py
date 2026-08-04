"""
Vendor-agnostic helpers for writing one darktable spektrafilm stock (single
development_time, n_dev=1 from the start -- no family, nothing for
collapse_to_darktable_pack() to flatten on that axis) plus its QA artifacts.

Split out of trix_common.py (2026-08) once a second vendor (Ilford, see
ilford_common.py) needed the exact same digitize -> fit -> assemble -> write
shape but with none of Kodak/Tri-X's development-time-family or
Contrast-Index machinery -- everything here was already vendor-agnostic in
practice, just named after the file it was born in. trix_common.py still
re-exports these names so kodak_trix400tx.py/_txp.py/_txt.py and
kodak_polymax_fine_art.py don't need to change their imports.
"""

import json

import numpy as np

import fitz

import density_model as dm
import spektra_profile as sp
from digitizer_core import render_qa_overlay


def speed_point_x(points, base_density, criterion=1.0):
    """Interpolate digitized (log_exposure, density) points to find the
    log_exposure at density = base_density + criterion."""
    xs = np.array([p[0] for p in points])
    ys = np.array([p[1] for p in points])
    order = np.argsort(ys)
    return float(np.interp(base_density + criterion, ys[order], xs[order]))


def ansi_speed_ei(points, base_density, criterion=0.1, k=0.8):
    """Simplified ANSI/ISO black-and-white negative film speed: EI = k / Hm,
    Hm = the real exposure in lux-seconds (10**log_exposure, so `points`
    must be in the chart's own real un-shifted page-axis units, not a
    canonical-grid-shifted curve) at density = base_density + criterion
    (0.1 and k=0.8 are ISO 6:1993's own constants for this style of speed
    point). This is the plain single-point speed-point method, NOT the full
    ANSI PH2.5/ISO 6:1993 two-point fractional-gradient method (which also
    requires a second point 1.3 log-H further along the curve to land
    within a specified delta-density range, a shape-sensitive correction
    this project doesn't attempt) -- expect good agreement on steep/
    higher-contrast curves and looser agreement on very low-contrast curves
    (a shallow toe makes the single-point method more sensitive to exactly
    where density departs from base), not an exact match to a
    manufacturer's own published EI on every curve. Useful as an
    independent real-number cross-check when a datasheet publishes its own
    EI alongside a curve (see products/kodak_techpan.py, whose datasheet
    publishes real EI per development time -- something Tri-X's own
    datasheet never does per bracket -- for how strong agreement on a
    to-be-relied-on curve raises confidence in that curve's own axis
    calibration), not as a from-scratch speed measurement."""
    log_exposure_at_h = speed_point_x(points, base_density, criterion=criterion)
    return k / (10.0 ** log_exposure_at_h)


def write_raw_and_qa(pdf_path, chart, result, out_dir):
    out_dir_raw = out_dir / "raw"
    out_dir_qa = out_dir / "qa"
    out_dir_raw.mkdir(parents=True, exist_ok=True)
    out_dir_qa.mkdir(parents=True, exist_ok=True)

    qa_path = out_dir_qa / f"{chart.chart_id}_qa_overlay.png"
    doc = fitz.open(pdf_path)
    render_qa_overlay([(chart, result["_qa_results"], result["_qa_calib"], doc[chart.page_index])], qa_path)
    doc.close()

    raw_out = dict(result)
    raw_out["qa_overlay_png"] = qa_path.name
    for k in ("_qa_results", "_qa_calib", "_qa_page_number"):
        raw_out.pop(k, None)
    (out_dir_raw / f"{chart.chart_id}.json").write_text(json.dumps(raw_out, indent=2))
    return qa_path


def write_single_dev_time_stock(
    *, out_root, stock, name, target_print, densitometer,
    log_sensitivity_density_over_min, reference_illuminant, viewing_illuminant,
    datasource, wavelengths, log_sensitivity, log_exposure,
    base_density_scalar, fit, dev_time_min,
):
    """Writes one fully self-contained single-development-time stock
    (n_dev=1 from the start, not collapsed from a wider family) to
    out_root/<stock>/profile.json -- the single darktable-loadable file
    (see spektra_profile.py's module docstring for why one file is now
    enough). `fit` is a density_model.NormCdfsFit already fit on this one
    development time's own net-density points (log_exposure grid is
    grids.LOG_EXPOSURE, the shared canonical grid)."""
    out_dir = out_root / stock
    out_dir.mkdir(parents=True, exist_ok=True)

    total = dm.evaluate_total(fit, log_exposure)                  # (256,)
    layers = dm.evaluate_layers(fit, log_exposure)                # (256,n_layers)
    density_curves = total[:, None]                               # (256,1)
    density_curves_layers = layers[:, :, None]                    # (256,n_layers,1)
    base_density = np.full((81, 1), base_density_scalar)
    density_curves_model = {
        "model_type": "norm_cdfs",
        "centers": fit.centers[None, :],
        "amplitudes": fit.amplitudes[None, :],
        "sigmas": fit.sigmas[None, :],
    }

    info = sp.build_info(
        stock=stock, name=name, type_="negative", support="film", stage="filming",
        use="still", antihalation="strong", target_print=target_print,
        channel_model="bw", densitometer=densitometer,
        log_sensitivity_density_over_min=log_sensitivity_density_over_min,
        reference_illuminant=reference_illuminant, viewing_illuminant=viewing_illuminant,
    )
    source_profile = sp.build_source_profile(
        info=info, datasource=datasource,
        wavelengths=wavelengths, log_sensitivity=log_sensitivity,
        channel_density_value=1.0, log_exposure=log_exposure,
        base_density=base_density, density_curves=density_curves,
        density_curves_layers=density_curves_layers,
        density_curves_model=density_curves_model, development_time=[dev_time_min],
    )
    sp.validate_source_profile(sp._json_safe(source_profile), n_dev_expected=1)

    pack_profile = sp.collapse_to_darktable_pack(source_profile)
    sp.validate_darktable_pack(pack_profile)
    sp.write_profile(out_dir / "profile.json", pack_profile)

    return source_profile, pack_profile, out_dir
