from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import pandas as pd
import os

app = FastAPI()

HTML_TEMPLATE = """
<html>
<head>
    <title>Sniper Zone Dashboard</title>
    <style>
        body { font-family: sans-serif; background: #121212; color: white; padding: 20px; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #333; padding: 12px; text-align: left; }
        th { background: #1f1f1f; color: #00ff88; }
        tr:nth-child(even) { background: #1a1a1a; }
        .status { color: #00ff88; font-weight: bold; }
    </style>
</head>
<body>
    <h1>🎯 Sniper Demand Zones (Explosive Mode)</h1>
    <p>Capital: ₹25,000 | Strategy: 2 Marubozu Validation</p>
    <table>
        <tr>
            <th>Date</th><th>Symbol</th><th>Entry (Limit)</th><th>Stop Loss</th><th>Target (1:4)</th><th>Status</th>
        </tr>
        {% for trade in trades %}
        <tr>
            <td>{{ trade.Date }}</td><td>{{ trade.Symbol }}</td><td>{{ trade.Entry }}</td>
            <td>{{ trade.SL }}</td><td>{{ trade.Target }}</td><td class="status">{{ trade.Status }}</td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
"""

from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory=".")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if os.path.exists("results.csv"):
        df = pd.read_csv("results.csv")
        trades = df.to_dict(orient="records")
    else:
        trades = []
    
    # Simple direct HTML response for speed
    from jinja2 import Template
    return Template(HTML_TEMPLATE).render(trades=trades)
