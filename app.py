from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import json, os, datetime

app = FastAPI()
templates = Jinja2Templates(directory=".")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # समय चेक (IST)
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    if (now.hour == 23 and now.minute >= 30) or (now.hour < 8):
        return HTMLResponse("<body style='background:#000;color:#444;text-align:center;padding-top:100px;font-family:monospace;'>TERMINAL CLOSED. REOPENS AT 8 AM IST.</body>")
    
    trades_data = []
    if os.path.exists("results.json"):
        try:
            with open("results.json", "r") as f:
                trades_data = json.load(f)
        except: trades_data = []

    # सबसे सुरक्षित तरीका (Keyword Arguments के साथ)
    return templates.TemplateResponse(
        name="index.html", 
        context={"request": request, "trades": trades_data}
    )
