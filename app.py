# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import sys
import datetime
import requests
from urllib.parse import quote
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

st.set_page_config(page_title="MarketHub · Zone Scanner", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")

if 'last_news_title' not in st.session_state:
    st.session_state.last_news_title = ""

st.markdown("""
<style>
:root{--bg:#0b1220; --line:#22304a; --txt:#e6edf7; --muted:#8ba1c0; --up:#1ecb6b; --down:#ff4b5c; --accent2:#22d3ee; --accent:#4f8cff;}
.stApp{background-color:var(--bg); color:var(--txt);}
[data-testid="stSidebar"]{background-color:#0d1524;}
[data-testid="stSidebar"] *{color:var(--txt);}
[data-testid="stHeader"]{background:rgba(11,18,32,.35);}
[data-baseweb="select"] *{background-color:#121a2b; color:#e6edf7;}

/* Tabs Styling for Mobile/Tablet */
.stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: #0d1524; padding: 10px; border-radius: 12px; }
.stTabs [data-baseweb="tab"] { background-color: #162238; border-radius: 8px; padding: 10px 16px; color: #8ba1c0; font-weight: 600; }
.stTabs [aria-selected="true"] { background-color: #4f8cff !important; color: #ffffff !important; }

/* Desktop Tables */
.board-table{width:100%; border-collapse:collapse; font-size:10.5px;}
.board-table th{text-align:left; color:var(--muted); font-size:9.5px; text-transform:uppercase; padding:3px 6px; border-bottom:1px solid var(--line); white-space:nowrap;}
.board-table td{padding:2.5px 6px; border-bottom:1px solid #161f33; color:#d9e5f6; font-variant-numeric:tabular-nums; white-space:nowrap;}
.board-table a.sym{font-weight:700; color:#eaf1fb; text-decoration:none;}
.board-table a.sym:hover{color:var(--accent2); text-decoration:underline;}
.board-table .grp td{background:#0e1626; color:var(--accent2); font-size:9px; font-weight:800; text-transform:uppercase; padding:3px 6px;}

.phead{display:flex; align-items:baseline; justify-content:space-between; flex-wrap:wrap;}
.phead .t{font-size:15px; font-weight:800; color:#eaf1fb;}
.phead .s{font-size:10.5px; color:var(--muted);}
.up{color:var(--up);} .dn{color:var(--down);} .flat{color:var(--muted);}

.sumbar{display:flex; gap:8px; flex-wrap:wrap; background:#0e1626; border:1px solid var(--line); border-radius:12px; padding:8px 12px; margin:8px 0; font-size:12.5px;}
.sumbar .it{color:#cfe0ff;} .sumbar b{color:#eaf1fb;} .sumbar .lbl{color:var(--muted); font-size:10.5px;}

.zwrap{overflow:auto; max-height:600px; border:1px solid var(--line); border-radius:12px; background:#0e1626; scrollbar-width:thin;}
.zhin{width:100%; border-collapse:collapse; font-size:12px; min-width:800px;}
.zhin thead th{position:sticky; top:0; z-index:3; text-align:left; color:var(--muted); font-size:10.5px; text-transform:uppercase; padding:7px 8px; border-bottom:1px solid var(--line); background:#0c1422; white-space:nowrap;}
.zhin td{padding:6px 8px; border-bottom:1px solid #18233a; color:#d9e5f6; white-space:nowrap;}
.zhin tr:hover{background:#131d31;}
.zhin a.sym{color:#eaf1fb; font-weight:700; text-decoration:none;}
.zhin a.sym:hover{color:var(--accent2); text-decoration:underline;}
.dot.dem{color:var(--up);} .dot.sup{color:var(--down);}
.zhin .hq{color:#f5c542;}
.st-fresh{color:var(--up);} .st-tested{color:var(--accent2);} .st-broken{color:var(--muted);}
.zscore{font-size:11px; padding:1px 7px; border-radius:12px; border:1px solid var(--line);}
.zscore.hi{color:var(--up); border-color:rgba(30,203,107,.4);}
.zscore.md{color:var(--accent2); border-color:rgba(34,211,238,.4);}
.zscore.lo{color:var(--muted);}

/* Mobile UI Cards Conversion */
@media (max-width: 768px) {
    .zhin thead { display: none; }
    .zhin, .zhin tbody, .zhin tr, .zhin td { display: block; width: 100%; min-width:100%; }
    .zhin tr { background: #0e1626; margin-bottom: 12px; border-radius: 12px; border: 1px solid #22304a; padding: 10px; }
    .zhin td { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px dashed #18233a; padding: 8px 4px; text-align:right;}
    .zhin td::before { content: attr(data-label); color: #8ba1c0; font-weight: 600; text-transform:uppercase; font-size:10px; text-align:left;}
    .zhin td:last-child { border-bottom: 0; }
}

.fdbx{background:#0e1626; border:1px solid var(--line); border-radius:10px; padding:8px 10px;}
.fdbx .lab{font-size:10px; color:var(--muted); text-transform:uppercase;}
.fdbx .val{font-size:19px; font-weight:800;}
.fdrow{display:flex; gap:12px; flex-wrap:wrap;} .fdrow .fdbx{flex:1 1 120px;}

.news-item{display:flex; gap:9px; padding:7px 4px; border-bottom:1px solid #18233a;}
.news-time{color:var(--muted); font-size:11px; width:44px; flex:0 0 44px;}
.news-title{color:#dbeeef; font-size:13px; font-weight:600; text-decoration:none;}
.news-src{color:var(--muted); font-size:10px;}
.livebox{display:flex; gap:10px; align-items:center; background:linear-gradient(90deg,#12233f,#0e1626); border:1px solid rgba(255,75,92,.35); border-radius:12px; padding:8px 11px; margin:4px 0 10px;}
.pulse{display:inline-block; width:9px; height:9px; border-radius:50%; background:#ff4b5c; box-shadow:0 0 0 0 rgba(255,75,92,.7); animation:pulse 1.6s infinite;}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(255,75,92,.7);} 70%{box-shadow:0 0 0 8px rgba(255,75,92,0);} 100%{box-shadow:0 0 0 0 rgba(255,75,92,0);}}
.chip{font-size:11px; background:#152036; border:1px solid var(--line); color:#cfe0ff; border-radius:20px; padding:2px 9px; display:inline-block;}
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600, show_spinner=False)
def _hi(text):
    if not text or not str(text).strip(): return str(text)
    try:
        r = requests.get("https://translate.googleapis.com/translate_a/single", params={"client": "gtx", "sl": "auto", "tl": "hi", "dt": "t", "q": str(text)}, timeout=5)
        if r.status_code == 200: return "".join(x[0] for x in r.json()[0]).strip()
    except Exception: pass
    return str(text)

LIVE_TFS = ["10m", "15m", "30m", "75m", "1h", "2h", "4h"]
STABLE_TFS = ["6h", "8h", "1D", "1W", "1M"]
TF_LABEL = {"10m": "10 Min", "15m": "15 Min", "1h": "1 Hour", "2h": "2 Hours", "4h": "4 Hours", "1D": "Daily", "1W": "Weekly", "1M": "Monthly"}
def _tf_hi(tf): return TF_LABEL.get(str(tf), str(tf))
def _score_cls(sc): return "hi" if sc >= 90 else ("md" if sc >= 60 else "lo")

@st.cache_data(ttl=30, show_spinner=False)
def load_market():
    try: import marketdata as md; return md.fetch_all()
    except ImportError: return {}

@st.cache_data(ttl=30, show_spinner=False)
def load_sectors():
    try: import sectors as sc; return sc.fetch_sectors()
    except ImportError: return []

@st.cache_data(ttl=120, show_spinner=False)
def load_news():
    try: import news as n; return n.fetch_latest(15)
    except ImportError: return []

@st.cache_data(ttl=300, show_spinner=False)
def load_events():
    try: import events as e; return e.fetch_events(10)
    except ImportError: return []

@st.cache_data(ttl=90, show_spinner=False)
def load_fiidii():
    try: import fiidii as f; return f.fetch(6)
    except ImportError: return []

@st.cache_data(ttl=30, show_spinner=False)
def load_scan(symbol, timeframe, min_score, strict, lookback, recommended):
    try: import zscan; return zscan.scan(symbol, timeframe, min_score=min_score, strict=strict, lookback_months=lookback, recommended=recommended)
    except ImportError: return [], None, None

def _day_key(): return datetime.datetime.now().strftime("%Y-%m-%d")

@st.cache_data(ttl=120, show_spinner=False)
def load_universe_live(tf_tuple, min_score, recommended, strict, eod_filter, symbols_tuple):
    try: import zscan; return zscan.scan_universe_zones(timeframes=tf_tuple, min_score=min_score, recommended=recommended, strict=strict, active_only=False, eod_filter=eod_filter, symbols=list(symbols_tuple) if symbols_tuple else None)
    except ImportError: return []

@st.cache_data(ttl=86400, show_spinner=False)
def load_universe_stable(tf_tuple, min_score, recommended, strict, eod_filter, symbols_tuple, day_key):
    try: import zscan; return zscan.scan_universe_zones(timeframes=tf_tuple, min_score=min_score, recommended=recommended, strict=strict, active_only=False, eod_filter=eod_filter, symbols=list(symbols_tuple) if symbols_tuple else None)
    except ImportError: return []

def _chg_html(c):
    if c is None: return '<span class="flat">—</span>'
    cls = "up" if c > 0 else ("dn" if c < 0 else "flat")
    return f'<span class="{cls}">{"+" if c > 0 else ""}{c:.2f}%</span>'

def _tv_chart_url(tv_sym, interval="1D"): return f'https://www.tradingview.com/chart/?symbol={quote(str(tv_sym))}&interval={interval}'

def render_board():
    data = load_market()
    if not data: return
    try:
        import marketdata as md
        html = ['<table class="board-table"><thead><tr><th>Symbol</th><th>Last</th><th>Chg%</th><th>Chart</th></tr></thead><tbody>']
        for grp, tiles in md.TILES:
            html.append(f'<tr class="grp"><td colspan="4">{grp.upper()}</td></tr>')
            for t in tiles:
                q = data.get(t["label"], {})
                px = f"{q['price']:,.2f}" if q.get("price") is not None else "—"
                tv_sym = md.tv_chart_symbol(t["label"]) if hasattr(md, "tv_chart_symbol") else t["label"]
                _tv_url = _tv_chart_url(tv_sym)
                html.append(f'<tr><td><a class="sym" href="{_tv_url}" target="_blank">📈 {t["label"]}</a></td><td>{px}</td><td>{_chg_html(q.get("chg_pct"))}</td><td class="tv"><a href="{_tv_url}" target="_blank">➜</a></td></tr>')
        html.append('</tbody></table>')
        st.markdown("".join(html), unsafe_allow_html=True)
    except Exception: pass

def render_sectors():
    sec = load_sectors()
    if not sec: return
    html = ['<table class="board-table"><thead><tr><th>Index</th><th>Last</th><th>Chg%</th><th>Chart</th></tr></thead><tbody>']
    for s in sec:
        cls, sign = ("up", "+") if s["chg_pct"] >= 0 else ("dn", "−")
        _tv_url = _tv_chart_url(s.get("label"))
        html.append(f'<tr><td><a class="sym" href="{_tv_url}" target="_blank">📈 {s["label"]}</a></td><td>{s["price"]:,.1f}</td><td class="{cls}">{sign}{s["chg_pct"]:.2f}%</td><td class="tv"><a href="{_tv_url}" target="_blank">➜</a></td></tr>')
    html.append('</tbody></table>')
    st.markdown("".join(html), unsafe_allow_html=True)

def _fmt2(v): return "—" if v is None else f"{float(v):,.2f}"

def _status_badge(es):
    es = es or ""
    if es == "Waiting": return '<span style="color:#4f8cff;font-weight:700;">⏳ Waiting</span>'
    if es == "Triggered": return '<span style="color:#22c55e;font-weight:700;">✅ Triggered</span>'
    if es.startswith("Failed"): return f'<span style="color:#f87171;">✖ {es.replace("Failed-", "")}</span>'
    return es or "—"

def render_zone_table(rows, scan_time=None):
    if not rows: return st.info("No valid zones found.")
    now = (scan_time or datetime.datetime.now()).strftime("%d-%b %H:%M")
    st.markdown(f'<div class="sumbar"><span class="it"><span class="lbl">Scan ⟳</span> <b>{now}</b></span><span class="sep">|</span><span class="it"><b>{len(rows)}</b> <span class="lbl">Zones</span></span><span class="sep">|</span><span class="it"><b>{sum(1 for r in rows if r["state"]=="Fresh")}</b> <span class="lbl">Fresh</span></span><span class="sep">|</span><span class="it"><span style="color:#f5c542;">⭐ {sum(1 for r in rows if r["hq"])}</span> <span class="lbl">HQ</span></span></div>', unsafe_allow_html=True)
    
    html = ['<div class="zwrap"><table class="zhin"><thead><tr><th>Asset</th><th>TF</th><th>Direction</th><th>Pattern</th><th>State</th><th>HQ</th><th>Score</th><th>Entry</th><th>Distal</th><th>SL</th><th>Risk %</th><th>Status</th></tr></thead><tbody>']
    
    for r in rows:
        disp = r["symbol"].replace(".NS", "")
        dot = '<span class="dot dem">●</span>' if r["dir"] == "Demand" else '<span class="dot sup">●</span>'
        
        tv_url = r.get("tv")
        if not tv_url:
            try: import tv; tv_url = tv.chart_url(r["symbol"], r["tf"])
            except ImportError: tv_url = f"https://www.tradingview.com/chart/?symbol=NSE:{disp}"
                
        symlink = f'<a class="sym" href="{tv_url}" target="_blank">📈 {disp}</a>'
        hq = '<span class="hq">⭐</span>' if r.get("hq") else ""
        
        # Mobile CSS requires data-label to show headers on cards
        html.append(f'<tr>'
                    f'<td data-label="Asset">{symlink}</td>'
                    f'<td data-label="TF">{_tf_hi(r["tf"])}</td>'
                    f'<td data-label="Direction">{dot} {r["dir"]}</td>'
                    f'<td data-label="Pattern">{r["pattern"]}</td>'
                    f'<td data-label="State" class="st-{r["state"].lower()}">{r["state"]}</td>'
                    f'<td data-label="HQ">{hq}</td>'
                    f'<td data-label="Score"><span class="zscore {_score_cls(r["score"])}">{r["score"]}</span></td>'
                    f'<td data-label="Entry">{r["entry"]:,.2f}</td>'
                    f'<td data-label="Distal">{_fmt2(r.get("distal"))}</td>'
                    f'<td data-label="SL">{r["sl"]:,.2f}</td>'
                    f'<td data-label="Risk %">{_fmt2(r.get("risk_pct"))}</td>'
                    f'<td data-label="Status">{_status_badge(r.get("entry_status"))}</td>'
                    f'</tr>')
    
    html.append('</tbody></table></div>')
    st.markdown("".join(html), unsafe_allow_html=True)

# ----------------- SIDEBAR -----------------
st.sidebar.markdown("## ⚙️ Settings")
scan_all = st.sidebar.toggle("All NSE stocks", value=True)

if scan_all:
    try:
        import zdata
        _u_syms, mcap, _ = zdata.build_universe()
    except ImportError: 
        _u_syms = ["RELIANCE.NS", "HDFCBANK.NS", "TCS.NS"]
        
    sel_universe = st.sidebar.multiselect("Stocks", _u_syms, default=list(_u_syms)) or list(_u_syms)
    univ_tfs = st.sidebar.multiselect("Timeframes", ["10m", "15m", "1h", "2h", "4h", "1D", "1W", "1M"], default=["15m", "1h", "4h", "1D"]) or ["15m", "1h", "4h", "1D"]
    live_sel = [t for t in univ_tfs if t in LIVE_TFS]
    stable_sel = [t for t in univ_tfs if t in STABLE_TFS]
    eod_filter = st.sidebar.toggle("EOD band filter", value=True)
    symbol, timeframe = "RELIANCE.NS", "4h"
else:
    sel_universe, univ_tfs, live_sel, stable_sel, eod_filter = None, [], [], [], True
    symbol = st.sidebar.text_input("Symbol", value="RELIANCE.NS")
    timeframe = st.sidebar.selectbox("Timeframe", ["15m", "1h", "4h", "1D"], index=2)

min_score = st.sidebar.slider("Min score", 20, 100, 45, step=5)
active_only = st.sidebar.toggle("Active zones only", value=True)
lookback = st.sidebar.selectbox("Lookback", ["All", "24", "12"])
lookback_months = None if lookback == "All" else int(lookback)

_scan_ts = None

# ----------------- MAIN APP & TABS -----------------
st.markdown("## 📊 MarketHub App")

tab1, tab2, tab3 = st.tabs(["🎯 Scanner", "🌍 Markets", "📰 Live News"])

with tab1:
    if scan_all:
        tf_tuple = tuple(univ_tfs)
        rows = []
        with st.spinner(f"Scanning..."):
            if live_sel: rows += load_universe_live(tuple(live_sel), min_score, False, False, eod_filter, tuple(sel_universe))
            if stable_sel: rows += load_universe_stable(tuple(stable_sel), min_score, False, False, eod_filter, tuple(sel_universe), _day_key())
            
        _scan_ts = datetime.datetime.now()
        
        c1, c2 = st.columns(2)
        dir_opt = c1.selectbox("Direction", ["All", "Demand", "Supply"], index=0)
        sort_opt = c2.selectbox("Sort", ["Near / Upcoming", "Score ↓", "Asset"], index=0)

        rr = [x for x in rows if (not active_only or x["state"] in ("Fresh", "Tested")) and (dir_opt == "All" or x["dir"] == dir_opt)]
        for x in rr: x["_dist"] = abs(x["last"] - x["entry"]) / x["entry"] if x["last"] else 1e9

        if sort_opt == "Near / Upcoming": rr.sort(key=lambda x: (x["_dist"], -x["score"]))
        elif sort_opt == "Score ↓": rr.sort(key=lambda x: -x["score"])
        else: rr.sort(key=lambda x: (x["symbol"], x["tf"]))

        render_zone_table(rr, scan_time=_scan_ts)
    else:
        try:
            zones, df, extra = load_scan(symbol, timeframe, min_score, False, lookback_months, False)
            last = float(df["close"].iloc[-1]) if df is not None and len(df) else None
            try: import tv; tv_url = tv.chart_url(symbol, timeframe)
            except ImportError: tv_url = f"https://www.tradingview.com/chart/?symbol=NSE:{symbol.replace('.NS', '')}"
                
            rows = [{"symbol": symbol, "tf": timeframe, "pattern": z.patternType, "dir": "Demand" if z.isDemand else "Supply", "entry": round(z.proxVal, 2), "distal": round(z.distVal, 2), "sl": round(z.slVal, 2), "risk_pct": round(getattr(z, "riskPct", 0.0), 2), "score": z.densityScore, "hq": bool(z.isHQ), "state": z.state, "touches": z.touchCount, "last": last, "tv": tv_url} for z in zones]
            if active_only: rows = [r for r in rows if r["state"] in ("Fresh", "Tested")]
            render_zone_table(rows, scan_time=datetime.datetime.now())
        except Exception as ex: 
            st.error(f"Error: {ex}")

with tab2:
    st.markdown('<div class="phead"><span class="t">🌍 Global Indices & Commodities</span></div>', unsafe_allow_html=True)
    render_board()
    st.markdown('<div class="phead"><span class="t">🧱 Sector Indices</span></div>', unsafe_allow_html=True)
    render_sectors()

with tab3:
    st.markdown('<div class="phead"><span class="t">📰 Live Market Feed</span></div>', unsafe_allow_html=True)
    ns = load_news()
    if ns:
        top = ns[0]
        title_hi = _hi(top["title"])
        st.markdown(f'<div class="livebox"><span class="pulse"></span><span style="color:#f2f6ff; font-weight:700; font-size:13px;"><a href="{top["link"]}" target="_blank" style="color:inherit; text-decoration:none;">{title_hi}</a></span></div>', unsafe_allow_html=True)
        
        # 🔔 Broker-Style Toast Notification
        if st.session_state.last_news_title != title_hi:
            st.toast(f"📰 ताज़ा खबर: {title_hi}", icon="🔥")
            st.session_state.last_news_title = title_hi

        for it in ns[1:]:
            st.markdown(f'<div class="news-item"><div class="news-time">{it["published"].strftime("%H:%M")}</div><div class="news-body"><a class="news-title" href="{it["link"]}" target="_blank">{_hi(it["title"])}</a><div><span class="chip t">{it["source"]}</span></div></div></div>', unsafe_allow_html=True)
    else:
        st.caption("कोई ताज़ा समाचार उपलब्ध नहीं है। सुनिश्चित करें कि news.py में feedparser इंस्टॉल है।")
