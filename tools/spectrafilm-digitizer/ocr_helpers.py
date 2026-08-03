"""
OCR-based fallbacks for datasheets where real embedded text is missing --
either because a chart's axis ticks/curve labels are vector-drawn shapes
with no font-encoded text (confirmed on 9 Fuji sheets + Ilford Multigrade),
or because a file's font has a broken/private ToUnicode map (confirmed on
several Fuji B&W sheets: NeopanAcros100.pdf, Neopan400.pdf, Neopan1600.pdf,
NPZ.pdf). See BLOCKED.md for the full list and how each was diagnosed.

Two distinct problems, two distinct functions here:
1. Axis ticks are upright text -- `ocr_words_in_region()` renders a region
   at high DPI and returns a list of (x0, y0, x1, y1, text) tuples in PAGE
   coordinates, in the exact shape `page.get_text("words")` returns, so it
   drops straight into the EXISTING `fit_axis()`/`find_label_position()`
   machinery with no changes to either -- no rotation needed, confirmed
   ticks OCR cleanly upright.
2. Curve-identifying labels (Fuji's "Red"/"Green"/"Blue") are ROTATED to
   follow the local curve slope, which plain OCR reads poorly or not at
   all. `ocr_confirm_label()` handles this differently: it does NOT try to
   find a label's position (the caller already knows roughly where one is,
   the same way every other file's char_box/label position was worked out
   by eye) -- it only CONFIRMS which of a small known vocabulary
   (["Red","Green","Blue"] or similar) a given small region says, by
   trying a range of rotation angles and taking a majority vote after
   fuzzy substring matching. Confirmed empirically (2026-07-05, Pro 400H)
   that literal OCR of a rotated label is rarely pixel-perfect (systematically
   drops the leading capital: "Blue"->"lue", "Green"->"reen") but the
   surviving substring is unambiguous against a 3-word vocabulary, so exact
   text recovery isn't necessary, just enough signal to disambiguate.
"""

import io
import re

import fitz
import pytesseract
from PIL import Image

_TICK_ANGLES = range(-55, -9, 2)  # degrees; empirically covers Fuji's label slopes
_PSM_MODES = (7, 8, 11, 13)


def ocr_words_in_region(page, bbox, zoom=8.0, whitelist=None):
    """Renders `bbox` (page-space (x0,y0,x1,y1)) at `zoom`x, OCRs it, and
    returns [(x0, y0, x1, y1, text), ...] in PAGE coordinates -- a drop-in
    substitute for the relevant slice of `page.get_text("words")`, usable
    directly by `fit_axis()`/`find_label_position()`. `whitelist`: optional
    tesseract `tessedit_char_whitelist` string (e.g. "0123456789.-" for pure
    numeric tick rows) -- tightening this measurably reduces misreads on
    the axis-tick case, where the vocabulary really is that constrained."""
    rect = fitz.Rect(bbox)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    config = "--psm 11"
    if whitelist:
        config += f" -c tessedit_char_whitelist={whitelist}"
    data = pytesseract.image_to_data(img, config=config, output_type=pytesseract.Output.DICT)
    words = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text:
            continue
        px0, py0 = data["left"][i], data["top"][i]
        pw, ph = data["width"][i], data["height"][i]
        # pixel (in the zoomed render) -> page coordinates
        x0 = rect.x0 + px0 / zoom
        y0 = rect.y0 + py0 / zoom
        x1 = rect.x0 + (px0 + pw) / zoom
        y1 = rect.y0 + (py0 + ph) / zoom
        words.append((x0, y0, x1, y1, text))
    return words


def ocr_confirm_label(page, bbox, candidates, zoom=16.0, angle_range=_TICK_ANGLES):
    """Confirms which of `candidates` (e.g. ["Red","Green","Blue"]) the
    rotated text in `bbox` (page-space) says. Tries every angle in
    `angle_range` at several tesseract page-segmentation modes, keeps only
    alphabetic output, and returns the candidate with the most fuzzy-match
    votes (a vote counts if the OCR text is a substring of the candidate,
    or vice versa, case-insensitive -- handles the systematic
    leading-capital-drop seen in practice without needing exact matches).
    Returns None if no candidate gets any votes."""
    rect = fitz.Rect(bbox)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    votes = {c: 0 for c in candidates}
    for angle in angle_range:
        rotated = img.rotate(angle, expand=True, fillcolor="white", resample=Image.BICUBIC)
        for psm in _PSM_MODES:
            text = pytesseract.image_to_string(rotated, config=f"--psm {psm}").strip()
            text = "".join(c for c in text if c.isalpha())
            if not text:
                continue
            text_l = text.lower()
            for c in candidates:
                cl = c.lower()
                if text_l == cl or text_l in cl or cl in text_l:
                    votes[c] += 1
    best = max(votes, key=votes.get)
    return best if votes[best] > 0 else None


