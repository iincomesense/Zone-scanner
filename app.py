# -*- coding: utf-8 -*-
"""
MarketHub — Demand & Supply Zone Scanner (Universe · multi-timeframe)
====================================================================
One page:
  • TOP   : Zone Scanner — all NSE stocks × multi-timeframe (English table,
            each row links to TradingView chart + live option chain/OI)
  • MID   : Live Market Board + Global Indices + Live Sector Indices (compact tables)
  • FII/DII (today) + Options OI
  • BOTTOM: News + Events (headlines in हिंदी, tap = open original)

Deploy:  streamlit run app.py   (all .py in the repo root)
Data:    Yahoo Finance / TradingView / NSE / niftytrader / RSS  (all keyless)
"""
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

st.set_page_config(page_title="MarketHub · Zone Scanner", page_icon="📊",
                   layout="wide", initial_sidebar_state="collapsed")

# ── Inline theme ────────────────────────────────────────────────────────────
st.markdown("""
<style>
:root{
  --bg:#0b1220; --line:#22304a; --txt:#e6edf7; --muted:#8ba1c0;
  --up:#1ecb6b; --down:#ff4b5c; --accent2:#22d3ee; --accent:#4f8cff;
}
.stApp{background-color:var(--bg); color:var(--txt);}
[data-testid="stSidebar"]{background-color:#0d1524;}
[data-testid="stSidebar"] *{color:var(--txt);}
[data-testid="stHeader"]{background:rgba(11,18,32,.35);}
[data-baseweb="select"] *{background-color:#121a2b; color:#e6edf7;}
[data-testid="stExpander"]{background-color:#121a2b;}
[data-testid="stExpander"] *{color:#e6edf7;}

/* compact board table (small) */
.board-table{width:100%; border-collapse:collapse; font-size:10.5px;}
.board-table th{text-align:left; color:var(--muted); font-size:9.5px; text-transform:uppercase;
  letter-spacing:.3px; padding:3px 6px; border-bottom:1px solid var(--line); white-space:nowrap;}
.board-table td{padding:2.5px 6px; border-bottom:1px solid #161f33; color:#d9e5f6;
  font-variant-numeric:tabular-nums; white-space:nowrap;}
.board-table tr:hover{background:#121a2c;}
.board-table a.sym{font-weight:700; color:#eaf1fb; text-decoration:none;}
.board-table a.sym:hover{color:var(--accent2); text-decoration:underline;}
.board-table td.nm{color:#8ba1c0; font-size:9.5px;}
.board-table .grp td{background:#0e1626; color:var(--accent2); font-size:9px;
  font-weight:800; text-transform:uppercase; letter-spacing:1px; padding:3px 6px;}
.board-table .src{color:#5a6c8a; font-size:8.5px;}
.board-table td.tv{color:var(--accent2); font-weight:700; font-size:11px;}

.phead{display:flex; align-items:baseline; justify-content:space-between; flex-wrap:wrap;}
.phead .t{font-size:15px; font-weight:800; color:#eaf1fb;}
.phead .s{font-size:10.5px; color:var(--muted);}
.up{color:var(--up);} .dn{color:var(--down);} .flat{color:var(--muted);}

/* summary bar */
.sumbar{display:flex; gap:8px; flex-wrap:wrap; background:#0e1626;
  border:1px solid var(--line); border-radius:12px; padding:8px 12px;
  margin:8px 0; font-size:12.5px;}
.sumbar .it{color:#cfe0ff; font-variant-numeric:tabular-nums;}
.sumbar .it b{color:#eaf1fb;}
.sumbar .sep{color:var(--muted);}
.sumbar .lbl{color:var(--muted); font-size:10.5px;}

/* Hindi zone table — horizontally AND vertically scrollable (no zone is cut off) */
.zwrap{overflow:auto; max-height:560px; border:1px solid var(--line); border-radius:12px;
  background:#0e1626; scrollbar-width:thin;}
.zhin{width:100%; border-collapse:collapse; font-size:12px; min-width:1080px;}
.zhin thead th{position:sticky; top:0; z-index:3; text-align:left; color:var(--muted);
  font-size:10.5px; text-transform:uppercase; letter-spacing:.4px; padding:7px 8px;
  border-bottom:1px solid var(--line); background:#0c1422; white-space:nowrap;}
.zhin td{padding:6px 8px; border-bottom:1px solid #18233a; color:#d9e5f6;
  font-variant-numeric:tabular-nums; white-space:nowrap;}
.zhin tr.near:hover{background:#13233a;}
.zhin td.near-up{color:var(--up);}
.zhin .zm{font-size:10px; color:var(--muted);}
.zhin tr:hover{background:#131d31;}
.zhin a{color:var(--accent2); text-decoration:none; font-weight:600;}
.zhin a.sym{color:#eaf1fb; font-weight:700;}
.zhin a.sym:hover{color:var(--accent2); text-decoration:underline;}
.zhin .dot{font-size:9px; vertical-align:middle;}
.dot.dem{color:var(--up);} .dot.sup{color:var(--down);}
.zhin .hq{color:#f5c542;}
.zhin .st-fresh{color:var(--up);} .zhin .st-tested{color:var(--accent2);}
.zhin .st-broken{color:var(--muted);}
.zscore{font-size:11px; padding:1px 7px; border-radius:12px; border:1px solid var(--line);}
.zscore.hi{color:var(--up); border-color:rgba(30,203,107,.4);}
.zscore.md{color:var(--accent2); border-color:rgba(34,211,238,.4);}
.zscore.lo{color:var(--muted);}
.oi{font-size:11px; padding:1px 7px; border-radius:10px; border:1px solid var(--line);
  white-space:nowrap; font-weight:600;}
.oi.plus{color:var(--up); border-color:rgba(30,203,107,.4);}
.oi.minus{color:var(--down); border-color:rgba(255,75,92,.35);}
.oi.none{color:var(--muted);}

.fdbx{background:#0e1626; border:1px solid var(--line); border-radius:10px; padding:8px 10px;}
.fdbx .lab{font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px;}
.fdbx .val{font-size:19px; font-weight:800; font-variant-numeric:tabular-nums;}
.fdbx .sub{font-size:10px; color:var(--muted);}
.fdrow{display:flex; gap:12px; flex-wrap:wrap;}
.fdrow .fdbx{flex:1 1 120px;}
.news-item{display:flex; gap:9px; padding:7px 4px; border-bottom:1px solid #18233a;}
.news-item:hover{background:#131d31;}
.news-time{color:var(--muted); font-size:11px; width:44px; flex:0 0 44px;}
.news-body{flex:1; min-width:0;}
.news-title{color:#dbeeef; font-size:13px; font-weight:600; text-decoration:none;}
.news-body a{text-decoration:none; word-break:break-word;}
.news-src{color:var(--muted); font-size:10px;}
/* live notification */
.livebox{display:flex; gap:10px; align-items:center; background:linear-gradient(90deg,#12233f,#0e1626);
  border:1px solid rgba(255,75,92,.35); border-radius:12px; padding:8px 11px; margin:4px 0 10px;}
.livebox .pulse{display:inline-block; width:9px; height:9px; border-radius:50%;
  background:#ff4b5c; box-shadow:0 0 0 0 rgba(255,75,92,.7); animation:pulse 1.6s infinite;}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(255,75,92,.7);}
  70%{box-shadow:0 0 0 8px rgba(255,75,92,0);} 100%{box-shadow:0 0 0 0 rgba(255,75,92,0);}}
.livebox .lbt{font-size:9.5px; letter-spacing:1px; color:#ff8b96; font-weight:800; white-space:nowrap;}
.livebox .lbtitle{font-size:12.5px; font-weight:600; color:#f2f6ff; line-height:1.35;}
.livebox a{color:inherit; text-decoration:none;}
.livebox a:hover{color:var(--accent2);}
.chip{font-size:11px; background:#152036; border:1px solid var(--line);
  color:#cfe0ff; border-radius:20px; padding:2px 9px; display:inline-block;}
.chip.t{background:#1a2740; color:var(--accent2);}
.chips{display:flex; gap:6px; flex-wrap:wrap; margin:3px 0;}
</style>
""", unsafe_allow_html=True)


