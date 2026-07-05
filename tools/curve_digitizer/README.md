# curve-digitizer

Extracts H&D / spectral-sensitivity curve data from Kodak/Eastman PDF
datasheets that plot the curves as vector paths (as opposed to a scanned
raster image). Reads the actual PDF drawing commands for each colored curve
directly, so extraction accuracy isn't limited by rendering DPI - it's as
precise as the original document's own vector geometry.

## How it works

1. `fit_axis()` finds every tick-label text object on the page (e.g. "-3.00",
   "0.00", ...) via `page.get_text("words")`, and least-squares fits a
   pixel -> data-value linear mapping from their bounding-box centers.
2. `extract_curve_points()` walks `page.get_drawings()` and collects every
   path vertex belonging to a fill of a given RGB color (each curve in these
   datasheets is drawn as its own solid/dashed/dash-dot color: blue, olive
   "green", red), skipping any vertex inside the legend swatch box.
3. `bin_average()` bins those raw vertices by x and averages y per bin, which
   collapses stroke-width thickness and dash/dash-dot gaps down to a single
   clean centerline, then linearly interpolates any remaining gaps onto a
   dense (400-point) uniform grid.
4. If `ChartSpec.monotonic_direction` is set ("increasing"/"decreasing"),
   `isotonic_regression()` (Pool Adjacent Violators) is applied to the dense
   curve first. Use this only for charts that are a real monotonic material
   property (density vs. exposure) - leave it `None` for anything with a
   genuine non-monotonic shape (e.g. a spectral sensitivity peak), where
   "violations" are the real curve, not noise to remove.
5. `simplify_to_target()` downsamples the dense curve to ~20-30 points via
   Ramer-Douglas-Peucker, binary-searching epsilon to hit that range. This
   matches the point count every other curve in `generate_film_looks.py`
   already uses (~15-40 hand-picked points), and gives adaptive spacing
   (denser at toes/knees/shoulders, sparse on straight runs) rather than a
   naive uniform grid. Note RDP alone *preserves* whatever point deviates
   most from a straight-line fit in each segment - on a noisy curve that's
   as likely to be a jitter spike as real curve shape, which is exactly why
   step 4 (monotonicity enforcement) has to happen *before* simplification,
   not after: a subsequence of an isotonic sequence is still isotonic, so
   simplifying an already-monotonic dense curve keeps it monotonic, but
   simplifying first and fixing monotonicity after does not reliably work.
6. `render_qa_overlay()` re-renders the source page at 4x and draws both the
   raw dense trace (thin, faint) and the final simplified points (markers)
   back on top, so you can visually confirm the simplified curve still sits
   on the original line before trusting it - not just the dense trace, since
   that's not what actually ends up in the output.

## Usage

```
uv run main.py
```

Edit the `CHARTS` list in `main.py` to point at a different PDF/page/curve
set - it needs: the page index, a regex matching that chart's tick-label
text, the fill RGB (from `page.get_drawings()`) for each curve, and a
`film_id` (a path relative to `film_paper_filter_data/`, e.g.
`films/color/internegative/kodak_internegative_ii_5272`) that doubles as the
output directory and filename prefix. The source PDF itself must already
live in the repo-root `papers/` folder (reference documents, not derived
data - `main.py`'s `PDF_DIR` points there).

## Output

Results are written directly into the film's canonical folder under
`film_paper_filter_data/`, not into this tool directory and not next to the
source PDF: `<film_id>_<chart_id>.json` - axis calibration, the final
simplified `points` per curve (what should get transcribed into
`generate_film_looks.py`), the dense pre-simplification `points_dense` (kept
for reference/QA, not meant to be transcribed), and `n_violations`/
`likely_direction` diagnostics. `<film_id>_<chart_id>_qa_overlay.png` -
visual QA render: faint raw trace + simplified points as markers, on top of
the original page.

## Currently digitized

`papers/kodak_internegative_ii_5272_TI1301.pdf` (repo-root `papers/` folder;
EASTMAN Color Internegative II Film 5272/7272 - the film explicitly built
for making internegatives from reversal/slide originals):
- `characteristic_curve` - page 6 ("CHARACTERISTIC, For Publication"):
  Density vs. Log Exposure, 3 layers, `monotonic_direction="increasing"`.
  25-29 points/layer after simplification, 0 monotonicity violations.
- `spectral_sensitivity` - page 7 ("SPECTRAL SENSITIVITY, For Publication"):
  Log Sensitivity vs. Wavelength (nm), 3 layers, no monotonicity enforcement
  (real peak shape). 21-26 points/layer after simplification.

Both validated by eye against the QA overlay. Measured film gamma from the
characteristic curve (regression slope over the middle 60% of each layer's
exposure range) is 0.527, matching the pre-simplification dense-curve
measurement of 0.529 to within noise - simplification preserves the real
curve shape, it doesn't just make the numbers different.
