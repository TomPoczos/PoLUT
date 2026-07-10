# Masking/flashing research sources

Secondary/web sources gathered while investigating why the reversal-film cascades
(Velvia, Kodachrome 64, Provia 100F, Ektachrome 100D) crush to ~3.5 stops of real
tonal separation instead of the film's own ~8-9 stop native capture range. Kept
separate from `papers/`'s primary manufacturer datasheets since these are
secondary sources (archival references, encyclopedic, retail/how-to) rather than
original manufacturer technical publications.

- **brianpritchard_FAOL_colour_duplicating_film_stocks.html** — Film Archive
  Online Library page on duplicating colour film with duplicating stocks.
  Confirms EASTMAN Color Internegative Film was designed for Ektachrome
  Commercial (a low-contrast, gamma≈1.0, never-projected duplicating positive)
  as its intended input — not a full-contrast consumer reversal original.
  States flashing is the real technique used to reduce contrast for
  higher-contrast originals, but "none [are] satisfactory." Gives real gamma
  figures (5272/7272 ≈0.50, 5243/7243 ≈1.00) and a worked printer-point/density
  example.
- **wikipedia_tone_reproduction.html** — points to L.A. Jones's foundational
  1920 paper and the Jones diagram; used to trace the primary source (see
  `papers/jones_1920_theory_of_tone_reproduction.pdf`).
- **wikipedia_unsharp_masking.html** — general background on unsharp/contrast-
  reduction masking and its use controlling density range of transparencies
  intended for photomechanical reproduction.
- **nfsa_gamma_glossary.html** — National Film and Sound Archive of Australia's
  glossary entry on gamma in film duplication chains.
- **freestylephoto_contrast_masking_traditional_print.html** — practical
  darkroom description (Lynn Radeka) of contrast-reduction masks, unsharp
  masks, and how they differ mechanically; confirms contrast-reduction masking
  is "especially effective... making Ilfochrome prints."
- **maskingkits_faq.html** — retail FAQ on contrast-reduction masking
  kits; confirms standard panchromatic camera film (e.g. Kodak T-Max 100) can
  serve as masking film in practice.
- **charlescramer_making_a_dye_transfer_print.html** — dye-transfer printing
  masking practice; real numeric example (masked separation negative gamma
  0.90 vs. unmasked 0.70) showing masking's effect on usable separation-negative
  gamma.

Primary sources referenced from this research live directly in `papers/`:
- `jones_1920_theory_of_tone_reproduction.pdf` — L.A. Jones, "On the Theory of
  Tone Reproduction, with a Graphic Method for the Solution of Problems,"
  J. Franklin Institute, July 1920, pp.39-90 (extracted from the full volume,
  archive.org). Origin of the gamma-product rule: γ_negative × γ_positive =
  γ_reproduction (p.64), with Jones's own worked example landing at ≈1.01,
  confirming γ_system ≈ 1.0 as the target for faithful tone reproduction
  through a duplicating chain.
- `patent_US4739375_internegative_contrast_correction_flash.pdf` — Kuzyk et
  al. 1988, "Apparatus for Producing Internegatives and Slides." Real,
  patented hardware with a secondary neutral-density-filtered flash unit
  specifically for contrast-correction exposure when duplicating a reversal
  original, confirming flashing as a real, spectrally-neutral technique (though
  operator-dialed, not a fixed published formula).
- `kodak_finegrain_duplicating_pan_2234_TI0147.pdf` — EASTMAN Fine Grain
  Duplicating Panchromatic Negative Film 2234/5234. Real Kodak duplicating
  stock with gamma continuously adjustable 0.47-0.78 via development time —
  the class of material actually used to hand-make contrast masks.
  Referenced as an example of controllable-gamma duplicating materials.
- `kodak_vision_color_intermediate_5242_H-1-2242.pdf` — real Kodak duplicating
  stock with "reproduction contrast near unity," used for negative-originated
  cinema mastering rather than reversal duplication; ruled out as a direct fix
  but confirms unity-gamma duplicating stocks are a real Kodak product class.
  (Already present in papers/ prior to this session.)