# ── Hindi translation for NEWS only (best-effort, keyless) ─────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def _hi(text):
    if not text or not str(text).strip():
        return str(text)
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "auto", "tl": "hi", "dt": "t", "q": str(text)},
            timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            out = "".join(x[0] for x in r.json()[0]).strip()
            if out:
                return out
    except Exception:
        pass
    return str(text)


# ── timeframes / labels ─────────────────────────────────────────────────────
LIVE_TFS = ["10m", "15m", "30m", "75m", "1h", "2h", "4h"]      # change within trading hours
STABLE_TFS = ["6h", "8h", "1D", "1W", "1M"]      # slow — not re-scanned repeatedly

TF_LABEL = {
    "10m": "10 Min", "15m": "15 Min", "30m": "30 Min", "75m": "75 Min", "1h": "1 Hour",
    "2h": "2 Hours", "4h": "4 Hours", "6h": "6 Hours", "8h": "8 Hours",
    "1D": "Daily", "1W": "Weekly", "1M": "Monthly",
}


def _tf_hi(tf):
    return TF_LABEL.get(str(tf), str(tf))


def _score_cls(sc):
    return "hi" if sc >= 90 else ("md" if sc >= 60 else "lo")


# ── Cached data helpers ─────────────────────────────────────────────────────
@st.cache_data(ttl=30, show_spinner=False)
def load_market():
    import marketdata as md
    return md.fetch_all()


@st.cache_data(ttl=30, show_spinner=False)
def load_sectors():
    import sectors as sc
    return sc.fetch_sectors()


@st.cache_data(ttl=300, show_spinner=False)
def load_news():
    import news as n
    return n.fetch_latest(20)


@st.cache_data(ttl=600, show_spinner=False)
def load_news_body(url):
    import news as n
    return n.fetch_article(url)


@st.cache_data(ttl=300, show_spinner=False)
def load_events():
    import events as e
    return e.fetch_events(16)


@st.cache_data(ttl=90, show_spinner=False)
def load_fiidii():
    import fiidii as f
    return f.fetch(6), f.monthly()


@st.cache_data(ttl=60, show_spinner=False)
def load_options(symbol):
    import options as o
    return o.live_oi(symbol), o.top_strikes(symbol, n=7), o.deep_links(symbol)


@st.cache_data(ttl=30, show_spinner=False)
def load_scan(symbol, timeframe, min_score, strict, lookback, recommended):
    import zscan
    return zscan.scan(symbol, timeframe, min_score=min_score, strict=strict,
                      lookback_months=lookback, recommended=recommended)


# universe scan split into LIVE (short TTL → auto-refresh) and STABLE (day-keyed)
def _day_key():
    """Return today's session key (YYYY-MM-DD).  Stable (>=1D) timeframes only change
    when the day changes, so we key their cache on this: a new day forces one fresh
    scan; within the day it stays cached (scanned once)."""
    return datetime.datetime.now().strftime("%Y-%m-%d")


@st.cache_data(ttl=120, show_spinner=False)
def load_universe_live(tf_tuple, min_score, recommended, strict, eod_filter, symbols_tuple):
    import zscan
    return zscan.scan_universe_zones(timeframes=tf_tuple, min_score=min_score,
                                     recommended=recommended, strict=strict,
                                     active_only=False, eod_filter=eod_filter,
                                     symbols=list(symbols_tuple) if symbols_tuple else None)


# Stable TFs (1D/1W/1M, and 6h/8h) change only once a day -> cached for the whole
# day; a new day (day_key) retriggers exactly one fresh scan.
@st.cache_data(ttl=86400, show_spinner=False)
def load_universe_stable(tf_tuple, min_score, recommended, strict, eod_filter, symbols_tuple, day_key):
    import zscan
    return zscan.scan_universe_zones(timeframes=tf_tuple, min_score=min_score,
                                     recommended=recommended, strict=strict,
                                     active_only=False, eod_filter=eod_filter,
                                     symbols=list(symbols_tuple) if symbols_tuple else None)


def fmt_cr(x):
    if x is None:
        return "—"
    x = float(x)
    cls = "up" if x > 0 else ("dn" if x < 0 else "flat")
    return f'<span class="{cls}">{x:+,.0f}</span>'


def _chg_html(c):
    if c is None:
        return '<span class="flat">—</span>'
    cls = "up" if c > 0 else ("dn" if c < 0 else "flat")
    sign = "+" if c > 0 else ("−" if c < 0 else "")
    return f'<span class="{cls}">{sign}{c:.2f}%</span>'


