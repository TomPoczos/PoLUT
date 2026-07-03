## Unapologeticly AI slop readme. Might find the time to rewrite it to a version that doesn't give you cancer sometime

# Film Look LUTs — Tri-X 400, Velvia 50, Kodachrome 64, Fuji Provia 100F, Kodak Ektachrome 100D, Kodak Portra 400, Kodak Ektar 100, Kodak Gold 200, Kodak Ultramax 400, Fuji Superia Reala, Fuji Superia X-tra 400

Physically grounded film emulation as .cube LUTs for darktable (or any software supporting 3D LUTs). These replace your tone mapper — they do the complete scene-to-display job that AgX, filmic, or sigmoid would otherwise handle.

**Tri-X 400** — black and white. 6 contrast levels × 6 Wratten glass filters = 36 LUTs per variant.
**Velvia 50, Kodachrome 64, Fuji Provia 100F, Kodak Ektachrome 100D** — color reversal (slide) film. Each has 8 looks: 5 through a real duplicating internegative (ExtraSoft/Soft/Normal/Punchy/ExtraPunchy) and 3 printed directly onto a real reversal print paper with no internegative (RadianceIII/IlfochromeM/IlfochromeP) — no filters (glass filters would alter a color film's rendering, which is the whole point of choosing one) = 16 LUTs per film (8 looks × classic/modern). See "Why a reversal print crushes without correction" below for what the direct-print route is and why it needed more than just swapping the paper.
**Kodak Portra 400, Kodak Ektar 100, Kodak Gold 200, Kodak Ultramax 400, Fuji Superia Reala, Fuji Superia X-tra 400** — color *negative* film. Same 5-look / no-filters shape as the reversal films' internegative route (10 LUTs per film), but a shorter 2-stage print cascade — see "What these replicate" below for why.

Every color-film look is produced purely by **choice of real print paper** — see "Choosing a print paper" below — not a synthetic contrast multiplier. Total: 196 LUTs.

## What these replicate

Each LUT encodes a complete photographic reproduction chain:

**Tri-X**: scene light → Kodak Wratten glass filter (spectral transmission × film sensitivity) → Tri-X 400 negative (H&D characteristic curve at 7 min development) → Kodak Polymax Fine-Art enlarging paper (at a specific contrast grade) → print reflectance → display. This is the full negative-to-print darkroom process.

**Velvia 50 / Kodachrome 64 / Fuji Provia 100F / Kodak Ektachrome 100D**: each of these four reversal (slide) films gets *two* independent print routes, both shipped, in the same folder.

The **internegative route** (5 looks — ExtraSoft through ExtraPunchy): scene light → the reversal film's own H&D characteristic curve (3 independent dye layers) → a real duplicating internegative (EASTMAN Color Internegative II Film 5272/7272) → a real RA-4 print paper (see the paper ladder below) → print reflectance → display — none of these four can go straight onto ordinary negative print paper, so real darkroom labs got a *printable* (forgiving) result from a slide by first shooting a duplicating internegative from it, then printing that internegative like an ordinary negative. That's exactly what this cascade does.

The **direct-print route** (3 looks — RadianceIII/IlfochromeM/IlfochromeP): scene light → the reversal film's own H&D curve, gamma-corrected first → a real print paper built to accept a reversal original directly, with no internegative stage → print reflectance → display. See "Why a reversal print crushes without correction" below for why the correction step is there and what it's based on — without it, this route reproduces the same over-contrasty crush an earlier, uncorrected version of this project shipped once and replaced (see "Honest limitations").

**Kodak Portra 400 / Kodak Ektar 100 / Kodak Gold 200 / Kodak Ultramax 400 / Fuji Superia Reala / Fuji Superia X-tra 400**: scene light → the negative's own H&D characteristic curve (3 independent dye layers), gamma-corrected against whichever real RA-4 print paper follows it → that paper → print reflectance → display. These are genuine camera *negatives* — unlike the four reversal stocks above, a negative already prints straight onto paper (that's what negative film *is for*), so there's no internegative stage to route through. An earlier version of this project briefly included three of these same films (Portra 400, Kodak Gold 200, Ektar 100), folded into the reversal-film lineup, and removed them because they didn't exercise the internegative pipeline the reversal-film architecture exists to demonstrate. They're back now as a genuinely separate, shorter cascade (`NEGATIVE_FILMS`/`_negative_gammacorrect_stage_fn()` in `generate_film_looks.py`) instead of being forced into the reversal shape — see "Choosing a print paper" for why the same 5-paper ladder works for negatives too, and "Why a reversal print crushes without correction" for why these are gamma-corrected too, not just the reversal direct-print route.

