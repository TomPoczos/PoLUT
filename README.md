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
2. Add a **LUT 3D** module instance. Set application color space to **Adobe RGB**.
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
| ExtraSoft | Kodak Endura Premier |
| Soft | Kodak Portra Endura |
| Normal | Fuji Crystal Archive Super Type C |
| Punchy | Fuji Crystal Archive DPII |
| ExtraPunchy | Fuji Crystal Archive Maxima |

Same 5 looks, same paper ladder, for all four films — a film's own native contrast just sets where on that ladder "gentle" vs "punchy" lands (see "Choosing a print paper"). There's no `Hard` look for color, unlike Tri-X's 6-grade ladder — deliberately: the ladder stays inside the range of real, non-clipping paper contrasts rather than extrapolating past what real materials offer.

### Classic vs Modern

**Classic** uses the geometric mean (density-space mixing, Tri-X only) or the real per-layer arithmetic mixing (color films) for colour-to-exposure conversion, and the real H&D characteristic curves throughout. No perceptual corrections. This is as close to the physical film process as a 3D LUT allows.

**Modern** adds the Helmholtz-Kohlrausch correction on top. HK accounts for the fact that saturated colours appear brighter to the human eye than their measured luminance — vivid blue sky looks brighter than a grey of equal luminance. Without HK, the B&W conversion can render saturated colours too dark. With it, the tonal separation matches human perception better, at the cost of departing from what the physical film would have produced. For colour films, HK adjusts the overall brightness of saturated inputs, preserving chromaticity while making vivid colours render lighter.

Neither variant is "better" — they serve different goals. Classic is more faithful to the darkroom. Modern produces more satisfying tonal separation to a contemporary viewer.

## Choosing a print paper

Every color-film look in this set is a real print paper, not a math knob — the same approach Tri-X already uses with Polymax's grades 0-5, extended to color. The method:

1. **Pick real, same-medium candidates.** `film_paper_filter_data/papers/color/for_negatives/` has 7 legitimate reflective RA-4 papers (Kodak Endura Premier, Portra Endura, Supra Endura; Fuji Crystal Archive Super Type C, Pro PDII, DPII, Maxima). Cinema release-print stocks (Kodak 2383/2393/5381-series, Technicolor V) and duratrans/backlit display materials (Fujiflex, Duraflex Plus) are excluded outright as the wrong medium, regardless of how their contrast might otherwise fit.
2. **Compute each candidate's own gamma** (regression slope over the middle 60% of each layer's exposure range), then the *compounded* system gamma with each film: film γ × internegative γ (≈0.527, fixed — every film here routes through the same internegative) × paper γ.
3. **Calibrate against a known-good reference.** Tri-X + Polymax grade 2 — unambiguously "normal" B&W printing — computes to system γ ≈ 1.16 by this same method. That's the target zone color "Normal" should land near.
4. **Pick 5 papers spanning that range with reasonable spacing**, reusing the same 5 papers across every film (their compounded-gamma order is preserved regardless of which film multiplies in front, so one shared ladder works for all four).

Measured native film gammas: Velvia 50 ≈1.63, Kodachrome 64 ≈1.84, Fuji Provia 100F ≈1.48, Kodak Ektachrome 100D ≈1.76. Resulting compounded system gamma per look (all four route through the same internegative, γ≈0.527):

| Look | Paper | Velvia 50 | Kodachrome 64 | Fuji Provia 100F | Kodak Ektachrome 100D |
|---|---|---|---|---|---|
| ExtraSoft | Kodak Endura Premier | 1.54 | 1.74 | 1.40 | 1.67 |
| Soft | Kodak Portra Endura | 1.62 | 1.82 | 1.47 | 1.74 |
| Normal | Fuji Crystal Archive Super Type C | 1.76 | 1.99 | 1.60 | 1.90 |
| Punchy | Fuji Crystal Archive DPII | 1.94 | 2.19 | 1.76 | 2.09 |
| ExtraPunchy | Fuji Crystal Archive Maxima | 2.11 | 2.38 | 1.91 | 2.27 |

Provia 100F's whole range sits comfortably below where the previous (now-removed) direct-to-reversal-paper Velvia look measured (system γ 1.91). Kodachrome 64 and Ektachrome 100D's ExtraPunchy nudges into the 2.2-2.4 range — still well clear of the Ilfochrome-direct-print clipping zone (2.0-3.0) that was rejected for lacking an internegative stage, precisely because the internegative is what keeps every one of these films printable in the first place — see "What these replicate" above.

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

