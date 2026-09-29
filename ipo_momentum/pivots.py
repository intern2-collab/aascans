"""
Swing-pivot engine + geometry/candle helpers for the pattern scanner.

The eye reads a chart by its turning points, not its raw candles. This module
turns daily OHLCV into a clean alternating sequence of minor highs / minor lows
(a zigzag), confirmed only when price reverses by more than an ATR-scaled
threshold, plus the small geometry helpers (line fits, level clustering,
candle strength) the detectors in patterns.py are built on.

Everything here is transparent and numeric — no black box.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


# ----------------------------------------------------------------- OHLC hygiene
def ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce numeric, fill open from close, clamp high/low to contain o/c."""
    d = df.dropna(subset=["close"]).copy()
    for col in ("open", "high", "low", "close", "volume"):
        if col not in d.columns:
            d[col] = d["close"]
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d["open"] = d["open"].fillna(d["close"])
    d["close"] = d["close"].astype(float)
    d["high"] = d[["high", "close", "open"]].max(axis=1)
    d["low"] = d[["low", "close", "open"]].min(axis=1)
    d["volume"] = d["volume"].fillna(0)
    return d.reset_index(drop=True)


def atr(d: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = d["high"], d["low"], d["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=1).mean()


# ----------------------------------------------------------------- zigzag pivots
def zigzag(d: pd.DataFrame, k: float = 1.6,
           floor_pct: float = 0.025, cap_pct: float = 0.12) -> list:
    """
    Alternating pivots via an ATR-scaled reversal threshold.

    Returns a list of dicts: {i, price, kind}, kind in {"H","L"}, alternating,
    oldest-first. A new extreme extends the current leg; a reverse move larger
    than `thr` (fraction of price) confirms the last extreme as a pivot and flips
    direction. `thr` adapts to each stock's volatility, bounded to [floor,cap].
    """
    n = len(d)
    if n < 4:
        return []
    close = d["close"].values
    high = d["high"].values
    low = d["low"].values
    a = atr(d, 10).values          # recent ATR so contracting swings stay detectable
    # per-bar reversal threshold as a fraction of price
    thr = np.clip(k * (a / np.where(close == 0, np.nan, close)), floor_pct, cap_pct)
    thr = np.nan_to_num(thr, nan=floor_pct)

    piv = []
    trend = 0                      # +1 up leg (tracking a high), -1 down leg, 0 unknown
    ehi_i, ehi = 0, high[0]        # running high extreme since last pivot
    elo_i, elo = 0, low[0]         # running low extreme since last pivot
    for i in range(1, n):
        t = thr[i]
        if trend == 0:
            if high[i] >= ehi:
                ehi_i, ehi = i, high[i]
            if low[i] <= elo:
                elo_i, elo = i, low[i]
            if ehi > 0 and (ehi - low[i]) / ehi > t:      # first decisive drop -> high pivot
                piv.append({"i": ehi_i, "price": float(ehi), "kind": "H"})
                trend, elo_i, elo = -1, i, low[i]
            elif elo > 0 and (high[i] - elo) / elo > t:   # first decisive rise -> low pivot
                piv.append({"i": elo_i, "price": float(elo), "kind": "L"})
                trend, ehi_i, ehi = 1, i, high[i]
        elif trend > 0:                                   # up leg: track high, watch for drop
            if high[i] >= ehi:
                ehi_i, ehi = i, high[i]
            if ehi > 0 and (ehi - low[i]) / ehi > t:
                piv.append({"i": ehi_i, "price": float(ehi), "kind": "H"})
                trend, elo_i, elo = -1, i, low[i]
        else:                                             # down leg: track low, watch for rise
            if low[i] <= elo:
                elo_i, elo = i, low[i]
            if elo > 0 and (high[i] - elo) / elo > t:
                piv.append({"i": elo_i, "price": float(elo), "kind": "L"})
                trend, ehi_i, ehi = 1, i, high[i]
    # close the final leg with its running extreme as a tentative pivot
    if trend > 0:
        piv.append({"i": ehi_i, "price": float(ehi), "kind": "H"})
    elif trend < 0:
        piv.append({"i": elo_i, "price": float(elo), "kind": "L"})
    # enforce strict alternation (keep the more extreme of any same-kind run)
    return _alternate(piv)


def _alternate(piv: list) -> list:
    out = []
    for p in piv:
        if out and out[-1]["kind"] == p["kind"]:
            if p["kind"] == "H":
                if p["price"] >= out[-1]["price"]:
                    out[-1] = p
            else:
                if p["price"] <= out[-1]["price"]:
                    out[-1] = p
        else:
            out.append(p)
    return out


def highs(piv: list) -> list:
    return [p for p in piv if p["kind"] == "H"]


def lows(piv: list) -> list:
    return [p for p in piv if p["kind"] == "L"]


# ----------------------------------------------------------------- geometry
def line_fit(xs, ys):
    """Least-squares slope+intercept and R^2 for a set of points."""
    xs = np.asarray(xs, float); ys = np.asarray(ys, float)
    if len(xs) < 2:
        return 0.0, float(ys[0]) if len(ys) else 0.0, 0.0
    m, b = np.polyfit(xs, ys, 1)
    pred = m * xs + b
    ss_res = float(((ys - pred) ** 2).sum())
    ss_tot = float(((ys - ys.mean()) ** 2).sum()) or 1e-9
    return float(m), float(b), 1.0 - ss_res / ss_tot


def parabola_fit(ys):
    """Fit y = a x^2 + b x + c over index; return a, vertex_frac, R^2.
    a>0 = concave up (bowl). vertex_frac = where the minimum sits in [0,1]."""
    ys = np.asarray(ys, float)
    n = len(ys)
    if n < 5:
        return 0.0, 0.5, 0.0
    xs = np.linspace(0, 1, n)
    a, b, c = np.polyfit(xs, ys, 2)
    pred = a * xs * xs + b * xs + c
    ss_res = float(((ys - pred) ** 2).sum())
    ss_tot = float(((ys - ys.mean()) ** 2).sum()) or 1e-9
    vtx = float(-b / (2 * a)) if a != 0 else 0.5
    return float(a), vtx, 1.0 - ss_res / ss_tot


def same_level(prices, tol=0.04) -> bool:
    """True if all prices sit within `tol` (fraction) of their mean."""
    prices = np.asarray(prices, float)
    if len(prices) < 2:
        return True
    m = prices.mean()
    return m > 0 and float(np.max(np.abs(prices - m)) / m) <= tol


def pct(a, b) -> float:
    return (a / b - 1.0) * 100.0 if b else 0.0


# ----------------------------------------------------------------- candles
def candle(d: pd.DataFrame, i: int = -1) -> dict:
    """Strength features of one bar (default last)."""
    o = float(d["open"].iloc[i]); c = float(d["close"].iloc[i])
    h = float(d["high"].iloc[i]); l = float(d["low"].iloc[i])
    rng = (h - l) or 1e-9
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    return {"bull": c >= o, "body_frac": body / rng,
            "upper_frac": upper / rng, "lower_frac": lower / rng,
            "close": c, "open": o, "high": h, "low": l, "range": rng}


def breakout_candle_note(d: pd.DataFrame) -> tuple[str, float]:
    """Grade the latest (breakout) bar. Returns (label, confidence_boost)."""
    if len(d) < 2:
        return "", 0.0
    cur = candle(d, -1); prev = candle(d, -2)
    # marubozu / strong body, closing near high
    if cur["bull"] and cur["body_frac"] >= 0.85 and cur["upper_frac"] <= 0.10:
        return "strong marubozu breakout candle (no upper wick)", 0.20
    # bullish engulfing
    if (cur["bull"] and not prev["bull"]
            and cur["close"] >= prev["open"] and cur["open"] <= prev["close"]):
        return "bullish engulfing", 0.15
    # piercing line: up bar closing above midpoint of prior down bar body
    if (cur["bull"] and not prev["bull"]
            and cur["close"] >= (prev["open"] + prev["close"]) / 2
            and cur["close"] < prev["open"]):
        return "piercing line", 0.10
    if cur["bull"] and cur["body_frac"] >= 0.6:
        return "solid up candle", 0.08
    return "", 0.0
