## Unapologeticly AI slop readme. Might find the time to rewrite it to a version that doesn't give you cancer sometime

# Film Look LUTs — Tri-X 400, Velvia 50, Kodachrome 64, Fuji Provia 100F, Kodak Ektachrome 100D

Physically grounded film emulation as .cube LUTs for darktable (or any software supporting 3D LUTs). These replace your tone mapper — they do the complete scene-to-display job that AgX, filmic, or sigmoid would otherwise handle.

**Tri-X 400** — black and white. 6 contrast levels × 6 Wratten glass filters = 36 LUTs per variant.
**Velvia 50, Kodachrome 64, Fuji Provia 100F, Kodak Ektachrome 100D** — color reversal (slide) film. Each has 5 looks (ExtraSoft/Soft/Normal/Punchy/ExtraPunchy), no filters (glass filters would alter a color film's rendering, which is the whole point of choosing one) = 10 LUTs per film (5 looks × classic/modern).

Every color-film look is produced purely by **choice of real print paper** — see "Choosing a print paper" below — not a synthetic contrast multiplier. Total: 112 LUTs.

## What these replicate

Each LUT encodes a complete photographic reproduction chain:

**Tri-X**: scene light → Kodak Wratten glass filter (spectral transmission × film sensitivity) → Tri-X 400 negative (H&D characteristic curve at 7 min development) → Kodak Polymax Fine-Art enlarging paper (at a specific contrast grade) → print reflectance → display. This is the full negative-to-print darkroom process.

**Velvia 50 / Kodachrome 64 / Fuji Provia 100F / Kodak Ektachrome 100D**: scene light → the reversal film's own H&D characteristic curve (3 independent dye layers) → a real duplicating internegative (EASTMAN Color Internegative II Film 5272/7272) → a real RA-4 print paper (see the paper ladder below) → print reflectance → display. All four are reversal (slide) films, not negatives, so none of them can go straight onto negative print paper — real darkroom labs got a *printable* (forgiving) result from a slide by first shooting a duplicating internegative from it, then printing that internegative like an ordinary negative. That's exactly what this cascade does. (An earlier version of this LUT set printed Velvia directly onto a reversal print paper, which is why some `Velvia50_*` files from before might look considerably more contrasty and hard to work with than the current ones — see "Honest limitations". An even earlier version briefly included color *negative* film — Portra 400, Kodak Gold 200, Ektar 100 — which was a dead end: negatives already print straight onto paper with no internegative stage, so they never used the pipeline this project actually built. Removed in favor of more reversal stocks that do.)

## Quick start — darktable setup

1. Turn AgX / filmic / sigmoid **OFF**.
2. Add a **LUT 3D** module instance. Set application color space to **Adobe RGB** (the default `.cube` files) — or to **PQ Rec.2020**, if you generated the LUTs with `--colorspace pq2020` (see "Colour space options" below).
3. Place it where the tone mapper would normally sit (end of the scene-referred section of the pipeline, after exposure, colour balance, etc).
4. Load one .cube file.
5. Use the **exposure** module to position middle grey. The LUT supplies the tonal *shape*; exposure decides where your scene sits on it. If the image looks too dark or too bright, that's an exposure placement issue — nudge it until a known mid-grey reads as mid-grey.

That's it. Output is neutral B&W for Tri-X, full colour for the four color films.

## The files

### Tri-X

Files are named `TriX_<Filter>_<Look>.cube` and live in `trix_classic/` or `trix_modern/`.

**Filters** (folded into the film's spectral response — genuinely "Tri-X shot through this glass"):

| Filter | What it does to the B&W rendering |
|---|---|
| NoFilter | Straight Tri-X. Renders blue sky light, foliage dark. |
| Yellow8 | Gentle sky darkening. The classic everyday B&W filter. |
| Orange21 | Stronger sky contrast, cuts haze. |
| Red25 | Dramatic near-black skies, luminous skin. |
| Green58 | Lifts foliage, flatters skin. |
| Blue47 | Brightens blues, darkens reds. Opposite of red. |

**Looks** (contrast — Kodak Polymax Fine-Art paper grade):

| Look | Polymax grade | Character |
|---|---|---|
| ExtraSoft | 0 | Very open shadows, gentle highlights |
| Soft | 1 | Slightly flat, good for high-contrast scenes |
| Normal | 2 | Standard darkroom printing |
| Punchy | 3 | Snappier midtones |
| ExtraPunchy | 4 | Strong separation, deep shadows |
| Hard | 5 | Dramatic, highlights push to white |

### Velvia 50, Kodachrome 64, Fuji Provia 100F, Kodak Ektachrome 100D

Files are named `<Film>_<Classic|Modern>_<Look>.cube` and live in one folder per film — `velvia/`, `kodachrome64/`, `provia100f/`, `ektachrome100d/` — not split into classic/modern subfolders the way Tri-X is. Tri-X needs the split because each variant already holds 36 files (6 looks × 6 filters); these color films have no filter dimension, so classic+modern together is only 10 files, small enough for one folder. Putting Classic/Modern right after the film name in the filename means a plain alphabetical listing groups all 5 Classic looks together, then all 5 Modern looks together.

No filters — these are all colour films; glass filters would alter their colour rendering, which is the whole point of choosing one.

**Looks** (contrast — real print paper, see "Choosing a print paper" below):

| Look | Paper |
|---|---|
| ExtraSoft | Fuji Crystal Archive Super Type C |
| Soft | Fuji Crystal Archive Pro PDII |
| Normal | Kodak Portra Endura |
| Punchy | Fuji Crystal Archive DPII |
| ExtraPunchy | Kodak Supra Endura |

Same 5 looks, same paper ladder, for all four films — a film's own native contrast just sets where on that ladder "gentle" vs "punchy" lands (see "Choosing a print paper"). There's no `Hard` look for color, unlike Tri-X's 6-grade ladder — deliberately: the ladder stays inside the range of real, non-clipping paper contrasts rather than extrapolating past what real materials offer.

### Classic vs Modern

**Classic** uses the geometric mean (density-space mixing, Tri-X only) or the real per-layer arithmetic mixing (color films) for colour-to-exposure conversion, and the real H&D characteristic curves throughout. No perceptual corrections. This is as close to the physical film process as a 3D LUT allows.

**Modern** adds the Helmholtz-Kohlrausch correction on top. HK accounts for the fact that saturated colours appear brighter to the human eye than their measured luminance — vivid blue sky looks brighter than a grey of equal luminance. Without HK, the B&W conversion can render saturated colours too dark. With it, the tonal separation matches human perception better, at the cost of departing from what the physical film would have produced. For colour films, HK adjusts the overall brightness of saturated inputs, preserving chromaticity while making vivid colours render lighter.

Neither variant is "better" — they serve different goals. Classic is more faithful to the darkroom. Modern produces more satisfying tonal separation to a contemporary viewer.

## Choosing a print paper

Every color-film look in this set is a real print paper, not a math knob — the same approach Tri-X already uses with Polymax's grades 0-5, extended to color. `film_paper_filter_data/papers/color/for_negatives/` has 7 legitimate reflective RA-4 papers (Kodak Endura Premier, Portra Endura, Supra Endura; Fuji Crystal Archive Super Type C, Pro PDII, DPII, Maxima). Cinema release-print stocks (Kodak 2383/2393/5381-series, Technicolor V) and duratrans/backlit display materials (Fujiflex, Duraflex Plus) are excluded outright as the wrong medium, regardless of how their contrast might otherwise fit.

**The ladder is picked by measuring the real cascade, not by estimating one paper at a time.** An earlier version of this table picked papers using each candidate's own regression-slope gamma (least-squares slope over the middle 60% of its own exposure range), multiplied by film γ × internegative γ as a proxy for the compounded result. That proxy turned out not to predict what actually gets rendered: side-by-side comparison of the shipped LUTs found ExtraSoft (Kodak Endura Premier) was in practice the *punchiest* look of the five, and Punchy/ExtraPunchy (Fuji Crystal Archive DPII/Maxima) were barely distinguishable. The proxy also never considered 2 of the 7 real, eligible candidate papers (Fuji Crystal Archive Pro PDII, Kodak Supra Endura) — they were identified as legitimate RA-4 papers early on but never digitized into the shipped ladder.

The fix: `tools/measure_paper_punch.py` (committed, read-only) runs *every* one of the 7 real candidate papers through the actual production cascade — `build_print_cascade()`, `_find_anchor`-calibrated exactly like every shipped LUT, not an isolated regression on the paper's own curve — for each of the 4 color films, and reports what that cascade actually renders: real sensitometric gamma (Δdensity/Δlog10 exposure) in the shadow/mid/highlight bands, and the encoded output at the real LUT corners (full-white and full-black neutral input). Run it yourself with `python3 tools/measure_paper_punch.py` any time paper data changes.

The current 5-paper ladder was picked from that measured output: full-range **span** (white-corner minus black-corner encoded output — the closest single number to "how punchy does this actually render," since it captures both contrast and a paper's own highlight headroom in one measurement) ranks the 7 candidates in the *same order on every one of the 4 films*, so one shared ladder still works for all of them:

| Look | Paper | Velvia 50 | Kodachrome 64 | Fuji Provia 100F | Kodak Ektachrome 100D |
|---|---|---|---|---|---|
| ExtraSoft | Fuji Crystal Archive Super Type C | 0.851 | 0.845 | 0.833 | 0.835 |
| Soft | Fuji Crystal Archive Pro PDII | 0.866 | 0.860 | 0.847 | 0.849 |
| Normal | Kodak Portra Endura | 0.895 | 0.893 | 0.886 | 0.886 |
| Punchy | Fuji Crystal Archive DPII | 0.897 | 0.900 | 0.894 | 0.893 |
| ExtraPunchy | Kodak Supra Endura | 0.919 | 0.919 | 0.916 | 0.914 |

(Span, not gamma — see `tools/measure_paper_punch.py`'s own output for the full shadow/mid/highlight gamma bands per film.) Kodak Endura Premier and Fuji Crystal Archive Maxima both measure well but sit too close to their neighbors on every film to add a usefully distinct rung — the same reason the *previous* ladder left Pro PDII and Supra Endura out — so they're the two left unused now instead.

Normal and Punchy measure close together (span differs by 0.002-0.007) — a real, measured near-tie, not an oversight. They're kept as adjacent rungs anyway because they're the same two papers (Portra Endura, Fuji Crystal Archive DPII) the previous "Soft"/"Punchy" ladder already shipped, side-by-side comparison already confirmed they render as distinguishable in practice, and Normal-below-Punchy is exactly where the real measured data places them.

One real, measured curve-crossover worth flagging, the same kind already documented for Tri-X's Polymax grades 0/1 (`tasks/06-extrasoft-soft-midtone-contrast-inversion.md`) — not a code defect: Pro PDII ("Soft") has *more* local midtone gamma than Portra Endura ("Normal") on every film, even though Pro PDII's overall span is lower. Portra Endura spreads its contrast more gradually across a wider exposure range instead of concentrating it around grey, so Soft/Normal are correctly ordered by overall shadow-to-highlight spread, not by local contrast right around grey — a viewer comparing the two on a subject with detail concentrated near midtone grey may see the "softer" look as locally punchier there.

## The colour science

### Density-space geometric mean (Tri-X) vs. per-layer arithmetic mixing (color films)

Tri-X colour-to-exposure uses `E = R^w_R × G^w_G × B^w_B` (geometric mean) instead of `E = w_R×R + w_G×G + w_B×B` (arithmetic mean). This is equivalent to a weighted average in log-density space, which models how film's logarithmic response to light actually works. The practical effect: deeper blacks on filter-blocked colours, more aggressive midtone separation, and physically correct zero-exposure when a filter completely blocks a channel.

This is only valid on scene-referred linear data — which is what these LUTs operate on (Adobe RGB decoded to linear before processing).

For every color film (Velvia, Kodachrome 64, Provia 100F, Ektachrome 100D), each of the 3 dye layers computes its own exposure from the input RGB via an arithmetic weighted sum (not geometric), because each layer responds to a narrow spectral band where the geometric mean's cross-channel suppression doesn't apply physically.

### Helmholtz-Kohlrausch correction (modern variants only)

Based on Fairchild & Pirrotta 1991 (*Color Research and Application* 16(6)). The model operates in CIELCh space:

```
L** = L* + (2.5 − 0.025·L*) · (0.116·|sin((h−90°)/2)| + 0.085) · C*
```

The correction is strongest for blue (h ≈ 270°) and red (h ≈ 0°/360°), weakest for yellow-green. It's converted to a linear exposure multiplier via the L*→Y inverse, then applied to the film exposure.

**The exposure multiplier is capped at `HK_MAX_MUL = 3.0×` (an explicit invariant, alongside `GREY = 0.18`).** The formula above has no built-in ceiling — `dL` grows linearly with `C*` forever, and its `(2.5 − 0.025·L*)` term is largest at low lightness, so dark, saturated pixels get the biggest (and least-validated) boost. Fairchild & Pirrotta fit and tested the model only against real Munsell surface chips (their published Table I): `L*` in roughly [30, 87], `C*` in roughly [6, 87]. Adobe RGB scene-linear data (used here deliberately for its wide gamut) routinely produces chroma well outside that range — e.g. saturated blue reaches `C* ≈ 136`, almost 60% past anything the model was ever checked against — and the formula happily extrapolates into multipliers of 6–7× rather than tapering off.

To pick a defensible ceiling rather than an arbitrary one: the largest luminance-matching ratio implied by any *measured* (not merely modelled) data point in Fairchild & Pirrotta's own Table I is about **2.7×** (sample 5PB3/10 — a dark, saturated purple-blue chip at `L* = 30.42`, `C* = 44.05` — matched to an achromatic lightness of 48.6, versus its own `L*` of 30.42). `HK_MAX_MUL = 3.0` sits just above that best-supported real data point, leaving ordinary saturated shadows and midtones (which land well under the cap — a cool-shadow color cast typically multiplies exposure by 1.6–1.9×) untouched, while cutting off the unbounded extrapolation that only wide-gamut synthetic colors ever reach.

Note this bounds `hk_mul()`'s own output, not necessarily the final pixel-value ratio between classic and modern LUTs — the negative/paper (Tri-X) or reversal (color films) transfer function's own local contrast can still amplify or damp a bounded exposure change, same as it does for any other exposure difference. That's expected film-curve behavior, not a regression of this bound.

### Perceptual effects not implemented (and why)

Five additional perceptual phenomena were evaluated for inclusion in the "modern" variants:

**Bezold-Brücke shift** (hue shifts with luminance): for B&W, the output is achromatic — no hue to shift. For the color films, the effect magnitude at SDR display luminance is approximately 2-5nm of hue shift, which is below the threshold of practical relevance and would alter the film's authentic hue rendering.

**Purkinje effect** (scotopic sensitivity shift): only applies at scotopic (rod-mediated) light levels. Display viewing is photopic. Not applicable.

**Hunt effect** (colorfulness increases with luminance): partially captured by HK's lightness-dependent term. For the reversal films, their own steep dye curves already produce a natural saturation boost in highlights. Explicit Hunt correction risks over-saturation on already-punchy stocks.

**Abney effect** (white-light-induced hue shift): too subtle at display luminance levels to produce a visible difference in the output.

**Chromatic adaptation**: handled by the white balance module upstream in the pipeline. Not the LUT's job.

## Honest limitations

**Highlight clipping**: both `adobergb` and `pq2020` clip input at exactly the same real exposure — middle-grey + 2.5 stops at 0 EV — because in a `.cube`'s `[0,1]` domain, encoded 1.0 always means linear pixel value 1.0, regardless of whether the curve between 0 and 1 is a fixed gamma or PQ. PQ doesn't move that ceiling. What it changes is only how the `[0,1]` code axis is distributed: PQ compresses shadow/mid detail heavily and leaves the clip point approached very gradually, which darktable's scene-referred lut3d input mode (this project's own darktable branch; not upstream) extrapolates past more gracefully than gamma's steep near-peak slope. Middle grey lands high on the PQ axis (code ~0.816) as a result, but this needs no exposure compensation — the LUT is anchored on scene-linear grey, so a normally-exposed frame renders grey as grey either way (see "Colour space options" for the one dropdown that must match). Either way, the print shoulder (Tri-X) and reversal shoulder (color films) already roll off highlights, so for most pictorial photography the loss is small.

**Every color-film look ladder is now real material data, not a synthetic contrast curve** — Velvia's grades used to be a parametric power-curve adjustment (no real multi-grade print data existed), and the one real-paper Velvia look that did exist (direct printing onto Kodak Ektachrome Radiance III) was structurally very contrasty, because printing a reversal film directly onto *any* reversal print paper compounds two already-high-contrast stages (confirmed against real Cibachrome/Ilfochrome and R-3 process accounts, not just this dataset). The fix was architectural, not a better parameter: real darkroom labs never printed slides directly either, for the same reason — they duplicated the slide onto an internegative first, which is a genuinely low-contrast material (measured γ≈0.527, digitized from EASTMAN Color Internegative II Film 5272/7272's real datasheet — see "Choosing a print paper"), then printed *that* like an ordinary negative. Two real print-paper candidates were tried and rejected for the old direct-print approach along the way: Ilfochrome Micrographic M/P (duplicating/microfilm stock, not pictorial paper, and its own gamma compounds with a reversal film's into an unusably contrasty, clipping result) and Kodak Dye Transfer (flagged by its own source library as "very experimental and unreliable," and its "for Slides" variant turned out to be a renamed copy of the unfinished Kodachrome curve, not independent data) — neither was fabricated data, both were real candidates that didn't hold up.

**Only reversal (slide) film is included, on purpose**: an earlier version of this project briefly added three color negative films (Portra 400, Kodak Gold 200, Ektar 100). They were removed — negatives print straight onto paper with no internegative stage, so they never exercised the internegative pipeline that's the actual point of this project's color-film architecture. If negative film support returns, it belongs as a genuinely separate 2-stage cascade (the same shape `build_trix_cascade()` already uses), not folded into the reversal-film lineup.

**Grain and halation**: spatial effects that a per-pixel LUT cannot represent. Use darktable's grain module and/or the Diffuse or Sharpen module with red-channel blend mode for halation simulation.

**Chromatic aberration interaction**: strong contrast filters (Red25, Blue47) amplify edge colour artifacts from darktable's chromatic aberration correction module. This is because the filter maps near-invisible colour shifts at edges into large luminance differences. Disable automatic CA correction when using strong filters, or use it sparingly.

**Spectral-to-RGB approximation**: converting a film's spectral sensitivity curve into three RGB weights assumes the selected colour space's primary spectra (Adobe RGB by default, or Rec.2020 with `--colorspace pq2020`). The weight magnitudes are approximate; the rendering character is robust and matches documented film behaviour.

**Two B&W stocks only**: Tri-X 400 and Double-X 5222 are the only B&W negatives with real digitized data available (from JanLohse/spectral_film_lut). The famous rest of the B&W roster — HP5, FP4, T-Max, Acros, Delta — is not included because the data does not exist in digitized form and we did not fabricate it.

**Iconic reversal stocks left out on purpose**: Kodak Aerochrome III (false-color infrared — a distinct creative effect, not "what a normal photo looked like," and its own native gamma is steep enough to compound close to the clipping zone even through the internegative) and Fuji FP-100C / Instax color (integral instant print materials — the shot is already a print the moment it develops; there's no real historical practice of duplicating an instant print onto an internegative, so the whole cascade this project builds wouldn't correspond to anything real for them).

## Colour space options

`--colorspace` picks which LUT-module application colour space the generated `.cube` files target. It has to match whatever you set in darktable's lut3d module (step 2 of "Quick start"), because it changes both the input/output transfer curve baked into the LUT *and* the RGB primaries used to compute the film's spectral weights (`R=`/`G=`/`B=` in each file's header comment).

**`adobergb` (default)**: A .cube LUT needs gamma-encoded input so the grid distributes its sample points where shadows and midtones need precision. Among the gamma-based encodings darktable's lut3d module offers, Adobe RGB has the widest colour gamut. This means saturated scene colours survive into the spectral weighting rather than being gamut-clipped before the film "sees" them. The gamma precision is equivalent to sRGB; the wider primaries are the deciding advantage. Its fixed 2.2-ish gamma is also what clips highlights at roughly middle-grey + 2.5 stops — see "Highlight clipping" below.

**`pq2020`**: Rec.2020 primaries (wider still than Adobe RGB) encoded with SMPTE ST 2084 (PQ) instead of a fixed gamma, applied completely unscaled — `pqenc`/`pqdec` are the exact same formula and constants darktable's own PQ Rec.2020 profile uses internally, which they have to be: the code axis position has to mean the same real exposure to this script as it does to darktable, and that requires an exact mathematical inverse, not a relabelled or rescaled one (an earlier version of this tool multiplied in a 203-nit "reference white" factor and got measurably wrong output — the film math read every image ~5.6 stops overexposed, so everything blew out — because it silently required the user to hit one exact, undocumented exposure value for the round-trip to stay correct). One consequence of the exact match: encoded 1.0 always means linear pixel value 1.0 for *any* `[0,1]`-domain transfer curve, gamma or PQ, so `pq2020`'s hard clip point sits at exactly the same real exposure as `adobergb`'s (~middle-grey + 2.5 stops at 0 EV) — PQ does not raise that ceiling. What PQ changes is only how the code axis is distributed: it's heavily compressed near the top, so most of the axis carries shadow/mid detail. Middle grey therefore lands high on the axis, at code ~0.816 (vs Adobe RGB's ~0.459) — but that needs **no** exposure compensation, because the LUT is anchored on *scene-linear* grey: feed it a normally-exposed frame (grey ≈ 0.18) and grey renders as grey, identical to the `adobergb` build in scene-linear terms. (An earlier version of this note claimed you needed ~-5 EV to "move grey off the compressed region" — that was wrong, and would render the image near-black.)

> **The one setting that must be right.** A `pq2020` `.cube` renders correctly only if darktable's LUT 3D module has **application color space = "PQ Rec2020 RGB"** (this project's darktable branch adds it) — and, per the project's intent, **input = scene-referred**. That dropdown *defaults to sRGB*. An Adobe RGB cube tolerates the sRGB default because Adobe's gamma ≈ sRGB (only a slight tone shift), so it's easy to never touch the dropdown — but a PQ cube read as sRGB is a wild curve mismatch: the effective transfer is flat and dark from −3 to +1 stop, then steps to white by +2, giving an image made of only crushed and blown pixels with exposure just shifting the ratio between them. **If a `pq2020` render looks like that, the application color space dropdown is wrong, not the LUT.**

`hk_mul()`'s `HK_MAX_MUL = 3.0` cap (see "Helmholtz-Kohlrausch correction" below) was derived against Adobe RGB's gamut specifically and hasn't been re-derived for Rec.2020's wider primaries — it still applies as a conservative ceiling, just not necessarily an optimal one, when this option is selected.

## Data provenance

**Tri-X 400**: spectral sensitivity from the Tri-X Pan 5063 emulsion as published in Kodak datasheet F-4017. Characteristic curve at 7 minutes development.

**Velvia 50, Kodachrome 64, Fuji Provia 100F, Kodak Ektachrome 100D**: spectral sensitivity (3 dye layers) and characteristic curves (3 layers, reversal) from the published Fujifilm/Kodak datasheets.

**Polymax Fine-Art**: characteristic curves at contrast grades 0 through 5 from the published Kodak datasheet.

**EASTMAN Color Internegative II Film 5272/7272**: spectral sensitivity and characteristic curve (3 layers), digitized directly from the real Kodak/Eastman datasheet TI1301 (`papers/kodak_internegative_ii_5272_TI1301.pdf`) via `film_paper_filter_data/tools/curve_digitizer/` — a purpose-built tool that reads the PDF's own vector drawing commands for each curve rather than tracing a rendered image, so extraction precision is limited only by the source document's own geometry, not by any rasterization DPI. See that tool's README for the extraction method (axis calibration from tick-label text positions, monotonicity enforcement via isotonic regression for the real material curve, Ramer-Douglas-Peucker simplification to a shape-preserving sparse point set).

**Print papers (Kodak Endura Premier, Kodak Portra Endura, Kodak Supra Endura, Fuji Crystal Archive Super Type C / Pro PDII / DPII / Maxima)**: characteristic curves (3 layers each) from published manufacturer datasheets.

**Wratten filters**: spectral transmission data from Kodak Publication B-3, "Handbook of Kodak Photographic Filters" (1990, ISBN 0-87985-658-0), transcribed by Paul Repacholi (1992), hosted at the University of Coimbra (mat.uc.pt). Cross-validated against the UEA Colour Group's wratten-db.

Film and paper curves and spectral sensitivities not otherwise noted above were digitized by the open-source project [spectral_film_lut](https://github.com/JanLohse/spectral_film_lut) (MIT license), pooled for reference in `film_paper_filter_data/`. CIE 1931 colour matching functions and the D65 illuminant are international standards.

## Generating

```
python generate_film_looks.py                                # 65^3, all 112 LUTs, Adobe RGB
python generate_film_looks.py --size 33                       # faster, smaller files
python generate_film_looks.py --only trix                      # Tri-X only (72 LUTs)
python generate_film_looks.py --only velvia kodachrome64        # just these two (20 LUTs)
python generate_film_looks.py --colorspace pq2020                # Rec.2020 + PQ instead of Adobe RGB
```

`--only` accepts any subset of `trix velvia kodachrome64 provia100f ektachrome100d`. Omit it for everything.

`--colorspace` accepts `adobergb` (default) or `pq2020` — see "Colour space options" below. It changes what the LUT expects as input/output, so match it to whatever you set as the lut3d module's application color space.

No dependencies beyond Python 3 standard library.

## License

The generator script and resulting LUT files are provided as-is. Film data is from published manufacturer datasheets, digitized under MIT license. CIE and D65 data are international standards. Wratten data is published reference material.
