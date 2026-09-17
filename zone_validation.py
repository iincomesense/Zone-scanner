# -*- coding: utf-8 -*-
"""zone_validation.py — अलग फाइल: scanned zones का validation (ZQS) + Streamlit section.

यह फाइल app.py के साथ repo के root में रखनी है.  यह **कोई नया data नहीं लाती** —
जो ज़ोन आपका `zone_core.py` (zscan के ज़रिए) पहले ही स्कैन कर चुका है, validation
ठीक उन्हीं पर लगता है.  दोनों modes support हैं:

  1) single-symbol (zscan.scan -> zones, dataframe, extra):
        import zone_validation as zv
        zv.render(df=dataframe, zones=zones, key="zv_single")

  2) universe (zscan.scan_universe_zones -> rows):
        zv.render_table(rows, key="zv_table")     # ek hi table, sirf A/B grade

Validation के चार नियम (17 महीने के असली बैकटेस्ट से, मूल 658 + फाइनल 79 trades):
    Q1 ज़ोन की चौड़ाई  <= 0.60 ATR   (मूल 25.1% -> 28.8%, p=0.007)
    Q2 ज़ोन की उम्र     >= 10 bars    (10+ : 31.1% / 53.8% ; 3-10: 18.3% / 14.9%)
    Q3 profit margin    >= 4 ATR      (Demand 35.2%)
    Q4 leg-out RVOL     >= 1.5x       (Supply 27.6% vs 22.5%; 3.0x -> 40%)
    ZQS = इनका जोड़ ; 3+ = A (trade), 2 = B (ऐच्छिक), 0-1 = C (छोड़ें)
Entry: ज़ोन की 30% गहराई पर limit (+6.0 / +4.4 अंक) ; SL: distal ; Target 1:2/1:3/1:5.
"""
from __future__ import annotations

import os
import shutil
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# backtest के final cuts (यही नियम बैकटेस्ट से निकले हैं)
# --------------------------------------------------------------------------
WIDTH_MAX_ATR = 0.60
MIN_AGE_BARS = 10
MIN_MARGIN_ATR = 4.0
MIN_DEP_RVOL = 1.5
ENTRY_DEPTH = 0.30                     # entry = proximal से ज़ोन की 30% गहराई
TARGET_RR = {"1:2": 2.0, "1:3": 3.0, "1:5": 5.0}
BACKTEST_WIN = {"A": "39.3% (मूल) / 55.6% (फाइनल)", "B": "34.0% (मूल)", "base": "25.1% / 49.4%"}

COLS_VIEW = ("#,ज़ोन,पैटर्न,श्रेणी,स्थिति,touches,बना (समय),उम्र (bars),चौड़ाई (ATR),Margin (ATR),"
             "Dep RVOL,Q1,Q2,Q3,Q4,ZQS,Grade,फ़ैसला,Entry (proximal),Entry (30% गहराई),SL (distal),"
             "TP 1:2,TP 1:3,TP 1:5,Risk (pts),Base weight,Touch penetration (ATR),नोट").split(",")
COLS_VIEW = [c for c in COLS_VIEW if c]


