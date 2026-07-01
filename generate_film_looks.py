#!/usr/bin/env python3
"""
generate_film_looks.py — Kodak Tri-X 400 + Fuji Velvia 50 film emulation LUTs

Generates 4 folders of curated film-look LUTs that replace your tone mapper:

  trix_classic/     — 36 LUTs (6 looks × 6 filters), pure film physics
  trix_modern/      — 36 LUTs, adds Helmholtz-Kohlrausch perceptual correction
  velvia_classic/   —  6 LUTs (6 looks, no filters), pure film physics
  velvia_modern/    —  6 LUTs, adds HK correction for color

Total: 84 LUTs. See README.md for setup and explanation.

Usage:
  python generate_film_looks.py                  # 65^3 default
  python generate_film_looks.py --size 33        # faster, smaller
  python generate_film_looks.py --only trix      # just Tri-X
  python generate_film_looks.py --only velvia    # just Velvia
  python generate_film_looks.py --help
"""

import argparse, math, os, time

# =========================================================================
# CIE 1931 2-deg observer + D65
# =========================================================================
CIE = {400:(0.01431,0.000396,0.06785),410:(0.04351,0.00121,0.2074),420:(0.13438,0.004,0.6456),430:(0.2839,0.0116,1.3856),440:(0.34828,0.023,1.74706),450:(0.3362,0.038,1.77211),460:(0.2908,0.06,1.6692),470:(0.19536,0.09098,1.28764),480:(0.09564,0.13902,0.81295),490:(0.03201,0.20802,0.46518),500:(0.0049,0.323,0.272),510:(0.0093,0.503,0.1582),520:(0.06327,0.71,0.07825),530:(0.1655,0.862,0.04216),540:(0.2904,0.954,0.0203),550:(0.43345,0.995,0.00875),560:(0.5945,0.995,0.0039),570:(0.7621,0.952,0.0021),580:(0.9163,0.87,0.00165),590:(1.0263,0.757,0.0011),600:(1.0622,0.631,0.0008),610:(1.0026,0.503,0.00034),620:(0.85445,0.381,0.00019),630:(0.6424,0.265,0.00005),640:(0.4479,0.175,0.00002),650:(0.2835,0.107,0),660:(0.1649,0.061,0),670:(0.0874,0.032,0),680:(0.04677,0.017,0),690:(0.0227,0.00821,0),700:(0.01135,0.004102,0)}
D65 = {400:82.75,410:91.49,420:93.43,430:86.68,440:104.86,450:117.01,460:117.81,470:114.86,480:115.09,490:108.81,500:109.35,510:107.8,520:104.79,530:107.69,540:104.41,550:104.05,560:100.0,570:96.33,580:95.79,590:88.69,600:90.01,610:89.6,620:87.7,630:83.29,640:83.7,650:80.03,660:80.21,670:82.28,680:78.28,690:69.72,700:71.61}

# =========================================================================
# Adobe RGB (1998)
# =========================================================================
_MA = [[2.04158790,-0.56500697,-0.34473135],[-0.96924364,1.87596750,0.04155506],[0.01344428,-0.11836239,1.01517499]]
_MA_INV = [[0.57667,0.18556,0.18823],[0.29734,0.62736,0.07529],[0.02703,0.07069,0.99134]]
_SSF = {}
for _wl in range(400,710,10):
    x,y,z = CIE[_wl]
    _SSF[_wl] = tuple(max(sum(_MA[r][c]*v for c,v in enumerate((x,y,z))),0) for r in range(3))
_AG = 2.19921875
def adec(v): return max(0.0,v)**_AG
def aenc(c): return max(0.0,min(1.0,c))**(1.0/_AG)

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
# colours (this tool decodes Adobe RGB) routinely exceed that C* range and produce
# unbounded multipliers when fed through the formula's linear C* term. 3.0x gives
# headroom above the largest paper-supported ratio while cutting off extrapolation
# far beyond it. See README "Helmholtz-Kohlrausch correction" for the full derivation.
HK_MAX_MUL = 3.0

def hk_mul(R,G,B):
    """HK exposure multiplier from linear Adobe RGB input, capped at HK_MAX_MUL."""
    if R<1e-6 and G<1e-6 and B<1e-6: return 1.0
    X=_MA_INV[0][0]*R+_MA_INV[0][1]*G+_MA_INV[0][2]*B
    Y=_MA_INV[1][0]*R+_MA_INV[1][1]*G+_MA_INV[1][2]*B
    Z=_MA_INV[2][0]*R+_MA_INV[2][1]*G+_MA_INV[2][2]*B
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
LOOKS = [("ExtraSoft","0"),("Soft","1"),("Normal","2"),("Punchy","3"),("ExtraPunchy","4"),("Hard","5")]
FILTER_ORDER = ["NoFilter","Yellow8","Orange21","Red25","Green58","Blue47"]
# Velvia parametric contrast (no real multi-grade data exists)
VELVIA_GAMMA = {"ExtraSoft":0.75,"Soft":0.85,"Normal":1.0,"Punchy":1.12,"ExtraPunchy":1.25,"Hard":1.45}
GREY = 0.18

