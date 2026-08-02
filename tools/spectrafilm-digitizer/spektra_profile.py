"""
Builds spektrafilm/darktable profile JSON as plain dicts/numpy arrays against
the documented schema directly -- no parallel dataclass hierarchy duplicating
`spektrafilm/src/spektrafilm/profiles/io.py`'s `Profile`/`ProfileInfo`/
`ProfileData` (see the project plan's design decision #2: that would just be
a second thing to keep in sync with upstream as it evolves, for a shape with
no real behavior to reuse).

Two related, same-schema outputs, for two different real consumers:

- `build_source_profile()` -- spektrafilm's own "source profile" shape (what
  lives in `spektrafilm/src/spektrafilm/data/profiles/*.json` and what the
  Python package/GUI itself loads via `load_profile()`). For a B&W stock this
  is genuinely single-channel (log_sensitivity/channel_density carry ONE
  column, not three) and can carry a real multi-development-time family.
- `collapse_to_darktable_pack()` -- the shape actually written into
  `devconfig/spektrafilm/profiles/*.json` and read by darktable's C loader
  (`sf_profile_load` in `spektra_sim.c`). This is a **direct port** of
  `spektrafilm_export_data.py`'s own BW collapse/widen block (read from
  `~/code/spektrafilm-export-data/spektrafilm_export_data.py`, function
  `main()`, the "stock profiles" section) -- not a hand-derived
  approximation. That script's own comment explains why the collapse step
  exists: shipping a real, uncollapsed development-time family straight
  through to darktable previously produced a confirmed bug ("kodak_2302...
  renders blank white"), because the C loader would sum every development
  time's fitted curve together as if they were legitimate sub-layers of one
  curve. Porting the exact algorithm (rather than re-deriving the collapsed
  shape by hand) is what guarantees our darktable-facing file avoids that
  same class of bug.
"""

import copy
import json
from datetime import date

import numpy as np

PROFILE_TYPES = frozenset({"negative", "positive"})
PROFILE_SUPPORTS = frozenset({"film", "paper"})
PROFILE_STAGES = frozenset({"filming", "printing"})
PROFILE_USES = frozenset({"still", "cine"})
PROFILE_ANTIHALATION = frozenset({"strong", "weak", "no"})
PROFILE_CHANNEL_MODELS = frozenset({"color", "bw"})


def _json_safe(obj):
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _json_safe(obj.tolist())
    if isinstance(obj, (np.floating,)):
        obj = float(obj)
    if isinstance(obj, float) and np.isnan(obj):
        return None
    return obj


def write_profile(path, profile: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(profile), indent=2))


def build_metadata(datasource: str) -> dict:
    """Independent-authorship metadata (project plan decision #3) -- this
    profile is digitized directly from a public Kodak datasheet, not derived
    from spektrafilm's own CC-BY-SA-licensed dataset, so it doesn't carry
    Andrea Volpato's copyright/license text."""
    return {
        "version": "0.1.0",
        "copyright": f"Copyright (c) {date.today().year} the PoLUT project.",
        "created": date.today().isoformat(),
        "license": "Digitized independently from a public Eastman Kodak Company "
                    "datasheet (see datasource); not derived from spektrafilm's own "
                    "CC-BY-SA-licensed profile dataset.",
        "citation": "",
        "datasource": datasource,
    }


def build_info(*, stock, name, type_, support, stage, use, antihalation,
               target_print, channel_model, densitometer,
               log_sensitivity_density_over_min, reference_illuminant,
               viewing_illuminant) -> dict:
    assert type_ in PROFILE_TYPES, type_
    assert support in PROFILE_SUPPORTS, support
    assert stage in PROFILE_STAGES, stage
    assert use in PROFILE_USES, use
    assert antihalation in PROFILE_ANTIHALATION, antihalation
    assert channel_model in PROFILE_CHANNEL_MODELS, channel_model
    return {
        "stock": stock, "name": name, "type": type_, "support": support,
        "stage": stage, "use": use, "antihalation": antihalation,
        "target_print": target_print, "channel_model": channel_model,
        "densitometer": densitometer,
        "log_sensitivity_density_over_min": log_sensitivity_density_over_min,
        "reference_illuminant": reference_illuminant,
        "viewing_illuminant": viewing_illuminant,
    }