# ==========================================================================
# helpers — zone_core.py के बिल्कुल same formula (ATR = Wilder RMA, RVOL = TOD)
# ==========================================================================
def _cols(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    low = {str(c).lower(): c for c in df.columns}
    return {k: low.get(k) for k in ("open", "high", "low", "close", "volume")}


def _rma(series: np.ndarray, length: int) -> np.ndarray:
    n = len(series)
    out = np.full(n, np.nan)
    if n < length or length <= 0:
        return out
    out[length - 1] = np.mean(series[:length])
    for i in range(length, n):
        out[i] = (series[i] - out[i - 1]) / length + out[i - 1]
    return out


_PREP_CACHE: "Dict[Tuple[Any, ...], Tuple[np.ndarray, np.ndarray]]" = {}


def _prep_key(df: pd.DataFrame, atr_period: int, vol_period: int):
    try:
        last_close = float(df["close"].iloc[-1])
    except Exception:                                            # noqa: BLE001
        last_close = float("nan")
    return (id(df), len(df), atr_period, vol_period, round(last_close, 6))


def _prep_cached(df: pd.DataFrame, atr_period: int, vol_period: int):
    """ATR + TOD-RVOL ek hi (symbol, tf) frame par do baar na nikle."""
    key = _prep_key(df, atr_period, vol_period)
    hit = _PREP_CACHE.get(key)
    if hit is not None:
        return hit
    value = (_atr(df, atr_period), _rvol_tod(df, vol_period))
    if len(_PREP_CACHE) > 300:                                   # chhota memory footprint
        _PREP_CACHE.clear()
    _PREP_CACHE[key] = value
    return value


def _atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    c = _cols(df)
    if len(df) == 0 or c["high"] is None:
        return np.empty(0)
    h = df[c["high"]].to_numpy(float)
    l = df[c["low"]].to_numpy(float)
    cl = df[c["close"]].to_numpy(float)
    prev = np.empty(len(cl))
    prev[0] = cl[0]
    prev[1:] = cl[:-1]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    tr[0] = h[0] - l[0]
    return _rma(tr, period)


def _rvol_tod(df: pd.DataFrame, period: int = 20) -> np.ndarray:
    c = _cols(df)
    if len(df) == 0 or c["volume"] is None:
        return np.full(len(df), np.nan)
    vol = pd.Series(df[c["volume"]].to_numpy(float), index=df.index)
    if isinstance(df.index, pd.DatetimeIndex):
        slot = pd.Series(df.index.hour * 60 + df.index.minute, index=df.index)
    else:
        slot = pd.Series(0, index=df.index)
    base = vol.groupby(slot).transform(lambda x: x.shift(1).rolling(period, min_periods=5).mean())
    return (vol / base.replace(0.0, np.nan)).to_numpy(float)


def _ts_at(df: pd.DataFrame, i: int):
    if isinstance(df.index, pd.DatetimeIndex):
        return df.index[i]
    for name in ("date", "datetime", "time", "timestamp"):
        for c in df.columns:
            if str(c).lower() == name:
                return df[c].iloc[i]
    return i


def _fmt_ts(x) -> str:
    try:
        return pd.Timestamp(x).strftime("%d-%b-%Y %H:%M")
    except Exception:                                            # noqa: BLE001
        return str(x)


def _apply_params(df: pd.DataFrame, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """app के params से volume/ATR settings लें (अगर दिए गए हों) — वरना default."""
    cfg = {"volSmaPeriod": 20, "atrPeriod": 14}
    for k in cfg:
        if params and params.get(k):
            try:
                cfg[k] = int(params[k])
            except (TypeError, ValueError):
                pass
    return cfg


# ==========================================================================
# core: हर ज़ोन की grading
# ==========================================================================
def validate_zones(df: pd.DataFrame, zones: Iterable[Any], *, params: Optional[Dict[str, Any]] = None,
                   entry_depth: float = ENTRY_DEPTH, width_max_atr: float = WIDTH_MAX_ATR,
                   min_age_bars: int = MIN_AGE_BARS, min_margin_atr: float = MIN_MARGIN_ATR,
                   min_dep_rvol: float = MIN_DEP_RVOL, now_bar: Optional[int] = None,
                   symbol: str = "", tf: str = "") -> pd.DataFrame:
    """स्कैन किए हुए zones को grade करता है. एक पंक्ति = एक ज़ोन."""
    zones = list(zones or [])
    if not zones or df is None or len(df) == 0:
        return pd.DataFrame(columns=["Asset", "TF"] + COLS_VIEW + ["_zone"])
    c = _cols(df)
    o = df[c["open"]].to_numpy(float) if c["open"] else None
    h = df[c["high"]].to_numpy(float)
    l = df[c["low"]].to_numpy(float)
    cl = df[c["close"]].to_numpy(float)
    vol = df[c["volume"]].to_numpy(float) if c["volume"] is not None else None
    cfg = _apply_params(df, params)
    atr, rvol = _prep_cached(df, cfg["atrPeriod"], cfg["volSmaPeriod"])
    n = len(df)
    j_now = n - 1 if now_bar is None else int(now_bar)

    rows = []
    for k, z in enumerate(zones, start=1):
        i = int(getattr(z, "createdBarIndex", -1))
        prox = float(getattr(z, "proxVal", np.nan))
        dist = float(getattr(z, "distVal", np.nan))
        dem = bool(getattr(z, "isDemand", True))
        if not (np.isfinite(prox) and np.isfinite(dist)) or not (0 <= i < n):
            continue
        width = abs(prox - dist)
        av = float(atr[i])
        width_atr = width / av if (np.isfinite(av) and av > 0) else np.nan

        first_touch = None
        for j in range(i + 1, j_now + 1):
            if l[j] <= prox <= h[j]:
                first_touch = j
                break
        upto = first_touch if first_touch is not None else j_now
        age = int(upto - i)
        if upto > i:
            margin = (float(h[i:upto + 1].max()) - prox) if dem else (prox - float(l[i:upto + 1].min()))
            margin_atr = margin / av if (np.isfinite(av) and av > 0) else np.nan
        else:
            margin_atr = np.nan
        dv = float(rvol[i]) if np.isfinite(rvol[i]) else np.nan

        bc = max(1, int(getattr(z, "baseCount", 1) or 1))
        a, b = max(0, i - bc), i
        base_w = np.nan
        if b > a:
            rng = np.maximum(h[a:b] - l[a:b], 1e-12)
            loc = (cl[a:b] - l[a:b]) / rng
            side = loc if dem else (1.0 - loc)
            if vol is not None and np.nansum(vol[a:b]) > 0:
                base_w = float(np.nansum(vol[a:b] * side) / np.nansum(vol[a:b]))
            else:
                base_w = float(np.nanmean(side))

        pen = np.nan
        if first_touch is not None:
            pen = (float(prox - l[first_touch]) / av) if dem else (float(h[first_touch] - prox) / av)

        q1 = bool(np.isfinite(width_atr) and width_atr <= width_max_atr)
        q2 = bool(age >= min_age_bars)
        q3 = bool(np.isfinite(margin_atr) and margin_atr >= min_margin_atr)
        q4_known = bool(np.isfinite(dv))
        q4 = bool(q4_known and dv >= min_dep_rvol)
        score = int(q1) + int(q2) + int(q3) + int(q4)
        grade = "A" if score >= 3 else ("B" if score == 2 else "C")

        state = str(getattr(z, "state", "") or "")
        broken = "broken" in state.lower()
        verdict = ("✖ छोड़ें (ज़ोन टूट चुका)" if broken else
                   {"A": "✅ Trade (validation पास)", "B": "◐ B-grade (ऐच्छिक)", "C": "✖ छोड़ें"}[grade])

        entry_deep = prox - entry_depth * width * (1 if dem else -1)
        sl = dist
        risk = abs(entry_deep - sl)
        tps = {kk: (entry_deep + rr * risk if dem else entry_deep - rr * risk) for kk, rr in TARGET_RR.items()}

        notes = []
        if not q1 and np.isfinite(width_atr):
            notes.append(f"ज़ोन चौड़ा ({width_atr:.2f} ATR > {width_max_atr})")
        if not q2:
            notes.append(f"उम्र कम ({age} bars < {min_age_bars})")
        if not q3 and np.isfinite(margin_atr):
            notes.append(f"margin कम ({margin_atr:.1f} ATR)")
        if not q4_known:
            notes.append("volume उपलब्ध नहीं (RVOL नहीं निकला)")
        elif not q4:
            notes.append(f"leg-out वॉल्यूम कम ({dv:.2f}× < {min_dep_rvol})")
        if np.isfinite(pen) and pen >= 0.80:
            notes.append(f"touch गहरा ({pen:.2f} ATR) — डेटा में 5% win")
        if np.isfinite(base_w) and base_w >= 0.70:
            notes.append(f"base में {'खरीदारी' if dem else 'बिकवाली'} का वज़न {base_w:.2f} — मज़बूत sign")
        if np.isfinite(margin_atr) and margin_atr > 12:
            notes.append(f"पुराना ज़ोन — भाव {margin_atr:.0f} ATR दूर तक गया था")
        if first_touch is None:
            notes.append("अभी तक proximal तक भाव नहीं आया (pending)")
        if broken:
            notes.append(f"इंजन कह रहा है ज़ोन टूट चुका (state: {state})")

        rows.append({
            "Asset": str(symbol).replace(".NS", "") or "-",
            "TF": str(tf) or "-",
            "#": k,
            "ज़ोन": "Demand" if dem else "Supply",
            "पैटर्न": str(getattr(z, "patternType", "") or ""),
            "श्रेणी": str(getattr(z, "zoneCategory", "") or ""),
            "स्थिति": state or "-",
            "touches": int(getattr(z, "touchCount", 0) or 0),
            "बना (समय)": _fmt_ts(getattr(z, "timestamp", _ts_at(df, i))),
            "उम्र (bars)": age,
            "चौड़ाई (ATR)": round(width_atr, 2) if np.isfinite(width_atr) else np.nan,
            "Margin (ATR)": round(margin_atr, 2) if np.isfinite(margin_atr) else np.nan,
            "Dep RVOL": round(dv, 2) if np.isfinite(dv) else np.nan,
            "Q1": "✔" if q1 else "✘", "Q2": "✔" if q2 else "✘",
            "Q3": "✔" if q3 else "✘", "Q4": "✔" if q4 else ("?" if not q4_known else "✘"),
            "ZQS": score, "Grade": grade, "फ़ैसला": verdict,
            "Entry (proximal)": round(prox, 2),
            "Entry (30% गहराई)": round(entry_deep, 2),
            "SL (distal)": round(sl, 2),
            "TP 1:2": round(tps["1:2"], 2), "TP 1:3": round(tps["1:3"], 2), "TP 1:5": round(tps["1:5"], 2),
            "Risk (pts)": round(risk, 2),
            "Base weight": round(base_w, 2) if np.isfinite(base_w) else np.nan,
            "Touch penetration (ATR)": round(pen, 2) if np.isfinite(pen) else np.nan,
            "नोट": "; ".join(notes),
            "_zone": z, "_created_i": i, "_first_touch_i": first_touch,
            "_demand": dem, "_prox": prox, "_dist": dist,
        })
    return pd.DataFrame(rows)


def _num(x):
    """NaN/Inf -> None (streamlit/JSON ke liye saaf)."""
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    return round(xf, 4) if np.isfinite(xf) else None


def grade_badge(grade: Any) -> str:
    """app की अपनी HTML table में grade दिखाने के लिए रंगीन बैज (कोई streamlit नहीं चाहिए)."""
    g = str(grade or "-").strip().upper()[:1]
    colour = {"A": "#1ecb6b", "B": "#fbbf24", "C": "#ff4b5c"}.get(g, "#8ba1c0")
    return f'<span style="color:{colour};font-weight:800;">{g if g in "ABC" else "—"}</span>'


def row_fields(vrow: Any) -> Dict[str, Any]:
    """Validation की एक पंक्ति को zscan row के keys में बदलता है.

    Patched zscan.py इसे हर universe row में मिला देता है, जिससे app की मौजूदा
    table में ही grade/ZQS/entry-buffer/TP दिख सकें.
    """
    if vrow is None:
        return {}
    g = vrow.get if hasattr(vrow, "get") else (lambda k, d=None: d)
    return {
        "grade": g("Grade"),
        "zqs": int(g("ZQS") or 0),
        "q1": g("Q1"), "q2": g("Q2"), "q3": g("Q3"), "q4": g("Q4"),
        "age_bars": _num(g("उम्र (bars)")),
        "width_atr": _num(g("चौड़ाई (ATR)")),
        "margin_atr": _num(g("Margin (ATR)")),
        "dep_rvol": _num(g("Dep RVOL")),
        "entry_buffer": _num(g("Entry (30% गहराई)")),
        "sl_distal": _num(g("SL (distal)")),
        "tp2": _num(g("TP 1:2")), "tp3": _num(g("TP 1:3")), "tp5": _num(g("TP 1:5")),
        "risk_pts": _num(g("Risk (pts)")),
        "base_weight": _num(g("Base weight")),
        "touch_pen": _num(g("Touch penetration (ATR)")),
        "verdict": g("फ़ैसला"),
        "v_note": g("नोट"),
    }


def vdf_from_rows(rows: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    """उन rows से validation table बनाता है जो patched zscan.py ने भेजी हैं (दोबारा scan नहीं)."""
    recs = []
    for k, r in enumerate([x for x in (rows or []) if isinstance(x, dict) and x.get("grade")], start=1):
        recs.append({
            "Asset": str(r.get("symbol", "")).replace(".NS", "") or "-",
            "TF": str(r.get("tf", "")) or "-",
            "#": k,
            "ज़ोन": r.get("dir"), "पैटर्न": r.get("pattern"),
            "श्रेणी": "", "स्थिति": r.get("state", "-"), "touches": r.get("touches", 0),
            "बना (समय)": r.get("ts", ""),
            "उम्र (bars)": r.get("age_bars"), "चौड़ाई (ATR)": r.get("width_atr"),
            "Margin (ATR)": r.get("margin_atr"), "Dep RVOL": r.get("dep_rvol"),
            "Q1": r.get("q1"), "Q2": r.get("q2"), "Q3": r.get("q3"), "Q4": r.get("q4"),
            "ZQS": r.get("zqs"), "Grade": r.get("grade"), "फ़ैसला": r.get("verdict"),
            "Entry (proximal)": r.get("entry"), "Entry (30% गहराई)": r.get("entry_buffer"),
            "SL (distal)": r.get("sl_distal"),
            "TP 1:2": r.get("tp2"), "TP 1:3": r.get("tp3"), "TP 1:5": r.get("tp5"),
            "Risk (pts)": r.get("risk_pts"), "Base weight": r.get("base_weight"),
            "Touch penetration (ATR)": r.get("touch_pen"), "नोट": r.get("v_note", ""),
            "_zone": None,
        })
    return pd.DataFrame(recs, columns=["Asset", "TF"] + COLS_VIEW + ["_zone"])


def _broken_mask(vdf: pd.DataFrame) -> pd.Series:
    return vdf.get("स्थिति", pd.Series([""] * len(vdf), index=vdf.index)).astype(str).str.lower().str.contains("brok")


def validation_summary(vdf: pd.DataFrame) -> Dict[str, Any]:
    if vdf is None or vdf.empty:
        return dict(total=0, A=0, B=0, C=0, demand=0, supply=0, pending=0, deep_touch=0,
                    strong_base=0, broken=0, a_live=0)
    brk = _broken_mask(vdf)
    a = (vdf["Grade"] == "A")
    return dict(
        broken=int(brk.sum()),
        a_live=int((a & ~brk).sum()),
        total=len(vdf),
        A=int((vdf["Grade"] == "A").sum()), B=int((vdf["Grade"] == "B").sum()),
        C=int((vdf["Grade"] == "C").sum()),
        demand=int((vdf["ज़ोन"] == "Demand").sum()), supply=int((vdf["ज़ोन"] == "Supply").sum()),
        pending=int(vdf["नोट"].str.contains("pending", na=False).sum()),
        deep_touch=int((vdf["Touch penetration (ATR)"] >= 0.80).sum()),
        strong_base=int((vdf["Base weight"] >= 0.70).sum()),
    )


def _split_scan_result(result: Any) -> Tuple[List[Any], Optional[pd.DataFrame]]:
    """zscan.scan() जैसे return (zones, dataframe, extra) को संभालता है."""
    zones, df = [], None
    if isinstance(result, tuple):
        for part in result:
            if df is None and isinstance(part, pd.DataFrame) and {"open", "high", "low", "close"} <= {
                    str(x).lower() for x in part.columns}:
                df = part
            elif isinstance(part, (list, tuple)) and part and hasattr(part[0], "proxVal"):
                zones = list(part)
    elif isinstance(result, list):
        zones = list(result)
    return zones, df


# ==========================================================================
# adapters — app.py के दोनों modes
# ==========================================================================
def validate_symbol(symbol: str, tf: str, scan_fn: Callable[..., Any], *, params: Optional[Dict[str, Any]] = None,
                    **scan_kwargs) -> Tuple[pd.DataFrame, Optional[pd.DataFrame], List[Any]]:
    """एक symbol/TF की scan चलाकर उसी के zones validate करता है."""
    result = scan_fn(symbol, tf, **scan_kwargs)
    zones, df = _split_scan_result(result)
    return validate_zones(df, zones, params=params, symbol=symbol, tf=tf), df, zones


def validate_rows(rows: Iterable[Dict[str, Any]], scan_fn: Callable[..., Any], *,
                  params: Optional[Dict[str, Any]] = None, cap: int = 25,
                  progress: Optional[Callable[[int, int, str], None]] = None,
                  **scan_kwargs) -> pd.DataFrame:
    """Universe scan के rows (symbol/tf/pattern/entry...) को उन्हीं symbol/TF की
    scan से validate करता है.  अगर row के अंदर ही zone object हो (`_zone`/`zone`),
    तो दोबारा scan नहीं होता."""
    pairs: List[Tuple[str, str]] = []
    for r in rows or []:
        sym, tf = str(r.get("symbol", "")), str(r.get("tf", ""))
        if sym and tf and (sym, tf) not in pairs:
            pairs.append((sym, tf))
    pairs = pairs[:cap]
    out = []
    for n, (sym, tf) in enumerate(pairs, start=1):
        if progress:
            progress(n, len(pairs), f"{str(sym).replace('.NS','')} · {tf}")
        try:
            vdf, _df, _z = validate_symbol(sym, tf, scan_fn, params=params, **scan_kwargs)
        except Exception:                                        # noqa: BLE001
            continue
        if vdf is None or vdf.empty:
            continue
        want = {(str(r.get("pattern", "")), round(float(r["entry"]), 2))
                for r in (rows or []) if str(r.get("symbol")) == sym and str(r.get("tf")) == tf
                and r.get("entry") is not None}
        if want:
            vdf = vdf[[(str(p), round(float(e), 2)) in want
                       for p, e in zip(vdf["पैटर्न"], vdf["Entry (proximal)"])]]
        out.append(vdf)
    if not out:
        return pd.DataFrame(columns=["Asset", "TF"] + COLS_VIEW + ["_zone"])
    return pd.concat(out, ignore_index=True)


# ==========================================================================
# Streamlit section (अलग सेक्शन — सिर्फ़ validation ज़ोन दिखेंगे)
# ==========================================================================
def _df_show(df: pd.DataFrame) -> None:
    """streamlit के नए/पुराने दोनों version पर चलता है (warning-free)."""
    import streamlit as st
    try:
        st.dataframe(df, width="stretch", hide_index=True)          # streamlit >= 1.49
    except TypeError:
        st.dataframe(df, use_container_width=True, hide_index=True)  # पुराने versions


def _render_table(vdf: pd.DataFrame, cols: List[str]) -> None:
    show = [c for c in cols if c in vdf.columns]
    _df_show(vdf[show])


def _chart(df: pd.DataFrame, a_full: pd.DataFrame, key: str, bars_shown: int = 200) -> None:
    try:
        import plotly.graph_objects as go
    except ImportError:
        return
    import streamlit as st
    c = _cols(df)
    if c["open"] is None:
        return
    tail = df.iloc[-bars_shown:]
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=list(tail.index), open=tail[c["open"]], high=tail[c["high"]],
                                 low=tail[c["low"]], close=tail[c["close"]], name="price",
                                 increasing_line_color="#26a69a", decreasing_line_color="#ef5350"))
    for _, r in a_full.iterrows():
        fig.add_hrect(y0=min(r["SL (distal)"], r["Entry (proximal)"]),
                      y1=max(r["SL (distal)"], r["Entry (proximal)"]),
                      fillcolor=("rgba(38,166,154,0.22)" if r["ज़ोन"] == "Demand"
                                 else "rgba(239,83,80,0.22)"),
                      line_width=1, line_color="#888")
        for name, colr, dash in (("Entry (30% गहराई)", "#2196f3", "solid"),
                                 ("SL (distal)", "#f44336", "dot"), ("TP 1:3", "#4caf50", "dash")):
            fig.add_hline(y=r[name], line_color=colr, line_dash=dash, line_width=1,
                          annotation_text=f"{name} · {r['पैटर्न']}", annotation_font_size=10)
    fig.update_layout(height=430, template="plotly_dark", margin=dict(l=10, r=10, t=30, b=10),
                      xaxis_rangeslider_visible=False, showlegend=False,
                      title="✅ सिर्फ़ validation पास करने वाले ज़ोन अंकित")
    try:
        st.plotly_chart(fig, width="stretch", key=f"{key}_chart")
    except TypeError:
        st.plotly_chart(fig, use_container_width=True, key=f"{key}_chart")


def _rules_expander() -> None:
    import streamlit as st
    with st.expander("इन नियमों के पीछे के असली आँकड़े (17 महीने, Nifty-50, 658+79 trades)", expanded=False):
        st.markdown("""
- **चौड़ाई ≤ 0.60 ATR** — मूल इंजन 25.1% → 28.8% (n=396, p=0.007); चौड़ा ज़ोन (≥0.75) Demand पर सिर्फ़ **10.9%**
- **उम्र ≥ 10 bars** — 10+ पर 31.1% / 53.8%; 3–10 bars पर 18.3% / 14.9% (इसलिए पुराना ज़ोन ज़रूरी है, पर 10 से ज़्यादा करने पर फ़ायदा नहीं)
- **Profit margin ≥ 4 ATR** — Demand 35.2%; 2.5–4.0 ATR पर baseline से नीचे
- **leg-out RVOL ≥ 1.5×** — Supply 27.6% vs 22.5%; 3.0× पर **40.0%**
- **ZQS ≥ 3 (A-grade)** — मूल 25.1% → **39.3%** (n=234, expR +0.76) · फाइनल 49.4% → **55.6%**
- **Entry ज़ोन की 30% गहराई पर** — +6.0 / +4.4 अंक; entry सिर्फ़ ~1% ज़ोन में छूटती है
- **Base weight ≥ 0.70** (Demand में खरीदारी का वज़नदार हिस्सा) — 27.2% → **38.6%** (फाइनल 54.8% → 69.2%)
- **Touch penetration ≤ 0.30 ATR** — 42.9% (उम्र ≥10 के साथ 52.5%); **≥ 0.80 ATR पर सिर्फ़ 5% win**

⚠️ यह backtest (01-Apr-2025 → 30-Aug-2026) है — निवेश सलाह नहीं; live/paper पर पुष्टि करें।
""")


def _section_header(vdf: pd.DataFrame, key: str, multi: bool) -> Tuple[pd.DataFrame, List[str]]:
    import streamlit as st
    s = validation_summary(vdf)
    st.markdown("### 🧪 Zone Validation (सिर्फ़ scanned ज़ोन पर — कोई नया data नहीं)")
    st.caption("ऊपर के scanner ने जो ज़ोन निकाले, validation सिर्फ़ **उन्हीं** पर लगता है. नियम: चौड़ाई ≤ 0.60 ATR · "
               "उम्र ≥ 10 bars · margin ≥ 4 ATR · leg-out RVOL ≥ 1.5× (3+ = A-grade). "
               "Entry ज़ोन की 30% गहराई पर, SL distal. wins: " + BACKTEST_WIN["A"])
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("कुल ज़ोन", s["total"])
    c2.metric("✅ A-grade (live)", s["a_live"],
              help=f"ZQS ≥ 3 और ज़ोन ज़िंदा (Fresh/Tested). कुल A-grade {s['A']} — बैकटेस्ट " + BACKTEST_WIN["A"])
    c3.metric("◐ B-grade", s["B"], help="ZQS = 2 — " + BACKTEST_WIN["B"])
    c4.metric("🕒 pending", s["pending"], help="अभी proximal तक भाव नहीं आया")
    c5.metric("⚠️ गहरा touch", s["deep_touch"], help="penetration ≥ 0.80 ATR — डेटा में 5% win")
    if s["broken"]:
        st.caption(f"कुल {s['total']} ज़ोन में से {s['broken']} ज़ोन इंजन की नज़र में **Broken** (भाव distal पार कर गया) — "
                   f"ऊपर की गिनती live ज़ोन की है; नीचे फ़िल्टर से टूटे ज़ोन निकाले गए हैं।")

    f1, f2, f3, f4, f5 = st.columns(5)
    grade = f1.multiselect("Grade", ["A", "B", "C"], default=["A"], key=f"{key}_grade")
    ztype = f2.multiselect("ज़ोन प्रकार", ["Demand", "Supply"], default=["Demand", "Supply"], key=f"{key}_zt")
    pats = sorted({str(p) for p in vdf["पैटर्न"].dropna().unique() if str(p)})
    pat = f3.multiselect("पैटर्न", pats, default=pats, key=f"{key}_pat")
    only_a = f4.checkbox("सिर्फ़ A-grade (trade वाले)", value=bool(s["a_live"]), key=f"{key}_onlyA")
    hide_broken = f5.checkbox("टूटे ज़ोन हटाएँ", value=True, help="Broken ज़ोन यानी भाव distal से आर-पार जा चुका — trade नहीं",
                             key=f"{key}_hidebrk")

    view = vdf.copy()
    if hide_broken:
        view = view[~_broken_mask(view)]
    if only_a:
        view = view[view["Grade"] == "A"]
    else:
        view = view[view["Grade"].isin(grade or ["A", "B", "C"])]
    view = view[view["ज़ोन"].isin(ztype or ["Demand", "Supply"])]
    view = view[view["पैटर्न"].isin(pat or pats)]
    # live (Fresh/Tested) पहले, फिर naya/purana aur ZQS
    state_rank = view["स्थिति"].astype(str).str.lower().apply(lambda x: 0 if "fresh" in x else (1 if "tested" in x else 2))
    view = view.assign(_sr=state_rank).sort_values(["_sr", "Grade", "ZQS"], ascending=[True, True, False])
    view = view.drop(columns=["_sr"])
    cols = (["Asset", "TF"] if multi else []) + COLS_VIEW
    if view.empty and not vdf.empty:
        st.warning("फ़िल्टर के कारण कोई ज़ोन नहीं बचा — “टूटे ज़ोन हटाएँ” बंद करें या Grade में B जोड़कर देखें।")
    return view, cols


def render(df: Optional[pd.DataFrame] = None, zones: Optional[Iterable[Any]] = None, *,
           key: str = "zone_validation", params: Optional[Dict[str, Any]] = None,
           symbol: str = "", tf: str = "", show_chart: bool = True, bars_shown: int = 200) -> pd.DataFrame:
    """Single-symbol mode का validation section (app.py की 'Scanner' tab में)."""
    import streamlit as st
    if df is None or zones is None:
        st.info("Validation के लिए वही dataframe और zones चाहिए जो scanner ने दिए थे।")
        return pd.DataFrame()
    vdf = validate_zones(df, zones, params=params, symbol=symbol, tf=tf)
    if vdf.empty:
        st.info("इस symbol/TF पर कोई ज़ोन नहीं मिला — validation दिखाने के लिए कुछ नहीं है।")
        return vdf
    view, cols = _section_header(vdf, key, multi=False)
    a_full = vdf[vdf["Grade"] == "A"]

    st.markdown(f"#### ✅ Validation पास करने वाले ज़ोन ({int((view['Grade'] == 'A').sum())})")
    a_view = view[view["Grade"] == "A"]
    if a_view.empty:
        st.warning("इस समय कोई A-grade ज़ोन नहीं है. नीचे B/C वाले हिस्से खोलकर देखें.")
    else:
        _render_table(a_view, cols)
        st.download_button("⬇️ A-grade ज़ोन CSV", a_view.drop(columns=[c for c in a_view.columns
                                                                       if c.startswith("_")]).to_csv(index=False).encode("utf-8"),
                           file_name="validation_A_zones.csv", mime="text/csv", key=f"{key}_dl")
    with st.expander(f"◐ B-grade ({int((view['Grade'] == 'B').sum())}) — ऐच्छिक", expanded=False):
        bv = view[view["Grade"] == "B"]
        st.write("कोई B-grade नहीं.") if bv.empty else _render_table(bv, cols)
    with st.expander(f"✖ छोड़ने वाले ({int((view['Grade'] == 'C').sum())}) — वजह के साथ", expanded=False):
        cv = view[view["Grade"] == "C"]
        st.write("कोई नहीं.") if cv.empty else _render_table(cv, cols)
    if show_chart and not a_full.empty:
        st.markdown("#### ✅ सिर्फ़ validation पास करने वाले ज़ोन (चार्ट)")
        _chart(df, a_full, key, bars_shown)
    _rules_expander()
    return vdf


# ==========================================================================
# 🧪 Compact section — ek hi table, scanner table ke format me, sirf A / B
#   (koi metric box / chip / chart / alag A-B-C section nahi)
# ==========================================================================
_TF_HI = {
    "5m": "5 Min", "10m": "10 Min", "15m": "15 Min", "30m": "30 Min",
    "1h": "1 Hour", "2h": "2 Hours", "4h": "4 Hours", "6h": "6 Hours",
    "75m": "75 Min", "8h": "8 Hours", "10h": "10 Hours", "12h": "12 Hours",
    "20h": "20 Hours", "1D": "Daily", "1W": "Weekly", "1M": "Monthly",
    "2D": "2 Days", "3M": "3 Months",
}

TABLE_CSS = """<style>
.zwrap{overflow:auto; max-height:600px; border:1px solid #22304a; border-radius:12px; background:#0e1626; scrollbar-width:thin;}
.zhin{width:100%; border-collapse:collapse; font-size:12px; min-width:760px;}
.zhin thead th{position:sticky; top:0; z-index:3; text-align:left; color:#8ba1c0; font-size:10.5px; text-transform:uppercase; padding:7px 8px; border-bottom:1px solid #22304a; background:#0c1422; white-space:nowrap;}
.zhin td{padding:6px 8px; border-bottom:1px solid #18233a; color:#d9e5f6; white-space:nowrap;}
.zhin tr:hover{background:#131d31;}
.zhin a.sym{color:#eaf1fb; font-weight:700; text-decoration:none;}
.zhin a.sym:hover{color:#22d3ee; text-decoration:underline;}
.dot.dem{color:#1ecb6b;} .dot.sup{color:#ff4b5c;}
.st-fresh{color:#1ecb6b;} .st-tested{color:#22d3ee;} .st-broken{color:#8ba1c0;}
@media (max-width: 768px) {
    .zhin thead{display:none;}
    .zhin, .zhin tbody, .zhin tr, .zhin td{display:block; width:100%; min-width:100%;}
    .zhin tr{background:#0e1626; margin-bottom:12px; border-radius:12px; border:1px solid #22304a; padding:10px;}
    .zhin td{display:flex; justify-content:space-between; align-items:center; border-bottom:1px dashed #18233a; padding:8px 4px; text-align:right;}
    .zhin td::before{content:attr(data-label); color:#8ba1c0; font-weight:600; text-transform:uppercase; font-size:10px; text-align:left;}
    .zhin td:last-child{border-bottom:0;}
}
</style>"""


def _tf_hi(tf) -> str:
    return _TF_HI.get(str(tf), str(tf))


def _fmt2v(value) -> str:
    return "—" if value is None else f"{float(value):,.2f}"


def row_grade(row: Any) -> str:
    """Row ka grade letter (A/B/C) — na ho to ''."""
    try:
        g = row.get("grade") if hasattr(row, "get") else None
    except Exception:
        g = None
    g = str(g or "").strip().upper()[:1]
    return g if g in ("A", "B", "C") else ""


def _status_cell(value) -> str:
    value = "" if value is None else str(value)
    if value == "Waiting":
        return '<span style="color:#4f8cff;font-weight:700;">⏳ Waiting</span>'
    if value == "Triggered":
        return '<span style="color:#22c55e;font-weight:700;">✅ Triggered</span>'
    if value.startswith("Failed"):
        return f'<span style="color:#f87171;">✖ {value.replace("Failed-", "")}</span>'
    return value or "—"


def _tv_url(row: Dict[str, Any]) -> str:
    url = row.get("tv")
    if url:
        return str(url)
    sym = str(row.get("symbol", "")).replace(".NS", "")
    return f"https://www.tradingview.com/chart/?symbol=NSE:{sym}"


def rows_table_html(rows: Iterable[Dict[str, Any]]) -> str:
    """Scanner table (render_zone_table) ke bilkul same format me HTML table."""
    rows = list(rows or [])
    html = [
        '<div class="zwrap"><table class="zhin"><thead><tr>'
        '<th>Asset</th><th>TF</th><th>Direction</th><th>Pattern</th>'
        '<th>State</th><th>Entry</th><th>Distal</th><th>SL</th>'
        '<th>Risk %</th><th>Grade</th><th>ZQS</th><th>Entry (buffer)</th>'
        '<th>Status</th>'
        '</tr></thead><tbody>'
    ]
    for row in rows:
        sym = str(row.get("symbol", "")).replace(".NS", "")
        direction = str(row.get("dir") or "")
        dot = ('<span class="dot dem">●</span>' if direction.lower().startswith("dem")
               else '<span class="dot sup">●</span>')
        state = str(row.get("state") or "")
        entry = row.get("entry")
        zqs = row.get("zqs")
        html.append(
            '<tr>'
            f'<td data-label="Asset"><a class="sym" href="{_tv_url(row)}" target="_blank">📈 {sym}</a></td>'
            f'<td data-label="TF">{_tf_hi(row.get("tf"))}</td>'
            f'<td data-label="Direction">{dot} {direction}</td>'
            f'<td data-label="Pattern">{row.get("pattern") or "—"}</td>'
            f'<td data-label="State" class="st-{state.lower()}">{state or "—"}</td>'
            f'<td data-label="Entry">{_fmt2v(entry)}</td>'
            f'<td data-label="Distal">{_fmt2v(row.get("distal"))}</td>'
            f'<td data-label="SL">{_fmt2v(row.get("sl"))}</td>'
            f'<td data-label="Risk %">{_fmt2v(row.get("risk_pct"))}</td>'
            f'<td data-label="Grade">{grade_badge(row_grade(row))}</td>'
            f'<td data-label="ZQS">{zqs if zqs is not None else "—"}</td>'
            f'<td data-label="Entry (buffer)">{_fmt2v(row.get("entry_buffer"))}</td>'
            f'<td data-label="Status">{_status_cell(row.get("entry_status"))}</td>'
            '</tr>'
        )
    html.append("</tbody></table></div>")
    return "".join(html)


def pick_ab_rows(rows: Iterable[Dict[str, Any]], keep: Iterable[str] = ("A", "B")) -> list:
    """Sirf A/B grade rows — A pehle, phir entry ke qareeb wale pehle."""
    keep = {str(g).strip().upper()[:1] for g in (keep or ())}
    sel = [r for r in (rows or []) if row_grade(r) in keep]

    def _dist(row):
        last, entry = row.get("last"), row.get("entry")
        try:
            return abs(float(last) - float(entry)) / float(entry)
        except (TypeError, ValueError, ZeroDivisionError):
            return 9e9

    sel.sort(key=lambda r: (0 if row_grade(r) == "A" else 1, _dist(r)))
    return sel


def render_table(rows: Iterable[Dict[str, Any]], *, key: str = "zv_table",
                 keep: Iterable[str] = ("A", "B"),
                 title: str = "🧪 Zone Validation — Grade A / B",
                 show_title: bool = True) -> pd.DataFrame:
    """Streamlit section: ek hi table, scanner table ke format me, sirf A/B grade.

    Sirf wahi zones jo upar ke scanner (zone_core.scan_zones → zscan.py) ne diye.
    Koi naya data source nahi, koi metric box / chip / chart nahi.
    """
    import streamlit as st
    rows = list(rows or [])
    if not rows:
        st.info("Scanner table khaali hai — pehle upar scan chalaayein.")
        return pd.DataFrame()

    graded = [r for r in rows if row_grade(r)]
    if not graded:
        st.info("Grade ke liye `zone_validation.py` ke saath patched `zscan.py` chahiye "
                "(validation khud scanner ke zones par chalti hai).")
        return pd.DataFrame()

    sel = pick_ab_rows(graded, keep)
    if show_title:
        st.markdown(f"### {title}")
    if not sel:
        st.info("Abhi koi A / B grade zone nahi mila.")
        return vdf_from_rows(graded)

    st.markdown(TABLE_CSS + rows_table_html(sel), unsafe_allow_html=True)
    return vdf_from_rows(sel)


def render_universe(rows: Iterable[Dict[str, Any]], scan_fn: Callable[..., Any] = None, *,
                    key: str = "zone_validation_uni",
                    params: Optional[Dict[str, Any]] = None, cap: int = 25,
                    show_chart: bool = False, **scan_kwargs) -> pd.DataFrame:
    """Universe mode — ab wahi compact A/B table (koi doobara scan nahi).

    ``scan_fn`` sirf compatibility ke liye rakha gaya hai; validation pehle se
    scanner ke saath hi aa jaati hai (patched zscan.py), isliye use nahi hota.
    """
    return render_table(rows, key=key, title="🧪 Zone Validation — Grade A / B")


# ==========================================================================
# local test (repo में चलाने की ज़रूरत नहीं)
# ==========================================================================
# ==========================================================================
# एक-क्लिक integration:  python zone_validation.py --patch
#   यह zscan.py और app.py दोनों को इसी जगह patch कर देता है (backup .bak बनाकर).
#   दोबारा चलाने पर कुछ नहीं बिगड़ता.  zone_core.py में कुछ नहीं बदलता.
# ==========================================================================
_APP_IMPORT = "import zone_validation as zv   # zone validation section (अलग फाइल)"

_APP_VALROWS_INIT = """
_val_rows = []          # 🧪 Zone Validation section (tabs ke baad) ke liye rows
"""

_APP_VALROWS_UNI = """
        _val_rows = filtered_rows
"""

_APP_VALROWS_SINGLE = """
            _val_rows = rows
"""

_APP_END_BLOCK = """
# ---------------- 🧪 Zone Validation (tabs ke baad, alag section) ----------------
# Sirf wahi zones jo upar ke scanner (zone_core.scan_zones via zscan.py) ne diye.
# Ek hi table, scanner table ke format me -- sirf A aur B grade.
try:
    import zone_validation as zv
    zv.render_table(_val_rows, key="zv_table")
except Exception as _zv_ex:
    st.caption(f"Zone validation section: {_zv_ex}")
"""

# purane (ab hataye gaye) blocks — inhe file me milें to nikaal denge
_APP_OLD_UNIVERSE_BLOCK = """    # ---------------- \U0001F9EA Zone Validation (\u0905\u0932\u0917 \u0938\u0947\u0915\u094d\u0936\u0928) ----------------
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
"""

_APP_OLD_SINGLE_BLOCK = """            # ---------------- \U0001F9EA Zone Validation (\u0905\u0932\u0917 \u0938\u0947\u0915\u094d\u0936\u0928) ----------------
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
"""

_APP_ROW_BLOCK = """            try:
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

"""

_ZSCAN_IMPORT = """

try:                                    # validation layer (अलग फाइल, optional)
    import zone_validation as _zv
except Exception:                       # कभी भी app को न रोके
    _zv = None
"""

_ZSCAN_SCAN_BLOCK = """    try:
        validation = (
            _zv.validate_zones(df, zones, symbol=symbol, tf=timeframe)
            if _zv is not None
            else None
        )
    except Exception:
        validation = None

"""

_ZSCAN_SYMBOL_BLOCK = """                _vby = {}
                if _zv is not None:
                    try:
                        _vdf = _zv.validate_zones(df, zones, symbol=sym, tf=tf)
                        _vby = {id(_r["_zone"]): _r for _, _r in _vdf.iterrows()}
                    except Exception:
                        _vby = {}
"""


def patch_app_file(path: str = "app.py") -> list:
    """app.py में: import + दोनों modes में section + table के Grade/ZQS/buffer कॉलम."""
    if not os.path.exists(path):
        return [f"⚠️ {path} नहीं मिली"]
    src = open(path, encoding="utf-8").read()
    text, done = src, []

    if "import zone_validation as zv" not in text:
        anchor = "if _HERE not in sys.path:\n    sys.path.insert(0, _HERE)\n"
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + _APP_IMPORT + "\n", 1)
        else:
            text = text.replace("import streamlit as st", "import streamlit as st\n" + _APP_IMPORT, 1)
        done.append("import जोड़ा")

    # purane version ke andar-wale section hata do (upgrade)
    for _old, _label in ((_APP_OLD_UNIVERSE_BLOCK, "universe"), (_APP_OLD_SINGLE_BLOCK, "single")):
        if _old in text:
            text = text.replace(_old, "", 1)
            done.append(f"पुराना {_label} वाला section हटाया")

    if "_val_rows = []" not in text:
        anchor = "scanned_symbols = []\nopt_symbol = None\n_scan_ts = None\n"
        if anchor in text:
            text = text.replace(anchor, anchor + _APP_VALROWS_INIT, 1)
            done.append("_val_rows की शुरुआत")

    if "key=\"zv_table\"" not in text:
        anchor = "render_zone_table(filtered_rows, scan_time=_scan_ts)"
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + _APP_VALROWS_UNI.strip("\n"), 1)

        anchor = "render_zone_table(rows, scan_time=_scan_ts)"
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + _APP_VALROWS_SINGLE.strip("\n"), 1)

        text = text.rstrip() + "\n" + _APP_END_BLOCK
        done.append("tabs के बाद A/B table वाला section")

    if "zv.row_fields" not in text:
        anchor = "            ]\n            if active_only:"
        if anchor in text:
            text = text.replace(anchor, "            ]\n" + _APP_ROW_BLOCK + "            if active_only:", 1)
            done.append("single-symbol rows में grade/buffer")

    if "zv.grade_badge" not in text:
        hdr, cell = "'<th>Risk %</th><th>Status</th>'", "            f'<td data-label=\"Status\">'"
        if hdr in text and cell in text:
            text = text.replace(hdr, "'<th>Risk %</th><th>Grade</th><th>ZQS</th><th>Entry (buffer)</th><th>Status</th>'", 1)
            text = text.replace(cell, (
                "            f'<td data-label=\"Grade\">{zv.grade_badge(row.get(\"grade\"))}</td>'\n"
                "            f'<td data-label=\"ZQS\">{row.get(\"zqs\") if row.get(\"zqs\") is not None else \"—\"}</td>'\n"
                "            f'<td data-label=\"Entry (buffer)\">{_fmt2(row.get(\"entry_buffer\"))}</td>'\n"
            ) + cell, 1)
            done.append("table में Grade/ZQS/Entry (buffer) कॉलम")

    if text != src:
        shutil.copyfile(path, path + ".bak")
        open(path, "w", encoding="utf-8").write(text)
    return done


