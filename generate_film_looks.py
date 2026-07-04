#!/usr/bin/env python3
"""
generate_film_looks.py — Tri-X 400, Velvia 50, Kodachrome 64, Fuji Provia
100F, Kodak Ektachrome 100D, Kodak Portra 400, Kodak Ektar 100, Kodak Gold
200, Kodak Ultramax 400, Fuji Superia Reala and Fuji Superia X-tra 400 film
emulation LUTs

Generates 12 folders of curated film-look LUTs that replace your tone mapper:

  trix_classic/               — 36 LUTs (6 looks x 6 filters), pure film physics
  trix_modern/                 — 36 LUTs, adds Helmholtz-Kohlrausch perceptual correction
  velvia/                      — 16 LUTs (5 real-paper + 3 direct-print looks x classic/modern)
  kodachrome64/                 — 16 LUTs, same structure
  provia100f/                   — 16 LUTs, same structure
  ektachrome100d/               — 16 LUTs, same structure
  negative-portra-400/          — 10 LUTs, same real-paper-cascade structure (no internegative)
  negative-ektar-100/           — 10 LUTs, same real-paper-cascade structure (no internegative)
  negative-gold-200/            — 10 LUTs, same real-paper-cascade structure (no internegative)
  negative-ultramax-400/        — 10 LUTs, same real-paper-cascade structure (no internegative)
  negative-superia-reala/       — 10 LUTs, same real-paper-cascade structure (no internegative)
  negative-superia-xtra-400/    — 10 LUTs, same real-paper-cascade structure (no internegative)

Total: 196 LUTs.

The first four color films are reversal (slide) stocks. Each gets two
independent print routes into its own folder: 5 looks (ExtraSoft/Soft/
Normal/Punchy/ExtraPunchy) printed through a real duplicating internegative
(EASTMAN Color Internegative II Film 5272/7272) and a real RA-4 print paper
-- the same cascade structure real darkroom labs used to get a printable
result from a slide -- via PAPER_LADDER, and 3 looks (RadianceIII/
IlfochromeM/IlfochromeP) printed straight onto a real direct-print paper
with no internegative stage, via DIRECT_PRINT_PAPERS, with a real-physics
gamma correction applied first (see GAMMA_CORRECT_TARGET). The last six are
camera color *negatives*, printed straight onto that same real RA-4 paper
with no internegative stage and no gamma correction (a camera negative's own
gamma is already low, unlike a reversal original's) -- see NEGATIVE_FILMS.
See README.md for the full process writeup, including "Why a reversal print
crushes without correction" for the gamma-correction physics.

Usage:
  python generate_film_looks.py                            # 65^3 default, everything
  python generate_film_looks.py --size 33                  # faster, smaller
  python generate_film_looks.py --only trix                 # just Tri-X
  python generate_film_looks.py --only velvia kodachrome64   # just these two
  python generate_film_looks.py --only negative-portra-400 negative-ektar-100  # just these two
  python generate_film_looks.py --colorspace pq2020          # Rec.2020 + PQ instead of Adobe RGB
  python generate_film_looks.py --help
"""

import argparse, math, os, time, json

# =========================================================================
# CIE 1931 2-deg observer + D65
# =========================================================================
CIE = {400:(0.01431,0.000396,0.06785),410:(0.04351,0.00121,0.2074),420:(0.13438,0.004,0.6456),430:(0.2839,0.0116,1.3856),440:(0.34828,0.023,1.74706),450:(0.3362,0.038,1.77211),460:(0.2908,0.06,1.6692),470:(0.19536,0.09098,1.28764),480:(0.09564,0.13902,0.81295),490:(0.03201,0.20802,0.46518),500:(0.0049,0.323,0.272),510:(0.0093,0.503,0.1582),520:(0.06327,0.71,0.07825),530:(0.1655,0.862,0.04216),540:(0.2904,0.954,0.0203),550:(0.43345,0.995,0.00875),560:(0.5945,0.995,0.0039),570:(0.7621,0.952,0.0021),580:(0.9163,0.87,0.00165),590:(1.0263,0.757,0.0011),600:(1.0622,0.631,0.0008),610:(1.0026,0.503,0.00034),620:(0.85445,0.381,0.00019),630:(0.6424,0.265,0.00005),640:(0.4479,0.175,0.00002),650:(0.2835,0.107,0),660:(0.1649,0.061,0),670:(0.0874,0.032,0),680:(0.04677,0.017,0),690:(0.0227,0.00821,0),700:(0.01135,0.004102,0)}
D65 = {400:82.75,410:91.49,420:93.43,430:86.68,440:104.86,450:117.01,460:117.81,470:114.86,480:115.09,490:108.81,500:109.35,510:107.8,520:104.79,530:107.69,540:104.41,550:104.05,560:100.0,570:96.33,580:95.79,590:88.69,600:90.01,610:89.6,620:87.7,630:83.29,640:83.7,650:80.03,660:80.21,670:82.28,680:78.28,690:69.72,700:71.61}

# =========================================================================
# Adobe RGB (1998)
# =========================================================================
_MA_ADOBE = [[2.04158790,-0.56500697,-0.34473135],[-0.96924364,1.87596750,0.04155506],[0.01344428,-0.11836239,1.01517499]]
_MA_INV_ADOBE = [[0.57667,0.18556,0.18823],[0.29734,0.62736,0.07529],[0.02703,0.07069,0.99134]]
_AG = 2.19921875
def adec(v): return max(0.0,v)**_AG
def aenc(c): return max(0.0,min(1.0,c))**(1.0/_AG)

# =========================================================================
# Rec.2020 (D65) + SMPTE ST 2084 (PQ) -- the other LUT-module application
# colour space this tool can target (see main()'s --colorspace). Rec.2020's
# primaries are wider than Adobe RGB's. PQ does NOT raise the highlight
# ceiling: both clip at linear pixel value 1.0 (~grey +2.5 stops at 0 EV),
# because encoded 1.0 means linear 1.0 for any [0,1]-domain TRC, gamma or PQ
# alike. All PQ changes is how the [0,1] code axis is distributed (most of it
# goes to shadow/mid detail). See the comment on pqenc/pqdec below for the
# full reasoning and -- crucially -- the one darktable setup requirement that
# makes or breaks it.
# =========================================================================
_MA_REC2020 = [[1.7166512,-0.3556708,-0.2533663],[-0.6666844,1.6164812,0.0157685],[0.0176399,-0.0427706,0.9421031]]
_MA_INV_REC2020 = [[0.6369580,0.1446169,0.1688810],[0.2627002,0.6779981,0.0593017],[0.0000000,0.0280727,1.0609851]]
# SMPTE ST 2084 (PQ) constants, applied completely unscaled -- deliberately.
# Several earlier versions of this comment (see git history) got this wrong
# in different directions, so the reasoning is spelled out in full.
#
# darktable's PQ Rec.2020 ICC profile is a standard, normalised matrix-
# shaper: D65 white, Rec.2020 primaries, TRC = `_PQ_fct` in
# src/common/colorspaces.c (confirmed by reading it, and by reading the fast
# matrix+TRC path in src/common/iop_profile.c that actually runs for lut3d).
# It applies this exact formula, with these exact constants, to the
# pipeline's scene-referred linear pixel value, with NO reference-white or
# reference-nits scaling anywhere -- the profile is normalised so linear 1.0
# is the connection-space white, the same role adec/aenc's 1.0 plays. So for
# a code position `v` to mean the same exposure here as to darktable, pqdec
# must be the *exact* inverse of what darktable computes: the same unscaled
# formula. Verified numerically -- pqenc() below matches darktable's inverse
# _PQ_fct to <1e-4 across the range (linear 0.18 -> code 0.816 in both).
#
# Do NOT rescale pqdec/pqenc. A previous committed version multiplied by a
# 203/10000-nit "reference white" factor; any factor K silently demands a
# matching exposure change before the LUT3D module, and without it the film
# math reads every image ~5.6 stops overexposed (grey lands on the paper's
# high-density shoulder) while darktable decodes the output at the wrong
# brightness -- exactly the everything-blown regression that produced.
#
# Staying unscaled means grey (0.18) lands at code ~0.816, not near the
# middle the way Adobe RGB's aenc(0.18)=0.459 does. That is correct and needs
# NO exposure compensation: the LUT is grey-anchored on *scene-linear* 0.18
# (see GREY), so at 0 EV scene 0.18 -> code 0.816 -> LUT -> code 0.816 ->
# 0.18 out. Grey renders as grey; the transfer is identical to the adobergb
# build in scene-linear terms, and 33^3 reproduces it to <0.02. (An earlier
# version of this comment claimed you must expose ~-5 EV to move grey off the
# "compressed" part of the code axis -- that is wrong and would drop grey ~5
# stops, rendering the image near-black. The LUT already compensates for
# where grey sits on the axis; grid precision there is fine.)
#
# THE ONE REAL FOOTGUN, and the likeliest cause if a pq2020 render looks
# broken: a PQ-baked .cube renders correctly ONLY if darktable's LUT 3D
# module has "application color space" = "PQ Rec2020 RGB" (this project's
# darktable branch adds it) and, per the project's intent, "input" =
# scene-referred. That dropdown DEFAULTS to sRGB. An Adobe RGB cube tolerates
# the sRGB default because Adobe gamma ~= sRGB (only a slight tone shift), so
# it is easy to never notice the dropdown -- but a PQ cube read as sRGB is a
# wild curve mismatch: the effective transfer is flat and dark from -3 to +1
# stop, then steps to white by +2, i.e. an image made of only crushed and
# blown pixels, exposure just shifting the ratio. If pq2020 looks like that,
# fix the dropdown, not the LUT.
_PQ_M1,_PQ_M2 = 0.1593017578125,78.84375
_PQ_C1,_PQ_C2,_PQ_C3 = 0.8359375,18.8515625,18.6875
def pqdec(v):
    v=max(0.0,min(1.0,v))
    vp=v**(1.0/_PQ_M2)
    num=max(vp-_PQ_C1,0.0); den=_PQ_C2-_PQ_C3*vp
    return (num/den)**(1.0/_PQ_M1) if den>0 else 0.0
def pqenc(c):
    c=max(0.0,min(1.0,c))
    cp=c**_PQ_M1
    return ((_PQ_C1+_PQ_C2*cp)/(1.0+_PQ_C3*cp))**_PQ_M2

# name -> (display label, RGB->XYZ matrix for hk_mul(), decode
# E-encoded->linear, encode linear->E-encoded). Selected once in main() via
# --colorspace and threaded through the pipeline; default stays Adobe RGB so
# the committed .cube files are unaffected unless --colorspace pq2020 is
# passed explicitly. Used to carry an `ssf` (XYZ->RGB CMF table) entry for
# _weights(), Tri-X's fixed-weight colour->exposure model; removed along with
# _weights() itself when Ticket 21 moved Tri-X onto the same per-pixel
# spectral reconstruction every color film already uses (see
# trix_exposure_grid()) -- nothing computes an XYZ->RGB CMF table anymore.
COLORSPACES = {
    "adobergb": dict(name="adobergb", label="Adobe RGB",   rgb2xyz=_MA_INV_ADOBE,   dec=adec, enc=aenc),
    "pq2020":   dict(name="pq2020",   label="PQ Rec.2020", rgb2xyz=_MA_INV_REC2020, dec=pqdec, enc=pqenc),
}

# =========================================================================
# CIELCh + Helmholtz-Kohlrausch (Fairchild & Pirrotta 1991)
# =========================================================================
_Xn,_Yn,_Zn = 0.95047,1.0,1.08883
_d3 = (6/29)**3
def _lf(t): return t**(1/3) if t>_d3 else t/(3*(6/29)**2)+4/29
def _lfi(t): return t**3 if t>6/29 else 3*(6/29)**2*(t-4/29)

# Ceiling on hk_mul()'s output. The Fairchild & Pirrotta (1991) L** model has no
# built-in bound and was fit/tested only against real Munsell surface chips (their
# Table I): L* in [~30,~87], C* in [~6,~87]. The largest luminance-matching ratio
# implied by any of their own measured (not just modelled) data points is ~2.7x
# (sample 5PB3/10: L*=30.42, C*=44.05 -> observed lightness 48.6). Wide-gamut scene
# colours (this tool decodes Adobe RGB by default, or wider-gamut Rec.2020 via
# --colorspace pq2020) routinely exceed that C* range and produce unbounded
# multipliers when fed through the formula's linear C* term. 3.0x gives
# headroom above the largest paper-supported ratio while cutting off extrapolation
# far beyond it. See README "Helmholtz-Kohlrausch correction" for the full derivation.
# Derived against Adobe RGB's gamut specifically -- not re-derived for Rec.2020's
# wider primaries, so it's a conservative (not necessarily optimal) cap there too.
HK_MAX_MUL = 3.0

def hk_mul(R,G,B,rgb2xyz=_MA_INV_ADOBE):
    """HK exposure multiplier from linear RGB input (primaries given by
    rgb2xyz, Adobe RGB by default), capped at HK_MAX_MUL."""
    if R<1e-6 and G<1e-6 and B<1e-6: return 1.0
    X=rgb2xyz[0][0]*R+rgb2xyz[0][1]*G+rgb2xyz[0][2]*B
    Y=rgb2xyz[1][0]*R+rgb2xyz[1][1]*G+rgb2xyz[1][2]*B
    Z=rgb2xyz[2][0]*R+rgb2xyz[2][1]*G+rgb2xyz[2][2]*B
    if Y<1e-6: return 1.0
    fy=_lf(Y/_Yn); L=116*fy-16
    a=500*(_lf(X/_Xn)-fy); b=200*(fy-_lf(Z/_Zn))
    C=math.sqrt(a*a+b*b); h=math.degrees(math.atan2(b,a))%360
    if L<=0.01 or C<0.5: return 1.0
    dL=(2.5-0.025*L)*(0.116*abs(math.sin(math.radians((h-90)/2)))+0.085)*C
    Yc=_Yn*_lfi((L+dL+16)/116); Yo=_Yn*_lfi((L+16)/116)
    if Yo<=1e-10: return 1.0
    return min(Yc/Yo, HK_MAX_MUL)

# =========================================================================
# Interpolation
# =========================================================================
def _il10(ks,vs,wl):
    if wl<ks[0]: return 0.0
    if wl>ks[-1]: return 0.0
    for i in range(len(ks)-1):
        if ks[i]<=wl<=ks[i+1]:
            t=(wl-ks[i])/(ks[i+1]-ks[i]); return 10**(vs[i]*(1-t)+vs[i+1]*t)
    return 0.0

def _il(ks,vs,x):
    if x<=ks[0]: return vs[0]
    if x>=ks[-1]: return vs[-1]
    lo,hi=0,len(ks)-1
    while hi-lo>1:
        m=(lo+hi)//2
        if ks[m]<=x: lo=m
        else: hi=m
    t=(x-ks[lo])/(ks[hi]-ks[lo]); return vs[lo]*(1-t)+vs[hi]*t

def _sc(d):
    pts=sorted((float(k),float(v)) for k,v in d.items())
    return [p[0] for p in pts],[p[1] for p in pts]

# =========================================================================
# Film data — Tri-X 400 (Kodak F-4017, 5063 emulsion)
# =========================================================================
TRIX_SENS = {300.106:2.4887,321.93:2.5772,340.09:2.657,354.311:2.6946,378.652:2.709,399.71:2.6975,420.878:2.6709,439.421:2.6171,454.955:2.55,472.732:2.4227,485.86:2.3157,497.237:2.2417,506.098:2.2232,514.029:2.2434,529.837:2.3163,548.434:2.3944,564.296:2.4424,575.564:2.4539,587.926:2.414,596.568:2.3764,605.648:2.377,612.977:2.403,619.979:2.4146,625.339:2.3938,630.371:2.3261,634.638:2.2203,643.663:1.6766,649.953:1.1155,657.611:0.5313,664.995:0.1553,668.277:0.0107}
TRIX_DEV7 = {-3.4444:0.3284,-3.3158:0.3393,-3.1488:0.3566,-2.9881:0.3764,-2.8335:0.412,-2.6932:0.462,-2.5528:0.5289,-2.2907:0.6779,-1.9185:0.9012,-1.6062:1.1017,-1.1333:1.4162,-0.7932:1.6414,-0.4773:1.839,0.0013:2.1093,0.3246:2.2732}

# Kodak Polymax Fine-Art VC paper, grades 0-5
POLY = {
"0":{0.2071:0.0384,0.3415:0.0395,0.4803:0.0405,0.5913:0.0448,0.6724:0.0533,0.7385:0.08,0.7876:0.1131,0.8762:0.1867,0.9509:0.2699,1.0491:0.4086,1.1377:0.5568,1.238:0.7147,1.3362:0.8811,1.4258:1.0006,1.4941:1.0945,1.587:1.2321,1.7236:1.4369,1.8485:1.6385,1.9733:1.8465,2.0694:2.0321,2.1163:2.1089,2.1836:2.1783,2.2519:2.2231,2.3501:2.2572,2.4461:2.2785,2.5507:2.2935,2.6681:2.3031,2.8986:2.302},
"1":{0.203:0.0392,0.3303:0.0403,0.5525:0.0425,0.697:0.05,0.7725:0.0587,0.8243:0.077,0.8675:0.1029,0.9365:0.1579,1.0325:0.2777,1.1587:0.4579,1.3129:0.6846,1.4521:0.8918,1.5707:1.0839,1.6926:1.2921,1.7983:1.5069,1.9159:1.7896,2.0044:2.0012,2.0874:2.1641,2.1273:2.2191,2.1737:2.2569,2.2719:2.2947,2.3927:2.299,2.507:2.2968,2.7939:2.299},
"2":{0.3074:0.0352,0.4312:0.0363,0.5849:0.0405,0.7001:0.048,0.7844:0.064,0.8399:0.0907,0.9242:0.1579,1.031:0.2742,1.1291:0.4203,1.2722:0.6656,1.3789:0.8555,1.4888:1.0646,1.6094:1.2833,1.7215:1.5628,1.7951:1.758,1.8677:1.9415,1.9242:2.0705,1.9851:2.1697,2.0416:2.2241,2.127:2.2711,2.2124:2.2935,2.3116:2.3009,2.4226:2.302,2.5944:2.3052},
"3":{0.4079:0.0371,0.5741:0.0382,0.71:0.0414,0.7725:0.0479,0.8286:0.0543,0.8675:0.0651,0.9009:0.0792,0.9505:0.1094,1.0098:0.1644,1.0659:0.2335,1.1587:0.3716,1.2978:0.6123,1.4359:0.8831,1.533:1.1238,1.6279:1.4065,1.7164:1.6914,1.8156:1.9763,1.8706:2.0983,1.9094:2.1598,1.9429:2.1986,2.0033:2.2483,2.0993:2.2968,2.2018:2.3152,2.356:2.3163,2.6926:2.3184},
"4":{0.6126:0.0363,0.7385:0.0395,0.8431:0.0405,0.9669:0.0405,1.0736:0.0448,1.159:0.0565,1.2188:0.0789,1.2796:0.1205,1.3308:0.1675,1.3949:0.2443,1.4493:0.3435,1.4963:0.4608,1.5688:0.672,1.6446:0.9067,1.7503:1.2374,1.8762:1.6556,1.9562:1.9201,2.0192:2.0929,2.0459:2.1473,2.0758:2.1964,2.1366:2.2583,2.1974:2.2892,2.2839:2.3063,2.3949:2.3127},
"5":{0.902:0.0382,1.0832:0.0403,1.1673:0.0457,1.2277:0.0543,1.2687:0.0673,1.3022:0.0889,1.3334:0.1202,1.368:0.1666,1.4111:0.2421,1.4413:0.3155,1.4888:0.4903,1.5308:0.6727,1.5707:0.8454,1.6549:1.2824,1.725:1.6321,1.7584:1.7896,1.8027:1.9699,1.8426:2.1091,1.8728:2.1846,1.9062:2.2289,1.9709:2.2645,2.0561:2.2861,2.1273:2.2968,2.233:2.3022,2.6688:2.3076},
}

# =========================================================================
# Film data — Fuji Velvia 50 (reversal, 3 dye layers)
# =========================================================================
VELVIA_SENS = [
{579.099:-0.8037,583.826:-0.6074,586.78:-0.4504,592.024:-0.3037,595.421:-0.2178,601.108:-0.1719,612.703:-0.0985,621.787:0.0,630.945:0.2,637.223:0.3741,641.95:0.4637,646.529:0.5274,650.591:0.5467,657.09:0.4963,659.453:0.3963,664.033:0.1111,671.787:-0.1363,681.019:-0.3185,686.632:-0.4548,689.365:-0.5444,691.137:-0.6207},
{486.016:-0.7274,494.355:-0.489,499.527:-0.3441,507.608:-0.1701,519.697:0.0425,528.166:0.1907,534.696:0.3389,540.578:0.4646,544.587:0.5258,548.401:0.5548,553.896:0.5322,556.934:0.4884,561.007:0.4439,567.149:0.4323,572.708:0.4549,575.812:0.4626,579.044:0.4356,583.44:0.1392,588.482:-0.2603,591.844:-0.5406},
{387.492:-0.2861,393.181:0.107,397.707:0.3615,400.422:0.4517,404.107:0.5238,410.701:0.5619,417.424:0.558,424.277:0.5258,432.035:0.5032,439.146:0.5097,444.835:0.5348,449.49:0.5638,452.981:0.5735,456.407:0.5354,461.385:0.4291,470.565:0.2036,475.931:0.0619,480.197:-0.0799,485.822:-0.3731,489.765:-0.5728,493.838:-0.7796},
]
VELVIA_CURVES = [
{-2.8207:3.3492,-2.4732:3.3448,-2.1301:3.3222,-1.9555:3.2917,-1.7818:3.2134,-1.6741:3.1108,-1.5672:2.9298,-1.4456:2.6714,-1.3397:2.4008,-1.2424:2.1276,-1.1017:1.7796,-0.888:1.3706,-0.6856:1.0487,-0.3538:0.5963,-0.0506:0.33,0.1639:0.2143,0.3151:0.1656,0.567:0.1351,0.897:0.1334,1.1168:0.1404},
{-2.8146:3.8129,-2.5861:3.8042,-2.3256:3.772,-2.1197:3.7085,-1.9303:3.5762,-1.787:3.4109,-1.6585:3.1456,-1.4917:2.7097,-1.3371:2.2929,-1.1903:1.9379,-1.027:1.562,-0.8298:1.2114,-0.5431:0.7894,-0.3329:0.5388,-0.0889:0.3231,0.0979:0.2187,0.3281:0.1656,0.5062:0.1569,0.7581:0.1543,0.9492:0.163,1.1142:0.1682},
{-2.8207:3.7111,-2.5688:3.6954,-2.3516:3.6737,-2.1041:3.5997,-1.9868:3.5327,-1.9086:3.4675,-1.8087:3.3457,-1.7193:3.1908,-1.6263:2.9802,-1.5594:2.8149,-1.4595:2.5452,-1.3553:2.2711,-1.2207:1.9492,-1.1025:1.6925,-0.9887:1.4663,-0.7594:1.0992,-0.6092:0.8799,-0.4172:0.6372,-0.2852:0.4884,-0.0741:0.3144,0.0128:0.2561,0.2021:0.196,0.4592:0.1551,0.8319:0.1612,1.1107:0.1673},
]