def auto_refresh(seconds, key):
    """Auto-refresh the page every `seconds` using Streamlit's BUILT-IN fragment
    API (no external package), falling back to a manual Refresh button if the
    built-in API is unavailable, so the app NEVER crashes."""
    secs = int(seconds)
    # Outer strip: show the next-refresh countdown (updates on each rerun).
    try:
        # Guarded: st.fragment(run_every=...) is built into Streamlit >=1.37.
        import streamlit as _st
        _st.caption(f"⟳ Auto-refresh every {secs//60}m · going live")
    except Exception:
        pass
    # Provide a manual refresh button that works on any Streamlit version.
    if st.button("⟳ Refresh now", key=f"refresh_{key}"):
        st.rerun()


# ── Compact English market board + sector indices (tables) ──────────────────
GRP_EN = {"dollar": "💵 Currencies", "rates": "🏛️ Rates & Bonds",
          "commodities": "🥇 Metals & Energy", "indices": "📈 Global Indices"}

# ── TradingView chart symbol resolution (never crashes) ──────────────────────
# app.py owns a canonical map, so the board/sector chart links keep working even
# if a stale marketdata.py / sectors.py is deployed WITHOUT tv_chart_symbol().
_BOARD_TV = {
    "DXY": "TVC:DXY", "USDINR": "FX_IDC:USDINR", "TLT": "AMEX:TLT",
    "US 10Y": "TVC:US10Y", "XAUUSD": "OANDA:XAUUSD", "XAGUSD": "OANDA:XAGUSD",
    "SPOTCRUDE": "TVC:USOIL", "GIFT NIFTY": "NSEIX:NIFTY1!", "NIFTY 50": "NSE:NIFTY",
    "US30": "TVC:DJI", "US500": "TVC:SPX", "JP225": "TVC:NI225", "SSE": "SSE:000001",
}
_SECTOR_TV = {
    "NIFTY AUTO": "NSE:NIFTY_AUTO", "NIFTY IT": "NSE:CNXIT",
    "NIFTY PHARMA": "NSE:NIFTY_PHARMA", "NIFTY FMCG": "NSE:NIFTY_FMCG",
    "NIFTY METAL": "NSE:NIFTY_METAL", "NIFTY ENERGY": "NSE:NIFTY_ENERGY",
    "NIFTY REALTY": "NSE:NIFTY_REALTY", "NIFTY MEDIA": "NSE:NIFTY_MEDIA",
    "NIFTY PSU BANK": "NSE:NIFTY_PSU_BANK", "NIFTY INFRA": "NSE:NIFTY_INFRA",
    "NIFTY FINANCIAL SERVICES": "NSE:NIFTY_FIN", "NIFTY BANK": "NSE:BANKNIFTY",
    "NIFTY 50": "NSE:NIFTY",
}


def _tv_chart_url(tv_sym, interval="1D"):
    """Build a TradingView chart URL for a symbol.  Safe (never raises)."""
    return f'https://www.tradingview.com/chart/?symbol={quote(str(tv_sym))}&interval={interval}'


def _board_tv_sym(label, module=None):
    """Resolve a board tile label -> TradingView symbol."""
    try:
        if module is not None and hasattr(module, "tv_chart_symbol"):
            return module.tv_chart_symbol(label)
    except Exception:
        pass
    return _BOARD_TV.get(str(label).strip(), str(label).strip())


def _sector_tv_sym(full, module=None):
    """Resolve an NSE sector full-name -> TradingView symbol."""
    try:
        if module is not None and hasattr(module, "tv_chart_symbol"):
            return module.tv_chart_symbol(full)
    except Exception:
        pass
    return _SECTOR_TV.get(str(full).strip(), str(full).strip())


def render_board():
    import marketdata as md
    data = load_market()
    st.markdown('<div class="phead"><span class="t">🌍 Live Market Board '
                '<span style="color:#1ecb6b;font-size:11px;">● LIVE</span></span>'
                '<span class="s">auto-refresh 30s · tap a symbol to open chart</span></div>',
                unsafe_allow_html=True)
    html = ['<table class="board-table"><thead><tr><th>Symbol</th><th>Last</th>'
            '<th>Chg%</th><th>Chart</th></tr></thead><tbody>']
    for grp, tiles in md.TILES:
        html.append(f'<tr class="grp"><td colspan="4">{GRP_EN.get(grp, grp)}</td></tr>')
        for t in tiles:
            q = data.get(t["label"], {})
            px = f"{q['price']:,.2f}" if q.get("price") is not None else "—"
            _tv_sym = _board_tv_sym(t["label"], md)
            _tv_url = _tv_chart_url(_tv_sym)
            html.append(f'<tr><td><a class="sym" href="{_tv_url}" target="_blank" '
                        f'title="Open {t["label"]} on TradingView">📈 {t["label"]}</a></td>'
                        f'<td>{px}</td>'
                        f'<td>{_chg_html(q["chg_pct"])}</td>'
                        f'<td class="tv"><a href="{_tv_url}" target="_blank" title="Chart">➜</a></td></tr>')
    html.append('</tbody></table>')
    st.markdown("".join(html), unsafe_allow_html=True)


def render_sectors():
    import sectors as sc
    sec = load_sectors()
    if not sec:
        return
    st.markdown('<div class="phead"><span class="t">🧱 Live Sector Indices '
                '<span style="color:#1ecb6b;font-size:11px;">● LIVE</span></span>'
                '<span class="s">NSE · 30s · tap an index to open chart</span></div>',
                unsafe_allow_html=True)
    html = ['<table class="board-table"><thead><tr><th>Index</th><th>Last</th>'
            '<th>Chg%</th><th>Chart</th></tr></thead><tbody>']
    for s in sec:
        cls = "up" if s["chg_pct"] >= 0 else "dn"
        sign = "+" if s["chg_pct"] >= 0 else "−"
        _tv_sym = _sector_tv_sym(s.get("full", s["label"]), sc)
        _tv_url = _tv_chart_url(_tv_sym)
        html.append(f'<tr><td><a class="sym" href="{_tv_url}" target="_blank" '
                    f'title="Open {s["label"]} on TradingView">📈 {s["label"]}</a></td>'
                    f'<td>{s["price"]:,.1f}</td>'
                    f'<td class="{cls}">{sign}{s["chg_pct"]:.2f}%</td>'
                    f'<td class="tv"><a href="{_tv_url}" target="_blank" title="Chart">➜</a></td></tr>')
    html.append('</tbody></table>')
    st.markdown("".join(html), unsafe_allow_html=True)


