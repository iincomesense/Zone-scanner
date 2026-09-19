import pandas as pd
import yfinance as yf
from tqdm import tqdm
import os

# आपके zone_core.py को सीधे इम्पोर्ट करना (बिना किसी बदलाव के)
# हम मान रहे हैं कि zone_core.py में 'find_zones' या सिमिलर फंक्शन है
try:
    import zone_core
except ImportError:
    print("❌ Error: zone_core.py नहीं मिली। कृपया फाइल अपलोड करें।")

class SniperScanner:
    def __init__(self, capital=25000, rr=4):
        self.capital = capital
        self.rr = rr

    def is_marubozu(self, candle):
        """अतिरिक्त वैलिडेशन नियम: 2 Marubozu Leg-out"""
        if candle is None: return False
        body = abs(candle['Close'] - candle['Open'])
        total_range = candle['High'] - candle['Low']
        # बॉडी 75% से ज्यादा और साइज 0.6% से बड़ा
        return (body > total_range * 0.75) and (body > candle['Open'] * 0.006)

    def process_stock(self, symbol):
        try:
            # 1. डेटा लाना (20 महीने का बैकटेस्ट सपोर्ट के लिए)
            df = yf.download(symbol, period="2y", interval="1d", progress=False)
            if df.empty: return None

            # 2. zone_core.py के मूल लॉजिक से ज़ोन ढूंढना (बिना किसी बदलाव के)
            # यहाँ हम zone_core के मुख्य फंक्शन को कॉल कर रहे हैं
            zones = zone_core.identify_zones(df) # मान लीजिए फंक्शन का नाम ये है
            
            if not zones: return None

            valid_trades = []
            for zone in zones:
                idx = zone['base_index'] # ज़ोन खत्म होने का इंडेक्स
                
                # चेक करें कि क्या पर्याप्त डेटा है आगे की कैंडल्स देखने के लिए
                if idx + 2 >= len(df): continue
                
                leg_out1 = df.iloc[idx + 1]
                leg_out2 = df.iloc[idx + 2]

                # 3. हमारा अतिरिक्त 'Explosive Validation' नियम
                if self.is_marubozu(leg_out1) and self.is_marubozu(leg_out2):
                    entry = round(leg_out1['Open'], 2)
                    sl = round(zone['low_price'] * 0.998, 2)
                    target = round(entry + (entry - sl) * self.rr, 2)
                    
                    valid_trades.append({
                        "Date": df.index[idx+1].strftime('%Y-%m-%d'),
                        "Symbol": symbol,
                        "Entry": entry,
                        "SL": sl,
                        "Target": target,
                        "Type": "Explosive Demand",
                        "Status": "READY 🎯"
                    })
            
            return valid_trades[-1] if valid_trades else None
        except Exception as e:
            return None

def run_automation():
    # zdata.py से स्टॉक्स की लिस्ट लाना
    from zdata import symbols # आपकी फाइल से
    
    scanner = SniperScanner(capital=25000, rr=4)
    results = []

    print(f"🚀 {len(symbols)} स्टॉक्स का गहन विश्लेषण शुरू...")
    for s in tqdm(symbols):
        res = scanner.process_stock(s)
        if res:
            results.append(res)

    # रिजल्ट को CSV में सेव करना (वेबसाइट इसी से डेटा लेगी)
    pd.DataFrame(results).to_csv("results.csv", index=False)
    print(f"✅ स्कैन पूरा। {len(results)} जैकपॉट मिले।")

if __name__ == "__main__":
    run_automation()