## Quick start — darktable setup

1. Turn AgX / filmic / sigmoid **OFF**.
2. Add a **LUT 3D** module instance. Set application color space to **Adobe RGB** (the default `.cube` files) — or to **PQ Rec.2020**, if you generated the LUTs with `--colorspace pq2020` (see "Colour space options" below).
3. Place it where the tone mapper would normally sit (end of the scene-referred section of the pipeline, after exposure, colour balance, etc).
4. Load one .cube file.
5. Use the **exposure** module to position middle grey. The LUT supplies the tonal *shape*; exposure decides where your scene sits on it. If the image looks too dark or too bright, that's an exposure placement issue — nudge it until a known mid-grey reads as mid-grey.

That's it. Output is neutral B&W for Tri-X, full colour for the ten color films.

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

Files are named `<Film>_<Classic|Modern>_<Look>.cube` and live in one folder per film — `velvia/`, `kodachrome64/`, `provia100f/`, `ektachrome100d/` — not split into classic/modern subfolders the way Tri-X is, and not split by print route either: internegative-route and direct-print-route looks live side by side in the same folder. Tri-X needs the classic/modern split because each variant already holds 36 files (6 looks × 6 filters); these color films have no filter dimension, so classic+modern together is only 16 files, small enough for one folder. Putting Classic/Modern right after the film name in the filename means a plain alphabetical listing groups all 8 Classic looks together, then all 8 Modern looks together.

No filters — these are all colour films; glass filters would alter their colour rendering, which is the whole point of choosing one.

**Looks** (contrast — real print paper/route, see "Choosing a print paper" and "Why a reversal print crushes without correction" below):

| Look | Route | Paper |
|---|---|---|
| ExtraSoft | internegative | Fuji Crystal Archive Super Type C |
| Soft | internegative | Fuji Crystal Archive Pro PDII |
| Normal | internegative | Kodak Portra Endura |
| Punchy | internegative | Fuji Crystal Archive DPII |
| ExtraPunchy | internegative | Kodak Supra Endura |
| RadianceIII | direct print, gamma-corrected | Kodak Ektachrome Radiance III |
| IlfochromeM | direct print, gamma-corrected | Ilfochrome Micrographic M |
| IlfochromeP | direct print, gamma-corrected | Ilfochrome Micrographic P |

Same 8 looks, same two routes, for all four films — a film's own native contrast just sets where on either ladder "gentle" vs "punchy" lands. There's no `Hard` look for color, unlike Tri-X's 6-grade ladder — deliberately: the ladder stays inside the range of real, non-clipping paper contrasts rather than extrapolating past what real materials offer.

### Kodak Portra 400, Kodak Ektar 100, Kodak Gold 200, Kodak Ultramax 400, Fuji Superia Reala, Fuji Superia X-tra 400

Files are named the same way as the reversal films — `<Film>_<Classic|Modern>_<Look>.cube` — but each lives in its own flat, prefixed folder: `negative-portra-400/`, `negative-ektar-100/`, `negative-gold-200/`, `negative-ultramax-400/`, `negative-superia-reala/`, `negative-superia-xtra-400/`. The `negative-` prefix (rather than a `negative/` parent folder) keeps the folder listing flat instead of adding another directory level for six films.

Same paper ladder, same 5 looks (ExtraSoft through ExtraPunchy), no filters, no `Hard` look — identical shape to the reversal films' file layout, just a shorter cascade underneath (see "What these replicate").

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

