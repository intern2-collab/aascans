"""
Bullish chart-pattern scanner — pivot-based, spec-driven.

Rules come from PATTERNS_SPEC.md (distilled from Bulkowski's Encyclopedia of
Chart Patterns identification tables + the Fidelity slides). Every detector works
off swing pivots (see pivots.py), reports TRIGGERED only on a confirmed breakout
(else FORMING), and returns the measured numbers so a human can verify on the
candlestick chart.

Each detector returns None or:
    {pattern, status, detail, confidence, target?}
status in {"breakout","forming"}. detect_patterns() runs them all on one stock.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from . import pivots as pv

LEVEL_TOL = 0.04          # two prices "at the same level"
FLAT_SLOPE = 0.004        # |slope|/price per bar counted as horizontal


# ------------------------------------------------------------------ small utils
def _recent(plist, n, lookback):
    return [p for p in plist if p["i"] >= n - lookback]


def _vol_mult(d, base_lo, base_hi):
    """Recent 3-day avg volume / base-window median volume."""
    v = d["volume"].values
    base = v[max(0, base_lo):max(1, base_hi)]
    med = float(np.median(base)) if len(base) else 0.0
    now = float(np.mean(v[-3:])) if len(v) >= 3 else float(v[-1])
    return (now / med) if med > 0 else 1.0


def _status(d, level, look=6, tol=0.03):
    """Classify the latest close against a breakout `level`.
    breakout = close DECISIVELY above level (by >=0.3 ATR) with a cross within
    `look` bars; forming = close just below level (within tol). Else None."""
    c = d["close"].values
    last = float(c[-1])
    if level <= 0:
        return None, 0.0
    a = pv.atr(d)
    margin = 0.3 * float(a.iloc[-1]) if len(a) else 0.0       # decisive-breakout buffer
    if last > level + margin:
        prior = c[max(0, len(c) - look - 1):-1]
        if len(prior) and float(np.min(prior)) <= level:      # fresh cross
            return "breakout", pv.pct(last, level)
        return None, 0.0                                       # stale breakout
    if level * (1 - tol) <= last <= level + margin:
        return "forming", pv.pct(last, level)
    return None, 0.0


def _clip(x):
    return round(float(max(0.05, min(0.95, x))), 2)


# ------------------------------------------------------------------ 1. HTF
def high_tight_flag(d, piv, hi, lo) -> dict | None:
    c = d["close"].values
    n = len(c)
    if n < 25:
        return None
    win = min(70, n)
    seg = c[-win:]
    lo_rel = int(np.argmin(seg))
    # pole top = highest high after the low but BEFORE the final (breakout) bar,
    # so the breakout bar itself is not mistaken for the pole top.
    after = seg[lo_rel:-1]
    if len(after) < 2:
        return None
    hi_rel = lo_rel + int(np.argmax(after))
    low_p, high_p = float(seg[lo_rel]), float(seg[hi_rel])
    pole = pv.pct(high_p, low_p)
    pole_len = hi_rel - lo_rel
    if pole < 90 or pole_len > 45 or pole_len < 3:
        return None
    flag = seg[hi_rel:]
    if len(flag) < 2:
        return None
    flag_low = float(np.min(flag))
    drift = pv.pct(high_p, flag_low)          # how far it pulled back off the high
    if drift > 25:
        return None
    st, dist = _status(d, high_p, look=len(flag) + 1)
    if st is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    vm = _vol_mult(d, n - win, hi_rel + (n - win))
    conf = 0.55 + cb + (0.1 if vm < 1.0 else 0)   # receding volume is good for HTF
    tag = "breakout" if st == "breakout" else "handle forming below high"
    det = (f"pole +{pole:.0f}% in {pole_len}d, flag pullback {drift:.0f}%, "
           f"breakout level {high_p:.1f} — {tag}"
           + (f"; {note}" if note else ""))
    return {"pattern": "High Tight Flag", "status": st, "detail": det,
            "confidence": _clip(conf), "target": round(high_p + (high_p - low_p), 1)}


# ------------------------------------------------------------------ 2. Channel
def channel_breakout(d, piv, hi, lo) -> dict | None:
    n = len(d)
    # exclude the breakout bar's own pivots when defining the band
    H = [p for p in _recent(hi, n, 90) if p["i"] < n - 1]
    L = [p for p in _recent(lo, n, 90) if p["i"] < n - 1]
    if len(H) < 2 or len(L) < 2:
        return None
    Hs = H[-3:]; Ls = L[-3:]
    hp = [p["price"] for p in Hs]; lp = [p["price"] for p in Ls]
    if not (pv.same_level(hp, LEVEL_TOL) and pv.same_level(lp, LEVEL_TOL)):
        return None
    res = float(np.mean(hp)); sup = float(np.mean(lp))
    if res <= sup:
        return None
    # slopes ~flat
    ms, *_ = pv.line_fit([p["i"] for p in Hs], hp)
    if abs(ms) / res > FLAT_SLOPE:
        return None
    depth = (res - sup) / res * 100
    touches = len(Hs) + len(Ls)
    st, dist = _status(d, res)
    if st is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    vm = _vol_mult(d, Ls[0]["i"], Hs[-1]["i"] or 1)
    if st == "breakout" and vm < 1.25 and cb <= 0:      # real channel breakouts confirm
        st = "forming"                                   # unconfirmed poke -> not a signal
    conf = 0.55 + min(0.15, (touches - 4) * 0.03) + cb + (0.1 if vm >= 1.5 else 0)
    tag = "breakout" if st == "breakout" else "coiling under resistance"
    det = (f"{touches} touches, {depth:.0f}%-wide band {sup:.1f}-{res:.1f}; "
           f"close {'above' if st=='breakout' else 'near'} resistance {res:.1f}"
           f" on {vm:.1f}x vol — {tag}" + (f"; {note}" if note else ""))
    return {"pattern": "Channel Breakout", "status": st, "detail": det,
            "confidence": _clip(conf), "target": round(res + (res - sup), 1)}


# ------------------------------------------------------------------ 3. Asc. tri
def ascending_triangle(d, piv, hi, lo) -> dict | None:
    n = len(d)
    H = [p for p in _recent(hi, n, 90) if p["i"] < n - 1]
    L = [p for p in _recent(lo, n, 90) if p["i"] < n - 1]
    if len(H) < 2 or len(L) < 2:
        return None
    res = max(p["price"] for p in H)                   # resistance = the flat top
    top_touches = [p for p in H if p["price"] >= res * 0.97]   # highs at the top
    if len(top_touches) < 2:
        return None
    Ls = L[-3:]
    lp = [p["price"] for p in Ls]
    ml, *_ = pv.line_fit([p["i"] for p in Ls], lp)     # rising bottom
    if ml <= 0 or lp[-1] <= lp[0]:
        return None
    if lp[-1] >= res * (1 - 0.02):                     # lows shouldn't reach the top yet
        return None
    Hs = top_touches
    st, dist = _status(d, res)
    if st is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    vm = _vol_mult(d, Ls[0]["i"], Hs[-1]["i"] or 1)
    conf = 0.55 + cb + (0.1 if vm >= 1.5 else 0)
    tag = "breakout" if st == "breakout" else "pressing flat resistance"
    det = (f"flat top {res:.1f} ({len(Hs)} highs), rising lows "
           f"{lp[0]:.1f}->{lp[-1]:.1f}; close {'above' if st=='breakout' else 'near'} "
           f"top on {vm:.1f}x vol — {tag}" + (f"; {note}" if note else ""))
    return {"pattern": "Ascending Triangle", "status": st, "detail": det,
            "confidence": _clip(conf)}


# ------------------------------------------------------------------ 4/5. Rounding + Cup
def _base_window(d, piv, lo):
    """Locate a rounding base: left rim high, cup bottom, and window bounds."""
    n = len(d); c = d["close"].values
    if n < 30:
        return None
    win = min(200, n)
    start = n - win
    seg = c[start:]
    bot_rel = int(np.argmin(seg)); bottom = float(seg[bot_rel])
    if bot_rel < 5 or bot_rel > len(seg) - 5:            # bottom must be interior
        return None
    left_rim = float(np.max(seg[:bot_rel]))               # high before the bottom
    right_max = float(np.max(seg[bot_rel:]))
    depth = (left_rim - bottom) / left_rim * 100 if left_rim else 0
    return {"start": start, "seg": seg, "bot_rel": bot_rel, "bottom": bottom,
            "left_rim": left_rim, "right_max": right_max, "depth": depth}


def rounding_bottom(d, piv, hi, lo) -> dict | None:
    bw = _base_window(d, piv, lo)
    if not bw or not (12 <= bw["depth"] <= 55):
        return None
    a, vtx, r2 = pv.parabola_fit(bw["seg"])
    if a <= 0 or r2 < 0.55 or not (0.25 <= vtx <= 0.75):   # concave, good fit, centered
        return None
    st, dist = _status(d, bw["left_rim"])
    if st is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    conf = 0.45 + 0.2 * (r2 - 0.55) / 0.45 + cb            # fit quality drives confidence
    tag = "breakout above rim" if st == "breakout" else "nearing rim"
    det = (f"smooth bowl (fit R2={r2:.2f}), {bw['depth']:.0f}% deep over "
           f"{len(bw['seg'])}d, rim {bw['left_rim']:.1f} — {tag}"
           + (f"; {note}" if note else ""))
    return {"pattern": "Rounding Bottom", "status": st, "detail": det,
            "confidence": _clip(conf)}


def cup_with_handle(d, piv, hi, lo) -> dict | None:
    n = len(d); c = d["close"].values
    H = [p for p in hi if n - 220 <= p["i"] < n - 1]        # rim candidates (not breakout bar)
    if len(H) < 2:
        return None
    best = None
    for li in range(len(H)):
        for ri in range(li + 1, len(H)):
            left, right = H[li], H[ri]
            if not pv.same_level([left["price"], right["price"]], 0.10):  # lips ~same level
                continue
            mids = [p for p in lo if left["i"] < p["i"] < right["i"]]
            if not mids:
                continue
            bottom = min(mids, key=lambda p: p["price"])   # cup bottom sits BETWEEN the rims
            rim = min(left["price"], right["price"])
            depth = (rim - bottom["price"]) / rim * 100 if rim else 0
            if not (12 <= depth <= 50):                    # U-cup depth
                continue
            pre = [p["price"] for p in lo if p["i"] < left["i"]]
            if not pre or pv.pct(left["price"], min(pre)) < 30:   # >=30% rise into the cup
                continue
            handle = c[right["i"]:]
            if len(handle) < 5:                            # handle >= ~1 week
                continue
            handle_low = float(np.min(handle))
            half = bottom["price"] + 0.5 * (rim - bottom["price"])
            handle_dd = pv.pct(right["price"], handle_low)
            if handle_low < half or not (2.0 <= handle_dd <= 25.0):   # real dip, upper half
                continue
            st, dist = _status(d, right["price"])
            if st is None:
                continue
            best = (left, right, bottom, depth, pv.pct(left["price"], min(pre)), handle_dd, st)
    if not best:
        return None
    left, right, bottom, depth, rise_in, handle_dd, st = best
    note, cb = pv.breakout_candle_note(d)
    conf = 0.5 + (0.1 if rise_in >= 30 else 0) + cb
    tag = "breakout above rim" if st == "breakout" else "handle forming"
    det = (f"{rise_in:.0f}% rise in, U-cup {depth:.0f}% deep, rim {right['price']:.1f}, "
           f"handle {handle_dd:.0f}% — {tag}" + (f"; {note}" if note else ""))
    return {"pattern": "Cup with Handle", "status": st, "detail": det,
            "confidence": _clip(conf),
            "target": round(right["price"] + (right["price"] - bottom["price"]), 1)}


# ------------------------------------------------------------------ 6. Double bottom
def double_bottom(d, piv, hi, lo) -> dict | None:
    n = len(d)
    L = _recent(lo, n, 160); H = _recent(hi, n, 160)
    if len(L) < 2:
        return None
    L1, L2 = L[-2], L[-1]
    if not pv.same_level([L1["price"], L2["price"]], 0.10):
        return None
    sep = L2["i"] - L1["i"]
    if sep < 10:                                           # >= ~2 weeks apart
        return None
    peaks = [p for p in H if L1["i"] < p["i"] < L2["i"]]
    if not peaks:
        return None
    peak = max(peaks, key=lambda p: p["price"])
    rise = pv.pct(peak["price"], max(L1["price"], L2["price"]))
    if rise < 10:                                          # >= 10% rise between
        return None
    st, dist = _status(d, peak["price"])
    if st is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    var = abs(pv.pct(L2["price"], L1["price"]))
    conf = 0.55 + (0.1 if var <= 6 else 0) + cb
    tag = "confirmed breakout" if st == "breakout" else "nearing confirmation"
    det = (f"two lows {L1['price']:.1f}/{L2['price']:.1f} ({var:.0f}% apart, {sep}d), "
           f"peak {peak['price']:.1f}; close {'above' if st=='breakout' else 'near'} "
           f"confirmation — {tag}" + (f"; {note}" if note else ""))
    return {"pattern": "Double Bottom", "status": st, "detail": det,
            "confidence": _clip(conf),
            "target": round(peak["price"] + (peak["price"] - min(L1["price"], L2["price"])), 1)}


# ------------------------------------------------------------------ 7. Triple bottom
def triple_bottom(d, piv, hi, lo) -> dict | None:
    n = len(d)
    L = _recent(lo, n, 220); H = _recent(hi, n, 220)
    if len(L) < 3:
        return None
    L1, L2, L3 = L[-3], L[-2], L[-1]
    lows3 = [L1["price"], L2["price"], L3["price"]]
    if not pv.same_level(lows3, LEVEL_TOL):
        return None
    if L2["price"] < min(L1["price"], L3["price"]) * 0.95:   # center not much lower (else IHS)
        return None
    peaks = [p for p in H if L1["i"] < p["i"] < L3["i"]]
    if len(peaks) < 2:
        return None
    conf_level = max(p["price"] for p in peaks)
    st, dist = _status(d, conf_level)
    if st is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    conf = 0.6 + cb
    tag = "confirmed breakout" if st == "breakout" else "nearing confirmation"
    det = (f"three lows ~{np.mean(lows3):.1f} ({L1['price']:.1f}/{L2['price']:.1f}/"
           f"{L3['price']:.1f}); confirmation {conf_level:.1f} — {tag}"
           + (f"; {note}" if note else ""))
    return {"pattern": "Triple Bottom", "status": st, "detail": det, "confidence": _clip(conf)}


# ------------------------------------------------------------------ 8. Inverse H&S
def inverse_hs(d, piv, hi, lo) -> dict | None:
    n = len(d)
    L = _recent(lo, n, 200); H = _recent(hi, n, 200)
    if len(L) < 3:
        return None
    head = min(L, key=lambda p: p["price"])               # head = the lowest trough
    left_c = [p for p in L if p["i"] < head["i"] and p["price"] > head["price"] * 1.03]
    right_c = [p for p in L if head["i"] < p["i"] < n - 1 and p["price"] > head["price"] * 1.03]
    if not left_c or not right_c:
        return None
    # choose the most symmetric shoulder pair at ~the same level
    best = None
    for LS in left_c:
        for RS in right_c:
            if not pv.same_level([LS["price"], RS["price"]], 0.10):
                continue
            tl = head["i"] - LS["i"]; tr = RS["i"] - head["i"]
            if tl <= 0 or tr <= 0 or max(tl, tr) / min(tl, tr) > 2.5:
                continue
            key = abs(tl - tr) + abs(pv.pct(RS["price"], LS["price"]))
            if best is None or key < best[0]:
                best = (key, LS, RS)
    if not best:
        return None
    _, LS, RS = best
    peaks = [p for p in H if LS["i"] < p["i"] < RS["i"]]
    if len(peaks) < 1:
        return None
    neck = max(p["price"] for p in peaks)                  # up-sloping neckline -> highest high
    HEAD = head
    st, dist = _status(d, neck)
    if st is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    conf = 0.6 + cb
    tag = "neckline breakout" if st == "breakout" else "nearing neckline"
    det = (f"L-shoulder {LS['price']:.1f}, head {HEAD['price']:.1f}, "
           f"R-shoulder {RS['price']:.1f}; neckline {neck:.1f} — {tag}"
           + (f"; {note}" if note else ""))
    return {"pattern": "Inverse Head & Shoulders", "status": st, "detail": det,
            "confidence": _clip(conf)}


# ------------------------------------------------------------------ 9. Falling wedge
def falling_wedge(d, piv, hi, lo) -> dict | None:
    n = len(d)
    H = [p for p in _recent(hi, n, 90) if p["i"] < n - 1]   # exclude breakout bar
    L = _recent(lo, n, 90)
    if len(H) < 3 or len(L) < 2:
        return None
    Hs = H[-3:]; Ls = L[-2:]
    xh = [p["i"] for p in Hs]; yh = [p["price"] for p in Hs]
    xl = [p["i"] for p in Ls]; yl = [p["price"] for p in Ls]
    mh, bh, _ = pv.line_fit(xh, yh)
    ml, bl, _ = pv.line_fit(xl, yl)
    if mh >= 0 or ml >= 0:                                  # both must slope down
        return None
    if mh >= ml:                                            # top steeper (more negative)
        return None
    span = max(xh[-1], xl[-1]) - min(xh[0], xl[0])          # full wedge width
    if span < 15:                                          # >= ~3 weeks
        return None
    top_now = mh * (n - 1) + bh                            # upper line at today
    st, dist = _status(d, float(top_now))
    if st is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    conf = 0.45 + cb
    tag = "breakout above wedge" if st == "breakout" else "nearing wedge top"
    det = (f"two down-sloping lines converging over {span}d, "
           f"{len(Hs)+len(Ls)} touches; upper line {top_now:.1f} — {tag}"
           + (f"; {note}" if note else ""))
    return {"pattern": "Falling Wedge", "status": st, "detail": det, "confidence": _clip(conf)}


# ------------------------------------------------------------------ 10. Flag
def flag(d, piv, hi, lo) -> dict | None:
    c = d["close"].values; n = len(c)
    if n < 20:
        return None
    look = min(30, n)
    seg = c[-look:]
    # split: pole then flag. Try flag lengths 4..15
    best = None
    for fl in range(4, 16):
        if fl >= look - 5:
            break
        pole = seg[:-fl]; fseg = seg[-fl:]
        if len(pole) < 4:
            continue
        pole_rise = pv.pct(float(pole[-1]), float(np.min(pole)))
        if pole_rise < 15:
            continue
        frange = pv.pct(float(np.max(fseg[:-1])), float(np.min(fseg[:-1])))
        if frange > 12:                                    # flag must be tight
            continue
        flag_high = float(np.max(fseg[:-1]))               # exclude the breakout bar
        st, dist = _status(d, flag_high, look=fl + 1)
        if st == "breakout":
            best = (fl, pole_rise, frange, flag_high, st)
            break
    if not best:
        return None
    fl, pole_rise, frange, flag_high, st = best
    note, cb = pv.breakout_candle_note(d)
    conf = 0.5 + cb
    det = (f"pole +{pole_rise:.0f}% then {fl}d tight flag ({frange:.0f}% range); "
           f"breakout above {flag_high:.1f}" + (f"; {note}" if note else ""))
    return {"pattern": "Flag", "status": st, "detail": det, "confidence": _clip(conf)}


# ------------------------------------------------------------------ candle: tail
def lower_tail_reversal(d, piv, hi, lo, lookback: int = 7) -> dict | None:
    dd = d.tail(lookback)
    if len(dd) < 4:
        return None
    o, h, l, c = dd["open"], dd["high"], dd["low"], dd["close"]
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    lower = pd.concat([o, c], axis=1).min(axis=1) - l
    strong = c >= (l + 0.5 * rng)
    tail = (lower >= 1.5 * body.replace(0, 1e-9)) & (lower >= 0.5 * rng) & strong
    nt = int(tail.fillna(False).sum())
    if nt >= 3:
        avg = float((lower[tail] / c[tail]).mean() * 100)
        return {"pattern": "Lower-tail reversals", "status": "forming",
                "detail": f"{nt} long lower-tail candles in {len(dd)}d "
                          f"(avg wick {avg:.1f}% of price) — bought off lows",
                "confidence": _clip(0.4 + 0.12 * nt)}
    return None


# ------------------------------------------------------------------ 11. Pennant
def pennant(d, piv, hi, lo) -> dict | None:
    c = d["close"].values; h = d["high"].values; l = d["low"].values; n = len(c)
    if n < 18:
        return None
    look = min(28, n)
    for fl in range(4, 16):
        if fl >= look - 6:
            break
        pole = c[-look:-fl]
        if len(pole) < 5:
            continue
        pr = pv.pct(float(pole[-1]), float(np.min(pole)))
        if pr < 15:
            continue
        hi_s, lo_s = h[-fl:], l[-fl:]
        half = fl // 2
        r1 = float(np.max(hi_s[:half]) - np.min(lo_s[:half]))
        r2 = float(np.max(hi_s[half:]) - np.min(lo_s[half:]))
        if half < 1 or r1 <= 0 or r2 >= r1 * 0.65:         # must clearly contract (converge)
            continue
        ph = float(np.max(c[-fl:-1]))
        st, dist = _status(d, ph, look=fl + 1)
        if st == "breakout":
            note, cb = pv.breakout_candle_note(d)
            return {"pattern": "Pennant", "status": st,
                    "detail": f"pole +{pr:.0f}% then {fl}-bar converging pennant; "
                              f"breakout above {ph:.1f}" + (f"; {note}" if note else ""),
                    "confidence": _clip(0.5 + cb)}
    return None


# ------------------------------------------------------------------ 12. Sym triangle
def symmetric_triangle(d, piv, hi, lo) -> dict | None:
    n = len(d)
    H = [p for p in _recent(hi, n, 90) if p["i"] < n - 1]
    L = [p for p in _recent(lo, n, 90) if p["i"] < n - 1]
    if len(H) < 2 or len(L) < 2:
        return None
    Hs, Ls = H[-3:], L[-3:]
    mh, bh, _ = pv.line_fit([p["i"] for p in Hs], [p["price"] for p in Hs])
    ml, bl, _ = pv.line_fit([p["i"] for p in Ls], [p["price"] for p in Ls])
    if mh >= 0 or ml <= 0:                                  # top down, bottom up
        return None
    span = max(Hs[-1]["i"], Ls[-1]["i"]) - min(Hs[0]["i"], Ls[0]["i"])
    if span < 15:                                          # > ~3 weeks (else pennant)
        return None
    top_now = mh * (n - 1) + bh
    st, dist = _status(d, float(top_now))
    if st is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    return {"pattern": "Symmetrical Triangle", "status": st,
            "detail": f"lower highs + higher lows converging over {span} bars; "
                      f"breakout above {top_now:.1f}" + (f"; {note}" if note else ""),
            "confidence": _clip(0.5 + cb)}


# ------------------------------------------------------------------ 13. Pipe bottom (weekly)
def pipe_bottom(d, piv, hi, lo) -> dict | None:
    n = len(d)
    if n < 20:
        return None
    low = d["low"].values; high = d["high"].values
    win_min = float(np.min(low[-20:]))                      # the pipe must be the recent low
    for i in range(n - 2, max(2, n - 16), -1):             # adjacent pair (i-1, i)
        pair_low = min(low[i], low[i - 1])
        if pair_low > win_min * 1.01:                       # only the genuine bottom
            continue
        surround = np.concatenate([low[max(0, i - 9):i - 1], low[i + 1:min(n, i + 9)]])
        if len(surround) < 4:
            continue
        med = float(np.median(surround))
        if med <= 0:
            continue
        depth = (med - pair_low) / med * 100
        overlap = min(high[i], high[i - 1]) - max(low[i], low[i - 1])
        if depth >= 18 and overlap > 0:                     # deep, obvious spikes only
            level = float(np.max(high[i - 1:i + 1]))
            st, dist = _status(d, level, look=n - i + 1)
            if st == "breakout":
                note, cb = pv.breakout_candle_note(d)
                return {"pattern": "Pipe Bottom", "status": "breakout",
                        "detail": f"two adjacent down-spikes {depth:.0f}% below surroundings; "
                                  f"closed above pipe high {level:.1f}" + (f"; {note}" if note else ""),
                        "confidence": _clip(0.55 + cb)}
    return None


# ------------------------------------------------------------------ 14. Horn bottom (weekly)
def horn_bottom(d, piv, hi, lo) -> dict | None:
    n = len(d)
    if n < 20:
        return None
    low = d["low"].values; high = d["high"].values
    win_min = float(np.min(low[-20:]))
    for i in range(n - 2, max(3, n - 16), -1):             # spikes at i-2 and i
        spike_low = min(low[i - 2], low[i]); center = low[i - 1]
        if spike_low > win_min * 1.01 or center <= spike_low * 1.02:
            continue
        surround = np.concatenate([low[max(0, i - 9):i - 2], low[i + 1:min(n, i + 9)]])
        if len(surround) < 4:
            continue
        med = float(np.median(surround))
        if med <= 0 or (med - spike_low) / med * 100 < 18:
            continue
        depth = (med - spike_low) / med * 100
        level = float(np.max(high[i - 2:i + 1]))
        st, dist = _status(d, level, look=n - i + 1)
        if st == "breakout":
            note, cb = pv.breakout_candle_note(d)
            return {"pattern": "Horn Bottom", "status": "breakout",
                    "detail": f"two down-spikes one bar apart {depth:.0f}% below surroundings; "
                              f"closed above {level:.1f}" + (f"; {note}" if note else ""),
                    "confidence": _clip(0.55 + cb)}
    return None


# ------------------------------------------------------------------ 15. Three rising valleys
def three_rising_valleys(d, piv, hi, lo) -> dict | None:
    n = len(d)
    L = _recent(lo, n, 220); H = _recent(hi, n, 220)
    if len(L) < 3:
        return None
    L1, L2, L3 = L[-3], L[-2], L[-1]
    if not (L1["price"] < L2["price"] < L3["price"]):      # strictly rising valleys
        return None
    if pv.pct(L3["price"], L1["price"]) > 40:              # not a runaway trend
        return None
    peaks = [p for p in H if L1["i"] < p["i"] < n - 1]
    if not peaks:
        return None
    level = max(p["price"] for p in peaks)
    st, dist = _status(d, level)
    if st is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    return {"pattern": "Three Rising Valleys", "status": st,
            "detail": f"three rising lows {L1['price']:.1f}<{L2['price']:.1f}<{L3['price']:.1f}; "
                      f"confirmation {level:.1f}" + (f"; {note}" if note else ""),
            "confidence": _clip(0.55 + cb)}


# ------------------------------------------------------------------ 16. Bump-and-run bottom
def bump_run_bottom(d, piv, hi, lo) -> dict | None:
    n = len(d)
    H = [p for p in _recent(hi, n, 150) if p["i"] < n - 1]
    if len(H) < 2:
        return None
    Hs = H[-3:] if len(H) >= 3 else H[-2:]
    mh, bh, _ = pv.line_fit([p["i"] for p in Hs], [p["price"] for p in Hs])
    if mh >= 0:                                            # down-sloping lead-in line
        return None
    bw = _base_window(d, piv, lo)
    if not bw:
        return None
    a, vtx, r2 = pv.parabola_fit(bw["seg"])
    if a <= 0 or r2 < 0.4:                                 # rounded bump
        return None
    line_now = mh * (n - 1) + bh
    st, dist = _status(d, float(line_now))
    if st is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    return {"pattern": "Bump-and-Run Bottom", "status": st,
            "detail": f"rounded bottom breaking above the down-sloping lead-in line "
                      f"{line_now:.1f}" + (f"; {note}" if note else ""),
            "confidence": _clip(0.4 + cb)}


# ------------------------------------------------------------------ 17. Measured move up
def measured_move_up(d, piv, hi, lo) -> dict | None:
    if len(lo) < 2 or len(hi) < 1:
        return None
    L2 = lo[-1]
    H1c = [p for p in hi if p["i"] < L2["i"]]
    if not H1c:
        return None
    H1 = H1c[-1]
    L1c = [p for p in lo if p["i"] < H1["i"]]
    if not L1c:
        return None
    L1 = L1c[-1]
    leg1 = H1["price"] - L1["price"]
    if leg1 <= 0:
        return None
    retr = (H1["price"] - L2["price"]) / leg1 * 100
    if not (30 <= retr <= 70):                             # 40-60% corrective (allow a little)
        return None
    st, dist = _status(d, H1["price"])
    if st is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    return {"pattern": "Measured Move Up", "status": st,
            "detail": f"leg +{pv.pct(H1['price'], L1['price']):.0f}%, {retr:.0f}% retrace, "
                      f"second leg breaking {H1['price']:.1f}" + (f"; {note}" if note else ""),
            "confidence": _clip(0.5 + cb)}


# ------------------------------------------------------------------ 18. Ascending scallop
def ascending_scallop(d, piv, hi, lo) -> dict | None:
    n = len(d)
    H = [p for p in _recent(hi, n, 150) if p["i"] < n - 1]
    L = _recent(lo, n, 150)
    if len(H) < 1 or len(L) < 1:
        return None
    c = d["close"].values
    for lh in reversed(H):                                 # left peak
        lows_after = [p for p in L if p["i"] > lh["i"]]
        if not lows_after:
            continue
        bottom = min(lows_after, key=lambda p: p["price"])
        dip = pv.pct(lh["price"], bottom["price"])
        if dip < 8 or dip > 40:                            # rounded recession depth
            continue
        seg = c[lh["i"]:]                                  # left peak -> now must trace a rounded U
        if len(seg) < 8:
            continue
        a, vtx, r2 = pv.parabola_fit(seg)
        if a <= 0 or r2 < 0.55 or not (0.2 <= vtx <= 0.8):
            continue
        st, dist = _status(d, lh["price"] * 1.01)          # right side decisively higher than left
        if st != "breakout":
            continue
        note, cb = pv.breakout_candle_note(d)
        return {"pattern": "Ascending Scallop", "status": "breakout",
                "detail": f"J-shape: left peak {lh['price']:.1f}, {dip:.0f}% rounded dip "
                          f"(fit R2={r2:.2f}), breakout to a higher high" + (f"; {note}" if note else ""),
                "confidence": _clip(0.45 + cb)}
    return None


# ------------------------------------------------------------------ 19. Gap up
def gap_up(d, piv, hi, lo) -> dict | None:
    n = len(d)
    if n < 12:
        return None
    low = d["low"].values; high = d["high"].values; c = d["close"].values
    if low[-1] > high[-2] and c[-1] > high[-2]:            # unfilled up gap today
        gap = pv.pct(low[-1], high[-2])
        vm = _vol_mult(d, n - 10, n - 1)
        prior = c[-12:-1]
        rng = pv.pct(float(np.max(prior)), float(np.min(prior)))
        kind = "breakaway (from consolidation)" if rng < 12 else "continuation (in trend)"
        if vm < 1.2:                                       # gaps that matter come on volume
            return None
        return {"pattern": "Gap Up", "status": "breakout",
                "detail": f"{kind} up-gap +{gap:.1f}% on {vm:.1f}x volume, unfilled",
                "confidence": _clip(0.5 + (0.15 if vm >= 1.5 else 0))}
    return None


# ------------------------------------------------------------------ 20. Diamond bottom
def diamond_bottom(d, piv, hi, lo) -> dict | None:
    n = len(d)
    H = [p for p in _recent(hi, n, 120) if p["i"] < n - 1]
    L = [p for p in _recent(lo, n, 120) if p["i"] < n - 1]
    if len(H) < 3 or len(L) < 3:
        return None
    Hs, Ls = H[-3:], L[-3:]
    amp = lambda hh, ll: abs(hh["price"] - ll["price"])
    a1, a2, a3 = amp(Hs[0], Ls[0]), amp(Hs[1], Ls[1]), amp(Hs[2], Ls[2])
    if not (a2 > a1 and a3 < a2):                          # broaden then narrow
        return None
    level = max(p["price"] for p in Hs)
    st, dist = _status(d, level)
    if st is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    return {"pattern": "Diamond Bottom", "status": st,
            "detail": f"broadened then narrowed (amp {a1:.1f}->{a2:.1f}->{a3:.1f}); "
                      f"breakout above {level:.1f}" + (f"; {note}" if note else ""),
            "confidence": _clip(0.45 + cb)}


# ------------------------------------------------------------------ 21. Broadening bottom
def broadening_bottom(d, piv, hi, lo) -> dict | None:
    n = len(d)
    H = [p for p in _recent(hi, n, 120) if p["i"] < n - 1]
    L = [p for p in _recent(lo, n, 120) if p["i"] < n - 1]
    if len(H) < 2 or len(L) < 2:
        return None
    mh, _, _ = pv.line_fit([p["i"] for p in H], [p["price"] for p in H])
    ml, _, _ = pv.line_fit([p["i"] for p in L], [p["price"] for p in L])
    if mh <= 0 or ml >= 0:                                  # highs up, lows down (diverging)
        return None
    Hs, Ls = H, L
    level = max(p["price"] for p in H)
    st, dist = _status(d, level)
    if st is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    return {"pattern": "Broadening Bottom", "status": st,
            "detail": f"megaphone (higher highs {Hs[0]['price']:.1f}->{Hs[-1]['price']:.1f}, "
                      f"lower lows {Ls[0]['price']:.1f}->{Ls[-1]['price']:.1f}); "
                      f"breakout above {level:.1f}" + (f"; {note}" if note else ""),
            "confidence": _clip(0.5 + cb)}


# ------------------------------------------------------------------ 22. Island reversal bottom
def island_bottom(d, piv, hi, lo) -> dict | None:
    n = len(d)
    if n < 8:
        return None
    low = d["low"].values; high = d["high"].values
    up_i = None
    for i in range(n - 1, max(0, n - 4), -1):              # recent up gap
        if low[i] > high[i - 1]:
            up_i = i; break
    if up_i is None:
        return None
    down_i = None
    for j in range(up_i - 1, max(0, up_i - 16), -1):       # prior down gap = island
        if high[j] < low[j - 1]:
            down_i = j; break
    if down_i is None:
        return None
    note, cb = pv.breakout_candle_note(d)
    return {"pattern": "Island Reversal Bottom", "status": "breakout",
            "detail": f"gap-down then gap-up ({up_i - down_i} bars apart) leaving an island — "
                      f"bullish reversal" + (f"; {note}" if note else ""),
            "confidence": _clip(0.5 + cb)}


_DETECTORS = [high_tight_flag, channel_breakout, ascending_triangle,
              cup_with_handle, rounding_bottom, double_bottom, triple_bottom,
              inverse_hs, falling_wedge, flag, pennant, symmetric_triangle,
              pipe_bottom, horn_bottom, three_rising_valleys, bump_run_bottom,
              measured_move_up, ascending_scallop, gap_up, diamond_bottom,
              broadening_bottom, island_bottom, lower_tail_reversal]


# ------------------------------------------------------------------ orchestration
def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily OHLCV into weekly bars (week ending Friday):
    open=first, high=max, low=min, close=last, volume=sum. Weekly candles are
    slower and less noisy — patterns on them carry more weight."""
    if df is None or not isinstance(df.index, pd.DatetimeIndex):
        return df
    agg = {"open": "first", "high": "max", "low": "min",
           "close": "last", "volume": "sum"}
    cols = {c: agg[c] for c in agg if c in df.columns}
    if "close" not in cols:
        return df
    w = df.resample("W-FRI").agg(cols).dropna(subset=["close"])
    return w


