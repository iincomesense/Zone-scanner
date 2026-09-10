"""
marketdata.py — unified live-quote layer for the MarketHub dashboard.

Two free sources are used so a single outage doesn't blank the board:

  1. Yahoo Finance (yfinance)  — primary, async pooled, works for most tickers.
  2. TradingView scanner        — secondary, used for GIFT NIFTY (NSEIX) and as a
                                  fallback when Yahoo returns nothing.

Every quote is a dict:
   {'symbol','name','price','prev','change','chg_pct','src','group','row','up'}
Missing values are filled with None so the UI degrades gracefully.
"""
from __future__ import annotations

import time
import requests
import yfinance as yf

# --------------------------------------------------------------------------- #
#  Dashboard layout: 4 rows, each a list of tiles.  Each tile = (label, list of
#  (source, symbol) candidates tried in order).
# --------------------------------------------------------------------------- #
TILES = [
    # ---- Group 'FX / Currency' ------------------------------------------ #
    ("dollar", [
        {"label": "DXY", "name": "US Dollar Index", "symbols": [("yahoo", "DX-Y.NYB"), ("tv", "TVC:DXY")]},
        {"label": "USDINR", "name": "USD / Indian Rupee", "symbols": [("yahoo", "INR=X")]},
    ]),
    # ---- Group 'Rates' ---------------------------------------------------- #
    ("rates", [
        {"label": "TLT", "name": "iShares 20+ Yr Treasury", "symbols": [("yahoo", "TLT")]},
        {"label": "US 10Y", "name": "US 10-Yr Treasury Yield", "symbols": [("yahoo", "^TNX")]},
    ]),
    # ---- Group 'Commodities' --------------------------------------------- #
    ("commodities", [
        {"label": "XAUUSD", "name": "Gold Spot / USD", "symbols": [("yahoo", "GC=F"), ("tv", "OANDA:XAUUSD")]},
        {"label": "XAGUSD", "name": "Silver Spot / USD", "symbols": [("yahoo", "SI=F"), ("tv", "OANDA:XAGUSD")]},
        {"label": "SPOTCRUDE", "name": "Crude Oil (WTI) Cash", "symbols": [("yahoo", "CL=F"), ("tv", "TVC:USOIL")]},
    ]),
    # ---- Group 'Indices' -------------------------------------------------- #
    ("indices", [
        {"label": "GIFT NIFTY", "name": "GIFT NIFTY 50 Index Future", "symbols": [("tv", "NSEIX:NIFTY1!"), ("yahoo", "^NSEI")]},
        {"label": "NIFTY 50", "name": "NIFTY 50 Index", "symbols": [("yahoo", "^NSEI"), ("tv", "NSE:NIFTY")]},
        {"label": "US30", "name": "Dow Jones 30", "symbols": [("yahoo", "^DJI")]},
        {"label": "US500", "name": "S&P 500 Index", "symbols": [("yahoo", "^GSPC")]},
        {"label": "JP225", "name": "Nikkei 225", "symbols": [("yahoo", "^N225")]},
        {"label": "SSE", "name": "SSE Composite (China)", "symbols": [("yahoo", "000001.SS")]},
    ]),
]

FLAT = [t for (_g, tiles) in TILES for t in tiles]
GROUPS = {k: v for k, v in TILES}
ROW_BY_GROUP = {"dollar": 1, "rates": 2, "commodities": 3, "indices": 4}

# TradingView chart symbol for each board tile -> built-in chart link (tap to open).
TV_CHART = {
    "DXY": "TVC:DXY",
    "USDINR": "FX_IDC:USDINR",
    "TLT": "AMEX:TLT",
    "US 10Y": "TVC:US10Y",
    "XAUUSD": "OANDA:XAUUSD",
    "XAGUSD": "OANDA:XAGUSD",
    "SPOTCRUDE": "TVC:USOIL",
    "GIFT NIFTY": "NSEIX:NIFTY1!",
    "NIFTY 50": "NSE:NIFTY",
    "US30": "TVC:DJI",
    "US500": "TVC:SPX",
    "JP225": "TVC:NI225",
    "SSE": "SSE:000001",
}


def tv_chart_symbol(label):
    """Return the TradingView chart symbol for a board tile label (fallback = label)."""
    return TV_CHART.get(str(label).strip(), str(label).strip())