def patch_zscan_file(path: str = "zscan.py") -> list:
    """zscan.py में: import + extra['validation'] + हर universe row में validation fields."""
    if not os.path.exists(path):
        return [f"⚠️ {path} नहीं मिली"]
    src = open(path, encoding="utf-8").read()
    text, done = src, []

    if "import zone_validation as _zv" not in text:
        anchor = "import zone_core\nimport zdata\n"
        if anchor in text:
            text = text.replace(anchor, anchor + _ZSCAN_IMPORT, 1)
        else:
            text = text.replace("import pandas as pd", "import pandas as pd" + _ZSCAN_IMPORT, 1)
        done.append("import जोड़ा")

    if '"validation": validation' not in text and "validation = (" not in text:
        anchor = "    if recommended:\n        recommendation = zone_core.recommended_trade_setup(\n"
        if anchor in text:
            text = text.replace(anchor, _ZSCAN_SCAN_BLOCK + anchor, 1)
            text = text.replace('            {"recommended": recommendation, "roi": roi},',
                                '            {"recommended": recommendation, "roi": roi, "validation": validation},', 1)
            text = text.replace('        result = (zones, df, zone_core.backtest_summary(zones, df))',
                                '        _summary = zone_core.backtest_summary(zones, df)\n'
                                '        if isinstance(_summary, dict):\n'
                                '            _summary["validation"] = validation\n'
                                '        result = (zones, df, _summary)', 1)
            done.append('scan() → extra["validation"]')

    if "_vby" not in text:
        anchor = "                tv_url = _tv.chart_url(sym, tf)\n"
        if anchor in text:
            text = text.replace(anchor, anchor + _ZSCAN_SYMBOL_BLOCK, 1)
            done.append("_scan_symbol में validation")

    if "_zv.row_fields" not in text:
        a4 = ('                    output.append(\n'
              "                        {\n"
              '                            "tp_score": target_context.get("score"),')
        b4 = ('                    _row = {\n'
              '                            "tp_score": target_context.get("score"),')
        a5 = ('                            "mcap_cr": zdata.MCAP_CR.get(sym),\n'
              "                        }\n"
              "                    )")
        b5 = ('                            "mcap_cr": zdata.MCAP_CR.get(sym),\n'
              "                    }\n"
              "                    if _vby:\n"
              "                        _vr = _vby.get(id(zone))\n"
              "                        if _vr is not None:\n"
              "                            _row.update(_zv.row_fields(_vr))\n"
              "                    output.append(_row)")
        if a4 in text and a5 in text:
            text = text.replace(a4, b4, 1).replace(a5, b5, 1)
            done.append("universe rows में grade/zqs/entry_buffer/tp3 …")

    if text != src:
        shutil.copyfile(path, path + ".bak")
        open(path, "w", encoding="utf-8").write(text)
    return done