def detect_patterns(df: pd.DataFrame, timeframe: str = "daily") -> list:
    """Run every bullish detector on one stock's OHLCV; return the list of hits.
    timeframe: 'daily' or 'weekly' (weekly resamples first)."""
    if timeframe == "weekly":
        df = to_weekly(df)
    if df is None or len(df) < 20:
        return []
    d = pv.ohlc(df)
    piv = pv.zigzag(d)
    hi, lo = pv.highs(piv), pv.lows(piv)
    out = []
    for fn in _DETECTORS:
        try:
            r = fn(d, piv, hi, lo)
        except Exception:
            r = None
        if r:
            out.append(r)
    names = {h["pattern"] for h in out}
    # de-duplicate overlapping families (keep the more specific / stronger)
    if "Cup with Handle" in names:
        out = [h for h in out if h["pattern"] != "Rounding Bottom"]
    if "Triple Bottom" in names:
        out = [h for h in out if h["pattern"] != "Double Bottom"]
    if "Inverse Head & Shoulders" in names:
        out = [h for h in out if h["pattern"] not in ("Triple Bottom", "Double Bottom")]
    if "High Tight Flag" in names:               # HTF is the stronger flag
        out = [h for h in out if h["pattern"] != "Flag"]
    if "Pennant" in names:                       # pennant is a converging flag
        out = [h for h in out if h["pattern"] != "Flag"]
    if "Diamond Bottom" in names:                # diamond = broaden THEN narrow (more specific)
        out = [h for h in out if h["pattern"] != "Broadening Bottom"]
    if "Rounding Bottom" in names or "Cup with Handle" in names:
        out = [h for h in out if h["pattern"] not in ("Bump-and-Run Bottom", "Ascending Scallop")]
    # breakouts first, then confidence
    out.sort(key=lambda h: (h.get("status") == "breakout", h["confidence"]), reverse=True)
    return out