# ── FII/DII (today + expandable history) ────────────────────────────────────
def render_fiidii():
    st.markdown('<div class="phead"><span class="t">🏛️ FII / DII (Today)</span>'
                '<span class="s">live · 90s</span></div>', unsafe_allow_html=True)
    try:
        days, monthly = load_fiidii()
    except Exception:
        days, monthly = [], {}
    if not days:
        st.caption("FII/DII data not reachable right now.")
        return
    today = days[0]
    fii, dii = today.get("fii_net"), today.get("dii_net")
    d = today.get("date", "")
    dome = d.strftime("%d-%b") if hasattr(d, "strftime") else str(d)
    st.markdown(
        f'<div class="fdrow">'
        f'<div class="fdbx"><div class="lab">FII / FPI {dome}</div>'
        f'<div class="val">{fmt_cr(fii)}</div>'
        f'<div class="sub">Buy {today.get("fii_buy","—")} · Sell {today.get("fii_sell","—")} Cr</div></div>'
        f'<div class="fdbx"><div class="lab">DII {dome}</div>'
        f'<div class="val">{fmt_cr(dii)}</div>'
        f'<div class="sub">Buy {today.get("dii_buy","—")} · Sell {today.get("dii_sell","—")} Cr</div></div>'
        f'<div class="fdbx"><div class="lab">NIFTY 50</div>'
        f'<div class="val">{today.get("nifty","—")}</div>'
        f'<div class="sub">chg {fmt_cr(today.get("chg",""))} pts</div></div>'
        f'</div>', unsafe_allow_html=True)
    if len(days) > 1:
        with st.expander(f"📅 Previous {min(len(days)-1, 5)} days (tap to expand)"):
            for rec in days[1:6]:
                st.markdown(
                    f'<div class="fdbx"><div class="lab">{rec.get("date","")}</div>'
                    f'<div class="val">FII {fmt_cr(rec.get("fii_net"))} · '
                    f'DII {fmt_cr(rec.get("dii_net"))} · NIFTY {rec.get("nifty","—")}</div></div>',
                    unsafe_allow_html=True)


# ── Options OI (compact) ────────────────────────────────────────────────────
def _oi_badge(oi, is_demand):
    if not oi:
        return '<span class="oi none">—</span>'
    if isinstance(oi, dict):
        cls = "plus" if oi.get("aligned") else "minus"
        return f'<span class="oi {cls}" title="Put OI vs Call OI">{oi["label"]}</span>'
    aligned = (oi.startswith("P>") if is_demand else oi.startswith("C>"))
    return f'<span class="oi {"plus" if aligned else "minus"}">{oi}</span>'


def render_options(symbol):
    live, strikes, links = load_options(symbol)
    st.markdown(f'<div class="phead"><span class="t">🎯 Options OI</span>'
                f'<span class="s">{symbol.upper()}</span></div>', unsafe_allow_html=True)
    if live:
        st.markdown(
            f'<div class="fdrow">'
            f'<div class="fdbx"><div class="lab">CALL OI</div>'
            f'<div class="val">{live["call_oi"]:,.0f}</div></div>'
            f'<div class="fdbx"><div class="lab">PUT OI</div>'
            f'<div class="val">{live["put_oi"]:,.0f}</div></div>'
            f'<div class="fdbx"><div class="lab">PCR</div>'
            f'<div class="val">{live["pcr"]:.2f}</div></div>'
            f'</div>', unsafe_allow_html=True)
    else:
        st.caption("Live OI blocked on cloud IP — open the chain link in your browser.")
    li = "".join(f'<a class="chip" href="{l["url"]}" target="_blank" '
                 f'style="text-decoration:none;">↗ {l["label"]}</a>' for l in links)
    st.markdown(f'<div class="chips">{li}</div>', unsafe_allow_html=True)


# ── Zone table (English headers, screenshot-style) ──────────────────────────
def zone_table_heading(rows, lookback_hi="All", scan_time=None):
    fresh = sum(1 for r in rows if r["state"] == "Fresh")
    tested = sum(1 for r in rows if r["state"] == "Tested")
    hq = sum(1 for r in rows if r["hq"])
    now = (scan_time or datetime.datetime.now()).strftime("%d-%b %H:%M:%S")
    return (f'<div class="sumbar">'
            f'<span class="it"><span class="lbl">Last scan ⟳</span> <b>{now}</b></span>'
            f'<span class="sep">|</span>'
            f'<span class="it"><b>{len(rows)}</b> <span class="lbl">Zones</span></span>'
            f'<span class="sep">|</span>'
            f'<span class="it"><b>{fresh}</b> <span class="lbl">Fresh</span></span>'
            f'<span class="sep">|</span>'
            f'<span class="it"><b>{tested}</b> <span class="lbl">Tested</span></span>'
            f'<span class="sep">|</span>'
            f'<span class="it"><span style="color:#f5c542;">⭐ {hq}</span> <span class="lbl">HQ</span></span>'
            f'<span class="sep">|</span>'
            f'<span class="it"><span class="lbl">Lookback</span> {lookback_hi}</span>'
            f'</div>')


def _fmt2(v):
    return "—" if v is None else f"{float(v):,.2f}"


def _tp_badge(r):
    """v13.3 TP-SCORE chip (REPORT14): ≥4/6 signs → 🎯 TP-High (56 % win in study), ≤2 → ⚠ TP-Low (19 %)."""
    sc, mx, lab = r.get("tp_score"), r.get("tp_max"), r.get("tp_label") or ""
    if sc is None or not mx:
        return "—"
    col = {"TP-High": "#22c55e", "TP-Low": "#f87171"}.get(lab, "#eab308")
    icon = {"TP-High": "🎯 ", "TP-Low": "⚠ "}.get(lab, "")
    why = (r.get("tp_why") or "").replace('"', "'")
    return (f'<span title="{why}" style="color:{col};font-weight:700;">{icon}{sc}/{mx}</span>'
            f'<span style="display:block;font-size:10px;color:#9fb0c8;">{r.get("tp_signs", "")}</span>')


def _status_badge(es):
    es = es or ""
    if es == "Waiting":
        return '<span style="color:#4f8cff;font-weight:700;">⏳ Waiting for retest</span>'
    if es == "Triggered":
        return '<span style="color:#22c55e;font-weight:700;">✅ Entry triggered</span>'
    if es.startswith("Failed"):
        why = es.replace("Failed-", "")
        return f'<span style="color:#f87171;">✖ {why}</span>'
    return es or "—"