**The same ladder is reused, unmodified, for the six negative films** (Portra 400, Ektar 100, Gold 200, Ultramax 400, Superia Reala, Superia X-tra 400) — not just because the papers are literally drawn from `film_paper_filter_data/papers/color/for_negatives/`, but checked directly: re-running the same span measurement through each negative film's own (shorter, 2-stage, no-internegative) cascade reproduces the identical ExtraSoft < Soft < Normal < Punchy < ExtraPunchy rank order on every one of the 6, with no crossovers. `tools/measure_paper_punch.py` only iterates `COLOR_FILMS` (the 4 reversal stocks) as shipped — it wasn't extended to loop `NEGATIVE_FILMS` too, so this was checked ad hoc rather than being a re-runnable part of that script; worth doing if paper data changes again.

Normal and Punchy measure close together (span differs by 0.002-0.007) — a real, measured near-tie, not an oversight. They're kept as adjacent rungs anyway because they're the same two papers (Portra Endura, Fuji Crystal Archive DPII) the previous "Soft"/"Punchy" ladder already shipped, side-by-side comparison already confirmed they render as distinguishable in practice, and Normal-below-Punchy is exactly where the real measured data places them.

One real, measured curve-crossover worth flagging, the same kind already documented for Tri-X's Polymax grades 0/1 (`tasks/06-extrasoft-soft-midtone-contrast-inversion.md`) — not a code defect: Pro PDII ("Soft") has *more* local midtone gamma than Portra Endura ("Normal") on every film, even though Pro PDII's overall span is lower. Portra Endura spreads its contrast more gradually across a wider exposure range instead of concentrating it around grey, so Soft/Normal are correctly ordered by overall shadow-to-highlight spread, not by local contrast right around grey — a viewer comparing the two on a subject with detail concentrated near midtone grey may see the "softer" look as locally punchier there.

## Why a reversal print crushes without correction

This section explains the physics behind the direct-print route's `gamma_correct_curve()` step in `generate_film_looks.py` — a piece of ~100-year-old sensitometric theory that isn't documented anywhere else in this project, so it gets a full writeup here rather than a one-line comment. Full source trail (every PDF, patent, and web page cited below) lives in `papers/` and `papers/masking_research/README.md`.

**The problem, measured.** Print a reversal film's own H&D curve straight onto a real print paper — no internegative, no correction — and the result crushes to only about 3-3.5 stops of real tonal separation around grey, even though the film's own digitized curve spans roughly 9 stops. Concretely, Kodak Ektachrome Radiance III printed straight from Kodachrome 64, uncorrected: encoded output is already pinned to ~0.93 by +1.5 EV over grey and ~0.005 by -1.5 EV. That's not a data error or a code bug — every number in that chain is real, digitized manufacturer data, correctly cascaded. It's a real, physical property of the material pairing.

**Why.** L.A. Jones's 1920 paper *"On the Theory of Tone Reproduction, with a Graphic Method for the Solution of Problems"* (`papers/jones_1920_theory_of_tone_reproduction.pdf`, p.64 — the origin of what's sometimes called Goldberg's rule) states it plainly: *"the product of the gamma of the negative by that of the positive is equal to that of the reproduction curve"* — γ₁ × γ₂ × ... = γ_system, with Jones's own worked example landing at γ_system ≈ 1.01. For a print to faithfully reproduce the tonal range of the scene it depicts, the gammas of every stage in the chain need to multiply out to about 1.0. Every real photographic material has gamma > 0, so unless something in the chain has gamma measurably below 1, the product overshoots 1 and the print comes out more contrasty than the scene — exactly the crush measured above. A still reversal film's own native gamma is already high before it even reaches a paper: measured directly off each film's own digitized curve (`_measured_gamma()`), Velvia 50 ≈ 2.0-2.1, Kodachrome 64 ≈ 1.7-1.9, Provia 100F ≈ 1.6-1.8, Ektachrome 100D ≈ 1.4-1.9 per layer. Pair that directly with a real print paper's own real gamma (Radiance III ≈ 1.2-1.3, Ilfochrome Micrographic M ≈ 1.9-2.1, Ilfochrome Micrographic P ≈ 1.4-1.6, also measured off their own digitized curves) and the product is well past 1 before you even account for anything else.

