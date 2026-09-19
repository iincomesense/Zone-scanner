from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import json, os, datetime, traceback

app = FastAPI()
templates = Jinja2Templates(directory=".")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
        
        # टर्मिनल क्लोज चेक
        if (now.hour == 23 and now.minute >= 30) or (now.hour < 8):
            return HTMLResponse("<html><body style='background:#000;color:#444;text-align:center;padding-top:100px;'>TERMINAL CLOSED. REOPENS AT 8 AM IST.</body></html>")

        # डेटा लोड करना
        trades = []
        if os.path.exists("results.json"):
            with open("results.json", "r") as f:
                trades = json.load(f)

        # फाइल चेक (सिर्फ जांच के लिए)
        if not os.path.exists("index.html"):
            return HTMLResponse(f"<html><body><h3>Error: index.html not found!</h3><p>Files present: {os.listdir('.')}</p></body></html>")

        # टेम्पलेट रेंडर करना
        return templates.TemplateResponse("index.html", {"request": request, "trades": trades})

    except Exception as e:
        # अगर कोई भी एरर आए, तो उसे स्क्रीन पर प्रिंट करें
        error_details = traceback.format_exc()
        return HTMLResponse(f"<html><body style='background:#111;color:red;padding:20px;'><pre>CRITICAL ERROR:\n{error_details}</pre></body></html>")