def render_zone_table(rows, title, subtitle, lookback_hi="All", scan_time=None):
    st.markdown(f'<div class="phead"><span class="t">{title}</span>'
                f'<span class="s">{subtitle}</span></div>', unsafe_allow_html=True)
    if not rows:
        st.info("No valid zones found. Try a lower score / wider timeframe.")
        return
    st.markdown(zone_table_heading(rows, lookback_hi, scan_time), unsafe_allow_html=True)
    html = ['<div class="zwrap"><table class="zhin"><thead><tr>'
            '<th>Asset</th><th>Chart</th><th>Timeframe</th><th>Direction</th>'
            '<th>Pattern</th><th>Type</th><th>State</th><th>HQ</th>'
            '<th>Score</th><th>Boring</th><th>Gap×LegIn</th><th>Entry (Proximal)</th><th>Distal</th><th>SL</th><th>Risk %</th><th>Entry status</th><th title="v13.3 TP-SCORE: A Nifty EMA20 · B HTF EMA20 · C leg-in volume · D quiet retest · E EMA slope · F macro (VIX/S&P)">TP-Score</th><th>OI</th><th>Chain</th>'
            '</tr></thead><tbody>']
    for r in rows:
        disp = r["symbol"].replace(".NS", "")
        is_dem = r["dir"] == "Demand"
        dot = ('<span class="dot dem">●</span>' if is_dem else '<span class="dot sup">●</span>')
        tv = (f'<a href="{r["tv"]}" target="_blank">✓ Open</a>' if r.get("tv") else "—")
        symlink = (f'<a class="sym" href="{r["tv"]}" target="_blank" '
                   f'title="TradingView {r["tf"]}">📈 {disp}</a>' if r.get("tv")
                   else f'<span style="font-weight:700;color:#eaf1fb;">{disp}</span>')
        state_txt = f'{r["state"]} (#{r.get("touches", 0)})'
        hq = '<span class="hq">⭐</span>' if r.get("hq") else ""
        score = f'<span class="zscore {_score_cls(r["score"])}">{r["score"]}</span>'
        chain = (f'<a href="{r["chain"]}" target="_blank">OI ↗</a>' if r.get("chain") else "—")
        oi = _oi_badge(r.get("oi"), is_dem)
        # distance of the zone to the current price (near/upcoming marker + badge)
        dist = r.get("_dist")
        dist_badge = ""
        near_cls = ""
        if dist is not None:
            d = dist * 100.0
            dist_badge = f'<span class="zm" title="% away from current LTP">🎯 {d:.1f}%</span>'
            if d <= 2.0:
                near_cls = ' class="near"'
                dist_badge = f'<span class="zm near-up" title="Near / upcoming">🎯 {d:.1f}%</span>'
        html.append(
            f'<tr{near_cls}><td>{symlink}</td><td>{tv}</td><td>{_tf_hi(r["tf"])}</td>'
            f'<td>{dot} {r["dir"]} <span style="display:block;">{dist_badge}</span></td>'
            f'<td>{r["pattern"]}</td>'
            f'<td>{r.get("cat", r.get("pattern_type", "Continuation"))}</td>'
            f'<td class="st-{r["state"].lower()}">{state_txt}</td><td>{hq}</td>'
            f'<td>{score}</td><td>{r.get("boring", "—")}</td><td>{_fmt2(r.get("gap_x_legin"))}</td><td>{r["entry"]:,.2f}</td><td>{_fmt2(r.get("distal"))}</td><td>{r["sl"]:,.2f}</td><td>{_fmt2(r.get("risk_pct"))}</td>'
            f'<td>{_status_badge(r.get("entry_status"))}</td>'
            f'<td>{_tp_badge(r)}</td>'
            f'<td>{oi}</td><td>{chain}</td></tr>')
    html.append('</tbody></table></div>')
    st.markdown("".join(html), unsafe_allow_html=True)
    st.caption("Sort = Near/Upcoming (closest to current LTP first). 🎯 % = distance of the zone "
               "entry from the current price (≤2% = near-upcoming, highlighted). "
               "Chart = TradingView at that TF. OI = live Put/Call OI (Demand lean-bullish when "
               "P>C; Supply lean-bearish when C>P). Chain = that stock's NSE option chain. "
               "Scroll the table up/down — every scanned zone is shown. "
               "v14.0 FINAL 12-RULE core: Entry line = boring candle BODY edge; SL = distal wick (buffer 0); "
               "leg-in (wick≤50%, lower wick≤25%, close-strong 60%, TR≥ATR), boring 1-3 (body≤20% classic UOC), "
               "leg-out (wick≤45%, body>leg-in ladder, TR≥1.5× boring, close-strong 60%, TR>ATR), band≤0.75%, RR 1:3. "
               "Entry = zone_core confirm-close engine (a candle touches the entry line and closes back beyond it). "
               "TP-Score (v13.3 study of every target-hitting zone): A = Nifty daily close on the zone's side of EMA20, "
               "B = higher-TF close on the zone's side of EMA20, C = leg-in candle volume ≥ 20-bar avg, D = retest candle "
               "volume < 1.3× avg (quiet), E = own-TF EMA20 slope with the zone, F = macro (demand: VIX ≥ 16.5 or S&P 20-day < 0; "
               "supply: VIX < 16.5). 🎯 ≥4/6 → 56 % win in backtest, ⚠ ≤2/6 → 19 %. Hover the score for the sign-by-sign reason.")


# ── Sidebar (collapsed by default, compact) ────────────────────────────────
import zdata

st.sidebar.markdown("## ⚙️ Scanner Settings")
scan_all = st.sidebar.toggle("All NSE stocks × Multi-Timeframe", value=True,
                             help="Scan the whole universe across selected timeframes. "
                                  "Turn off for a single symbol.")
@st.cache_data(ttl=86400, show_spinner=False)
def _universe_today(day_key):
    """NSE F&O stocks with market-cap >= ₹45,000 Cr (live NSE list + yfinance mcap; bundled fallback)."""
    try:
        syms, mcap, src = zdata.build_universe()
        return syms, {k: mcap.get(k) for k in syms}, src
    except Exception:
        syms, mcap = zdata.universe_snapshot()
        return syms, {k: mcap.get(k) for k in syms}, "bundled snapshot"