**Real duplicating labs hit this exact wall.** EASTMAN Color Internegative Film (the stock this project's internegative route already uses) was engineered so internegative gamma (~0.5) times a real print-paper gamma (~2.0) lands close to 1.0 — but that arithmetic assumes a gamma-≈1.0 input. Its real intended input was Ektachrome Commercial, a low-contrast *duplicating positive*, "never projected" (`papers/masking_research/brianpritchard_FAOL_colour_duplicating_film_stocks.html`) — not a full-contrast camera original. Feed it (or any similarly-engineered paper) a real reversal film instead, and the identical mismatch appears, just hidden behind an extra stage — which is exactly why this project's internegative route (left untouched by this fix, see below) still has the same problem underneath, and exactly why an earlier version of this project's *uncorrected* direct Radiance III cascade (commit `cf14a88`, replaced in `881f3da`) was, in the previous README's own words, "structurally very contrasty."

Real labs' own fixes for a too-contrasty original were real, but neither has a published formula: **flashing** — a second, spectrally-neutral pre-exposure, confirmed as real hardware in US Patent 4,739,375 (`papers/patent_US4739375_internegative_contrast_correction_flash.pdf`, a photoflash-based internegative duplicator with a dedicated "contrast correction exposure" unit) — and **optical contrast-reduction sandwich masking** (`papers/masking_research/freestylephoto_contrast_masking_traditional_print.html`). The most authoritative secondary source found on this (brianpritchard.com's Film Archive Online Library, written for working motion-picture archivists) says of flashing: "none [are] satisfactory." Flashing also only ever partially fixes the problem it's used for — it adds density to the toe/shadows but leaves the shoulder/highlights' own gamma close to untouched — which doesn't match the crush measured above, which happens symmetrically at both ends.

### Why the target is 1.1, not 1.0

Jones's product rule targets unity system gamma — the mathematically correct target for *faithful* (colorimetrically exact) reproduction, and what real labs' own internegative engineering was built around. But unity gamma is only the right target when the print is viewed under the same conditions as the original scene. It isn't: a scene is viewed in full, bright, wide-field adaptation; a print or a screen is viewed dimmer, smaller, without the eye locally re-adapting the way it did across the real scene. C. J. Bartleson and E. J. Breneman's landmark study, *"Brightness perception in complex fields"* (*J. Opt. Soc. Am.* 57, pp.953-957, 1967 — full text not accessible during this research, JOSA paywalled; cited here via two real secondary sources that are saved locally and do carry the exact citation and mechanism: `papers/masking_research/choi_bartleson_breneman_brightness_stevens_power_law.pdf`, a 1994 IS&T paper by a Kodak Eastman scientist working through the derivation, and `papers/masking_research/roufs_global_brightness_contrast_perceptual_image_quality.pdf`, an independent Eindhoven University study that reproduces the same finding experimentally) established that the reproduction gamma humans actually prefer is greater than 1 for every viewing condition tested, and depends on how dark the surround is relative to the display: a darker surround than the original scene needs a *steeper* reproduction gamma to match perceived contrast. Reflection prints (Radiance III, Ilfochrome) and ordinary screen viewing are the *light*-surround case — the smallest correction of the three regimes Bartleson & Breneman describe (light/dim/dark surround), commonly summarized as ≈1.1, versus ≈1.5-1.6 for dark-surround transparency/projection viewing. Roufs et al.'s own independent measurement, under a moderately dark-surround slide-viewing setup, found preferred gamma around 1.2-1.4, trending back toward 1.0 as they engineered the dark-surround effect out of their apparatus — consistent with, not contradicting, the light-surround figure being lower still.

`GAMMA_CORRECT_TARGET = 1.1` is this second, independent, cited real constraint layered on top of Jones — not an arbitrary tweak. It does not, by itself, fully resolve the shadow-crush problem described next: pushing a *uniform* correction's target well past 1.1 recovers less than a stop of shadow depth before it starts recompressing the highlights the whole fix exists to preserve, which is what motivated scoping the correction the way it's scoped below rather than simply raising the target further.

### Why the correction fits a real model instead of rescaling or discarding the curve's own shape

Two further mechanisms were tried after the target was fixed at 1.1, and both were rejected — the full history, with measured numbers for each, is in `generate_film_looks.py`'s own `GAMMA_CORRECT_TARGET` comment block (referred to there as v1-v4; this section covers v3 and v4).

