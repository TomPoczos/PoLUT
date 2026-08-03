#!/usr/bin/env bash
#
# Deploys every digitized profile.json under outputs/ (all films, all papers)
# into a darktable checkout's spektrafilm devconfig, so the spektrafilm module
# picks them up. See this project's own CLAUDE.md, "Deploying a profile to
# darktable for real testing", for why both destination directories below are
# required -- darktable's C loader (_resolve_pack_dir in spektrafilm.c)
# resolves from the hash-keyed packs/<hash>/ snapshot, not the top-level
# profiles/ dir directly, so a profile only copied to the top-level dir
# silently won't appear in darktable's film-stock list at all.
#
# "Registering" a profile is nothing more than the file existing under
# profiles/ in both locations: darktable's _scan_profiles() (spektrafilm.c)
# globs *.json out of <pack>/profiles/ itself at module-open time, there is no
# separate manifest/index file to edit. Restart darktable after running this
# either way -- there is no live reload.
#
# Usage:
#   ./import-to-dt.sh <path-to-darktable-checkout-or-configdir> [--dry-run]
#
# Examples:
#   ./import-to-dt.sh ~/code/darktable            # checkout root (has devconfig/)
#   ./import-to-dt.sh ~/code/darktable/devconfig   # configdir itself
#   ./import-to-dt.sh ~/.config/darktable          # a real (non-dev) install
#
# Run `uv run main.py` first to (re)build outputs/ -- this script only copies
# what's already there, it doesn't digitize or fit anything.

set -euo pipefail

usage() {
  echo "Usage: $0 <path-to-darktable-checkout-or-configdir> [--dry-run]" >&2
  exit 1
}

