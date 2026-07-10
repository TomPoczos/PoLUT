# Blocked / out-of-scope source files

Tracks PDFs (or specific panels within a PDF) in `papers/125pixcom/` that
were investigated and found genuinely not extractable with the current
tool, or genuinely contain no digitizable curve data — as opposed to items
that are simply not yet done. Each entry records what was tried and why it
failed, so a future session (or a future capability added to the tool)
doesn't have to re-derive the same conclusion from scratch.

This file does NOT track "not yet started" work — only things actively
investigated and confirmed blocked/out-of-scope.

## Genuinely blocked (real curve data exists, but not extractable)

### ~~Fuji "Characteristic Curves" panel — vector paths, but zero extractable
### tick/label text (9 files)~~ — RESOLVED 2026-07-05
- **Files**: `film/fuji/velvia_100_datasheet.pdf`, `sensia_200_datasheet.pdf`,
  `sensia_400_datasheet.pdf`, `pro_400h_datasheet.pdf`, `pro_800z_datasheet.pdf`,
  `pro_160c_datasheet.pdf`, `pro_160s_datasheet.pdf`, `superia_reala_datasheet.pdf`,
  `superia_xtra800_datasheet.pdf`
- **Was blocked because**: same class of blocker as Ilford Multigrade above
  — real vector curve traces exist (confirmed via `extract_traces_in_region`),
  but the axis ticks and the "Red"/"Green"/"Blue" curve-identifying labels
  are vector-drawn shapes, not embedded font text (zero words returned by a
  direct search of the panel region on every file checked). Distinguished
  from the raster-image group below by checking `page.get_images()` --
  these files have zero images in that column, confirming the chart really
  is vector paths, just unlabeled ones.