def _run_patch(args) -> int:
    """python zone_validation.py --patch [--dir REPO_DIR]"""
    base = args.dir or os.getcwd()
    if not os.path.exists(os.path.join(base, "app.py")) and os.path.exists(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")):
        base = os.path.dirname(os.path.abspath(__file__))
    print(f"repo folder: {base}\n")
    ok = True
    for name, fn in (("zscan.py", patch_zscan_file), ("app.py", patch_app_file)):
        path = os.path.join(base, name)
        try:
            done = fn(path)
        except Exception as exc:                                 # noqa: BLE001
            print(f"⚠️ {name}: {exc}")
            ok = False
            continue
        print(f"— {name}")
        for line in done:
            print(f"   • {line}")
        if done and done[0].startswith("⚠️"):
            ok = False
        print("   (backup .bak बना दिया गया)" if done and not done[0].startswith("⚠️") else "")
    print("\nअब चलाएँ:  streamlit run app.py")
    print("manual paste के लिए blocks: `python zone_validation.py --hooks`")
    return 0 if ok else 2


def _print_hooks() -> int:
    print("---- zscan.py : import के बाद ----" + _ZSCAN_IMPORT)
    print("---- zscan.py : scan() में `if recommended:` से ठीक पहले ----\n" + _ZSCAN_SCAN_BLOCK)
    print("---- zscan.py : _scan_symbol() में `tv_url = _tv.chart_url(sym, tf)` के बाद ----\n" + _ZSCAN_SYMBOL_BLOCK)
    print("---- zscan.py : row dict को _row बनाएँ + अंत में update ----\n"
          "                    _row = {  # output.append( की जगह\n"
          "                        ... पुराने keys वैसे ही ...\n"
          "                            \"mcap_cr\": zdata.MCAP_CR.get(sym),\n"
          "                    }\n"
          "                    if _vby:\n"
          "                        _vr = _vby.get(id(zone))\n"
          "                        if _vr is not None:\n"
          "                            _row.update(_zv.row_fields(_vr))\n"
          "                    output.append(_row)")
    print("---- app.py : sys.path block के बाद ----\n" + _APP_IMPORT)
    print("---- app.py : scanned_symbols/opt_symbol/_scan_ts के बाद ----" + _APP_VALROWS_INIT)
    print("---- app.py : `render_zone_table(filtered_rows, scan_time=_scan_ts)` के बाद ----"
          + _APP_VALROWS_UNI)
    print("---- app.py : `render_zone_table(rows, scan_time=_scan_ts)` के बाद ----"
          + _APP_VALROWS_SINGLE)
    print("---- app.py : file के सबसे अंत में (tabs के बाद) ----" + _APP_END_BLOCK)
    print("---- app.py : rows बनने के बाद ----\n" + _APP_ROW_BLOCK)
    print("---- app.py : table header + cells ----\n"
          "header: '<th>Risk %</th><th>Grade</th><th>ZQS</th><th>Entry (buffer)</th><th>Status</th>'\n"
          "row:    Grade/ZQS/Entry (buffer) के तीन <td> Status के ठीक पहले (देखें ZONE_VALIDATION_APP_STEPS.md)")
    return 0


def _demo() -> int:
    """Local test — kisi bhi machine par surakshit (data na mile to sirf help dikhata hai)."""
    try:
        import pickle
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import zone_core as ZC

        for cand in ("/home/user/data/wf/tfs_b.pkl", os.path.join(os.getcwd(), "tfs_b.pkl")):
            if not os.path.exists(cand):
                continue
            tfs = pickle.load(open(cand, "rb"))
            frame = tfs["4h"]["RELIANCE"]
            zones = ZC.scan_zones(frame)
            vdf = validate_zones(frame, zones, symbol="RELIANCE.NS", tf="4h")
            show = ["बना (समय)", "ज़ोन", "पैटर्न", "उम्र (bars)", "चौड़ाई (ATR)", "Margin (ATR)", "Dep RVOL",
                    "ZQS", "Grade", "Entry (30% गहराई)", "SL (distal)", "TP 1:3", "Base weight"]
            print(f"RELIANCE 4h: {len(zones)} zones -> validation table {vdf.shape}")
            print(vdf[show].to_string(index=False))
            print("summary:", validation_summary(vdf))
            return 0
    except Exception as exc:                                     # noqa: BLE001
        print(f"(local demo skip: {exc})")
    print("\nइस्तेमाल:")
    print("  python zone_validation.py --patch     # zscan.py aur app.py me section/hook jodta hai")
    print("  python zone_validation.py --hooks     # manual paste ke chhote blocks")
    print("  python zone_validation.py --demo      # sirf local test")
    return 0


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Zone validation layer (alag file)")
    ap.add_argument("--patch", action="store_true", help="zscan.py aur app.py ko isi jagah patch kare")
    ap.add_argument("--hooks", action="store_true", help="manual paste ke liye chhote blocks chhape")
    ap.add_argument("--dir", default=None, help="repo folder (default: current folder)")
    ap.add_argument("--demo", action="store_true", help="local test (default)")
    args = ap.parse_args()

    if args.hooks:
        raise SystemExit(_print_hooks())
    if args.patch:
        raise SystemExit(_run_patch(args))
    if args.demo:
        raise SystemExit(_demo())

    raise SystemExit(_demo())        # koi flag na ho to demo/help hi dikh jata hai
