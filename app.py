from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from jinja2 import Template
import pandas as pd
import os

app = FastAPI()

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Sniper Zone Dashboard</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0e1117; color: white; padding: 30px; }
        .container { max-width: 1000px; margin: auto; }
        h1 { color: #00ff88; border-bottom: 2px solid #333; padding-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; box-shadow: 0 4px 8px rgba(0,0,0,0.5); }
        th, td { border: 1px solid #2d2d2d; padding: 15px; text-align: left; }
        th { background: #1f2937; color: #00ff88; font-weight: 600; }
        tr:hover { background: #1a202c; }
        .status-badge { background: #059669; color: white; padding: 4px 10px; border-radius: 12px; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 Sniper Demand Zones (Explosive Mode)</h1>
        <p>Strategy: <b>zone_core.py</b> + <b>2 Marubozu Validation</b></p>
        <p>Capital: ₹25,000 | System Refresh: Nightly (9:30 PM IST)</p>
        <table>
            <tr>
                <th>Date</th><th>Stock</th><th>Entry (Limit)</th><th>SL</th><th>Target (1:5)</th><th>Status</th>
            </tr>
            {% for trade in trades %}
            <tr>
                <td>{{ trade.Date }}</td><td><b>{{ trade.Symbol }}</b></td>
                <td>{{ trade.Entry }}</td><td>{{ trade.SL }}</td><td>{{ trade.Target }}</td>
                <td><span class="status-badge">{{ trade.Status }}</span></td>
            </tr>
            {% endfor %}
        </table>
        {% if not trades %}
        <p style="text-align:center; margin-top:50px; color:#666;">अभी कोई सक्रिय 'Explosive' ज़ोन नहीं मिला। कृपया कल चेक करें।</p>
        {% endif %}
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    trades = []
    if os.path.exists("results.csv"):
        df = pd.read_csv("results.csv")
        trades = df.to_dict(orient="records")
    
    return Template(HTML_PAGE).render(trades=trades)