**Highlight clipping**: Adobe RGB encoding clips input at approximately middle-grey + 2.5 stops. This is a fundamental limitation of the .cube LUT format — no wide-range perceptual encoding (PQ, log) is available in darktable's lut3d module. The print shoulder (Tri-X) and reversal shoulder (color films) already roll off highlights, so for most pictorial photography the loss is small.

**Every color-film look ladder is now real material data, not a synthetic contrast curve** — Velvia's grades used to be a parametric power-curve adjustment (no real multi-grade print data existed), and the one real-paper Velvia look that did exist (direct printing onto Kodak Ektachrome Radiance III) was structurally very contrasty, because printing a reversal film directly onto *any* reversal print paper compounds two already-high-contrast stages (confirmed against real Cibachrome/Ilfochrome and R-3 process accounts, not just this dataset). The fix was architectural, not a better parameter: real darkroom labs never printed slides directly either, for the same reason — they duplicated the slide onto an internegative first, which is a genuinely low-contrast material (measured γ≈0.527, digitized from EASTMAN Color Internegative II Film 5272/7272's real datasheet — see "Choosing a print paper"), then printed *that* like an ordinary negative. Two real print-paper candidates were tried and rejected for the old direct-print approach along the way: Ilfochrome Micrographic M/P (duplicating/microfilm stock, not pictorial paper, and its own gamma compounds with a reversal film's into an unusably contrasty, clipping result) and Kodak Dye Transfer (flagged by its own source library as "very experimental and unreliable," and its "for Slides" variant turned out to be a renamed copy of the unfinished Kodachrome curve, not independent data) — neither was fabricated data, both were real candidates that didn't hold up.

**Only reversal (slide) film is included, on purpose**: an earlier version of this project briefly added three color negative films (Portra 400, Kodak Gold 200, Ektar 100). They were removed — negatives print straight onto paper with no internegative stage, so they never exercised the internegative pipeline that's the actual point of this project's color-film architecture. If negative film support returns, it belongs as a genuinely separate 2-stage cascade (the same shape `build_trix_cascade()` already uses), not folded into the reversal-film lineup.

**Grain and halation**: spatial effects that a per-pixel LUT cannot represent. Use darktable's grain module and/or the Diffuse or Sharpen module with red-channel blend mode for halation simulation.

**Chromatic aberration interaction**: strong contrast filters (Red25, Blue47) amplify edge colour artifacts from darktable's chromatic aberration correction module. This is because the filter maps near-invisible colour shifts at edges into large luminance differences. Disable automatic CA correction when using strong filters, or use it sparingly.

**Spectral-to-RGB approximation**: converting a film's spectral sensitivity curve into three RGB weights assumes Adobe RGB primary spectra. The weight magnitudes are approximate; the rendering character is robust and matches documented film behaviour.

**Two B&W stocks only**: Tri-X 400 and Double-X 5222 are the only B&W negatives with real digitized data available (from JanLohse/spectral_film_lut). The famous rest of the B&W roster — HP5, FP4, T-Max, Acros, Delta — is not included because the data does not exist in digitized form and we did not fabricate it.

**Iconic reversal stocks left out on purpose**: Kodak Aerochrome III (false-color infrared — a distinct creative effect, not "what a normal photo looked like," and its own native gamma is steep enough to compound close to the clipping zone even through the internegative) and Fuji FP-100C / Instax color (integral instant print materials — the shot is already a print the moment it develops; there's no real historical practice of duplicating an instant print onto an internegative, so the whole cascade this project builds wouldn't correspond to anything real for them).

## Why Adobe RGB

A .cube LUT needs gamma-encoded input so the grid distributes its sample points where shadows and midtones need precision. Among the encodings darktable's lut3d module offers, Adobe RGB has the widest colour gamut of the gamma options. This means saturated scene colours survive into the spectral weighting rather than being gamut-clipped before the film "sees" them. The gamma precision is equivalent to sRGB; the wider primaries are the deciding advantage.

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
python generate_film_looks.py                                # 65^3, all 112 LUTs
python generate_film_looks.py --size 33                       # faster, smaller files
python generate_film_looks.py --only trix                      # Tri-X only (72 LUTs)
python generate_film_looks.py --only velvia kodachrome64        # just these two (20 LUTs)
```

`--only` accepts any subset of `trix velvia kodachrome64 provia100f ektachrome100d`. Omit it for everything.

No dependencies beyond Python 3 standard library.

## License

The generator script and resulting LUT files are provided as-is. Film data is from published manufacturer datasheets, digitized under MIT license. CIE and D65 data are international standards. Wratten data is published reference material.
