## Unapologeticly AI slop readme. Might find the time to rewrite it to a version that doesn't give you cancer sometime

# Film Look LUTs — Kodak Tri-X 400 & Fuji Velvia 50

Physically grounded film emulation as .cube LUTs for darktable (or any software supporting 3D LUTs). These replace your tone mapper — they do the complete scene-to-display job that AgX, filmic, or sigmoid would otherwise handle.

**Tri-X 400** — black and white. 6 contrast levels × 6 Wratten glass filters = 36 LUTs per variant.
**Velvia 50** — color reversal (slide film). 6 contrast levels, no filters = 6 LUTs per variant.

Each film ships in two variants: **classic** (pure film physics, no perceptual corrections) and **modern** (adds Helmholtz-Kohlrausch perceptual brightness correction). Total: 84 LUTs.

## What these replicate

Each LUT encodes a complete photographic reproduction chain:

**Tri-X**: scene light → Kodak Wratten glass filter (spectral transmission × film sensitivity) → Tri-X 400 negative (H&D characteristic curve at 7 min development) → Kodak Polymax Fine-Art enlarging paper (at a specific contrast grade) → print reflectance → display. This is the full negative-to-print darkroom process.

**Velvia**: scene light → Fuji Velvia 50 reversal film (3 independent dye layers, each with its own spectral sensitivity and H&D curve) → slide transmittance → display. This is the projected-slide experience. Contrast grades are parametric (see "Honest limitations" below).

## Quick start — darktable setup

1. Turn AgX / filmic / sigmoid **OFF**.
2. Add a **LUT 3D** module instance. Set application color space to **Adobe RGB**.
3. Place it where the tone mapper would normally sit (end of the scene-referred section of the pipeline, after exposure, colour balance, etc).
4. Load one .cube file.
5. Use the **exposure** module to position middle grey. The LUT supplies the tonal *shape*; exposure decides where your scene sits on it. If the image looks too dark or too bright, that's an exposure placement issue — nudge it until a known mid-grey reads as mid-grey.

That's it. Output is neutral B&W for Tri-X, full colour for Velvia.

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

### Velvia

Files are named `Velvia50_<Look>.cube` and live in `velvia_classic/` or `velvia_modern/`.

No filters — Velvia is a colour film; glass filters would alter its colour rendering, which is the whole point of choosing it.

The same six look names (ExtraSoft through Hard) provide the contrast ladder. See "Honest limitations" for what drives them.

### Classic vs Modern

**Classic** uses the geometric mean (density-space mixing) for colour-to-exposure conversion and the real H&D characteristic curves. No perceptual corrections. This is as close to the physical film process as a 3D LUT allows.

**Modern** adds the Helmholtz-Kohlrausch correction on top. HK accounts for the fact that saturated colours appear brighter to the human eye than their measured luminance — vivid blue sky looks brighter than a grey of equal luminance. Without HK, the B&W conversion can render saturated colours too dark. With it, the tonal separation matches human perception better, at the cost of departing from what the physical film would have produced. For colour (Velvia), HK adjusts the overall brightness of saturated inputs, preserving chromaticity while making vivid colours render lighter.

Neither variant is "better" — they serve different goals. Classic is more faithful to the darkroom. Modern produces more satisfying tonal separation to a contemporary viewer.

## The colour science

### Density-space geometric mean (both stocks)

Colour-to-exposure uses `E = R^w_R × G^w_G × B^w_B` (geometric mean) instead of `E = w_R×R + w_G×G + w_B×B` (arithmetic mean). This is equivalent to a weighted average in log-density space, which models how film's logarithmic response to light actually works. The practical effect: deeper blacks on filter-blocked colours, more aggressive midtone separation, and physically correct zero-exposure when a filter completely blocks a channel.

This is only valid on scene-referred linear data — which is what these LUTs operate on (Adobe RGB decoded to linear before processing).

For Velvia, each dye layer computes its own exposure from the input RGB via an arithmetic weighted sum (not geometric), because each layer responds to a narrow spectral band where the geometric mean's cross-channel suppression doesn't apply physically.

### Helmholtz-Kohlrausch correction (modern variants only)

Based on Fairchild & Pirrotta 1991 (*Color Research and Application* 16(6)). The model operates in CIELCh space:

```
L** = L* + (2.5 − 0.025·L*) · (0.116·|sin((h−90°)/2)| + 0.085) · C*
```

The correction is strongest for blue (h ≈ 270°) and red (h ≈ 0°/360°), weakest for yellow-green. It's converted to a linear exposure multiplier via the L*→Y inverse, then applied to the film exposure.

### Perceptual effects not implemented (and why)