# =========================================================================
# Film data — EASTMAN Color Internegative II Film 5272/7272 (duplicating
# negative made from a reversal/slide original; the middle stage of Velvia's
# print cascade below). Digitized via film_paper_filter_data/tools/
# curve_digitizer/ from the real Kodak/Eastman datasheet TI1301 (papers/
# kodak_internegative_ii_5272_TI1301.pdf) — vector-precise extraction, real
# monotonicity enforced at the source (see that tool's README). Layer order
# reordered from the digitizer's own blue/green/red output to match
# VELVIA_SENS/VELVIA_CURVES's established [red-sensitive/cyan-forming,
# green-sensitive/magenta-forming, blue-sensitive/yellow-forming] convention.
# Measured gamma ~0.527 — genuinely low-contrast, like an ordinary camera
# negative, engineered to leave headroom for the print paper's own contrast.
# =========================================================================
INTERNEGATIVE_II_SENS = [
{532.4:-2.998,544.3:-2.83,553:-2.669,558.6:-2.49,576.5:-2.086,598.4:-1.488,602.3:-1.41,622.6:-1.135,633.3:-0.9236,634.9:-0.9144,635.3:-0.8871,636.9:-0.8771,637.3:-0.8503,645.3:-0.7265,653.6:-0.5256,655.6:-0.5047,657.6:-0.5031,660.4:-0.5484,667.1:-0.8851,681.4:-1.962,691:-2.583},
{489.5:-2.49,494.5:-2.156,505.8:-1.787,520.1:-1.651,520.6:-1.615,522.9:-1.577,527.9:-1.527,534.7:-1.374,535.2:-1.339,536.1:-1.337,542.8:-1.136,546.2:-1.075,546.7:-1.034,552.1:-0.9508,555.7:-0.9521,566.7:-1.058,576.8:-1.327,579.3:-1.463,586.6:-2.183,590.5:-2.463,601.5:-2.963},
{399.4:0.21,408.3:0.2146,426.5:0.0328,432.6:-0.0566,439.4:-0.2026,440.3:-0.1975,444.3:-0.2955,445.2:-0.2918,457.9:-0.5851,466.8:-0.8601,467.7:-0.8599,480:-1.302,480.3:-1.284,481.6:-1.322,494.8:-1.855,498.5:-1.964,499.1:-2.03,500:-2.033,500.6:-2.089,501.6:-2.095,510.5:-2.453,511.4:-2.527,513.9:-2.59,520.3:-2.895,521.3:-2.985,522.2:-2.994},
]
INTERNEGATIVE_II_CURVES = [
{-1.2434:0.0626,-1.0432:0.0654,-0.824:0.0945,-0.5666:0.1606,-0.4522:0.2031,-0.4236:0.2066,-0.3473:0.2423,-0.3187:0.2472,-0.2139:0.2925,0.0245:0.4159,0.1865:0.4835,0.1961:0.495,0.32:0.5506,0.3295:0.5617,0.4916:0.6314,0.5297:0.6548,0.7013:0.7105,1.0159:0.8366,1.1208:0.8975,1.178:0.9193,1.1875:0.931,1.2161:0.937,1.2542:0.9635,1.3782:1.0206,1.5402:1.1265,1.5974:1.1518,1.607:1.1669,1.8929:1.3314,2.5603:1.6636},
{-1.2434:0.4822,-1.026:0.4841,-0.8464:0.5016,-0.6289:0.5435,-0.4399:0.6115,-0.2697:0.7099,-0.0996:0.7896,0.0233:0.8571,0.1273:0.9277,0.3542:1.0541,0.4109:1.0773,0.496:1.1252,0.5811:1.1589,0.6189:1.1824,0.7134:1.2189,1.1955:1.4595,1.3563:1.5643,1.5453:1.6667,1.5642:1.6709,1.7817:1.8069,1.8762:1.8539,1.9235:1.87,1.9707:1.9006,2.0558:1.9391,2.5285:2.1297},
{-1.2434:0.803,-0.8621:0.8195,-0.7191:0.8354,-0.5951:0.8655,-0.4998:0.9021,-0.4807:0.9031,-0.2805:0.9981,-0.1375:1.0806,0.0436:1.2003,0.0722:1.21,0.7968:1.6891,0.873:1.7229,1.0446:1.8234,1.0733:1.8311,1.3974:2.0223,1.4737:2.0535,1.6453:2.1538,1.6739:2.1616,1.9217:2.3074,1.998:2.3452,2.0171:2.3462,2.1982:2.4225,2.2173:2.4226,2.3222:2.4657,2.408:2.4838,2.5605:2.503},
]

# Real published Kodak calibration target for the internegative, Status M
# density, [red/cyan-forming, green/magenta-forming, blue/yellow-forming] --
# matches INTERNEGATIVE_II_CURVES' own layer order. Not derived or guessed:
# transcribed directly from EASTMAN Color Internegative II Film 5272/7272's
# own datasheet (TI1301, section 9 "Laboratory Aim Density (LAD)"): "Status
# M LAD values for EASTMAN Color Internegative II Film: Internegative LAD
# Aim Red 0.90, Green 1.30, Blue 1.70 (+/-0.12 density)" -- the density the
# internegative should read when a normally-exposed reversal original is
# printed onto it at the center of the printer range. Used by
# build_print_cascade() (via COLOR_FILMS) as this stage's calibration
# reference point instead of an invented density-midpoint heuristic.
INTERNEGATIVE_II_LAD_AIM = [0.90, 1.30, 1.70]

# =========================================================================
# Print paper data — real RA-4 negative/print papers, forming a shared
# 5-rung contrast ladder (like POLY's grades 0-5 do for Tri-X) used by
# every color film below. Excludes cinema release-print stocks (Kodak
# 2383/2393/5381-series, Technicolor V) and duratrans/backlit display
# materials (Fujiflex, Duraflex Plus) as the wrong medium regardless of
# gamma fit. See README "Choosing a print paper" for the full selection
# writeup and the measured-span table (tools/measure_paper_punch.py) behind
# PAPER_LADDER's ordering.
# =========================================================================
CA_PRO_PDII = [  # Fuji Crystal Archive Pro PDII
{0.6569:0.1224,0.7192:0.1231,0.7815:0.1275,0.8438:0.1333,0.906:0.1418,0.9683:0.1531,1.0306:0.1672,1.0929:0.1855,1.1552:0.2074,1.2175:0.2336,1.2779:0.262,1.3129:0.2778,1.4183:0.3523,1.5294:0.4599,1.6601:0.6393,1.7141:0.7519,1.7607:0.8688,1.786:0.9421,1.8132:1.0065,1.8327:1.0837,1.8522:1.1483,1.8642:1.2121,1.8794:1.2921,1.8911:1.332,1.9297:1.5461,1.9641:1.7418,1.9722:1.7435,2.0421:2.0444,2.0605:2.106,2.0819:2.1693,2.1072:2.2371,2.1364:2.3035,2.1695:2.3693,2.2084:2.4345,2.2518:2.4949,2.3077:2.5605,2.37:2.618,2.4323:2.6642,2.4871:2.6959,2.5569:2.7291,2.6192:2.7514,2.6815:2.7687,2.7438:2.7811,2.8061:2.7899,2.8684:2.7953,2.9248:2.7964},
{0.6569:0.1477,0.7192:0.1497,0.7795:0.1531,0.8308:0.158,0.906:0.1676,0.9528:0.1751,1.0473:0.1959,1.1674:0.2371,1.2979:0.2957,1.4473:0.3957,1.6033:0.5646,1.7196:0.7657,1.7839:0.9242,1.8502:1.1407,1.8625:1.1989,1.8775:1.2513,1.9106:1.398,1.9797:1.752,2.039:1.9795,2.058:2.0737,2.0897:2.1382,2.1146:2.1962,2.1377:2.2558,2.1897:2.3383,2.2259:2.3908,2.2649:2.4393,2.3934:2.5595,2.4498:2.5961,2.5338:2.639,2.6036:2.6648,2.6659:2.6823,2.7325:2.6959,2.7948:2.7052,2.8528:2.7105,2.9151:2.7143,2.9482:2.7145},
{0.6569:0.1477,0.7192:0.1502,0.7795:0.1531,0.8308:0.158,0.906:0.1674,0.9683:0.1789,1.0273:0.19,1.139:0.2201,1.2449:0.2607,1.3546:0.3183,1.529:0.4618,1.5796:0.525,1.6205:0.5841,1.6614:0.6494,1.6964:0.7164,1.7276:0.7823,1.7548:0.8486,1.7782:0.9071,1.7996:0.9762,1.8191:1.0386,1.8385:1.1153,1.8561:1.178,1.8758:1.2491,1.9359:1.5117,1.966:1.6263,2.0371:1.8554,2.0838:1.9672,2.1383:2.0733,2.2104:2.1768,2.2921:2.265,2.3895:2.3414,2.4985:2.4004,2.6114:2.4427,2.7301:2.4716,2.8508:2.4868,2.9657:2.493},
]
PORTRA_ENDURA = [  # Kodak Portra Endura Paper
{-3:0.0888,-2.3878:0.0952,-2.2468:0.1081,-2.1715:0.1243,-2.0929:0.1469,-2.016:0.1791,-1.9455:0.2259,-1.8734:0.2953,-1.7981:0.3873,-1.7308:0.4922,-1.6346:0.7101,-1.5385:0.9699,-1.4423:1.2604,-1.3333:1.6154,-1.2548:1.8687,-1.2212:1.9672,-1.1731:2.0931,-1.117:2.2028,-1.0673:2.2835,-1.0128:2.3609,-0.9391:2.4287,-0.8365:2.4965,-0.7372:2.5352,-0.609:2.5724,-0.484:2.6046,-0.3718:2.624,-0.3045:2.6321,-0.1603:2.6563},
{-2.9904:0.092,-2.2949:0.1033,-2.0481:0.1662,-1.891:0.2808,-1.7676:0.4325,-1.6907:0.5713,-1.5801:0.8327,-1.4599:1.1813,-1.3702:1.4798,-1.2853:1.7283,-1.2019:1.9527,-1.1026:2.1544,-1.0288:2.2609,-0.9006:2.3916,-0.7853:2.4691,-0.6635:2.5239,-0.5449:2.5756,-0.4519:2.6095,-0.3269:2.6272,-0.1587:2.6595},
{-2.9936:0.0904,-2.3942:0.0968,-2.2051:0.1162,-2.0769:0.1549,-1.9135:0.2517,-1.8189:0.3421,-1.7372:0.4615,-1.6074:0.7327,-1.5353:0.9279,-1.4343:1.2426,-1.3702:1.4588,-1.2532:1.8203,-1.2163:1.9188,-1.1635:2.0446,-1.1042:2.156,-1.0385:2.2464,-0.9647:2.3045,-0.9167:2.3303,-0.8622:2.3513,-0.7644:2.3739,-0.6058:2.3932,-0.4423:2.4077,-0.3077:2.4142,-0.1635:2.4223},
]
CA_SUPER_TYPE_C = [  # Fuji Crystal Archive Super Type C
{-0.2482:0.0895,-0.0158:0.1,0.1548:0.1281,0.3465:0.1857,0.4813:0.2488,0.6:0.3254,0.7685:0.4868,0.9342:0.7493,1.036:1.0013,1.1112:1.2884,1.1828:1.6274,1.234:1.871,1.3113:2.1427,1.4131:2.3869,1.5458:2.5772,1.6568:2.6803,1.7642:2.7484,1.8906:2.8011,2.0092:2.8334,2.1237:2.8502,2.1995:2.8558,2.2761:2.86},
{-0.2496:0.1155,-0.0959:0.1211,0.0509:0.1351,0.1815:0.1597,0.3282:0.2025,0.4167:0.2383,0.4912:0.2748,0.5649:0.3218,0.6267:0.3661,0.7418:0.4664,0.8422:0.583,0.9349:0.7479,1.0388:1.0041,1.1098:1.2638,1.1659:1.5165,1.206:1.7061,1.2467:1.8745,1.2979:2.0465,1.3492:2.1834,1.4222:2.3364,1.5444:2.4978,1.6462:2.5926,1.7635:2.6649,1.8976:2.7168,2.0275:2.7498,2.1785:2.7702,2.281:2.7737},
{-0.2489:0.1176,-0.065:0.1225,0.1036:0.1443,0.237:0.1737,0.3634:0.2166,0.5213:0.291,0.6512:0.3794,0.7903:0.5156,0.8837:0.6391,0.9813:0.8392,1.0571:1.0498,1.1048:1.2358,1.1561:1.4358,1.2165:1.6639,1.2699:1.8359,1.3309:1.9889,1.3906:2.0977,1.4637:2.2016,1.5683:2.3104,1.6568:2.3785,1.7803:2.4417,1.9004:2.4859,2.0219:2.5161,2.1714:2.5364,2.3224:2.5442},
]
CA_DPII = [  # Fuji Crystal Archive DPII
{-0.0535:0.1023,0.107:0.1063,0.2607:0.1172,0.3261:0.1262,0.3944:0.143,0.4628:0.1669,0.5322:0.2046,0.6006:0.2563,0.7056:0.3745,0.7889:0.5126,0.886:0.7331,1.0297:1.1662,1.1824:1.6232,1.2735:1.8715,1.3707:2.0901,1.4688:2.249,1.5907:2.403,1.7324:2.5291,1.8365:2.5967,1.9356:2.6404,2.0416:2.6682},
{-0.0486:0.1033,0.0476:0.1053,0.1417:0.1093,0.2577:0.1162,0.3717:0.1391,0.4757:0.1758,0.5709:0.2344,0.669:0.3219,0.8236:0.5851,0.9177:0.8136,0.9732:0.9874,1.0555:1.2854,1.1011:1.4444,1.1784:1.7126,1.2795:1.9858,1.328:2.1,1.3845:2.1894,1.4331:2.256,1.5035:2.3295,1.5857:2.3762,1.6928:2.4228,1.8028:2.4517,1.9207:2.4695,2.0416:2.4805},
{-0.0476:0.0606,0.0396:0.0646,0.1665:0.0695,0.3003:0.0834,0.4708:0.1301,0.5669:0.1887,0.6551:0.2781,0.7572:0.4371,0.8454:0.6298,0.9197:0.8185,0.999:1.0669,1.0585:1.2904,1.1318:1.5397,1.2071:1.7921,1.2587:1.954,1.3518:2.1387,1.3984:2.2123,1.4579:2.2808,1.5282:2.3444,1.6274:2.394,1.7393:2.4358,1.8484:2.4616,1.9574:2.4735,2.0347:2.4775},
]
SUPRA_ENDURA = [  # Kodak Supra Endura Paper
{-2.8178:0.0827,-2.4666:0.0827,-2.3277:0.0827,-2.1782:0.0891,-2.0367:0.1005,-1.9056:0.1329,-1.827:0.1718,-1.7274:0.248,-1.6592:0.3306,-1.5662:0.4895,-1.502:0.6337,-1.4482:0.8039,-1.3722:1.1183,-1.325:1.3339,-1.2805:1.5867,-1.2385:1.8006,-1.194:2.0016,-1.1533:2.1669,-1.114:2.3096,-1.0721:2.4117,-1.0315:2.4749,-0.9934:2.5235,-0.9436:2.5673,-0.8781:2.5997,-0.8204:2.6256,-0.7366:2.6451,-0.6343:2.658,-0.5636:2.6467,-0.5059:2.6272},
{-2.8165:0.0827,-2.4797:0.0827,-2.0839:0.0859,-1.9817:0.0972,-1.8899:0.1135,-1.8296:0.1394,-1.7851:0.1702,-1.7379:0.2075,-1.6828:0.269,-1.616:0.3695,-1.5413:0.5138,-1.4758:0.6759,-1.3958:0.953,-1.3172:1.2853,-1.2333:1.6872,-1.1389:2.0405,-1.0983:2.1605,-1.0524:2.2577,-0.9987:2.3485,-0.9463:2.4165,-0.8912:2.4668,-0.8283:2.5138,-0.7733:2.5462,-0.7077:2.5737,-0.6474:2.59,-0.5924:2.5932,-0.5452:2.5883,-0.5007:2.5786},
{-2.8126:0.0859,-2.3696:0.0843,-2.097:0.0924,-1.9633:0.1167,-1.8716:0.1475,-1.7877:0.1977,-1.7169:0.2577,-1.6461:0.3485,-1.5858:0.4489,-1.519:0.5932,-1.4666:0.7342,-1.4063:0.9579,-1.346:1.2237,-1.2962:1.5024,-1.2464:1.7715,-1.1953:1.9984,-1.1507:2.1507,-1.1035:2.2836,-1.0668:2.3485,-1.0223:2.4068,-0.9725:2.4489,-0.9253:2.4765,-0.8729:2.4895,-0.8152:2.5008,-0.768:2.5089,-0.7025:2.5154,-0.6396:2.5203,-0.5819:2.5105,-0.5242:2.4878,-0.4954:2.4749},
]

# name -> paper curve list (3 layers), used as the final stage in every
# color film's cascade. Each layer's own _find_anchor start index (needed
# only by Kodak Supra Endura, whose raw curve has a single leading
# digitization-noise sample on its blue/yellow-forming layer -- density
# oscillating ~0.0016, not a real reversal, the same kind of noise Kodak
# Endura Premier and Fuji Provia 100F needed handling for, just smaller) is
# detected automatically per layer by _detect_lead_noise_start() rather than
# hand-derived here -- see that function's docstring.
#
# This assignment was re-derived from tools/measure_paper_punch.py, which
# runs every real candidate paper (film_paper_filter_data/papers/color/
# for_negatives/, the same 7-paper "legitimate reflective RA-4" pool
# identified in tasks/DONE-07) through the actual production cascade
# (build_print_cascade(), _find_anchor-calibrated exactly like every shipped
# LUT) instead of estimating contrast from a regression slope over each
# paper's own curve in isolation. The isolated-regression estimate that
# originally produced this ladder (see README "Choosing a print paper" git
# history) turned out not to predict what the real cascade renders: it
# ranked Kodak Endura Premier "ExtraSoft" when it's actually the punchiest
# candidate of the 7 on every film, put Fuji Crystal Archive Maxima and DPII
# so close together ("Punchy"/"ExtraPunchy") they're barely distinguishable
# side by side, and never considered 2 real, eligible papers (Fuji Crystal
# Archive Pro PDII, Kodak Supra Endura) that were digitized in the source
# pool but never promoted into this ladder.
#
# Measured full-range span (white-corner minus black-corner encoded output,
# averaged across the 3 layers -- the real cascade's own answer to "how
# punchy does this actually render," not a curve-fit proxy) is consistent
# in rank order across all 4 color films, so one shared ladder still works
# for all of them; see tools/measure_paper_punch.py's own output for the
# per-film numbers, and README "Choosing a print paper" for the summary
# table. Two of the 7 real candidates (Kodak Endura Premier, Fuji Crystal
# Archive Maxima) measure well but sit too close to their neighbors to add a
# usefully distinct rung, so -- same as the previous ladder leaving 2 papers
# unused -- they're left out here in favor of Pro PDII and Supra Endura,
# which are not.
#
# One real, measured non-monotonicity worth flagging (same kind of
# curve-crossover documented in tasks/06 for Tri-X's Polymax grades 0/1,
# not a code defect): Fuji Crystal Archive Pro PDII ("Soft") has *more*
# local midtone gamma than Kodak Portra Endura ("Normal") on every film,
# even though Pro PDII's overall span is lower -- Portra Endura spreads its
# contrast more gradually across a wider range instead of concentrating it
# around grey. So Soft vs Normal are correctly ordered by overall
# shadow-to-highlight spread, not by local contrast right around grey.
PAPER_LADDER = {
"ExtraSoft":   CA_SUPER_TYPE_C,
"Soft":        CA_PRO_PDII,
"Normal":      PORTRA_ENDURA,
"Punchy":      CA_DPII,
"ExtraPunchy": SUPRA_ENDURA,
}
COLOR_LOOKS = ["ExtraSoft", "Soft", "Normal", "Punchy", "ExtraPunchy"]