def _yf_quote(sym: str):
    """Return (price, prev) or (None, None).  prev uses the prior close so intraday
    change is measured against the previous session (live-feed convention)."""
    try:
        t = yf.Ticker(sym)
        h = t.history(period="5d")
        if h is None or len(h) == 0:
            p = t.fast_info
            return getattr(p, "last_price", None), getattr(p, "previous_close", None)
        last = float(h["Close"].iloc[-1])
        prev = float(h["Close"].iloc[-2]) if len(h) > 1 else float(h["Close"].iloc[-1])
        return last, prev
    except Exception:
        return None, None


def _tv_quote(sym: str):
    """Fetch a single symbol through the TradingView scanner (multi-field)."""
    try:
        payload = {
            "symbols": {"tickers": [sym], "query": {"types": []}},
            "columns": ["name", "description", "close", "prev_close", "change",
                        "change_abs", "exchange"],
        }
        r = requests.post("https://scanner.tradingview.com/futures/scan",
                          json=payload, timeout=8,
                          headers={"User-Agent": "Mozilla/5.0",
                                   "Content-Type": "application/json"})
        d = r.json()
        for it in d.get("data", []):
            if it.get("s") != sym:
                continue
            col = it["d"]
            if col[2] is None:
                continue
            price = float(col[2])
            prev = col[3] if col[3] is not None else (price - (col[5] or 0.0))
            return price, float(prev) if prev else None
    except Exception:
        pass
    return None, None


def _tv_quote_bulk(symbols):
    """Fetch many TradingView symbols in ONE request (fast path)."""
    try:
        payload = {"symbols": {"tickers": list(symbols)}, "columns": [
            "name", "description", "close", "prev_close", "change", "change_abs", "exchange"]}
        r = requests.post("https://scanner.tradingview.com/futures/scan",
                          json=payload, timeout=8,
                          headers={"User-Agent": "Mozilla/5.0",
                                   "Content-Type": "application/json"})
        out = {}
        for it in r.json().get("data", []):
            col = it["d"]
            if col[2] is None:
                continue
            price = float(col[2])
            prev = col[3] if col[3] is not None else (price - (col[5] or 0.0))
            out[it["s"]] = (price, float(prev) if prev else None)
        return out
    except Exception:
        return {}


def fetch_all():
    """Fetch every tile's quote, trying sources in listed order.
    Uses a shared TradingView bulk call to keep it fast."""
    results = {}
    # Prefer TV where it is the only/primary source (GIFT NIFTY etc.)
    try:
        tv_symbols = [t["symbols"][0][1] for t in FLAT if t["symbols"][0][0] == "tv"]
        tv_bulk = _tv_quote_bulk(tv_symbols)
    except Exception:
        tv_bulk = {}

    for tile in FLAT:
        got = None
        src = "yahoo"
        for (kind, sym) in tile["symbols"]:
            if kind == "tv":
                if sym in tv_bulk and tv_bulk[sym][0] is not None:
                    price, prev = tv_bulk[sym]
                    got = (price, prev)
                    src = "tv"
                    break
                else:
                    price, prev = _tv_quote(sym)
                    if price is not None:
                        got = (price, prev); src = "tv"; break
            else:  # yahoo
                price, prev = _yf_quote(sym)
                if price is not None:
                    got = (price, prev); src = "yahoo"; break
        price, prev = (got[0], got[1]) if got else (None, None)
        change = None
        chg_pct = None
        if price is not None:
            if prev and prev:
                change = price - prev
                chg_pct = (change / prev) * 100.0
            else:
                change = None
        results[tile["label"]] = {
            "symbol": tile["label"],
            "name": tile["name"],
            "price": price,
            "prev": prev,
            "change": change,
            "chg_pct": chg_pct,
            "src": src,
            "group": _which_group(tile["label"]),
            "up": (chg_pct or 0.0) >= 0,   # neutral counts as neutral/up
            "up_": (chg_pct if chg_pct is not None else 0.0) > 0,
        }
    return results


def _which_group(label):
    for g, tiles in GROUPS.items():
        for t in tiles:
            if t["label"] == label:
                return g
    return "other"


def get_group_tiles(group):
    return GROUPS.get(group, [])


def symbol_for(label):
    for t in FLAT:
        if t["label"] == label:
            return t["symbols"][0][1]
    return None


if __name__ == "__main__":
    import json
    d = fetch_all()
    for k, v in d.items():
        print(f"{k:10s} price={v['price']} chg%={v['chg_pct']} src={v['src']}")
