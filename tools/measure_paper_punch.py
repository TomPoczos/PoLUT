#!/usr/bin/env python3
"""Measure each real candidate RA-4 paper's actual rendered contrast/headroom
through the real production cascade, for every color film in COLOR_FILMS.

Why this exists: PAPER_LADDER's look assignment (README "Choosing a print
paper") was picked using a proxy metric -- least-squares regression slope
over the middle 60% of each *material's own* exposure range, computed once
offline and never re-checked against what the real cascade (film -> real
internegative datum -> paper, `_find_anchor`-calibrated exactly like
production) actually produces over the working exposure range a LUT corner
can reach. That proxy doesn't see per-layer gamma divergence, or a paper's
own Dmax being reached before the internegative's own highlight exposure is,
so it can rank a paper as "harder" while it actually renders flatter and/or
clips highlights sooner once it's run through the real chain. Confirmed in
practice: ExtraSoft (Endura Premier) measuring punchier than Soft/Normal on
some films, Punchy vs ExtraPunchy nearly indistinguishable, Fuji papers
losing highlight headroom.

This script fixes the metric, not the paper choice: it runs *every* real,
same-medium RA-4 paper this project has already identified as eligible
(film_paper_filter_data/papers/color/for_negatives/ -- see README "Choosing
a print paper" point 1) through the actual build_print_cascade() machinery,
for every color film, and reports real measured numbers -- not a synthetic
contrast knob, no data invented. Read-only: doesn't touch generate_film_looks.py,
PAPER_LADDER, or any committed .cube file.

Usage: python3 tools/measure_paper_punch.py
"""
import sys, os, json, math

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
import generate_film_looks as gfl

_FOR_NEGATIVES = os.path.join(_ROOT, "film_paper_filter_data", "papers", "color", "for_negatives")


def _load_paper_json(fname):
    """Load a print-paper curve straight from the source pool JSON, in the
    same [red/cyan, green/magenta, blue/yellow]-layer, float-keyed dict
    format PAPER_LADDER's own entries use. Confirmed against a paper already
    digitized both ways (kodak_endura_premier.json vs ENDURA_PREMIER in
    generate_film_looks.py) that this pool's own list order already matches
    that convention directly -- no reordering needed here, unlike the
    internegative curve digitizer's blue/green/red output."""
    with open(os.path.join(_FOR_NEGATIVES, fname)) as f:
        d = json.load(f)
    return [{float(k): v for k, v in layer.items()} for layer in d["sensiometric_curve"]]


# The 7 real, same-medium RA-4 papers README "Choosing a print paper" point 1
# identifies as legitimate candidates (cinema release-print stocks and
# duratrans/backlit materials already excluded there as wrong medium). 5 are
# already digitized as constants in generate_film_looks.py; the other 2
# (Supra Endura, Pro PDII) were identified as real candidates in
# tasks/DONE-07 but never brought into the shipped ladder -- loaded here
# straight from the source JSON so every eligible paper actually gets
# measured, not just the 5 already picked.
ALL_PAPERS = dict(gfl.PAPER_LADDER)
ALL_PAPERS["Supra Endura"] = _load_paper_json("kodak_supra_endura.json")
ALL_PAPERS["Pro PDII"] = _load_paper_json("fuji_ca_pdII.json")

# name -> look currently assigned in the shipped PAPER_LADDER, for comparing
# measured order against what's actually shipping.
CURRENT_LOOK = {}
for _look, _curve in gfl.PAPER_LADDER.items():
    for _name, _c in ALL_PAPERS.items():
        if _c is _curve:
            CURRENT_LOOK[_name] = _look

# Scene-exposure stops around GREY to sample density/gamma bands at. Chosen
# to match the real working range: Adobe RGB clips scene input at roughly
# grey+2.5 stops (see README "Honest limitations"), and shadow behavior past
# -2 stops is where paper Dmin/toe noise lives.
STOPS = [-3, -2, -1, 0, 1, 2, 2.5]


def _density(reflectance):
    return -math.log10(max(reflectance, 1e-9))


def _measure_layer(xfer):
    """Sample one layer's real cascade transfer function across STOPS, plus
    the exact white/black LUT-corner exposures (E=1.0 / E=0.0 -- layer
    weights are normalized to sum to 1, so a full-white/full-black neutral
    pixel produces exactly that per-layer exposure, not an approximation)."""
    samples = {s: gfl.aenc(xfer(gfl.GREY * (2 ** s))) for s in STOPS}
    samples["white"] = gfl.aenc(xfer(1.0))
    samples["black"] = gfl.aenc(xfer(0.0))
    dens = {k: _density(gfl.adec(v)) for k, v in samples.items()}
    return samples, dens