def _merge_adjacent_fragments(words):
    """Confirmed (2026-07-05, Superia X-tra 800) that tesseract sometimes
    splits one visual tick into two word fragments at the decimal point --
    "-2.0" comes back as separate "-2" and "0" tokens with the "." dropped
    entirely, which `ocr_axis_calib`'s regex then can't recognize as a
    single number at all (not a wrong-value problem, a missing-candidate
    problem). Merges any two words on the same row/column (near-identical
    center on the OTHER axis) whose gap is small relative to their own
    height/width into one combined token (with a "." inserted between if
    neither half already has one), before the caller's regex filtering."""
    if len(words) < 2:
        return words
    merged = []
    used = [False] * len(words)
    for i in range(len(words)):
        if used[i]:
            continue
        x0, y0, x1, y1, text = words[i]
        cy = (y0 + y1) / 2
        h = y1 - y0
        best_j, best_gap = None, None
        for j in range(i + 1, len(words)):
            if used[j]:
                continue
            jx0, jy0, jx1, jy1, jtext = words[j]
            jcy = (jy0 + jy1) / 2
            if abs(jcy - cy) > h * 0.6:
                continue
            gap = jx0 - x1
            if 0 <= gap < h * 0.9 and (best_gap is None or gap < best_gap):
                best_j, best_gap = j, gap
        if best_j is not None:
            jx0, jy0, jx1, jy1, jtext = words[best_j]
            combined_text = text if ("." in text or "." in jtext) else text + "." + jtext
            merged.append((min(x0, jx0), min(y0, jy0), max(x1, jx1), max(y1, jy1), combined_text))
            used[i] = used[best_j] = True
        else:
            merged.append(words[i])
            used[i] = True
    return merged


def ocr_axis_calib(page, bbox, tick_regex=r"-?\d+\.\d+", axis="x", zoom=8.0, whitelist="0123456789.-"):
    """OCR equivalent of `fit_axis()` for a panel whose tick text isn't
    real (or isn't correctly encoded): OCRs `bbox`, filters to tokens
    matching `tick_regex` (after normalizing common OCR punctuation slips:
    stray trailing/leading junk chars, en-dash/minus variants), and
    least-squares fits (slope, intercept) mapping pixel -> value, same
    convention as `ChartSpec.x_axis_calib_override`/`y_axis_calib_override`.

    Confirmed (2026-07-05) that OCR reads the MINUS SIGN unreliably --
    sometimes one tick in a row loses it (Pro 400H: one of five), sometimes
    most of them do (Pro 800Z: three of five) -- while the DIGITS
    themselves (the magnitude) are always read correctly. A real tick row
    is an evenly-spaced arithmetic sequence, so this brute-forces every
    combination of sign for the candidates that read as non-negative
    (typically <=5 ticks per axis, so <=32 combinations -- cheap) and keeps
    whichever sign assignment gives the tightest least-squares fit. Far
    more robust than trying to special-case "drop the single worst
    outlier," which isn't enough when several signs are wrong at once.

    `whitelist` (new parameter, spectrafilm-digitizer fork only -- default
    unchanged from the original curve_digitizer version, so every existing
    caller there is unaffected): confirmed on Ilford HP5 Plus's spectral-
    sensitivity wavelength row (2026-08, 6 pure-digit ticks ~26pt apart at
    zoom 8-10) that the default digit-only whitelist makes tesseract's
    --psm 11 layout analysis merge the whole evenly-spaced row into ONE
    token ("400450500550600650") -- word-gap detection apparently keys off
    a character class this whitelist excludes. Passing `whitelist=None`
    (falls through to plain, unrestricted OCR) splits the same row into 6
    clean tokens instead; only worth using when a row is confirmed merging,
    since the default whitelist is otherwise the more constrained/reliable
    read for a pure numeric tick vocabulary."""
    import itertools
    import numpy as np

    words = ocr_words_in_region(page, bbox, zoom=zoom, whitelist=whitelist)
    words = _merge_adjacent_fragments(words)
    numeric_regex = tick_regex.replace(r"\d", "[0-9]")
    candidates = []  # (pixel, magnitude, had_minus)
    for x0, y0, x1, y1, text in words:
        cleaned = text.replace("–", "-").replace("−", "-")
        cleaned = re.sub(r"[^-0-9.]", "", cleaned)
        if not re.fullmatch(numeric_regex, cleaned.lstrip("-")):
            # Mirror-image of the fragment-split issue: tesseract sometimes
            # mangles a tick's decimal point instead of cleanly separating
            # on it (confirmed on Ilford Multigrade, 2026-07-05: "2.0" reads
            # as "20" at some zooms, "2-0" -- dash instead of dot -- at
            # others). Strip to bare digits and reconstruct a single "."
            # before the last digit; only applies to simple one-decimal
            # tick rows ("\d.\d"-shaped regexes), which is what every case
            # seen so far actually is.
            sign = "-" if cleaned.startswith("-") else ""
            digits_only = re.sub(r"[^0-9]", "", cleaned)
            repaired = sign + digits_only[:-1] + "." + digits_only[-1] if len(digits_only) >= 2 else None
            if repaired and re.fullmatch(numeric_regex, repaired.lstrip("-")):
                cleaned = repaired
            else:
                continue
        try:
            val = float(cleaned)
        except ValueError:
            continue
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        px = cx if axis == "x" else cy
        candidates.append((px, abs(val), cleaned.startswith("-")))
    if len(candidates) < 2:
        raise RuntimeError(f"OCR found only {len(candidates)} tick(s) matching {tick_regex!r} in {bbox}")

    allows_negative = tick_regex.startswith("-?")
    if not allows_negative:
        # A caller-supplied tick_regex with no "-?" is an explicit claim that
        # this axis never has negative values -- confirmed real failure mode
        # (Ilford Ortho Plus, 2026-07-07): the small perpendicular tick-mark
        # dash strokes sitting just outside the digit text get OCR'd (with
        # whitelist="0123456789.-") as a spurious leading "-" merged onto
        # the adjacent real digit, silently negating every tick and
        # flipping the whole axis's sign. Any detected minus is therefore
        # OCR noise here, not a real sign -- drop it rather than trust it.
        candidates = [(px, mag, False) for px, mag, _had_minus in candidates]

    pixels = [c[0] for c in candidates]
    mags = [c[1] for c in candidates]
    had_minus = [c[2] for c in candidates]
    ambiguous = [i for i in range(len(candidates)) if not had_minus[i] and mags[i] != 0 and allows_negative]

    best = None
    for flip_bits in itertools.product([1, -1], repeat=len(ambiguous)):
        signs = [-1 if had_minus[i] else 1 for i in range(len(candidates))]
        for idx, bit in zip(ambiguous, flip_bits):
            signs[idx] = bit
        values = [s * m for s, m in zip(signs, mags)]
        slope, intercept = np.polyfit(pixels, values, 1)
        resid = sum((v - (slope * p + intercept)) ** 2 for p, v in zip(pixels, values))
        if best is None or resid < best[0]:
            best = (resid, slope, intercept)
    return float(best[1]), float(best[2])


