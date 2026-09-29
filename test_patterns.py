"""Validate each bullish detector on constructed textbook shapes + no false positives."""
import numpy as np, pandas as pd
from ipo_momentum import patterns as P

rng = np.random.default_rng(42)

def stretch(a, n):
    a = np.asarray(a, float)
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a)

def legs(points, per=4):
    """Concatenate straight legs between vertices, preserving sharp turning points."""
    out = []
    for i in range(len(points) - 1):
        out += list(np.linspace(points[i], points[i + 1], per, endpoint=False))
    out.append(points[-1])
    return np.array(out, float)

def mk(closes, opens=None, highs=None, lows=None, vols=None, noise=0.0):
    c = np.asarray(closes, float)
    if noise:
        c = c * (1 + rng.normal(0, noise, len(c)))
    o = np.asarray(opens, float) if opens is not None else np.r_[c[0], c[:-1]]
    h = np.asarray(highs, float) if highs is not None else np.maximum(c, o) * 1.003
    l = np.asarray(lows, float) if lows is not None else np.minimum(c, o) * 0.997
    v = np.asarray(vols, float) if vols is not None else np.full(len(c), 1000.0)
    idx = pd.date_range("2025-01-01", periods=len(c), freq="B")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=idx)

def show(label, df, want):
    got = P.detect_patterns(df)
    gn = [f"{h['pattern']}[{h['status']}]" for h in got]
    ok = any(want in g for g in gn)
    print(f"{'PASS' if ok else 'FAIL'}  {label:22} want~{want:26} -> {gn}")
    return ok

results = []

# 1. HTF: +120% pole then tight flag then breakout
pole = np.linspace(10, 22, 30); flagseg = np.array([22, 21.4, 21, 21.3, 20.8, 21, 21.2, 22.4])
results.append(show("high tight flag", mk(np.r_[pole, flagseg]), "High Tight Flag"))

# 2. Channel: flat band with touches, marubozu breakout
band = []
for _ in range(3): band += [47, 48, 49, 50, 49, 48, 47, 48, 49, 50]
c = np.array(band, float); o = np.r_[c[0], c[:-1]]
c = np.r_[c, 53.0]; o = np.r_[o, 50.05]
h = np.maximum(c, o); l = np.minimum(c, o); h[-1] = 53.0; l[-1] = 50.0
v = np.r_[np.full(len(c) - 1, 1000.0), 3000.0]
results.append(show("channel + marubozu", mk(c, o, h, l, v), "Channel Breakout"))

# 3. Ascending triangle: flat top 60, rising lows, sharp turning points, fresh breakout
at = legs([50, 60, 53, 60, 56, 60, 58, 60, 62], per=3)
results.append(show("ascending triangle", mk(at), "Ascending Triangle"))

# 4. Rounding bottom: smooth U, breakout above rim (no handle, no 30% rise-in)
x = np.linspace(-1, 1, 80); u = 25 + 8 * x**2
results.append(show("rounding bottom", mk(np.r_[u, [33.5]], noise=0.01), "Rounding Bottom"))

# 5. Cup with handle: >=30% rise in, U cup, real handle dip, breakout
rise = np.linspace(10, 30, 25)
cup = 30 - 8 * np.sin(np.linspace(0, np.pi, 45))
handle = np.array([30, 29, 28.2, 27.8, 28, 28.5, 29, 31.5])
results.append(show("cup with handle", mk(np.r_[rise, cup, handle], noise=0.004), "Cup with Handle"))

# 6. Double bottom (realistic separation ~ 4-5 weeks)
db = stretch([50, 46, 42, 40, 41, 43, 45, 46, 45, 43, 41, 40.5, 41, 43, 45, 47], 40)
results.append(show("double bottom", mk(db), "Double Bottom"))

# 7. Triple bottom
tb = stretch([50, 45, 40, 44, 46, 44, 40.5, 44, 46, 45, 40.2, 43, 46, 48], 45)
results.append(show("triple bottom", mk(tb), "Triple Bottom"))

# 8. Inverse H&S
ih = stretch([50, 44, 42, 45, 46, 40, 38, 41, 46, 45, 42, 44, 47], 40)
results.append(show("inverse H&S", mk(ih), "Inverse Head & Shoulders"))

# 9. Falling wedge: converging down-sloping lines, sharp turns, fresh breakout at end
fw = legs([60, 52, 57, 50, 54, 48, 51, 47, 55], per=3)
results.append(show("falling wedge", mk(fw), "Falling Wedge"))

# 10. Flag: steep pole then a PARALLEL (constant-width) flag then breakout
fg = np.r_[np.linspace(20, 30, 18), [30, 29, 30, 29, 30, 29, 31]]
results.append(show("flag", mk(fg), "Flag"))