# =========================================================================
# Direct-print papers for reversal originals -- real photographic materials
# designed to be exposed *directly* by a reversal (slide) original, with no
# internegative-duplication stage in between: Kodak Ektachrome Radiance III
# (a genuine Kodak reversal print paper) and Ilfochrome Micrographic M/P
# (dye-destruction duplicating/microfilm stock; CLAUDE.md already records
# that this pairing was tried once for Velvia as a *direct* cascade and
# rejected for compounding to an unusably contrasty 2.0-3.0 system gamma --
# that rejection was for going through it *uncorrected*, the same problem
# every route here has without the GAMMA_CORRECT_TARGET fix above; it is not
# re-rejected here). Digitized from film_paper_filter_data/papers/color/
# for_reversal/*.json (kodak_ektachrome_radiance_iii.json,
# ilfochrome_micrographic_m.json, ilfochrome_micrographic_p.json) -- the
# same spectral_film_lut-derived pool PAPER_LADDER's papers come from, not a
# separate/less-trusted source.
#
# Density *falls* with exposure for all three (increasing=False), the same
# direction as every reversal dye layer (VELVIA_CURVES etc.) and unlike
# every PAPER_LADDER paper (increasing=True, ordinary negative-working RA-4
# stock) -- confirmed directly against each raw JSON's own digitized curve,
# not assumed: these are reversal-process print materials (R-3-family
# chromogenic reversal paper / dye-destruction), photographically a
# different animal from RA-4 despite both being "the paper a print comes
# out on." Layer order matches the established [red/cyan, green/magenta,
# blue/yellow] convention (confirmed against each JSON's own log_sensitivity
# peak wavelengths: ~650nm/~550nm/~445nm), so no reordering was needed the
# way INTERNEGATIVE_II_CURVES needed. Each source JSON also carries a real
# published Status A "lad" field (Radiance III: [1,1,1]; both Ilfochromes:
# [0.910,1.013,0.981]) confirming these are genuine calibrated print
# materials, not experimental/placeholder data -- unused here since only a
# *non-final* cascade stage needs a ref_d (see build_print_cascade's
# docstring) and these are always the final stage in DIRECT_PRINT_PAPERS'
# 2-stage cascade.
#
# No SENS (spectral sensitivity) data is transcribed for any of the three --
# same as every PAPER_LADDER paper, a paper's own spectral sensitivity is
# irrelevant here because it never receives scene light directly, only the
# calibrated printing exposure build_print_cascade() hands it from the
# reversal film's own (gamma-corrected) stage.
# =========================================================================
RADIANCE_III_CURVES = [
{0.0:2.5171,0.1634:2.5206,0.3578:2.5171,0.5251:2.4785,0.6924:2.4181,0.8076:2.3545,0.9491:2.2256,1.1217:2.0444,1.2737:1.8659,1.412:1.6738,1.4794:1.5728,1.5421:1.4756,1.6072:1.3784,1.6793:1.2805,1.756:1.1832,1.835:1.0842,1.9117:0.9874,1.9884:0.8902,2.0674:0.7912,2.1465:0.695,2.2255:0.6014,2.3068:0.5045,2.3882:0.407,2.4719:0.3106,2.5648:0.2201,2.6625:0.1574,2.7601:0.1217,2.8577:0.1042,2.9553:0.0987,3.0529:0.0969,3.1506:0.0953,3.2482:0.0931,3.3458:0.0901,3.4434:0.0874,3.541:0.0862,3.6387:0.0862,3.7363:0.0862,3.7921:0.0862},
{0.0057:2.4181,0.2567:2.4199,0.4668:2.4026,0.5912:2.3789,0.7624:2.3457,0.9335:2.2528,1.0891:2.1168,1.2058:2.0002,1.412:1.6738,1.4794:1.5728,1.5421:1.4756,1.6072:1.3784,1.6793:1.2805,1.756:1.1832,1.835:1.0842,1.9117:0.9874,1.9884:0.8902,2.0674:0.7912,2.1465:0.695,2.2255:0.6014,2.3068:0.5045,2.3882:0.407,2.4719:0.3106,2.5648:0.2201,2.6625:0.1574,2.7601:0.1217,2.8577:0.1042,2.9553:0.0987,3.0529:0.0969,3.1506:0.0953,3.2482:0.0931,3.3458:0.0901,3.4434:0.0874,3.541:0.0862,3.6387:0.0862,3.7363:0.0862,3.7921:0.0862},
{0.0:2.451,0.2023:2.4549,0.3851:2.4564,0.5679:2.4238,0.7274:2.4026,0.8596:2.3538,0.9841:2.2606,1.1043:2.1359,1.2061:1.9966,1.412:1.6738,1.4794:1.5728,1.5421:1.4756,1.6072:1.3784,1.6793:1.2805,1.756:1.1832,1.835:1.0842,1.9117:0.9874,1.9884:0.8902,2.0674:0.7912,2.1465:0.695,2.2255:0.6014,2.3068:0.5045,2.3882:0.407,2.4719:0.3106,2.5648:0.2201,2.6625:0.1574,2.7601:0.1217,2.8577:0.1042,2.9553:0.0987,3.0529:0.0969,3.1506:0.0953,3.2482:0.0931,3.3458:0.0901,3.4434:0.0874,3.541:0.0862,3.6387:0.0862,3.7363:0.0862,3.7921:0.0862},
]
ILFOCHROME_M_CURVES = [
{0.001:2.0643,0.0411:2.0617,0.1008:2.0606,0.1606:2.0583,0.2203:2.0573,0.28:2.0552,0.3397:2.0547,0.3994:2.0521,0.4592:2.0514,0.5189:2.0481,0.5786:2.0477,0.6383:2.0436,0.6981:2.0341,0.7578:2.0212,0.8175:2.0035,0.8772:1.9785,0.937:1.9458,0.9967:1.905,1.0564:1.8569,1.1147:1.8022,1.1673:1.7431,1.2128:1.6843,1.254:1.6243,1.291:1.564,1.3223:1.5025,1.3547:1.4419,1.3792:1.3826,1.4076:1.3226,1.4361:1.2635,1.4645:1.2053,1.4915:1.1466,1.5185:1.0878,1.5484:1.0292,1.5797:0.9648,1.876:0.3368,1.9016:0.285,1.9464:0.2151,2.0347:0.1199,2.1094:0.0693,2.1752:0.0478,2.2739:0.0374,2.4055:0.0277,2.9932:0.0158},
{0.0411:2.3973,0.1008:2.3953,0.1606:2.3925,0.2203:2.3901,0.28:2.3877,0.3397:2.3841,0.3994:2.3816,0.4592:2.3796,0.5189:2.3776,0.5786:2.3738,0.6383:2.3644,0.6981:2.347,0.7421:2.3315,0.7935:2.3068,0.8578:2.2711,0.9475:2.2012,1.0308:2.1153,1.0834:2.0498,1.1261:1.9903,1.1645:1.932,1.2:1.8749,1.2341:1.8154,1.2654:1.7539,1.2939:1.6895,1.3209:1.6269,1.3465:1.5674,1.3735:1.5049,1.4005:1.4426,1.4261:1.3832,1.4517:1.3234,1.4773:1.2653,1.5043:1.2021,1.5328:1.1363,1.5598:1.0773,1.5854:1.0147,1.6152:0.9493,1.6653:0.8221,1.7491:0.6257,1.8119:0.4799,1.8747:0.3341,1.924:0.2493,1.9719:0.1735,2.0406:0.0991,2.1124:0.053,2.2231:0.0321,2.419:0.0269,2.6089:0.0217,2.8302:0.0158,2.9977:0.0128},
{0.0525:2.4545,0.1122:2.4523,0.1719:2.4492,0.2317:2.4463,0.2914:2.4427,0.3511:2.4393,0.4108:2.4356,0.4705:2.4323,0.5303:2.4288,0.59:2.4197,0.6497:2.4032,0.7094:2.3795,0.7549:2.3582,0.8578:2.2889,0.9573:2.1945,1.0493:2.0935,1.0962:2.0326,1.1374:1.9732,1.1758:1.9138,1.2114:1.8561,1.2441:1.7966,1.274:1.735,1.301:1.6736,1.3266:1.6137,1.3536:1.5541,1.382:1.4911,1.409:1.4298,1.4346:1.3657,1.4602:1.305,1.4858:1.2448,1.5114:1.1856,1.5384:1.1237,1.5655:1.0611,1.5996:0.9812,1.7124:0.7142,1.8006:0.5075,1.8762:0.3341,1.9449:0.2226,1.9906:0.1735,2.0743:0.1058,2.1707:0.0589,2.2223:0.05,2.2664:0.05,2.3921:0.0463,2.5311:0.0433,2.7509:0.0433,2.9962:0.0381},
]
ILFOCHROME_P_CURVES = [
{0.004:1.9192,0.3655:1.9171,0.5641:1.9083,0.7291:1.8805,0.8845:1.8364,1.007:1.7801,1.0844:1.7334,1.1638:1.6696,1.2275:1.6038,1.3035:1.5137,1.387:1.4038,1.5294:1.1882,1.6882:0.959,1.8005:0.7922,1.8998:0.6491,1.984:0.5182,2.0908:0.3541,2.1798:0.2484,2.2633:0.1683,2.3783:0.0897,2.4673:0.0517,2.5509:0.0361,2.659:0.0348,2.8151:0.0327,2.9356:0.0341,3.0:0.0354},
{0.0013:2.2284,0.2286:2.2202,0.3724:2.208,0.5038:2.1917,0.6873:2.1517,0.7893:2.1205,0.905:2.071,1.0098:2.0161,1.1152:1.9266,1.2131:1.8229,1.2843:1.7347,1.3336:1.6723,1.3979:1.5665,1.4869:1.4187,1.6061:1.2126,1.717:1.0146,1.8457:0.7759,1.8984:0.6667,1.9607:0.542,2.0401:0.4002,2.1414:0.2538,2.214:0.167,2.2736:0.1134,2.3263:0.0734,2.3996:0.0456,2.4755:0.0354,2.5591:0.0354,2.6672:0.0354,2.811:0.0334,2.9151:0.0341,2.9986:0.0354},
{0.004:2.2812,0.2779:2.2582,0.4696:2.2358,0.5778:2.2195,0.6859:2.1985,0.7722:2.1755,0.827:2.1511,0.8804:2.1253,0.9461:2.0832,1.0063:2.0331,1.0666:1.9802,1.1385:1.9076,1.2699:1.7469,1.3856:1.5543,1.4596:1.4364,1.5499:1.2858,1.6348:1.1448,1.7608:0.9359,1.8361:0.803,1.921:0.6769,1.9771:0.5847,2.0538:0.4504,2.1161:0.3589,2.1853:0.2741,2.2537:0.2144,2.3167:0.1656,2.392:0.1249,2.5029:0.0897,2.6399:0.0734,2.7713:0.0626,2.885:0.0571,2.9781:0.0585},
]

# name -> paper curve list (3 layers), the direct-print equivalent of
# PAPER_LADDER. Iterated by DIRECT_PRINT_LOOKS in file-naming order.
DIRECT_PRINT_PAPERS = {
    "RadianceIII": RADIANCE_III_CURVES,
    "IlfochromeM": ILFOCHROME_M_CURVES,
    "IlfochromeP": ILFOCHROME_P_CURVES,
}
DIRECT_PRINT_LOOKS = ["RadianceIII", "IlfochromeM", "IlfochromeP"]

# =========================================================================
# Film data — Kodachrome 64, Fuji Provia 100F, Kodak Ektachrome 100D
# (reversal, 3 dye layers each, same [red/cyan, green/magenta, blue/yellow]
# layer order as VELVIA_SENS/VELVIA_CURVES -- confirmed against the raw
# film_paper_filter_data source JSON directly, not assumed). Like Velvia,
# all three are reversal (slide) films: none of them can go straight onto
# negative print paper, so all three route through INTERNEGATIVE_II_CURVES
# via the same 3-stage film->internegative->paper cascade Velvia uses, not
# the 2-stage cascade build_trix_cascade()/Portra-style negatives use.
# =========================================================================
KODACHROME64_SENS = [  # Kodachrome 64
{481.31:-1.8515,495.41:-1.7974,503.35:-1.7516,513.05:-1.5836,523.99:-1.4192,533.95:-1.324,544.8:-1.2474,553.44:-1.1447,561.02:-0.9486,574.16:-0.5845,584.83:-0.1643,589.77:0.0271,596.12:0.1811,603.88:0.2838,616.23:0.4099,622.05:0.4986,630.86:0.7087,641.01:0.8534,646.21:0.9169,650.44:0.93,654.85:0.8814,661.73:0.6573,668.43:0.3585,673.02:0.0784,680.78:-0.5752,687.48:-1.0233,700.71:-1.6956},
{400.09:-1.789,440.04:-1.2428,460.49:-0.9972,467.37:-0.9412,472.66:-0.8553,481.48:-0.5817,491.36:-0.3511,507.05:0.0084,516.05:0.2007,524.25:0.3399,534.39:0.5079,542.5:0.6443,547.44:0.7077,553.44:0.7255,559.88:0.6956,565.08:0.6246,570.9:0.4986,574.78:0.3632,580.78:0.0317,590.65:-0.7806,594.71:-1.1261,598.59:-1.3968,604.06:-1.6863,610.23:-1.9524},
{400.18:-1.5,402.5:-1,405:-0.5,410.32:0.5733,412.35:0.747,416.31:0.915,419.49:0.9832,423.1:1,430.34:0.9813,439.07:0.9141,447:0.8207,457.32:0.7134,465.43:0.6293,471.69:0.55,478.48:0.4099,485.27:0.2232,500.97:-0.3511,511.46:-0.7993,520.55:-1.2241,530.42:-1.6909,536.16:-1.9888},
]
KODACHROME64_CURVES = [
{-2.3572:3.6757,-2.2676:3.6587,-2.178:3.6296,-2.0884:3.5824,-1.9988:3.5177,-1.9114:3.437,-1.8303:3.3497,-1.7599:3.2623,-1.698:3.1719,-1.6426:3.0819,-1.5914:2.9892,-1.5466:2.9003,-1.506:2.8124,-1.4655:2.7196,-1.4271:2.6347,-1.3887:2.5457,-1.3503:2.4533,-1.3119:2.3637,-1.2756:2.2761,-1.2394:2.1853,-1.201:2.0962,-1.1626:2.0036,-1.1242:1.9161,-1.0836:1.8266,-1.041:1.736,-1.0004:1.6496,-0.9556:1.5605,-0.9066:1.4663,-0.8575:1.3743,-0.8063:1.2812,-0.7551:1.1911,-0.7018:1.0999,-0.6463:1.0091,-0.5887:0.9184,-0.529:0.8278,-0.4671:0.7383,-0.3967:0.6471,-0.3135:0.5557,-0.2239:0.4732,-0.1343:0.4059,-0.0447:0.348,0.0022:0.3259,0.2838:0.201,0.3649:0.1923},
{-2.3572:3.4447,-2.2676:3.4275,-2.178:3.4021,-2.0884:3.3618,-1.9988:3.3011,-1.9114:3.2203,-1.8367:3.1248,-1.7748:3.0445,-1.7172:2.9534,-1.6639:2.8607,-1.6148:2.7711,-1.57:2.6796,-1.5274:2.5862,-1.4847:2.4921,-1.4463:2.3972,-1.4058:2.3062,-1.3631:2.2166,-1.3247:2.1291,-1.2842:2.0373,-1.2394:1.9453,-1.1626:1.773,-1.1156:1.6778,-1.0687:1.5859,-1.0218:1.4971,-0.9748:1.408,-0.9279:1.3182,-0.8767:1.2253,-0.8212:1.1378,-0.7636:1.0415,-0.706:0.9476,-0.6362:0.8497,-0.4967:0.6576,-0.4244:0.5773,-0.3348:0.5016,-0.2452:0.4289,-0.1556:0.3691,-0.0724:0.3253,0.0726:0.2619,0.2668:0.2041,0.3564:0.1949},
{-2.3572:3.3128,-2.2676:3.2733,-2.178:3.2272,-2.0884:3.1714,-1.9988:3.1031,-1.9135:3.0215,-1.8388:2.9373,-1.7748:2.8494,-1.7194:2.7605,-1.6724:2.6715,-1.6241:2.5728,-1.5743:2.4851,-1.5274:2.3904,-1.4847:2.2989,-1.442:2.2075,-1.3994:2.1177,-1.3588:2.0313,-1.3183:1.9439,-1.2756:1.849,-1.2308:1.7641,-1.1839:1.6714,-1.137:1.5795,-1.09:1.4886,-1.041:1.3976,-0.9898:1.3064,-0.9364:1.2113,-0.8788:1.1225,-0.8191:1.0303,-0.753:0.9347,-0.6826:0.8459,-0.625:0.7714,-0.5156:0.6613,-0.3987:0.5445,-0.2623:0.4375,-0.1727:0.3728,-0.0831:0.3243,-0.0298:0.3003,0.114:0.2431,0.2668:0.2036,0.3564:0.1979},
]

PROVIA100F_SENS = [  # Fuji Provia 100F
{571.53:-0.5466,576.93:-0.454,581.1:-0.3572,587.73:-0.1152,594.85:0.1483,597.91:0.2525,602.58:0.3413,609.94:0.4228,616.56:0.5129,626.13:0.6936,633.99:0.8713,637.73:0.954,640.61:0.9926,644.05:0.9896,649.14:0.9026,658.4:0.4271,665.52:-0.1765,667.91:-0.4032,671.04:-0.587},
{475.46:-0.6097,481.35:-0.4491,488.47:-0.2163,495.03:-0.0012,499.69:0.1207,511.17:0.3627,524.29:0.5968,533.13:0.7212,538.83:0.7929,542.76:0.8082,547.85:0.7978,554.6:0.7647,559.82:0.7414,565.34:0.7439,570.55:0.7702,574.23:0.7917,579.14:0.7825,582.45:0.7151,586.5:0.5251,591.04:0.1299,594.72:-0.2531,597.61:-0.6134},
{388.65:-0.8536,394.72:-0.2561,402.21:0.3811,406.13:0.712,409.2:0.8192,414.23:0.9007,420.86:0.9436,426.99:0.9485,435.28:0.962,442.45:0.9988,448.77:1.0551,455.15:1.0809,461.35:1.0613,470.92:0.8744,478.83:0.5527,486.01:0.1513,492.39:-0.201,497.55:-0.5043,501.23:-0.6605},
]
PROVIA100F_CURVES = [
{-3.3819:3.289,-3.1206:3.2916,-2.8652:3.2832,-2.6506:3.2438,-2.4426:3.1769,-2.2662:3.0781,-2.0849:2.9257,-1.9434:2.7206,-1.7072:2.2468,-1.4526:1.758,-1.2504:1.403,-1.0291:1.0288,-0.8087:0.7065,-0.5458:0.4018,-0.3777:0.2528,-0.213:0.1666,-0.0383:0.1155,0.1448:0.0854,0.3236:0.0804,0.827:0.0812},
{-3.3827:3.4255,-3.1456:3.4255,-2.8003:3.4255,-2.609:3.4037,-2.4551:3.3535,-2.2804:3.2564,-2.1356:3.1258,-2.0125:2.94,-1.8794:2.6872,-1.7587:2.436,-1.599:2.0928,-1.4642:1.7906,-1.2155:1.3394,-0.9617:0.9208,-0.6689:0.5374,-0.475:0.3282,-0.3844:0.2587,-0.2879:0.2009,-0.1547:0.1498,-0.03:0.1122,0.1032:0.0887,0.2529:0.082,0.49:0.082,0.827:0.082},
{-3.3852:3.3359,-3:3.3368,-2.792:3.325,-2.5507:3.2782,-2.426:3.2313,-2.2779:3.1317,-2.1689:3.017,-2.0033:2.8194,-1.8702:2.5683,-1.678:2.1882,-1.4908:1.8283,-1.2779:1.4482,-1.0349:1.0397,-0.8103:0.7049,-0.6522:0.5165,-0.4584:0.3148,-0.2754:0.1967,-0.0549:0.1197,0.1572:0.0837,0.411:0.082,0.6439:0.0837,0.827:0.0837},
]

EKTACHROME100D_SENS = [  # Kodak Ektachrome 100D
{554.09:-1.022,564.36:-0.9702,573.35:-0.6981,588.64:0.438,599.38:0.6926,631.6:1.1752,641.63:1.3438,647.12:1.4066,652.14:1.3945,656.46:1.2226,661.25:0.7135,669.53:0.0083,684.59:-0.9967},
{472.84:-0.5647,483.11:-0.0413,493.85:0.3939,500.04:0.5295,530.16:0.9934,543.46:1.1873,548.83:1.1961,555.25:1.151,564.59:1.2083,568.33:1.1829,573.46:1.2182,576.97:1.1598,581.87:0.6915,590.51:-0.0028,600.31:-0.6088,604.51:-1.0022},
{394.75:0.5262,398.02:0.8127,404.44:1.0937,410.97:1.3008,419.61:1.4375,427.08:1.5047,430.35:1.4848,434.44:1.3747,439.11:1.3339,446.11:1.3328,456.38:1.3736,467.94:1.2479,474.94:0.7631,481.71:0.3609,487.2:0.1515,498.4:-0.1041,505.29:-0.2782,514.05:-0.5372,519.65:-0.7686},
]
EKTACHROME100D_CURVES = [
{-2.7798:3.2106,-2.6443:3.2083,-2.5027:3.1863,-2.398:3.1532,-2.3094:3.1028,-2.1973:3.0302,-2.1087:2.9527,-2.0225:2.8481,-1.908:2.6943,-1.8133:2.5527,-1.668:2.3004,-1.4231:1.8757,-1.2483:1.5864,-1.0415:1.254,-0.8224:0.9525,-0.5823:0.6941,-0.3718:0.5022,-0.2142:0.3853,-0.1009:0.3177,0.0186:0.255},
{-2.7784:3.6098,-2.6935:3.6049,-2.5703:3.5804,-2.4595:3.5424,-2.3314:3.4686,-2.1948:3.3653,-2.0778:3.2115,-1.935:2.9727,-1.8267:2.7498,-1.6434:2.3546,-1.4563:1.9187,-1.3492:1.691,-1.2163:1.4324,-1.0957:1.2232,-0.9406:0.9955,-0.7892:0.7924,-0.6279:0.6201,-0.4691:0.4688,-0.3324:0.3704,-0.1674:0.2856,0.0161:0.2168},
{-2.7685:3.8081,-2.638:3.7713,-2.5309:3.7185,-2.4201:3.6447,-2.3265:3.5598,-2.2551:3.465,-2.1332:3.2853,-1.9154:2.8421,-1.7259:2.3927,-1.524:1.9002,-1.3234:1.4693,-1.1487:1.1738,-0.9394:0.8661,-0.7757:0.6729,-0.5971:0.4859,-0.4223:0.3555,-0.2438:0.2646,0.0148:0.207},
]