Five additional perceptual phenomena were evaluated for inclusion in the "modern" variants:

**Bezold-Brücke shift** (hue shifts with luminance): for B&W, the output is achromatic — no hue to shift. For Velvia, the effect magnitude at SDR display luminance is approximately 2-5nm of hue shift, which is below the threshold of practical relevance and would alter Velvia's authentic hue rendering.

**Purkinje effect** (scotopic sensitivity shift): only applies at scotopic (rod-mediated) light levels. Display viewing is photopic. Not applicable.

**Hunt effect** (colorfulness increases with luminance): partially captured by HK's lightness-dependent term. For Velvia, the film's own steep dye curves already produce a natural saturation boost in highlights. Explicit Hunt correction risks over-saturation on an already-punchy stock.

**Abney effect** (white-light-induced hue shift): too subtle at display luminance levels to produce a visible difference in the output.

**Chromatic adaptation**: handled by the white balance module upstream in the pipeline. Not the LUT's job.

## Honest limitations

**Highlight clipping**: Adobe RGB encoding clips input at approximately middle-grey + 2.5 stops. This is a fundamental limitation of the .cube LUT format — no wide-range perceptual encoding (PQ, log) is available in darktable's lut3d module. The print shoulder (Tri-X) and reversal shoulder (Velvia) already roll off highlights, so for most pictorial photography the loss is small.

**Velvia contrast grades are parametric**: the six Velvia looks use a power-curve contrast adjustment around middle grey rather than separate real paper/process data (no multi-grade reversal print data exists in digitized form). The spectral sensitivity and H&D characteristic curves are real; the contrast variation is synthetic. Tri-X contrast grades, by contrast, come from real Kodak Polymax paper grade data (grades 0–5).

**Grain and halation**: spatial effects that a per-pixel LUT cannot represent. Use darktable's grain module and/or the Diffuse or Sharpen module with red-channel blend mode for halation simulation.

**Chromatic aberration interaction**: strong contrast filters (Red25, Blue47) amplify edge colour artifacts from darktable's chromatic aberration correction module. This is because the filter maps near-invisible colour shifts at edges into large luminance differences. Disable automatic CA correction when using strong filters, or use it sparingly.

**Spectral-to-RGB approximation**: converting a film's spectral sensitivity curve into three RGB weights assumes Adobe RGB primary spectra. The weight magnitudes are approximate; the rendering character is robust and matches documented film behaviour.

**Two B&W stocks only**: Tri-X 400 and Double-X 5222 are the only B&W negatives with real digitized data available (from JanLohse/spectral_film_lut). The famous rest of the B&W roster — HP5, FP4, T-Max, Acros, Delta — is not included because the data does not exist in digitized form and we did not fabricate it.

## Why Adobe RGB

A .cube LUT needs gamma-encoded input so the grid distributes its sample points where shadows and midtones need precision. Among the encodings darktable's lut3d module offers, Adobe RGB has the widest colour gamut of the gamma options. This means saturated scene colours survive into the spectral weighting rather than being gamut-clipped before the film "sees" them. The gamma precision is equivalent to sRGB; the wider primaries are the deciding advantage.

## Data provenance

**Tri-X 400**: spectral sensitivity from the Tri-X Pan 5063 emulsion as published in Kodak datasheet F-4017. Characteristic curve at 7 minutes development.

**Velvia 50**: spectral sensitivity (3 dye layers) and characteristic curves (3 layers, reversal) from the published Fujifilm datasheet.

**Polymax Fine-Art**: characteristic curves at contrast grades 0 through 5 from the published Kodak datasheet.

**Wratten filters**: spectral transmission data from Kodak Publication B-3, "Handbook of Kodak Photographic Filters" (1990, ISBN 0-87985-658-0), transcribed by Paul Repacholi (1992), hosted at the University of Coimbra (mat.uc.pt). Cross-validated against the UEA Colour Group's wratten-db.

All film curves and spectral sensitivities were digitized by the open-source project [spectral_film_lut](https://github.com/JanLohse/spectral_film_lut) (MIT license). CIE 1931 colour matching functions and the D65 illuminant are international standards.

## Generating

```
python generate_film_looks.py                  # 65^3, all 84 LUTs
python generate_film_looks.py --size 33        # faster, smaller files
python generate_film_looks.py --only trix      # Tri-X only (72 LUTs)
python generate_film_looks.py --only velvia    # Velvia only (12 LUTs)
```

No dependencies beyond Python 3 standard library.

## License

The generator script and resulting LUT files are provided as-is. Film data is from published manufacturer datasheets, digitized under MIT license. CIE and D65 data are international standards. Wratten data is published reference material.