def build_source_profile(
    *, info: dict, datasource: str,
    wavelengths: np.ndarray,           # (81,)
    log_sensitivity: np.ndarray,       # (81,) or (81,1) -- one column, BW
    channel_density_value: float,      # scalar, normally 1.0 for a single-emulsion BW stock
    log_exposure: np.ndarray,          # (256,)
    base_density: np.ndarray,          # (81, n_dev)
    density_curves: np.ndarray,        # (256, n_dev)
    density_curves_layers: np.ndarray,  # (256, n_layers, n_dev)
    density_curves_model: dict,        # {model_type, centers/amplitudes/sigmas: (n_dev, n_layers)}
    development_time: list,            # length n_dev, ASCENDING (collapse picks the middle position)
) -> dict:
    assert info["channel_model"] == "bw"
    wavelengths = np.asarray(wavelengths, dtype=float)
    log_sensitivity = np.asarray(log_sensitivity, dtype=float).reshape(-1, 1)
    log_exposure = np.asarray(log_exposure, dtype=float)
    base_density = np.asarray(base_density, dtype=float)
    density_curves = np.asarray(density_curves, dtype=float)
    density_curves_layers = np.asarray(density_curves_layers, dtype=float)

    n_dev = len(development_time)
    assert list(development_time) == sorted(development_time), \
        "development_time must be ascending -- the collapse step picks the middle *position*"
    assert wavelengths.shape == (81,)
    assert log_exposure.shape == (256,)
    assert log_sensitivity.shape == (81, 1)
    assert base_density.shape == (81, n_dev)
    assert density_curves.shape == (256, n_dev)
    assert density_curves_layers.shape[0] == 256 and density_curves_layers.shape[2] == n_dev
    for key in ("centers", "amplitudes", "sigmas"):
        arr = np.asarray(density_curves_model[key])
        assert arr.shape[0] == n_dev, f"density_curves_model.{key} outer axis must be development_time ({n_dev})"

    channel_density = np.full((81, 1), float(channel_density_value))

    return {
        "metadata": build_metadata(datasource),
        "info": info,
        "data": {
            "wavelengths": wavelengths,
            "log_sensitivity": log_sensitivity,
            "channel_density": channel_density,
            "base_density": base_density,
            "midscale_neutral_density": None,
            "log_exposure": log_exposure,
            "density_curves": density_curves,
            "density_curves_layers": density_curves_layers,
            "density_curves_model": {
                "model_type": density_curves_model["model_type"],
                "centers": np.asarray(density_curves_model["centers"]),
                "amplitudes": np.asarray(density_curves_model["amplitudes"]),
                "sigmas": np.asarray(density_curves_model["sigmas"]),
            },
            "development_time": list(development_time),
        },
    }


def _widen3_rows(rows):
    """[[v], [v], ...] -> [[v,v,v], [v,v,v], ...] -- spektrafilm_export_data.py's
    `row * 3` (Python list repetition on a 1-element list)."""
    return [list(row) * 3 for row in rows]


