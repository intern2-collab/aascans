"""
Google-Sheet writer for the live paper portfolio.

Auth: a Google service-account JSON key (data/gsheet_service_account.json).
The user creates one blank Google Sheet, shares it (Editor) with the service
account's email, and puts the sheet's URL/key in data/gsheet_config.txt.

Tabs written every cycle: Dashboard, Portfolio, TradeLog, PnL, NAVHistory.
A portfolio-vs-Nifty500 line chart is added to NAVHistory once.

All Sheets calls are best-effort: any failure is caught and reported so the
trading loop never dies because the sheet is briefly unreachable.
"""
from __future__ import annotations
import os, re
import pandas as pd

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_HERE = os.path.dirname(os.path.dirname(__file__))
_CRED = os.path.join(_HERE, "data", "gsheet_service_account.json")
_CONF = os.path.join(_HERE, "data", "gsheet_config.txt")
TABS = ["Dashboard", "Portfolio", "TradeLog", "PnL", "NAVHistory", "Patterns"]


def _sheet_key() -> str | None:
    if os.path.exists(_CONF):
        t = open(_CONF, encoding="utf-8").read().strip()
        m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", t)   # full URL
        return m.group(1) if m else (t or None)
    return None


def available() -> tuple[bool, str]:
    """Is the Sheets path ready to use? Returns (ok, reason-if-not)."""
    try:
        import gspread  # noqa
        from google.oauth2.service_account import Credentials  # noqa
    except Exception:
        return False, "gspread/google-auth not installed (pip install gspread google-auth)"
    if not os.path.exists(_CRED):
        return False, f"service-account key missing at {_CRED}"
    if not _sheet_key():
        return False, f"sheet URL/key missing at {_CONF}"
    return True, ""


