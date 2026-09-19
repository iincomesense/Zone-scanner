import pandas as pd
import yfinance as yf

class SniperEngine:
    def __init__(self, rr_ratio=4):
        self.rr_ratio = rr_ratio

    def is_marubozu(self, candle):
        body = abs(candle['Close'] - candle['Open'])
        total_range = candle['High'] - candle['Low']
        return (body > total_range * 0.75) and (body > candle['Open'] * 0.005)

    def scan_explosive_zones(self, symbol):
        try:
            df = yf.download(symbol, period="1y", interval="1d", progress=False)
            if df.empty or len(df) < 50: return None
            
            # पिछले 5 दिनों में कोई नया ज़ोन बना है?
            for i in range(len(df)-5, len(df)-2):
                base = df.iloc[i]
                leg_out1 = df.iloc[i+1]
                leg_out2 = df.iloc[i+2]
                
                if self.is_marubozu(leg_out1) and self.is_marubozu(leg_out2):
                    entry = round(leg_out1['Open'], 2)
                    sl = round(base['Low'] * 0.998, 2)
                    target = round(entry + (entry - sl) * self.rr_ratio, 2)
                    
                    return {
                        "Symbol": symbol,
                        "Date": df.index[i+1].strftime('%Y-%m-%d'),
                        "Entry": entry,
                        "SL": sl,
                        "Target": target,
                        "RR": f"1:{self.rr_ratio}",
                        "Status": "READY 🎯"
                    }
            return None
        except: return None
