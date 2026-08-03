"""
Runs the pre-collapse `build_source_profile()` shape (the real
development-time family, spektrafilm's own "source profile" shape) through
the REAL, installed `spektrafilm` package as an external validation oracle --
authoritative correctness from the actual dependency, not a reimplementation
of it (see project plan design decision #2). Since spektra_profile.py stopped
writing that shape to disk as its own file (only the collapsed/widened
`profile.json` is written now -- see that module's docstring for why one
file is enough as of darktable's pack_format 2), `validate_spektrafilm_source_profile()`
takes the in-memory dict directly and round-trips it through a temp file
instead of reading a persisted `profile.spektrafilm.json`.

Shells out to `~/venv-spektrafilm-dev/bin/python` (the venv
`refresh-spektrafilm-profiles.sh` already maintains for exactly this kind of
task -- see that script) rather than adding `spektrafilm` and its full
runtime (colour-science, numba, rawpy, exiv2, lensfunpy, PySide6, napari,
OpenImageIO...) to this tool's own venv.

Note: the module path differs from what `~/code/spektrafilm`'s (0.3.4, main
branch) source tree suggests (`spektrafilm.profiles.io`) -- the actually
*installed* venv is pinned to a `dev`-branch snapshot (0.3.3) that has since
restructured to `spektrafilm.data.profiles_loader`. We validate against
whichever module is actually importable in that venv (found via a small
probe), since that's the real, running dependency.

IMPORTANT, confirmed by direct testing (not assumed): only the pre-collapse
source shape is meaningfully checked here. The installed `profiles_loader`'s
`_validate_profile` has moved *ahead* of darktable's own bundled C reader --
it now expects a BW stock's `log_sensitivity`/`channel_density` to stay
single-column (`n_channels == 1`, a property derived from `channel_model`),
never widened to 3 identical RGB columns. darktable's `spektra_sim.c`
(`json_read_dmatrix(..., SF_NWL, 3)`) is still on the *older* always-3-columns
convention for exactly these two fields -- confirmed unconditional, and
confirmed unchanged by the pack_format-2 commit that fixed the separate
`density_curves_model` ambiguity (see spektra_profile.py's module docstring)
-- and rejects (or rather, the Python validator rejects) our correctly-widened
`profile.json` for exactly that reason -- a real, confirmed skew between the
two consumers' current schema versions, not a bug in our output. So
`profile.json` is validated instead by `spektra_profile.validate_darktable_pack()`,
which mirrors the C reader's own requirements directly (see that function) --
the authoritative check for the file that actually matters to darktable.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import spektra_profile as sp

VENV_PYTHON = Path.home() / "venv-spektrafilm-dev" / "bin" / "python"

_PROBE = r"""
import importlib, json, sys
candidates = ["spektrafilm.profiles.io", "spektrafilm.data.profiles_loader"]
mod = None
for name in candidates:
    try:
        mod = importlib.import_module(name)
        break
    except ImportError:
        continue
if mod is None:
    print(json.dumps({"ok": False, "error": f"none of {candidates} importable"}))
    sys.exit(1)

data = json.load(open(sys.argv[1]))
try:
    profile = mod.profile_from_dict(data)
    mod._validate_profile(profile, data.get("info", {}).get("stock", "?"))
except Exception as exc:  # noqa: BLE001 -- report, don't crash the subprocess
    print(json.dumps({"ok": False, "module": name, "error": f"{type(exc).__name__}: {exc}"}))
    sys.exit(0)

print(json.dumps({
    "ok": True, "module": name,
    "wavelengths_n": int(profile.data.wavelengths.shape[0]),
    "log_exposure_n": int(profile.data.log_exposure.shape[0]),
    "density_curves_shape": list(profile.data.density_curves.shape),
    "is_negative": profile.is_negative, "is_bw": profile.is_bw,
}))
"""


def validate_spektrafilm_source_externally(profile_path: Path) -> dict:
    """Standalone/CLI entry point: validates an already-written profile file
    on disk. Kept for `uv run validate_external.py <profile.json>` -- see
    module docstring's CLI usage note in the tool's own CLAUDE.md."""
    if not VENV_PYTHON.exists():
        return {"ok": False, "error": f"{VENV_PYTHON} not found -- skipping external validation"}
    result = subprocess.run(
        [str(VENV_PYTHON), "-c", _PROBE, str(profile_path)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0 and not result.stdout.strip():
        return {"ok": False, "error": f"subprocess failed: {result.stderr.strip()[-2000:]}"}
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"ok": False, "error": f"unparseable output: {result.stdout!r} {result.stderr!r}"}


def validate_spektrafilm_source_profile(source_profile: dict) -> dict:
    """In-memory variant for main.py: `source_profile` (build_source_profile()'s
    own return value, not yet written to disk anywhere) is round-tripped
    through a scratch temp file so `validate_spektrafilm_source_externally()`'s
    subprocess-based check can run against it without spektra_profile.py ever
    persisting the pre-collapse shape as its own file under outputs/."""
    if not VENV_PYTHON.exists():
        return {"ok": False, "error": f"{VENV_PYTHON} not found -- skipping external validation"}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(sp._json_safe(source_profile), f)
        tmp_path = Path(f.name)
    try:
        return validate_spektrafilm_source_externally(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    report = validate_spektrafilm_source_externally(Path(sys.argv[1]))
    print(json.dumps(report, indent=2))
    sys.exit(0 if report.get("ok") else 1)
