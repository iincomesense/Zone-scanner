import pandas as pd
import yfinance as yf
from tqdm import tqdm
import zone_core  # आपका मूल zone_core.py इम्पोर्ट कर रहा है
import os

# --- 2 Marubozu Validation नियम ---
def is_marubozu(df, idx):
    if idx >= len(df): return False
    candle = df.iloc[idx]
    body = abs(candle['close'] - candle['open'])
    total_range = candle['high'] - candle['low']
    # नियम: बॉडी 75% से ज्यादा और भाव में कम से कम 0.6% की बढ़त
    return (total_range > 0) and (body > total_range * 0.75) and (body > candle['open'] * 0.006)

def run_automation():
    # zdata.py से स्टॉक्स की लिस्ट लाना
    try:
        from zdata import symbols
    except ImportError:
        # अगर zdata.py नहीं है, तो उदाहरण के लिए कुछ स्टॉक्स
        symbols = ["RELIANCE.NS", "HDFCBANK.NS", "SBIN.NS", "TCS.NS", "INFY.NS"]

    all_verified_trades = []
    print(f"🚀 {len(symbols)} स्टॉक्स का विश्लेषण शुरू (Explosive Mode)...")

    for symbol in tqdm(symbols):
        try:
            # 1. डेटा लाना (कॉलम नाम स्माल केस में होने चाहिए zone_core के लिए)
            temp_df = yf.download(symbol, period="2y", interval="1d", progress=False)
            if temp_df.empty: continue
            
            df = temp_df.rename(columns={
                'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'
            })

            # 2. zone_core.py के मूल लॉजिक से ज़ोन ढूंढना (0% बदलाव)
            found_zones = zone_core.scan_zones(df, accountCapital=25000)
            
            if not found_zones: continue

            # 3. '2 Marubozu' वैलिडेशन फिल्टर (अतिरिक्त नियम)
            for zone in found_zones:
                idx = zone.createdBarIndex # Leg-out 1 का इंडेक्स
                
                # चेक करें कि Leg-out 1 और Leg-out 2 दोनों Marubozu हैं या नहीं
                if is_marubozu(df, idx) and is_marubozu(df, idx + 1):
                    # केवल वही ज़ोन लें जो अभी भी 'Fresh' या 'Tested' हैं (टूटे नहीं हैं)
                    if zone.state in ["Fresh", "Tested"]:
                        all_verified_trades.append({
                            "Date": zone.timestamp.strftime('%Y-%m-%d') if zone.timestamp else "N/A",
                            "Symbol": symbol,
                            "Entry": round(zone.proxVal, 2),
                            "SL": round(zone.slVal, 2),
                            "Target": round(zone.tpVal, 2),
                            "Pattern": zone.patternType,
                            "Status": "VALIDATED ✅"
                        })
        except Exception as e:
            continue

    # रिजल्ट को CSV में सेव करना (वेबसाइट यहीं से डेटा उठाएगी)
    res_df = pd.DataFrame(all_verified_trades)
    if not res_df.empty:
        res_df.to_csv("results.csv", index=False)
        print(f"✅ स्कैन पूरा। {len(all_verified_trades)} जैकपॉट मिले।")
    else:
        print("❌ कोई भी ज़ोन Explosive नियमों पर खरा नहीं उतरा।")

if __name__ == "__main__":
    run_automation()
