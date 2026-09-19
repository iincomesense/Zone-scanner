import os, json, smtplib, yfinance as yf
import pandas as pd
from email.mime.text import MIMEText
from zone_core import scan_zones

# --- GitHub Secrets से सुरक्षा ---
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")
CAPITAL = 25000
RISK_PER_TRADE = 500

def send_alert(symbol, price):
    if not GMAIL_USER or not GMAIL_PASS: return
    msg = MIMEText(f"🎯 SNIPER ALERT: {symbol} touched Proximal Line at {price}. Check Dhan App!")
    msg['Subject'] = f"🚀 Sniper Touch: {symbol}"
    msg['From'], msg['To'] = GMAIL_USER, GMAIL_USER
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.send_message(msg)
    except: pass

def run_scanner():
    try: from zdata import symbols
    except: symbols = ["RELIANCE.NS", "SBIN.NS", "HDFCBANK.NS"]
    
    results = []
    for sym in symbols:
        df = yf.download(sym, period="1mo", interval="1d", progress=False)
        if df.empty: continue
        
        zones = scan_zones(df, accountCapital=CAPITAL)
        if not zones: continue

        curr_price = df['close'].iloc[-1]
        for z in zones:
            # ±10% Range Filter
            if not (curr_price * 0.9 <= z.proxVal <= current_price * 1.1): continue
            
            # Position Sizing
            risk = abs(z.proxVal - z.slVal)
            qty = int(RISK_PER_TRADE / risk) if risk > 0 else 0
            
            results.append({
                "symbol": sym,
                "link": f"https://www.tradingview.com/chart/?symbol=NSE:{sym.replace('.NS','')}",
                "entry": round(z.proxVal, 2),
                "sl": round(z.slVal, 2),
                "tp": round(z.tpVal, 2),
                "qty": qty,
                "status": z.state
            })
    
    with open("results.json", "w") as f:
        json.dump(results, f)

if __name__ == "__main__":
    run_scanner()
