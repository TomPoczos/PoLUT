"""
Re-checks every already-produced consolidated-data/ JSON's axis calibration
for internal consistency (evenly-spaced tick_matches), independent of
whatever `fit_axis` fix level was in effect when it was generated.

Why this exists: the QA overlay PNG cannot detect a wrong-but-internally-
consistent axis calibration (it round-trips through the same slope/
intercept that produced the data), so calibration bugs can hide behind a
visually "correct-looking" overlay indefinitely. Run this after any change
to fit_axis/locate_panel_bboxes, and periodically as a general regression
check across all produced output -- not just when adding new products.

Usage: uv run audit_calibration.py [consolidated-data root]
"""

import glob
import json
import sys

import numpy as np

DEFAULT_ROOT = "/home/tom/Pictures/LUTs/PoLUT/consolidated-data"


def check_ticks(label, ticks):
    if len(ticks) < 2:
        return True
    pixels = [t[0] for t in ticks]
    values = [t[1] for t in ticks]
    slope, intercept = np.polyfit(pixels, values, 1)
    resid = [abs((slope * p + intercept) - v) for p, v in zip(pixels, values)]
    maxval = max((abs(v) for v in values if v != 0), default=1)
    if max(resid) > 0.4 * maxval:
        print(f"  BAD {label}: resid={[round(r, 2) for r in resid]} "
              f"ticks={list(zip([round(p, 1) for p in pixels], values))}")
        return False
    return True


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROOT
    files = sorted(glob.glob(f"{root}/**/*.json", recursive=True))
    n_bad = 0
    for f in files:
        d = json.load(open(f))
        charts = d.get("charts", {})
        for chart_id, chart in charts.items():
            xt = chart.get("x_axis_calibration", {}).get("tick_matches", [])
            yt = chart.get("y_axis_calibration", {}).get("tick_matches", [])
            label = f"{f.split('/')[-1]}::{chart_id}"
            if not check_ticks(label + " x", xt):
                n_bad += 1
            if not check_ticks(label + " y", yt):
                n_bad += 1
    print(f"\n{len(files)} files checked, {n_bad} bad axis calibrations found.")


if __name__ == "__main__":
    main()