def collapse_to_darktable_pack(source_profile: dict) -> dict:
    """Direct port of spektrafilm_export_data.py's BW stock-profile
    collapse+widen block (see module docstring) -- operates on the same
    JSON-shaped dict `build_source_profile()` produces (already run through
    `_json_safe`-equivalent plain lists), not on numpy arrays, to stay a
    faithful line-for-line port rather than a reimplementation in a
    different data representation."""
    prof = copy.deepcopy(_json_safe(source_profile))
    assert prof["info"]["channel_model"] == "bw"
    d = prof["data"]

    times = d.get("development_time") or []
    curves = d.get("density_curves") or []
    assert len(times) >= 1 and curves and len(curves[0]) == len(times), \
        "collapse_to_darktable_pack expects development_time to match density_curves' column count"
    # len(times) == 1 is the legitimate "no real family, one representative
    # curve" case (e.g. a paper whose only real varying axis -- contrast
    # grade/filter -- isn't development time at all, so there's nothing to
    # expose via this mechanism; see products/kodak_polymax_fine_art.py's own
    # docstring). idx==0 falls out of the same formula with no special case
    # needed: collapsing a length-1 "family" to its only member.

    idx = (len(times) - 1) // 2  # matches upstream's select_development_time(None)

    d["density_curves"] = [[row[idx]] for row in curves]

    base = d.get("base_density")
    d["base_density"] = [row[idx] for row in base]

    layers = d.get("density_curves_layers")
    d["density_curves_layers"] = [[[lay[idx]] for lay in row] for row in layers]

    d["development_time"] = [times[idx]]

    model = d.get("density_curves_model")
    for key in ("centers", "amplitudes", "sigmas", "alphas"):
        arr = model.get(key)
        if arr and len(arr) == len(times):
            model[key] = [arr[idx]]

    # widen: 1-column -> 3 identical columns for log_sensitivity/density_curves
    for key in ("log_sensitivity", "density_curves"):
        if key in d and d[key] and len(d[key][0]) == 1:
            d[key] = _widen3_rows(d[key])

    # channel_density: 1-column -> 3 identical columns, each = value/3
    cd = d.get("channel_density")
    if cd and len(cd[0]) == 1:
        d["channel_density"] = [
            [None if row[0] is None else row[0] / 3.0] * 3 for row in cd
        ]

    # density_curves_model: the one collapsed row repeated 3x (channel-major)
    for key in ("centers", "amplitudes", "sigmas", "alphas"):
        arr = model.get(key)
        if arr and len(arr) == 1:
            model[key] = arr * 3

    return prof


# ---------------------------------------------------------------------------
# Structural validation -- mirrors what actually consumes each file, not a
# generic schema checker. The source-profile checks mirror
# spektrafilm.profiles.io.ProfileData's own array shapes (adapted for the
# family case); the pack checks mirror darktable's C reader
# (spektra_sim.c: sf_profile_load, json_read_darray/json_read_dmatrix)
# exactly -- SF_NWL=81, SF_NLE=256, exact-length requirement, channel-major
# (n,3) shapes, single development_time.
# ---------------------------------------------------------------------------

def validate_darktable_pack(profile: dict):
    d = profile["data"]
    assert len(d["wavelengths"]) == 81
    assert len(d["log_exposure"]) == 256
    assert len(d["log_sensitivity"]) == 81 and all(len(r) == 3 for r in d["log_sensitivity"])
    assert len(d["channel_density"]) == 81 and all(len(r) == 3 for r in d["channel_density"])
    assert len(d["base_density"]) == 81 and all(not isinstance(v, list) for v in d["base_density"])
    assert len(d["density_curves"]) == 256 and all(len(r) == 3 for r in d["density_curves"])
    dev_times = d.get("development_time") or []
    assert len(dev_times) == 1, "darktable pack profile must be collapsed to a single development_time"
    model = d["density_curves_model"]
    assert len(model["centers"]) == 3, "channel-major widening expected (3 identical rows)"
    n_layers = len(model["centers"][0])
    assert len(model["amplitudes"][0]) == n_layers and len(model["sigmas"][0]) == n_layers


def validate_source_profile(profile: dict, n_dev_expected: int):
    d = profile["data"]
    assert len(d["wavelengths"]) == 81
    assert len(d["log_exposure"]) == 256
    assert len(d["log_sensitivity"]) == 81 and all(len(r) == 1 for r in d["log_sensitivity"])
    assert len(d["channel_density"]) == 81 and all(len(r) == 1 for r in d["channel_density"])
    assert len(d["base_density"]) == 81 and all(len(r) == n_dev_expected for r in d["base_density"])
    assert len(d["density_curves"]) == 256 and all(len(r) == n_dev_expected for r in d["density_curves"])
    dev_times = d.get("development_time") or []
    assert len(dev_times) == n_dev_expected
    assert list(dev_times) == sorted(dev_times)
    model = d["density_curves_model"]
    assert len(model["centers"]) == n_dev_expected
