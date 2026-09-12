# -*- coding: utf-8 -*-
"""
marketdata.py — Macro Finance & Global Indices Fetcher
"""
import yfinance as yf

TILES = [
    ("indices", [
        {"label": "NIFTY 50", "symbol": "^NSEI"},
        {"label": "BANK NIFTY", "symbol": "^NSEBANK"},
        {"label": "US30 (Dow)", "symbol": "^DJI"},
        {"label": "US500 (S&P)", "symbol": "^GSPC"}
    ]),
    ("commodities", [
        {"label": "GOLD", "symbol": "GC=F"},
        {"label": "CRUDE OIL", "symbol": "CL=F"}
    ]),
    ("rates", [
        {"label": "US 10Y YIELD", "symbol": "^TNX"},
        {"label": "INDIA 10Y", "symbol": "IN10YT=RR"}
    ]),
    ("dollar", [
        {"label": "USD/INR", "symbol": "INR=X"},
        {"label": "DOLLAR INDEX", "symbol": "DX-Y.NYB"}
    ])
]

def tv_chart_symbol(label):
    # TradingView के लिए सही सिंबल रिज़ॉल्यूशन
    tv_map = {
        "NIFTY 50": "NSE:NIFTY", "BANK NIFTY": "NSE:BANKNIFTY",
        "US30 (Dow)": "TVC:DJI", "US500 (S&P)": "TVC:SPX",
        "GOLD": "OANDA:XAUUSD", "CRUDE OIL": "TVC:USOIL",
        "US 10Y YIELD": "TVC:US10Y", "INDIA 10Y": "TVC:IN10Y",
        "USD/INR": "FX_IDC:USDINR", "DOLLAR INDEX": "TVC:DXY"
    }
    return tv_map.get(label, label)

def fetch_all():
    symbols = []
    for grp, tiles in TILES:
        for t in tiles:
            symbols.append(t["symbol"])
            
    data = {}
    try:
        tickers = yf.Tickers(" ".join(symbols))
        for grp, tiles in TILES:
            for t in tiles:
                sym = t["symbol"]
                lbl = t["label"]
                try:
                    info = tickers.tickers[sym].info
                    price = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
                    prev = info.get("regularMarketPreviousClose") or price
                    if price and prev:
                        chg_pct = ((price - prev) / prev) * 100
                        data[lbl] = {"price": price, "chg_pct": chg_pct}
                except Exception:
                    pass
    except Exception:
        pass
    return data
