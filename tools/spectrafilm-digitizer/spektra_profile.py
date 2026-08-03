"""
Builds spektrafilm/darktable profile JSON as plain dicts/numpy arrays against
the documented schema directly -- no parallel dataclass hierarchy duplicating
`spektrafilm/src/spektrafilm/profiles/io.py`'s `Profile`/`ProfileInfo`/
`ProfileData` (see the project plan's design decision #2: that would just be
a second thing to keep in sync with upstream as it evolves, for a shape with
no real behavior to reuse).

Two related, same-schema builders, feeding ONE file on disk per product
(`profile.json` -- see `write_single_dev_time_stock()`/`build_grade()`'s own
call sites). Before darktable's `pack_format` 2 (`~/code/darktable` commit
`eedbad83dc`, "support pack v2 files, fix Tri-X column layout to follow
upstream spektrafilM"), this used to be two files written to disk
(`profile.spektrafilm.json` + `profile.darktable.json`), because darktable's
C reader (`sf_profile_load` in `spektra_sim.c`) used to *guess* whether a BW
stock's `density_curves_model` outer axis was the development-time family or
a (fake, widened) channel axis from its row count alone -- wrong on at least
one real stock (Kodak Double-X, off by 1.34 density) and the exact bug this
project's own Tri-X profiles hit (named directly in the darktable commit
message). Pack format 2 fixed that specific ambiguity: `dev_major` is now
resolved from the profile's own declared `channel_model`, not the array
shape, so `density_curves_model` no longer needs to be pre-widened to 3
identical rows -- confirmed both by reading the current C source
(`spektra_sim.c`'s `sf_profile_load`, the `centers`/`amplitudes`/`sigmas`
block) and against real upstream profiles already in the installed devconfig
pack (`kodak_doublex.json`, a genuine 5-development-time family, ships
`density_curves_model.centers` shape `(5, 3)` = `(n_dev, n_layers)`,
un-widened, under this same `pack_format: 2` pack).

This does **not** mean the whole two-shape distinction disappeared, though --
only the specific ambiguity above did. `log_sensitivity`/`channel_density`
are still read unconditionally as `(SF_NWL, 3)` matrices by the C reader
(`json_read_dmatrix(data, "log_sensitivity", ..., SF_NWL, 3)`, untouched by
the pack-v2 commit and confirmed 3-wide even in real upstream BW profiles
like `kodak_doublex.json`/`kodak_2302.json`) -- there is no `channel_model`
escape hatch for these two fields, so a BW stock's single real channel still
has to be replicated into 3 identical columns for darktable to load the
file at all. And the raw digitized `density_curves`/`base_density` (not the
fitted `_model`) only get to skip pre-widening/pre-collapsing when a real,
multi-member `development_time` family is shipped (`n_dev > 1`, which
triggers the C reader's own runtime slice-and-widen path) -- every stock
this tool currently produces ships exactly one development time per file
(see `trix_common.py`'s own module docstring for why), so `n_dev == 1`
always, and these two fields still need the same widen/flatten treatment
they always did. `collapse_to_darktable_pack()` below reflects exactly this:
it drops the now-unnecessary `density_curves_model` widening, keeps
everything else.

- `build_source_profile()` -- spektrafilm's own "source profile" shape (what
  lives in `spektrafilm/src/spektrafilm/data/profiles/*.json` and what the
  Python package/GUI itself loads via `load_profile()`). For a B&W stock this
  is genuinely single-channel (log_sensitivity/channel_density carry ONE
  column, not three) and can carry a real multi-development-time family.
  Never written to disk as its own file anymore -- kept in memory only, as
  the input to `collapse_to_darktable_pack()` and to the external validation
  round-trip (`validate_external.py`), which still needs this exact
  un-widened shape since the newer installed `spektrafilm` package's own
  validator rejects a widened BW profile regardless of `pack_format`
  (see `validate_external.py`'s own docstring -- that skew is unrelated to
  today's darktable fix and still stands).
- `collapse_to_darktable_pack()` -- the shape actually written to disk as
  `profile.json` and read by darktable's C loader (`sf_profile_load` in
  `spektra_sim.c`). Still collapses a real development-time family to its
  middle representative (`idx = (len(times)-1)//2`, matching upstream's
  `select_development_time(None)`) and still widens `log_sensitivity`/
  `channel_density`/`density_curves` to 3 identical columns and flattens
  `base_density` to one value per wavelength -- all still genuinely required
  by the C reader, not a stale workaround. What it no longer does is widen
  `density_curves_model`'s rows: that field is written straight through in
  its real `(n_dev, n_layers)` shape now that `dev_major` no longer depends
  on guessing from it.
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
    """Collapses a development-time family (if any) to its middle
    representative and widens the fields darktable's C reader still requires
    3-wide/flat regardless of `pack_format` -- everything here except the
    (now-dropped) `density_curves_model` widening is a direct port of
    `spektrafilm_export_data.py`'s own BW collapse/widen block (see module
    docstring for the pack_format-2 history and which pieces of that port
    are still load-bearing vs. now unnecessary)."""
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

    # density_curves_model is NOT collapsed or widened anymore -- darktable's
    # pack_format 2 resolves its outer axis from channel_model (dev_major=bw)
    # rather than guessing from row count, so the real, un-widened
    # (n_dev, n_layers) shape `build_source_profile()` already produced loads
    # correctly as-is (see module docstring). Left fully intact here.

    # widen: 1-column -> 3 identical columns for log_sensitivity/density_curves
    # (still required unconditionally by the C reader -- see module docstring)
    for key in ("log_sensitivity", "density_curves"):
        if key in d and d[key] and len(d[key][0]) == 1:
            d[key] = _widen3_rows(d[key])

    # channel_density: 1-column -> 3 identical columns, each = value/3
    cd = d.get("channel_density")
    if cd and len(cd[0]) == 1:
        d["channel_density"] = [
            [None if row[0] is None else row[0] / 3.0] * 3 for row in cd
        ]

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
    # density_curves_model is intentionally left un-widened (pack_format 2,
    # dev_major resolved from channel_model -- see module docstring): its
    # outer axis is the (collapsed, length-1) development_time family, not a
    # channel axis, so `centers` has exactly one real row, not 3.
    model = d["density_curves_model"]
    assert len(model["centers"]) == len(dev_times), \
        "density_curves_model outer axis must match the (collapsed) development_time family"
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
