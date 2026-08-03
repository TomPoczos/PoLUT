#!/bin/sh
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
#
# Deliberately plain POSIX sh, not bash, for portability (no arrays, no
# [[ ]], no local, no process substitution) -- everything that needs to
# survive across a loop or a subshell is kept in a scratch file under
# WORKDIR instead of a shell variable/array. Two consequences of that
# trade-off, both standard for POSIX sh scripts and accepted deliberately:
# path lists are newline-separated (a profile.json path containing a literal
# newline would misparse -- not a real concern on this project's own
# outputs/ tree), and `mktemp -d` is used for the scratch dir even though
# POSIX itself doesn't specify mktemp, because every real sh (dash, ash/
# busybox, ksh, macOS's sh) ships one and there's no safer POSIX-blessed way
# to get a private scratch directory.

set -eu

usage() {
  echo "Usage: $0 <path-to-darktable-checkout-or-configdir> [--dry-run]" >&2
  exit 1
}

[ $# -ge 1 ] || usage

DT_PATH=$1
DRY_RUN=0
if [ "${2:-}" = "--dry-run" ]; then
  DRY_RUN=1
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd -P)
OUTPUTS_DIR="$SCRIPT_DIR/outputs"

if [ ! -d "$OUTPUTS_DIR" ]; then
  echo "error: $OUTPUTS_DIR does not exist -- run 'uv run main.py' first" >&2
  exit 1
fi

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT INT TERM

# Resolve DT_PATH to the actual spektrafilm dir (the one holding pack.json +
# profiles/), accepting a checkout root, a --configdir, or the spektrafilm
# dir itself.
SPEKTRA_DIR=""
for candidate in "$DT_PATH/devconfig/spektrafilm" "$DT_PATH/spektrafilm" "$DT_PATH"; do
  if [ -f "$candidate/pack.json" ] && [ -d "$candidate/profiles" ]; then
    SPEKTRA_DIR=$candidate
    break
  fi
done

if [ -z "$SPEKTRA_DIR" ]; then
  echo "error: couldn't find a spektrafilm pack (pack.json + profiles/) under" >&2
  echo "  $DT_PATH" >&2
  echo "  $DT_PATH/spektrafilm" >&2
  echo "  $DT_PATH/devconfig/spektrafilm" >&2
  echo "Pass the darktable checkout root, its --configdir, or the spektrafilm dir directly." >&2
  exit 1
fi

echo "spektrafilm pack: $SPEKTRA_DIR"

# Destination profiles/ dirs: the top-level (hand-installed) one, plus every
# hash-keyed snapshot under packs/ -- both are real load paths, see header.
# Kept as a newline-separated file (DEST_LIST), not a shell array, so it can
# be replayed with a `while read` loop as many times as needed below.
DEST_LIST="$WORKDIR/dest_dirs"
: > "$DEST_LIST"
echo "$SPEKTRA_DIR/profiles" >> "$DEST_LIST"
if [ -d "$SPEKTRA_DIR/packs" ]; then
  for hash_dir in "$SPEKTRA_DIR"/packs/*/; do
    [ -d "$hash_dir" ] || continue
    hash_dir=${hash_dir%/}
    if [ -d "$hash_dir/profiles" ]; then
      echo "$hash_dir/profiles" >> "$DEST_LIST"
    fi
  done
fi

echo "destinations:"
while IFS= read -r d; do echo "  $d"; done < "$DEST_LIST"

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
MISSING_LUT="$WORKDIR/missing_lut"
: > "$MISSING_LUT"
while IFS= read -r d; do
  pack_root=$(dirname "$d")
  if [ ! -f "$pack_root/spectra_lut.f32" ]; then
    echo "$pack_root/spectra_lut.f32" >> "$MISSING_LUT"
  fi
done < "$DEST_LIST"

if [ -s "$MISSING_LUT" ]; then
  echo "error: no spektrafilm data pack installed -- missing:" >&2
  while IFS= read -r f; do echo "  $f" >&2; done < "$MISSING_LUT"
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
  [ -f "$pj" ] || continue
  fmt=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('pack_format'))" "$pj" 2>/dev/null || echo "unreadable")
  if [ "$fmt" != "2" ]; then
    echo "warning: $pj has pack_format=$fmt (expected 2) -- a rebuilt darktable may fail to load this pack at all" >&2
  fi
done

# Every deployable profile is a file literally named profile.json; its stock
# slug is its immediate parent directory's name (matches every products/*.py
# OUT_DIR convention -- see main.py's PRODUCTS dict and this project's own
# CLAUDE.md "Deploying a profile to darktable for real testing"). Stock ->
# source-path is recorded as one file per stock under STOCKS_DIR (filename =
# stock slug, contents = source path) instead of an associative array, since
# POSIX sh has none; a stock slug is always a plain directory basename, so
# it's already safe to reuse as a filename.
STOCKS_DIR="$WORKDIR/stocks"
mkdir -p "$STOCKS_DIR"

find "$OUTPUTS_DIR" -type f -name "profile.json" > "$WORKDIR/found_profiles"

while IFS= read -r src; do
  stock=$(basename "$(dirname "$src")")
  map_file="$STOCKS_DIR/$stock"
  if [ -f "$map_file" ]; then
    existing=$(cat "$map_file")
    if ! cmp -s "$existing" "$src"; then
      echo "error: two different profile.json files both map to stock '$stock':" >&2
      echo "  $existing" >&2
      echo "  $src" >&2
      exit 1
    fi
    continue
  fi
  printf '%s\n' "$src" > "$map_file"
done < "$WORKDIR/found_profiles"

stock_count=0
for map_file in "$STOCKS_DIR"/*; do
  [ -f "$map_file" ] || continue
  stock_count=$((stock_count + 1))
done

if [ "$stock_count" -eq 0 ]; then
  echo "error: no profile.json files found under $OUTPUTS_DIR" >&2
  exit 1
fi

echo
echo "found $stock_count stock(s):"
for map_file in "$STOCKS_DIR"/*; do
  [ -f "$map_file" ] || continue
  basename "$map_file"
done | sort

echo
copied=0
for map_file in "$STOCKS_DIR"/*; do
  [ -f "$map_file" ] || continue
  stock=$(basename "$map_file")
  src=$(cat "$map_file")

  if ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$src" 2>/dev/null; then
    echo "error: $src is not valid JSON, skipping" >&2
    continue
  fi

  while IFS= read -r dest_dir; do
    dest="$dest_dir/$stock.json"
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "[dry-run] $src -> $dest"
    else
      cp "$src" "$dest"
      echo "$src -> $dest"
    fi
  done < "$DEST_LIST"
  copied=$((copied + 1))
done

dest_count=0
while IFS= read -r d; do
  dest_count=$((dest_count + 1))
done < "$DEST_LIST"

echo
if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry run: would deploy $copied stock(s) to $dest_count location(s) each"
else
  echo "deployed $copied stock(s) to $dest_count location(s) each"
  echo "restart darktable for the new/updated profiles to be picked up (no live reload)"
fi