# =========================================================================
# Film data — Kodak Portra 400, Kodak Ektar 100, Kodak Gold 200, Kodak
# Ultramax 400, Fuji Superia Reala, Fuji Superia X-tra 400 (camera color
# *negative* stocks, 3 dye layers each, same
# [red/cyan, green/magenta, blue/yellow] layer order as VELVIA_SENS/
# VELVIA_CURVES -- confirmed against each film's raw source JSON directly
# (film_paper_filter_data/films/color/negative/*.json, same
# spectral_film_lut-derived pool the reversal films above came from, Status
# M density, exposure_base 10 i.e. log10 H matching every other curve dict
# in this file) by checking each layer's own peak sensitivity wavelength,
# not assumed. Unlike every reversal film above, density here *rises* with
# exposure (increasing=True), the same direction as TRIX_DEV7 and every
# PAPER_LADDER paper -- these are genuine camera negatives, not reversal
# (slide) stock, so they print straight onto a real print paper with a
# 2-stage cascade (build_negative_cascade() below), never through
# INTERNEGATIVE_II_CURVES -- see the COLOR_FILMS-vs-negative-films split in
# main() and CLAUDE.md's note on why negative-film support must stay a
# separate lineup rather than folding into COLOR_FILMS.
#
# Two of the eighteen digitized characteristic-curve layers have a single
# leading Dmin-plateau digitization-noise sample (EKTAR100_CURVES layer 2,
# SUPERIA_REALA_CURVES layer 2) -- the same kind of noise Kodak Supra
# Endura and Fuji Provia 100F needed _detect_lead_noise_start() for;
# handled automatically the same way, no hand-tuned start index needed
# here either.
#
# SUPERIA_XTRA400_SENS layer 1 (green-sensitive) has one raw source point
# dropped: the source JSON has a sample at 565.2822nm reading 1.0051, a
# ~1.5-log-unit dive-and-recovery between neighbors at 560.2424 (2.4959)
# and 567.6539 (2.4319) that are themselves smooth and consistent with
# each other -- a single bad digitization sample, not a real spectral
# feature (unlike, say, a reversal dye layer's genuine solarization tail,
# which spans many consecutive points). Confirmed by checking neighbor
# consistency before dropping it, not assumed.
# =========================================================================
PORTRA400_SENS = [
{492.535:0.4215,498.661:0.5118,504.788:0.5997,511.297:0.69,518.955:0.7689,527.379:0.8143,535.802:0.8003,544.226:0.7789,551.118:0.8224,555.713:0.917,559.542:1.0145,563.37:1.1103,566.817:1.2003,569.88:1.2958,572.56:1.3949,574.857:1.4897,577.155:1.5872,579.452:1.6779,582.132:1.7761,585.196:1.8627,588.259:1.969,592.853:2.07,599.363:2.1563,606.255:2.2479,613.913:2.3316,622.336:2.387,630.76:2.4032,639.184:2.4221,645.31:2.532,651.436:2.6026,657.945:2.5492,661.391:2.4307,662.157:2.3508,663.689:2.2574,665.22:2.1376,666.752:2.0076,668.284:1.8735,669.815:1.7344,671.347:1.5892,672.878:1.442,674.41:1.2846,675.941:1.1201,677.473:0.9576,679.005:0.8046,679.77:0.7166},
{390.685:1.2694,393.748:1.3658,396.812:1.4633,402.555:1.548,410.979:1.5266,419.402:1.4613,427.826:1.4033,436.25:1.3527,444.673:1.3243,453.097:1.3254,461.521:1.3453,469.179:1.3868,474.539:1.4873,478.368:1.5888,481.814:1.6816,484.877:1.7608,488.706:1.8512,493.684:1.9481,500.576:2.0414,509:2.113,517.423:2.1857,525.847:2.2674,533.122:2.3544,539.631:2.4429,547.289:2.5214,555.713:2.51,563.753:2.4284,571.028:2.3413,576.772:2.2635,580.218:2.1721,582.515:2.0651,584.94:1.9366,585.578:1.8404,587.876:1.707,589.407:1.5943,590.939:1.4724,592.471:1.3475,594.002:1.2115,595.534:1.0693,597.065:0.917,598.597:0.7809,599.745:0.6895},
{380.347:1.7591,382.644:1.8593,384.942:1.9676,387.239:2.0705,389.537:2.1721,391.834:2.2736,394.131:2.3711,396.429:2.4578,399.875:2.5559,406.384:2.6037,414.808:2.5805,423.231:2.5576,431.655:2.5646,440.079:2.5524,448.502:2.5162,456.926:2.521,465.35:2.5738,471.859:2.5532,475.688:2.4645,478.368:2.3833,480.665:2.2885,482.58:2.1761,483.728:2.0726,485.26:1.967,487.43:1.8505,488.323:1.751,490.161:1.6457,492.918:1.5168,495.215:1.4139,497.513:1.3056,499.81:1.2054,502.108:1.1038,504.405:1.0104,506.702:0.917,509:0.8168,512.139:0.6807,515.126:0.523,517.423:0.4052,519.721:0.3037},
]
PORTRA400_CURVES = [
{-3.386:0.2172,-3.253:0.2218,-3.119:0.2264,-2.986:0.2316,-2.853:0.2406,-2.72:0.2625,-2.587:0.3031,-2.453:0.3594,-2.32:0.4267,-2.187:0.4964,-2.054:0.5643,-1.92:0.6331,-1.787:0.7024,-1.654:0.7732,-1.521:0.8425,-1.388:0.9144,-1.254:0.9867,-1.121:1.0587,-0.988:1.1318,-0.855:1.2052,-0.722:1.2794,-0.588:1.3545,-0.455:1.4291,-0.322:1.505,-0.189:1.5809,-0.055:1.6564,0.078:1.7327,0.211:1.8094,0.344:1.8866,0.477:1.9643,0.556:2.0108},
{-3.386:0.6434,-3.253:0.6482,-3.119:0.6523,-2.986:0.6584,-2.853:0.669,-2.72:0.6951,-2.587:0.7393,-2.453:0.7995,-2.32:0.8708,-2.187:0.9463,-2.054:1.0211,-1.92:1.0951,-1.787:1.1698,-1.654:1.244,-1.521:1.3178,-1.388:1.3912,-1.254:1.4656,-1.121:1.5398,-0.988:1.613,-0.855:1.6864,-0.722:1.7592,-0.588:1.833,-0.455:1.9066,-0.322:1.9802,-0.189:2.0519,-0.055:2.1234,0.078:2.1966,0.211:2.2695,0.344:2.3417,0.477:2.4147,0.556:2.4578},
{-3.377:0.866,-3.244:0.8704,-3.111:0.8762,-2.978:0.8923,-2.845:0.9244,-2.711:0.9788,-2.578:1.0495,-2.445:1.1295,-2.312:1.2129,-2.179:1.2959,-2.045:1.3797,-1.912:1.4633,-1.779:1.5474,-1.646:1.6318,-1.512:1.716,-1.379:1.8007,-1.246:1.8849,-1.113:1.9702,-0.98:2.0554,-0.846:2.1409,-0.713:2.2264,-0.58:2.3117,-0.447:2.3971,-0.314:2.4824,-0.18:2.5685,-0.047:2.6552,0.086:2.7413,0.219:2.8275,0.352:2.9142,0.486:3.0015,0.561:3.0499},
]

EKTAR100_SENS = [
{554.759:0.1914,559.38:0.2841,562.257:0.3312,565.135:0.3588,569.32:0.3485,572.546:0.4793,581.178:1.1263,586.323:1.4135,590.596:1.5207,596.438:1.6176,603.413:1.7304,606.814:1.7595,610.65:1.7657,614.923:1.7588,626.52:1.8107,631.316:1.8418,635.85:1.9062,645.267:1.994,648.667:2.0397,653.027:2.0536,656.428:2.0231,663.926:1.8183,667.85:1.5795,681.801:1.0017,687.992:0.8045,692.526:0.4966,694.968:0.2993},
{394.93:0.8391,399.639:0.9346,404.435:0.9692,408.882:0.9567,415.857:0.9118,419.955:0.8599,427.192:0.7976,432.25:0.7491,437.133:0.6813,443.062:0.619,450.299:0.6149,455.531:0.6073,464.686:0.6107,468.61:0.6038,473.406:0.6523,478.55:0.7893,485.962:1.1007,493.897:1.2854,501.744:1.3941,510.551:1.4612,518.224:1.5436,527.815:1.6716,535.837:1.7553,540.546:1.7927,544.208:1.8356,549.701:1.8217,555.543:1.7754,559.729:1.7788,564.263:1.7539,567.227:1.7076,570.889:1.657,574.203:1.6418,578.039:1.5138,582.486:1.1643,587.021:0.6869,590.072:0.3768},
{379.584:1.0931,385.339:1.3235,390.135:1.5622,394.494:1.7802,399.029:1.9207,403.388:2.0072,406.44:2.0383,410.8:2.0459,415.857:2.0293,419.083:2.01,423.705:2.0224,430.68:2.0432,435.912:2.0639,438.877:2.084,442.539:2.0681,447.77:2.0266,453.525:2.0176,460.85:2.0702,465.558:2.1193,468.348:2.1491,471.662:2.1401,474.888:2.0895,476.894:1.9864,483.608:1.4619,489.275:0.8529,494.856:0.3561},
]
EKTAR100_CURVES = [
{-2.837:0.2103,-2.424:0.225,-2.281:0.2364,-2.123:0.2634,-2.021:0.2911,-1.929:0.3246,-1.748:0.4087,-1.495:0.5386,-0.965:0.8546,-0.341:1.2091,0.306:1.5545,0.837:1.8052,1.159:1.9343},
{-2.838:0.6366,-2.426:0.6431,-2.255:0.6611,-2.107:0.6905,-1.974:0.7313,-1.78:0.8252,-1.341:1.0866,-0.519:1.5643,0.103:1.9073,0.705:2.2029,1.153:2.4104},
{-2.835:0.8473,-2.725:0.8612,-2.623:0.871,-2.5:0.8702,-2.368:0.8832,-2.191:0.9249,-1.968:1.0384,-1.784:1.1552,-1.556:1.2989,-1.472:1.365,-1.385:1.4238,-1.085:1.6182,-0.545:1.9726,-0.1:2.2756,0.333:2.5394,0.773:2.7991,1.158:3.067},
]

GOLD200_SENS = [
{391.296:0.3886,394.173:0.4731,400.525:0.6223,408.557:0.5588,416.468:0.454,423.66:0.3463,430.852:0.2366,439.003:0.1269,447.803:0.0405,464.518:0.0,485.53:0.0101,492.703:0.1146,515.718:0.3548,525.786:0.4338,535.855:0.5001,542.808:0.5554,558.87:0.7548,567.26:0.8513,577.089:1.0979,580.206:1.1551,590.035:1.3832,594.35:1.4501,608.734:1.6179,617.365:1.7289,625.755:1.8296,632.708:1.9204,642.057:2.0959,649.618:2.1978,657.88:2.1908,662.434:2.0966,664.832:1.9187,666.803:1.804,669.094:1.6801,671.118:1.5661,673.462:1.453,676.034:1.3311,678.497:1.2125,682.332:1.1002,687.367:0.9018,689.764:0.8217},
{380.987:0.5871,384.823:0.7093,388.179:0.8258,391.536:0.9299,399.57:1.2203,408.796:1.2238,418.865:1.1395,426.537:1.0691,441.4:0.9324,461.058:0.9208,469.209:0.9307,478.079:1.107,491.984:1.5168,494.621:1.5729,510.443:1.7562,519.314:1.8572,525.067:1.9323,534.248:2.093,541.129:2.1926,549.522:2.2363,558.39:2.1802,564.863:2.0739,570.617:1.8932,574.452:1.7795,577.329:1.6681,579.213:1.5606,581.036:1.4334,585.24:1.1066,587.398:0.9079,588.871:0.7935,590.72:0.6665,592.227:0.5461,594.111:0.417,595.857:0.3004},
{371.158:0.9047,375.569:1.0102,379.07:1.1589,382.426:1.2786,385.542:1.3904,388.419:1.4992,391.775:1.6148,393.813:1.7173,396.536:1.821,410.235:2.1099,420.304:2.0915,430.373:2.0943,439.482:2.1499,459.38:2.1796,468.73:2.3224,475.682:2.2364,479.218:2.1053,479.278:2.0478,481.915:1.8552,483.388:1.7315,484.312:1.6084,485.331:1.4935,487.429:1.1687,488.748:1.091,491.265:0.8654,492.763:0.756,495.041:0.6473,505.649:0.1463,509.005:0.0556},
]
GOLD200_CURVES = [
{-2.902:0.256,-2.773:0.2617,-2.644:0.271,-2.515:0.2885,-2.385:0.3159,-2.256:0.355,-2.127:0.4047,-1.997:0.4638,-1.868:0.5297,-1.739:0.599,-1.609:0.6683,-1.48:0.7379,-1.351:0.8072,-1.222:0.8767,-1.092:0.9465,-0.963:1.017,-0.834:1.0881,-0.704:1.1592,-0.575:1.2308,-0.446:1.3028,-0.316:1.3751,-0.187:1.4475,-0.058:1.5176,0.072:1.5769,0.201:1.6278,0.33:1.6711,0.46:1.7109,0.589:1.7491,0.718:1.7876,0.823:1.8196},
{-2.894:0.6617,-2.765:0.6685,-2.635:0.6816,-2.506:0.7062,-2.377:0.7421,-2.248:0.7898,-2.118:0.8461,-1.989:0.9075,-1.86:0.9757,-1.73:1.0488,-1.601:1.1224,-1.472:1.1963,-1.342:1.2701,-1.213:1.3434,-1.084:1.4173,-0.955:1.4911,-0.825:1.5643,-0.696:1.6377,-0.567:1.7108,-0.437:1.7833,-0.308:1.8557,-0.179:1.927,-0.049:1.9953,0.08:2.0566,0.209:2.1069,0.339:2.1484,0.468:2.1865,0.597:2.224,0.727:2.2626,0.827:2.2923},
{-2.677:0.9637,-2.548:0.9757,-2.419:1.0049,-2.289:1.0472,-2.16:1.1019,-2.031:1.1688,-1.901:1.2465,-1.772:1.3244,-1.643:1.4029,-1.514:1.4837,-1.384:1.5686,-1.255:1.6616,-1.125:1.7488,-0.996:1.8158,-0.867:1.8863,-0.738:1.9623,-0.608:2.0427,-0.479:2.1247,-0.35:2.2063,-0.22:2.2874,-0.091:2.3656,0.038:2.4381,0.168:2.4995,0.297:2.5496,0.426:2.5942,0.555:2.6371,0.685:2.6821,0.806:2.724},
]

SUPERIA_REALA_SENS = [
{557.705:1.0543,560.761:1.1395,563.582:1.2203,566.403:1.3003,569.224:1.3799,572.044:1.4591,574.16:1.5099,579.86:1.6827,583.563:1.7667,586.854:1.8502,590.144:1.9252,596.726:2.0748,609.89:2.2588,617.177:2.3195,624.699:2.356,632.221:2.3596,639.274:2.3104,644.445:2.2348,647.971:2.1579,651.027:2.0782,654.553:1.9259,656.621:1.8266,657.844:1.7444,659.066:1.6578,660.429:1.5659,662.008:1.4675,663.485:1.3767,665.013:1.3062,667.011:1.224,669.362:1.1379},
{465.324:0.7422,467.675:0.8273,469.791:0.9134,471.671:0.9897,473.551:1.0647,475.667:1.1448,477.783:1.2274,480.133:1.3168,482.484:1.4052,484.835:1.4923,487.185:1.5793,489.536:1.6634,492.122:1.7511,496.823:1.919,499.174:1.9931,505.05:2.1586,508.577:2.2416,513.513:2.3197,520.33:2.3786,527.852:2.4048,535.374:2.3927,542.896:2.346,549.713:2.2795,555.355:2.2067,560.056:2.1315,564.287:2.053,568.048:1.9573,570.869:1.8786,572.985:1.8015,574.865:1.7235,576.276:1.6727,579.802:1.4927,581.917:1.3948,583.798:1.3026,585.678:1.211,587.794:1.1262,589.909:1.075},
{390.573:2.2987,394.569:2.3832,398.565:2.4476,406.087:2.5316,413.61:2.5746,421.132:2.5737,428.654:2.5554,436.176:2.5495,443.698:2.5688,451.22:2.6158,458.742:2.6494,466.264:2.6566,473.551:2.6178,478.723:2.5369,481.544:2.4584,483.659:2.3803,485.54:2.2951,487.421:2.2011,489.183:2.0995,490.241:2.0498,492.592:1.9375,496.823:1.7322,498.704:1.6821,505.286:1.4201,507.871:1.3371,510.222:1.2553,512.573:1.173,514.923:1.0988},
]
SUPERIA_REALA_CURVES = [
{-3.581:0.2932,-3.462:0.2932,-3.337:0.3057,-3.216:0.3128,-3.094:0.321,-2.972:0.3324,-2.85:0.3457,-2.728:0.3637,-2.607:0.3831,-2.485:0.4002,-2.363:0.4233,-2.241:0.4508,-1.998:0.5226,-1.876:0.5771,-1.754:0.645,-1.632:0.7161,-1.51:0.7881,-1.389:0.8719,-1.145:1.0305,-0.901:1.1978,-0.78:1.2804,-0.658:1.362,-0.534:1.4404,-0.414:1.5216,-0.292:1.5994,-0.171:1.6858,-0.046:1.7653,0.073:1.8434,0.317:2.0},
{-3.57:0.5039,-3.448:0.5076,-3.326:0.5128,-3.204:0.5221,-2.961:0.5548,-2.839:0.5813,-2.717:0.6081,-2.595:0.6344,-2.473:0.6632,-2.352:0.6971,-2.23:0.7403,-2.108:0.7928,-1.986:0.856,-1.864:0.9166,-1.742:0.9911,-1.621:1.0642,-1.499:1.1474,-1.377:1.2288,-1.255:1.3095,-1.133:1.3906,-1.012:1.4712,-0.89:1.5505,-0.768:1.6356,-0.646:1.7152,-0.523:1.7916,-0.403:1.871,-0.281:1.9566,-0.159:2.0285,-0.037:2.1122,0.085:2.193,0.206:2.2745,0.287:2.3267},
{-3.581:0.9752,-3.459:0.9749,-3.337:0.9752,-3.216:0.979,-3.094:0.9812,-2.972:0.9851,-2.85:0.992,-2.728:1.0041,-2.607:1.0171,-2.485:1.0403,-2.363:1.0765,-2.241:1.1274,-2.119:1.1819,-1.998:1.2369,-1.876:1.2975,-1.754:1.3623,-1.632:1.4343,-1.51:1.5087,-1.389:1.5878,-1.267:1.67,-1.145:1.7504,-1.022:1.8307,-0.901:1.913,-0.78:1.9915,-0.658:2.0704,-0.534:2.1525,-0.414:2.2394,-0.292:2.3239,-0.171:2.4125,-0.049:2.4946,0.073:2.5768,0.195:2.6601,0.276:2.7147},
]

ULTRAMAX400_SENS = [
{487.614:0.2352,494.195:0.352,504.209:0.4907,515.104:0.6582,524.524:0.7858,536.542:0.8244,545.87:0.8644,555.999:1.0746,564.582:1.2233,571.163:1.324,574.311:1.46,577.458:1.5967,580.606:1.7204,588.474:1.9717,595.961:2.0859,609.218:2.2313,621.236:2.3445,631.25:2.4563,639.834:2.5931,649.992:2.6855,659.291:2.6474,663.869:2.5053,667.016:2.3567,669.877:2.214,673.025:2.0889,678.461:1.8388,681.609:1.706,685.042:1.5795,688.19:1.4583,690.707:1.3221,692.195:1.2015,693.912:1.0713,695.629:0.8975,697.346:0.7457,699.062:0.599,700.092:0.4685},
{390.617:0.8417,394.05:0.9675,401.919:1.1163,413.507:1.0869,423.587:1.0197,437.542:0.9105,450.418:0.8939,461.576:0.9461,470.669:0.9938,477.099:1.1452,479.603:1.2811,481.605:1.4252,483.404:1.5607,485.897:1.7181,492.478:1.9378,499.918:2.0863,510.504:2.2105,520.233:2.335,529.389:2.4676,538.545:2.5894,549.616:2.6678,560.29:2.6114,570.019:2.4591,576.6:2.3513,580.033:2.2067,586.328:1.7044,587.963:1.5391,589.094:1.3877,590.239:1.2582,591.478:1.1169,593.114:0.9198,594.34:0.7794,595.811:0.631,597.344:0.4687},
{366.868:1.2945,371.446:1.4383,374.88:1.5754,378.599:1.7069,382.891:1.8328,391.253:2.1797,393.478:2.3212,396.339:2.4399,412.363:2.6647,424.38:2.6414,436.397:2.6484,445.668:2.6238,460.432:2.5963,472.838:2.6894,479.145:2.4317,481.36:2.288,483.567:2.1565,494.958:1.5021,505.926:0.7958,515.369:0.3951,518.802:0.2554,521.949:0.1401},
]
ULTRAMAX400_CURVES = [
{-3.373:0.2856,-3.243:0.2856,-3.112:0.2886,-2.982:0.3016,-2.851:0.3256,-2.721:0.361,-2.59:0.4073,-2.459:0.4548,-2.329:0.5119,-2.198:0.5733,-2.068:0.6378,-1.937:0.7046,-1.806:0.77,-1.676:0.8343,-1.545:0.9008,-1.415:0.9683,-1.284:1.038,-1.154:1.1053,-1.023:1.1738,-0.892:1.2414,-0.762:1.3089,-0.631:1.3768,-0.501:1.4456,-0.37:1.514,-0.239:1.5807,-0.109:1.6456,0.022:1.7084,0.152:1.7693,0.283:1.83,0.413:1.882,0.519:1.9163},
{-3.373:0.6928,-3.243:0.6936,-3.112:0.6993,-2.982:0.7154,-2.851:0.7452,-2.721:0.7865,-2.59:0.8382,-2.459:0.8973,-2.329:0.9628,-2.198:1.0342,-2.068:1.1063,-1.937:1.1794,-1.806:1.2513,-1.676:1.3201,-1.545:1.389,-1.415:1.4582,-1.284:1.5281,-1.154:1.5987,-1.023:1.6695,-0.892:1.7402,-0.762:1.8111,-0.631:1.8821,-0.501:1.9539,-0.37:2.0243,-0.239:2.0927,-0.109:2.1561,0.022:2.2171,0.152:2.2757,0.283:2.3328,0.413:2.3852,0.519:2.4226},
{-3.373:0.9782,-3.243:0.9791,-3.112:0.9846,-2.982:1.0003,-2.851:1.0305,-2.721:1.0725,-2.59:1.1257,-2.459:1.1875,-2.329:1.2558,-2.198:1.3276,-2.068:1.4023,-1.937:1.4786,-1.806:1.5543,-1.676:1.6295,-1.545:1.7069,-1.415:1.7854,-1.284:1.8644,-1.154:1.9445,-1.023:2.0244,-0.892:2.1031,-0.762:2.1815,-0.631:2.2607,-0.501:2.3397,-0.37:2.4173,-0.239:2.4953,-0.109:2.5765,0.022:2.6577,0.152:2.7378,0.283:2.8172,0.413:2.8923,0.522:2.9473},
]

SUPERIA_XTRA400_SENS = [
{565.579:1.0349,567.95:1.1481,570.322:1.2672,572.694:1.3842,575.066:1.4891,577.734:1.5895,579.809:1.6669,586.331:1.8816,591.371:1.9871,597.3:2.0842,605.304:2.1787,614.791:2.2353,624.278:2.2597,633.765:2.2736,643.252:2.2738,650.96:2.2174,655.11:2.1147,657.482:2.0112,659.557:1.9017,661.336:1.8024,663.115:1.6932,664.893:1.585,666.672:1.4698,668.451:1.3516,670.23:1.2315,672.008:1.1133,674.084:1.0014,676.159:0.9237},
{464.189:0.7922,466.561:0.9046,468.932:1.0066,471.6:1.107,474.565:1.2095,477.826:1.3089,481.384:1.4112,485.238:1.5098,488.202:1.579,501.247:1.8103,509.548:1.9071,518.145:1.9921,524.963:2.093,530.3:2.1913,535.933:2.2895,542.455:2.3872,550.756:2.4736,560.242:2.4959,567.654:2.4319,571.804:2.327,574.176:2.2204,575.955:2.1171,577.734:2.0149,579.809:1.8935,585.145:1.5413,587.22:1.4162,588.999:1.302,590.778:1.1868,592.557:1.0726,594.336:0.9604,596.707:0.8508,598.782:0.7951},
{401.932:2.0167,404.304:2.1258,407.565:2.2276,414.383:2.3321,423.87:2.3809,433.357:2.3893,442.844:2.3917,452.33:2.4133,460.928:2.4809,469.525:2.5726,477.53:2.541,482.273:2.4361,484.941:2.3336,487.016:2.2323,488.795:2.1251,490.574:2.0,492.204:1.8674,495.317:1.5694,497.096:1.4509,498.875:1.3367,500.95:1.2263,503.322:1.1205,505.693:1.0349},
]
SUPERIA_XTRA400_CURVES = [
{-3.545:0.1397,-3.381:0.1518,-3.217:0.1744,-3.053:0.2059,-2.889:0.2469,-2.725:0.298,-2.561:0.355,-2.397:0.4233,-2.233:0.5101,-2.069:0.6041,-1.905:0.7011,-1.741:0.7995,-1.577:0.9027,-1.413:1.0039,-1.25:1.1004,-1.085:1.2007,-0.922:1.3004,-0.758:1.4009,-0.594:1.5014,-0.43:1.6023,-0.266:1.7035,-0.102:1.8053,0.062:1.9077,0.226:2.0106,0.32:2.0693},
{-3.545:0.4542,-3.381:0.4613,-3.217:0.4725,-3.053:0.493,-2.889:0.5264,-2.725:0.5799,-2.561:0.6546,-2.397:0.7508,-2.233:0.8547,-2.069:0.9611,-1.905:1.0683,-1.741:1.1757,-1.577:1.2843,-1.413:1.3927,-1.25:1.5016,-1.085:1.6101,-0.922:1.7199,-0.758:1.8299,-0.594:1.9401,-0.43:2.0505,-0.266:2.1623,-0.102:2.2751,0.062:2.3877,0.218:2.4969},
{-3.553:0.727,-3.389:0.7339,-3.225:0.7424,-3.061:0.7555,-2.897:0.7786,-2.733:0.8222,-2.569:0.8944,-2.405:0.9926,-2.241:1.1026,-2.077:1.218,-1.913:1.3353,-1.749:1.4546,-1.585:1.5723,-1.421:1.6879,-1.257:1.8021,-1.093:1.9159,-0.929:2.0287,-0.765:2.1415,-0.602:2.2535,-0.438:2.3657,-0.274:2.4791,-0.11:2.5926,0.054:2.7071,0.191:2.804},
]

