import os, json, yfinance as yf
import pandas as pd
from zone_core import scan_zones # आपके मूल इंजन से

# --- सुरक्षा के लिए एन्वायरमेंट वेरिएबल्स ---
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")
CAPITAL = 25000
RISK_PER_TRADE = 500 # ₹25k का 2%

def get_tv_link(symbol):
    clean_sym = symbol.replace(".NS", "")
    return f"https://www.tradingview.com/chart/?symbol=NSE:{clean_sym}"

def run_institutional_scan():
    try:
        from zdata import symbols
    except: symbols = ["RELIANCE.NS", "SBIN.NS"]

    valid_trades = []
    for sym in symbols:
        df = yf.download(sym, period="1mo", interval="1d", progress=False)
        if df.empty: continue
        
        # 1. zone_core.py से स्कैन (बिना बदलाव के)
        zones = scan_zones(df, accountCapital=CAPITAL)
        if not zones: continue

        for z in zones:
            # 2. ±10% Range फिल्टर (आज के क्लोज से)
            current_price = df['Close'].iloc[-1]
            if not (current_price * 0.9 <= z.proxVal <= current_price * 1.1): continue

            # 3. 2-Marubozu Validation (Explosive Check)
            # यहाँ आपका मार्बोज़ु लॉजिक चलेगा...
            
            # 4. Position Sizing (Quantity)
            risk = abs(z.proxVal - z.slVal)
            qty = int(RISK_PER_TRADE / risk) if risk > 0 else 0

            valid_trades.append({
                "symbol": sym,
                "link": get_tv_link(sym),
                "entry": round(z.proxVal, 2),
                "sl": round(z.slVal, 2),
                "tp": round(z.tpVal, 2),
                "qty": qty,
                "status": z.state
            })

    with open("results.json", "w") as f:
        json.dump(valid_trades, f)

if __name__ == "__main__":
    run_institutional_scan()
