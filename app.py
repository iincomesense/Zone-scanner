from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import json, os, datetime

app = FastAPI()
# टेम्पलेट्स के लिए करंट डायरेक्टरी सेट करना
templates = Jinja2Templates(directory=".")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # भारतीय समय (IST) सेट करना
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    
    # रात 11:30 PM से सुबह 8 AM तक 'Closed' मैसेज
    if (now.hour == 23 and now.minute >= 30) or (now.hour < 8):
        return HTMLResponse("<html><body style='background:#000;color:#555;text-align:center;padding-top:100px;font-family:monospace;'>TERMINAL CLOSED. REOPENS AT 8 AM IST.</body></html>")
    
    trades_data = []
    if os.path.exists("results.json"):
        try:
            with open("results.json", "r") as f:
                data = f.read()
                if data:
                    trades_data = json.loads(data)
        except Exception as e:
            print(f"Error reading results: {e}")
    
    # कॉन्टेक्स्ट को कीवर्ड (context=) के साथ भेजना ज्यादा सुरक्षित है
    return templates.TemplateResponse(
        name="index.html", 
        context={"request": request, "trades": trades_data}
    )
