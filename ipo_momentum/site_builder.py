"""
Writes the AASCANS website's data feed (webapp/data.json) from a scan.

The website itself (webapp/index.html, style.css, app.js) is static and branded;
only this data file changes each run. deploy.py then pushes webapp/ to the host.
For each flagged stock we include recent OHLC candles so the site can draw a
candlestick chart with the breakout level marked.
"""
from __future__ import annotations
import json, os, datetime as dt
import numpy as np
import pandas as pd

from . import pivots as pv
from .patterns import detect_patterns, to_weekly

DAILY_BARS = 90
WEEKLY_BARS = 60


def _candles(src: pd.DataFrame, n: int) -> list:
    idx = src.tail(n).index
    d = pv.ohlc(src).tail(n)
    out = []
    for i, (_, r) in enumerate(d.iterrows()):
        t = idx[i]
        ms = int(pd.Timestamp(t).timestamp() * 1000)
        out.append([ms, round(float(r["open"]), 2), round(float(r["high"]), 2),
                    round(float(r["low"]), 2), round(float(r["close"]), 2)])
    return out


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
            "patterns": [{"name": h["pattern"], "status": h.get("status", ""),
                          "detail": h["detail"], "conf": h["confidence"]} for h in hits],
            "candles": _candles(src, n_bars),
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