# =========================================================================
# Wratten filter transmission (%), Kodak B-3
# =========================================================================
FILTERS = {
"Yellow8":{400:0,410:0,420:0,430:0,440:0,450:0,460:0.25,470:5.5,480:19,490:41,500:63.5,510:78,520:84.1,530:86.5,540:87.7,550:88.4,560:88.8,570:89.2,580:89.5,590:89.9,600:90.1,610:90.3,620:90.5,630:90.7,640:90.9,650:91.1,660:91.1,670:91.2,680:91.3,690:91.4,700:91.5},
"Orange21":{400:0,410:0,420:0,430:0,440:0,450:0,460:0,470:0,480:0,490:0,500:0,510:0,520:0,530:0,540:2.5,550:29,560:65,570:80.6,580:85.4,590:87.3,600:88.1,610:88.7,620:89,630:89.5,640:89.9,650:90.2,660:90.4,670:90.5,680:90.5,690:90.6,700:90.6},
"Red25":{400:0,410:0,420:0,430:0,440:0,450:0,460:0,470:0,480:0,490:0,500:0,510:0,520:0,530:0,540:0,550:0,560:0,570:0,580:0,590:12.6,600:50,610:75,620:82.6,630:85.5,640:86.7,650:87.6,660:88.2,670:88.5,680:89,690:89.3,700:89.5},
"Green58":{400:0,410:0,420:0,430:0,440:0,450:0,460:0,470:0.23,480:1.38,490:4.9,500:17.7,510:38.8,520:52.2,530:53.6,540:47.6,550:38.4,560:27.8,570:17.4,580:9,590:3.5,600:1.5,610:0.41,620:0,630:0,640:0,650:0,660:0,670:0,680:0,690:0,700:0.53},
"Blue47":{400:9.7,410:21.8,420:37.8,430:47.8,440:50.3,450:48.2,460:42.8,470:35.7,480:27.1,490:18.2,500:10.2,510:4.3,520:1.2,530:0,540:0,550:0,560:0,570:0,580:0,590:0,600:0,610:0,620:0,630:0,640:0,650:0,660:0,670:0,680:0,690:0,700:0},
}

# =========================================================================
# Look definitions
# =========================================================================
# Tri-X only -- its 6-grade Polymax ladder is untouched by this change.
LOOKS = [("ExtraSoft","0"),("Soft","1"),("Normal","2"),("Punchy","3"),("ExtraPunchy","4"),("Hard","5")]
FILTER_ORDER = ["NoFilter","Yellow8","Orange21","Red25","Green58","Blue47"]
GREY = 0.18

# =========================================================================
# Spectral reconstruction (Jakob & Hanika 2019) -- see Ticket 16
# (tasks/16-fixed-rgb-weights-no-spectral-reconstruction.md) and Ticket 21
# (tasks/21-trix-geometric-mean-not-physical-model.md)
# =========================================================================
# Every color film's per-layer exposure used to come from a FIXED per-channel
# weight triple, computed once by integrating a whole spectral sensitivity
# curve against D65 and the colour space's own RGB primaries
# (`layer_weights()`, now removed) -- every pixel's exposure was then just a
# plain `R*wr + G*wg + B*wb` dot product against that fixed triple. That is
# mathematically equivalent to assuming every photographed colour is exactly
# a linear-light mixture of the three RGB primaries' own spectral power
# distributions -- real reflectance spectra are not that, and a real film's
# spectral sensitivity is not colorimetric, so two real colours that are
# metamers under the CIE 1931 observer (same RGB triple) can and do expose
# real film differently. Tri-X's own analogous fixed-weight function,
# `_weights()`, was believed exempt from this ("B&W has no per-channel colour
# to get wrong the same way") -- Ticket 21 found that reasoning conflates
# hue-contamination (a color-only symptom) with the underlying cause (film
# sensitivity isn't colorimetric, full stop): a saturated red rendered
# *paper black* under `_weights()` + the geometric mean it fed, when real
# panchromatic Tri-X's actual spectral sensitivity (strong through ~640nm)
# exposes a red flower *brighter than grey*. `_weights()` is gone; every
# color film below AND Tri-X (via `trix_exposure_grid()`) now reconstructs a
# real, physically-plausible reflectance spectrum per LUT grid point (Jakob &
# Hanika 2019, "A Low-Dimensional Function Space for Efficient Spectral
# Upsampling," Computer Graphics Forum 38(2), 147-155) and integrates each
# layer's (or Tri-X's one panchromatic curve's) own real digitized
# sensitivity against THAT instead of against the primaries themselves. See
# papers/spectral_upsampling/README.md for the full research trail
# (including the reference C++ implementation and the independent Python
# port this project's own coefficient tables were fit with) and
# tools/spectral_upsample_fit/ for the offline fitting tool that produces
# spectral_upsampling_tables/<colorspace>.json -- this file only ever
# *evaluates* that baked table (stdlib json + plain arithmetic, no scipy),
# the same "fit offline, consume as data" split tools/gamma_correction_fit/
# already established for *_SPLITGAUSS_FIT.
#
# The reconstructed spectrum depends only on the LUT grid's (R,G,B)
# coordinate and the target colour space's own gamut (which baked table is
# loaded) -- NOT on which film/layer is being rendered -- so it's computed
# once per (size, colorspace) via build_spectrum_grid() and shared across
# every one of this run's color films, the same "compute once, reuse many"
# principle as DONE-05/DONE-08/DONE-11's fixes elsewhere in this file.
_SPECTRAL_TABLE_CACHE = {}
def _spectral_table(cs_name):
    """Load+cache spectral_upsampling_tables/<cs_name>.json (baked by
    tools/spectral_upsample_fit/)."""
    if cs_name not in _SPECTRAL_TABLE_CACHE:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "spectral_upsampling_tables", f"{cs_name}.json")
        with open(path) as f:
            _SPECTRAL_TABLE_CACHE[cs_name] = json.load(f)
    return _SPECTRAL_TABLE_CACHE[cs_name]

def _rgb_to_sigmoid_coeffs(table, r, g, b):
    """Jakob & Hanika (2019) coefficient lookup: largest-channel-relative
    gamut parameterization + trilinear interpolation over the baked table,
    matching tools/spectral_upsample_fit/main.py's _chroma_vector() /
    _solve_column() convention exactly (verified there against an exact
    grid-vertex round-trip, not assumed -- see that tool's own comments):
    for the largest channel `l`, the OTHER two channels normalized by it are
    stored (chroma[(l+1)%3] on the table's axis2, chroma[(l+2)%3] on axis3).
    Achromatic (r==g==b) input uses the model's own closed-form solution
    (a flat spectrum at exactly that reflectance -- see rgb2spec_fetch_mono()
    in the reference C++ implementation, papers/spectral_upsampling/README.md)
    instead of interpolating, both because it's exact and because grey is
    the one input the table's discrete chroma grid doesn't sample directly."""
    r=max(0.0,min(1.0,r)); g=max(0.0,min(1.0,g)); b=max(0.0,min(1.0,b))
    if r==g==b:
        # Closed-form flat-spectrum solution (rgb2spec_fetch_mono() in the
        # reference C++ implementation). v==0/v==1 need their own exact
        # branches (not an epsilon clamp -- an earlier version of this
        # function clamped to [1e-6, 1-1e-6] instead, which left pure black
        # reconstructing at reflectance 1e-6 instead of exactly 0, caught by
        # this project's own grey-invariant test): a large-magnitude
        # sentinel coefficient (matching the reference's +-8192, just in
        # double precision where +-1e6 already saturates the sigmoid to
        # 0.0/1.0 to float precision) reproduces exactly 0/1 through
        # _sigmoid_spectrum() instead of merely approximating it.
        v=r
        if v<=0.0: return (0.0,0.0,-1e6)
        if v>=1.0: return (0.0,0.0,1e6)
        return (0.0,0.0,(v-0.5)/math.sqrt(v*(1.0-v)))
    rgb=(r,g,b)
    vmax=max(rgb)
    if vmax<=1e-10:
        return (0.0,0.0,-8192.0)
    l=rgb.index(vmax)
    chroma=[c/vmax for c in rgb]
    y1=chroma[(l+1)%3]; y2=chroma[(l+2)%3]
    size=table["size"]; lightness=table["lightness_scale"]; coeffs=table["coefficients"]
    xg=max(0.0,min(float(size-1),y2*(size-1)))
    yg=max(0.0,min(float(size-1),y1*(size-1)))
    x0=min(int(xg),size-2); x1=x0+1; tx=xg-x0
    y0=min(int(yg),size-2); y1i=y0+1; ty=yg-y0
    lo,hi=0,size-1
    while hi-lo>1:
        m=(lo+hi)//2
        if lightness[m]<=vmax: lo=m
        else: hi=m
    zi=min(lo,size-2)
    denom=lightness[zi+1]-lightness[zi]
    tz=(vmax-lightness[zi])/denom if denom>0 else 0.0

    def at(z,y,x): return coeffs[l][z][y][x]
    c00,c01,c10,c11=at(zi,y0,x0),at(zi,y0,x1),at(zi,y1i,x0),at(zi,y1i,x1)
    d00,d01,d10,d11=at(zi+1,y0,x0),at(zi+1,y0,x1),at(zi+1,y1i,x0),at(zi+1,y1i,x1)
    out=[0.0,0.0,0.0]
    for k in range(3):
        lo_z=(c00[k]*(1-tx)+c01[k]*tx)*(1-ty)+(c10[k]*(1-tx)+c11[k]*tx)*ty
        hi_z=(d00[k]*(1-tx)+d01[k]*tx)*(1-ty)+(d10[k]*(1-tx)+d11[k]*tx)*ty
        out[k]=lo_z*(1-tz)+hi_z*tz
    return tuple(out)

def _sigmoid_spectrum(coeffs, wavelengths):
    """R(lambda) = 1/2 + U/(2*sqrt(1+U^2)), U = c0*lambda^2 + c1*lambda + c2
    -- the Jakob & Hanika (2019) sigmoid reflectance model, evaluated in the
    wavelength (nm) domain (coefficients are already dimensionalised by
    tools/spectral_upsample_fit/, matching dimensionalise_coefficients() in
    colour.recovery.jakob2019)."""
    c0,c1,c2=coeffs
    out=[]
    for wl in wavelengths:
        u=c0*wl*wl+c1*wl+c2
        out.append(0.5+u/(2.0*math.sqrt(1.0+u*u)))
    return out

_SPECTRAL_WAVELENGTHS=list(range(400,710,10))

def build_spectrum_grid(size, cs):
    """Reconstruct a real, physically-plausible reflectance spectrum for
    every LUT grid point once -- shared across every color film's exposure
    calculation for this (size, colorspace) run (see this section's own
    module comment)."""
    table=_spectral_table(cs["name"])
    dec=cs["dec"]; n=size-1
    grid=[None]*(size*size*size)
    idx=0
    for bi in range(size):
        for gi in range(size):
            for ri in range(size):
                R,G,B=dec(ri/n),dec(gi/n),dec(bi/n)
                coeffs=_rgb_to_sigmoid_coeffs(table,R,G,B)
                grid[idx]=_sigmoid_spectrum(coeffs,_SPECTRAL_WAVELENGTHS)
                idx+=1
    return grid

_SPECTRUM_GRID_CACHE = {}
def get_spectrum_grid(size, cs):
    key=(size, cs["name"])
    if key not in _SPECTRUM_GRID_CACHE:
        _SPECTRUM_GRID_CACHE[key]=build_spectrum_grid(size,cs)
    return _SPECTRUM_GRID_CACHE[key]

def build_hk_grid(size, cs):
    """Precompute hk_mul() for every LUT grid point once (Ticket 22). hk_mul()
    depends only on the decoded grid-point RGB and the colour space -- not on
    film, look, filter, or variant -- so every Modern-variant LUT for a given
    (size, colorspace) run shares one grid instead of recomputing it from
    scratch, the same "compute once, reuse many" shape as get_spectrum_grid().
    Indexed identically to the spectrum grid's own (bi,gi,ri) nesting."""
    dec,rgb2xyz=cs["dec"],cs["rgb2xyz"]; n=size-1
    grid=[0.0]*(size*size*size)
    idx=0
    for bi in range(size):
        B=dec(bi/n)
        for gi in range(size):
            G=dec(gi/n)
            for ri in range(size):
                grid[idx]=hk_mul(dec(ri/n),G,B,rgb2xyz)
                idx+=1
    return grid

_HK_GRID_CACHE = {}
def get_hk_grid(size, cs):
    key=(size, cs["name"])
    if key not in _HK_GRID_CACHE:
        _HK_GRID_CACHE[key]=build_hk_grid(size,cs)
    return _HK_GRID_CACHE[key]

def layer_exposure_grid(sens_list, spectrum_grid):
    """Per-grid-point exposure for each of a color film's layers -- the
    layer_weights() replacement. For each layer, normalizes by that layer's
    own real Sum(sens*D65) total (exactly the same normalization role
    `tot` played in the old _weights()) so that an achromatic grey pixel
    (whose reconstructed spectrum is exactly flat, see
    _rgb_to_sigmoid_coeffs()'s mono case) still yields exposure == the grey
    reflectance value itself, unchanged -- preserving every existing
    GREY=0.18 cascade-anchor calibration (build_print_cascade() etc.)
    without having to touch any of that machinery. Deliberately does NOT
    take an `ssf` (colour-space CMF row) argument the way the old
    layer_weights() did: which RGB colour space is being targeted is now
    fully captured by which baked table `spectrum_grid` was reconstructed
    from, so mixing in the colour space's own CMF row a second time here
    (as the old normalization implicitly did) would be double-counting it."""
    out=[]
    for layer in sens_list:
        sk=sorted(layer); sv=[layer[k] for k in sk]
        sens_d65=[_il10(sk,sv,wl)*D65[wl] for wl in _SPECTRAL_WAVELENGTHS]
        tot=sum(sens_d65)
        if tot<=0:
            out.append([0.0]*len(spectrum_grid))
            continue
        out.append([sum(s*w for s,w in zip(spectrum,sens_d65))/tot for spectrum in spectrum_grid])
    return out

def trix_exposure_grid(sens, filt, spectrum_grid):
    """Per-grid-point Tri-X exposure -- the `_weights()` replacement (Ticket
    21). Tri-X has one panchromatic sensitivity curve, not a list of dye
    layers, but a real Wratten filter over the lens attenuates the light
    reaching it wavelength-by-wavelength same as any other spectral
    transmission, so the per-wavelength weight is
    `sens(lambda) * filter_transmission(lambda)/100 * D65(lambda)` (filter
    term omitted entirely when `filt` is None, i.e. NoFilter) instead of
    `layer_exposure_grid()`'s plain `sens(lambda) * D65(lambda)`. Normalizing
    by the sum of those weights is exactly the photographer's own
    filter-factor compensation -- it's what keeps an 18%-grey card metering
    the same through a yellow filter as without one -- and, as in
    `layer_exposure_grid()`, is also what guarantees an achromatic grey
    pixel's (exactly flat, see `_rgb_to_sigmoid_coeffs()`'s mono case)
    reconstructed spectrum still yields exposure == the grey reflectance
    value itself, preserving GREY=0.18 unchanged."""
    sk=sorted(sens); sv=[sens[k] for k in sk]
    ft=None
    if filt:
        fk=sorted(filt); fv=[filt[k] for k in fk]; ft=(fk,fv)
    weights=[]
    for wl in _SPECTRAL_WAVELENGTHS:
        s=_il10(sk,sv,wl)
        if ft: s*=_il(ft[0],ft[1],wl)/100.0
        weights.append(s*D65[wl])
    tot=sum(weights)
    if tot<=0:
        return [0.0]*len(spectrum_grid)
    return [sum(s*w for s,w in zip(spectrum,weights))/tot for spectrum in spectrum_grid]

# =========================================================================
# Cascade builders
# =========================================================================
def _find_anchor(xs, ys, td, increasing, start=0):
    """Find x where digitized curve xs->ys crosses target density td.

    xs/ys must be sorted by increasing exposure (xs ascending). `increasing`
    says which direction density moves with exposure for this curve: True for
    negative/print curves (density rises with exposure, e.g. Polymax), False
    for reversal dye layers (density falls with exposure). Clamps to the
    nearest endpoint if td is outside the digitized range.

    Scans from index `start` (0 by default) — the well-behaved, non-solarized
    end of every curve in this dataset — and returns the first bracketing
    crossing, which is the physically correct one even though several of the
    digitized curves wobble non-monotonically further out (Polymax grades 0/1
    dip near Dmax; all three Velvia dye layers reverse/solarize at the
    extreme-overexposure tail). To keep that assumption honest, raise instead
    of silently misfiring if the curve isn't monotonic in the region actually
    scanned before the crossing. `start` lets a caller skip a leading sample
    known to be noise rather than a real reversal (e.g. Ektachrome Radiance
    III's first two points sit on an essentially flat Dmax plateau and wobble
    by ~0.003-0.004 density — digitization noise, not solarization — nowhere
    near where any of its grey-anchor crossings actually fall). The pre-loop
    endpoint clamp is start-aware too: it checks ys[start]/xs[start], not
    ys[0]/xs[0], so a target density that falls within the skipped noisy
    leading samples clamps to the first trusted sample rather than silently
    returning a noisy xs[0].
    """
    if increasing:
        if td<=ys[start]: return xs[start]
        if td>=ys[-1]: return xs[-1]
        for i in range(start,len(xs)-1):
            if ys[i]>ys[i+1]:
                raise ValueError(f"_find_anchor: curve not monotonic before crossing (index {i}: {ys[i]} > {ys[i+1]})")
            if ys[i]==ys[i+1]:
                if td==ys[i]: return xs[i]
                continue
            if ys[i]<=td<=ys[i+1]:
                t=(td-ys[i])/(ys[i+1]-ys[i]); return xs[i]*(1-t)+xs[i+1]*t
    else:
        if td>=ys[start]: return xs[start]
        if td<=ys[-1]: return xs[-1]
        for i in range(start,len(xs)-1):
            if ys[i]<ys[i+1]:
                raise ValueError(f"_find_anchor: curve not monotonic before crossing (index {i}: {ys[i]} < {ys[i+1]})")
            if ys[i]==ys[i+1]:
                if td==ys[i]: return xs[i]
                continue
            if ys[i]>=td>=ys[i+1]:
                t=(td-ys[i])/(ys[i+1]-ys[i]); return xs[i]*(1-t)+xs[i+1]*t
    raise ValueError("_find_anchor: target density not found in curve range")

def _detect_lead_noise_start(curve, increasing, max_lead=15):
    """Auto-detect how many leading samples of a digitized curve are
    Dmin/Dmax-plateau digitization noise rather than the real monotonic
    climb/decline, so `_find_anchor()` knows where to start scanning.

    Restores the auto-skip the old (deleted) build_velvia_print_cascade()
    used to do (`lead=pys[:5]; start=lead.index(max(lead))`) as a general
    per-curve function, instead of requiring a hand-derived magic number at
    every PAPER_LADDER/COLOR_FILMS call site. Real digitization noise on a
    flat plateau shows up as a direction violation (a decrease where the
    curve should be rising, or vice versa) confined to the first handful of
    samples; genuine non-monotonicity elsewhere in a curve (Polymax grades
    0/1 dipping near Dmax, a reversal dye layer solarizing at the extreme-
    overexposure tail) lives far from index 0 and must stay visible to
    _find_anchor()'s own monotonicity check, so this only scans a bounded
    leading window (`max_lead`, generously larger than any noise run
    actually seen in this file's data) rather than the whole curve. Returns
    the index right after the last violation found in that window -- 0 if
    the leading window is already clean, which every currently-shipped
    curve except Provia 100F (layers 0 and 2) and Kodak Supra Endura (layer
    2) is.
    """
    xs, ys = _sc(curve)
    n = min(max_lead, len(ys) - 1)
    last_bad = -1
    for i in range(n):
        bad = (ys[i] > ys[i+1]) if increasing else (ys[i] < ys[i+1])
        if bad:
            last_bad = i
    return last_bad + 1

