"""
sectors.py — live NSE sector index prices (NIFTY sectoral indices) via NSE allIndices.

NSE is the authoritative source and returns every NIFTY sectoral index (last,
previous close, % change) in one call.  Falls back to Yahoo for the handful of
sector indices Yahoo still carries if NSE is unavailable.
"""
from __future__ import annotations

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/121 Safari/537.36")

# Nifty sector indices -> display label / group.
SECTORS = [
    ("NIFTY AUTO", "Auto"),
    ("NIFTY IT", "IT"),
    ("NIFTY PHARMA", "Pharma"),
    ("NIFTY FMCG", "FMCG"),
    ("NIFTY METAL", "Metal"),
    ("NIFTY ENERGY", "Energy"),
    ("NIFTY REALTY", "Realty"),
    ("NIFTY MEDIA", "Media"),
    ("NIFTY PSU BANK", "PSU Bank"),
    ("NIFTY INFRA", "Infra"),
    ("NIFTY FINANCIAL SERVICES", "FinServ"),
    ("NIFTY BANK", "Bank"),
    ("NIFTY 50", "NIFTY 50"),
]

# Yahoo fallback tickers for a few sectors.
YAHOO_FALLBACK = {
    "NIFTY BANK": "^NSEBANK",
    "NIFTY IT": "^CNXIT",
    "NIFTY PHARMA": "^CNXPHARMA",
}

# TradingView chart symbol for each sector index (built-in chart link, tap to open).
TV_CHART = {
    "NIFTY AUTO": "NSE:NIFTY_AUTO",
    "NIFTY IT": "NSE:CNXIT",
    "NIFTY PHARMA": "NSE:NIFTY_PHARMA",
    "NIFTY FMCG": "NSE:NIFTY_FMCG",
    "NIFTY METAL": "NSE:NIFTY_METAL",
    "NIFTY ENERGY": "NSE:NIFTY_ENERGY",
    "NIFTY REALTY": "NSE:NIFTY_REALTY",
    "NIFTY MEDIA": "NSE:NIFTY_MEDIA",
    "NIFTY PSU BANK": "NSE:NIFTY_PSU_BANK",
    "NIFTY INFRA": "NSE:NIFTY_INFRA",
    "NIFTY FINANCIAL SERVICES": "NSE:NIFTY_FIN",
    "NIFTY BANK": "NSE:BANKNIFTY",
    "NIFTY 50": "NSE:NIFTY",
}


def tv_chart_symbol(full_label):
    """Return the TradingView chart symbol for an NSE sector index (fallback = full)."""
    return TV_CHART.get(str(full_label).strip(), str(full_label).strip())


def _nse_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
        "Origin": "https://www.nseindia.com",
    })
    try:
        s.get("https://www.nseindia.com/", timeout=8)
    except Exception:
        pass
    return s


def fetch_sectors():
    """Return list of dicts {label, full, price, prev, chg_pct, src}, newest = NSE."""
    out = []
    try:
        s = _nse_session()
        r = s.get("https://www.nseindia.com/api/allIndices", timeout=12)
        if r.status_code == 200:
            data = {row.get("index"): row for row in r.json().get("data", [])}
            for full, label in SECTORS:
                row = data.get(full)
                if not row:
                    continue
                last = float(row.get("last"))
                prev = float(row.get("previousClose")) or last
                chg = row.get("percentChange")
                chg = float(chg) if chg not in (None, "") else (
                    (last - prev) / prev * 100 if prev else 0.0)
                out.append({"label": label, "full": full, "price": last,
                            "prev": prev, "chg_pct": chg, "src": "NSE"})
            if out:
                return out
    except Exception:
        pass
    # Fallback to Yahoo for the sectors it carries.
    try:
        import yfinance as yf
        for full, label in SECTORS:
            ticker = YAHOO_FALLBACK.get(full)
            if not ticker:
                continue
            d = yf.download(ticker, period="1mo", interval="1d",
                            progress=False, auto_adjust=False)
            if d is None or d.empty:
                continue
            c = d["Close"].dropna()
            if len(c) < 1:
                continue
            last = float(c.iloc[-1])
            prev = float(c.iloc[-2]) if len(c) > 1 else last
            out.append({"label": label, "full": full, "price": last, "prev": prev,
                        "chg_pct": (last - prev) / prev * 100 if prev else 0.0,
                        "src": "Y"})
    except Exception:
        pass
    return out


if __name__ == "__main__":
    for s in fetch_sectors():
        print(f"{s['label']:10s} {s['price']:>10,.1f}  {s['chg_pct']:+.2f}%  {s['src']}")
