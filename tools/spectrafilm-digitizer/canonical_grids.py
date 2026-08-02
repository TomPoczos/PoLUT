"""
The two fixed grids every darktable spektrafilm profile's `data` arrays are
sampled on. Both are exactly reconstructible with numpy (confirmed bit-exact,
`np.array_equal`, against the wavelengths/log_exposure arrays shipped in
darktable's own `devconfig/spektrafilm/pack.json`) rather than pasted as
literals, so there's no transcription-error risk and no drift between this
file and the one place that actually defines the grid.

Both lengths are load-bearing: darktable's C reader (`spektra_sim.c`,
`json_read_darray`/`json_read_dmatrix`) requires an exact-length match
(SF_NWL=81, SF_NLE=256, see `spektra_sim.h`) or refuses to load the profile
at all -- there is no partial/resampled fallback on the native side.
"""

import numpy as np

# 380..780 nm in 5 nm steps -- spektrafilm's SPECTRAL_SHAPE / darktable's SF_NWL.
WAVELENGTHS_NM = np.arange(380.0, 780.0 + 1e-9, 5.0)

# -3..4 log10(exposure), 256 points -- spektrafilm's LOG_EXPOSURE / darktable's SF_NLE.
LOG_EXPOSURE = np.linspace(-3.0, 4.0, 256)

assert WAVELENGTHS_NM.shape == (81,)
assert LOG_EXPOSURE.shape == (256,)