def build_print_cascade(stages):
    """N-stage print cascade: E -> reflectance.

    `stages` is an ordered list of (curve_dict, increasing, start, ref_d)
    tuples, first = what receives scene light (a camera film, or a reversal
    film's own curve), last = the final print material (a real paper).
    `increasing` means density rises with exposure (any negative-type
    material: Tri-X's TRIX_DEV7, the internegative, every paper in
    PAPER_LADDER); False means density falls with exposure (a reversal dye
    layer, e.g. Velvia). `start` is passed to whichever _find_anchor()
    search that stage needs, for curves with leading digitization noise
    before the real crossing (e.g. Kodak Supra Endura as a final stage, or
    Fuji Provia 100F's own reversal curve as a non-final one -- both have a
    tiny Dmax-plateau wobble in their first sample or two; 0 for every other
    curve in this file, which are clean). Callers get this via
    _detect_lead_noise_start() rather than a hand-derived constant, so it
    stays correct as curve data changes. `ref_d` is the target
    density _find_anchor() searches for to find that stage's own
    calibration reference point -- ignored for the final stage, which is
    always grey-anchored to 18% reflectance regardless of what's passed.

    Every stage except the last is a pure forward evaluation via _il() --
    its density becomes the next stage's printing exposure, calibrated
    against a fixed "printer light" constant derived from each stage's own
    reference exposure (where _find_anchor() finds density=ref_d) and the
    density the *previous* stage produces there. That's how light physically
    passes through an intermediate duplicating stage (an internegative) or a
    negative film feeding a paper: no search needed for the exposure flow
    itself, only for where to calibrate it -- exactly the two-stage
    structure the old build_trix_cascade()/build_velvia_print_cascade() each
    hardcoded once; this generalizes it to any chain length so a 3-stage
    film->internegative->paper cascade and a 2-stage film->paper cascade
    share one implementation. Only the LAST stage is grey-anchored to 18%
    reflectance instead of an arbitrary ref_d, since that's the one physical
    material whose own density has to reproduce exactly 18% reflectance when
    the whole chain is fed GREY scene exposure.

    `ref_d` deliberately isn't computed in here -- an earlier version tried
    a built-in "density-range midpoint" heuristic for every non-final stage,
    which is arbitrary (not tied to any real photographic reference) and
    left a real, measurable stop-plus of highlight headroom unused (verified
    against the shipped Velvia50_Classic_Normal.cube: neutral white topped
    out at encoded 0.827 instead of the ~0.93-0.94 Tri-X reliably reaches).
    Callers now supply ref_d explicitly, so each one can be traced to either
    real published calibration data (see COLOR_FILMS: the internegative's
    ref_d is Kodak's own published "Internegative LAD Aim" density from the
    EASTMAN Color Internegative II Film 5272/7272 datasheet TI1301 sec.9,
    not a guess; a reversal film's own ref_d is the exposure that reproduces
    18% reflectance on *its own* curve, the same universal photographic
    grey convention every other anchor in this file uses) or, where no
    better published reference exists (Tri-X's TRIX_DEV7 -- see
    build_trix_cascade()), a density-range-midpoint fallback that's at least
    labeled as such rather than presented as if it were real data.
    """
    parsed = [(_sc(curve), inc, st, rd) for curve, inc, st, rd in stages]
    refs = []  # (own reference exposure, density there), non-final stages only
    for (xs, ys), inc, st, ref_d in parsed[:-1]:  # last stage is grey-anchored separately below
        na = _find_anchor(xs, ys, ref_d, increasing=inc, start=st)
        refs.append((na, _il(xs, ys, na)))

    (fxs, fys), finc, fst, _ = parsed[-1]
    fdm = min(fys)
    td = _grey_target_density(fys)
    lhg = _find_anchor(fxs, fys, td, increasing=finc, start=fst)

    pls = []
    for i in range(len(parsed) - 1):
        dn_i = refs[i][1]
        if i == len(parsed) - 2:  # transition into the final (grey-anchored) stage
            pls.append(lhg + dn_i)
        else:
            na_next = refs[i+1][0]
            pls.append(na_next + dn_i)

    (x0, y0), _, _, _ = parsed[0]
    na0 = refs[0][0]

    def xfer(E):
        lh = x0[0]-10 if E<=1e-9 else na0+math.log10(E/GREY)
        D = _il(x0, y0, lh)
        for i in range(1, len(parsed)):
            (xs_i, ys_i), _, _, _ = parsed[i]
            D = _il(xs_i, ys_i, pls[i-1]-D)
        return max(0.0, min(1.0, 10**(-(D-fdm))))
    return xfer

def _grey_target_density(ys):
    """Density where a curve reproduces 18% reflectance, given its already-
    parsed density values. Shared by reversal_grey_target() (a documented
    sanity check, not called from any cascade) and build_print_cascade()'s
    final-stage grey anchor (the one place this actually feeds a cascade),
    so the "min(ys) - log10(0.18)" formula exists in exactly one place."""
    return min(ys) - math.log10(0.18)

def reversal_grey_target(curve):
    """Target density where a reversal-type curve reproduces 18% reflectance
    -- the same universal photographic grey convention the final stage of
    every cascade is anchored to. Lands in the same ballpark (~0.83-1.00
    density across all four reversal films checked) as Kodak's own published
    reference for a normally-exposed reversal original (Status M 1.10, from
    the "reversal LAD control film" spec in EASTMAN Color Internegative II
    Film 5272/7272's datasheet, TI1301 sec.9) -- a different reference
    material, so not an exact match, but the right order of magnitude for
    the same real-world concept: where does *grey* belong.

    NOT used as a non-final stage's calibration reference point (despite an
    earlier version of this function doing exactly that) -- checked directly
    and it's the wrong tool for that job. "Where does grey belong" and "how
    do I avoid wasting this stage's dynamic range in the calibration
    handoff" are different questions: on Velvia's own curve this target
    sits at only ~20-23% of the layer's full density range (density_
    midpoint() sits at 50% by construction), which starves the highlight
    end of the very headroom this calibration is trying to preserve. Kept
    around only for its original purpose: sanity-checking that our own
    grey math lands in the right ballpark against Kodak's published number
    (see the comment above), not for feeding into build_print_cascade().

    Deliberately has no call sites in the cascade-building code -- it exists
    solely as a documented, on-demand sanity check (run it by hand against
    a curve when questioning whether the grey math is in the right
    ballpark), not as dead code left behind by accident.
    """
    _, ys = _sc(curve)
    return _grey_target_density(ys)

def _straight_line_window(xs, ys, n_samples=41, frac=0.5):
    """Shared core of _straight_line_density_range() and _measured_gamma():
    finds the straight-line (constant-gamma) portion of a digitized H&D
    curve, excluding the toe (near Dmin) and shoulder (near Dmax) where real
    film/paper response compresses. Resamples onto a uniform exposure grid
    (`_il()`), takes local slope between adjacent grid points, and keeps the
    widest contiguous run where |slope| is within `frac` of the curve's peak
    slope. Resampling onto a uniform grid first matters: raw point-to-point
    slopes on the original digitized points spike on short intervals from
    ordinary digitization noise (this codebase's curves are adaptively,
    unevenly spaced -- see curve_digitizer's RDP simplification), even
    where the underlying curve is smooth; a uniform grid dilutes that noise
    instead of amplifying it.

    Returns (grid, grid_y, lo, hi) where grid[lo:hi+1]/grid_y[lo:hi+1] is the
    straight-line window and slopes[lo:hi] (i.e. grid_y[i+1]-grid_y[i] for i
    in range(lo,hi)) are the segment's own local slopes -- density range
    (_straight_line_density_range) and gamma (_measured_gamma) are two
    different readings of that same window, not two different searches.
    """
    x_lo, x_hi = xs[0], xs[-1]
    grid = [x_lo + (x_hi-x_lo)*i/(n_samples-1) for i in range(n_samples)]
    grid_y = [_il(xs, ys, x) for x in grid]
    slopes = [(grid_y[i+1]-grid_y[i])/(grid[i+1]-grid[i]) for i in range(n_samples-1)]
    peak = max(abs(s) for s in slopes)
    thresh = peak * frac
    n = len(slopes)
    best = (0, 0)
    i = 0
    while i < n:
        if abs(slopes[i]) >= thresh:
            j = i
            while j < n and abs(slopes[j]) >= thresh:
                j += 1
            if j - i > best[1] - best[0]:
                best = (i, j)
            i = j
        else:
            i += 1
    return grid, grid_y, best[0], best[1]

def _straight_line_density_range(xs, ys, n_samples=41, frac=0.5):
    """The density span [lo, hi] covered by the straight-line (constant-
    gamma) portion of a digitized H&D curve -- see _straight_line_window()
    for how that portion is found."""
    grid, grid_y, lo, hi = _straight_line_window(xs, ys, n_samples, frac)
    seg_ys = grid_y[lo:hi+1]
    return min(seg_ys), max(seg_ys)

def _measured_gamma(curve, n_samples=41, frac=0.5):
    """Real measured gamma (contrast) of a digitized H&D curve: the average
    slope magnitude (density change per log-exposure unit) over its own
    straight-line portion, found by _straight_line_window() -- the same
    window density_midpoint() reads its density range from, just read for
    slope instead of span.

    Not called by the direct-print gamma-correction pipeline itself as of
    v4 (see GAMMA_CORRECT_TARGET's comment) -- that now reads exact local
    gamma off each material's own fitted split-normal-CDF model
    (_split_gauss_local_gamma()) rather than a window-averaged estimate off
    the raw digitized points. Kept, deliberately, as the real diagnostic
    this project's own README "Why a reversal print crushes without
    correction" cites directly (the native per-film/per-paper gamma figures
    quoted there came from calling this) -- same status as
    reversal_grey_target() below: an intentional, documented, on-demand
    tool, not dead code left behind by accident.

    Reported as a positive magnitude regardless of
    curve direction (a reversal dye layer or a reversal-type direct-print
    paper has density *falling* with exposure, `increasing=False`; every use
    of gamma in this file -- GAMMA_CORRECT_TARGET and gamma_correct_curve()
    below, applying L.A. Jones's 1920 gamma-product rule -- cares about
    magnitude only, matching how gamma is conventionally reported in every
    manufacturer datasheet already in this file (INTERNEGATIVE_II_CURVES'
    own comment states "measured gamma ~0.527" the same way, sign dropped)."""
    xs, ys = _sc(curve)
    grid, grid_y, lo, hi = _straight_line_window(xs, ys, n_samples, frac)
    slopes = [abs((grid_y[i+1]-grid_y[i])/(grid[i+1]-grid[i])) for i in range(lo, hi)]
    return sum(slopes) / len(slopes)

def density_midpoint(curve):
    """Density at the midpoint of the density range spanned by a curve's
    own straight-line portion -- real measured data (the material's own
    actual response), used as a stage's calibration reference point
    specifically where no better *published calibration* number exists for
    that exact question (see build_print_cascade's docstring: this is a
    labeled fallback, not presented as if it were a manufacturer's own aim
    density). Matches Kodak's own stated general LAD methodology for
    duplicating films where no per-film aim density is published: "the
    specified aims are at the center of the usable straight-line portion of
    the sensitometric curve of the film" (EASTMAN EKTACHROME Film 5240/7240
    datasheet TI0986, sec.11) -- i.e. this isn't an arbitrary substitute for
    missing data, it's an approximation of Kodak's own documented practice
    for exactly this situation. Deliberately still used for every reversal
    film's own stage in COLOR_FILMS: reversal_grey_target() was tried there
    instead and made headroom measurably worse (see that function's
    docstring) because "where grey belongs" and "how to not waste dynamic
    range in a calibration handoff" are different questions, and only this
    one answers the second.
    """
    xs, ys = _sc(curve)
    lo, hi = _straight_line_density_range(xs, ys)
    return (lo + hi) / 2

# =========================================================================
# Gamma correction for direct-print (no-internegative) reversal cascades --
# see DIRECT_PRINT_PAPERS below and papers/masking_research/README.md for
# the full research trail. Summary of the physics, since this leans on a
# 100+ year old result that isn't otherwise documented anywhere else in this
# file:
#
# A reversal film printed straight onto a real print paper crushes to only
# ~3-3.5 stops of usable tonal separation around grey (verified by hand:
# Kodachrome 64 on Kodak Ektachrome Radiance III, uncorrected, reaches
# encoded 0.93 by +1.5 EV and 0.005 by -1.5 EV) even though the film's own
# digitized H&D curve spans ~9 stops. This is not a data or code bug -- it's
# L.A. Jones's 1920 tone-reproduction theory (papers/
# jones_1920_theory_of_tone_reproduction.pdf, p.64): "the product of the
# gamma of the negative by that of the positive is equal to that of the
# reproduction curve" -- gamma_stage1 * gamma_stage2 * ... = gamma_system,
# with Jones's own worked example landing at ~1.01 as the target for
# faithful (undistorted) reproduction of the original's own tonal range.
# Every material in a print chain has real gamma > 0; unless something in
# the chain has gamma measurably below 1, the product overshoots 1 and the
# print is more contrasty than the scene it depicts. A still reversal film's
# own native gamma is high on its own (Velvia 50 ~1.63, Kodachrome 64 ~1.84,
# Provia 100F ~1.48, Ektachrome 100D ~1.76 -- see README "Why Adobe RGB").
# Pairing that directly with a print paper of its own real, unreduced gamma
# (Radiance III, Ilfochrome Micrographic M/P all measure gamma > 1 on their
# own straight-line portions -- see _measured_gamma()) compounds well past
# 1, which is exactly the crush the direct-print route reproduces without
# correction (and exactly why an earlier version of this project's real,
# uncorrected Radiance III cascade -- commit cf14a88, replaced in 881f3da --
# was "structurally very contrasty," per README's own account).
#
# Real duplicating labs hit the same wall: EASTMAN Color Internegative Film
# was engineered (internegative gamma ~0.5 x print-paper gamma ~2.0 ~= 1.0)
# for a low-contrast (gamma ~1.0) *duplicating positive* input (Ektachrome
# Commercial, "never projected" -- papers/masking_research/
# brianpritchard_FAOL_colour_duplicating_film_stocks.html), not a
# full-contrast camera original -- so feeding it a real reversal film has the
# identical mismatch, just hidden behind an extra stage (see COLOR_FILMS,
# left untouched here). Real labs' own fix for a too-high-contrast original
# was flashing (US Patent 4,739,375, papers/
# patent_US4739375_internegative_contrast_correction_flash.pdf: a second,
# neutral-density-filtered flash exposure) or an optical contrast-reduction
# sandwich mask (papers/masking_research/
# freestylephoto_contrast_masking_traditional_print.html) -- both real,
# neither with a published formula (brianpritchard.com's own verdict on
# flashing here: "none [are] satisfactory"). Flashing only ever partially
# fixes this (it adds density to the toe/shadows, leaving the shoulder/
# highlights' own gamma close to untouched) -- since our own measurement
# above crushes symmetrically at both ends, that's not the right model to
# copy even if its exact dial setting were published, which it isn't.
#
# What this file does instead: apply Jones's own math directly, using only
# real data -- and only where Jones's own theory actually claims validity.
#
# GAMMA_CORRECT_TARGET default 1.35, not 1.0. Jones's 1920 product rule targets
# unity system gamma -- the mathematically correct target for *faithful*
# reproduction, and the one real labs' own engineering (internegative gamma
# x paper gamma ~= 1.0, see above) was built around. But unity system gamma
# is the right target only for reproducing a *captured* image at the exact
# viewing conditions of the original scene; any real viewing/display chain
# is under different conditions (dimmer, smaller subtended angle, no local
# scene adaptation) than the scene it depicts, and Bartleson & Breneman
# ("Brightness Perception in Complex Fields," J. Opt. Soc. Am. 57, 1967 --
# cited alongside Jones in the same tone-reproduction literature, e.g.
# Lehmbeck & Urbach, "Basics for Tone Reproduction in Digital Imaging
# Systems," ref. 59; the primary 1967 paper itself was not accessible
# during this research -- cited here via two real secondary sources saved
# locally that carry the citation and the mechanism, papers/masking_research/
# choi_bartleson_breneman_brightness_stevens_power_law.pdf and .../
# roufs_global_brightness_contrast_perceptual_image_quality.pdf) found the
# system gamma humans actually prefer depends on how dark the surround is
# relative to the display: ~1.1 for a light/bright surround (an ordinary
# reflection print in a lit room), ~1.5-1.6 for a dark-surround transparency/
# projection viewing -- and, separately, a dedicated figure "for TV" (a
# self-luminous display, moderately-dark/"dim" surround, the real category a
# monitor viewed while photo-editing falls into) that Roufs, Koselka & van
# Tongeren's own independent experiment reproduces almost exactly:
# their own test rig was a slide (reversal-film) scanner feeding a monitor --
# i.e. very close to this project's actual output path, a digitized film
# image displayed on a screen -- and found "the optimal value for the
# effective gamma is about 1.2-1.3 ... very near what Bartleson and Breneman
# found for TV in 1967." This project's own output is a LUT that replaces a
# raw processor's tone mapper entirely (see module docstring/README) --
# i.e. the rendered image is *displayed on a monitor*, not printed and hung
# on a wall under room light -- so the correct viewing-condition target is
# this TV/monitor figure, not the light-surround reflection-print one. The
# module default was raised to 1.25 (the midpoint of Roufs et al.'s own
# reported 1.2-1.3 range) after real-world use showed the reflection-print
# target (1.1) rendering flat/washed-out on screen -- and then, after
# real-world use showed 1.25 itself still not enough punch, exposed as a
# tunable via --gamma (default 1.35, still inside the cited light-surround-
# to-dark-surround real range of ~1.1-1.6, but past the specific 1.2-1.3 TV
# figure) rather than re-deriving a single "more correct" fixed constant a
# third time -- see --gamma's own help text for the citations. Every call
# site reads the *current* value of this module global at call time (not a
# stale def-time-bound default -- see gamma_correct_curve()'s own
# `target=None` handling), so main() can override it from args.gamma before
# any LUT is built.
#
# Ticket 19 finding, and why the default moved back down to 1.25: measured
# directly (tasks/19-gamma-correction-undershoots-target-at-grey.md), the
# mechanism itself was solving its Jones-rule criterion at the wrong
# operating point -- the fitted model's toe/shoulder junction x0 rather than
# the real grey crossing, and each paper's downstream gamma read off its
# *fitted* model rather than the *digitized* curve build_print_cascade()
# actually renders through -- and was systematically undershooting whatever
# target it was given. End-to-end at the "1.35" default, real delivered
# system gamma at grey measured ~1.06-1.41 across routes -- so the push from
# 1.25 to 1.35 documented above was real-world use compensating for this
# undershoot, not a genuine preference for system gamma beyond the Roufs et
# al. TV figure. `gamma_correct_curve()` now evaluates the criterion at the
# model's own real grey crossing (`film_ref_d`, `z_ref` via `_norm_ppf()`),
# and `_digitized_local_gamma()` (a centered secant on the paper's real
# digitized curve) replaces `_split_gauss_local_gamma(paper_fit, ...)` for
# downstream_gamma in both `_direct_print_stage_fn()` and
# `_negative_gammacorrect_stage_fn()`. With both fixed, "1.35" genuinely
# means 1.35 at grey (verified: mean 1.34-1.343 across both routes, versus
# the old 1.06-1.41 spread) -- so the default moved back to 1.25, the
# original Roufs et al. midpoint, to reproduce the punch real-world use had
# already validated without inheriting the undershoot that produced it.
#
# TWO EARLIER VERSIONS of gamma_correct_curve() are documented here (not
# just in git history) because both looked reasonable and both measurably
# failed real-world use, and the reasons matter for not repeating them:
#
# v1 (uniform scalar): rescale the entire digitized curve's density by one
# constant factor around the pivot. Jones's own product rule is explicit
# about its own scope -- "for the straight line portions where gradient is
# constant and replaceable by gamma" (p.64) -- he never claims it governs
# the toe or shoulder. A uniform scalar nonetheless flattens the toe/
# shoulder too, which are already lower-gamma than the straight line by
# definition, so scaling them down *again* by the same factor flattens them
# far more than the theory justifies. Measured failure: Kodachrome 64 x
# Radiance III's corrected curve topped out at density 2.72 against the real
# digitized curve's 3.68, and the print's own shadow density reached only
# 1.83 against Radiance III's real digitized Dmax of 2.52 -- shadows read as
# washed-out grey, about a stop of the paper's real black reserve unused.
#
# v2 (windowed): rescale only inside _straight_line_window() (the curve's
# own "straight line," by the same definition _measured_gamma()/
# density_midpoint() already use), carrying the toe/shoulder forward
# *additively* using real, unmodified deltas outside it. Better, but still
# measurably insufficient, and for a reason worth recording: the window's
# own boundary (a 50%-of-peak-slope threshold) is a free parameter with no
# physical meaning, and local gamma *inside* the window is not constant --
# it peaks near the pivot and tapers toward the window edges, the same way
# the un-corrected curve's own slope does, just uniformly scaled. Measured
# on Velvia 50 x Radiance III: local gamma right at grey came out to ~1.3-1.5
# even though the *window-averaged* gamma (what the correction was actually
# solved for) was 1.1 -- the correction was doing its arithmetic correctly,
# but "average gamma over an arbitrarily-thresholded window" is not the same
# claim as "gamma near grey is 1.1," and the abrupt transition into
# unmodified real toe data at the window boundary left real shadow content
# (a subject a couple of stops under grey) landing right in that transition,
# still measurably short of the paper's true Dmax.
#
# v3 (straight line, no free parameter): don't rescale the original curve's
# shape at all -- construct the corrected curve as a single straight line
# through the pivot at slope GAMMA_CORRECT_TARGET/downstream_gamma, extended
# until it reaches the film's own real, measured Dmin/Dmax. Fixed the
# shortfall almost completely (Kodachrome 64 x Radiance III: print's shadow
# density reached 2.517 against Radiance III's real 2.521 Dmax, versus 0.4-
# 0.7 short for v1/v2) -- but discards the film's own toe/shoulder curvature
# entirely, replacing a real, measured, material-specific characteristic
# with a straight line. That curvature is real photographic data (how
# gradually *this specific* film's response saturates near black and white
# is part of what makes it that film, not an incidental detail) and
# rejecting v3 for erasing it is the correct call, not a nitpick.
#
# v4 (this version): keep the real toe/shoulder shape *and* reach the real
# Dmax, by fitting an actual model to the real digitized data instead of
# either rescaling it (v1/v2) or discarding it (v3). The physical origin of
# the H&D curve's toe/straight-line/shoulder shape is well established in
# sensitometry: an emulsion is a population of individual silver-halide
# grains, each becoming developable once its own quantum catch crosses its
# own threshold, and that population has a real, measured spread of
# individual grain sensitivities -- J.H. Webb, "Graphical Analysis of
# Photographic Exposure and a New Theoretical Formulation of the H and D
# Curve," J. Opt. Soc. Am. 29, 314-326 (1939), derives the H&D curve from
# exactly this picture (primary source paywalled; the finding that Webb's
# own equation "cannot be integrated mathematically" is itself consistent
# with a cumulative-Gaussian origin, whose integral has no elementary closed
# form either -- see papers/masking_research/README.md for the corroborating
# secondary sources actually saved). The curve's value at any exposure is
# therefore a *cumulative distribution* of how many grains have crossed
# threshold by that exposure -- the standard idealization of a threshold-
# crossing process over a log-normally-distributed population is a
# cumulative Gaussian (normal) distribution against log exposure.
#
# tools/gamma_correction_fit/ (a separate uv-managed tool, scipy/numpy --
# see that project's own README for why those stay out of this file) fits
# an *asymmetric* cumulative-Gaussian ("split-normal": independent toe/
# shoulder widths sigma_lo/sigma_hi either side of the inflection x0, real
# because toe and shoulder are physically different mechanisms -- grain-
# threshold statistics near Dmin, dye/silver exhaustion near Dmax, with no
# reason to share a width) to each reversal film's and each direct-print
# paper's own real digitized curve via least-squares regression
# (scipy.optimize.curve_fit). Fit quality against the real data, checked not
# assumed: R² > 0.998 and max residual < 0.07 density units on every one of
# the 12 film-layer and 9 paper-layer curves fit (see that tool's own
# printed output). REVERSAL_FILM_FIT/DIRECT_PRINT_PAPER_FIT below are those
# fitted parameters, transcribed as data, the same way every other derived
# constant in this file is.
#
# The corrected curve is then a pure *horizontal* (exposure-axis-only)
# rescale of the fitted film model around the pivot: every real fitted
# density value is kept exactly as-is (so the model's own real fitted
# Dmin/Dmax are reached exactly, not truncated), just relabeled to a new,
# stretched exposure position, by whatever constant factor makes the
# model's own *exact* analytic local gamma at the pivot (no window-average,
# no finite-difference approximation -- the derivative of a normal CDF is a
# normal PDF, computed directly) times downstream_gamma (the paper's own
# fitted model, evaluated the same exact way at its own real grey-
# reproduction point) equal GAMMA_CORRECT_TARGET. A pure horizontal stretch
# preserves the fitted curve's shape exactly (toe:shoulder proportions
# unchanged) while spreading the same real density swing over more exposure
# -- physically correct, since "lower gamma" means exactly that: the same
# density change now needs more exposure, not a smaller density change.
#
# Verified (same Kodachrome 64 x Radiance III comparison as v1-v3 above):
# print's shadow density reaches 2.519 against the fitted model's own real
# Dmax of 2.561 -- 0.04 short, comparable to v3's 0.004 but with the film's
# real toe/shoulder curvature intact, not replaced by a straight line.
# Checked across all 4 reversal films x 3 direct-print papers x 3 layers:
# shortfall is under 0.06 density units (a small fraction of a stop) in
# every one of the 36 combinations, and local gamma near grey now sits
# consistently close to GAMMA_CORRECT_TARGET itself (not 20-40% above it,
# which is what v2's window-average had actually delivered near the pivot),
# tapering smoothly into the toe/shoulder with no window-boundary kink.
#
# Inserting a second real material (e.g. EASTMAN Fine Grain Duplicating
# Panchromatic Negative 2234/5234, papers/
# kodak_finegrain_duplicating_pan_2234_TI0147.pdf) as an intermediate
# cascade stage was considered and rejected in an earlier round of this
# investigation: it is itself a duplicating stock designed around some
# assumed low-contrast "master positive" input, so using it would relocate
# the exact real-vs-duplicating-positive mismatch this correction exists to
# escape, not resolve it (same failure mode as INTERNEGATIVE_II_CURVES
# against a real reversal original -- see above).
#
# v5 (this version): v4's own verification above only ever checked the
# *shadow* end (an extreme, off-scale exposure where the fitted model has
# already reached its own flat asymptote) -- it never checked the symmetric
# highlight question at the one exposure every real image actually supplies:
# encoded pure white, only ~2.47 stops over 18% grey (log2(1/GREY)). Checked
# directly, v4 fell well short there: every one of the 4 reversal films x 3
# direct-print papers needed *more than 3 stops* above grey to reach 90% of
# its own asymptotic white, so an encoded-white pixel topped out around
# 0.72-0.85 reflectance -- never approaching paper white, on every single
# combination. Root cause: v4's single shared factor k was derived from the
# model's local gamma at whichever real-world reference exposure (na0, a
# reversal film's own density-midpoint) happened to land -- then applied
# identically to *both* the toe (x<x0) and shoulder (x>=x0) halves. Every
# material fit in this file has sigma_lo != sigma_hi by design (toe/grain-
# threshold statistics and shoulder/dye-exhaustion are different physical
# mechanisms); Velvia's own fitted shoulder is ~1.6x wider than its toe.
# na0 happened to fall in the toe half for every material checked, so v4's k
# was already correct for the toe -- but reusing that same factor for the
# shoulder over-stretched it, demanding far more exposure headroom than a
# [0,1]-normalized image can ever supply.
#
# gamma_correct_curve() now derives two independent factors, k_lo and k_hi,
# each satisfying the identical Jones-rule criterion v4 already used
# (local_gamma * downstream_gamma == target) but evaluated at the toe/
# shoulder junction x0 using that half's *own* sigma, instead of inheriting
# whichever factor the other half needed. Both halves still meet
# continuously at x0 (matching the un-corrected model's own value-
# continuous/slope-discontinuous behavior there -- an accepted
# simplification already, see split_gaussian_cdf's own docstring in
# tools/gamma_correction_fit/main.py). The toe's correction is unchanged
# from v4; only the shoulder moves. Verified: Velvia x Radiance III now
# needs ~2.25-2.3 stops to reach 90% of white (within the ~2.47 stops
# actually available), reflectance ~0.93-0.94 at encoded white -- matching
# the reference point Tri-X reliably reaches -- and consistent across all
# 12 reversal film x direct-print-paper combinations (2.2-2.8 stops needed,
# versus 3.0-3.8 under v4). The shadow side is untouched by this fix and
# still compresses within roughly a stop below grey -- a real, measured
# material property (the toe genuinely is narrower than the shoulder in the
# digitized data), not an artifact of the correction mechanism, and a
# separate question from the highlight bug this fixes. Applies identically
# to NEGATIVE_FILMS x PAPER_LADDER (same function), but barely moves
# anything there: negative-film fits have sigma_lo and sigma_hi within a few
# percent of each other, so the asymmetry that made this fix necessary for
# the reversal films isn't present in those materials' own digitized curves.
# =========================================================================
GAMMA_CORRECT_TARGET = 1.25  # overridable via --gamma; see comment block above (Ticket 19: moved back from 1.35 now that the correction mechanism itself is fixed)