# =========================================================================
# Weight computation
# =========================================================================
def _weights(sens, filt=None):
    """Compute colour->grey weights from spectral sensitivity + optional filter."""
    sk=sorted(sens); sv=[sens[k] for k in sk]
    ft=None
    if filt:
        fk=sorted(filt); fv=[filt[k] for k in fk]; ft=(fk,fv)
    wr=wg=wb=0.0
    for wl in range(400,710,10):
        s=_il10(sk,sv,wl)
        if ft: s*=_il(ft[0],ft[1],wl)/100.0
        d=D65[wl]; r,g,b=_SSF[wl]
        wr+=s*d*r; wg+=s*d*g; wb+=s*d*b
    tot=wr+wg+wb
    return (wr/tot,wg/tot,wb/tot) if tot>0 else (1/3,1/3,1/3)

def velvia_layer_weights():
    """3×3 matrix: per-layer weights mapping Adobe RGB → layer exposure."""
    return [_weights(layer) for layer in VELVIA_SENS]

# =========================================================================
# Cascade builders
# =========================================================================
def _find_anchor(xs, ys, td, increasing):
    """Find x where digitized curve xs->ys crosses target density td.

    xs/ys must be sorted by increasing exposure (xs ascending). `increasing`
    says which direction density moves with exposure for this curve: True for
    negative/print curves (density rises with exposure, e.g. Polymax), False
    for reversal dye layers (density falls with exposure). Clamps to the
    nearest endpoint if td is outside the digitized range.

    Scans from index 0 — the well-behaved, non-solarized end of every curve
    in this dataset — and returns the first bracketing crossing, which is the
    physically correct one even though several of the digitized curves wobble
    non-monotonically further out (Polymax grades 0/1 dip near Dmax; all three
    Velvia dye layers reverse/solarize at the extreme-overexposure tail). To
    keep that assumption honest, raise instead of silently misfiring if the
    curve isn't monotonic in the region actually scanned before the crossing.
    """
    if increasing:
        if td<=ys[0]: return xs[0]
        if td>=ys[-1]: return xs[-1]
        for i in range(len(xs)-1):
            if ys[i]>ys[i+1]:
                raise ValueError(f"_find_anchor: curve not monotonic before crossing (index {i}: {ys[i]} > {ys[i+1]})")
            if ys[i]==ys[i+1]:
                if td==ys[i]: return xs[i]
                continue
            if ys[i]<=td<=ys[i+1]:
                t=(td-ys[i])/(ys[i+1]-ys[i]); return xs[i]*(1-t)+xs[i+1]*t
    else:
        if td>=ys[0]: return xs[0]
        if td<=ys[-1]: return xs[-1]
        for i in range(len(xs)-1):
            if ys[i]<ys[i+1]:
                raise ValueError(f"_find_anchor: curve not monotonic before crossing (index {i}: {ys[i]} < {ys[i+1]})")
            if ys[i]==ys[i+1]:
                if td==ys[i]: return xs[i]
                continue
            if ys[i]>=td>=ys[i+1]:
                t=(td-ys[i])/(ys[i+1]-ys[i]); return xs[i]*(1-t)+xs[i+1]*t
    raise ValueError("_find_anchor: target density not found in curve range")

def build_trix_cascade(paper):
    """Tri-X dev7 negative × Polymax paper → transfer function E→reflectance."""
    nxs,nys=_sc(TRIX_DEV7); pxs,pys=_sc(paper)
    na=0.5*(nxs[0]+nxs[-1]); dn=_il(nxs,nys,na); pdm=min(pys)
    td=pdm-math.log10(0.18)
    lhg=_find_anchor(pxs,pys,td,increasing=True)
    pl=lhg+dn
    def xfer(E):
        lh=nxs[0]-10 if E<=1e-9 else na+math.log10(E/GREY)
        dp=_il(pxs,pys,pl-_il(nxs,nys,lh))
        return max(0.0,min(1.0,10**(-(dp-pdm))))
    return xfer

def build_velvia_layer(curve, gamma_adj):
    """Single Velvia dye layer: reversal curve + parametric contrast."""
    xs,ys=_sc(curve); dm=min(ys)
    # Anchor: find logH where D gives 18% transmittance (reversal: D falls with exposure)
    td=dm-math.log10(0.18)  # target D
    anc=_find_anchor(xs,ys,td,increasing=False)
    def xfer(E):
        lh=xs[0]-10 if E<=1e-9 else anc+math.log10(E/GREY)
        D=_il(xs,ys,lh); T=10**(-(D-dm))
        if gamma_adj!=1.0 and T>1e-9:
            T=GREY*(T/GREY)**gamma_adj
        return max(0.0,min(1.0,T))
    return xfer