def ocr_overline_negative_calib(page, bbox, tick_regex=r"\d\.\d", axis="x"):
    """OCR equivalent of `kodak_common.overline_negative_calib` for a tick
    row that uses the vector-overline minus-sign convention (ticks read as
    bare unsigned magnitudes, e.g. "3.0 2.0 1.0 0.0 1.0") when there is no
    real text layer to search at all -- confirmed necessary (Konica
    centuria_pro_400/csuper400/professional_160, 2026-07-07), NOT just
    `ocr_axis_calib` with an unbounded `tick_regex="-?..."`: an evenly-
    spaced tick row with unknown signs is ambiguous between "all-but-the-
    rightmost negative" (the real convention here) and other sign
    assignments that fit an evenly-spaced line equally well (zero residual
    either way) -- confirmed the brute-force least-squares search in
    `ocr_axis_calib` picks whichever combination needs the FEWEST sign
    flips when several tie on residual, which is the OPPOSITE of what this
    convention needs (3 of 5 ticks negative, not 1). This function skips
    the brute force entirely and applies the known convention directly:
    negate every OCR'd tick except the rightmost (by pixel), matching
    `overline_negative_calib`'s own logic exactly, just fed OCR candidates
    instead of `page.get_text("words")`."""
    import numpy as np

    words = ocr_words_in_region(page, bbox, zoom=6.0, whitelist="0123456789.")
    words = _merge_adjacent_fragments(words)
    candidates = []
    for x0, y0, x1, y1, text in words:
        if not re.fullmatch(tick_regex, text):
            continue
        try:
            val = float(text)
        except ValueError:
            continue
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        px = cx if axis == "x" else cy
        candidates.append((px, val))
    if len(candidates) < 2:
        raise RuntimeError(f"OCR found only {len(candidates)} tick(s) matching {tick_regex!r} in {bbox}")
    candidates.sort(key=lambda c: c[0])
    corrected = [-v for _, v in candidates[:-1]] + [candidates[-1][1]]
    pixels = [p for p, _ in candidates]
    slope, intercept = np.polyfit(pixels, corrected, 1)
    return float(slope), float(intercept)
