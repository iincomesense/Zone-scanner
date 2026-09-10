"""
options.py — NSE options chain: deep links + best-effort live Open Interest.

NSE restricts the option-chain JSON API for datacenter/cloud IPs (returns `{}`),
so this module:
  1. ALWAYS builds reliable deep links to view the option chain in a browser
     (nseindia.com, niftytrader.in, kotakneo) — these work from any browser.
  2. Best-effort fetches the live strike-wise OI from NSE and computes total
     CALL OI, total PUT OI and the Put-Call Ratio.  If that is blocked (expected
     on Streamlit Cloud), it returns empty and the UI shows only the links.

Scope: index (NIFTY / BANKNIFTY) and equity symbols (RELIANCE, TCS, ...).
"""
from __future__ import annotations

import json
import requests
from urllib.parse import quote

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/121 Safari/537.36")

# F&O index / stock symbols we can look up on the option chain.
EQUITY_FNO = {
    "RELIANCE.NS": "RELIANCE", "TCS.NS": "TCS", "INFY.NS": "INFY",
    "HDFCBANK.NS": "HDFCBANK", "ICICIBANK.NS": "ICICIBANK", "SBIN.NS": "SBIN",
    "BHARTIARTL.NS": "BHARTIARTL", "HINDUNILVR.NS": "HINDUNILVR", "ITC.NS": "ITC",
    "LT.NS": "LT", "BAJFINANCE.NS": "BAJFINANCE", "KOTAKBANK.NS": "KOTAKBANK",
    "AXISBANK.NS": "AXISBANK", "NESTLEIND.NS": "NESTLEIND", "WIPRO.NS": "WIPRO",
    "TITAN.NS": "TITAN", "ULTRACEMCO.NS": "ULTRACEMCO", "ASIANPAINT.NS": "ASIANPAINT",
}
INDEX_FNO = {"^NSEI": "NIFTY", "^NSEBANK": "BANKNIFTY"}

IS_INDEX = {"^NSEI", "^NSEBANK"}


def fno_symbol(symbol: str):
    """Return the NSE F&O symbol for a Yahoo-style symbol (strips .NS / ^)."""
    s = symbol.strip().upper()
    if s in INDEX_FNO:
        return INDEX_FNO[s], True
    if s in EQUITY_FNO:
        return EQUITY_FNO[s], False
    # best effort: strip suffix
    base = s.replace(".NS", "").replace(".BO", "").replace("^", "")
    return base, False


def deep_links(symbol: str):
    """Return a list of {label, url} browser links to view the option chain."""
    fno, is_idx = fno_symbol(symbol)
    links = []
    _q = quote(fno)          # URL-safe symbol (handles M&M -> M%26M)
    _ql = quote(fno.lower())
    if is_idx:
        # Index option chains live on the dedicated index page.
        links.append({"label": "NSE Option Chain",
                      "url": f"https://www.nseindia.com/option-chain"
                             f"?symbol={_q}"})
        links.append({"label": "niftytrader (live)",
                      "url": f"https://www.niftytrader.in/nse-option-chain/{_ql}"})
        links.append({"label": "Kotak Neo",
                      "url": "https://www.kotakneo.com/futures-and-options/"
                             "index-options/nifty-50-option-chain/"})
        links.append({"label": "ICICI Direct",
                      "url": "https://www.icicidirect.com/futures-and-options/"
                             "nifty-option-chain"})
    else:
        # Equity option chains -> use the NSE equity page and aggregators.
        links.append({"label": "NSE Equity OC",
                      "url": f"https://www.nseindia.com/option-chain"
                             f"?symbol={_q}"})
        links.append({"label": "niftytrader (live)",
                      "url": f"https://www.niftytrader.in/equity-option-chain/{_ql}"})
        links.append({"label": "Sensibull",
                      "url": f"https://web.sensibull.com/option-chain?underlying={_q}"})
    return links


def _nse_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/option-chain",
        "Origin": "https://www.nseindia.com",
    })
    try:
        s.get("https://www.nseindia.com/", timeout=8)
    except Exception:
        pass
    return s