if scan_all:
    _u_syms, _u_mcap, _u_src = _universe_today(datetime.date.today().isoformat())
    st.sidebar.markdown(f"**Universe** — Nifty F&O stocks, market-cap ≥ ₹45,000 Cr "
                        f"<span style='font-size:10px;color:#8ba1c0;'>({len(_u_syms)} stocks · {_u_src})</span>",
                        unsafe_allow_html=True)
    sel_universe = st.sidebar.multiselect(
        "Stocks (all selected by default — remove any to narrow)", _u_syms, default=list(_u_syms),
        format_func=lambda x: f"{x.replace('.NS', '')}  ₹{(_u_mcap.get(x) or 0)/1000:.0f}k Cr",
        help="Auto-built daily from the NSE F&O list; only stocks with market-cap ≥ ₹45,000 Cr.")
    if not sel_universe:
        sel_universe = list(_u_syms)
    st.sidebar.markdown("**Timeframes**\n"
                        "<span style='font-size:10px;color:#8ba1c0;'>Intraday = live auto-refresh · Daily+ = scanned **once a day**</span>",
                        unsafe_allow_html=True)
    univ_tfs = st.sidebar.multiselect(
        "Timeframes", zdata.TIMEFRAMES, default=["10m", "15m", "1h", "2h", "4h", "6h", "1D", "1W", "1M"],
        format_func=_tf_hi,
        help="15m-4h auto-refresh during the day. 1D/1W/1M (and 6h/8h) change only "
             "once the day completes, so they are scanned once a day.")
    if not univ_tfs:
        univ_tfs = ["10m", "15m", "1h", "2h", "4h", "6h", "1D", "1W", "1M"]
    live_sel = [t for t in univ_tfs if t in LIVE_TFS]
    stable_sel = [t for t in univ_tfs if t in STABLE_TFS]
    auto_live = st.sidebar.toggle("Live auto-refresh (intraday)", value=True,
                                  help="Automatically re-scan the fast timeframes; "
                                       "slow timeframes stay cached.")
    eod_filter = st.sidebar.toggle("Scan only in EOD band (daily close high+10% … low−10%)", value=True,
                                   help="No date range: every TF's full history is scanned and only zones "
                                        "inside the last completed daily candle's high+10% … low−10% are shown.")
    symbol, timeframe = "RELIANCE.NS", "4h"
else:
    sel_universe, univ_tfs, live_sel, stable_sel = None, [], [], []
    auto_live, eod_filter = False, True
    symbol = st.sidebar.text_input("Symbol", value="RELIANCE.NS",
                                   help="^NSEI = Nifty, ^NSEBANK = Bank Nifty.")
    timeframe = st.sidebar.selectbox("Timeframe", zdata.TIMEFRAMES,
                                     index=zdata.TIMEFRAMES.index("4h"))

min_score = st.sidebar.slider("Min quality score (v14.0 12-rule core: 0–100)", 20, 100, 45, step=5)
strict = st.sidebar.toggle("Spec-strict rules", value=False)
recommended = st.sidebar.toggle("Recommended setup (12-rule · confirm-close · RR1:3)", value=False)
active_only = st.sidebar.toggle("Active zones only (Fresh/Tested)", value=True,
                                help="Hide Broken zones.")
lookback = st.sidebar.selectbox("Lookback", ["All", "24", "12", "6", "3"])
lookback_months = None if lookback == "All" else int(lookback)
st.sidebar.markdown("---")
st.sidebar.caption("Live data: Yahoo / TradingView / NSE / niftytrader (keyless). "
                   f"{datetime.datetime.now().strftime('%d-%b %H:%M')} IST")


# state that flows from the zone scan into the Options OI panel (below)
scanned_symbols = []      # unique symbols that produced zones
opt_symbol = None         # default stock to show option-chain / OI for
_scan_ts = None           # last universe-scan timestamp (current update time)


# ── TOP: Zone Scanner ──────────────────────────────────────────────────────
st.markdown("## 📊 Demand & Supply Zone Scanner")
st.caption("Nifty F&O stocks (market-cap ≥ ₹45,000 Cr) × 10m/15m/1h/2h/4h/6h/1D/1W/1M · EOD band high+10% … low−10% · DBR/RBR/RBD/DBD · zone_core v14.0 FINAL 12-RULE CORE "
           "(Entry = boring BODY edge · SL = distal wick, buffer 0 · leg-in: wick≤50% / lower wick≤25% / close-strong 60% / TR≥ATR · boring 1-3 body≤20% classic UOC · leg-out: wick≤45% / body>leg-in / TR≥1.5× boring / close-strong 60% / TR>ATR · band≤0.75% · confirm-close · RR 1:3) · "
           "tap any row for TradingView chart + live option OI.")