**v3 — a single straight line.** Jones's product rule is explicit about its own scope: *"for the straight line portions where gradient is constant and replaceable by gamma"* (p.64) — he never claims it governs the toe or shoulder. An earlier version applied one scalar to the *entire* digitized curve including the toe/shoulder, which are already lower-gamma than the straight line by definition, so scaling them down *again* by the same factor flattened them far more than the theory justifies and measurably starved the print of shadow density reach. A window-scoped version (rescale only inside the curve's own straight-line region, defined by a slope threshold, carry the toe/shoulder forward unmodified outside it) did better but left an arbitrary, physically-meaningless threshold governing where the correction stopped, and local gamma right at grey still ran 20-40% hotter than the target — the window-*average* gamma matched 1.1, but gamma at any specific point inside the window did not. Replacing all of that with a single straight line through the pivot, extended only as far as the film's own real measured Dmin/Dmax required, fixed the shortfall almost completely (Kodachrome 64 × Radiance III: print's shadow density reached 2.517 against the paper's real digitized Dmax of 2.521) — but it discarded the film's own toe/shoulder curvature entirely. That curvature is real, measured, material-specific data — how gradually a given film's response saturates near black and white is part of what makes it that film — and replacing it with a straight line for mathematical convenience was rejected on exactly those grounds.

**v4 (current) — fit a real model instead.** The physical origin of the H&D curve's toe/straight-line/shoulder shape is well established in sensitometry: an emulsion is a population of individual silver-halide grains, each becoming developable once its own quantum catch crosses its own threshold, and that population has a real, measured spread of individual grain sensitivities. J.H. Webb, *"Graphical Analysis of Photographic Exposure and a New Theoretical Formulation of the H and D Curve,"* *J. Opt. Soc. Am.* 29, 314-326 (1939), derives the H&D curve from exactly this picture — primary source paywalled and not accessible during this research (see `papers/masking_research/README.md` for the honest citation trail on this one), but the finding that Webb's own equation "cannot be integrated mathematically" is itself consistent with a cumulative-Gaussian origin, whose integral has no elementary closed form either. The curve's value at any exposure is therefore a *cumulative distribution* of how many grains have crossed threshold by that exposure — the standard idealization of a threshold-crossing process over a log-normally-distributed population is a cumulative Gaussian (normal) distribution against log exposure.

`tools/gamma_correction_fit/` (a separate `uv`-managed tool using scipy/numpy — kept out of the dependency-free main generator, the same pattern `film_paper_filter_data/tools/curve_digitizer/` already uses) fits an *asymmetric* cumulative-Gaussian ("split-normal": independently-fit widths `sigma_lo`/`sigma_hi` either side of the inflection point) to each reversal film's and each direct-print paper's own real digitized curve, via least-squares regression against the real data — asymmetric because the toe and shoulder are physically different mechanisms (grain-threshold statistics near Dmin; dye/silver exhaustion near Dmax) with no reason to share a width, and real emulsions are visibly not symmetric toe-to-shoulder. Fit quality is checked, not assumed: R² > 0.998 and max residual under 0.07 density units on every one of the 21 real curves fit (12 film layers, 9 paper layers). The fitted parameters (`*_SPLITGAUSS_FIT` in `generate_film_looks.py`) are transcribed as data, exactly like every other derived constant in this file.

`gamma_correct_curve()` then rescales the fitted model's *exposure axis only*, around the pivot — every fitted density value is kept exactly as the model computes it (so the model's own real fitted Dmin/Dmax are reached, not truncated), just relabeled to a new exposure position stretched by whatever factor makes the model's own *exact* analytic local gamma at the pivot (the derivative of a normal CDF is a normal PDF — computed directly, no window-average or finite-difference approximation) times the paper's own fitted local gamma at its real grey-reproduction point equal `GAMMA_CORRECT_TARGET`. A pure horizontal rescale preserves the fitted curve's shape exactly — toe:shoulder proportions unchanged — while spreading the same real density swing over more exposure, which is physically correct: lower gamma means exactly that, the same density change now needs more exposure, not a smaller density change. `generate_film_looks.py` itself stays scipy-free: `_norm_cdf()`/`_norm_pdf()` reimplement the standard normal CDF/PDF with only `math.erf` (stdlib), verified to match `scipy.stats.norm` to float precision.