# Fitted split-normal-CDF parameters (x0, d_lo, d_hi, sigma_lo, sigma_hi) per
# layer, produced by tools/gamma_correction_fit/main.py (`uv run main.py`)
# against each material's own real digitized curve already in this file --
# see the GAMMA_CORRECT_TARGET block above for the model, the physical
# justification, and the measured fit quality (R² > 0.998 on every layer).
# d_lo/d_hi are the model's own fitted density value as x -> -inf/+inf
# respectively (so for a decreasing reversal-type curve, d_lo is the
# fitted Dmax and d_hi is the fitted Dmin) -- not manufacturer-published
# numbers, but a least-squares fit to manufacturer-published *curves*,
# exactly as transparent about its own derivation as density_midpoint() or
# any other derived-not-published constant in this file.
VELVIA_SPLITGAUSS_FIT = [(-1.09863, 3.36063, 0.11369, 0.42569, 0.70938), (-1.22987, 3.82002, 0.13862, 0.47409, 0.71762), (-1.23102, 3.72241, 0.13072, 0.47733, 0.74127)]
KODACHROME64_SPLITGAUSS_FIT = [(-1.13981, 3.74262, 0.12945, 0.56109, 0.70427), (-1.20362, 3.52665, 0.15167, 0.54334, 0.69121), (-1.24723, 3.38457, 0.16398, 0.5542, 0.70478)]
PROVIA100F_SPLITGAUSS_FIT = [(-1.41231, 3.3012, 0.04784, 0.58261, 0.70548), (-1.45229, 3.44865, 0.04979, 0.54321, 0.71592), (-1.43736, 3.36174, 0.05708, 0.58776, 0.71665)]
EKTACHROME100D_SPLITGAUSS_FIT = [(-1.33196, 3.2784, 0.09, 0.62819, 0.84399), (-1.46142, 3.65243, 0.14364, 0.54266, 0.74537), (-1.58608, 3.87044, 0.14325, 0.54257, 0.74311)]
RADIANCEIII_SPLITGAUSS_FIT = [(1.67277, 2.56125, 0.05981, 0.65904, 0.65691), (1.70681, 2.44541, 0.0621, 0.58546, 0.63977), (1.68778, 2.4853, 0.06063, 0.56683, 0.65505)]
ILFOCHROMEM_SPLITGAUSS_FIT = [(1.5475, 2.05698, 0.00854, 0.374, 0.31682), (1.51505, 2.39459, -0.00274, 0.40747, 0.33799), (1.49866, 2.45143, 0.02175, 0.4245, 0.33984)]
ILFOCHROMEP_SPLITGAUSS_FIT = [(1.69499, 1.92629, 0.01114, 0.49075, 0.42615), (1.68263, 2.22109, 0.01197, 0.52031, 0.37516), (1.63925, 2.27265, 0.03463, 0.51464, 0.45914)]
DIRECT_PRINT_PAPER_FIT = {"RadianceIII": RADIANCEIII_SPLITGAUSS_FIT, "IlfochromeM": ILFOCHROMEM_SPLITGAUSS_FIT, "IlfochromeP": ILFOCHROMEP_SPLITGAUSS_FIT}

