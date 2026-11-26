"""
Writes the AASCANS website's data feed (webapp/data.json) from a scan.

The website itself (webapp/index.html, style.css, app.js) is static and branded;
only this data file changes each run. deploy.py then pushes webapp/ to the host.
For each flagged stock we include recent OHLC candles plus overlays (50/200-day
EMA, volume, and the 52-week high) so the site can draw a richer chart.
"""
from __future__ import annotations
import json, os, datetime as dt
import numpy as np
import pandas as pd

from . import pivots as pv
from .patterns import detect_patterns, to_weekly

DAILY_BARS = 90
WEEKLY_BARS = 60


def _overlays(src: pd.DataFrame, n: int, tf: str):
    """Return (candles, ema50, ema200, vol, hi52) for the last n bars.

    EMAs are computed over the FULL history (so a 200-EMA is meaningful even
    though only the last n bars are drawn), then sliced to the window. The
    52-week high is the highest high over the last year (252 daily / 52 weekly).
    """
    d = pv.ohlc(src)                      # open/high/low/close/volume, numeric
    if not len(d):
        return [], [], [], [], 0.0
    close = d["close"].astype(float)
    e50_full = close.ewm(span=50, adjust=False).mean()
    e200_full = close.ewm(span=200, adjust=False).mean()
    hi_win = 52 if tf == "weekly" else 252
    hi52 = float(d["high"].tail(hi_win).max())

    idx = src.tail(n).index
    dd = d.tail(n).reset_index(drop=True)
    e50 = e50_full.tail(n).reset_index(drop=True)
    e200 = e200_full.tail(n).reset_index(drop=True)

    candles, ema50, ema200, vol = [], [], [], []
    m = min(len(dd), len(idx))
    for i in range(m):
        r = dd.iloc[i]
        ms = int(pd.Timestamp(idx[i]).timestamp() * 1000)
        candles.append([ms, round(float(r["open"]), 2), round(float(r["high"]), 2),
                        round(float(r["low"]), 2), round(float(r["close"]), 2)])
        ema50.append(round(float(e50.iloc[i]), 2))
        ema200.append(round(float(e200.iloc[i]), 2))
        v = r.get("volume", 0)
        vol.append(int(float(v)) if pd.notna(v) else 0)
    return candles, ema50, ema200, vol, round(hi52, 2)


def _rows_for(meta: dict, companies: dict, tf: str, market: dict = None) -> list:
    market = market or {}
    n_bars = WEEKLY_BARS if tf == "weekly" else DAILY_BARS
    rows = []
    for sym, m in meta.items():
        df = m.get("df")
        hits = detect_patterns(df, timeframe=tf)
        if not hits:
            continue
        src = to_weekly(df) if tf == "weekly" else df
        d = pv.ohlc(src)
        if len(d) < 6:
            continue
        window = d["high"].values[-12:-2]
        level = float(np.max(window)) if len(window) else float(d["high"].iloc[-1])
        candles, ema50, ema200, vol, hi52 = _overlays(src, n_bars, tf)
        mkt = market.get(sym, "IN")               # "IN", "US" (S&P 500), or "US2" (Russell-only)
        rows.append({
            "symbol": sym,
            "company": companies.get(sym, ""),
            "mkt": mkt,                            # which index/market this belongs to
            "cur": "$" if mkt in ("US", "US2") else "₹",  # $ for US, ₹ for India
            "last": round(float(d["close"].iloc[-1]), 2),
            "brk": int(sum(1 for h in hits if h.get("status") == "breakout")),
            "conf": round(max(h["confidence"] for h in hits), 2),
            "level": round(level, 2),
            "hi52": hi52,                          # 52-week high
            "patterns": [{"name": h["pattern"], "status": h.get("status", ""),
                          "detail": h["detail"], "conf": h["confidence"]} for h in hits],
            "candles": candles,
            "ema50": ema50,                        # 50-period EMA, aligned to candles
            "ema200": ema200,                      # 200-period EMA, aligned to candles
            "vol": vol,                            # volume, aligned to candles
        })
    rows.sort(key=lambda r: (r["brk"], r["conf"]), reverse=True)
    return rows


def build_data(meta: dict, companies: dict, out_json: str,
               timeframes=("weekly", "daily"), market: dict = None) -> dict:
    data = {"generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "universe": len(meta), "frames": {}}
    for tf in timeframes:
        data["frames"][tf] = _rows_for(meta, companies, tf, market=market)
    os.makedirs(os.path.dirname(out_json) or ".", exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    return {tf: len(data["frames"].get(tf, [])) for tf in timeframes}
