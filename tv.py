"""
tv.py — TradingView chart deep links for any Yahoo-style symbol / timeframe.

Builds a browser link to open the symbol on TradingView at the matching chart
interval.  Used to link every scanned zone back to its price chart, exactly like
the option-chain deep links in options.py.
"""
from __future__ import annotations

from urllib.parse import quote

# Our timeframe label -> TradingView chart interval.
TF_TO_TV = {
    "10m": "10", "15m": "15", "30m": "30", "75m": "60", "1h": "60", "2h": "120",
    "4h": "240", "6h": "360", "8h": "720", "1D": "1D", "1W": "1W", "1M": "1M",
}

# Index symbols -> TradingView NSE index codes.
_INDEX_TV = {
    "^NSEI": "NSE:NIFTY",
    "^NSEBANK": "NSE:BANKNIFTY",
    "^NIFTY": "NSE:NIFTY",
}

_TV_BASE_URL = "https://www.tradingview.com/chart/"


def tv_symbol(symbol: str) -> str:
    """Return a TradingView symbol string (e.g. NSE:RELIANCE, NSE:NIFTY)."""
    s = str(symbol).strip()
    if s.upper() in _INDEX_TV:
        return _INDEX_TV[s.upper()]
    base = s.replace(".NS", "").replace(".BO", "").replace("^", "").upper()
    return f"NSE:{base}"


def chart_url(symbol: str, timeframe: str = "1D") -> str:
    """Return a full TradingView chart URL for a symbol / timeframe."""
    iv = TF_TO_TV.get(str(timeframe).lower().replace(" ", ""), TF_TO_TV.get(timeframe, "D"))
    return f"{_TV_BASE_URL}?symbol={quote(tv_symbol(symbol))}&interval={iv}"


def is_index(symbol: str) -> bool:
    return str(symbol).strip() in _INDEX_TV


if __name__ == "__main__":
    print(chart_url("RELIANCE.NS", "4h"))
    print(chart_url("^NSEI", "1D"))
    print(chart_url("TCS.NS", "75m"))
    print(chart_url("^NSEBANK", "2h"))
