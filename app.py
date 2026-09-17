# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime
import inspect
import os
import sys
from urllib.parse import quote

import requests
import streamlit as st


_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import zone_validation as zv   # zone validation section (अलग फाइल)


st.set_page_config(
    page_title="MarketHub · Zone Scanner",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "last_news_title" not in st.session_state:
    st.session_state.last_news_title = ""


st.markdown(
    """
<style>
:root{--bg:#0b1220; --line:#22304a; --txt:#e6edf7; --muted:#8ba1c0; --up:#1ecb6b; --down:#ff4b5c; --accent2:#22d3ee; --accent:#4f8cff;}
.stApp{background-color:var(--bg); color:var(--txt);}
[data-testid="stSidebar"]{background-color:#0d1524;}
[data-testid="stSidebar"] *{color:var(--txt);}
[data-testid="stHeader"]{background:rgba(11,18,32,.35);}
[data-baseweb="select"] *{background-color:#121a2b; color:#e6edf7;}

.stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: #0d1524; padding: 10px; border-radius: 12px; }
.stTabs [data-baseweb="tab"] { background-color: #162238; border-radius: 8px; padding: 10px 16px; color: #8ba1c0; font-weight: 600; }
.stTabs [aria-selected="true"] { background-color: #4f8cff !important; color: #ffffff !important; }

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
.zhin{width:100%; border-collapse:collapse; font-size:12px; min-width:760px;}
.zhin thead th{position:sticky; top:0; z-index:3; text-align:left; color:var(--muted); font-size:10.5px; text-transform:uppercase; padding:7px 8px; border-bottom:1px solid var(--line); background:#0c1422; white-space:nowrap;}
.zhin td{padding:6px 8px; border-bottom:1px solid #18233a; color:#d9e5f6; white-space:nowrap;}
.zhin tr:hover{background:#131d31;}
.zhin a.sym{color:#eaf1fb; font-weight:700; text-decoration:none;}
.zhin a.sym:hover{color:var(--accent2); text-decoration:underline;}
.dot.dem{color:var(--up);} .dot.sup{color:var(--down);}
.st-fresh{color:var(--up);} .st-tested{color:var(--accent2);} .st-broken{color:var(--muted);}

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
.fdrow{display:flex; gap:12px; flex-wrap:wrap; margin-bottom:15px;} .fdrow .fdbx{flex:1 1 120px;}

.news-item{display:flex; gap:9px; padding:7px 4px; border-bottom:1px solid #18233a;}
.news-time{color:var(--muted); font-size:11px; width:44px; flex:0 0 44px;}
.news-title{color:#dbeeef; font-size:13px; font-weight:600; text-decoration:none;}
.news-src{color:var(--muted); font-size:10px;}
.livebox{display:flex; gap:10px; align-items:center; background:linear-gradient(90deg,#12233f,#0e1626); border:1px solid rgba(255,75,92,.35); border-radius:12px; padding:8px 11px; margin:4px 0 10px;}
.pulse{display:inline-block; width:9px; height:9px; border-radius:50%; background:#ff4b5c; box-shadow:0 0 0 0 rgba(255,75,92,.7); animation:pulse 1.6s infinite;}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(255,75,92,.7);} 70%{box-shadow:0 0 0 8px rgba(255,75,92,0);} 100%{box-shadow:0 0 0 0 rgba(255,75,92,0);}}
.chip{font-size:11px; background:#152036; border:1px solid var(--line); color:#cfe0ff; border-radius:20px; padding:2px 9px; display:inline-block;}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600, show_spinner=False)
def _hi(text):
    if not text or not str(text).strip():
        return str(text)
    try:
        response = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": "auto",
                "tl": "hi",
                "dt": "t",
                "q": str(text),
            },
            timeout=5,
        )
        if response.status_code == 200:
            return "".join(x[0] for x in response.json()[0]).strip()
    except Exception:
        pass
    return str(text)


# Canonical timeframe options shown in the sidebar. The first group is the
# requested default set; the extra entries remain available for extension.
TIMEFRAME_OPTIONS = [
    "5m", "10m", "15m", "30m", "1h", "2h", "4h", "6h",
    "1D", "1W", "1M",
    "75m", "8h", "10h", "12h", "20h", "2D", "3M",
]
DEFAULT_SCAN_TFS = [
    "5m", "10m", "15m", "30m", "1h", "2h", "4h", "6h",
    "1D", "1W", "1M",
]
LIVE_TFS = {
    "5m", "10m", "15m", "30m", "1h", "2h", "4h", "6h",
    "75m", "8h", "10h", "12h", "20h",
}
STABLE_TFS = {"1D", "1W", "1M", "2D", "3M"}
TF_LABEL = {
    "5m": "5 Min",
    "10m": "10 Min",
    "15m": "15 Min",
    "30m": "30 Min",
    "1h": "1 Hour",
    "2h": "2 Hours",
    "4h": "4 Hours",
    "6h": "6 Hours",
    "75m": "75 Min",
    "8h": "8 Hours",
    "10h": "10 Hours",
    "12h": "12 Hours",
    "20h": "20 Hours",
    "1D": "Daily",
    "1W": "Weekly",
    "1M": "Monthly",
    "2D": "2 Days",
    "3M": "3 Months",
}


def _tf_hi(tf):
    return TF_LABEL.get(str(tf), str(tf))


# Scoring was removed from zone_core. Keep this compatibility value at zero
# while older zscan function signatures are being migrated.
SCORE_FILTER = 0
DEFAULT_ACCOUNT_CAPITAL = 25000.0


def _call_scanner(function, args=(), kwargs=None, account_capital=DEFAULT_ACCOUNT_CAPITAL):
    """Call old or new zscan APIs without reintroducing score filtering.

    Older scanners may not yet accept accountCapital. The argument is passed
    only when the function signature supports it. Unsupported legacy keyword
    arguments are also filtered safely.
    """
    kwargs = dict(kwargs or {})
    kwargs["min_score"] = SCORE_FILTER

    try:
        parameters = inspect.signature(function).parameters
        accepts_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in parameters.values()
        )

        if "accountCapital" in parameters or accepts_kwargs:
            kwargs["accountCapital"] = account_capital
        elif "account_capital" in parameters:
            kwargs["account_capital"] = account_capital

        if not accepts_kwargs:
            kwargs = {
                key: value
                for key, value in kwargs.items()
                if key in parameters
            }
    except (TypeError, ValueError):
        # If a wrapped function does not expose a signature, use the normal
        # legacy call. The score value is still zero.
        kwargs["min_score"] = SCORE_FILTER

    return function(*args, **kwargs)


@st.cache_data(ttl=30, show_spinner=False)
def load_market():
    try:
        import marketdata as md
        return md.fetch_all()
    except ImportError:
        return {}


@st.cache_data(ttl=30, show_spinner=False)
def load_sectors():
    try:
        import sectors as sc
        return sc.fetch_sectors()
    except ImportError:
        return []


@st.cache_data(ttl=30, show_spinner=False)
def load_news():
    try:
        import news as n
        return n.fetch_latest(15)
    except ImportError:
        return []


@st.cache_data(ttl=30, show_spinner=False)
def load_events():
    try:
        import events as e
        return e.fetch_events(10)
    except ImportError:
        return []


@st.cache_data(ttl=90, show_spinner=False)
def load_fiidii():
    try:
        import fiidii as f
        return f.fetch(6)
    except ImportError:
        return []


@st.cache_data(ttl=60, show_spinner=False)
def load_options(symbol):
    try:
        import options as o
        return o.live_oi(symbol), o.top_strikes(symbol, n=7), o.deep_links(symbol)
    except ImportError:
        return None, [], []


@st.cache_data(ttl=30, show_spinner=False)
def load_scan(
    symbol,
    timeframe,
    min_score,
    strict,
    lookback,
    recommended,
    account_capital=DEFAULT_ACCOUNT_CAPITAL,
):
    try:
        import zscan

        return _call_scanner(
            zscan.scan,
            args=(symbol, timeframe),
            kwargs={
                "strict": strict,
                "lookback_months": lookback,
                "recommended": recommended,
            },
            account_capital=account_capital,
        )
    except ImportError:
        return [], None, None


def _day_key():
    return datetime.datetime.now().strftime("%Y-%m-%d")


@st.cache_data(ttl=120, show_spinner=False)
def load_universe_live(
    tf_tuple,
    min_score,
    recommended,
    strict,
    eod_filter,
    symbols_tuple,
    eod_upper_pct=10.0,
    eod_lower_pct=10.0,
    account_capital=DEFAULT_ACCOUNT_CAPITAL,
):
    try:
        import zscan

        return _call_scanner(
            zscan.scan_universe_zones,
            kwargs={
                "timeframes": tf_tuple,
                "recommended": recommended,
                "strict": strict,
                "active_only": False,
                "eod_filter": eod_filter,
                "eod_upper_pct": eod_upper_pct,
                "eod_lower_pct": eod_lower_pct,
                "symbols": list(symbols_tuple) if symbols_tuple else None,
            },
            account_capital=account_capital,
        )
    except ImportError:
        return []


@st.cache_data(ttl=86400, show_spinner=False)
def load_universe_stable(
    tf_tuple,
    min_score,
    recommended,
    strict,
    eod_filter,
    symbols_tuple,
    day_key,
    eod_upper_pct=10.0,
    eod_lower_pct=10.0,
    account_capital=DEFAULT_ACCOUNT_CAPITAL,
):
    try:
        import zscan

        return _call_scanner(
            zscan.scan_universe_zones,
            kwargs={
                "timeframes": tf_tuple,
                "recommended": recommended,
                "strict": strict,
                "active_only": False,
                "eod_filter": eod_filter,
                "eod_upper_pct": eod_upper_pct,
                "eod_lower_pct": eod_lower_pct,
                "symbols": list(symbols_tuple) if symbols_tuple else None,
            },
            account_capital=account_capital,
        )
    except ImportError:
        return []


def _chg_html(c):
    if c is None:
        return '<span class="flat">—</span>'
    cls = "up" if c > 0 else ("dn" if c < 0 else "flat")
    return f'<span class="{cls}">{"+" if c > 0 else ""}{c:.2f}%</span>'


def fmt_cr(x):
    if x is None:
        return "—"
    x = float(x)
    cls = "up" if x > 0 else ("dn" if x < 0 else "flat")
    return f'<span class="{cls}">{x:+,.0f}</span>'


def _tv_chart_url(tv_sym, interval="1D"):
    return f'https://www.tradingview.com/chart/?symbol={quote(str(tv_sym))}&interval={interval}'


def render_board():
    data = load_market()
    if not data:
        return
    try:
        import marketdata as md

        html = [
            '<table class="board-table"><thead><tr>'
            '<th>Symbol</th><th>Last</th><th>Chg%</th><th>Chart</th>'
            '</tr></thead><tbody>'
        ]
        for group, tiles in md.TILES:
            html.append(
                f'<tr class="grp"><td colspan="4">{group.upper()}</td></tr>'
            )
            for tile in tiles:
                quote_data = data.get(tile["label"], {})
                price = (
                    f'{quote_data["price"]:,.2f}'
                    if quote_data.get("price") is not None
                    else "—"
                )
                tv_sym = (
                    md.tv_chart_symbol(tile["label"])
                    if hasattr(md, "tv_chart_symbol")
                    else tile["label"]
                )
                tv_url = _tv_chart_url(tv_sym)
                html.append(
                    f'<tr><td><a class="sym" href="{tv_url}" '
                    f'target="_blank">📈 {tile["label"]}</a></td>'
                    f'<td>{price}</td>'
                    f'<td>{_chg_html(quote_data.get("chg_pct"))}</td>'
                    f'<td class="tv"><a href="{tv_url}" '
                    f'target="_blank">➜</a></td></tr>'
                )
        html.append("</tbody></table>")
        st.markdown("".join(html), unsafe_allow_html=True)
    except Exception:
        pass


def render_sectors():
    sectors = load_sectors()
    if not sectors:
        return

    html = [
        '<table class="board-table"><thead><tr>'
        '<th>Index</th><th>Last</th><th>Chg%</th><th>Chart</th>'
        '</tr></thead><tbody>'
    ]
    for sector in sectors:
        cls, sign = (
            ("up", "+") if sector["chg_pct"] >= 0 else ("dn", "−")
        )
        tv_url = _tv_chart_url(sector.get("label"))
        html.append(
            f'<tr><td><a class="sym" href="{tv_url}" target="_blank">'
            f'📈 {sector["label"]}</a></td>'
            f'<td>{sector["price"]:,.1f}</td>'
            f'<td class="{cls}">{sign}{sector["chg_pct"]:.2f}%</td>'
            f'<td class="tv"><a href="{tv_url}" target="_blank">➜</a></td></tr>'
        )
    html.append("</tbody></table>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_fiidii():
    try:
        days = load_fiidii()
    except Exception:
        days = []

    if not days:
        st.caption("FII/DII data not reachable right now.")
        return

    today = days[0]
    date_value = today.get("date", "")
    date_text = (
        date_value.strftime("%d-%b")
        if hasattr(date_value, "strftime")
        else str(date_value)
    )
    st.markdown(
        f'<div class="fdrow">'
        f'<div class="fdbx"><div class="lab">FII / FPI {date_text}</div>'
        f'<div class="val">{fmt_cr(today.get("fii_net"))}</div>'
        f'<div class="sub">Buy {today.get("fii_buy", "—")} · '
        f'Sell {today.get("fii_sell", "—")} Cr</div></div>'
        f'<div class="fdbx"><div class="lab">DII {date_text}</div>'
        f'<div class="val">{fmt_cr(today.get("dii_net"))}</div>'
        f'<div class="sub">Buy {today.get("dii_buy", "—")} · '
        f'Sell {today.get("dii_sell", "—")} Cr</div></div>'
        f'<div class="fdbx"><div class="lab">NIFTY 50</div>'
        f'<div class="val">{today.get("nifty", "—")}</div>'
        f'<div class="sub">chg {fmt_cr(today.get("chg", ""))} pts</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def render_options(symbol):
    live, strikes, links = load_options(symbol)
    if live:
        st.markdown(
            f'<div class="fdrow">'
            f'<div class="fdbx"><div class="lab">CALL OI</div>'
            f'<div class="val">{live["call_oi"]:,.0f}</div></div>'
            f'<div class="fdbx"><div class="lab">PUT OI</div>'
            f'<div class="val">{live["put_oi"]:,.0f}</div></div>'
            f'<div class="fdbx"><div class="lab">PCR</div>'
            f'<div class="val">{live["pcr"]:.2f}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    links_html = "".join(
        f'<a class="chip" href="{link["url"]}" target="_blank" '
        f'style="text-decoration:none; margin-right:4px;">'
        f'↗ {link["label"]}</a>'
        for link in links
    )
    if links_html:
        st.markdown(
            f'<div style="margin-bottom:10px;">{links_html}</div>',
            unsafe_allow_html=True,
        )


def _fmt2(value):
    return "—" if value is None else f"{float(value):,.2f}"


def _status_badge(entry_status):
    entry_status = entry_status or ""
    if entry_status == "Waiting":
        return '<span style="color:#4f8cff;font-weight:700;">⏳ Waiting</span>'
    if entry_status == "Triggered":
        return '<span style="color:#22c55e;font-weight:700;">✅ Triggered</span>'
    if entry_status.startswith("Failed"):
        return (
            f'<span style="color:#f87171;">✖ '
            f'{entry_status.replace("Failed-", "")}</span>'
        )
    return entry_status or "—"


def render_zone_table(rows, scan_time=None):
    if not rows:
        return st.info("No valid zones found.")

    now = (scan_time or datetime.datetime.now()).strftime("%d-%b %H:%M")
    fresh_count = sum(1 for row in rows if row.get("state") == "Fresh")
    st.markdown(
        f'<div class="sumbar">'
        f'<span class="it"><span class="lbl">Scan ⟳</span> '
        f'<b>{now}</b></span><span class="sep">|</span>'
        f'<span class="it"><b>{len(rows)}</b> '
        f'<span class="lbl">Zones</span></span><span class="sep">|</span>'
        f'<span class="it"><b>{fresh_count}</b> '
        f'<span class="lbl">Fresh</span></span></div>',
        unsafe_allow_html=True,
    )

    html = [
        '<div class="zwrap"><table class="zhin"><thead><tr>'
        '<th>Asset</th><th>TF</th><th>Direction</th><th>Pattern</th>'
        '<th>State</th><th>Entry</th><th>Distal</th><th>SL</th>'
        '<th>Risk %</th><th>Grade</th><th>ZQS</th><th>Entry (buffer)</th><th>Status</th>'
        '</tr></thead><tbody>'
    ]

    for row in rows:
        display_symbol = row["symbol"].replace(".NS", "")
        dot = (
            '<span class="dot dem">●</span>'
            if row["dir"] == "Demand"
            else '<span class="dot sup">●</span>'
        )

        tv_url = row.get("tv")
        if not tv_url:
            try:
                import tv
                tv_url = tv.chart_url(row["symbol"], row["tf"])
            except ImportError:
                tv_url = (
                    "https://www.tradingview.com/chart/?symbol=NSE:"
                    + display_symbol
                )

        symbol_link = (
            f'<a class="sym" href="{tv_url}" target="_blank">'
            f'📈 {display_symbol}</a>'
        )
        state_class = str(row.get("state", "")).lower()
        html.append(
            f'<tr>'
            f'<td data-label="Asset">{symbol_link}</td>'
            f'<td data-label="TF">{_tf_hi(row["tf"])}</td>'
            f'<td data-label="Direction">{dot} {row["dir"]}</td>'
            f'<td data-label="Pattern">{row["pattern"]}</td>'
            f'<td data-label="State" class="st-{state_class}">'
            f'{row["state"]}</td>'
            f'<td data-label="Entry">{row["entry"]:,.2f}</td>'
            f'<td data-label="Distal">{_fmt2(row.get("distal"))}</td>'
            f'<td data-label="SL">{row["sl"]:,.2f}</td>'
            f'<td data-label="Risk %">{_fmt2(row.get("risk_pct"))}</td>'
            f'<td data-label="Grade">{zv.grade_badge(row.get("grade"))}</td>'
            f'<td data-label="ZQS">{row.get("zqs") if row.get("zqs") is not None else "—"}</td>'
            f'<td data-label="Entry (buffer)">{_fmt2(row.get("entry_buffer"))}</td>'
            f'<td data-label="Status">'
            f'{_status_badge(row.get("entry_status"))}</td>'
            f'</tr>'
        )

    html.append("</tbody></table></div>")
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

    selected_universe = (
        st.sidebar.multiselect("Stocks", _u_syms, default=list(_u_syms))
        or list(_u_syms)
    )
    universe_timeframes = (
        st.sidebar.multiselect(
            "Timeframes",
            TIMEFRAME_OPTIONS,
            default=DEFAULT_SCAN_TFS,
        )
        or list(DEFAULT_SCAN_TFS)
    )
    live_selected = [tf for tf in universe_timeframes if tf in LIVE_TFS]
    stable_selected = [tf for tf in universe_timeframes if tf in STABLE_TFS]
    symbol, timeframe = "RELIANCE.NS", "4h"
else:
    selected_universe = None
    universe_timeframes = []
    live_selected = []
    stable_selected = []
    symbol = st.sidebar.text_input("Symbol", value="RELIANCE.NS")
    timeframe = st.sidebar.selectbox(
        "Timeframe", TIMEFRAME_OPTIONS, index=TIMEFRAME_OPTIONS.index("1h")
    )

# EOD band settings apply to universe scans. Both sides are independently
# changeable; the default remains 10% above the daily high and 10% below the
# daily low.
eod_filter = st.sidebar.toggle("EOD band filter", value=True)
eod_upper_pct = st.sidebar.number_input(
    "EOD upper band %",
    min_value=0.0,
    max_value=100.0,
    value=10.0,
    step=1.0,
)
eod_lower_pct = st.sidebar.number_input(
    "EOD lower band %",
    min_value=0.0,
    max_value=100.0,
    value=10.0,
    step=1.0,
)

# Score filtering has been removed. This zero is retained only for old zscan
# function signatures and is never exposed as a UI setting.
min_score = SCORE_FILTER

account_capital = st.sidebar.number_input(
    "Account capital",
    min_value=1.0,
    value=float(DEFAULT_ACCOUNT_CAPITAL),
    step=1000.0,
    format="%.2f",
)
active_only = st.sidebar.toggle("Active zones only", value=True)
lookback = st.sidebar.selectbox("Lookback", ["All", "24", "12"])
lookback_months = None if lookback == "All" else int(lookback)

scanned_symbols = []
opt_symbol = None
_scan_ts = None


# ----------------- MAIN APP & TABS -----------------
st.markdown("## 📊 MarketHub App")

tab1, tab2, tab3 = st.tabs(["🎯 Scanner", "🌍 Markets & OI", "📰 Live News"])

with tab1:
    if scan_all:
        rows = []
        with st.spinner("Scanning..."):
            if live_selected:
                rows += load_universe_live(
                    tuple(live_selected),
                    min_score,
                    False,
                    False,
                    eod_filter,
                    tuple(selected_universe),
                    eod_upper_pct,
                    eod_lower_pct,
                    account_capital,
                )
            if stable_selected:
                rows += load_universe_stable(
                    tuple(stable_selected),
                    min_score,
                    False,
                    False,
                    eod_filter,
                    tuple(selected_universe),
                    _day_key(),
                    eod_upper_pct,
                    eod_lower_pct,
                    account_capital,
                )

        _scan_ts = datetime.datetime.now()

        col1, col2 = st.columns(2)
        direction_option = col1.selectbox(
            "Direction", ["All", "Demand", "Supply"], index=0
        )
        sort_option = col2.selectbox(
            "Sort", ["Near / Upcoming", "Asset"], index=0
        )

        filtered_rows = [
            row
            for row in rows
            if (
                not active_only
                or row.get("state") in ("Fresh", "Tested")
            )
            and (
                direction_option == "All"
                or row.get("dir") == direction_option
            )
        ]

        for row in filtered_rows:
            last_price = row.get("last")
            entry_price = row.get("entry")
            row["_dist"] = (
                abs(last_price - entry_price) / entry_price
                if last_price is not None and entry_price
                else 1e9
            )

        if sort_option == "Near / Upcoming":
            filtered_rows.sort(key=lambda row: row["_dist"])
        else:
            filtered_rows.sort(
                key=lambda row: (
                    row.get("symbol", ""),
                    row.get("tf", ""),
                )
            )

        seen = set()
        for row in filtered_rows:
            row_symbol = row.get("symbol")
            if row_symbol not in seen:
                seen.add(row_symbol)
                scanned_symbols.append(row_symbol)

        if filtered_rows:
            opt_symbol = filtered_rows[0].get("symbol")

        render_zone_table(filtered_rows, scan_time=_scan_ts)

    # ---------------- 🧪 Zone Validation (अलग सेक्शन) ----------------
    try:
        import zone_validation as zv
        import zscan
        zv.render_universe(
            filtered_rows,
            scan_fn=lambda s, tf: zscan.scan(
                s, tf,
                strict=False,
                lookback_months=lookback_months,
                recommended=False,
                min_score=SCORE_FILTER,
                accountCapital=account_capital,
            ),
            key="zv_universe",
            cap=20,
        )
    except Exception as _zv_ex:
        st.caption(f"Zone validation section: {_zv_ex}")

    else:
        try:
            zones, dataframe, extra = load_scan(
                symbol,
                timeframe,
                min_score,
                False,
                lookback_months,
                False,
                account_capital,
            )
            last_price = (
                float(dataframe["close"].iloc[-1])
                if dataframe is not None and len(dataframe)
                else None
            )

            try:
                import tv
                tv_url = tv.chart_url(symbol, timeframe)
            except ImportError:
                tv_url = (
                    "https://www.tradingview.com/chart/?symbol=NSE:"
                    + symbol.replace(".NS", "")
                )

            rows = [
                {
                    "symbol": symbol,
                    "tf": timeframe,
                    "pattern": zone.patternType,
                    "dir": "Demand" if zone.isDemand else "Supply",
                    "entry": round(zone.proxVal, 2),
                    "distal": round(zone.distVal, 2),
                    "sl": round(zone.slVal, 2),
                    "risk_pct": round(
                        getattr(zone, "riskPct", 0.0),
                        2,
                    ),
                    "state": zone.state,
                    "touches": zone.touchCount,
                    "last": last_price,
                    "tv": tv_url,
                }
                for zone in zones
            ]
            try:
                _vext = extra.get("validation") if isinstance(extra, dict) else None
                _vmap = {
                    id(_r["_zone"]): _r
                    for _, _r in (_vext.iterrows() if _vext is not None else [])
                }
            except Exception:
                _vmap = {}
            for _row, _zone in zip(rows, zones):
                _vr = _vmap.get(id(_zone))
                if _vr is not None:
                    _row.update(zv.row_fields(_vr))

            if active_only:
                rows = [
                    row
                    for row in rows
                    if row["state"] in ("Fresh", "Tested")
                ]

            _scan_ts = datetime.datetime.now()
            scanned_symbols = [symbol]
            opt_symbol = symbol
            render_zone_table(rows, scan_time=_scan_ts)

            # ---------------- 🧪 Zone Validation (अलग सेक्शन) ----------------
            try:
                import zone_validation as zv
                zv.render(
                    df=dataframe,
                    zones=zones,
                    key="zv_single",
                    symbol=symbol,
                    tf=timeframe,
                    params=None,
                )
            except Exception as _zv_ex:
                st.caption(f"Zone validation section: {_zv_ex}")

        except Exception as ex:
            st.error(f"Error: {ex}")

with tab2:
    st.markdown(
        '<div class="phead"><span class="t">🏛️ FII / DII (Today)</span></div>',
        unsafe_allow_html=True,
    )
    render_fiidii()

    st.markdown(
        '<div class="phead"><span class="t">🎯 Options OI</span></div>',
        unsafe_allow_html=True,
    )
    options_symbols = scanned_symbols or ([symbol] if symbol else [])
    if options_symbols:
        display_symbols = {
            item.replace(".NS", ""): item for item in options_symbols
        }
        display_names = list(display_symbols.keys())
        default_name = (opt_symbol or options_symbols[0]).replace(".NS", "")
        picked = st.selectbox(
            "Stock",
            display_names,
            index=(
                display_names.index(default_name)
                if default_name in display_names
                else 0
            ),
            label_visibility="collapsed",
        )
        render_options(display_symbols[picked])
    else:
        render_options(symbol)

    st.markdown(
        '<div class="phead"><span class="t">🌍 Global Indices & Commodities</span></div>',
        unsafe_allow_html=True,
    )
    render_board()

    st.markdown(
        '<div class="phead"><span class="t">🧱 Sector Indices</span></div>',
        unsafe_allow_html=True,
    )
    render_sectors()

with tab3:
    st.markdown(
        '<div class="phead"><span class="t">📰 Live Market Feed</span></div>',
        unsafe_allow_html=True,
    )
    news_items = load_news()
    if news_items:
        top = news_items[0]
        title_hi = _hi(top["title"])
        st.markdown(
            f'<div class="livebox"><span class="pulse"></span>'
            f'<span style="color:#f2f6ff; font-weight:700; font-size:13px;">'
            f'<a href="{top["link"]}" target="_blank" '
            f'style="color:inherit; text-decoration:none;">{title_hi}</a>'
            f'</span></div>',
            unsafe_allow_html=True,
        )

        if st.session_state.last_news_title != title_hi:
            st.toast(f"📰 ताज़ा खबर: {title_hi}", icon="🔥")
            st.session_state.last_news_title = title_hi

        for item in news_items[1:]:
            st.markdown(
                f'<div class="news-item">'
                f'<div class="news-time">{item["published"].strftime("%H:%M")}</div>'
                f'<div class="news-body"><a class="news-title" '
                f'href="{item["link"]}" target="_blank">'
                f'{_hi(item["title"])}</a><div>'
                f'<span class="chip t">{item["source"]}</span>'
                f'</div></div></div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption(
            "कोई ताज़ा समाचार उपलब्ध नहीं है। सुनिश्चित करें कि "
            "news.py में feedparser इंस्टॉल है।"
        )
