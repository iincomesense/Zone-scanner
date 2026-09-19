from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import json, os, datetime

app = FastAPI()

# पक्का करें कि templates फोल्डर या करंट डायरेक्टरी सही है
templates = Jinja2Templates(directory=".")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    
    # समय चेक (11:30 PM to 8 AM)
    if (now.hour == 23 and now.minute >= 30) or (now.hour < 8):
        return HTMLResponse("<html><body style='background:#000;color:#444;text-align:center;padding-top:100px;font-family:monospace;'>TERMINAL CLOSED. REOPENS AT 8 AM.</body></html>")
    
    trades = []
    # चेक करें कि क्या फाइल मौजूद है
    if os.path.exists("results.json"):
        try:
            with open("results.json", "r") as f:
                trades = json.load(f)
        except Exception as e:
            print(f"JSON Error: {e}")
            trades = []

    # अगर index.html फाइल नहीं मिली तो सुरक्षा के लिए चेक
    if not os.path.exists("index.html"):
        return HTMLResponse(f"<html><body><h3>Error: index.html not found in root directory.</h3><p>Current files: {os.listdir('.')}</p></body></html>")

    try:
        return templates.TemplateResponse("index.html", {"request": request, "trades": trades})
    except Exception as e:
        return HTMLResponse(f"<html><body><h3>Template Error</h3><p>{str(e)}</p></body></html>")
