from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import json, os, datetime

app = FastAPI()
templates = Jinja2Templates(directory=".")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # भारतीय समय (IST) के अनुसार वर्तमान समय निकालें
    # UTC + 5:30 = IST
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    
    # रात 11:30 PM (23:30) से सुबह 8:00 AM तक टर्मिनल को 'CLOSED' दिखाना
    is_closed = False
    if now.hour >= 23 and now.minute >= 30:
        is_closed = True
    if now.hour < 8:
        is_closed = True

    if is_closed:
        return HTMLResponse("""
        <html>
            <body style='background:#000; color:#444; font-family:monospace; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;'>
                <div style='text-align:center;'>
                    <div style='font-size:24px; font-weight:bold; margin-bottom:10px;'>TERMINAL CLOSED</div>
                    <div style='font-size:12px; letter-spacing:2px;'>REOPENS AT 08:00 AM IST</div>
                </div>
            </body>
        </html>
        """)
    
    # ट्रेड्स डेटा लोड करना
    trades = []
    if os.path.exists("results.json"):
        try:
            with open("results.json", "r") as f:
                trades = json.load(f)
        except:
            trades = []
    
    # index.html के साथ डेटा भेजना
    return templates.TemplateResponse("index.html", {"request": request, "trades": trades})