def _norm_cdf(z):
    """Standard normal CDF via math.erf -- exact (to float precision, checked
    directly against scipy.stats.norm.cdf across [-6,6] by
    tools/gamma_correction_fit/main.py), stdlib-only so this file doesn't
    need scipy at generation time even though the fit that produced
    *_SPLITGAUSS_FIT above did."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

def _norm_pdf(z):
    """Standard normal PDF -- the exact analytic derivative of _norm_cdf,
    used for local_gamma below instead of a finite-difference estimate."""
    return math.exp(-z * z / 2.0) / math.sqrt(2.0 * math.pi)

def _norm_ppf(p, lo=-8.0, hi=8.0, iters=60):
    """Inverse standard normal CDF via bisection over _norm_cdf (Ticket 19)
    -- stdlib-only, same rationale as _norm_cdf itself not needing scipy.
    +/-8 sigma brackets every p this file ever calls this with (real fitted
    density values sit well inside the model's own asymptotic range), and
    60 bisection iterations narrows that to below float precision."""
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        if _norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0

def _split_gauss_density(params, x):
    """D(x) for the fitted split-normal-CDF model -- see GAMMA_CORRECT_TARGET
    block for what this model is and why."""
    x0, d_lo, d_hi, sigma_lo, sigma_hi = params
    sigma = sigma_lo if x < x0 else sigma_hi
    return d_lo + (d_hi - d_lo) * _norm_cdf((x - x0) / sigma)

def _split_gauss_local_gamma(params, x):
    """Exact analytic |dD/dx| of the fitted model at x."""
    x0, d_lo, d_hi, sigma_lo, sigma_hi = params
    sigma = sigma_lo if x < x0 else sigma_hi
    return abs((d_hi - d_lo) * _norm_pdf((x - x0) / sigma) / sigma)

def _digitized_local_gamma(pxs, pys, x, h=0.15):
    """|dD/dx| at x via a centered secant on the paper's real digitized
    curve (Ticket 19 factor 1) -- what a downstream stage_fn should use for
    `downstream_gamma` instead of _split_gauss_local_gamma(paper_fit, x),
    which reads the *fitted* model's gamma at that point. The fit is
    excellent globally (R^2 > 0.998) but a global least-squares fit is least
    constrained exactly on the low-density toe where every paper's grey
    crossing (`lhg`) sits -- measured gamma_digitized(lhg)/gamma_fitted(lhg)
    ratios of 0.84-0.98 across the 3 direct-print papers and the 5
    PAPER_LADDER papers, i.e. gamma_correct_curve() was dividing by a bigger
    number than build_print_cascade() actually multiplies by, since the
    cascade renders through the digitized curve, never through the fit.

    h=0.15 (~1/2 stop in the log10(E) units this file's curves are keyed by,
    log10(2)/2 = 0.15) is the window: checked against h=0.10 and h=0.20 on
    every paper/layer in this file, all three agree within a few percent
    (not the sensitive-to-a-single-segment regime a much smaller h would hit,
    nor wide enough to blur into the toe/shoulder curvature on either side of
    lhg). This is not v2's rejected window-average -- v2 window-averaged the
    *film-side* rescale itself; this only reads the downstream operating-
    point slope, previously proxied by an even less local number (a global
    fit), same role _measured_gamma() plays elsewhere in this file just
    evaluated at one specific point instead of over a whole straight-line
    span."""
    return abs(_il(pxs, pys, x + h) - _il(pxs, pys, x - h)) / (2 * h)

def gamma_correct_curve(film_params, film_ref_d, downstream_gamma, target=None, n_samples=61):
    """Build the Jones-corrected reversal-film curve from its fitted split-
    normal-CDF model (`film_params`, one of the *_SPLITGAUSS_FIT rows above)
    -- see the GAMMA_CORRECT_TARGET block for the full physical/mathematical
    justification and the mechanisms (uniform rescale, windowed rescale,
    straight line, single-pivot split-Gaussian) this replaced, and why each
    fell short.

    v5/Ticket 19 fix (this version): v5 (and v4 before it) solved k_lo/k_hi
    from the model's local gamma at the toe/shoulder junction x0 -- but a
    pure horizontal rescale keeps every half's local gamma *shape* the same,
    it doesn't make the junction gamma equal the grey-point gamma unless the
    grey crossing happens to land exactly at x0, which it doesn't (measured
    z_ref -- the grey crossing's distance from x0 in model sigma-units --
    consistently -0.11 to -0.23, not 0). Solving the criterion at x0 instead
    of at the real grey operating point delivered a system gamma at grey
    systematically ~97-99% of target on the film side alone (compounding
    with a larger paper-side shortfall, see the two stage_fn()s below) --
    measured end-to-end in tasks/19-gamma-correction-undershoots-target-at-
    grey.md. `film_ref_d` (both callers already hold this, it's the same
    ref_d used for this stage's own build_print_cascade() anchor) locates
    that real crossing: `p = (film_ref_d-d_lo)/(d_hi-d_lo)` is the model's
    CDF value there, `z_ref = _norm_ppf(p)` its z-score (the same z-score
    regardless of which half's sigma will end up converting it to an
    exposure offset, since the model is one continuous CDF in z across the
    x0 junction), and `_norm_pdf(z_ref)` replaces the old `_norm_pdf(0.0)`
    in the peak-density-rate used by both k_lo and k_hi -- exactly the
    fix the ticket derives algebraically (system gamma at grey =
    target * [phi(z_ref)/phi(0)] * [paper-side ratio], so dividing the
    peak by phi(0) and using phi(z_ref) instead cancels that first factor).

    v4 (single-pivot) rescaled the whole curve by one factor `k`, derived
    from the model's local gamma at whichever real-world reference exposure
    (`na0`) happened to land in the curve's toe or shoulder half, then
    applied that *same* k to the other half too. Every material fit in this
    file has sigma_lo != sigma_hi by design (toe/grain-threshold statistics
    and shoulder/dye-exhaustion are different physical mechanisms, see
    split_gaussian_cdf's own docstring), so reusing one side's factor for
    the other silently over- or under-corrects it. Measured on Velvia x
    Radiance III: v4 needed >3 stops of exposure above grey to reach 90% of
    its own asymptotic white -- more headroom than a normalized linear image
    ever supplies (encoded pure white is only ~2.47 stops over 18% grey,
    log2(1/GREY)) -- so real encoded-white pixels topped out around
    0.78-0.80 reflectance, never approaching paper white, across all 4
    reversal films x 3 direct-print papers.

    This version corrects the toe (`x < x0`) and shoulder (`x >= x0`) by
    independent factors `k_lo`/`k_hi`, each chosen so *that* half's own
    natural local gamma at the toe/shoulder junction x0 (`peak/sigma_lo` or
    `peak/sigma_hi`, `peak` being the shared PDF peak `|d_hi-d_lo|*φ(0)`),
    times `downstream_gamma`, equals `target` -- the same Jones-rule
    criterion v4 applied once, now applied to each half on its own terms.
    Both halves stay anchored at the model's own x0 (mapping to itself, so
    the curve is continuous there, matching the un-corrected model's own
    value-continuous/slope-discontinuous behavior at the junction -- an
    accepted simplification already, see split_gaussian_cdf's docstring).
    Verified: this brings Velvia x Radiance III down to ~2.25-2.3 stops to
    reach 90% of white (within the available headroom), reflectance
    ~0.93-0.94 at encoded white -- matching the reference point Tri-X
    reliably reaches -- without disturbing the toe, which was already being
    corrected by its own natural factor under v4 (na0 happened to fall on
    the toe side for every material checked).

    Every fitted density value is kept exactly as computed by the model, so
    its own real fitted Dmin/Dmax are reached, not truncated -- only exposure
    positions are relabeled. build_print_cascade() re-finds wherever this
    curve reproduces each caller's own `ref_d` via `_find_anchor()`
    regardless of where that lands, so no pivot-density bookkeeping is
    needed here.

    Returns a `n_samples`-point curve dict spanning +/-8 sigma either side
    of the model's own fitted x0 (comfortably covering where the CDF moves
    perceptibly -- beyond that the model is, to float precision, flat at
    its own fitted Dmin/Dmax) for build_print_cascade()'s existing dict-
    based machinery. Construction guarantees monotonicity, so `start=0` is
    always correct here -- `_detect_lead_noise_start()` doesn't need to run
    on it.
    """
    if target is None:
        target = GAMMA_CORRECT_TARGET  # live lookup, not a def-time-bound default -- see --gamma
    x0, d_lo, d_hi, sigma_lo, sigma_hi = film_params
    z_ref = _norm_ppf((film_ref_d - d_lo) / (d_hi - d_lo))
    peak = abs(d_hi - d_lo) * _norm_pdf(z_ref)
    k_lo = target / (downstream_gamma * (peak / sigma_lo))
    k_hi = target / (downstream_gamma * (peak / sigma_hi))
    lo = x0 - 8 * sigma_lo
    hi = x0 + 8 * sigma_hi
    step = (hi - lo) / (n_samples - 1)
    corrected = {}
    for i in range(n_samples):
        x_orig = lo + i * step
        y = _split_gauss_density(film_params, x_orig)
        k = k_lo if x_orig < x0 else k_hi
        x_new = x0 + (x_orig - x0) / k
        corrected[x_new] = y
    return corrected

# Computed once at import instead of once per build_trix_cascade() call --
# depends only on TRIX_DEV7, not on the paper/look/variant being built.
TRIX_DEV7_REF_D = density_midpoint(TRIX_DEV7)

def build_trix_cascade(paper):
    """Tri-X dev7 negative × Polymax paper → transfer function E→reflectance.

    TRIX_DEV7's own reference point (its density-range midpoint) has no
    equivalent published LAD-style target the way the internegative does --
    this is a labeled fallback, not real calibration data, kept only because
    it's already been checked to perform well (Tri-X's own highlight/shadow
    headroom lands within rounding of the theoretical best case for every
    Polymax grade -- see tasks/DONE-07-... for the numbers). Don't copy this
    pattern for a new material without checking it the same way first.
    """
    return build_print_cascade([(TRIX_DEV7, True, 0, TRIX_DEV7_REF_D), (paper, True, 0, None)])

# =========================================================================
# LUT writers
# =========================================================================
def write_bw_lut(path, title, exposure_grid, xfer, size, use_hk, cs=COLORSPACES["adobergb"]):
    """B&W LUT: per-pixel spectral exposure + optional HK → negative×print
    cascade. `cs` picks the LUT module application colour space (see
    COLORSPACES); defaults to Adobe RGB. `exposure_grid` is a per-grid-point
    exposure list from trix_exposure_grid() (Ticket 21 — real spectral
    reconstruction per pixel, replacing the old fixed-weight-triple
    `R**wr * G**wg * B**wb` geometric mean), indexed in the same
    (bi,gi,ri)-nested order as this function's own grid loop. HK multipliers
    come from the cached get_hk_grid() (Ticket 22) instead of decoding RGB and
    calling hk_mul() per pixel -- decode is no longer needed here at all,
    since exposure_grid already holds the real per-pixel exposure."""
    enc,label=cs["enc"],cs["label"]
    hk_grid=get_hk_grid(size,cs) if use_hk else None
    with open(path,'w') as f:
        f.write(f'TITLE "{title}"\n')
        f.write(f'# {label} in/out. REPLACES AgX. {title}.\n')
        f.write(f'LUT_3D_SIZE {size}\nDOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n\n')
        for idx,E in enumerate(exposure_grid):
            if hk_grid is not None and E>1e-9: E*=hk_grid[idx]
            v=enc(xfer(E))
            f.write(f'{v:.6f} {v:.6f} {v:.6f}\n')

def write_color_lut(path, title, lw, xfers, size, use_hk, cs=COLORSPACES["adobergb"]):
    """Color LUT: per-layer exposure → per-layer film/paper cascade → RGB out.
    `cs` picks the LUT module application colour space (see COLORSPACES);
    defaults to Adobe RGB. `lw` is a per-layer, per-grid-point exposure grid
    from layer_exposure_grid() (Ticket 16 — real spectral reconstruction per
    pixel, replacing the old fixed-weight-triple `R*wr+G*wg+B*wb` dot
    product), indexed in the same (bi,gi,ri)-nested order as this function's
    own grid loop. HK multipliers come from the cached get_hk_grid() (Ticket
    22) instead of decoding RGB and calling hk_mul() per pixel -- decode is no
    longer needed here at all."""
    enc,label=cs["enc"],cs["label"]
    hk_grid=get_hk_grid(size,cs) if use_hk else None
    with open(path,'w') as f:
        f.write(f'TITLE "{title}"\n')
        f.write(f'# {label} in/out. REPLACES AgX. {title}.\n')
        f.write(f'LUT_3D_SIZE {size}\nDOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n\n')
        n_idx=len(lw[0])
        for idx in range(n_idx):
            hk=hk_grid[idx] if hk_grid is not None else 1.0
            out=[]
            for li in range(3):
                E=lw[li][idx]
                if E>1e-9: E*=hk
                out.append(xfers[li](E))
            f.write(f'{enc(out[0]):.6f} {enc(out[1]):.6f} {enc(out[2]):.6f}\n')

# =========================================================================
# Main
# =========================================================================
# key, file prefix, display name, spectral sensitivity, cascade-stage builder
# (given a layer index and the chosen paper's full 3-layer curve list,
# returns the ordered [(curve, increasing, start, ref_d), ...] list
# build_print_cascade() expects). All four are reversal (slide) films --
# none can go straight onto negative print paper, so all four route through
# INTERNEGATIVE_II_CURVES via the same 3-stage film->internegative->paper
# cascade (see README "What these replicate"). A camera negative (e.g.
# Portra) would use a 2-stage cascade instead, the same shape as
# build_trix_cascade() -- deliberately not part of this lineup, see
# tasks/DONE-07-... for why negative films were removed.
#
# Reference densities (ref_d):
#   - the internegative stage uses INTERNEGATIVE_II_LAD_AIM[li] -- Kodak's
#     own published calibration target for this exact film, from its real
#     datasheet (see that constant's own comment for the citation).
#   - each film's own stage uses density_midpoint() on its own curve --
#     reversal_grey_target() (18% reflectance) was tried here first since
#     it's the more "real" number, but it answers a different question than
#     this calibration point needs answered and measurably hurt highlight
#     headroom (see reversal_grey_target()'s own docstring for why). No
#     published aim density exists for "how much of a reversal film's own
#     range should map onto the internegative," the way one does for the
#     internegative's own target -- density_midpoint() is the documented
#     fallback for that, not presented as manufacturer data.
#
# Every stage's `start` is auto-detected per curve/layer via
# _detect_lead_noise_start() rather than hand-derived -- e.g. Provia 100F's
# own curve (layers 0 and 2) has the same kind of tiny leading Dmax-plateau
# digitization noise Kodak Supra Endura has, and it's a non-final stage
# whose own reference point gets searched too (see build_print_cascade
# docstring), but this now requires no per-film magic number to discover
# that or keep it correct as data changes.
#
# Each film's own-stage ref_d is precomputed once per layer here rather than
# inside the lambda below: density_midpoint() resamples the curve onto 41
# points and scans local slopes, and depends only on (film, li) -- not on
# paper/look/variant -- so recomputing it inside the lambda would redo that
# work on every stage_fn(li, paper) call in main()'s per-look loop instead
# of once (see tasks/11-...).
VELVIA_REF_D = [density_midpoint(c) for c in VELVIA_CURVES]
KODACHROME64_REF_D = [density_midpoint(c) for c in KODACHROME64_CURVES]
PROVIA100F_REF_D = [density_midpoint(c) for c in PROVIA100F_CURVES]
EKTACHROME100D_REF_D = [density_midpoint(c) for c in EKTACHROME100D_CURVES]

def _reversal_stage_fn(film_curves, film_ref_d):
    """Builds a COLOR_FILMS stage-list function for a 3-layer reversal film:
    its own curve -> the internegative -> whichever paper is passed in at
    call time. The only axis of variation across films is which curve list
    and ref_d list get closed over here; start indices are always auto-
    detected per curve/layer via _detect_lead_noise_start()."""
    return lambda li, paper: [
        (film_curves[li], False, _detect_lead_noise_start(film_curves[li], False), film_ref_d[li]),
        (INTERNEGATIVE_II_CURVES[li], True, _detect_lead_noise_start(INTERNEGATIVE_II_CURVES[li], True), INTERNEGATIVE_II_LAD_AIM[li]),
        (paper[li], True, _detect_lead_noise_start(paper[li], True), None)]

COLOR_FILMS = [
    ("velvia", "Velvia50", "Velvia 50", VELVIA_SENS,
     _reversal_stage_fn(VELVIA_CURVES, VELVIA_REF_D)),
    ("kodachrome64", "Kodachrome64", "Kodachrome 64", KODACHROME64_SENS,
     _reversal_stage_fn(KODACHROME64_CURVES, KODACHROME64_REF_D)),
    ("provia100f", "Provia100F", "Fuji Provia 100F", PROVIA100F_SENS,
     _reversal_stage_fn(PROVIA100F_CURVES, PROVIA100F_REF_D)),
    ("ektachrome100d", "Ektachrome100D", "Kodak Ektachrome 100D", EKTACHROME100D_SENS,
     _reversal_stage_fn(EKTACHROME100D_CURVES, EKTACHROME100D_REF_D)),
]
COLOR_FILM_KEYS = [f[0] for f in COLOR_FILMS]

# =========================================================================
# Direct-print (no internegative) cascades for the same four reversal films,
# onto DIRECT_PRINT_PAPERS instead of through INTERNEGATIVE_II_CURVES +
# PAPER_LADDER. COLOR_FILMS/_reversal_stage_fn() above is deliberately left
# untouched -- this is a second, additional route for each film, not a
# replacement (see GAMMA_CORRECT_TARGET's comment for why the internegative
# route is a separate, not-yet-revisited problem).
# =========================================================================
def _direct_print_stage_fn(film_ref_d, film_fit):
    """Builds a 2-stage (film -> paper, no internegative) stage-list
    function for one of DIRECT_PRINT_PAPERS. `film_fit` is that film's own
    *_SPLITGAUSS_FIT (one fitted-model tuple per layer, see
    GAMMA_CORRECT_TARGET's comment for what the model is and why). Each
    layer's own reversal curve is gamma-corrected (gamma_correct_curve())
    using *that specific paper layer's own* real digitized-curve local gamma
    (`_digitized_local_gamma()`, Ticket 19 -- not the fitted model: measured
    gamma_digitized(lhg)/gamma_fitted(lhg) ratios of 0.84-0.98 on these
    exact papers, since build_print_cascade() renders through the digitized
    curve, never the fit), evaluated exactly at that paper layer's own real
    grey-reproduction exposure (`lhg`, found via _find_anchor() on the
    paper's real digitized curve the same way build_print_cascade() itself
    finds it for the final stage) as the downstream gamma -- not a blended
    film-wide or paper-wide number -- so R/G/B each get the correction their
    own physical channel actually needs. `paper_fit` is accepted but no
    longer used here (kept so all three routes -- direct-print, negative,
    and Ticket 20's eventual internegative fix -- share one `(li, paper,
    paper_fit)` stage_fn arity; see Ticket 19/20 for why DIRECT_PRINT_PAPER_FIT
    isn't deleted outright). `film_ref_d[li]` is passed through unchanged as
    the corrected stage's own `ref_d` -- build_print_cascade() finds wherever
    the corrected curve reproduces that density via _find_anchor(),
    regardless of where gamma_correct_curve() placed it (see that function's
    own docstring for
    why no pivot bookkeeping is needed here)."""
    def stage_fn(li, paper, paper_fit):
        pxs, pys = _sc(paper[li])
        lhg = _find_anchor(pxs, pys, _grey_target_density(pys), increasing=False,
                            start=_detect_lead_noise_start(paper[li], False))
        downstream_gamma = _digitized_local_gamma(pxs, pys, lhg)
        corrected = gamma_correct_curve(film_fit[li], film_ref_d[li], downstream_gamma)
        return [
            (corrected, False, 0, film_ref_d[li]),
            (paper[li], False, _detect_lead_noise_start(paper[li], False), None)]
    return stage_fn

DIRECT_PRINT_STAGE_FNS = {
    "velvia": _direct_print_stage_fn(VELVIA_REF_D, VELVIA_SPLITGAUSS_FIT),
    "kodachrome64": _direct_print_stage_fn(KODACHROME64_REF_D, KODACHROME64_SPLITGAUSS_FIT),
    "provia100f": _direct_print_stage_fn(PROVIA100F_REF_D, PROVIA100F_SPLITGAUSS_FIT),
    "ektachrome100d": _direct_print_stage_fn(EKTACHROME100D_REF_D, EKTACHROME100D_SPLITGAUSS_FIT),
}

# =========================================================================
# Camera color *negative* films -- Kodak Portra 400, Kodak Ektar 100, Kodak
# Gold 200, Fuji Superia Reala. Unlike COLOR_FILMS above, these print
# straight onto a real paper with a 2-stage cascade (own curve -> paper),
# the same shape build_trix_cascade() uses -- never through
# INTERNEGATIVE_II_CURVES, since these are already camera negatives, not
# reversal originals needing duplication. Kept as a genuinely separate
# lineup/loop from COLOR_FILMS per CLAUDE.md (folding negative and reversal
# films into one list was tried once and reverted).
#
# Reuses PAPER_LADDER/COLOR_LOOKS -- the same 5 real RA-4 papers, which
# live in film_paper_filter_data/papers/color/for_negatives/ and are
# already literally "for negatives," not repurposed reversal-print stock.
#
# ref_d: each film's own stage uses density_midpoint() on its own curve,
# same fallback and same justification as TRIX_DEV7_REF_D -- none of the
# four source JSONs (film_paper_filter_data/films/color/negative/*.json)
# carry a populated `lad` field (checked directly: all four are None), so
# no published aim density exists to prefer over it.
# =========================================================================
PORTRA400_REF_D = [density_midpoint(c) for c in PORTRA400_CURVES]
EKTAR100_REF_D = [density_midpoint(c) for c in EKTAR100_CURVES]
GOLD200_REF_D = [density_midpoint(c) for c in GOLD200_CURVES]
ULTRAMAX400_REF_D = [density_midpoint(c) for c in ULTRAMAX400_CURVES]
SUPERIA_REALA_REF_D = [density_midpoint(c) for c in SUPERIA_REALA_CURVES]
SUPERIA_XTRA400_REF_D = [density_midpoint(c) for c in SUPERIA_XTRA400_CURVES]

# Fitted split-normal-CDF parameters (see GAMMA_CORRECT_TARGET's comment
# block for the model and physical justification), produced the same way
# and by the same tool (tools/gamma_correction_fit/main.py) as the reversal-
# film/direct-print-paper fits above -- added after real-world use of the
# corrected direct-print route showed negative films rendering *punchier*
# than the freshly-corrected reversal route, backwards from the real
# photographic hierarchy (reversal stock is the punchier material). Root
# cause, measured directly: negative films' own native gamma is correctly
# low (0.47-0.68 via _measured_gamma(), matching the low-native-gamma design
# every color negative stock uses so it prints at roughly unity contrast on
# normal paper) -- but PAPER_LADDER's own real measured gammas are steep
# (2.5-4.3 across all 5 papers, including "ExtraSoft") and had never been
# checked against Jones's rule, since PAPER_LADDER's contrast ladder was
# derived from measuring rendered *span* (see "Choosing a print paper"), not
# from a faithful-reproduction target. Negative films were landing at local
# gamma ~1.4-1.7 near grey as a result, versus the direct-print route's
# ~1.0-1.1 -- this brings them to the same cited target.
PORTRA400_SPLITGAUSS_FIT = [(-0.70038, 0.03093, 2.57193, 1.65061, 1.71457), (-0.86103, 0.45501, 2.93445, 1.56294, 1.72233), (-0.81425, 0.49958, 3.84205, 1.89852, 1.99513)]
EKTAR100_SPLITGAUSS_FIT = [(-0.4743, 0.13059, 2.18973, 1.14815, 1.47336), (-0.40382, 0.54321, 2.76455, 1.2091, 1.62263), (-0.3225, 0.64147, 3.65097, 1.5602, 1.82413)]
GOLD200_SPLITGAUSS_FIT = [(-0.90396, 0.13546, 1.97904, 1.2081, 1.28289), (-0.97357, 0.52209, 2.45108, 1.21737, 1.30855), (-0.96708, 0.71997, 2.95163, 1.3048, 1.39998)]
ULTRAMAX400_SPLITGAUSS_FIT = [(-0.95426, 0.11996, 2.31556, 1.5183, 1.63969), (-1.08119, 0.48849, 2.80918, 1.53045, 1.67593), (-0.8204, 0.72756, 3.58136, 1.71247, 1.80699)]
SUPERIA_REALA_SPLITGAUSS_FIT = [(-0.66916, 0.28091, 2.43622, 1.14306, 1.24322), (-0.76371, 0.45357, 2.83446, 1.28848, 1.38359), (-0.7417, 0.92877, 3.12751, 1.16353, 1.21494)]
SUPERIA_XTRA400_SPLITGAUSS_FIT = [(-0.87916, -0.02129, 2.69236, 1.60197, 1.68601), (-1.0027, 0.28678, 3.06989, 1.47399, 1.57426), (-1.07883, 0.59911, 3.28507, 1.30548, 1.48051)]
EXTRASOFT_LADDER_SPLITGAUSS_FIT = [(1.15345, 0.1427, 2.8191, 0.31865, 0.26408), (1.15143, 0.16865, 2.72305, 0.32574, 0.25562), (1.13107, 0.16119, 2.49537, 0.32053, 0.27389)]
SOFT_LADDER_SPLITGAUSS_FIT = [(1.91889, 0.17396, 2.74557, 0.27598, 0.23077), (1.91835, 0.17973, 2.67193, 0.29549, 0.22953), (1.89651, 0.18107, 2.44614, 0.28978, 0.24665)]
NORMAL_LADDER_SPLITGAUSS_FIT = [(-1.41765, 0.0994, 2.60846, 0.31537, 0.31046), (-1.41426, 0.10326, 2.60966, 0.31249, 0.35737), (-1.42853, 0.10225, 2.402, 0.30765, 0.26383)]
PUNCHY_LADDER_SPLITGAUSS_FIT = [(1.09443, 0.11165, 2.66888, 0.30535, 0.38118), (1.05771, 0.11567, 2.45743, 0.28037, 0.26923), (1.05294, 0.06956, 2.45706, 0.28822, 0.26974)]
EXTRAPUNCHY_LADDER_SPLITGAUSS_FIT = [(-1.31601, 0.09836, 2.63391, 0.2441, 0.18074), (-1.30717, 0.09246, 2.57494, 0.24627, 0.2234), (-1.32696, 0.10403, 2.49781, 0.24027, 0.16483)]
PAPER_LADDER_FIT = {
    "ExtraSoft": EXTRASOFT_LADDER_SPLITGAUSS_FIT, "Soft": SOFT_LADDER_SPLITGAUSS_FIT,
    "Normal": NORMAL_LADDER_SPLITGAUSS_FIT, "Punchy": PUNCHY_LADDER_SPLITGAUSS_FIT,
    "ExtraPunchy": EXTRAPUNCHY_LADDER_SPLITGAUSS_FIT,
}

def _negative_gammacorrect_stage_fn(film_ref_d, film_fit):
    """Builds a NEGATIVE_FILMS stage-list function for a 3-layer camera
    negative: its own curve, gamma-corrected (gamma_correct_curve(), see
    GAMMA_CORRECT_TARGET's comment) against whichever PAPER_LADDER paper is
    passed in at call time -- whichever paper is passed at call time -> the
    same paper directly, no internegative stage. Mirrors
    _direct_print_stage_fn()'s shape (fitted-model film-side correction,
    digitized-curve secant for the paper-side downstream gamma -- Ticket 19,
    `_digitized_local_gamma()` -- at each material's own real operating
    point) but with increasing=True (density rises with exposure, like
    TRIX_DEV7 and every PAPER_LADDER paper) on both stages instead of False
    on the first -- replaces the former, uncorrected _negative_stage_fn()
    (see this constant block's own comment for why the correction was
    added). `paper_fit` is accepted but unused here for the same reason as
    _direct_print_stage_fn()'s -- shared 3-arg stage_fn arity across routes."""
    def stage_fn(li, paper, paper_fit):
        pxs, pys = _sc(paper[li])
        lhg = _find_anchor(pxs, pys, _grey_target_density(pys), increasing=True,
                            start=_detect_lead_noise_start(paper[li], True))
        downstream_gamma = _digitized_local_gamma(pxs, pys, lhg)
        corrected = gamma_correct_curve(film_fit[li], film_ref_d[li], downstream_gamma)
        return [
            (corrected, True, 0, film_ref_d[li]),
            (paper[li], True, _detect_lead_noise_start(paper[li], True), None)]
    return stage_fn

NEGATIVE_FILMS = [
    ("negative-portra-400", "Portra400", "Kodak Portra 400", PORTRA400_SENS,
     _negative_gammacorrect_stage_fn(PORTRA400_REF_D, PORTRA400_SPLITGAUSS_FIT)),
    ("negative-ektar-100", "Ektar100", "Kodak Ektar 100", EKTAR100_SENS,
     _negative_gammacorrect_stage_fn(EKTAR100_REF_D, EKTAR100_SPLITGAUSS_FIT)),
    ("negative-gold-200", "Gold200", "Kodak Gold 200", GOLD200_SENS,
     _negative_gammacorrect_stage_fn(GOLD200_REF_D, GOLD200_SPLITGAUSS_FIT)),
    ("negative-ultramax-400", "Ultramax400", "Kodak Ultramax 400", ULTRAMAX400_SENS,
     _negative_gammacorrect_stage_fn(ULTRAMAX400_REF_D, ULTRAMAX400_SPLITGAUSS_FIT)),
    ("negative-superia-reala", "SuperiaReala", "Fuji Superia Reala", SUPERIA_REALA_SENS,
     _negative_gammacorrect_stage_fn(SUPERIA_REALA_REF_D, SUPERIA_REALA_SPLITGAUSS_FIT)),
    ("negative-superia-xtra-400", "SuperiaXtra400", "Fuji Superia X-tra 400", SUPERIA_XTRA400_SENS,
     _negative_gammacorrect_stage_fn(SUPERIA_XTRA400_REF_D, SUPERIA_XTRA400_SPLITGAUSS_FIT)),
]
NEGATIVE_FILM_KEYS = [f[0] for f in NEGATIVE_FILMS]

def main():
    global GAMMA_CORRECT_TARGET
    here=os.path.dirname(os.path.abspath(__file__))
    p=argparse.ArgumentParser(description="Generate Tri-X 400, Velvia 50, Kodachrome 64, Fuji Provia 100F and Kodak Ektachrome 100D film emulation LUTs.")
    p.add_argument('--size',type=int,default=65,help='LUT grid N (N^3). Default 65.')
    p.add_argument('--output',default=here)
    p.add_argument('--only',nargs='+',choices=['trix']+COLOR_FILM_KEYS+NEGATIVE_FILM_KEYS,help='Generate only these film(s). Default: all.')
    p.add_argument('--colorspace',choices=list(COLORSPACES),default='adobergb',
                    help="LUT module application color space: 'adobergb' (default) or 'pq2020' (Rec.2020 primaries + SMPTE ST 2084 PQ).")
    p.add_argument('--gamma',type=float,default=GAMMA_CORRECT_TARGET,
                    help=f'Jones system-gamma target for the direct-print and negative-film gamma correction '
                         f'(see GAMMA_CORRECT_TARGET comment block) -- real, cited range is roughly 1.1 '
                         f'(Bartleson & Breneman light-surround/reflection-print) to 1.5-1.6 (dark-surround/'
                         f'projection); 1.2-1.3 is their separate TV/self-luminous-display figure, corroborated '
                         f'by Roufs et al.\'s own slide-scanner-to-monitor measurement. Default {GAMMA_CORRECT_TARGET}.')
    args=p.parse_args()
    if not 9<=args.size<=129: p.error("--size 9..129")
    only=set(args.only) if args.only else {'trix',*COLOR_FILM_KEYS,*NEGATIVE_FILM_KEYS}
    cs=COLORSPACES[args.colorspace]
    GAMMA_CORRECT_TARGET=args.gamma

    t0=time.time(); total=0

    # --- Tri-X ---
    if 'trix' in only:
        trix_grids={fn:trix_exposure_grid(TRIX_SENS,FILTERS.get(fn),get_spectrum_grid(args.size,cs)) for fn in FILTER_ORDER}
        for variant,use_hk in [("trix_classic",False),("trix_modern",True)]:
            outdir=os.path.join(args.output,variant)
            os.makedirs(outdir,exist_ok=True)
            print(f"\n{'='*60}\n{variant} ({'+ HK' if use_hk else 'no HK'})  |  {args.size}^3  |  {cs['label']}  |  {len(LOOKS)*len(FILTER_ORDER)} LUTs")
            for look,grade in LOOKS:
                xfer=build_trix_cascade(POLY[grade])
                for fn in FILTER_ORDER:
                    fname=f"TriX_{fn}_{look}.cube"
                    t1=time.time()
                    write_bw_lut(os.path.join(outdir,fname),
                                 f"Tri-X {fn} {look}",trix_grids[fn],xfer,args.size,use_hk,cs=cs)
                    total+=1
                    print(f"  {fname:<42s} ({time.time()-t1:.1f}s)")

    # --- Color films: Velvia 50, Kodachrome 64, Provia 100F, Ektachrome 100D ---
    # Every PAPER_LADDER look is a real paper choice through the internegative
    # route, no synthetic gamma. Each film also gets DIRECT_PRINT_LOOKS: the
    # same reversal curve, gamma-corrected (see GAMMA_CORRECT_TARGET), printed
    # straight onto a real direct-print paper with no internegative stage --
    # see DIRECT_PRINT_STAGE_FNS's own comment for why this is a second route
    # per film rather than a replacement for the PAPER_LADDER one.
    for key,fileprefix,dispname,sens,stage_fn in COLOR_FILMS:
        if key not in only: continue
        lw=layer_exposure_grid(sens,get_spectrum_grid(args.size,cs))
        outdir=os.path.join(args.output,key)
        os.makedirs(outdir,exist_ok=True)
        n_luts=(len(COLOR_LOOKS)+len(DIRECT_PRINT_LOOKS))*2
        print(f"\n{'='*60}\n{key} ({dispname})  |  {args.size}^3  |  {cs['label']}  |  {n_luts} LUTs")
        for look in COLOR_LOOKS:
            paper=PAPER_LADDER[look]
            xfers=[build_print_cascade(stage_fn(li,paper)) for li in range(3)]
            for variant_label,use_hk in [("Classic",False),("Modern",True)]:
                fname=f"{fileprefix}_{variant_label}_{look}.cube"
                t1=time.time()
                write_color_lut(os.path.join(outdir,fname),
                                f"{dispname} {variant_label} {look}",lw,xfers,args.size,use_hk,cs=cs)
                total+=1
                print(f"  {fname:<42s} ({time.time()-t1:.1f}s)")
        direct_stage_fn=DIRECT_PRINT_STAGE_FNS[key]
        for look in DIRECT_PRINT_LOOKS:
            paper=DIRECT_PRINT_PAPERS[look]
            paper_fit=DIRECT_PRINT_PAPER_FIT[look]
            xfers=[build_print_cascade(direct_stage_fn(li,paper,paper_fit)) for li in range(3)]
            for variant_label,use_hk in [("Classic",False),("Modern",True)]:
                fname=f"{fileprefix}_{variant_label}_{look}.cube"
                t1=time.time()
                write_color_lut(os.path.join(outdir,fname),
                                f"{dispname} {variant_label} {look}",lw,xfers,args.size,use_hk,cs=cs)
                total+=1
                print(f"  {fname:<42s} ({time.time()-t1:.1f}s)")

    # --- Negative films: Portra 400, Ektar 100, Gold 200, Superia Reala ---
    # Same PAPER_LADDER/COLOR_LOOKS as the reversal films, but a 2-stage
    # own-curve->paper cascade (no internegative) via NEGATIVE_FILMS -- kept
    # as a separate lineup/loop from COLOR_FILMS on purpose, see that
    # constant's own comment.
    for key,fileprefix,dispname,sens,stage_fn in NEGATIVE_FILMS:
        if key not in only: continue
        lw=layer_exposure_grid(sens,get_spectrum_grid(args.size,cs))
        outdir=os.path.join(args.output,key)
        os.makedirs(outdir,exist_ok=True)
        print(f"\n{'='*60}\n{key} ({dispname})  |  {args.size}^3  |  {cs['label']}  |  {len(COLOR_LOOKS)*2} LUTs")
        for look in COLOR_LOOKS:
            paper=PAPER_LADDER[look]
            paper_fit=PAPER_LADDER_FIT[look]
            xfers=[build_print_cascade(stage_fn(li,paper,paper_fit)) for li in range(3)]
            for variant_label,use_hk in [("Classic",False),("Modern",True)]:
                fname=f"{fileprefix}_{variant_label}_{look}.cube"
                t1=time.time()
                write_color_lut(os.path.join(outdir,fname),
                                f"{dispname} {variant_label} {look}",lw,xfers,args.size,use_hk,cs=cs)
                total+=1
                print(f"  {fname:<42s} ({time.time()-t1:.1f}s)")

    print(f"\nDone. {total} LUTs in {time.time()-t0:.0f}s")

if __name__=='__main__':
    main()