[[ $# -ge 1 ]] || usage

DT_PATH="$1"
DRY_RUN=0
if [[ "${2:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
OUTPUTS_DIR="$SCRIPT_DIR/outputs"

[[ -d "$OUTPUTS_DIR" ]] || {
  echo "error: $OUTPUTS_DIR does not exist -- run 'uv run main.py' first" >&2
  exit 1
}

# Resolve DT_PATH to the actual spektrafilm dir (the one holding pack.json +
# profiles/), accepting a checkout root, a --configdir, or the spektrafilm
# dir itself.
resolve_spektra_dir() {
  local base="$1"
  for candidate in "$base/devconfig/spektrafilm" "$base/spektrafilm" "$base"; do
    if [[ -f "$candidate/pack.json" && -d "$candidate/profiles" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

SPEKTRA_DIR="$(resolve_spektra_dir "$DT_PATH")" || {
  echo "error: couldn't find a spektrafilm pack (pack.json + profiles/) under" >&2
  echo "  $DT_PATH" >&2
  echo "  $DT_PATH/spektrafilm" >&2
  echo "  $DT_PATH/devconfig/spektrafilm" >&2
  echo "Pass the darktable checkout root, its --configdir, or the spektrafilm dir directly." >&2
  exit 1
}

echo "spektrafilm pack: $SPEKTRA_DIR"

# Destination profiles/ dirs: the top-level (hand-installed) one, plus every
# hash-keyed snapshot under packs/ -- both are real load paths, see header.
DEST_DIRS=("$SPEKTRA_DIR/profiles")
if [[ -d "$SPEKTRA_DIR/packs" ]]; then
  while IFS= read -r -d '' hash_dir; do
    if [[ -d "$hash_dir/profiles" ]]; then
      DEST_DIRS+=("$hash_dir/profiles")
    fi
  done < <(find "$SPEKTRA_DIR/packs" -mindepth 1 -maxdepth 1 -type d -print0)
fi

echo "destinations:"
for d in "${DEST_DIRS[@]}"; do echo "  $d"; done

# This script only ADDS profile.json files to an EXISTING pack -- it cannot
# create one. A real pack is pack.json + spectra_lut.f32 + profiles/ together;
# spectra_lut.f32 is the shared spectral-basis table the module's math runs
# on (see spektra_sim.c's sf_pack_lut_hash()/"spectra_lut.f32" reads) and
# isn't film-specific, so no profile.json this tool produces can substitute
# for it. It normally comes from a real spektrafilm release's own
# spektrafilm_export_data.py export (github.com/andreavolpato/spektrafilm --
# a separate project from darktable's spektrafilm *module*, confusingly
# same-named), a one-time setup step this script does not perform. Check every
# destination pack root, not just the top-level one -- a hash-keyed
# packs/<hash>/ snapshot missing its own spectra_lut.f32 is just as broken as
# the top-level dir missing it.
missing_lut=()
for d in "${DEST_DIRS[@]}"; do
  pack_root="$(dirname "$d")"
  [[ -f "$pack_root/spectra_lut.f32" ]] || missing_lut+=("$pack_root/spectra_lut.f32")
done
if [[ ${#missing_lut[@]} -gt 0 ]]; then
  echo "error: no spektrafilm data pack installed -- missing:" >&2
  for f in "${missing_lut[@]}"; do echo "  $f" >&2; done
  echo "This script only adds profile.json files to an EXISTING pack; it can't create" >&2
  echo "one. spectra_lut.f32 is the shared spectral table the whole pack (and every" >&2
  echo "profile in it) depends on -- install a real spektrafilm data pack first" >&2
  echo "(normally produced by spektrafilm_export_data.py from a spektrafilm release," >&2
  echo "github.com/andreavolpato/spektrafilm), then re-run this script to add to it." >&2
  exit 1
fi

# pack_format 2 is required for a rebuilt darktable to load anything from the
# pack at all (see this project's CLAUDE.md and spektra_profile.py's own
# schema-skew note) -- warn, don't silently proceed, if either pack.json is
# still on an older format.
for pj in "$SPEKTRA_DIR/pack.json" "$SPEKTRA_DIR"/packs/*/pack.json; do
  [[ -f "$pj" ]] || continue
  fmt="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('pack_format'))" "$pj" 2>/dev/null || echo "unreadable")"
  if [[ "$fmt" != "2" ]]; then
    echo "warning: $pj has pack_format=$fmt (expected 2) -- a rebuilt darktable may fail to load this pack at all" >&2
  fi
done

# Every deployable profile is a file literally named profile.json; its stock
# slug is its immediate parent directory's name (matches every products/*.py
# OUT_DIR convention -- see main.py's PRODUCTS dict and this project's own
# CLAUDE.md "Deploying a profile to darktable for real testing").
declare -A STOCK_SRC=()
while IFS= read -r -d '' src; do
  stock="$(basename "$(dirname "$src")")"
  if [[ -n "${STOCK_SRC[$stock]:-}" ]] && ! cmp -s "${STOCK_SRC[$stock]}" "$src"; then
    echo "error: two different profile.json files both map to stock '$stock':" >&2
    echo "  ${STOCK_SRC[$stock]}" >&2
    echo "  $src" >&2
    exit 1
  fi
  STOCK_SRC[$stock]="$src"
done < <(find "$OUTPUTS_DIR" -type f -name "profile.json" -print0)

if [[ ${#STOCK_SRC[@]} -eq 0 ]]; then
  echo "error: no profile.json files found under $OUTPUTS_DIR" >&2
  exit 1
fi

echo
echo "found ${#STOCK_SRC[@]} stock(s):"
for stock in "${!STOCK_SRC[@]}"; do echo "  $stock"; done | sort

echo
copied=0
for stock in "${!STOCK_SRC[@]}"; do
  src="${STOCK_SRC[$stock]}"

  if ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$src" 2>/dev/null; then
    echo "error: $src is not valid JSON, skipping" >&2
    continue
  fi

  for dest_dir in "${DEST_DIRS[@]}"; do
    dest="$dest_dir/$stock.json"
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "[dry-run] $src -> $dest"
    else
      cp "$src" "$dest"
      echo "$src -> $dest"
    fi
  done
  copied=$((copied + 1))
done

echo
if [[ $DRY_RUN -eq 1 ]]; then
  echo "dry run: would deploy $copied stock(s) to ${#DEST_DIRS[@]} location(s) each"
else
  echo "deployed $copied stock(s) to ${#DEST_DIRS[@]} location(s) each"
  echo "restart darktable for the new/updated profiles to be picked up (no live reload)"
fi
