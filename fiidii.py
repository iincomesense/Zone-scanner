"""
fiidii.py — FII/DII daily flows (today's live + recent ~10 days history).

Two complementary sources:
  * niftytrader.in `__NEXT_DATA__` -> `series` (90 daily rows) gives the last N
    days with fii_net_value / dii_net_value / nifty close.  Reliable, keyless.
  * nseindia fiidiiTradeReact -> today's buy/sell/value in real time (in Rs cr).
    Shown as the "Today" card; the history fills the last few days.

Returns a list of day-records, newest first:
  {date, fii_net, dii_net, nifty, change, alt (bool)}
"""
from __future__ import annotations

import re
import json
import datetime
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121 Safari/537.36"
NIFTYTRADER_URL = "https://www.niftytrader.in/fii-dii-data"


def _niftytrader_series():
    try:
        r = requests.get(NIFTYTRADER_URL, timeout=14, headers={"User-Agent": UA})
        if r.status_code != 200:
            return []
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        if not m:
            return []
        pp = json.loads(m.group(1))["props"]["pageProps"]
        return pp.get("series", []) or []
    except Exception:
        return []


def _nse_today():
    try:
        s = requests.Session()
        s.headers.update({"User-Agent": UA,
                          "Accept": "application/json, text/plain, */*",
                          "Referer": "https://www.nseindia.com/",
                          "Origin": "https://www.nseindia.com"})
        s.get("https://www.nseindia.com/", timeout=8)
        r = s.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=10)
        if r.status_code != 200:
            return {}
        out = {}
        for row in r.json():
            cat = row.get("category", "")
            if cat.startswith("FII"):
                out["fii"] = (float(row.get("buyValue") or 0), float(row.get("sellValue") or 0))
            elif cat.startswith("DII"):
                out["dii"] = (float(row.get("buyValue") or 0), float(row.get("sellValue") or 0))
            out["date"] = row.get("date")
        return out
    except Exception:
        return {}


def fetch(days=6):
    """Return newest-first daily FII/DII records for the last `days` days."""
    series = _niftytrader_series()
    today = _nse_today()
    recs = []
    for row in sorted(series, key=lambda x: x.get("created_at", "")):
        try:
            d = datetime.date.fromisoformat(row["created_at"][:10])
        except Exception:
            continue
        recs.append({
            "date": d,
            "fii_net": row.get("fii_net_value"),
            "dii_net": row.get("dii_net_value"),
            "nifty": row.get("last_trade_price"),
            "chg": row.get("change_value"),
            "alt": False,   # from niftytrader history
        })
    # Overlay real-time today's buy/sell from NSE if present and matches latest date
    if today and recs:
        latest = recs[-1]
        today_d = today.get("date")
        try:
            td = datetime.datetime.strptime(today_d, "%d-%b-%Y").date()
        except Exception:
            td = latest["date"]
        if td == latest["date"]:
            if "fii" in today:
                latest["fii_buy"], latest["fii_sell"] = today["fii"]
            if "dii" in today:
                latest["dii_buy"], latest["dii_sell"] = today["dii"]
            latest["alt"] = True  # has real-time buy/sell detail
            # recompute net to match exchange reported net
            if "fii" in today:
                latest["fii_net"] = round(today["fii"][0] - today["fii"][1], 2)
            if "dii" in today:
                latest["dii_net"] = round(today["dii"][0] - today["dii"][1], 2)
    recs = [r for r in recs if r["date"] is not None]
    recs.sort(key=lambda x: x["date"], reverse=True)
    return recs[:days]


def monthly():
    """Return month-level summary rows (niftytrader tableData), newest first."""
    try:
        r = requests.get(NIFTYTRADER_URL, timeout=14, headers={"User-Agent": UA})
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        pp = json.loads(m.group(1))["props"]["pageProps"]
        rows = pp.get("tableData", {}).get("fii_dii_summary_data", [])
        rows.sort(key=lambda x: x.get("month", ""), reverse=True)
        return rows[:9]
    except Exception:
        return []


if __name__ == "__main__":
    print("=== last 6 daily ===")
    for rec in fetch(6):
        print(rec)
    print("\n=== monthly ===")
    for m in monthly():
        print(m)