def scan_universe(meta: dict, companies: dict = None,
                  timeframe: str = "daily") -> pd.DataFrame:
    """meta: {symbol: {"df": ohlcv}}. One row per symbol showing any pattern.
    timeframe: 'daily' or 'weekly'."""
    companies = companies or {}
    rows = []
    for sym, m in meta.items():
        df = m.get("df")
        hits = detect_patterns(df, timeframe=timeframe)
        if not hits:
            continue
        triggered = [h for h in hits if h.get("status") == "breakout"]
        src = to_weekly(df) if timeframe == "weekly" else df
        last = float(pv.ohlc(src)["close"].iloc[-1])
        rows.append({
            "symbol": sym,
            "timeframe": timeframe,
            "company": companies.get(sym, ""),
            "patterns": ", ".join(
                (h["pattern"] + ("*" if h.get("status") == "breakout" else ""))
                for h in hits),
            "n_patterns": len(hits),
            "n_breakouts": len(triggered),
            "confidence": round(max(h["confidence"] for h in hits), 2),
            "last_price": round(last, 2),
            "details": " | ".join(
                f"{h['pattern']} [{h.get('status','')}]: {h['detail']}" for h in hits),
        })
    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values(["n_breakouts", "n_patterns", "confidence"],
                            ascending=False).reset_index(drop=True)
    return df
