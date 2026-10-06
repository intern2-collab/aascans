#!/usr/bin/env python3
"""
Pattern scanner runner — the engine where we test the detectors on real charts.

Loads a universe (default data/universe.csv), fetches daily OHLCV from Yahoo,
runs the 23 bullish detectors on DAILY and WEEKLY bars, and writes:
  output/patterns_daily.csv, output/patterns_weekly.csv   (raw hits)
  output/patterns_report.html                             (review page)

Usage:
  python scan_patterns.py                       # full universe, daily+weekly
  python scan_patterns.py --limit 30            # first 30 names (quick test)
  python scan_patterns.py --symbols RELIANCE,TCS,INFY
  python scan_patterns.py --timeframe weekly    # weekly only
  python scan_patterns.py --rng 2y --pause 0.3
"""
import argparse, os, sys, datetime as dt
import warnings
warnings.filterwarnings("ignore")
import pandas as pd

from ipo_momentum.data import build_price_panel
from ipo_momentum.patterns import scan_universe

OUT = "output"


# where the IPO system keeps its genuine-IPO symbols
IPO_SOURCES = ["output/rankings_1m_latest.csv", "data/seen_symbols.csv"]


def _read_symbols(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_csv(path)
    except Exception:
        return []
    col = "symbol" if "symbol" in df.columns else df.columns[0]
    return [str(s).strip().upper() for s in df[col] if str(s).strip()]


def load_symbols(args) -> tuple[list, int]:
    """Returns (symbols, n_ipos_merged). Universe = Nifty list + the IPO set."""
    if args.symbols:
        return [s.strip().upper() for s in args.symbols.split(",") if s.strip()], 0

    ipo = []
    if not args.no_ipos:
        for src in IPO_SOURCES:
            ipo += _read_symbols(src)
    ipo = list(dict.fromkeys(ipo))                 # dedup, keep order

    if args.ipos_only:
        base = []
    else:
        if not os.path.exists(args.universe):
            sys.exit(f"universe file not found: {args.universe}")
        base = _read_symbols(args.universe)

    merged = list(dict.fromkeys(base + ipo))       # union, base first
    n_ipos_new = len([s for s in ipo if s not in set(base)])
    if args.limit:
        merged = merged[:args.limit]
    return merged, n_ipos_new


def _html(daily: pd.DataFrame, weekly: pd.DataFrame, n_scanned: int, ts: str) -> str:
    def section(title, df, note):
        if df is None or not len(df):
            return f"<h2>{title}</h2><p class='muted'>No patterns detected. {note}</p>"
        rows = []
        for _, r in df.iterrows():
            pats = str(r["patterns"]).replace("*", "<b style='color:#37d67a'>&#9650;</b>")
            rows.append(
                "<tr>"
                f"<td class='sym'>{r['symbol']}</td>"
                f"<td class='num'>{r.get('n_breakouts', 0)}</td>"
                f"<td>{pats}</td>"
                f"<td class='num'>{r['confidence']:.2f}</td>"
                f"<td class='num'>{r['last_price']:.2f}</td>"
                f"<td class='det'>{r['details']}</td>"
                "</tr>")
        return (f"<h2>{title} <span class='muted'>({len(df)} stocks)</span></h2>"
                "<table><thead><tr><th>Symbol</th><th>Brk</th><th>Patterns "
                "(&#9650;=confirmed breakout)</th><th>Conf</th><th>Price</th>"
                "<th>Measured detail — cross-check on the chart</th></tr></thead><tbody>"
                + "\n".join(rows) + "</tbody></table>")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pattern Scan</title><style>
:root{{color-scheme:light dark}}
body{{font:13px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:#0f1216;color:#e8eaed}}
.wrap{{max-width:1200px;margin:0 auto;padding:20px 16px 60px}}
h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:16px;margin:26px 0 8px}}
.muted{{color:#9aa0a6}} .meta{{color:#9aa0a6;font-size:12px;margin-bottom:10px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th,td{{padding:6px 8px;border-bottom:1px solid #262b31;text-align:left;vertical-align:top}}
th{{color:#9aa0a6;position:sticky;top:0;background:#0f1216}}
td.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
td.sym{{font-weight:700;white-space:nowrap}} td.det{{color:#c4c7ca;font-size:11.5px}}
tr:hover td{{background:#161b21}}
</style></head><body><div class="wrap">
<h1>Bullish Pattern Scan</h1>
<div class="meta">Generated {ts} · {n_scanned} symbols scanned · 23 bullish patterns from
Bulkowski · &#9650; marks a <b>confirmed breakout</b> (else the setup is still forming).
Every flag shows its measured numbers — verify against the candlestick chart.</div>
<p class="muted">Weekly first (slower, less noise); daily below.</p>
{section("Weekly patterns", weekly, "")}
{section("Daily patterns", daily, "")}
</div></body></html>"""


def main():
    p = argparse.ArgumentParser(description="Bullish chart-pattern scanner")
    p.add_argument("--universe", default="data/universe.csv")
    p.add_argument("--symbols", default="", help="comma-separated override list")
    p.add_argument("--limit", type=int, default=0, help="scan only the first N (quick test)")
    p.add_argument("--timeframe", default="both", choices=["daily", "weekly", "both"])
    p.add_argument("--rng", default="2y", help="Yahoo history range (2y gives enough weekly bars)")
    p.add_argument("--pause", type=float, default=0.35, help="seconds between fetches")
    p.add_argument("--sheet", action="store_true",
                   help="also push results to the Google Sheet (Patterns (Weekly)/(Daily) tabs)")
    p.add_argument("--no-ipos", action="store_true",
                   help="scan the universe file only, do NOT merge the IPO set")
    p.add_argument("--ipos-only", action="store_true",
                   help="scan ONLY the genuine-IPO set (skip the Nifty universe file)")
    p.add_argument("--no-site", action="store_true",
                   help="skip writing webapp/data.json for the AASCANS site")
    p.add_argument("--no-us", action="store_true",
                   help="skip the US S&P 500 set (India only)")
    p.add_argument("--sp500-file", default="data/sp500.csv",
                   help="S&P 500 ticker list (US symbols, Yahoo-ready)")
    p.add_argument("--russell-only", action="store_true",
                   help="scan ONLY the Russell-3000 (ex-S&P-500) set and write its own feed")
    p.add_argument("--russell-file", default="data/russell3000.csv",
                   help="Russell-3000 (ex-S&P-500) ticker list")
    p.add_argument("--out-json", default="webapp/data.json",
                   help="site feed to write (Russell run uses webapp/data_r3000.json)")
    p.add_argument("--deploy", action="store_true",
                   help="after the scan, push the AASCANS site live (needs data/netlify_token.txt)")
    p.add_argument("--cache-hours", type=float, default=0,
                   help="reuse cached prices younger than N hours (0 = always fetch fresh; "
                        "default 0 so closing prices are never stale)")
    a = p.parse_args()

    fresh = a.cache_hours <= 0

    # ---- Russell-3000 (ex-S&P-500) daily feed: its own file, no India/sheet ----
    if a.russell_only:
        if not os.path.exists(a.russell_file):
            sys.exit(f"Russell file not found: {a.russell_file}")
        rsyms = _read_symbols(a.russell_file)
        out = a.out_json if a.out_json != "webapp/data.json" else "webapp/data_r3000.json"
        print(f"[{dt.datetime.now():%H:%M:%S}] fetching {len(rsyms)} Russell-3000 symbols "
              f"({'fresh' if fresh else f'cache<{a.cache_hours}h'}) ...", flush=True)
        _, rmeta = build_price_panel(rsyms, suffix="", rng=a.rng, pause=a.pause,
                                     verbose=False, refresh=fresh,
                                     max_age_hours=(None if fresh else a.cache_hours))
        print(f"  got price data for {len(rmeta)}/{len(rsyms)} Russell symbols", flush=True)
        market = {s: "US2" for s in rmeta}
        from ipo_momentum.site_builder import build_data
        tfs = ("weekly", "daily") if a.timeframe == "both" else (a.timeframe,)
        counts = build_data(rmeta, {}, out, timeframes=tfs, market=market)
        print(f"[{dt.datetime.now():%H:%M:%S}] wrote {out} (Russell feed — {counts})")
        return

    syms, n_ipos = load_symbols(a)
    scope = ("IPO set only" if a.ipos_only else
             f"universe + {n_ipos} IPOs" if not a.no_ipos else "universe only")
    fresh = a.cache_hours <= 0
    print(f"[{dt.datetime.now():%H:%M:%S}] fetching {len(syms)} symbols ({scope}, {a.rng}, "
          f"{'fresh' if fresh else f'cache<{a.cache_hours}h'}) ...", flush=True)
    _, meta = build_price_panel(syms, rng=a.rng, pause=a.pause, verbose=False,
                                refresh=fresh, max_age_hours=(None if fresh else a.cache_hours))
    print(f"  got price data for {len(meta)}/{len(syms)} Indian symbols", flush=True)

    # ---- US S&P 500 (fetched WITHOUT the .NS suffix; own market tag) ----
    us_meta = {}
    market = {s: "IN" for s in meta}
    if not a.no_us and os.path.exists(a.sp500_file):
        us_syms = _read_symbols(a.sp500_file)
        print(f"[{dt.datetime.now():%H:%M:%S}] fetching {len(us_syms)} US S&P 500 symbols ...", flush=True)
        _, us_meta = build_price_panel(us_syms, suffix="", rng=a.rng, pause=a.pause,
                                       verbose=False, refresh=fresh,
                                       max_age_hours=(None if fresh else a.cache_hours))
        for s in us_meta:
            market[s] = "US"
        print(f"  got price data for {len(us_meta)}/{len(us_syms)} US symbols", flush=True)
    elif not a.no_us:
        print(f"  S&P 500 file not found ({a.sp500_file}) — scanning India only", flush=True)

    os.makedirs(OUT, exist_ok=True)
    names = {}
    daily = weekly = pd.DataFrame()
    if a.timeframe in ("daily", "both"):
        daily = scan_universe(meta, names, timeframe="daily")
        daily.to_csv(f"{OUT}/patterns_daily.csv", index=False)
        print(f"  DAILY : {len(daily)} stocks with patterns "
              f"({int(daily['n_breakouts'].sum()) if len(daily) else 0} breakout-flags)")
    if a.timeframe in ("weekly", "both"):
        weekly = scan_universe(meta, names, timeframe="weekly")
        weekly.to_csv(f"{OUT}/patterns_weekly.csv", index=False)
        print(f"  WEEKLY: {len(weekly)} stocks with patterns "
              f"({int(weekly['n_breakouts'].sum()) if len(weekly) else 0} breakout-flags)")

    ts = f"{dt.datetime.now():%Y-%m-%d %H:%M}"
    with open(f"{OUT}/patterns_report.html", "w", encoding="utf-8") as f:
        f.write(_html(daily, weekly, len(meta), ts))
    print(f"[{dt.datetime.now():%H:%M:%S}] wrote {OUT}/patterns_report.html + CSVs")

    if not a.no_site:
        try:
            from ipo_momentum.site_builder import build_data
            tfs = ("weekly", "daily") if a.timeframe == "both" else (a.timeframe,)
            site_meta = {**meta, **us_meta}           # India + US on the website
            counts = build_data(site_meta, names, "webapp/data.json",
                                timeframes=tfs, market=market)
            print(f"[{dt.datetime.now():%H:%M:%S}] wrote webapp/data.json "
                  f"(AASCANS feed — {counts}, {len(us_meta)} US names)")
        except Exception as e:
            print(f"  site data build skipped: {str(e)[:120]}")

    if a.deploy:
        try:
            from deploy import deploy as _dep
            _dep("webapp", "aascans")
        except SystemExit as e:
            print(f"  deploy skipped: {e}")
        except Exception as e:
            print(f"  deploy error: {str(e)[:160]}")

    if a.sheet:
        try:
            from ipo_momentum import gsheet
            ok0, why = gsheet.available()
            if not ok0:
                print(f"  Google Sheet skipped: {why}")
            else:
                if a.timeframe in ("weekly", "both"):
                    ok, msg = gsheet.push_patterns(weekly, ts, tab="Patterns (Weekly)",
                                                   title="BULLISH PATTERNS — WEEKLY (slower, less noise)")
                    print(f"  Sheet 'Patterns (Weekly)' -> {'ok' if ok else 'FAILED'}: {msg}")
                if a.timeframe in ("daily", "both"):
                    ok, msg = gsheet.push_patterns(daily, ts, tab="Patterns (Daily)",
                                                   title="BULLISH PATTERNS — DAILY")
                    print(f"  Sheet 'Patterns (Daily)'  -> {'ok' if ok else 'FAILED'}: {msg}")
        except Exception as e:
            print(f"  Google Sheet push error: {str(e)[:120]}")


if __name__ == "__main__":
    main()
