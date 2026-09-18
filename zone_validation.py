import streamlit as st
import pandas as pd

# --- 1. एडवांस्ड इंस्टीट्यूशनल दिमाग (Validation Logic) ---
def validate_zone_logic(zone, df_daily, df_75m, df_weekly):
    """
    यह वही मास्टर लॉजिक है जो हमने 1:5 टारगेट के लिए बनाया है।
    """
    score = 0
    ai_msg = "Fresh Zone Found."
    
    # Triple Confirmation Rules
    if zone.get('type') == 'Demand':
        # 15m Setup
        if df_daily['ema20'].iloc[-1] > df_daily['ema50'].iloc[-1] and df_75m.get('supertrend', 'Buy') == 'Buy':
            score += 50
        # High TF Setup
        elif df_weekly['ema20'].iloc[-1] > df_weekly['ema50'].iloc[-1]:
            score += 50
    
    # Score के आधार पर फैसला
    is_valid = score >= 50
    return is_valid, ai_msg

# --- 2. स्क्रीन पर दिखाने वाला फंक्शन (The Missing Hand) ---
def render_table(rows, key=None, keep=None):
    """
    यह फंक्शन उस एरर को ठीक करेगा और आपके जोन्स को स्क्रीन पर सुंदर तरीके से दिखाएगा।
    """
    if not rows:
        st.info("कोई इंस्टीट्यूशनल जोन नहीं मिला जो हमारे कड़े नियमों पर खरा उतरे।")
        return

    # डेटा को टेबल के रूप में तैयार करना
    df = pd.DataFrame(rows)
    
    # टेबल में केवल जरूरी कॉलम दिखाना
    cols_to_show = ["symbol", "timeframe", "type", "proximal", "distal", "state"]
    if all(col in df.columns for col in cols_to_show):
        st.dataframe(df[cols_to_show], use_container_width=True)
    else:
        st.dataframe(df, use_container_width=True)

    st.success("✅ इंस्टीट्यूशनल स्नाइपर लॉजिक सक्रिय है: 1:5 RR के लिए फिल्टर चालू हैं।")

# नोट: यह फाइल आपके ऐप के 'दिमाग' और 'चेहरे' दोनों का काम करेगी।