if scan_all:
    tf_tuple = tuple(univ_tfs)
    rows = []
    _t0 = datetime.datetime.now()
    with st.spinner(f"Scanning {len(sel_universe)} stocks × {len(tf_tuple)} timeframes … "
                    "(first run ≈ 30-60 s, then a few seconds)"):
        if live_sel:
            rows += load_universe_live(tuple(live_sel), min_score, recommended, strict,
                                       eod_filter, tuple(sel_universe))
        if stable_sel:
            rows += load_universe_stable(tuple(stable_sel), min_score, recommended, strict,
                                         eod_filter, tuple(sel_universe), _day_key())
    _scan_secs = (datetime.datetime.now() - _t0).total_seconds()
    # auto-refresh the fast (live) timeframes only
    if auto_live and live_sel:
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=180_000, key="mh_univ")
        except Exception:
            auto_refresh(180, "mh_univ")
    st.markdown(f'<div class="phead"><span class="t">🧭 Universe Zone Scan '
                f'<span style="color:#4f8cff;">({len(sel_universe)} × '
                f'{" · ".join(tf_tuple)})</span></span>'
                f'<span class="s">{len(live_sel)} live TF (auto-refresh) · '
                f'{len(stable_sel)} daily+ TF (scanned once a day)</span></div>',
                unsafe_allow_html=True)
    if eod_filter:
        st.caption("📌 EOD band ON — no date range; every timeframe's full history is scanned and only "
                   "zones inside the last completed daily (EOD close) candle's **high+10% … low−10%** are shown.")
    st.caption(f"⚡ scan {_scan_secs:.1f}s · {len(rows)} zones (before filters) · "
               f"{datetime.datetime.now().strftime('%H:%M:%S')} IST")
    # record the CURRENT update/scan time (refresh keeps this live)
    _scan_ts = datetime.datetime.now()

    f1, f2, f3 = st.columns([1, 1, 1])
    dir_opt = f1.selectbox("Direction", ["All", "Demand", "Supply"], index=0)
    sort_opt = f2.selectbox("Sort", ["Near / Upcoming", "TP-Score ↓", "Score ↓", "Asset"], index=0)
    st_opt = f3.selectbox("State", ["All", "Fresh", "Tested"], index=0)

    rr = rows
    if active_only:
        rr = [x for x in rr if x["state"] in ("Fresh", "Tested")]
    if dir_opt == "Demand":
        rr = [x for x in rr if x["dir"] == "Demand"]
    elif dir_opt == "Supply":
        rr = [x for x in rr if x["dir"] == "Supply"]
    if st_opt == "Fresh":
        rr = [x for x in rr if x["state"] == "Fresh"]
    elif st_opt == "Tested":
        rr = [x for x in rr if x["state"] == "Tested"]

    # "Near / Upcoming" = the zone closest to the current price first (the NEXT
    # zones the stock is likely to reach).  Everything scrolls, so nothing is missed.
    def _dist(x):
        return abs(x["last"] - x["entry"]) / x["entry"] if x["last"] else 1e9
    for x in rr:
        x["_dist"] = _dist(x)
    if sort_opt == "Near / Upcoming":
        rr = sorted(rr, key=lambda x: (x["_dist"], -x["score"]))
    elif sort_opt == "TP-Score ↓":
        rr = sorted(rr, key=lambda x: (-(x.get("tp_score") or 0) / max(x.get("tp_max") or 1, 1), x["_dist"]))
    elif sort_opt == "Score ↓":
        rr = sorted(rr, key=lambda x: -x["score"])
    else:  # Asset
        rr = sorted(rr, key=lambda x: (x["symbol"], x["tf"]))

    # carry scanned-symbol set + default option stock (best score)
    seen = set()
    for x in rr:
        sym = x["symbol"]
        if sym not in seen:
            seen.add(sym)
            scanned_symbols.append(sym)
    if scanned_symbols and not opt_symbol:
        opt_symbol = max(rr, key=lambda x: x["score"])["symbol"]

    render_zone_table(rr, "All NSE Futures Stocks — Multi-Timeframe",
                      f'{len(tf_tuple)} TF · {len(sel_universe)} stocks · '
                      f'{len(rr)} zones', lookback_hi="All", scan_time=_scan_ts)
else:
    # single-stock scan -> same English table
    try:
        zones, df, extra = load_scan(symbol, timeframe, min_score, strict,
                                     lookback_months, recommended)
        last = float(df["close"].iloc[-1]) if df is not None and len(df) else None
    except Exception as ex:
        st.error(f"Could not scan {symbol}: {ex}")
        zones, df, extra = [], None, None
        last = None

    import tv as _tv
    import options as _opt
    import zscan as _zs
    _links = _opt.deep_links(symbol)
    _lc = "".join(f'<a class="chip" href="{l["url"]}" target="_blank" '
                  f'style="text-decoration:none;">↗ {l["label"]}</a>' for l in _links)
    _tvchip = (f'<a class="chip t" href="{_tv.chart_url(symbol, timeframe)}" '
               f'target="_blank" style="text-decoration:none;">📈 TradingView chart</a>')
    st.markdown(f'<div class="chips">{_tvchip}{_lc}</div>', unsafe_allow_html=True)

    band = None
    if eod_filter:
        zones, band = _zs.eod_zone_filter(zones, symbol)
    if band:
        st.markdown(
            f'<div class="sumbar" style="margin-top:4px;">'
            f'<span class="it"><span class="lbl">EOD band</span> '
            f'low {band["lo"]:,.2f}−10% = {band["eod_lo"]:,.2f} … '
            f'high {band["hi"]:,.2f}+10% = {band["eod_hi"]:,.2f}</span>'
            f'</div>', unsafe_allow_html=True)

    rows = [{"symbol": symbol, "tf": timeframe, "pattern": z.patternType,
             "dir": "Demand" if z.isDemand else "Supply", "cat": z.zoneCategory,
             "entry": round(z.proxVal, 2), "distal": round(z.distVal, 2), "sl": round(z.slVal, 2),
             "risk_pct": round(getattr(z, "riskPct", 0.0), 2),
             "entry_status": getattr(z, "entryStatus", ""), "boring": getattr(z, "baseCount", 0),
             "gap_x_legin": round(getattr(z, "gapToLegIn", 0.0), 2),
             "tp": round(z.tpVal, 2), "score": z.densityScore, "hq": bool(z.isHQ),
             "state": z.state, "touches": z.touchCount, "last": last,
             "chain": _links[0]["url"] if _links else "",
             "tv": _tv.chart_url(symbol, timeframe),
             "oi": _zs.oi_bias(symbol, z.isDemand)} for z in zones]
    if active_only:
        rows = [r for r in rows if r["state"] in ("Fresh", "Tested")]
    _scan_ts = datetime.datetime.now()
    scanned_symbols = [symbol]
    opt_symbol = symbol
    render_zone_table(rows, f"{symbol.replace('.NS','')} · {_tf_hi(timeframe)}",
                      "Single stock", lookback_hi=lookback, scan_time=_scan_ts)

    if isinstance(extra, dict) and extra.get("roi") and extra["roi"].get("n_trades"):
        roi, rec = extra["roi"], extra["recommended"]
        st.success(f"**Recommended ROI** (12-rule · {rec['entry_mode']} entry · RR 1:{rec['targetRR']:.1f}): "
                   f"{roi['n_trades']} trades · win {roi['win_pct']:.0f}% · "
                   f"**{roi['net_roi_pct']:+.2f}%**")


# ── MID: Market board + Sector indices (compact tables) ────────────────────
st.markdown('<div style="height:14px;"></div>', unsafe_allow_html=True)
try:
    render_board()
except Exception as _e:
    st.caption(f"Market board temporarily unavailable ({_e}).")
st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
try:
    render_sectors()
except Exception as _e:
    st.caption(f"Sector indices temporarily unavailable ({_e}).")

st.markdown('<div style="height:10px;"></div>', unsafe_allow_html=True)
r1, r2 = st.columns([1.0, 1.0], gap="small")
with r1:
    render_fiidii()