def connect():
    """Return the opened spreadsheet, or raise with a clear message."""
    import gspread
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_file(_CRED, scopes=_SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(_sheet_key())


def _ws(sh, title: str, rows: int = 200, cols: int = 12):
    try:
        return sh.worksheet(title)
    except Exception:
        return sh.add_worksheet(title=title, rows=rows, cols=cols)


def _put(ws, values: list):
    """Clear a tab and write a list-of-lists (header + rows)."""
    ws.clear()
    if values:
        ws.update(values, value_input_option="RAW")


def _df_to_values(df: pd.DataFrame) -> list:
    if df is None or not len(df):
        return [["(none)"]]
    return [list(df.columns)] + df.astype(object).where(pd.notna(df), "").values.tolist()


def push(state: dict, holdings_df: pd.DataFrame, metrics: dict,
         nav_hist_df: pd.DataFrame, updated_ts: str) -> tuple[bool, str]:
    """Write every tab. Returns (ok, message)."""
    ok, why = available()
    if not ok:
        return False, why
    try:
        sh = connect()
    except Exception as e:
        return False, f"connect failed: {str(e)[:120]}"

    try:
        # ---- Dashboard (returns summary + benchmark comparison) ----
        m = metrics or {}
        dash = [
            ["IPO MOMENTUM — LIVE PAPER PORTFOLIO"],
            ["Last updated", updated_ts],
            ["Inception", str(state.get("inception"))[:19]],
            ["Initial capital (Rs)", state.get("initial_capital")],
            [],
            ["METRIC", "PORTFOLIO", "NIFTY 500"],
            ["Current value (Rs)", m.get("nav"), ""],
            ["Absolute return %", m.get("abs_return_pct"), m.get("bench_abs_return_pct")],
            ["CAGR %", m.get("cagr_pct"), m.get("bench_cagr_pct")],
            ["Volatility % (ann.)", m.get("volatility_pct"), ""],
            ["Beta vs Nifty 500", m.get("beta"), ""],
            ["Max drawdown %", m.get("max_drawdown_pct"), ""],
            ["Days live", m.get("days_live"), ""],
            ["Realized P&L (Rs)", round(state.get("realized_pnl", 0.0), 2), ""],
        ]
        _put(_ws(sh, "Dashboard"), dash)

        # ---- Current portfolio ----
        _put(_ws(sh, "Portfolio"), _df_to_values(holdings_df))

        # ---- Trade log (newest last) ----
        tl = pd.DataFrame(state.get("trade_log", []))
        _put(_ws(sh, "TradeLog"), _df_to_values(tl))

        # ---- P&L statement: realized (closed) + unrealized (open) ----
        _put(_ws(sh, "PnL"), _pnl_values(state, holdings_df))

        # ---- NAV history (portfolio vs benchmark, rebased to capital) ----
        _put(_ws(sh, "NAVHistory"), _df_to_values(nav_hist_df))
        _ensure_chart(sh, nav_hist_df)
        return True, "ok"
    except Exception as e:
        return False, f"write failed: {str(e)[:120]}"


def push_patterns(patterns_df: pd.DataFrame, updated_ts: str,
                  tab: str = "Patterns", title: str = "") -> tuple[bool, str]:
    """
    Write a technical-pattern scan to its own `tab`, independently of the portfolio
    push so a pattern-scan failure never touches the portfolio tabs (and vice-versa).
    Call once per timeframe, e.g. tab='Patterns (Weekly)' and tab='Patterns (Daily)'.
    Best-effort.
    """
    ok, why = available()
    if not ok:
        return False, why
    try:
        sh = connect()
    except Exception as e:
        return False, f"connect failed: {str(e)[:120]}"
    try:
        n = 0 if patterns_df is None else len(patterns_df)
        header = [
            [title or f"BULLISH CHART-PATTERN SCAN — {tab}"],
            ["Last updated", updated_ts],
            ["Stocks flagged", n],
            ["Legend", "* on a pattern name = CONFIRMED breakout (else still forming). "
                       "Every flag shows its measured numbers — verify on the chart."],
            [],
        ]
        if n:
            cols = ["symbol", "timeframe", "company", "patterns", "n_breakouts",
                    "n_patterns", "confidence", "last_price", "details"]
            keep = [c for c in cols if c in patterns_df.columns]
            body = [keep] + patterns_df[keep].astype(object).where(
                pd.notna(patterns_df[keep]), "").values.tolist()
        else:
            body = [["(no patterns detected this scan)"]]
        _put(_ws(sh, tab, rows=800, cols=10), header + body)
        return True, f"{n} flagged"
    except Exception as e:
        return False, f"write failed: {str(e)[:120]}"


def _pnl_values(state: dict, holdings_df: pd.DataFrame) -> list:
    rows = [["P&L STATEMENT"], [],
            ["Realized P&L (Rs)", round(state.get("realized_pnl", 0.0), 2)]]
    unreal = float(holdings_df["unrealized_pnl"].sum()) if holdings_df is not None and len(holdings_df) else 0.0
    rows.append(["Unrealized P&L (Rs)", round(unreal, 2)])
    rows.append(["Total P&L (Rs)", round(state.get("realized_pnl", 0.0) + unreal, 2)])
    rows.append([])
    rows.append(["OPEN POSITIONS"])
    if holdings_df is not None and len(holdings_df):
        rows.append(["symbol", "company", "cost", "value", "unrealized_pnl", "unrealized_pct"])
        for _, r in holdings_df.iterrows():
            rows.append([r["symbol"], r["company"], r["cost"], r["value"],
                         r["unrealized_pnl"], r["unrealized_pct"]])
    return rows


def _ensure_chart(sh, nav_hist_df: pd.DataFrame):
    """Add a portfolio-vs-Nifty500 line chart to NAVHistory once (best-effort)."""
    if nav_hist_df is None or len(nav_hist_df) < 2:
        return
    try:
        ws = sh.worksheet("NAVHistory")
        meta = sh.fetch_sheet_metadata()
        for s in meta.get("sheets", []):
            if s["properties"]["title"] == "NAVHistory" and s.get("charts"):
                return                       # chart already present
        sid = ws._properties["sheetId"]
        nrow = len(nav_hist_df) + 1
        req = {"addChart": {"chart": {"spec": {
            "title": "Portfolio vs Nifty 500 (rebased to Rs 5,00,000)",
            "basicChart": {"chartType": "LINE", "legendPosition": "BOTTOM_LEGEND",
                "axis": [{"position": "BOTTOM_AXIS", "title": "Date"},
                         {"position": "LEFT_AXIS", "title": "Value (Rs)"}],
                "domains": [{"domain": {"sourceRange": {"sources": [
                    {"sheetId": sid, "startRowIndex": 0, "endRowIndex": nrow,
                     "startColumnIndex": 0, "endColumnIndex": 1}]}}}],
                "series": [
                    {"series": {"sourceRange": {"sources": [
                        {"sheetId": sid, "startRowIndex": 0, "endRowIndex": nrow,
                         "startColumnIndex": 1, "endColumnIndex": 2}]}}, "targetAxis": "LEFT_AXIS"},
                    {"series": {"sourceRange": {"sources": [
                        {"sheetId": sid, "startRowIndex": 0, "endRowIndex": nrow,
                         "startColumnIndex": 2, "endColumnIndex": 3}]}}, "targetAxis": "LEFT_AXIS"}],
                "headerCount": 1}},
            "position": {"overlayPosition": {"anchorCell": {
                "sheetId": sid, "rowIndex": 1, "columnIndex": 4}}}}}}
        sh.batch_update({"requests": [req]})
    except Exception:
        pass       # a missing chart never blocks the data update