- `kodak_color_internegative_2273_3273_ti.pdf` — KODAK Color Internegative
  Film 2273/3273/ESTAR Base. Higher-contrast internegative variant vs.
  5272/7272 in the same product family; confirms contrast can also be
  controlled by adjusting development (temperature/time/pH) as an
  alternative to masking/flashing.
- `kodak_H-740_basic_photographic_sensitometry_workbook.pdf` — Kodak's own
  self-teaching sensitometry workbook; consulted for a rigorous treatment of
  flashing/masking math but didn't contain the specific formulas sought
  (practical/introductory rather than derivational in content).
- `kodak_internegative_ii_5272_TI1301.pdf` — the primary internegative
  datasheet this project already used; reread in full during this research
  and confirmed it documents no masking/flashing requirement for reversal
  originals, meaning the measured contrast crush is what the datasheet's own
  documented process produces as-is. (Already present in papers/ prior to
  this session.)

### Round 2: why the corrected direct-print route was still crushing shadows

After the initial gamma-correction fix (target=1.0) shipped, real-world use
showed shadows reading as washed-out grey instead of black even though
highlights looked correct -- diagnosed as GAMMA_CORRECT_TARGET being both
the wrong target value (unity system gamma is the pure-fidelity target, not
the target a human viewer prefers for a print) and, more fundamentally, a
uniform scalar being the wrong *shape* of correction (it flattens the toe/
shoulder along with the straight line, when Jones's own theory only claims
validity for the straight line). See generate_film_looks.py's
GAMMA_CORRECT_TARGET comment block and README "Why a reversal print crushes
without correction" for the resulting fix (gamma_correct_curve() now scopes
the rescale to the straight-line window and carries the toe/shoulder forward
additively using the curve's own real digitized deltas).

- `choi_bartleson_breneman_brightness_stevens_power_law.pdf` — King F. Choi
  (Eastman Kodak Company), "Relationship Between Bartleson and Breneman's
  Brightness vs Luminance Equation and Stevens' Power Law," IS&T 1994 Annual
  Conference Proceedings p.433 (reprinted in *Recent Progress in Color
  Processing*, Chapter I). Gives the precise primary citation --
  C. J. Bartleson and E. J. Breneman, "Brightness perception in complex
  fields," *J. Opt. Soc. Am.* 57, pp.953-957 (1967) -- and explains the
  underlying mechanism: a darker viewing surround than the original scene
  requires a steeper reproduction gamma to match perceived brightness
  contrast, the physical basis for print/display system gamma exceeding 1.0.
- `roufs_global_brightness_contrast_perceptual_image_quality.pdf` — Roufs,
  Koselka & van Tongeren (Institute for Perception Research, Eindhoven),
  "Global Brightness Contrast and the Effect on Perceptual Image Quality,"
  same IS&T proceedings. Independent experimental confirmation: subject-
  preferred reproduction gamma is "greater than 1 for all test scenes,"
  measured optimum around ~1.2-1.4 for their (slide-scanner + monitor,
  moderately dark-surround) viewing setup, explicitly attributed to the same
  Bartleson & Breneman surround mechanism, with optimal gamma trending back
  toward 1 only as the dark-surround effect is designed out of the viewing
  setup. Corroborates "somewhat above 1, not exactly 1" without independently
  reproducing Bartleson & Breneman's own specific light/dark/dim-surround
  table -- GAMMA_CORRECT_TARGET=1.1 (light-surround/reflection-print figure)
  is cited as commonly summarized from Bartleson & Breneman (1967) itself,
  which was not accessible in full text (JOSA, paywalled) during this
  research.