- **How it was unblocked**: OCR, via a new `ocr_helpers.py` module
  (`pytesseract` + system `tesseract` 5.5.2, added to the `uv` project) —
  confirmed the user's recommendation that tesseract (not a heavier
  PyTorch-based OCR engine) was right for this: crisp, computer-rendered
  vector typography, not scanned/handwritten text. Two distinct sub-problems,
  solved differently:
  - **Axis ticks**: `ocr_words_in_region()` renders a tick row/column at
    high DPI and returns page-coordinate-mapped words, a drop-in substitute
    for `page.get_text("words")` that plugs straight into nothing-changed
    `fit_axis()`-adjacent logic (actually a simpler bespoke `ocr_axis_calib()`,
    since `fit_axis()`'s clustering/outlier-rejection machinery wasn't needed
    once tick candidates were already scoped to a tight bbox). Two OCR
    failure modes discovered and corrected for: (a) the minus sign is
    dropped unreliably — sometimes one tick in five, sometimes three of
    five — fixed by brute-forcing every sign combination for non-negative-
    read candidates and keeping whichever combination best fits a straight
    line (real ticks are an evenly-spaced arithmetic sequence, so the
    correct combination fits far better than any wrong one); (b) tesseract
    sometimes splits one tick at the decimal point into two word fragments
    ("-2.0" -> "-2" + "0") — fixed by merging adjacent same-row fragments
    with a small gap before regex-matching.
  - **Curve identity** (R/G/B), two different templates needed two
    different mechanisms:
    - `fuji_ocr_product` (Pro 400H/800Z/160C/160S, Superia Reala/X-tra 800):
      the rotated inline "Red"/"Green"/"Blue" labels (tilted to follow each
      curve's local slope) turned out to be unreliable to OCR directly even
      with a rotation-angle search — systematically drops the leading
      capital ("Blue"->"lue"), and the labels sit close enough together
      diagonally that a hand-picked crop box for one routinely clips its
      neighbor. Solved instead via RANK ORDER: checked all 7
      already-digitized Fuji color films and found EVERY negative film
      shows Blue>Green>Red by density (top-to-bottom on the chart) and
      EVERY reversal film shows the reverse, Red>Green>Blue, no
      exceptions — a real, empirically-verified Fuji house convention, so
      `film_type` alone determines label order; no per-word OCR needed.
    - `fuji_ocr_dash_reversal_product` (Velvia 100, Sensia 200/400): a
      different template where the 3 curves are position-ambiguous
      (near-overlapping for most of their range) but style-disambiguated
      (solid/dash/dash-dot line, confirmed by rendering and reading the
      legend box directly) — real Strategy B (`vector_stroke_dash`,
      dash-pattern matching) territory, same mechanism Kodak already uses,
      no OCR or rank-order needed for curve identity at all, just for axis
      ticks. This surfaced two real, separate `digitizer_core.py` bugs/gaps
      fixed along the way: `extract_curve_points_by_stroke()` had no
      `region_bbox` scoping at all (unlike Strategy D) and so matched
      gridlines/frame lines and an unrelated same-styled chart elsewhere on
      the same page — added an optional `region_bbox` parameter, defaulting
      to `None` so every existing (Kodak) call site is unaffected; and the
      dash-pattern regexes needed to match by NUMBER of dash values (2 vs 4)
      rather than exact numbers, since the specific values differ file to
      file (Velvia 100: `[3 1.5]`/`[8.999 1.5 2.5 1.5]`; Sensia 200/400:
      `[3.5 2]`/`[8.999 2 3 2]` or `[9 2 3 2]`).
  Also added `CurveSpec.label_position_override` (a hand-specified
  `(x, y)` bypassing `label_regex`/`find_label_position()` entirely) to
  support feeding the rank-order convention's synthetic ordered positions
  into the existing `assign_traces_to_labels_exclusive()` machinery
  unchanged.
  All 9 files verified via QA overlay before being added to
  `fuji_still.py`'s real `PRODUCTS` list; corpus-wide `audit_calibration.py`
  clean at 156 files (up from 147).

### Fuji "Characteristic Curves" panel — embedded raster image
- **Resolved 2026-07-05/06 for 5 of 6 files**: `velvia_50_datasheet.pdf`,
  `provia_100f_datasheet.pdf`, `RTPIIAF3-024E_1.pdf`, `sensia_100_datasheet.pdf`,
  `superia_100_datasheet.pdf` were digitized via a dedicated column-scan
  pixel tracer (`fuji_raster.py`/`raster_tracer.py`, NOT `digitizer_core.py`'s
  Strategy C) — nearest-active-trace column tracking with morphological
  gridline detection (`scipy.ndimage.binary_opening`) to distinguish tilted
  gridlines from real curve ink, plus splice/isolated-point-filtering
  techniques for cases where curves visually merge. Real effort: several
  rounds of gridline-deletion bugs, toe/coverage regressions, and multilayer
  QA-overlay compositing bugs were found and fixed — see project memory
  (`project_consolidated_data_extraction.md`) for the full blow-by-blow, not
  repeated here. Output lives in `consolidated-data/film/photography/
  {negative,reversal}/fuji/fuji_{superia100,velvia50,sensia100,provia100f,rtpii}_*.json`.
- **`superia_200_datasheet.pdf` remains blocked, and NOT scheduled for the
  same treatment**: decision made 2026-07-06 to deprioritize further raster
  pixel-tracing work generally (see the Ilford raster entry below for the
  same call) — the Fuji raster pipeline above was real, working, and
  verified, but expensive per file (custom tuning, multiple bug rounds) for
  each new chart. Revisit if raster tracing becomes a priority again; the
  tooling (`raster_tracer.py`) already exists and works, this file just
  hasn't been run through it.
- **Fuji B&W individual datasheets** (`NeopanAcros100.pdf`, `Neopan400.pdf`,
  `Neopan1600.pdf`, `NPZ.pdf`) are the SAME underlying blocker (embedded
  raster, see below) and are equally deprioritized as of 2026-07-06, not
  just "not yet attempted."

### Fuji B&W individual datasheets — whole-page scanned raster + broken text
- **Files (real datasheets, still blocked)**: `film/fuji/NeopanAcros100.pdf`,
  `Neopan400.pdf`, `Neopan1600.pdf`, `NPZ.pdf`
- **Not actually datasheets — corrected 2026-07-06**: `Profilm_misc.pdf`,
  `Proseries.pdf` are single-page marketing comparison brochures (product
  property tables + a saturation/contrast scatter chart), no characteristic-
  curve data at all -- moved to the "no curve data" section below. The
  original entry lumped them in with the real B&W films because they share
  the same broken-text symptom, but that symptom isn't why they're
  out-of-scope; they'd be out of scope even with perfect text.
- **Why blocked (revised diagnosis, 2026-07-06)**: the ORIGINAL diagnosis
  (subsetted font, no ToUnicode map, garbled text) is real but incomplete
  — checking `page.get_images()` on the real films (prompted by testing
  whether the Fuji/Ilford OCR approach would apply here too) found this is
  NOT "real vector curves with a broken text layer" like the resolved Fuji
  case above. It's a genuinely different, HARDER problem: confirmed on
  NeopanAcros100.pdf that each of its 6 "Characteristic Curves" panels
  (3 developers x 2 film formats) is its OWN embedded raster image
  (`CCITTFaxDecode` -- classic bitonal fax/scan compression), not vector
  paths at all. Checked Neopan400/1600/NPZ too: every page in all 3 has at
  least one embedded image, consistent with these being whole-page scanned
  documents (not vector-native PDFs with an isolated raster chart the way
  the 6 Fuji COLOR raster files are) -- axis ticks, gridlines, and curve
  lines are all part of one bitmap per panel, with a garbled OCR-generated
  text layer stamped on top (explaining the private-use-area character
  symptom -- some historical OCR pass over the scan, not a font-embedding
  bug). **This is the SAME underlying blocker as the "embedded raster
  image" Fuji color category two sections below, not a text-extraction
  problem** -- OCR-for-ticks (which resolved the vector-no-text category
  above) doesn't help here, because the curve SHAPE itself was never
  vector data to extract; it needs actual pixel-based curve tracing
  (Strategy C), which is real, harder, not-yet-built work, same as that
  category. Fuji's 65-page `ProfessionalFilmDataGuide.pdf` compilation
  covers at least Neopan 100 Acros with clean, fully vector/readable text
  (not yet confirmed whether ITS charts are vector or raster) -- worth
  checking first before attempting raster tracing on these, since it may
  sidestep the problem entirely rather than requiring new capability.
- **What would unblock it**: same as the embedded-raster Fuji color
  category -- Strategy C adapted to trace by pattern/position instead of
  color (not attempted yet, real future work, not a quick OCR fix) -- or
  check/use `ProfessionalFilmDataGuide.pdf` as an alternate clean source
  first, or manual digitizing.

### Ilford film — 2018+ reprints, embedded raster image
- **Files**: `film/ilford/Delta-100_201811.pdf`, `Delta-400_201811.pdf`,
  `Delta-3200_201811.pdf`, `FP4-Plus_201811.pdf`, `HP5-Plus_201811.pdf`,
  `Ortho-Plus_201910.pdf`, `Pan-F-Plus_201812.pdf`, `SFX-200_201811.pdf`,
  `XP2-Super_201811.pdf`
- **Why blocked**: confirmed via `page.get_images()` that every 2018+
  reprint embeds 7-10 raster images per file (vs. 0 on each film's matching
  pre-2018 sheet) -- same raster-tracing problem class as the Fuji color
  group above, deprioritized 2026-07-06 rather than attempted. Not needed
  anyway: each of these films has an older (2001-2004) sheet covering the
  SAME real product/curve with genuine vector paths, used instead (see
  `ilford_film.py`) -- these 2018+ files aren't a different product, just a
  reformatted reprint, so nothing is lost by sourcing from the older sheet.
- **What would unblock it**: same as the Fuji raster group -- not planned.

### Konica film — several sheets, embedded raster chart image
- **Files**: `film/konica/IMP50.pdf`, `VX200.pdf`, `VX400.pdf` (page 2 in
  each), `INF750.pdf`/`konica_inf750.pdf` (page 3, byte-identical
  duplicates of each other)
- **Why blocked**: confirmed via visual inspection (the chart's own text/
  numerals render visibly blurrier/pixelated than the surrounding
  vector-drawn body text at the same zoom) that these sheets' "SPECTRAL
  SENSITIVITY"/"CHARACTERISTIC CURVES" panels are embedded raster images,
  not vector paths + real text -- `overline_negative_calib` finds 0 tick
  candidates since there's no real tick text at all. Same raster-tracing
  problem class as the Fuji/Ilford 2018+ raster groups, not attempted
  (Strategy C not built). Every OTHER Konica sheet checked (10 of 14 real
  candidates: VX Super 100/200/400, VX100 Improved, Centuria Super 100/
  200/800/1600, Chrome Centuria 100/200, Chrome R-100) is genuine vector +
  real text and IS digitized (`konica.py`) -- this is a per-file printing
  quirk, not a vendor-wide pattern.
- **What would unblock it**: Strategy C (raster pixel-tracing) + OCR for
  axis tick labels, same as the Fuji color raster group.

### ~~Konica film — no text layer at all (vector shapes only)~~ — RESOLVED 2026-07-07 for csuper400/professional_160
- **Files originally cited as blocked**: `film/konica/centuria_pro_400.pdf`,
  `csuper400.pdf` (page 1), `professional_160.pdf`
- **Was blocked because**: these pages have substantial real vector
  drawings (1500-3700 per page) but 0 real text objects anywhere --
  consistent with body text (and axis tick numerals) having been outlined
  to vector shapes at export time rather than kept as real glyphs, a
  different failure mode from both "raster scan" and the "graphs
  referenced by code only" pattern seen in some Kodak motion-picture TI
  sheets.
- **`centuria_pro_400.pdf` reclassified, not unblocked**: both pages are
  a pure marketing brochure (product photography, no chart of any kind)
  -- confirmed by actually rendering and looking at them, not assumed
  from the missing text layer. Moved to the "no curve data at all"
  section below.
- **`csuper400.pdf`/`professional_160.pdf` unblocked**: the curve ink
  itself is real stroked vector paths in both files (Strategy D still
  finds exactly 3 clean traces on csuper400; `professional_160.pdf`'s 3
  curves are distinguished by real distinct stroke COLOR against a black
  page background, a genuinely different template from every other
  Konica sheet). Axis calibration and panel position via OCR
  (`ocr_helpers`); curve identity via each trace's own endpoint/color, not
  OCR. See `konica.py`'s `csuper400_product()`/`professional_160_product()`
  docstrings for the full mechanism and two real bugs this surfaced and
  fixed along the way: (1) `ocr_axis_calib` was trusting a spuriously-
  OCR'd leading "-" merged in from tick-mark dash strokes next to real
  digit text, silently negating an entire axis that has no real sign at
  all (fixed in `ocr_helpers.py`, re-verified no regression on the
  already-shipped Ilford Multigrade papers and Fuji OCR products, both of
  which use the same unsigned-tick-regex code path); (2) an evenly-spaced
  overline-convention tick row is genuinely ambiguous for a residual-
  minimizing brute-force sign search -- new `ocr_overline_negative_calib`
  applies the known "negate all but rightmost" convention directly
  instead of searching. Both verified via QA overlay before shipping.
  page, even though these ARE vector) combined with a much stricter
  curve-vs-decoration path filter (e.g. minimum path length/point count)
  to separate real data traces from thousands of vector letterform paths.