with r2:
    # Option chain / OI for the SCANNED stock (not Nifty).  Default = best stock
    # that produced a zone; switch to any other scanned stock via the selector.
    opts = scanned_symbols or ([symbol] if symbol else [])
    if opts:
        _disp = {s.replace(".NS", ""): s for s in opts}
        _names = list(_disp.keys())
        _default = (opt_symbol or opts[0]).replace(".NS", "")
        if _default not in _names:
            _default = _names[0]
        picked = st.selectbox("🎯 Options OI — stock", _names, index=_names.index(_default))
        render_options(_disp[picked])
    else:
        render_options(symbol)


# ── BOTTOM: News (हिंदी) + Events (हिंदी), live ────────────────────────────
st.markdown('<div style="height:14px;"></div>', unsafe_allow_html=True)
nc1, nc2 = st.columns([1.15, 1.0], gap="small")

with nc1:
    st.markdown("## 📰 News <span class='s'>हिंदी हेडलाइन · tap = read · live</span>",
                unsafe_allow_html=True)
    ns = load_news()
    if not ns:
        st.info("No headlines right now.")
    else:
        # 🔴 LIVE notification — today's top/breaking story, tap to read
        top = ns[0]
        ttop = top["published"]
        t_hi = _hi(top["title"])
        st.markdown(
            f'<div class="livebox"><span class="pulse"></span>'
            f'<span class="lbt">🔴 LIVE</span>'
            f'<a class="lbtitle" href="{top["link"]}" target="_blank" '
            f'title="Open original">दिन का प्रमुख · {t_hi}</a></div>',
            unsafe_allow_html=True)
        if top["link"].startswith("http"):
            with st.expander("📖 इस समाचार को पढ़ें (tap to read)"):
                body = load_news_body(top["link"]) or top.get("summary") or "Full text unavailable."
                st.markdown(f'<div style="font-size:12.5px;color:#cdd9ec;line-height:1.6;'
                            f'white-space:pre-line;max-height:330px;overflow:auto;">{body}</div>',
                            unsafe_allow_html=True)
                st.markdown(f'<div style="margin-top:4px;"><a href="{top["link"]}" '
                            f'target="_blank">original ↗</a></div>', unsafe_allow_html=True)
        # today's top headlines (the rest)
        for it in ns[1:11]:
            hi_title = _hi(it["title"])
            tags = "".join(f'<span class="chip t">{t}</span>' for t in it["tags"])
            tm = it["published"]
            tms = tm.strftime("%H:%M") if hasattr(tm, "strftime") else str(tm)[:5]
            st.markdown(
                f'<div class="news-item"><div class="news-time">{tms}</div>'
                f'<div class="news-body"><a class="news-title" href="{it["link"]}" '
                f'target="_blank">{hi_title}</a>'
                f'<div>{tags}<span class="news-src"> · {it["source"]} · '
                f'<a href="{it["link"]}" target="_blank" style="color:#8ba1c0;">'
                f'original ↗</a></span></div></div></div>', unsafe_allow_html=True)
            if it["link"].startswith("http"):
                with st.expander("📖 पढ़ें"):
                    body = load_news_body(it["link"]) or it.get("summary") or "Full text unavailable."
                    st.markdown(f'<div style="font-size:12.5px;color:#cdd9ec;line-height:1.6;'
                                f'white-space:pre-line;max-height:330px;overflow:auto;">{body}</div>',
                                unsafe_allow_html=True)
                    st.markdown(f'<div style="margin-top:4px;"><a href="{it["link"]}" '
                                f'target="_blank">original ↗</a></div>', unsafe_allow_html=True)

with nc2:
    st.markdown("## ⚡ NSE & Futures Events <span class='s'>हिंदी · tap = open · live</span>",
                unsafe_allow_html=True)
    ev = load_events()
    if ev:
        # 🔴 LIVE event notification — current event, tap to read
        top = ev[0]
        stars = "".join(f'<span class="chip">{s}</span>' for s in top["stocks"])
        tick = (f'<span class="chip t">{top["tick"]}</span>' if top["tick"] and not top["stocks"] else "")
        st.markdown(
            f'<div class="livebox"><span class="pulse"></span>'
            f'<span class="lbt">⚡ LIVE</span>'
            f'<a class="lbtitle" href="{top["link"]}" target="_blank" '
            f'title="Open original">{stars}{tick} {_hi(top["title"])}</a></div>',
            unsafe_allow_html=True)
        if top["link"].startswith("http"):
            with st.expander("📖 इस इवेंट को पढ़ें (tap to read)"):
                bd = load_news_body(top["link"])
                st.markdown(f'<div style="font-size:12.5px;color:#cdd9ec;line-height:1.6;'
                            f'white-space:pre-line;max-height:330px;overflow:auto;">'
                            f'{bd or "Full text unavailable."}</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="margin-top:4px;"><a href="{top["link"]}" '
                            f'target="_blank">original ↗</a></div>', unsafe_allow_html=True)
        for it in ev[1:10]:
            hi_title = _hi(it["title"])
            stamps = "".join(f'<span class="chip">{s}</span>' for s in it["stocks"])
            tick = (f'<span class="chip t">{it["tick"]}</span>' if it["tick"] and not it["stocks"] else "")
            tm = it["published"]
            tms = tm.strftime("%H:%M") if hasattr(tm, "strftime") else str(tm)[:5]
            st.markdown(
                f'<div class="news-item"><div class="news-time">{tms}</div>'
                f'<div class="news-body">{stamps}{tick}'
                f'<div style="margin-top:2px;color:#cfe0ff;font-size:12.5px;">'
                f'<a href="{it["link"]}" target="_blank" style="color:#dbe7fb;'
                f'text-decoration:none;">{hi_title}</a></div>'
                f'<div class="news-src">{it["source"]}</div></div></div>', unsafe_allow_html=True)
            if it["link"].startswith("http"):
                with st.expander("📖 पढ़ें"):
                    bd = load_news_body(it["link"])
                    st.markdown(f'<div style="font-size:12.5px;color:#cdd9ec;line-height:1.6;'
                                f'white-space:pre-line;max-height:330px;overflow:auto;">'
                                f'{bd or "Full text unavailable."}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div style="margin-top:4px;"><a href="{it["link"]}" '
                                f'target="_blank">original ↗</a></div>', unsafe_allow_html=True)
    else:
        st.info("No events right now.")


st.markdown("---")
st.caption("MarketHub · Zone Scanner (Universe + multi-timeframe). Quotes: Yahoo/TradingView; "
           "flows: NSE/niftytrader; news & events: RSS. Not investment advice. "
           f"Today: {datetime.datetime.now().strftime('%d-%b-%Y %H:%M')} IST")