- `lehmbeck_basics_tone_reproduction_digital_imaging.pdf` — Donald R.
  Lehmbeck, "Basics for Tone Reproduction in Digital Imaging Systems"
  (excerpted from Lehmbeck & Urbach, *Image Quality for Scanning and Digital
  Imaging Systems*, ch.3, in *Handbook of Optical and Laser Scanning*, 2nd
  ed., CRC Press, 2012). Consulted for the same tone-reproduction lineage
  Jones/Bartleson-Breneman/Nelson belong to; also cites Jones & Condit's
  landmark 1941/1948 studies of real outdoor-scene dynamic range (~160:1
  average, log-range 2.2) and shows a representative real camera/printer
  characteristic curve with the same toe/straight-line/shoulder structure
  this project's own curves have, including the real phenomenon of camera
  flare reducing captured shadow contrast below the true scene value.

### Round 3: preserving the film's own toe/shoulder shape while still reaching real Dmax

Round 2's window-scoped fix (target=1.1) was still measurably insufficient
in real-world use (shadows still read washed-out), and two further
mechanisms were tried and rejected before landing on the current one -- see
`generate_film_looks.py`'s `GAMMA_CORRECT_TARGET` comment block for the
full v1-v4 history and the measured numbers for each:

- v3 (a single straight line through the pivot, extended to the film's own
  real Dmin/Dmax) fixed the shortfall almost completely but discarded the
  film's own toe/shoulder curvature entirely -- rejected on the grounds that
  the gradualness of a film's own toe/shoulder is real, measured, material-
  specific data, not an incidental detail to erase for mathematical
  convenience.
