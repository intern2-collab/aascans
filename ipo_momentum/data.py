"""
Data layer: fetch daily OHLCV (in INR) and listing dates from Yahoo Finance.

Why Yahoo directly (not yfinance): the yfinance cookie/crumb handshake is
flaky behind proxies. The v8 chart endpoint is stable, returns the listing
date via meta.firstTradeDate, and works with a plain requests GET + backoff.

Everything is cached to disk (parquet) so a backtest re-run is instant and
does not re-hammer Yahoo.
"""
from __future__ import annotations
import os, time, json, datetime as dt
from typing import Optional
import requests
import pandas as pd

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36"
}
_HOSTS = [
    "https://query1.finance.yahoo.com",
    "https://query2.finance.yahoo.com",
]

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _chart(symbol: str, rng: str = "3y", interval: str = "1d",
           max_retries: int = 6, pause: float = 1.5) -> Optional[dict]:
    """Raw Yahoo v8 chart pull with host-rotation + exponential backoff."""
    last = None
    sym_url = symbol.replace("^", "%5E")   # index tickers (^CRSLDX, ^NSEI) need the caret encoded
    for attempt in range(max_retries):
        host = _HOSTS[attempt % len(_HOSTS)]
        url = f"{host}/v8/finance/chart/{sym_url}?range={rng}&interval={interval}"
        try:
            r = requests.get(url, headers=_UA, timeout=25)
            if r.status_code == 200:
                return r.json()
            last = r.status_code
            if r.status_code in (404, 400):  # symbol doesn't exist; don't retry
                return {"_err": r.status_code}
        except Exception as e:  # noqa
            last = str(e)[:60]
        time.sleep(pause * (attempt + 1))
    return {"_err": last}


def _to_frame(js: dict) -> Optional[pd.DataFrame]:
    try:
        res = js["chart"]["result"][0]
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
        adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose")
        idx = pd.to_datetime(ts, unit="s").normalize()
        df = pd.DataFrame({
            "open": q.get("open"), "high": q.get("high"),
            "low": q.get("low"), "close": q.get("close"),
            "volume": q.get("volume"),
        }, index=idx)
        df["adjclose"] = adj if adj is not None else df["close"]
        df = df[~df.index.duplicated(keep="last")].dropna(subset=["close"])
        return df
    except Exception:
        return None


def listing_date(js: dict) -> Optional[dt.date]:
    try:
        ftd = js["chart"]["result"][0]["meta"].get("firstTradeDate")
        return dt.datetime.utcfromtimestamp(ftd).date() if ftd else None
    except Exception:
        return None


def get_history(symbol: str, suffix: str = ".NS", rng: str = "3y",
                use_cache: bool = True, refresh: bool = False,
                max_age_hours: float = None) -> tuple[Optional[pd.DataFrame], Optional[dt.date]]:
    """
    Return (price_dataframe, listing_date) for one symbol.
    price_dataframe index = trading days, columns include adjclose & volume.

    Cache is used only when it is FRESH: refresh=True always re-fetches, and
    max_age_hours (when set) forces a re-fetch of any cache older than that many
    hours. This prevents serving a stale close.
    """
    yh = symbol if symbol.endswith((".NS", ".BO")) else symbol + suffix
    cache_px = os.path.join(CACHE_DIR, f"{yh}.csv")
    cache_meta = os.path.join(CACHE_DIR, f"{yh}.meta.json")
    fresh_enough = use_cache and not refresh and os.path.exists(cache_px) and os.path.exists(cache_meta)
    if fresh_enough and max_age_hours is not None:
        try:
            age_h = (time.time() - os.path.getmtime(cache_px)) / 3600.0
            if age_h > max_age_hours:
                fresh_enough = False
        except Exception:
            fresh_enough = False
    if fresh_enough:
        try:
            df = pd.read_csv(cache_px, index_col=0, parse_dates=True)
            meta = json.load(open(cache_meta))
            ld = dt.date.fromisoformat(meta["listing_date"]) if meta.get("listing_date") else None
            return df, ld
        except Exception:
            pass
    js = _chart(yh, rng=rng)
    if not js or "_err" in js:
        return None, None
    df = _to_frame(js)
    ld = listing_date(js)
    if df is not None and len(df):
        df.to_csv(cache_px)
        json.dump({"listing_date": ld.isoformat() if ld else None,
                   "symbol": symbol, "yahoo": yh}, open(cache_meta, "w"))
    return df, ld


def build_price_panel(symbols: list[str], suffix: str = ".NS", rng: str = "3y",
                      refresh: bool = False, pause: float = 0.6,
                      verbose: bool = True, max_age_hours: float = None) -> tuple[pd.DataFrame, dict]:
    """
    Fetch all symbols and return:
      - panel: DataFrame of adjusted close, columns = symbols, index = dates
      - meta:  {symbol: {"listing_date": date, "df": full ohlcv df}}
    refresh=True re-fetches all; max_age_hours re-fetches only stale caches.
    """
    closes, meta = {}, {}
    for i, s in enumerate(symbols):
        df, ld = get_history(s, suffix=suffix, rng=rng, refresh=refresh, max_age_hours=max_age_hours)
        if df is not None and len(df) > 5:
            closes[s] = df["adjclose"]
            meta[s] = {"listing_date": ld, "df": df}
            if verbose:
                print(f"[{i+1}/{len(symbols)}] {s:14} ok  list={ld} bars={len(df)}")
        else:
            if verbose:
                print(f"[{i+1}/{len(symbols)}] {s:14} -- no data")
        time.sleep(pause)
    panel = pd.DataFrame(closes).sort_index()
    return panel, meta