### Ilford Delta 100 Professional (pre-2018 sheet) — embedded raster image
- **File**: `film/ilford/Delta_100-200209.pdf`, page 3
- **Why blocked**: unlike every other pre-2018 Ilford film sheet in this
  corpus (Delta 400/3200, FP4+, HP5+, Pan F+, XP2 Super — all confirmed
  real vector strokes), this ONE file's Characteristic Curve panel is a
  single embedded raster image (xref 24, rect matches the chart area
  exactly) — confirmed via `page.get_drawings()` returning zero stroked
  paths in the chart region (only a single white-filled background
  rectangle). A real, isolated exception within an otherwise-vector batch,
  not assumed from the file's vintage alone (Delta 400/3200 are the same
  2002 vintage and are fully vector).
- **What would unblock it**: same raster-tracing work as the Fuji group,
  deprioritized 2026-07-06.

### MACO IR820c — spectral sensitivity comparison diagram, embedded raster
- **File**: `film/maco/MACO_IR820c_AURA.pdf`, page 8 ("Spectral sensitivity
  of infrared films")
- **Why blocked**: confirmed via `page.get_images()` a single embedded
  raster (JPEG) image, not vector paths. Also a third-party comparative
  diagram (credited "© 2002 Schroeders Negativ-Praxis", comparing MACO
  IR820c/IR750c/Cube 400c against Kodak HIE and Konica IR) rather than the
  manufacturer's own primary measurement — even if unblocked, it's a
  multi-product spectral-sensitivity comparison, not this film's own
  characteristic curve (which IS captured, see `maco_rollei_film.py` — a
  real vector chart on page 6, unaffected by this).
- **What would unblock it**: raster tracing, deprioritized this session
  (same call as the Fuji/Ilford raster groups).

### Rollei Infrared — characteristic + spectral sensitivity, embedded raster
- **File**: `film/rollei/Rollei_Infrared.pdf`, page 1
- **Why blocked**: the sheet's own text has "Characteristic diagram:" and
  "Spectral sensitivity:" labels, but both diagrams sit in the space
  occupied by a single large embedded raster JPEG (confirmed via
  `page.get_images()`) — not vector data.
- **What would unblock it**: raster tracing, deprioritized this session.

### Ilford SFX 200 — no Characteristic Curve chart at all
- **Files**: `film/ilford/SFX200-200404.pdf`, `SFX200-200704.pdf`,
  `SFX-200_201811.pdf`
- **Why out of scope**: confirmed via full-text search across all 6 pages
  of both the 2004 and 2007 sheets (and the 2018 one is raster anyway, see
  above) — this is a short "FACT SHEET" (spectral sensitivity, filter
  factors, dev-time/temperature nomogram) with no "Characteristic Curve(s)"
  section and no density-vs-exposure chart of any kind, unlike every other
  Ilford film in this corpus. Not a text/vector extraction problem -- there
  is genuinely no curve to extract.

### EASTMAN Color Negative Film 5247 (ti0835) / 5297,7297 (ti1607) / Sound Recording Film 2378,5378 (ti2125) — same "graphs referenced, not embedded" pattern as 5274
- **Files**: `motionpicture/kodak/ti0835.pdf`, `motionpicture/kodak/ti1607.pdf`,
  `motionpicture/kodak/ti2125.pdf` (all old-format "TECHNICAL INFORMATION
  DATA SHEET" TI-numbered sheets, 1993-2001)
- **Why blocked**: confirmed by reading each "Graphs" section directly --
  all three list MTF/Characteristic/Spectral-Sensitivity/Spectral-Dye-
  Density curves by external reference code only (e.g. "Characteristic b)
  (6-83)"), identical pattern to 5274 above. `page.get_drawings()` returns
  dozens of hits on the relevant pages but these are table/border lines
  from the surrounding text layout, not real chart data -- confirmed via
  direct page render, not assumed from the drawing count alone.
- **What would unblock it**: same as 5274 -- finding the actual graph
  attachment, not present in this corpus under a name found so far.

### EASTMAN Panchromatic Separation Film 2238 (TI2404) / Sound Recording Film 2374 (TI2292) — same pattern, found in motionpicture/kodak_2018/
- **Files**: `motionpicture/kodak_2018/2238_TI2404.pdf`,
  `motionpicture/kodak_2018/2374_ti2292.pdf`
- **Why blocked**: same "Graphs" section listing curves by external
  reference code only (e.g. "Characteristic A) Exposed at 580nm... (4-01)"),
  confirmed by reading each file's own Graphs section directly. Same class
  as ti0835/ti1607/ti2125/5274 above, just found later in the
  `kodak_2018/` reprint folder rather than the main `motionpicture/kodak/`
  folder.
- **What would unblock it**: same as 5274 -- finding the actual graph
  attachment, not present in this corpus under a name found so far.

### KODAK VISION 200T (5274/7274) — real graphs not embedded in this PDF
- **File**: `motionpicture/kodak/5274.pdf` ("TI2325", 1997 old-format sheet)
- **Why blocked**: this datasheet's "15) Graphs" section explicitly REFERS
  to charts by external page codes ("Characteristic: B) Log Exposure
  (7-99), C) Camera Stops (7-99)", "Spectral Sensitivity: D) (1-97)", etc)
  rather than embedding them -- confirmed by reading every page: the whole
  document is text-only (no images, no chart-shaped vector drawings
  anywhere), consistent with this being an older format that shipped its
  sensitometric graphs as a SEPARATE physical/PDF attachment not included
  in this corpus. Not a text/vector extraction problem -- there's nothing
  in this specific file to extract.
- **What would unblock it**: finding the actual graph attachment (not
  present in this corpus under a name found so far) -- not attempted.

### EASTMAN EXR 500T Film 5298 — embedded raster images
- **File**: `motionpicture/kodak/5298-ti2082.pdf` ("TI2082", 1993 old-format
  sheet)
- **Why blocked**: unlike 5274 above, this one's graphs (pages 6-10) DO
  exist in the PDF, but each is a single embedded raster image (confirmed
  via `page.get_images()`: 1 image, 0 drawings, per page) -- same raster-
  tracing blocker class as the Fuji/Ilford raster groups, deprioritized
  this session.
- **What would unblock it**: raster tracing, deprioritized this session.

### KODAK Recording Film 2475
- **File**: `film/kodak/2475.pdf`
- **Why blocked**: real product, real characteristic curves plotted across
  2 developer panels, but the entire page is a single raster scan image —
  confirmed 0 vector drawings and 0 real text objects anywhere on the page
  (a scanned datasheet, not a born-digital one). Same blocker class as the
  Fuji raster files above (Strategy C, pixel-tracing, not built this
  session). Confirmed 2026-07-06.
- **What would unblock it**: Strategy C (raster pixel-tracing) plus OCR for
  the axis tick labels (no real text layer at all, `pytesseract` fallback
  would be needed even for the ticks).

## Different chart semantics (not a text/vector extraction problem)

### Ektachrome EIR (infrared)
- **File**: `film/kodak/ti2323-Ektachrome_EIR.pdf`
- **Why out of scope for the current template**: plots "Green/Red",
  "Red/IR", "Blue/Green" *ratio* curves (false-color infrared film), not
  simple per-layer density-vs-exposure curves. Fundamentally different
  chart semantics from every other reversal film's template.
- **What would unblock it**: a new chart type/template built specifically
  for ratio curves — not a bug fix, a new feature.

## No curve data at all (confirmed, not a datasheet)

- `film/konica/centuria_pro_400.pdf` — a 2-page marketing brochure (product
  photography, marketing copy), confirmed by rendering and looking at both
  pages directly — no chart of any kind, unlike `csuper400.pdf`/
  `professional_160.pdf` (also brochure-like in places, but both have a
  real chart page elsewhere in the same file). Confirmed 2026-07-07.
- `motionpicture/kodak_2018/discontinuation_notices/*.pdf` (44 files) —
  Kodak Product Change Notices (PCN)/discontinued-listing announcements
  (e.g. "The KODAK Molecular Sieve strand length will increase from 46 cm
  to 54 cm"), confirmed by reading a sample directly. Not datasheets, no
  chart data of any kind.
- `film/kodak/e40-1996_12.pdf`, `e41/e42/e43/e44-1998_02.pdf`,
  `p255-2000_02/2001_05/2003_06.pdf` — 1990s multi-product "comparison
  guide" brochures. **Deliberately deferred per explicit user instruction**
  ("that's not a spec. keep that to the very end and when there is nothing
  else we will check it out together") — not independently confirmed
  content-free, just off-limits until user says otherwise. Different
  category from the rest of this file: this is a scope decision, not a
  technical blocker.
- `paper/kodak/e176.pdf` — "TECHNICAL DATA / REFERENCE" document on
  post-processing image stability. No chart data; its keyword-search hit
  was a false positive on body text.
- `paper/kodak/ENDURAImagePermanenceWhitePaper_LTR_EN.pdf`,
  `Silver_Halide_Executive_Summary.pdf`, `Silver_Halide_White_Paper.pdf`,
  `enduraWhitePaper.pdf` — whitepapers, no chart data.
- `paper/kodak/e119.pdf` (KODAK PROFESSIONAL DURATRANS Plus / DURACLEAR
  Plus Digital Display Material, Nov 2002, E-119) — a real, distinct
  product from the already-digitized plain "Duratrans/Duraclear Display
  Material" (non-Plus, 1999, from `e143.pdf`), but this 4-page sheet has
  no characteristic-curve chart at all (only a process-control target
  density mentioned in body text, "density of 2.10... D-max"). Confirmed
  2026-07-07.
- `paper/kodak/e4013.pdf` (KODAK PROFESSIONAL Day/Night Digital Display
  Material, Nov 2003, E-4013) — a real, distinct, earlier predecessor of
  the already-digitized "Endura Day/Night Display Material" (E-4034,
  April 2004, from `e4034.pdf`) — different pub number, different product
  name (no "ENDURA"), but no characteristic-curve chart anywhere in this
  4-page sheet. Confirmed 2026-07-07.
- `paper/kodak/g12.pdf` (KODAK EKTAMATIC SC Paper, G-12, 2000),
  `g19.pdf` (KODAK ELITE Fine-Art Paper, G-19, 1999), `g21.pdf` (KODAK
  PROFESSIONAL POLYCONTRAST III RC Paper, G-21, 2004 — a real, distinct,
  older product from the already-digitized "Polycontrast IV RC Paper"
  from `g4037.pdf`) — all 3 real, distinct products, confirmed via
  full-text search (no "CURVE" anywhere in any of the three; the few
  "DENSITY" hits are body text about paper-contrast selection, not a
  chart) to have no characteristic-curve chart data. Confirmed 2026-07-07.
- `paper/kodak/e4020-2.pdf` — byte-identical duplicate of already-digitized
  `e4020.pdf` (Ultra Endura Paper). `e4021-200909.pdf` (Sept 2009
  printing) — duplicate of already-digitized `e4021.pdf` (Sept 2008
  printing, Portra Endura Paper): identical curves page (shared figure
  codes F002_1274AC/1275AC). `e4028-200909.pdf` (Sept 2009 printing) —
  duplicate of already-digitized `e4028.pdf` (Sept 2008 printing, Endura
  Metallic Paper): identical curves page text. All confirmed 2026-07-07.
- `paper/ilford/Contrast Control.pdf` — an exposure-factor lookup table,
  no chart.
- `paper/ilford/Processing Paper.pdf` — processing instructions only, no
  chart.
- `paper/foma/Fomaspeed_412.pdf` — single-page product description, no
  chart data.
- `film/fuji/Profilm_misc.pdf`, `Proseries.pdf` — single-page marketing
  comparison brochures (product property tables + a saturation/contrast
  scatter chart comparing several films/products at once), no
  characteristic-curve data. Confirmed 2026-07-06; previously miscategorized
  under the Fuji B&W broken-text-encoding entry above (they share the same
  garbled-text symptom as the real B&W film datasheets, but that's not why
  these two are out of scope -- they have no curve data regardless of
  whether their text is readable).
- `film/charts/ilford/2006129224892363.pdf` — Kodak-to-Ilford film/paper/
  chemistry equivalence conversion tables, no chart data.
  `film/charts/ilford/2006216122447.pdf` — an Ilford film processing-time
  reference table (dev times per film/developer/dilution), no chart data
  either. Both confirmed 2026-07-06.
- `film/rollei/Development_Rollei films.pdf` — a bilingual (English/Dutch)
  development-time table (film x developer x dilution), no characteristic-
  curve chart at all. Confirmed 2026-07-06.
- `film/kodak/5246-1983_09.pdf` (KODAK DIRECT POSITIVE PANCHROMATIC FILM
  5246) — real product, but confirmed genuinely no chart of any kind on
  either page. Confirmed 2026-07-06.
- `film/kodak/e24-Vericolor.pdf` (KODAK VERICOLOR Slide Film, a duplicating/
  positive-transparency-from-negative product) — real product, confirmed
  genuinely no chart data across all 4 pages. Confirmed 2026-07-06.

## Confirmed duplicates (real product, but data already captured elsewhere)

- `film/kodak/e4024-2009.pdf` — confirmed duplicate of already-digitized
  `film/kodak/e4024-Ektachrome_E100G.pdf` (identical source figure codes
  F009_0525AC/0524AC/0526AC/0527AC found on page 4 of both). Confirmed
  2026-07-06.
- `film/kodak/E7022_Gold_200-2016.pdf` — confirmed duplicate of already-
  digitized `film/kodak/E7022-Gold_100_200.pdf`'s Gold 200 panel (identical
  source figure codes E7022B/E7022C in both — the 2016 sheet only reprints
  the 200-speed half of the original combined Gold 100/200 datasheet).
  Confirmed 2026-07-06.
- `film/kodak/E7019_en-Ultra_Max_400.pdf` (2007 edition) — same nominal
  product ("KODAK ULTRA MAX 400 Film") and same curve shape/axis
  calibration as the already-digitized `E7023_max_400-2016.pdf`, just an
  older Kodak publication number (E-7019 vs E-7023) predating the "Log H
  Ref" annotation Kodak later added to its sheets — treated as an older
  edition of the same measured product, not digitized separately, same
  policy as `lab_h12383t.pdf` above. Confirmed 2026-07-06.
- `film/kodak/E7023-Ultra_Max_400.pdf` (Feb 2009 printing) — confirmed
  duplicate of already-digitized `E7023_max_400-2016.pdf` (identical
  figure code E7023C on both). Confirmed 2026-07-06.
- `film/kodak/f4001-P3200TMZ-2019.pdf` — same product/page/title as
  already-digitized `F4001-P3200TMZ-2018.pdf`, but this printing's
  Characteristic Curves and Contrast Index Curves panels are embedded
  RASTER images (3 ICCBased images per page, 0 real text/vector content on
  those pages) rather than vector+text like the 2018 sheet — a worse
  (raster) rendition of the same real data already captured from the
  better (vector) 2018 source, not a new distinct product. Confirmed
  2026-07-06.
- `film/kodak/e55-1996_12.pdf`, `e55-2003_08.pdf`, `e55-2009_06.pdf`
  (KODACHROME 25/64/200 Professional Films, pub E-55) — confirmed
  duplicate of the Kodachrome 25/64/200 data already digitized from
  `e88-2002_03.pdf` (identical figure codes F002_0486AC/0490AC/0494AC in
  all four files). Confirmed 2026-07-06.
- `film/kodak/e88-1998_01.pdf` — duplicate of `e88-2002_03.pdf` (identical
  figure codes F002_0485-0490AC). `e88-2005_09.pdf`/`e88-2009_06.pdf` —
  same Kodachrome 64/200 data as `e88-2002_03.pdf` (shared codes
  F002_0489-0494AC); these two later editions simply dropped the
  discontinued Kodachrome 25 section (confirmed via title text: "KODACHROME
  64 and 200 Films", vs the 2002 edition's "KODACHROME 25, 64, and 200
  Films") — no new curve data in either. Confirmed 2026-07-06.
- `film/kodak/e190-Portra-2006.pdf` (KODAK PROFESSIONAL PORTRA 160NC,
  160VC, 400NC, 400VC, and 800 Films, pub E-190, Oct 2006) — same product
  family as `e4040-Portra-2006/2008/2009.pdf` (pub E-4040, digitized as
  Portra 160NC/160VC/400NC/400VC above) but under Kodak's earlier E-190
  publication number, using its own distinct figure-code prefix
  (F009_0153-0156AC/0180-0181AC vs E-4040's E4040A-K) — genuinely a
  separate print run, not byte-identical, but same nominal products/year
  digitized from the more standard E-4040 sheet already; not digitized a
  second time from this earlier-numbered sibling. Confirmed 2026-07-06.
- `film/kodak/e4046-EKTAR-2008/2009/2010.pdf` — confirmed duplicates of
  already-digitized `e4046_ektar_100-2016.pdf` (identical figure codes
  E4046A-D in all four files). Confirmed 2026-07-06.
- `film/kodak/e4050-Portra-400.pdf` (2010 printing) — confirmed duplicate
  of already-digitized `e4050_portra_400-2016.pdf` (identical figure code
  E4040C and identical "Log H Ref: -1.44" text). `e4051-Portra-160.pdf`
  (2011 printing) — confirmed duplicate of already-digitized
  `e4051_Portra_160-2016.pdf` (identical distinctive "Log H Ref: -1.051"
  text on both). Confirmed 2026-07-06.
- `film/kodak/f11-Duplicating_SO-132-200105.pdf` (2001 printing) — confirmed
  duplicate of already-digitized `f11-Duplicating_SO-132.pdf` (identical
  page text). Confirmed 2026-07-06.
- `film/kodak/f13-HIE-200006.pdf` (June 2000 printing, "KODAK High Speed
  Infrared Film") — confirmed duplicate of already-digitized
  `f13-HIE.pdf` (Dec 2002 printing, rebranded "KODAK PROFESSIONAL
  High-Speed Infrared Film") — identical D-19/D-76/HC-110(Dil B)
  Characteristic Curves chart on both. Confirmed 2026-07-06.
- `film/kodak/f4018-125PX-2002.pdf` — confirmed duplicate of already-
  digitized `f4018-125PX-2007.pdf` (identical page text throughout,
  including the IMAGE STRUCTURE section). Confirmed 2026-07-06.
- `film/kodak/f9-Tri-X_Pan-199906.pdf` — duplicate of already-digitized
  `f9-Tri-X_Pan.pdf` (shared figure codes F002_0355-0360AC).
  `f8-Plus-X_Pan-199709.pdf` — duplicate of already-digitized
  `f8-Plus-X_Pan.pdf` (shared codes F009_0018-0022AC + F002_0062GC).
  `f7-Verichrome-199611.pdf` — duplicate of already-digitized
  `f7-Verichrome.pdf` (shared codes F002_0528-0530AC).
  `f10-Ektapan-199710.pdf` — duplicate of already-digitized
  `f10-Ektapan.pdf` (shared codes F002_0531/0532AC). All four confirmed
  2026-07-06 — older print-date editions of the same F-series sheets,
  each sharing its sibling's real figure codes.
- `film/kodak/f4016_tmax_100-2018.pdf` — duplicate of already-digitized
  `f4016_TMax_100-2016.pdf` (shared figure codes F002_0449AC/0542AC/
  0547AC). `f4016-TMAX-2007a.pdf`/`f4016-TMAX-2007b.pdf` — duplicates of
  already-digitized `f4016-TMAX-2004.pdf` (shared figure codes
  F002_0449/0506/0507/0509/0511/0512/0513AC — this 30-page combined T-Max
  100+400 book is itself the same underlying old-formulation data as
  `f32-TMAX.pdf`, see the Pre-2007-Formulation entry in kodak_bw.py).
  `f4017-400TX-2005.pdf`/`f4017-400TX-2007.pdf` — same nominal product
  and pub number (F-4017) as already-digitized `f4017-2016.pdf`, but
  these older editions each carry FOUR separate multi-developer-time
  "Characteristic Curves" pages (T-MAX Developer/D-76 for 400 in both
  35mm and 120, D-76 for 320TXP + its own Contrast Index Curve, HC-110 for
  320TXP Sheets + Contrast Index Curve comparing D-76/HC-110/XTOL/T-MAX RS)
  — genuinely richer development-time-family data than the 2016 sheet's
  single representative curve per format, not digitized here (would need
  its own dedicated multi-panel digitization pass, see "Not blocked"
  section below). `f4043-TMAX_400-2007.pdf` — duplicate of already-
  digitized `f4043_TMax_400-2016.pdf` (shared figure codes F4043A-E).
  Confirmed 2026-07-06.
- `film/kodak/f32-199910.pdf`, `f32-TMAX-200109.pdf` — older printings of
  the same F-32 "KODAK T-MAX Professional Films" book as
  `f32-TMAX.pdf` (which IS digitized, see kodak_bw.py's "T-Max 100/400
  (Pre-2007 Formulation)" products) — identical page structure/figure
  codes across all three (confirmed via T-Max 100/400/P3200 section
  headers landing on the same page indices with the same content).
  Confirmed 2026-07-06.
- `film/kodak/P3200_FAQs.pdf`, `portra400QAs.pdf`, `PORTRA_Film_Q&A.pdf` —
  Q&A/FAQ marketing documents, no chart data. Confirmed 2026-07-06.
- `film/kodak/f11-199904.pdf` (April 1999 printing) — confirmed duplicate
  of already-digitized `f11-Duplicating_SO-132.pdf` (identical page text).
  `film/kodak/f2350-T400CN-199902.pdf` (Feb 1999 printing) — confirmed
  duplicate of already-digitized `f2350-T400CN.pdf` (2003 printing,
  identical CURVES page text). Both confirmed 2026-07-06.

- `paper/kodak/e4038.pdf`'s Transparency panel — byte-identical to
  `e4031.pdf`'s Transparency Digital panel (same source figure code
  "F002_0517AC" in both files). Its Clear panel is real/distinct and IS
  captured (different figure code).
- `paper/kodak/E4042-2.pdf` — confirmed duplicate of `E4042.pdf` (identical
  header/year); not digitized separately.
- `film/fuji/True_Definition_DataSheet.pdf` ("Fujicolor True Definition 400
  [CH]") — confirmed a rebrand of Superia X-tra 400 (both carry the same
  "[CH]" product code and CN-16 process); digitizes cleanly but not added
  as a separate product.
- `film/fuji/AF3-0221E2Velvia50PIB.pdf` — byte-identical duplicate of
  `velvia_50_datasheet.pdf` (same doc code AF3-0221E2). `AF3-203U_Pro160S_
  Product_Information_Bulletin.pdf` / `AF3-204U_Pro160C_Product_Information_
  Bulletin.pdf` — older-revision duplicates of `pro_160s_datasheet.pdf` /
  `pro_160c_datasheet.pdf` (same product, different doc code/revision).
  `FUJICOLOR_PRO_NEG_FAMILY_BROCHURE_101305.pdf` — marketing brochure, no
  chart data.
- `motionpicture/kodak/KODAK_VISION3_200T_5213_7213_Product_Information.pdf`
  and `motionpicture/kodak/VISION3_50D_5203_SS.pdf` — marketing "Product
  Information"/spec-sheet brochures for VISION3 200T (5213/7213, already
  digitized from its real H-1-5213t technical sheet earlier this session)
  and VISION3 50D (5203/7203, already digitized from H-1-5203t). Both
  brochures render the same Sensitometric/MTF/Granularity/Spectral curves
  as color-coded (actual RGB-colored lines, not black+inline-label)
  charts — confirmed real chart data, not fabricated, but the 50D sheet
  explicitly cites "See Kodak publication H-1-5203t... for more
  information" confirming it's presenting the same underlying
  measurement, not new data. Not digitized separately — would need a new
  Strategy A (color-fill) extractor since this rendering has no inline
  B/G/R text labels, for data already captured. `VISION3_50D_5203_
  Technical_Backgrounder.pdf` referenced in earlier session notes does not
  exist in the corpus under that name (checked directly, file not found).
- `motionpicture/kodak_2018/TI5254.pdf`-equivalent duplicate found
  2026-07-06: `motionpicture/kodak_2018/2254_TI2651.pdf` (July 2015 printing,
  same H-1-5254t pub as the already-digitized `TI5254.pdf`, August 2012
  printing) — identical panel structure, not digitized separately.
- `motionpicture/kodak_2018/5203_ti2657.pdf`, `5213_TI2653.pdf` — same
  H-1-5203t/H-1-5213t pub numbers as already-digitized
  `5203-Vision3-50D-TI5203.pdf`/`5213-Vision3-200T.pdf` (different print
  dates, same product). `5207_ti2650.pdf` — same H-1-5207t pub as
  already-digitized `5207-Vision3-250D.pdf`. `5219_TI2647.pdf` — same
  H-1-5219t pub as already-digitized `5219-Vision3-500T-tech.pdf` (2015 vs
  2007 printing). `5222_ti0299.pdf` — same H-1-5222 pub as already-
  digitized `5222-Double-X.pdf`. `7266_ti2617.pdf` — same H-1-7266t pub as
  already-digitized `7266-TRI-X-rev.pdf` (2015 vs 2003 printing). All
  confirmed via matching pub number + product name 2026-07-06.
- `motionpicture/kodak_2018/2237_SS.pdf`, `5207_SS_4pgs.pdf`,
  `5213_SS_4pgs.pdf`, `5222_SS.pdf`, `7266_SS.pdf`, `VISION3_50D_5203_SS.pdf`,
  `EKEI-4032_Vision3Sellsheet.pdf` — marketing "sell sheet" brochures (2-4
  pages, no real Characteristic Curves chart), same category as the
  already-logged VISION3 Product_Information/SS files above. `2378E_ti2125.pdf`
  — same TI2125 as already-logged `ti2125.pdf` ("graphs referenced, not
  embedded" pattern). `Kodak_VISION3_Color_Digital_Intermediate_Film_2254_
  5254_Product_Information.pdf`, `VISION3_DI_ Film_2254_Customer_
  Testimonials.pdf`, `VISION3_DI_Film_2254_Technical_Backgrounder.pdf` —
  marketing/editorial pieces about 2254/5254 (the real datasheet for which
  is `TI5254.pdf`, already digitized), no chart data of their own.
  `US_plugins_acrobat_en_motion_products_kit_kitChem2(1).pdf` — Kit
  Chemicals product marketing, no chart. `5273_Customer_Tool.pdf` — a
  1-page process-comparison table (X273 vs X272), no chart. All confirmed
  2026-07-06.
- `motionpicture/kodak_2018/US_plugins_acrobat_en_motion_products_lab_
  h1so302.pdf` (TI2497, "KODAK Black-and-White Print Film / 2302, 3302 /
  ESTAR Base") — real, previously-unseen product, but its Characteristic/
  Spectral-Sensitivity/Gamma/Net-Fog/Granularity charts are all referenced
  by figure letter only ("Characteristic B) (11-99)") with 0 real drawings
  or images on the page — same "graphs referenced by code only, not
  embedded" pattern as ti0835/ti1607/ti2125/2238/2374 already logged above.
  Confirmed 2026-07-06.
- `motionpicture/kodak_2018/US_plugins_acrobat_en_motion_support_processing_
  h333.pdf` (79-page "Using KODAK Kit Chemicals in Motion Picture Film
  Laboratories"), `motionpicture/kodak/cineonfileformat4.5.pdf` (Cineon
  digital file format spec, not a film datasheet), `motionpicture/kodak/
  CIS287.pdf` (1-page bulletin), `motionpicture/misc/SystemsTechnology
  Brochure.pdf` (digital 4K+ scanning-systems theory, not film
  sensitometry), `motionpicture/misc/ulm0004-1.pdf` (residual-thiosulfate
  analytical-procedure module), and all 21
  `motionpicture/kodak_guides/US_plugins_acrobat_en_motion_newsletters_
  filmEss_*.pdf` files (an educational "Film Essentials" newsletter series
  covering history/optics/workflow topics) — confirmed via full-text
  search (no "DENSITY" anywhere in any of these files) to contain no
  characteristic-curve chart data; out of scope. Confirmed 2026-07-06.
- `motionpicture/kodak/5201-Vision2-50D.pdf`, `5205-Vision2-250D.pdf` —
  4-page marketing brochures (real Sensitometric/Spectral-Sensitivity
  charts present but color-coded, same Strategy-A blocker as the Vision2
  100T/200T/500T-Expression entry above), redundant with the real
  technical datasheets already digitized for these two products
  (`5201-Vision2-50D-tech.pdf`/`5205-Vision2-250D-tech.pdf`). Not logged as
  "pending" since, unlike 5212/5217/5229, real non-color-coded data for
  these two products already exists in the corpus. Confirmed 2026-07-06.
- `motionpicture/kodak/lab/lab_h12383t.pdf` ("KODAK VISION Color Print
  Film / 2383, 3383", printed March 2005/H-1-2383t) — an older printing of
  the same "2383" product already digitized from the newer 2015 sheet
  `motionpicture/kodak_2018/2383_ti2397.pdf` (kodak_mp_intermediate.py's
  `color_print_2383_product`). Unlike the 7276/7278-vs-7265/7266 case
  earlier this session (where an older catalog-numbered sheet was treated
  as its own real measured data point), this is the SAME catalog number
  and product name on both sheets, just a different print date -- treated
  as a straightforward duplicate rather than a distinct measurement.

## Not blocked — confirmed pending work (do not confuse with the above)

- `motionpicture/kodak/5212-Vision2-100T.pdf`, `5217-Vision2-200T.pdf`,
  `5229-Vision2Exp-500T.pdf` (KODAK VISION2 100T/200T/500T-Expression Color
  Negative Films — 4-page marketing "www.kodak.com/go/motion" sheets, NOT
  duplicates of anything already digitized; no "-tech" sibling exists for
  these 3 in the corpus, unlike 5201/5205/5218 which do) — real
  Sensitometric/Spectral-Sensitivity/Spectral-Dye-Density/MTF/Granularity
  charts confirmed present (149-254 real vector drawings per file), but the
  curves are identified by COLOR (RGB-coded lines per a legend), not inline
  text labels — same Strategy A (color-fill) blocker as the VISION3
  marketing brochures already logged in the "Confirmed duplicates" section
  above, except these 3 products have no other real source in the corpus,
  so they're genuinely pending rather than redundant. Confirmed 2026-07-06.
- `motionpicture/kodak/5279.pdf` (KODAK VISION 500T Color Negative Film
  5279/7279, 1996 — a Vision2/Vision3 500T predecessor, not covered
  anywhere else in the corpus): real Spectral-Sensitivity AND Spectral-Dye-
  Density curves with inline Cyan-/Magenta-/Yellow-Forming-Layer labels
  (Strategy D, same COLOR_NEG_SPECTRAL_LABELS pattern used elsewhere,
  figure codes F002_0264AC/0286AC) — confirmed real and extractable, not
  yet digitized. This sheet has NO characteristic (density-vs-exposure)
  curve at all, only the spectral charts and a Diffuse RMS Granularity
  chart (which itself uses "DENSITY" as its x-axis, not exposure — a
  different chart type, not mistakable for the real H&D curve).
- `motionpicture/kodak/5230-TI2654.pdf` (KODAK 500T Color Negative Film
  5230/7230, 2011) and `5285-Ektachrome-100D.pdf` (KODAK EKTACHROME 100D
  Color Reversal Film 5285, 2000) — real, distinct products not found
  elsewhere in the corpus, but neither sheet contains a characteristic
  (density-vs-exposure) curve at all — confirmed via full-text search (no
  "LOG EXPOSURE" + "DENSITY" pairing on any page beyond Granularity/MTF
  charts, which use different axes). Nothing to digitize from either file.
- `motionpicture/kodak/5245-1999.pdf` (EASTMAN EXR 50D, 1999 printing) —
  same nominal product as already-digitized `5245.pdf`, but genuinely a
  DIFFERENT source figure (F002_0587AC, plain "LOG EXPOSURE (lux-seconds)"
  x-axis) than `5245.pdf`'s own Characteristic Curves chart (F010_0261AC,
  "Camera Stops" x-axis) — verified via side-by-side render, not a
  byte-duplicate. Not digitized a second time since the same real product
  is already captured from `5245.pdf`; noting the distinct figure code
  here in case a future need arises to cross-check the two measurements.
  `5293-1999.pdf` (EXR 200T) likely follows the identical pattern relative
  to already-digitized `5293.pdf` (not independently re-verified, lower
  priority given 5245's result).
- `film/kodak/f4017-400TX-2005.pdf`/`f4017-400TX-2007.pdf` (KODAK
  PROFESSIONAL TRI-X 320 and 400 Films, pub F-4017, older editions):
  4 real, undigitized multi-developer/development-time-family
  Characteristic Curves panels beyond what `f4017-2016.pdf` already
  captures (Tri-X 400/35mm x T-MAX Developer 5/7/9/11min; Tri-X 400/35mm
  and /120 x D-76 6/8/10/12min; Tri-X 320TXP/120-220 x D-76 8/10/12/14min
  + its own Contrast Index Curve; Tri-X 320TXP/Sheets x HC-110 4/6/9/14min
  + a Contrast Index Curve comparing MICRODOL-X/HC-110(B)/XTOL/T-MAX RS at
  various development times) — confirmed real via direct page-text read
  2026-07-06, not yet digitized (would follow the same BwPanel
  development-time-family pattern already used elsewhere in kodak_bw.py,
  just several more panels than any product currently has).
- `film/agfa/agfa_films.pdf` (1998 "AGFA Range of Films PROFESSIONAL"
  brochure): pages 6-8 (AGFACOLOR Optima II 100/200/400, Portrait XPS 160,
  Ultra 50; AGFACHROME RSX II 100) have real, vector-extractable Spectral
  sensitivity AND Spectral density (Blue/Green/Red or Yellow/Magenta/Cyan
  dye density vs. wavelength) charts -- confirmed real data via direct text
  search, NOT yet digitized. These color films have no true characteristic
  (density-vs-exposure) curve anywhere in this brochure (confirmed: only
  page 9's B&W AGFAPAN APX 25/100/400 panels have one; the "Characteristic
  values and curves" phrase on page 5 is just a section header, not a real
  chart) -- only spectral sensitivity/density, a real but secondary chart
  type this project doesn't otherwise track as a named schema field yet.
  Page 9's own "Sharpness" (MTF) and "Gamma-time curves" panels (same ones
  already noted not-digitized for the standalone `agfapanapx25.pdf`) are
  the same real-but-untracked-chart-type situation.
- `techpubs/agfa/agfa_bw_manual.pdf` (69 pages): a full Agfa BW film range
  catalog/brochure whose own table of contents lists "Density curves" per
  product section (Scala 200x, APX range, and possibly others) -- NOT
  surveyed in depth this session (techpubs/ was treated as out-of-scope
  chemistry/process manuals by convention elsewhere in this corpus, but
  this specific file's TOC suggests it may be a superset or alternate
  source of the same real data already captured from `agfa_films.pdf`/
  `agfa_scala.pdf`/`agfapanapx25.pdf` -- or may contain additional
  products/charts not seen elsewhere). Worth a real survey pass before
  assuming it's redundant. `techpubs/agfa/agfa_bw_film_chemicals_en.pdf`
  and `agfa_film_chem.pdf` were spot-checked (both mention "exposure" but
  not "density curve") and are more likely genuine chemistry-only manuals,
  lower priority to check.
