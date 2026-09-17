# -*- coding: utf-8 -*-
"""pages/Zone_Validation.py — 🧪 Zone Validation dashboard (Zone Scanner se ALAG page).

यह Page Streamlit के sidebar navigation में अपने-आप दिखता है (pages/ folder).
यहाँ सिर्फ़ वही ज़ोन आते हैं जो आपका `zone_core.scan_zones()` — `zscan.py` के ज़रिए —
पहले ही स्कैन करता है और जिनमें validation के cuts पास होते हैं (Grade A / B).

⚠️ कोई नया / अलग data source नहीं (ना Yahoo, ना कोई और feed) — वही scanner, वही data.
Table ठीक scanner table के format में है: Asset (chart link) · TF · Direction · Pattern ·
State · Entry · Distal · SL · Risk % · Grade · ZQS · Entry (buffer) · Status.
"""
from __future__ import annotations

import datetime
import os
import sys

import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))       # .../pages
_ROOT = os.path.dirname(_HERE)                           # repo root
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import zone_validation as zv


SCORE_FILTER = 0                       # scoring हट चुकी है — सिर्फ़ compatibility
DEFAULT_ACCOUNT_CAPITAL = 25000.0

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


st.set_page_config(
    page_title="Zone Validation",
    page_icon="🧪",
    layout="wide",
)


def _day_key() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# वही scanner (zscan.scan_universe_zones → zone_core.scan_zones) — कोई नया data नहीं
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=120, show_spinner=False)
def _scan_live(tfs, eod_filter, upper_pct, lower_pct, symbols, capital):
    import zscan
    return zscan.scan_universe_zones(
        timeframes=tuple(tfs),
        min_score=SCORE_FILTER,
        recommended=False,
        strict=False,
        active_only=False,
        eod_filter=eod_filter,
        eod_upper_pct=upper_pct,
        eod_lower_pct=lower_pct,
        symbols=list(symbols) if symbols else None,
        accountCapital=capital,
    )


@st.cache_data(ttl=86400, show_spinner=False)
def _scan_stable(tfs, eod_filter, upper_pct, lower_pct, symbols, day_key, capital):
    import zscan
    return zscan.scan_universe_zones(
        timeframes=tuple(tfs),
        min_score=SCORE_FILTER,
        recommended=False,
        strict=False,
        active_only=False,
        eod_filter=eod_filter,
        eod_upper_pct=upper_pct,
        eod_lower_pct=lower_pct,
        symbols=list(symbols) if symbols else None,
        accountCapital=capital,
    )


# --------------------------------------------------------------------------- #
# Sidebar — इस page की अपनी settings
# --------------------------------------------------------------------------- #
st.sidebar.markdown("## 🧪 Validation Settings")

try:
    import zdata
    _universe, _mcap, _ = zdata.build_universe()
except Exception:                                            # noqa: BLE001
    _universe = []

if _universe:
    selected_symbols = (
        st.sidebar.multiselect("Stocks", _universe, default=list(_universe))
        or list(_universe)
    )
else:
    selected_symbols = []

selected_tfs = (
    st.sidebar.multiselect("Timeframes", TIMEFRAME_OPTIONS, default=DEFAULT_SCAN_TFS)
    or list(DEFAULT_SCAN_TFS)
)
live_tfs = [tf for tf in selected_tfs if tf in LIVE_TFS]
stable_tfs = [tf for tf in selected_tfs if tf in STABLE_TFS]

eod_filter = st.sidebar.toggle("EOD band filter", value=True)
eod_upper_pct = st.sidebar.number_input(
    "EOD upper band %", min_value=0.0, max_value=100.0, value=10.0, step=1.0,
)
eod_lower_pct = st.sidebar.number_input(
    "EOD lower band %", min_value=0.0, max_value=100.0, value=10.0, step=1.0,
)
account_capital = st.sidebar.number_input(
    "Account capital",
    min_value=1.0,
    value=float(DEFAULT_ACCOUNT_CAPITAL),
    step=1000.0,
    format="%.2f",
)
active_only = st.sidebar.toggle("Active zones only", value=True)
show_b = st.sidebar.toggle("B-grade भी दिखाएँ", value=True)

if st.sidebar.button("🔄 दोबारा scan करें"):
    st.cache_data.clear()        # अगली बार scanner फिर से चलेगा (वही zscan/zone_core)

try:
    st.sidebar.page_link("app.py", label="🎯 Zone Scanner", icon="🎯")
except Exception:                                            # noqa: BLE001
    pass


# --------------------------------------------------------------------------- #
# Dashboard — सिर्फ़ validation पास करने वाले ज़ोन (Grade A / B)
# --------------------------------------------------------------------------- #
rows = []
with st.spinner("Scanner चल रहा है (zone_core.scan_zones)…"):
    if live_tfs:
        rows += _scan_live(
            tuple(live_tfs), eod_filter, eod_upper_pct, eod_lower_pct,
            tuple(selected_symbols), account_capital,
        )
    if stable_tfs:
        rows += _scan_stable(
            tuple(stable_tfs), eod_filter, eod_upper_pct, eod_lower_pct,
            tuple(selected_symbols), _day_key(), account_capital,
        )

if active_only:
    rows = [
        row for row in rows
        if str(row.get("state", "")) in ("Fresh", "Tested")
    ]

zv.render_table(
    rows,
    key="zv_page",
    keep=("A", "B") if show_b else ("A",),
    title="🧪 Zone Validation — Grade A / B" if show_b else "🧪 Zone Validation — Grade A",
)