- v4 (current): fit an actual model to the real digitized curve data
  instead of rescaling or discarding it, then derive the correction
  analytically from that fit. `tools/gamma_correction_fit/` (a separate
  uv-managed tool, scipy/numpy -- see that tool's own README) does the
  fitting; `generate_film_looks.py` stays scipy-free, consuming only the
  fitted parameters as data, the same way it consumes every other derived
  constant.

The model choice (an asymmetric cumulative-Gaussian / "split-normal" CDF,
`sigma_lo`/`sigma_hi` independently fit either side of the inflection) is
grounded in the real physical origin of the H&D curve's shape, not picked
for mathematical convenience: an emulsion is a population of individual
silver-halide grains, each becoming developable once its own quantum catch
crosses its own threshold, and the curve's value at any exposure is
therefore a cumulative distribution of how many grains have crossed
threshold by that exposure.

- **J.H. Webb, "Graphical Analysis of Photographic Exposure and a New
  Theoretical Formulation of the H and D Curve," *J. Opt. Soc. Am.* 29,
  314-326 (1939)** — the primary source for deriving the H&D curve from
  grain-sensitivity-distribution statistics. Not accessible in full text
  during this research (JOSA, paywalled, no free/legal copy found) -- cited
  via the abstract and secondary summaries (confirmed real via multiple
  independent search results, including a direct quote from the abstract:
  "sensitivity variation among grains of a photographic emulsion depends
  upon inherent variation in grain sensitivity among grains of the same
  size class as well as upon size distribution," and the corroborating
  detail that Webb's own resulting equation "cannot be integrated
  mathematically" -- consistent with a cumulative-Gaussian origin, whose
  integral has no elementary closed form either). Flagged here explicitly
  as a citation not independently verified against the primary text, unlike
  every PDF actually saved in this folder.

### Round 4: negative films needed the same correction, for a different reason

After Round 3's fix shipped, real-world use surfaced a second, related
problem: negative-film LUTs (Portra 400 etc.) were rendering *punchier*
than the freshly-corrected reversal films -- backwards from the real
photographic hierarchy, where reversal stock is the punchier material.
Measured directly with `tools/gamma_correction_fit/` (same tool, no new
sources needed -- same J.H. Webb-grounded model applies unchanged to a
camera negative's own H&D curve, which has the identical grain-threshold
physical origin as a reversal film's): negative films' own native gamma is
correctly low (0.47-0.68 per layer, the standard negative-stock design so
it prints near unity contrast on normally-graded paper) -- the mismatch was
on the paper side. `PAPER_LADDER` (the 5 real RA-4 papers negative films
print onto) has its own real measured gammas running steep, 2.5-4.3 across
all 5 papers including "ExtraSoft," and had never actually been checked
against Jones's rule -- its ordering was derived from measuring rendered
*span* (`tools/measure_paper_punch.py`), a different question from "does
this pairing land near the faithful-reproduction target." Fixed the same
way as Round 3: fit `PAPER_LADDER`'s own curves with the same model, and
gamma-correct each negative film against the specific paper it's printing
onto, targeting the same `GAMMA_CORRECT_TARGET` (1.1 at the time, revised
to 1.25 in Round 5 below). No new external citations were needed for this
round -- the physical justification for the model (Webb 1939, cited above)
applies to any silver-halide H&D curve, negative or reversal, equally.

### Round 5: the target itself was the wrong viewing condition

After Round 4 shipped, real-world use of the reversal direct-print route
still read flat and washed-out on screen, even with grey holding and local
gamma near the 1.1 target. The target value itself was wrong, not the
mechanism: `GAMMA_CORRECT_TARGET = 1.1` is Bartleson & Breneman's
*light-surround reflection-print* figure (`choi_bartleson_breneman_...pdf`,
cited above), the right number for a physical print viewed in a lit room.
But this project's actual output is a `.cube` LUT that replaces a raw
processor's tone mapper entirely and is viewed on a self-luminous monitor
-- Radiance III/Ilfochrome/PAPER_LADDER are the real proxy materials this
cascade uses to derive each film's correct response shape, not the final
viewing medium. That's a TV/display viewing condition, not a reflection-
print one, and Bartleson & Breneman published a separate figure for it.

`roufs_global_brightness_contrast_perceptual_image_quality.pdf` (already
saved for Round 2, under-used until now) turns out to measure almost
exactly this project's own output path directly: their test rig was a
**slide (reversal-film) scanner feeding a monitor**. Direct quotes: "the
gamma of the slide scanner - monitor chain was about 1.2 in all cases,"
and "the optimal value for the effective gamma is about 1.2-1.3 ... this
value is very near what Bartleson and Breneman found for TV in 1967."
`GAMMA_CORRECT_TARGET` was revised from 1.1 to 1.25 (the midpoint of
Roufs et al.'s own reported 1.2-1.3 range) on this basis -- no new source
needed to be fetched, the correct figure was already sitting in a source
saved three rounds earlier for a different purpose.

### Round 6: exposed as a tunable instead of re-deriving a fifth fixed number

Real-world use after Round 5 shipped showed 1.25 itself still short of the
punch a reversal film should have on screen. Rather than searching for a
still-more-precise fixed constant a fourth time, `GAMMA_CORRECT_TARGET`
was turned into a CLI-overridable default (`--gamma`, default raised to
1.35) -- the request this time was explicitly for a tunable value, not
another single "correct" number, since the cited literature itself only
pins the TV/display figure to a point estimate (1.2-1.3) under specific
lab conditions that don't exactly match any one viewer's real monitor,
room lighting, or preference. 1.35 stays inside the real cited range this
whole investigation has used throughout (~1.1 light-surround reflection
print to ~1.5-1.6 dark-surround/projection viewing) rather than picking an
arbitrary number outside literature support. No new source was needed for
this round either.

This also surfaced and fixed a real latent bug, independent of the target
value itself: `gamma_correct_curve()`'s `target` parameter had a Python
default-argument value (`target=GAMMA_CORRECT_TARGET`) that gets bound
once, when the function is *defined* (at module import time) -- reassigning
the module-level `GAMMA_CORRECT_TARGET` global later (e.g. from `--gamma`
inside `main()`) would silently have had no effect on already-defined
call sites relying on that stale default. Fixed by making `target` default
to `None` and reading the live module global inside the function body at
call time instead.
