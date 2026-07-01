# Film, Paper & Filter Data — Pooled Reference Collection

Every piece of digitized photographic material data discovered across this project, pooled into one structured folder. This is raw reference data, not processed LUTs — spectral sensitivities, characteristic (H&D) curves, and filter transmission spectra, exactly as published by the manufacturers and digitized by open-source projects.

## Folder structure

```
films/
  bw/                      B&W negative films (Tri-X, Double-X + development-time variants)
  color/
    negative/              Color negative films (Portra, Ektar, Gold, cine stocks, etc.)
    reversal/              Color reversal/slide films (Velvia, Provia, Kodachrome, Ektachrome, etc.)
papers/
  bw/                      B&W enlarging papers (Polymax Fine-Art + grades, Kodak 2302 + process times)
  color/
    for_negatives/         Papers/print films for printing from color negatives (Endura, Fujiflex, etc.)
    for_reversal/          Papers/print materials for printing from slides (Ilfochrome, Ektachrome Radiance, Dye Transfer)
filters/
  wratten_b3_handbook/     58 Wratten filters, direct from the Kodak B-3 handbook (primary source)
  wratten_alt_digitization/  33 Wratten filters, independent alternate digitization (density format, finer sampling)
```

Each film/paper JSON contains the full record as published: `name`, `manufacturer`, `film_type` (negative/positive), `stage` (camera/print), `medium`, `year`, `iso`, `log_sensitivity` (one dict per spectral layer: wavelength → log sensitivity), and `sensiometric_curve` (one dict per layer: log exposure → density). Where a film has multiple development-time or process-time/grade variants, each variant is its own file.

## Sources

**Film and paper data** — extracted from [spectral_film_lut](https://github.com/JanLohse/spectral_film_lut) by JanLohse (MIT license), which digitized published manufacturer datasheets (Kodak, Fuji, Ilford, Technicolor). Extraction was done via real Python import of each module (not text parsing), so every value — including computed/derived fields like development-time variants that reference a shared base curve — is exactly what the library itself would produce.

**Wratten filter data (b3_handbook/)** — 58 filters spanning visible-light contrast filters, UV/IR filters, color conversion filters, and densitometry filters, digitized from **Kodak Publication B-3, "Handbook of Kodak Photographic Filters"** (1990, ISBN 0-87985-658-0). Originally transcribed by Paul Repacholi (1992) and hosted at the University of Coimbra (mat.uc.pt), later converted to MATLAB format by [mikeharris100/wratten-db](https://github.com/mikeharris100/wratten-db) — this is the source pulled here. Values are percent transmission and density at 10nm intervals, 400–700nm.

**Wratten filter data (alt_digitization/)** — 33 filters, an independent digitization bundled inside spectral_film_lut's own `wratten_filters.py`. Stored as density at finer, non-uniform wavelength sampling. Overlaps substantially with the B-3 handbook set but was digitized separately — useful for cross-checking, and covers slightly different wavelength resolution in places. Does not include the full B-3 handbook range (missing several filters the primary source has, e.g. #11, #23A, #33, #39, #47B, #74, #80-series, #81-series, #82-series).

## Honesty notes

**Aliased/derived records.** A few entries in the film/paper data are not independent measurements — they reuse another material's curve data with only a name (or a small number of fields) changed:
- **Kodak Dye Transfer for Slides** reuses the exact curve data of **Kodak Dye Transfer for Kodachrome** — the source repository marks the "for slides" variant as unfinished (`# TODO: integrate`, describing a separation-negative process that hasn't been implemented). Treat "for Slides" as Kodachrome-calibrated data under a different name, not independent measurement.
- **Ilfochrome Micrographic P** is a derivative of **Ilfochrome Micrographic M** with its own `sensiometric_curve` override but shared base metadata — this one does have independently digitized curve data, just built on the same base record.

**Ilfochrome Micrographic vs. photographic Ilfochrome/Cibachrome.** The Ilfochrome data available is the "Micrographic" formulation — a duplicating/microfilm variant of Ilford's silver dye-bleach chemistry — not the classic "Ilfochrome Classic/Deluxe" pictorial paper used in fine-art darkrooms. Same process family (the one famous for punchy, saturated, archival prints from slides), but formulation tuning may differ from what a photographic print of the era would show. No photographic-grade Ilfochrome/Cibachrome curve set was found digitized anywhere online.

**Spectral sensitivity → RGB is lossy by nature.** Any use of `log_sensitivity` data to derive RGB channel weights (e.g. for building a LUT) requires assuming a set of display primaries and an illuminant. The raw data here is illuminant- and gamut-agnostic; that assumption gets made downstream, not in this data.

**B&W films with real data: only two.** Kodak Tri-X 400 and Kodak Double-X (5222) are the only B&W camera negatives with genuine digitized spectral sensitivity + H&D curves in this collection. Other famous B&W stocks (HP5, FP4, T-Max, Acros, Delta) are not included because no digitized data was found — nothing here was fabricated to fill the gap.

## Regenerating

The extraction was done with a small Python script that imports each film/paper module directly from the spectral_film_lut source tree (bypassing its GUI-dependent `__init__.py`) and serializes the resulting dataclass instances to JSON. The Wratten data was pulled from the `.mat` files in wratten-db via `scipy.io.loadmat`, and from the `WRATTEN` dict in spectral_film_lut's `wratten_filters.py` via direct import. No values were hand-transcribed or estimated for this dump — everything traces to one of the source repositories above.