# =========================================================================
# LUT writers
# =========================================================================
def write_bw_lut(path, title, weights, xfer, size, use_hk):
    """B&W LUT: geometric mean + optional HK → negative×print cascade."""
    wr,wg,wb=weights; n=size-1
    with open(path,'w') as f:
        f.write(f'TITLE "{title}"\n')
        f.write(f'# Adobe RGB in/out. REPLACES AgX. R={wr:.4f} G={wg:.4f} B={wb:.4f}\n')
        f.write(f'LUT_3D_SIZE {size}\nDOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n\n')
        for bi in range(size):
            for gi in range(size):
                for ri in range(size):
                    R,G,B=adec(ri/n),adec(gi/n),adec(bi/n)
                    E=1.0
                    if wr>0: E*=R**wr if R>0 else 0.0
                    if E>0 and wg>0: E*=G**wg if G>0 else 0.0
                    if E>0 and wb>0: E*=B**wb if B>0 else 0.0
                    if use_hk and E>1e-9: E*=hk_mul(R,G,B)
                    v=aenc(xfer(E))
                    f.write(f'{v:.6f} {v:.6f} {v:.6f}\n')

def write_color_lut(path, title, lw, xfers, size, use_hk):
    """Color LUT: per-layer exposure → per-layer reversal curve → RGB out."""
    n=size-1
    with open(path,'w') as f:
        f.write(f'TITLE "{title}"\n')
        f.write(f'# Adobe RGB in/out. REPLACES AgX. Velvia 50 color reversal.\n')
        f.write(f'LUT_3D_SIZE {size}\nDOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n\n')
        for bi in range(size):
            for gi in range(size):
                for ri in range(size):
                    R,G,B=adec(ri/n),adec(gi/n),adec(bi/n)
                    # Per-layer exposure (arithmetic, not geometric — each layer sees its own band)
                    hk=hk_mul(R,G,B) if use_hk else 1.0
                    out=[]
                    for li in range(3):
                        wr,wg,wb=lw[li]
                        E=wr*R+wg*G+wb*B
                        if E>1e-9: E*=hk
                        out.append(xfers[li](E))
                    f.write(f'{aenc(out[0]):.6f} {aenc(out[1]):.6f} {aenc(out[2]):.6f}\n')

# =========================================================================
# Main
# =========================================================================
def main():
    here=os.path.dirname(os.path.abspath(__file__))
    p=argparse.ArgumentParser(description="Generate Tri-X 400 + Velvia 50 film emulation LUTs.")
    p.add_argument('--size',type=int,default=65,help='LUT grid N (N^3). Default 65.')
    p.add_argument('--output',default=here)
    p.add_argument('--only',choices=['trix','velvia'],help='Generate only one stock.')
    args=p.parse_args()
    if not 9<=args.size<=129: p.error("--size 9..129")

    t0=time.time(); total=0

    # --- Tri-X ---
    if args.only!='velvia':
        trix_weights={fn:_weights(TRIX_SENS,FILTERS.get(fn)) for fn in FILTER_ORDER}
        for variant,use_hk in [("trix_classic",False),("trix_modern",True)]:
            outdir=os.path.join(args.output,variant)
            os.makedirs(outdir,exist_ok=True)
            print(f"\n{'='*60}\n{variant} ({'+ HK' if use_hk else 'no HK'})  |  {args.size}^3  |  {len(LOOKS)*len(FILTER_ORDER)} LUTs")
            for look,grade in LOOKS:
                xfer=build_trix_cascade(POLY[grade])
                for fn in FILTER_ORDER:
                    fname=f"TriX_{fn}_{look}.cube"
                    t1=time.time()
                    write_bw_lut(os.path.join(outdir,fname),
                                 f"Tri-X {fn} {look}",trix_weights[fn],xfer,args.size,use_hk)
                    total+=1
                    print(f"  {fname:<42s} ({time.time()-t1:.1f}s)")

    # --- Velvia ---
    if args.only!='trix':
        vlw=velvia_layer_weights()
        for variant,use_hk in [("velvia_classic",False),("velvia_modern",True)]:
            outdir=os.path.join(args.output,variant)
            os.makedirs(outdir,exist_ok=True)
            print(f"\n{'='*60}\n{variant} ({'+ HK' if use_hk else 'no HK'})  |  {args.size}^3  |  {len(LOOKS)} LUTs")
            for look,_ in LOOKS:
                gm=VELVIA_GAMMA[look]
                xfers=[build_velvia_layer(VELVIA_CURVES[li],gm) for li in range(3)]
                fname=f"Velvia50_{look}.cube"
                t1=time.time()
                write_color_lut(os.path.join(outdir,fname),
                                f"Velvia 50 {look}",vlw,xfers,args.size,use_hk)
                total+=1
                print(f"  {fname:<42s} ({time.time()-t1:.1f}s)")

    print(f"\nDone. {total} LUTs in {time.time()-t0:.0f}s")

if __name__=='__main__':
    main()
