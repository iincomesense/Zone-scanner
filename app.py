from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import json, os, datetime, traceback

app = FastAPI()
# templates सेटअप
templates = Jinja2Templates(directory=".")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        # 1. समय गणना (IST)
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
        
        # 2. रात 11:30 PM से सुबह 8 AM तक क्लोज्ड मैसेज
        if (now.hour == 23 and now.minute >= 30) or (now.hour < 8):
            return HTMLResponse("<body style='background:#000;color:#555;text-align:center;padding-top:100px;font-family:monospace;'>TERMINAL CLOSED. REOPENS AT 8 AM IST.</body>")
        
        # 3. डेटा लोड करना
        trades_data = []
        if os.path.exists("results.json"):
            with open("results.json", "r") as f:
                content = f.read().strip()
                if content:
                    trades_data = json.loads(content)

        # 4. पक्का करें कि index.html मौजूद है
        if not os.path.exists("index.html"):
             return HTMLResponse("<h3>Error: index.html not found in root folder!</h3>")

        # 5. फिक्स: 'context' को सही तरीके से भेजना (यह एरर को खत्म कर देगा)
        # यहाँ हम सीधे डिक्शनरी पास कर रहे हैं जैसा कि आधुनिक FastAPI मांगता है
        return templates.TemplateResponse(
            "index.html", 
            {"request": request, "trades": trades_data}
        )

    except Exception as e:
        # अगर फिर भी कोई दिक्कत आए, तो यह सादा HTML टेबल दिखा देगा (Fallback Mode)
        error_msg = str(e)
        rows = "".join([f"<tr><td>{t.get('symbol','-')}</td><td>{t.get('entry','-')}</td></tr>" for t in trades_data])
        return HTMLResponse(f"""
            <body style='background:#111;color:#eee;font-family:sans-serif;padding:20px;'>
                <h3>System Running in Recovery Mode</h3>
                <p style='color:orange;'>Template Error: {error_msg}</p>
                <table border='1' style='width:100%; border-collapse:collapse;'>
                    <tr style='background:#222;'><th>Symbol</th><th>Entry</th></tr>
                    {rows}
                </table>
                <p style='font-size:10px;color:#555;margin-top:20px;'>Please check if index.html has any syntax errors.</p>
            </body>
        """)