# 11. Lower-tail reversals (need >=20 bars now; pad with a prior downtrend)
pre = list(np.linspace(60, 51, 16))
tail_c = pre + [50, 48, 49, 47, 48, 46, 47]
tail_o = pre + [50, 49, 49.5, 48, 48.5, 47, 47.2]
tail_l = list(np.array(pre) - 0.5) + [49, 46, 47, 45, 46, 44, 45]
tail_h = list(np.array(pre) + 0.3) + [50.2, 49.2, 49.6, 48.2, 48.6, 47.1, 47.4]
results.append(show("lower-tail", mk(tail_c, tail_o, tail_h, tail_l), "Lower-tail"))

# ---- new detectors ----
# 12. Pennant: pole then converging (contracting) consolidation, breakout
pen = np.r_[np.linspace(20, 32, 16), [32, 30, 31.5, 30.7, 31.1, 30.9, 33.5]]
results.append(show("pennant", mk(pen), "Pennant"))

# 13. Symmetrical triangle: lower highs + higher lows converging, breakout
sym = legs([48, 58, 52, 56, 53.5, 55.5, 54.5, 59], per=4)
results.append(show("symmetric triangle", mk(sym), "Symmetrical Triangle"))

# 14. Pipe bottom: two adjacent deep low bars then breakout
pc = [50]*20 + [48, 48, 50, 51, 52.5]
pl = [49.5]*20 + [40, 40, 49, 50, 51.5]   # the two spikes
ph = [50.5]*20 + [49, 49, 50.5, 51.5, 53]
po = [50]*20 + [49, 48.5, 50, 51, 52]
results.append(show("pipe bottom", mk(pc, po, ph, pl), "Pipe Bottom"))

# 15. Horn bottom: two down-spikes separated by one bar
hc = [50]*19 + [48, 49, 48, 50, 51, 52.5]
hl = [49.5]*19 + [40, 48, 40, 49, 50, 51.5]
hh = [50.5]*19 + [49, 49.5, 49, 50.5, 51.5, 53]
ho = [50]*19 + [49, 48.8, 49, 50, 51, 52]
results.append(show("horn bottom", mk(hc, ho, hh, hl), "Horn Bottom"))

# 16. Three rising valleys: three rising lows, breakout
trv = legs([50, 45, 48, 46, 50, 47, 52, 54], per=4)
results.append(show("three rising valleys", mk(trv), "Three Rising Valleys"))

# 17. Measured move up: leg, ~50% retrace, second leg breakout
mmu = legs([40, 50, 45, 55], per=8)
results.append(show("measured move up", mk(mmu), "Measured Move Up"))

# 18. Ascending scallop: left peak, rounded dip, higher right peak
sca = legs([50, 55, 48, 58], per=9)
results.append(show("ascending scallop", mk(sca), "Ascending Scallop"))

# 19. Gap up: unfilled up-gap on volume after consolidation
gc = [50]*25 + [55]
gl = [49]*25 + [53]      # last low 53 > prior high 50.5 = gap
gh = [50.5]*25 + [55.5]
go = [50]*25 + [53.2]
gv = [1000]*25 + [3500]
results.append(show("gap up", mk(gc, go, gh, gl, gv), "Gap Up"))

# 20. Diamond bottom: broaden then narrow, breakout
dia = legs([50, 53, 49, 56, 44, 53, 47, 51, 49, 54], per=3)
results.append(show("diamond bottom", mk(dia), "Diamond"))

# 21. Broadening bottom: higher highs + lower lows diverging, breakout
brd = legs([52, 54, 48, 57, 44, 58], per=5)
results.append(show("broadening bottom", mk(brd), "Broadening Bottom"))

# 22. Island reversal bottom: gap down, island, gap up
ic = [50]*20 + [44, 44, 45, 44, 50]
il = [49]*20 + [43, 43, 44, 43, 50]   # gap down (43<49), gap up at end (50>46)
ih2 = [50.5]*20 + [45, 45, 46, 45, 51]
io = [50]*20 + [44, 44, 45, 44, 50.2]
results.append(show("island bottom", mk(ic, io, ih2, il), "Island"))

print()
fp = 0; total = 0
for s in range(30):
    r = np.random.default_rng(100 + s)
    walk = np.abs(100 + np.cumsum(r.normal(0, 1.2, 130))) + 20
    hits = [h for h in P.detect_patterns(mk(walk)) if h["status"] == "breakout"]
    total += len(hits)
    if hits: fp += 1
print(f"random-walk false positives: {fp}/30 walks had >=1 breakout ({total} total)")
print(f"\nDETECTOR PASSES: {sum(results)}/{len(results)}")