**The result, measured the same way.** Kodachrome 64 × Radiance III: the print's shadow density now reaches 2.519 against the fitted model's own real Dmax of 2.561 — 0.04 short, comparable to v3's 0.004 shortfall, but with the film's real toe/shoulder curvature intact rather than replaced by a straight line. Checked across all 4 reversal films × 3 direct-print papers × 3 layers (36 combinations): shortfall against each paper's own fitted real Dmax is under 0.06 density units (a small fraction of a stop) in every case, and local gamma near grey now sits consistently close to `GAMMA_CORRECT_TARGET` itself, tapering smoothly into the toe/shoulder with no window-boundary kink — grey at -2 EV to +1 EV runs local gamma ≈0.8-1.1, easing off gradually beyond that rather than cutting off abruptly.

| Film | RadianceIII span | IlfochromeM span | IlfochromeP span |
|---|---|---|---|
| Velvia 50 | 0.744 | 0.745 | 0.701 |
| Kodachrome 64 | 0.773 | 0.752 | 0.708 |
| Fuji Provia 100F | 0.785 | 0.758 | 0.721 |
| Kodak Ektachrome 100D | 0.754 | 0.737 | 0.698 |

(Span = encoded white-corner minus black-corner output, same metric and methodology as "Choosing a print paper"'s table above.) These spans read *higher* than the earlier window-scoped version's 0.66-0.75 — that's not a regression, it's the fix reaching closer to the real material's own extremes at *both* corners at once (white corner brighter, black corner darker), which is exactly what closing the Dmax shortfall does to this particular metric; the number to trust for "is this still gradual, not crushed" is the local-gamma profile above, not span alone. Ilfochrome Micrographic M needs the largest correction of the three (its own measured gamma, ~1.9-2.1, is the highest of any paper in this file) and was the specific case CLAUDE.md already records as rejected once for compounding too hard *uncorrected* — it is not re-rejected here; correcting it is the more direct test of whether this fix actually works, and it renders comparably to the other two once corrected.

### Negative films needed the same correction too

The reasoning above talked about reversal films specifically, on the assumption that a camera negative's own low native gamma would keep it from overshooting Jones's target the way a reversal original does. That assumption turned out to be wrong in practice, caught by real-world use after the direct-print route above shipped: negative-film LUTs were rendering visibly *punchier* than the freshly-corrected reversal films — backwards from the real photographic hierarchy, where reversal stock is the punchier material.

Measured directly: negative films' own native gamma *is* correctly low (0.47–0.68 per layer via `_measured_gamma()` — exactly the low-native-gamma design every color negative stock uses, so it prints at roughly unity contrast on a normally-graded paper). The problem is on the paper side. `PAPER_LADDER`'s own real measured gammas are steep — 2.5–4.3 across all 5 papers, including "ExtraSoft" — and had never actually been checked against Jones's rule; the ladder's ordering was derived from measuring rendered *span* (see "Choosing a print paper" above), which is a different question from "does this pairing land near the faithful-reproduction target." Negative film × `PAPER_LADDER` was landing at local gamma ≈1.4–1.7 near grey, measured the same way as everywhere else in this section, versus the reversal direct-print route's ≈1.0–1.1.

The fix is the identical v4 mechanism, applied to a different pairing: `tools/gamma_correction_fit/` fits the same split-normal-CDF model to all 6 negative films' and all 5 `PAPER_LADDER` papers' real digitized curves (R² > 0.995 on every layer), and `_negative_gammacorrect_stage_fn()` (replacing the former, uncorrected `_negative_stage_fn()`) applies the same horizontal-rescale-to-target-1.1 correction, using each specific paper's own fitted local gamma at its real grey-reproduction point as the downstream factor — the same per-layer, per-paper precision the reversal route already has. Verified: Portra 400 × Normal now runs local gamma ≈1.0–1.25 near grey, matching the reversal route's target instead of running 30-50% hotter.

**What this still doesn't touch.** The internegative route (`COLOR_FILMS`/`_reversal_stage_fn()`) is left exactly as it was — it has the identical underlying gamma-product problem, just via a different, currently-uncorrected pairing (measured separately: local gamma swings from ~0.2 to ~3.6 across just a few stops, the original crush problem this whole investigation started from), and is a separate piece of work.

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

**Every color-film look ladder is now real material data, not a synthetic contrast curve** — Velvia's grades used to be a parametric power-curve adjustment (no real multi-grade print data existed), and the one real-paper Velvia look that did exist (direct printing onto Kodak Ektachrome Radiance III, *uncorrected*) was structurally very contrasty, because printing a reversal film directly onto *any* reversal print paper compounds two already-high-contrast stages (confirmed against real Cibachrome/Ilfochrome and R-3 process accounts, not just this dataset). The fix at the time was architectural, not a better parameter: real darkroom labs mostly didn't print slides directly either, for the same reason — they duplicated the slide onto an internegative first, which is a genuinely low-contrast material (measured γ≈0.527, digitized from EASTMAN Color Internegative II Film 5272/7272's real datasheet — see "Choosing a print paper"), then printed *that* like an ordinary negative. Ilfochrome Micrographic M/P was tried alongside Radiance III for that old direct-print approach and rejected too, for the identical uncorrected-compounding reason. Both are back now, alongside Radiance III, as the direct-print route described in "Why a reversal print crushes without correction" above — the difference this time is a real-physics gamma correction applied first, not a rejection reversed on a whim. Kodak Dye Transfer was also considered at the time and stays excluded regardless: flagged by its own source library as "very experimental and unreliable," and its "for Slides" variant turned out to be a renamed copy of the unfinished Kodachrome curve, not independent data.

**Negative films are a shorter cascade than the reversal films, by design, not an oversight**: Portra 400 / Ektar 100 / Gold 200 / Ultramax 400 / Superia Reala / Superia X-tra 400 print straight onto the same real RA-4 paper the reversal films use, with no internegative stage — the same 2-stage shape `build_trix_cascade()` already uses for Tri-X, generalized in `NEGATIVE_FILMS`/`_negative_gammacorrect_stage_fn()` (gamma-corrected against `PAPER_LADDER`, see "Why a reversal print crushes without correction" → "Negative films needed the same correction too"). An earlier version of this project briefly added three of these same films folded into the reversal-film lineup and removed them because they didn't exercise the internegative pipeline that lineup exists to demonstrate; they're back now as their own separate lineup instead, which is the correct fix, not a reversal of that decision.

**Kodak Portra 400 / Ektar 100 / Gold 200's own H&D and spectral-sensitivity curves were independently re-digitized from the real Kodak Alaris publication PDFs** (`E-4050`, `E-4046`, `E-7022` — see "Data provenance") as a cross-check against the community-sourced `spectral_film_lut` transcription already shipped, rather than trusting a single source uncritically. Per-layer gamma (contrast) matched within roughly 2-6% across all 9 (3 films × 3 layers) comparisons, and spectral peak wavelengths matched within about 5-20nm — good agreement for independent graph digitization, and specifically confirms that Portra 400, Ektar 100, and Gold 200 really do have quite similar per-layer gamma and spectral response to each other in real life (not a transcription artifact), which is why their rendered LUTs look closer to each other than to, say, Superia Reala's.

**Fuji Superia X-tra 400's green-sensitive layer had one bad source sample dropped**: the raw `spectral_film_lut`-derived JSON had a single point at 565.28nm reading 1.0051 log-sensitivity, a steep dive-and-recovery between two otherwise-smooth neighbors — confirmed as a digitization error (not a real spectral feature) before excluding it; see the comment above `SUPERIA_XTRA400_SENS` in `generate_film_looks.py`.

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

**Kodak Portra 400, Kodak Ektar 100, Kodak Gold 200, Kodak Ultramax 400, Fuji Superia Reala, Fuji Superia X-tra 400**: spectral sensitivity (3 dye layers) and characteristic curves (3 layers, negative) from `film_paper_filter_data/films/color/negative/*.json`, pooled from the same `spectral_film_lut` source as the reversal films above. Portra 400, Ektar 100, and Gold 200's curves were additionally cross-checked against the real Kodak Alaris publication PDFs — `E-4050` (Portra 400), `E-4046` (Ektar 100), `E-7022` (Gold 200), downloaded from Kodak Alaris's own site and kept in `papers/` — by independently re-digitizing the characteristic-curve and spectral-sensitivity charts straight from each PDF's vector drawing commands (the same technique `film_paper_filter_data/tools/curve_digitizer/` uses, extended to separate same-color, uncolored curve traces by position instead of by fill color, since these particular Kodak Alaris consumer/pro datasheets draw all three dye-layer curves in plain black rather than color-coding them). Per-layer gamma matched the shipped data within ~2-6%, spectral peaks within ~5-20nm — see "Honest limitations" for what that confirmed.

**Polymax Fine-Art**: characteristic curves at contrast grades 0 through 5 from the published Kodak datasheet.

**EASTMAN Color Internegative II Film 5272/7272**: spectral sensitivity and characteristic curve (3 layers), digitized directly from the real Kodak/Eastman datasheet TI1301 (`papers/kodak_internegative_ii_5272_TI1301.pdf`) via `film_paper_filter_data/tools/curve_digitizer/` — a purpose-built tool that reads the PDF's own vector drawing commands for each curve rather than tracing a rendered image, so extraction precision is limited only by the source document's own geometry, not by any rasterization DPI. See that tool's README for the extraction method (axis calibration from tick-label text positions, monotonicity enforcement via isotonic regression for the real material curve, Ramer-Douglas-Peucker simplification to a shape-preserving sparse point set).

**Print papers (Kodak Endura Premier, Kodak Portra Endura, Kodak Supra Endura, Fuji Crystal Archive Super Type C / Pro PDII / DPII / Maxima)**: characteristic curves (3 layers each) from published manufacturer datasheets.

**Direct-print papers for reversal originals (Kodak Ektachrome Radiance III, Ilfochrome Micrographic M/P)**: characteristic curves (3 layers each) from `film_paper_filter_data/papers/color/for_reversal/*.json`, the same `spectral_film_lut`-derived pool as everything else in this section — see "Why a reversal print crushes without correction" for how these are used (gamma-corrected first) and why. The gamma-correction physics itself (`GAMMA_CORRECT_TARGET`, `gamma_correct_curve()`) is sourced from L.A. Jones's 1920 tone-reproduction paper and a set of secondary sources (a 1988 internegative-duplicator patent, duplicating-film datasheets, archival-industry and darkroom-technique references) rather than a single manufacturer datasheet — the full citation trail and every source PDF/HTML page is in `papers/` and `papers/masking_research/README.md`.

**Wratten filters**: spectral transmission data from Kodak Publication B-3, "Handbook of Kodak Photographic Filters" (1990, ISBN 0-87985-658-0), transcribed by Paul Repacholi (1992), hosted at the University of Coimbra (mat.uc.pt). Cross-validated against the UEA Colour Group's wratten-db.

Film and paper curves and spectral sensitivities not otherwise noted above were digitized by the open-source project [spectral_film_lut](https://github.com/JanLohse/spectral_film_lut) (MIT license), pooled for reference in `film_paper_filter_data/`. CIE 1931 colour matching functions and the D65 illuminant are international standards.

## Generating

```
python generate_film_looks.py                                # 65^3, all 196 LUTs, Adobe RGB
python generate_film_looks.py --size 33                       # faster, smaller files
python generate_film_looks.py --only trix                      # Tri-X only (72 LUTs)
python generate_film_looks.py --only velvia kodachrome64        # just these two (32 LUTs)
python generate_film_looks.py --only negative-portra-400 negative-ektar-100  # just these two (20 LUTs)
python generate_film_looks.py --colorspace pq2020                # Rec.2020 + PQ instead of Adobe RGB
```

`--only` accepts any subset of `trix velvia kodachrome64 provia100f ektachrome100d negative-portra-400 negative-ektar-100 negative-gold-200 negative-ultramax-400 negative-superia-reala negative-superia-xtra-400`. Omit it for everything.

`--colorspace` accepts `adobergb` (default) or `pq2020` — see "Colour space options" below. It changes what the LUT expects as input/output, so match it to whatever you set as the lut3d module's application color space.

No dependencies beyond Python 3 standard library.

## License

The generator script and resulting LUT files are provided as-is. Film data is from published manufacturer datasheets, digitized under MIT license. CIE and D65 data are international standards. Wratten data is published reference material.