def live_oi(symbol: str):
    """Best-effort return dict {symbol, expiry, call_oi, put_oi, pcr, rows, max_call_oi_strike,
    max_put_oi_strike, atm}.  Returns {} if NSE blocks the request (common on cloud)."""
    fno, is_idx = fno_symbol(symbol)
    url = ("https://www.nseindia.com/api/option-chain-indices?symbol=" + fno if is_idx
           else "https://www.nseindia.com/api/option-chain-equities?symbol=" + fno)
    try:
        s = _nse_session()
        r = s.get(url, timeout=12)
        if r.status_code != 200:
            return {}
        data = r.json()
        rec = data.get("records", {})
        rows = rec.get("data", [])
        if not rows:
            return {}
        expiry = rec.get("expiryDates", [])[0] if rec.get("expiryDates") else rows[0].get("expiryDate")
        # nearest expiry (first data block matching the first expiry)
        exdata = [x for x in rows if x.get("expiryDate") in (expiry, rec.get("expiryDates", [None])[0])]
        if not exdata:
            exdata = rows
        call_oi = sum((x.get("CE", {}).get("openInterest") or 0) for x in exdata)
        put_oi = sum((x.get("PE", {}).get("openInterest") or 0) for x in exdata)
        atm = None
        ltp = rec.get("underlyingValue") or rows[0].get("underlying", {}).get("ltp")
        step = _step_for(fno, is_idx)
        if ltp:
            atm = int(round(ltp / step) * step)
        max_call = max((x for x in exdata if x.get("CE")),
                       key=lambda x: x["CE"].get("openInterest") or 0, default=None)
        max_put = max((x for x in exdata if x.get("PE")),
                      key=lambda x: x["PE"].get("openInterest") or 0, default=None)
        return {
            "symbol": fno, "is_index": is_idx, "expiry": expiry,
            "call_oi": call_oi, "put_oi": put_oi,
            "pcr": (put_oi / call_oi) if call_oi else None,
            "atm": atm,
            "max_call_oi_strike": max_call.get("strikePrice") if max_call else None,
            "max_put_oi_strike": max_put.get("strikePrice") if max_put else None,
            "rows": len(exdata),
        }
    except Exception:
        return {}


def _step_for(fno, is_idx):
    # Simplistic step for ATM strike calc (index: 50/100; stock: 5/10/20...)
    if is_idx:
        return 50 if fno == "NIFTY" else 100
    return 5


def top_strikes(symbol: str, n=10, expiry_index=0):
    """Best-effort return list of rows around ATM for a compact OI table."""
    fno, is_idx = fno_symbol(symbol)
    url = ("https://www.nseindia.com/api/option-chain-indices?symbol=" + fno if is_idx
           else "https://www.nseindia.com/api/option-chain-equities?symbol=" + fno)
    try:
        s = _nse_session()
        r = s.get(url, timeout=12)
        if r.status_code != 200:
            return []
        rec = r.json().get("records", {})
        rows = rec.get("data", [])
        if not rows:
            return []
        expiry = rec.get("expiryDates", [])[0]
        rows = [x for x in rows if x.get("expiryDate") == expiry]
        ltp = rec.get("underlyingValue") or (rows[0].get("underlying") or {}).get("ltp")
        step = _step_for(fno, is_idx)
        atm = int(round((ltp / step) * step)) if ltp else None
        if atm is None:
            atm = rows[len(rows) // 2].get("strikePrice")
        near = sorted(rows, key=lambda x: abs((x.get("strikePrice") or 0) - atm))[:n]
        return [{
            "strike": x.get("strikePrice"),
            "ce_oi": (x.get("CE") or {}).get("openInterest"),
            "pe_oi": (x.get("PE") or {}).get("openInterest"),
            "ce_ltp": (x.get("CE") or {}).get("lastPrice"),
            "pe_ltp": (x.get("PE") or {}).get("lastPrice"),
        } for x in near]
    except Exception:
        return []


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE.NS"
    print("links:", deep_links(sym))
    print("live_oi:", live_oi(sym))