def _gamma(dens, s_lo, s_hi):
    """Real sensitometric gamma (delta density / delta log10 exposure) over
    a specific stop band, measured on the actual cascade output -- not a
    regression slope over an arbitrary window of one material's own curve in
    isolation."""
    return (dens[s_lo] - dens[s_hi]) / ((s_hi - s_lo) * math.log10(2))


def measure(film_key, paper_name):
    """Returns per-layer + averaged metrics for one (film, paper) pair, or
    None with an error string if the real cascade isn't calibratable for
    this pairing (e.g. a monotonicity violation _find_anchor refuses to scan
    past) -- reported, not hidden, since an eligible-looking paper that
    can't actually calibrate against a given film is itself a finding."""
    film = next(f for f in gfl.COLOR_FILMS if f[0] == film_key)
    _, _, _, sens, stage_fn = film
    paper = ALL_PAPERS[paper_name]
    try:
        xfers = [gfl.build_print_cascade(stage_fn(li, paper)) for li in range(3)]
    except ValueError as e:
        return None, str(e)

    per_layer = [_measure_layer(x) for x in xfers]
    white = [s["white"] for s, _ in per_layer]
    black = [s["black"] for s, _ in per_layer]
    mid_g = [_gamma(d, -1, 1) for _, d in per_layer]
    shadow_g = [_gamma(d, -2, 0) for _, d in per_layer]
    hi_g = [_gamma(d, 0, 2) for _, d in per_layer]

    def avg(xs):
        return sum(xs) / len(xs)

    return {
        "white_avg": avg(white), "white_spread": max(white) - min(white),
        "black_avg": avg(black), "black_spread": max(black) - min(black),
        "span": avg(white) - avg(black),
        "mid_gamma": avg(mid_g), "shadow_gamma": avg(shadow_g), "hi_gamma": avg(hi_g),
        "per_layer_white": white, "per_layer_black": black,
    }, None


def main():
    print(__doc__.split("\n\n")[0])
    print(f"\nCandidate papers ({len(ALL_PAPERS)}): " + ", ".join(sorted(ALL_PAPERS)))

    for film_key, _, dispname, _, _ in gfl.COLOR_FILMS:
        print(f"\n{'=' * 100}\n{dispname}\n{'=' * 100}")
        rows = []
        for name in ALL_PAPERS:
            m, err = measure(film_key, name)
            rows.append((name, m, err))

        rows.sort(key=lambda r: (r[1] is None, -(r[1]["span"] if r[1] else 0)))

        hdr = f"{'paper':<16} {'look (current)':<15} {'shadow_γ':>9} {'mid_γ':>7} {'hi_γ':>7} {'white':>7} {'black':>7} {'span':>7} {'ch.spread':>9}"
        print(hdr)
        print("-" * len(hdr))
        for name, m, err in rows:
            look = CURRENT_LOOK.get(name, "-")
            if m is None:
                print(f"{name:<16} {look:<15} FAILED: {err}")
                continue
            print(f"{name:<16} {look:<15} {m['shadow_gamma']:>9.2f} {m['mid_gamma']:>7.2f} "
                  f"{m['hi_gamma']:>7.2f} {m['white_avg']:>7.3f} {m['black_avg']:>7.3f} "
                  f"{m['span']:>7.3f} {m['white_spread']:>9.3f}")

    print(f"""
{'=' * 100}
Columns:
  shadow_γ / mid_γ / hi_γ  real sensitometric gamma (Δdensity / Δlog10 exposure) of the
                           FULL cascade (film -> internegative -> paper), averaged across
                           the 3 layers, over -2..0 / -1..+1 / 0..+2 stops around grey.
                           Not a single curve-fit number over one material's own range --
                           three bands, so a paper that's flat in the highlights but steep
                           in the midtones (or vice versa) shows up as a real split instead
                           of averaging away.
  white / black            average encoded (gamma-applied) output at the real LUT corners
                           (full-white / full-black neutral input), across the 3 layers.
                           This is where headroom loss actually shows: a paper can have a
                           respectable mid_γ and still leave "white" well under 1.0 because
                           its own Dmax is reached before the internegative's highlight
                           exposure is -- exactly the "half a stop left on the table" effect.
  span                     white - black. The real full-range contrast+headroom number --
                           closest single proxy for "how punchy does this actually render."
  ch.spread                max-min of the 3 layers' own white-corner values -- a large
                           spread means the paper doesn't just get punchier/flatter, it
                           shifts color balance at the highlight end.
""")


if __name__ == "__main__":
    main()
