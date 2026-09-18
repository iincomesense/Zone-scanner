# -*- coding: utf-8 -*-
"""zone_validation.py — अलग फाइल: scanned zones का validation (ZQS) + Streamlit section.

यह फाइल app.py के साथ repo के root में रखनी है.  यह **कोई नया data नहीं लाती** —
जो ज़ोन आपका `zone_core.py` (zscan के ज़रिए) पहले ही स्कैन कर चुका है, validation
ठीक उन्हीं पर लगता है.  दोनों modes support हैं:

  1) single-symbol (zscan.scan -> zones, dataframe, extra):
        import zone_validation as zv
        zv.render(df=dataframe, zones=zones, key="zv_single")

  2) universe (zscan.scan_universe_zones -> rows):
        zv.render_universe(rows, scan_fn=lambda sym, tf: zscan.scan(sym, tf), key="zv_uni")

Validation के चार नियम (17 महीने के असली बैकटेस्ट से, मूल 658 + फाइनल 79 trades):
    Q1 ज़ोन की चौड़ाई  <= 0.60 ATR   (मूल 25.1% -> 28.8%, p=0.007)
    Q2 ज़ोन की उम्र     >= 10 bars    (10+ : 31.1% / 53.8% ; 3-10: 18.3% / 14.9%)
    Q3 profit margin    >= 4 ATR      (Demand 35.2%)
    Q4 leg-out RVOL     >= 1.5x       (Supply 27.6% vs 22.5%; 3.0x -> 40%)
    ZQS = इनका जोड़ ; 3+ = A (trade), 2 = B (ऐच्छिक), 0-1 = C (छोड़ें)
Entry: PROXIMAL line (आपकी सहमति 17-09-2026 — जैसा स्कैनर दिखाता है) ; SL: distal ;
Target 1:2/1:3/1:5. ज़ोन की 30% गहराई पर entry ऐच्छिक (साइडबार से) — बैकटेस्ट में
वह 1:3 = 40.6% / 1:5 = 29.3% था, proximal पर 1:3 = 34.5% / 1:5 = 18.8% (1 जन–30 अग 2026).

🎯 1:5 इंस्ट्यूशनल Playbook (18-09-2026, नया — v7):
    हर TF का अपना नियम, असली बैकटेस्ट से चुना (लक्ष्य: 1:5 RR पर हर TF 34%+ — 6/8 TF हासिल,
    2 घंटे भी ✅ 1:5 46%/39%). 15m · 30m · 1h · 2h · 4h · Daily अपने नियम; 6h पर 4h के और
    Weekly पर Daily के नियम (आपका फ़ैसला, टॉगल से बंद भी हो सकता है). Entry की गहराई भी
    playbook के हिसाब से (Daily/Weekly 30%, बाक़ी proximal). यह सिर्फ़ validation की तरफ़ है —
    zone_core.py के inputs नहीं बदले. तालिका: PB_TFS (नीचे).
"""
from __future__ import annotations

import os
import shutil
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# validation के चार नियम (सब असली बैकटेस्ट से) — None = नियम बंद
# आपकी सहमति (17-09-2026): चौड़ाई बंद · उम्र 5 · दूरी बंद · वॉल्यूम बंद · 4 में से 3
# --------------------------------------------------------------------------
WIDTH_MAX_ATR = None                   # बंद (पहले 0.60) — चालू होने पर 45% ज़ोन हटते थे
MIN_AGE_BARS = 5                       # 5 bars (पहले 10) — 3–10 bars वाले ज़ोन की win सिर्फ़ 18%
MIN_MARGIN_ATR = None                  # बंद (पहले 4.0) — सबसे सख़्त शर्त थी (55% ज़ोन हटाती थी)
MIN_DEP_RVOL = None                    # बंद (पहले 1.5) — बंद करने पर +70 ज़ोन, win सिर्फ़ −2.0%
MIN_PASS = 3                           # "4 में से 3 नियम ज़रूरी" (चालू नियमों में से)

DEEP_TOUCH_ATR = 0.80                  # इससे गहरा touch = कमज़ोर (बैकटेस्ट: win 5%)
HIDE_DEEP_TOUCH = True                 # ऐसे ज़ोन छिपाओ — win 26.7% → 35.6%
MARK_BASE_WEIGHT = 0.70                # Demand base में खरीदारी का वज़न — निशान (win 38.6% vs 19.0%)
MARK_SMALL_TFS = {"5m", "10m", "15m", "30m", "75m"}    # छोटा TF = कमज़ोर (win 18–26%)
MARK_DBD = True                        # DBD पैटर्न पर निशान (win 20.2%)

ENTRY_DEPTH = 0.0                      # 0 = proximal (आपकी सहमति) · 0.30 = ज़ोन की 30% गहराई
ENTRY_LABEL = "Entry (proximal)"       # table का column नाम (गहराई बदलने पर अपने-आप बदलता है)
TARGET_RR = {"1:2": 2.0, "1:3": 3.0, "1:5": 5.0}
# --------------------------------------------------------------------------
# 🎯 1:5 इंस्ट्यूशनल Playbook (18-09-2026) — हर TF का अपना नियम, असली बैकटेस्ट से चुना
#    लक्ष्य (आपका): 1:5 जोखिम-इनाम पर हर TF 34%+ — 6/8 TF हासिल (2 घंटे भी ✅); 6h/1W पर नमूना ही कम.
#    आपका फ़ैसला: 6 घंटे पर 4h के नियम · Weekly पर Daily के नियम चलें.
#    ज़ोन वही रहते हैं (zone_core.py) — यह सिर्फ़ validation की तरफ़ की जाँच है.
# --------------------------------------------------------------------------
PLAYBOOK_ON = True                     # चालू = table में सिर्फ़ playbook पास ज़ोन
PLAYBOOK_ALIAS = True                  # 6h → 4h के नियम · 1W → Daily के नियम
PLAYBOOK_HIDE_OTHER = False            # जिन TF का playbook नहीं (5m/10m/75m…) — डिफ़ॉल्ट: दिखें

PB_RULE_LABEL = {
    "touch_le50": "touch ≤0.50 ATR",
    "touch_le35": "touch ≤0.35 ATR",
    "room3": "जगह ≥3× जोखिम",
    "age10": "उम्र ≥10 bars",
    "dep05": "ताक़तवर निकास ≥0.5 ATR",
    "imbal": "imbalance (base पर void गैप)",
    "rejclose": "ज़ोन से बाहर बंद",
    "base1": "base 1 candle",
    "demand_only": "सिर्फ़ Demand",
}
PB_TF_ALIAS = {"6h": "4h", "1W": "1d"}     # आपका फ़ैसला — टॉगल बंद करने पर इनका playbook नहीं
PB_TFS = {
    "15m": dict(rules=("touch_le50", "room3", "demand_only"), depth=0.0, weak=False,
                bt="1:5 41.7% / 41.7% (n 12/12) · 1:3 50%"),
    "30m": dict(rules=("age10", "rejclose"), depth=0.0, weak=False,
                bt="1:5 40.0% / 40.0% (n 5/5) · 1:3 60%"),
    "1h":  dict(rules=("touch_le50", "rejclose"), depth=0.0, weak=False,
                bt="1:5 36.4% / 36.4% (n 44/107) · 1:3 52% / 50%"),
    "2h":  dict(rules=("touch_le50", "dep05"), depth=0.0, weak=False,
                bt="1:5 46.2% / 39.3% (n 13/28) · 1:3 69% / 54%"),
    "4h":  dict(rules=("touch_le35", "imbal", "room3"), depth=0.0, weak=False,
                bt="1:5 36.4% / 36.8% (n 22/57) · 1:3 46% / 49%"),
    "1d":  dict(rules=("touch_le35", "room3", "base1"), depth=0.30, weak=False,
                bt="1:5 40.0% / 40.0% (n 5/10) · 1:3 60% / 50%"),
}
PB_WEAK = {"6h", "1W"}             # alias वाले TF — नमूना कमज़ोर (चेतावनी दिखेगी)
# --------------------------------------------------------------------------
# 🏔️🕳️ HTF नियम (18-09-2026) — तीन हाइलाइट: **Z** Zone-in-Zone · **G** Gap · **P** Pivot-Gap
#   Z : LTF ज़ोन का base candle price-area ऊपर के TF के Demand/Supply ज़ोन से overlap (सही दिशा)
#   G : ऊपर के TF की दो candles का void गैप (सही दिशा) base area से overlap — जो pivot जोड़ी न हो
#   P : वही गैप जो swing pivot जोड़ी (pivot high–low) से बना हो
# जाँच हर ऊपर वाले TF पर चलती है (सीढ़ी: 30m→1h→2h→4h→1d→1W→1M …) और **जो नियम मिलते ही रुक जाती है**.
# कोई उम्र / "ताज़ा" शर्त नहीं (आपकी सहमति) · validation पहले, Z/G/P उसके बाद.
# असली बैकटेस्ट (निफ़्टी-50 · SL distal · ये नियम ज़रूरी करने पर):
#   1 जन–30 अग 2026, proximal — validation 34.5%/18.8% (n168) · Z 34.4%/12.5% (n32) ·
#   G 35.0%/19.7% (n159) · P 34.4%/17.2% (n94) · कोई एक 34.6%/19.5% (n161)
#   17 महीने, proximal — 36.1%/22.1% (n333) · Z 33.3%/18.1% (n72) · G 36.2%/22.4% (n314) ·
#   P 35.8%/22.3% (n180) · कोई एक 35.6%/22.1% (n319)
# 18-09-2026 (आपका सुधार): **तीनों में से कोई एक मिलना = ज़ोन validation पास (वैलिड)** और
#   **कोई भी न मिले = वैलिड नहीं** (लिस्ट में नहीं आएगा). हाइलाइट (चमकता Z/G/P + वह TF) वैसा ही रहता है.
#   असली बैकटेस्ट असर: नियम लागू करने पर ज़ोन 168 → 161 (−4%) और win लगभग वही (1:3 34.5% → 34.6%,
#   1:5 18.8% → 19.5%) — यानी सस्ता नियम है, ज़ोन कम नहीं होते.
# --------------------------------------------------------------------------
HTF_CHAIN = ["5m", "10m", "15m", "20m", "30m", "1h", "2h", "3h", "4h", "6h", "8h", "1d", "1W", "1M"]
HTF_ALIAS = {"8h": "1d", "6h": "4h"}         # NSE सेशन (6h15m) में ये कैंडल नहीं बनते → यही लेते हैं
HTF_SCAN_ENABLED = True                      # HTF ज़ोन/गैप उसी zscan → zone_core से (नया data source नहीं)
HTF_STOP_ON_FIRST = True                     # जो नियम मिलते ही ऊपर चढ़ना बंद
HTF_CHECKS = ("Z", "G", "P")                 # कौन-सी जाँचें चालू हैं
HTF_REQUIRE = "any"                          # "" = सिर्फ़ दिखाओ · "any" = कोई एक ज़रूरी (डिफ़ॉल्ट) · "Z"/"G"/"P"
HTF_LETTER = {"Z": "Zone-in-Zone", "G": "Gap", "P": "Pivot-Gap"}
HTF_COLOUR = {"Z": "#7ee787", "G": "#22d3ee", "P": "#fbbf24"}
TF_MINUTES = {"5m": 5, "10m": 10, "15m": 15, "20m": 20, "30m": 30, "75m": 75, "1h": 60,
              "2h": 120, "3h": 180, "4h": 240, "6h": 360, "8h": 480, "10h": 600,
              "12h": 720, "20h": 1200, "1d": 1440, "2d": 2880, "1W": 10080, "1M": 43200}

RULES = {"width_max_atr": WIDTH_MAX_ATR, "min_age_bars": MIN_AGE_BARS,
         "min_margin_atr": MIN_MARGIN_ATR, "min_dep_rvol": MIN_DEP_RVOL,
         "min_pass": MIN_PASS, "deep_touch_atr": DEEP_TOUCH_ATR,
         "hide_deep_touch": HIDE_DEEP_TOUCH, "mark_base_weight": MARK_BASE_WEIGHT,
         "mark_small_tfs": MARK_SMALL_TFS, "mark_dbd": MARK_DBD, "show_marks": True,
         "htf_checks": HTF_CHECKS, "htf_require": HTF_REQUIRE,
         "playbook_on": PLAYBOOK_ON, "playbook_alias": PLAYBOOK_ALIAS,
         "playbook_hide_other": PLAYBOOK_HIDE_OTHER,
         "playbook_per_row_depth": True, "entry_depth": ENTRY_DEPTH}
BACKTEST_WIN = {"A": "26.7% → 35.6% (गहरा touch हटाने पर)", "B": "30.0%", "base": "25.1% / 49.4%"}


RULE_HELP = {
    "width": "चौड़ाई ≤0.60 ATR — बंद करने पर ज़ोन 295 → 366 (win 34.6% → 32.3%)",
    "age":   "उम्र ≥5 bars — 3–10 bars वाले ज़ोन की win सिर्फ़ 18% थी",
    "margin": "दूरी ≥4 ATR — बंद करने पर ज़ोन 295 → 389 (win 34.6% → 31.6%)",
    "rvol":  "leg-out वॉल्यूम ≥1.5× — बंद करने पर ज़ोन 295 → 365 (win 34.6% → 32.6%)",
    "pass":  "4 में से कितने नियम ज़रूरी — 3 = साफ़ लिस्ट, 2 = 50% ज़्यादा ज़ोन",
    "deep":  "गहरा touch (≥0.80 ATR) — इन ज़ोन में win 5%; छिपाने पर win 26.7% → 35.6%",
    "marks": "निशान — DBD पैटर्न, छोटा TF, मज़बूत base (फ़िल्टर नहीं, सिर्फ़ जानकारी)",
    "htf":   "Z = Zone-in-Zone · G = Gap · P = Pivot-Gap — LTF ज़ोन के base candle price-area पर, "
             "हर ऊपर वाले TF पर जाँच (ज़ोन → गैप → pivot गैप), जो नियम मिलते ही रुक जाती है. "
             "**किसी एक का मिलना = ज़ोन वैलिड; कोई भी न मिले = वैलिड नहीं (लिस्ट से बाहर).** "
             "असली बैकटेस्ट असर: ज़ोन 168 → 161 (−4%) · 1:3 34.5% → 34.6% · 1:5 18.8% → 19.5% "
             "(17 महीने: 333 → 319 · 36.1% → 35.6%) — यानी बहुत कम ज़ोन हटते हैं.",
}

COLS_VIEW = ("#,ज़ोन,पैटर्न,श्रेणी,स्थिति,touches,बना (समय),उम्र (bars),चौड़ाई (ATR),Margin (ATR),"
             "Dep RVOL,जगह (×जोखिम),Q1,Q2,Q3,Q4,ZQS,Grade,निशान,HTF (Z·G·P),HTF मिला (TF),🎯 1:5 Playbook,फ़ैसला,"
             "Entry (proximal),Entry (proximal से गहराई),SL (distal),"
             "TP 1:2,TP 1:3,TP 1:5,Risk (pts),Base weight,Touch penetration (ATR),नोट").split(",")
COLS_VIEW = [c for c in COLS_VIEW if c]


# ==========================================================================
# नियम engine — grade, निशान और "कौन-सा ज़ोन दिखे" (दोबारा scan की ज़रूरत नहीं)
# ==========================================================================
def grade_of(q, rules: Optional[Dict[str, Any]] = None):
    """चार नियमों के नतीजे से grade. बंद नियम (None) अपने-आप पास माने जाते हैं."""
    r = dict(RULES)
    r.update(rules or {})
    active = sum(1 for x in q if x is not None)          # बंद नियम (None) गिनती में नहीं
    need = int(r.get("min_pass") or 0)
    need = min(need, active) if active else 0
    sc = int(sum(1 for x in q if x is True))
    if sc >= need:
        return "A", need
    if need and sc >= need - 1:
        return "B", need
    return "C", need


def _fnum(value):
    """None/NaN safe float."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def row_rules(row: Any, rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """एक row के कच्चे आँकड़ों (width/age/margin/rvol/pen) से Q1–Q4, grade और निशान."""
    r = dict(RULES)
    r.update(rules or {})
    g = row.get if hasattr(row, "get") else (lambda k, d=None: d)
    width, age = _fnum(g("width_atr")), _fnum(g("age_bars"))
    margin, rvol = _fnum(g("margin_atr")), _fnum(g("dep_rvol"))
    pen, base_w = _fnum(g("touch_pen")), _fnum(g("base_weight"))
    w_max, a_min = r.get("width_max_atr"), r.get("min_age_bars")
    m_min, v_min = r.get("min_margin_atr"), r.get("min_dep_rvol")

    q1 = None if w_max is None else bool(width is not None and width <= float(w_max))
    q2 = None if a_min in (None, 0) else bool(age is not None and age >= float(a_min))
    q3 = None if m_min is None else bool(margin is not None and margin >= float(m_min))
    q4 = None if v_min is None else bool(rvol is not None and rvol >= float(v_min))
    grade, need = grade_of((q1, q2, q3, q4), r)

    d_atr = float(r.get("deep_touch_atr") or DEEP_TOUCH_ATR)
    deep = bool(pen is not None and pen >= d_atr)
    marks = []
    if r.get("show_marks", True):
        if deep:
            marks.append("🔻 गहरा touch")
        if str(g("tf", "")) in (r.get("mark_small_tfs") or MARK_SMALL_TFS):
            marks.append("⏱️ छोटा TF")
        if r.get("mark_dbd", MARK_DBD) and str(g("pattern", "") or "").upper() == "DBD":
            marks.append("⚠️ DBD")
        bw = r.get("mark_base_weight", MARK_BASE_WEIGHT)
        if (str(g("dir", "") or "").lower().startswith("dem")
                and base_w is not None and bw is not None and base_w >= float(bw)):
            marks.append("⭐ मज़बूत base")
        flags = str(g("htf_flags", "") or "")
        if flags:
            marks.append("🏔️ " + flags + (" · " + str(g("htf_match_tf", "") or "") if g("htf_match_tf") else ""))
    htf_req = str(r.get("htf_require") or "").strip().upper()
    if htf_req in ("NONE", "NO"):
        htf_req = ""
    htf_z = bool(g("htf_z") is True)
    htf_g = bool(g("htf_g") is True)
    htf_p = bool(g("htf_p") is True)
    htf_hit = bool(htf_z or htf_g or htf_p)                  # कोई एक मिला?
    try:
        has_htf = any(k in row for k in ("htf_checked", "htf_ok", "htf_zone",
                                         "htf_z", "htf_g", "htf_p", "htf_flags"))
    except TypeError:
        has_htf = False
    _hc = g("htf_checked")                                   # None = जानकारी ही नहीं
    htf_known = bool(_hc is True) if _hc is not None else bool(has_htf)
    htf_pass = {"": True, "ANY": htf_hit,
                "Z": htf_z, "G": htf_g, "P": htf_p}.get(htf_req, True)
    if htf_req and not htf_known:
        htf_pass = True        # HTF जाँच चली ही नहीं (जैसे बंद) → शर्त लागू नहीं, वरना सब हट जाएँ
    # 🎯 1:5 playbook (जोड़ा गया 18-09-2026) — ज़ोन के उसी आँकड़ों पर
    _metrics = {"dep_atr": g("dep_atr"), "room_atr": g("room_atr"), "width_atr": width,
                "touch_pen": pen, "age_bars": age, "base_cnt": g("base_cnt"),
                "imbal": g("imbal"), "rej_close": g("rej_close"),
                "dir": g("dir") or g("ज़ोन") or g("direction")}
    _has_pb = any(_metrics.get(k) is not None for k in ("dep_atr", "room_atr", "base_cnt", "imbal"))
    if not _has_pb and g("pb_checked") is None:
        _pb = dict(pb_pass=None, pb_known=False, pb_weak=False, pb_depth=None, pb_fail=[],
                   pb_rules="", pb_bt="", pb_tf=pb_tf_key(g("tf")),
                   pb_note="playbook के लिए ज़रूरी आँकड़े इस row में नहीं हैं", pb_room=None)
    else:
        _pb = playbook_check(g("tf"), _metrics, alias=r.get("playbook_alias"),
                             depth=(r.get("playbook_depth")
                                    if not r.get("playbook_per_row_depth", True) else None))
    _pb = dict(_pb)
    _pb["pb_hide"] = bool(r.get("playbook_on", PLAYBOOK_ON)) and (
        (_pb.get("pb_pass") is False) or (_pb.get("pb_pass") is None and _pb.get("pb_known") and _pb.get("pb_rules") == ""
                                          and bool(r.get("playbook_hide_other", PLAYBOOK_HIDE_OTHER))))
    return {"q1": q1, "q2": q2, "q3": q3, "q4": q4,
            "score": int(sum(1 for x in (q1, q2, q3, q4) if x is True)),
            "grade": grade, "need": need, "marks": " · ".join(marks),
            "pb_pass": _pb.get("pb_pass"), "pb_known": _pb.get("pb_known", False),
            "pb_fail": _pb.get("pb_fail") or [], "pb_rules": _pb.get("pb_rules", ""),
            "pb_note": _pb.get("pb_note", ""), "pb_bt": _pb.get("pb_bt", ""),
            "pb_weak": _pb.get("pb_weak", False), "pb_depth": _pb.get("pb_depth"),
            "pb_room": _pb.get("pb_room"), "pb_tf": _pb.get("pb_tf", ""),
            "pb_hide": _pb.get("pb_hide", False),
            "htf_ok": htf_hit, "htf_pass": htf_pass, "htf_req": htf_req, "deep": deep,
            "hide": (bool(r.get("hide_deep_touch", HIDE_DEEP_TOUCH)) and deep)
                    or (bool(htf_req) and not htf_pass)}


def apply_rules(rows: Iterable[Dict[str, Any]], rules: Optional[Dict[str, Any]] = None):
    """Scanner की rows पर आपके चुने हुए नियम लगाता है (दोबारा scan नहीं).

    साइडबार में नियम बदलते ही table तुरंत बदल जाती है.
    """
    kept, hidden, hidden_htf, hidden_pb = [], 0, 0, 0
    for row in (rows or []):
        if not isinstance(row, dict):
            continue
        out = dict(row)
        if not any(k in out for k in ("age_bars", "width_atr", "margin_atr", "dep_rvol")):
            out.setdefault("marks", "")
            kept.append(out)                      # कच्चा डेटा नहीं → जैसा था वैसा
            continue
        info = row_rules(out, rules)
        out["grade"] = info["grade"]
        out["zqs"] = info["score"]
        out["q1"], out["q2"], out["q3"], out["q4"] = info["q1"], info["q2"], info["q3"], info["q4"]
        out["marks"] = info["marks"]
        out["deep_touch"] = info["deep"]
        out["htf_ok"] = info.get("htf_ok", out.get("htf_ok"))
        for _k in ("pb_pass", "pb_known", "pb_rules", "pb_note", "pb_bt", "pb_weak", "pb_depth", "pb_room", "pb_tf"):
            out[_k] = info.get(_k, out.get(_k))
        out["pb_fail"] = info.get("pb_fail") or []
        if info.get("pb_room") is not None:
            out["जगह (×जोखिम)"] = info["pb_room"]
        if info.get("pb_hide"):
            hidden_pb += 1
            continue
        if info["hide"]:
            if info.get("htf_req") and not info.get("htf_pass", True) and not info["deep"]:
                hidden_htf += 1
            else:
                hidden += 1
            continue
        kept.append(out)
    return kept, {"kept": len(kept), "hidden_deep": hidden, "hidden_htf": hidden_htf,
                  "hidden_playbook": hidden_pb}


def apply_entry(row: Any, depth: float = ENTRY_DEPTH, sl_mode: str = "distal") -> Dict[str, Any]:
    """एक row पर entry तरीक़ा लगाता है (दोबारा scan के बिना).

    depth = 0 → entry = proximal (स्कैनर जैसा) · depth = 0.30 → ज़ोन की 30% गहराई.
    SL = distal (आपका नियम, कोई ATR बफ़र नहीं) · Target 1:2 / 1:3 / 1:5.
    """
    out = dict(row)
    prox, dist = _fnum(row.get("entry")), _fnum(row.get("distal"))
    if prox is None or dist is None:
        return out
    dem = str(row.get("dir", "") or "").lower().startswith("dem")
    width = abs(prox - dist)
    ent = prox - float(depth or 0.0) * width * (1 if dem else -1)
    sl = dist
    risk = abs(ent - sl)
    out["entry"] = round(prox, 2)
    out["entry_buffer"] = round(ent, 2)
    out["sl"] = out["sl_distal"] = round(sl, 2)
    out["risk_pts"] = round(risk, 2)
    out["risk_pct"] = round(risk / ent * 100, 2) if ent else None
    for name, rr in TARGET_RR.items():
        out["tp" + name[-1]] = round(ent + rr * risk if dem else ent - rr * risk, 2)
    out["entry_mode"] = "proximal" if (depth or 0) <= 0 else f"{int(depth * 100)}% गहराई"
    return out


def entry_label(depth: float = ENTRY_DEPTH) -> str:
    """Table के column का नाम (proximal / 30% गहराई)."""
    return "Entry (proximal)" if (depth or 0) <= 0 else f"Entry ({int(depth * 100)}% गहराई)"


def rules_summary(rules: Optional[Dict[str, Any]] = None) -> str:
    """एक लाइन में चालू नियम (साइडबार / CLI के लिए)."""
    r = dict(RULES)
    r.update(rules or {})
    parts = []
    if r.get("width_max_atr") is not None:
        parts.append(f"चौड़ाई ≤{r['width_max_atr']} ATR")
    if r.get("min_age_bars") not in (None, 0):
        parts.append(f"उम्र ≥{int(r['min_age_bars'])} bars")
    if r.get("min_margin_atr") is not None:
        parts.append(f"दूरी ≥{r['min_margin_atr']} ATR")
    if r.get("min_dep_rvol") is not None:
        parts.append(f"RVOL ≥{r['min_dep_rvol']}×")
    txt = " · ".join(parts) if parts else "कोई नियम चालू नहीं (सब ज़ोन)"
    return f"{txt} — {len(parts)} चालू, {int(r.get('min_pass') or 0)} ज़रूरी"


# ==========================================================================
# 🎯 1:5 playbook engine — हर TF के नियम, ज़ोन के आँकड़ों पर (कोई नया data नहीं)
# ==========================================================================
_PB_NORM = {"1D": "1d", "1d": "1d", "1W": "1W", "1w": "1W", "1M": "1M", "1m": "1M"}


def pb_tf_key(tf: Any) -> str:
    """TF का नाम एक जैसा करता है (1D → 1d, 1W → 1W)."""
    t = str(tf or "").strip()
    if t in _PB_NORM:
        return _PB_NORM[t]
    tl = t.lower()
    if tl.endswith("m") or tl.endswith("h"):
        return tl
    return t


def playbook_for(tf: Any, alias: Optional[bool] = None) -> Optional[Dict[str, Any]]:
    """उस TF का 1:5 playbook. न मिले तो None (5m/10m जैसे TF)."""
    key = pb_tf_key(tf)
    pb = PB_TFS.get(key)
    if pb is None and bool(PLAYBOOK_ALIAS if alias is None else alias):
        alt = PB_TF_ALIAS.get(key)
        if alt:
            pb = PB_TFS.get(alt)
    return pb


def playbook_check(tf: Any, m: Any, alias: Optional[bool] = None,
                   depth: Optional[float] = None) -> Dict[str, Any]:
    """एक ज़ोन के आँकड़ों पर उस TF का playbook लगाता है.

    लौटाता है: pb_pass (True/False/None) · pb_fail (छूटे नियम) · pb_note · pb_depth · pb_weak.
    जिन नियमों का आँकड़ा ही नहीं (जैसे touch अभी हुआ ही नहीं) वे "अभी लागू नहीं" माने जाते हैं —
    इसलिए ताज़ा (pending) ज़ोन छिपते नहीं, पर उन पर शर्त लिखी रहती है.
    """
    pb = playbook_for(tf, alias)
    g = m.get if hasattr(m, "get") else (lambda k, d=None: d)
    if pb is None:
        return dict(pb_pass=None, pb_known=True, pb_weak=False, pb_depth=None, pb_fail=[],
                    pb_rules="", pb_bt="", pb_tf=pb_tf_key(tf),
                    pb_note="इस TF का 1:5 playbook नहीं — इन छोटे TF पर बैकटेस्ट नमूना नहीं बना")

    def _b(v):
        if v is None:
            return None
        if isinstance(v, float) and not np.isfinite(v):
            return None
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes")
        try:
            return bool(v)
        except Exception:                                        # noqa: BLE001
            return None

    dep = _fnum(g("dep_atr"))
    room_atr, width = _fnum(g("room_atr")), _fnum(g("width_atr"))
    pen, age, base_cnt = _fnum(g("touch_pen")), _fnum(g("age_bars")), _fnum(g("base_cnt"))
    imbal, rej = _b(g("imbal")), _b(g("rej_close"))
    txt = str(g("dir", "") or g("ज़ोन", "") or g("direction", "") or "").lower()
    dem = txt.startswith("dem")

    d_use = float(pb.get("depth") or 0.0) if depth is None else float(depth or 0.0)
    rr = None
    if room_atr is not None and width:
        rr = (float(room_atr) / float(width)) / max(1e-9, 1.0 - d_use)

    tests = {
        "touch_le50": None if pen is None else bool(pen <= 0.50),
        "touch_le35": None if pen is None else bool(pen <= 0.35),
        "room3": None if rr is None else bool(rr >= 3.0),
        "age10": None if age is None else bool(age >= 10),
        "dep05": None if dep is None else bool(dep >= 0.5),
        "imbal": imbal,
        "rejclose": rej,
        "base1": None if base_cnt is None else bool(base_cnt <= 1),
        "demand_only": bool(dem),
    }
    need = list(pb.get("rules") or ())
    unknown = [k for k in need if tests.get(k) is None]
    failed = [k for k in need if tests.get(k) is False]
    known = len(unknown) < len(need)
    note = ""
    if unknown and any(k.startswith("touch") or k == "rejclose" for k in unknown):
        note = "touch अभी नहीं हुआ — भाव ज़ोन में घुसे तो यही शर्त लागू होगी"
    _ak = pb_tf_key(tf)
    _weak = bool(pb.get("weak")) or (_ak in PB_WEAK)
    if _weak:
        note = (note + " · " if note else "") + ("इस TF पर नमूना कमज़ोर (भरोसा कम, सावधानी रखें)"
                                                 if _ak in PB_WEAK else "नमूना कमज़ोर")
    return dict(pb_pass=(None if not known else not failed), pb_known=known,
                pb_weak=_weak, pb_depth=d_use,
                pb_fail=[PB_RULE_LABEL.get(k, k) for k in failed],
                pb_rules=" + ".join(PB_RULE_LABEL.get(k, k) for k in need),
                pb_bt=str(pb.get("bt") or ""), pb_tf=pb_tf_key(tf), pb_note=note,
                pb_room=round(rr, 2) if rr is not None else None)


def playbook_table_md() -> str:
    """साइडबार के लिए छोटी तालिका — हर TF का नियम + असली बैकटेस्ट."""
    lines = ["| TF | Entry | 1:5 का नियम | असली बैकटेस्ट |", "|---|---|---|---|"]
    for tf, pb in PB_TFS.items():
        nm = {"1d": "Daily", "1W": "Weekly"}.get(tf, tf)
        dep = "proximal" if not pb.get("depth") else f"{int(pb['depth'] * 100)}% गहराई"
        rules = " + ".join(PB_RULE_LABEL.get(k, k) for k in pb.get("rules") or ())
        if pb.get("weak"):
            rules += " ⚠️"
        lines.append(f"| {nm} | {dep} | {rules} | {pb.get('bt', '')} |")
    lines.append("| 6h · Weekly | — | जैसा आपने चुना: 6h पर 4h के नियम · Weekly पर Daily के नियम | नमूना कमज़ोर ⚠️ |")
    lines.append("| 5m · 10m · 75m … | — | playbook नहीं (बैकटेस्ट नमूना नहीं) | — |")
    return "\n".join(lines)


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

# ==========================================================================
# 🏔️🕳️ HTF इंजन — सीढ़ी पर एक-एक करके जाँच, नियम मिलते ही रुक जाओ
# ==========================================================================
_HTF_CACHE = {}
_HTF_LOCK = None
_HTF_TLS = None


def _htf_tls():
    global _HTF_TLS
    if _HTF_TLS is None:
        import threading
        _HTF_TLS = threading.local()
    return _HTF_TLS


def htf_busy() -> bool:
    """HTF scan के अंदर चल रहे हैं? (वहाँ validation दोबारा HTF न खींचे)"""
    return int(getattr(_htf_tls(), "depth", 0) or 0) > 0


def _htf_lock():
    global _HTF_LOCK
    if _HTF_LOCK is None:
        import threading
        _HTF_LOCK = threading.Lock()
    return _HTF_LOCK


def _tf_key(tf) -> str:
    """TF का नाम एक जैसा करो ('1D' · 'D' · 'daily' → '1d'; '1W' → '1W'; '1M' → '1M')."""
    t = str(tf or "").strip()
    low = t.lower()
    if low in ("1d", "d", "day", "daily"):
        return "1d"
    if low in ("1w", "w", "week", "weekly"):
        return "1W"
    if low in ("1m", "m", "month", "monthly"):
        return "1M"
    return low


def htf_ladder(tf):
    """LTF से ऊपर के सारे TF उस क्रम में — (tf, नोट) की सूची. नियम मिलते ही आगे नहीं देखा जाता."""
    key = _tf_key(tf)
    mins = TF_MINUTES.get(key)
    if not mins:
        return []
    out, seen = [], set()
    for t in HTF_CHAIN:
        if TF_MINUTES.get(t, 0) <= mins:
            continue
        real = HTF_ALIAS.get(t, t)
        note = f"{t} नहीं बनता → {real}" if t in HTF_ALIAS else ""
        if real in seen or real == key:
            continue
        seen.add(real)
        out.append((real, note))
    return out


def htf_zones_for(symbol, htf_tf):
    """उसी zscan → zone_core से उस TF के ज़ोन (cache में)."""
    if not (HTF_SCAN_ENABLED and symbol and htf_tf):
        return None, None
    key = ("z", str(symbol), str(htf_tf))
    with _htf_lock():
        if key in _HTF_CACHE:
            return _HTF_CACHE[key]
    tls = _htf_tls()
    tls.depth = int(getattr(tls, "depth", 0) or 0) + 1     # अंदर वाली validation में HTF off
    try:
        import zscan
        zones, df, _ = zscan.scan(str(symbol), str(htf_tf), min_score=0)
    except Exception:                                       # noqa: BLE001
        zones, df = [], None
    finally:
        tls.depth = int(getattr(tls, "depth", 0) or 0) - 1
    with _htf_lock():
        _HTF_CACHE[key] = (zones, df)
    return zones, df


def _htf_gap_arrays(dfH):
    """void गैप (असली खाली जगह) + pivot जोड़ी — सब vector में (तेज़)."""
    o = dfH["open"].to_numpy(float)
    h = dfH["high"].to_numpy(float)
    l = dfH["low"].to_numpy(float)
    c = dfH["close"].to_numpy(float)
    n = len(c)
    if n < 3:
        return None
    isH = np.zeros(n, bool)
    isL = np.zeros(n, bool)
    isH[1:-1] = (h[1:-1] > h[:-2]) & (h[1:-1] >= h[2:])
    isL[1:-1] = (l[1:-1] < l[:-2]) & (l[1:-1] <= l[2:])
    pivH = isH.copy()
    pivL = isL.copy()
    pivH[:-1] |= isH[1:]
    pivH[1:] |= isH[:-1]
    pivL[:-1] |= isL[1:]
    pivL[1:] |= isL[:-1]
    o1, c0 = o[1:], c[:-1]
    h0, l0 = h[:-1], l[:-1]
    up = o1 > h0                       # bullish void गैप: candle-2 का Open > candle-1 का High
    dn = o1 < l0                       # bearish void गैप
    nan = np.nan
    vlo = np.where(up, h0, np.where(dn, o1, nan))
    vhi = np.where(up, o1, np.where(dn, l0, nan))
    pu = up & pivL[:-1] & pivH[1:]     # bullish pivot जोड़ी: candle-1 = pivot low, candle-2 = pivot high
    pd = dn & pivH[:-1] & pivL[1:]     # bearish pivot जोड़ी: candle-1 = pivot high, candle-2 = pivot low
    return dict(idx1=np.arange(1, n), up=up, dn=dn, pu=pu, pd=pd, vlo=vlo, vhi=vhi)


def htf_data_for(symbol, htf_tf):
    """ज़ोन + गैप सारणी + बंद होने का समय — सब एक बार में (cache)."""
    key = ("d", str(symbol), str(htf_tf))
    with _htf_lock():
        if key in _HTF_CACHE:
            return _HTF_CACHE[key]
    zones, df = htf_zones_for(symbol, htf_tf)
    data = None
    if df is not None and len(df) > 3:
        try:
            idx = df.index
            dur = np.timedelta64(TF_MINUTES.get(_tf_key(htf_tf), 1440), "m")
            close_ns = idx.asi8 + dur.astype("timedelta64[ns]").astype("int64")
            g = _htf_gap_arrays(df)
            if g is not None:
                idx1 = g.pop("idx1")
                data = dict(zones=list(zones or []), df=df, Hns=close_ns,
                            ns=close_ns[idx1], **g)
        except Exception:                                   # noqa: BLE001
            data = None
    with _htf_lock():
        _HTF_CACHE[key] = data
    return data


def _htf_ref_ns(idxH, ref_ts):
    ref = pd.Timestamp(ref_ts)
    tz = getattr(idxH, "tz", None)
    if ref.tzinfo is None and tz is not None:
        ref = ref.tz_localize(tz)
    if ref.tzinfo is not None and tz is None:
        ref = ref.tz_localize(None)
    return int(ref.value)


def htf_rung_flags(data, base_lo, base_hi, ref_ts, dem):
    """एक HTF (सीढ़ी का एक डंडा) पर Z / G / P."""
    out = dict(z=False, g=False, p=False, z_broken=False)
    if not data or not (np.isfinite(base_lo) and np.isfinite(base_hi)):
        return out
    try:
        ref_ns = _htf_ref_ns(data["df"].index, ref_ts)
    except Exception:                                       # noqa: BLE001
        return out
    Hns = data["Hns"]
    t_pos = int(np.searchsorted(Hns, ref_ns, side="right") - 1)
    if t_pos < 0:
        return out
    # ---- Z: सही दिशा का HTF ज़ोन जिसका price-area base box से मिलता है
    cH = None
    for zh in data["zones"]:
        iH = int(getattr(zh, "createdBarIndex", -1))
        if iH < 0 or iH > t_pos:
            continue
        p_h = float(getattr(zh, "proxVal", np.nan))
        d_h = float(getattr(zh, "distVal", np.nan))
        if not (np.isfinite(p_h) and np.isfinite(d_h)):
            continue
        lo, hi = (p_h, d_h) if p_h <= d_h else (d_h, p_h)
        if min(base_hi, hi) - max(base_lo, lo) <= 0:
            continue
        if bool(getattr(zh, "isDemand", True)) != bool(dem):
            continue
        out["z"] = True
        if iH < t_pos:                                      # टूटा हुआ? (सिर्फ़ जानकारी)
            if cH is None:
                cH = data["df"]["close"].to_numpy(float)
            seg = cH[iH + 1:t_pos + 1]
            if bool(np.any(seg < lo)) if dem else bool(np.any(seg > hi)):
                out["z_broken"] = True
    # ---- G / P: void गैप (G = सामान्य, P = pivot जोड़ी वाला)
    upto = int(np.searchsorted(data["ns"], ref_ns, side="right"))
    if upto > 0:
        sel = (np.arange(upto) <= t_pos)
        if bool(sel.any()):
            ov = (np.minimum(base_hi, data["vhi"][:upto])
                  - np.maximum(base_lo, data["vlo"][:upto]))
            ok = np.nan_to_num(ov, nan=-1.0) > 0
            ok &= sel
            same = ok & (data["up"][:upto] if dem else data["dn"][:upto])
            piv = (data["pu"][:upto] | data["pd"][:upto])
            out["g"] = bool((same & ~piv).any())
            out["p"] = bool((same & piv).any())
    return out


def htf_cascade(symbol, tf, base_lo, base_hi, ref_ts, dem,
                checks=HTF_CHECKS, stop_first=None):
    """सीढ़ी पर जाँच — जो नियम (Z/G/P) मिलते ही ऊपर चढ़ना बंद.

    लौटाता है: z / g / p (किसी भी HTF पर मिला या नहीं), match_tf (पहला मिला TF),
    flags (उस समय के अक्षर), rungs (कहाँ-कहाँ देखा गया).
    """
    out = dict(z=False, g=False, p=False, match_tf="", flags="", note="", rungs=[], ladder="")
    if not (HTF_SCAN_ENABLED and symbol and checks):
        return out
    stop = HTF_STOP_ON_FIRST if stop_first is None else bool(stop_first)
    for rung, note in htf_ladder(tf):
        data = htf_data_for(symbol, rung)
        out["rungs"].append(rung)
        if not data:
            continue
        r = htf_rung_flags(data, base_lo, base_hi, ref_ts, dem)
        z = r["z"] and ("Z" in checks)
        g = r["g"] and ("G" in checks)
        p = r["p"] and ("P" in checks)
        out["z"] |= z
        out["g"] |= g
        out["p"] |= p
        if (z or g or p) and not out["match_tf"]:
            out["match_tf"] = rung
            out["flags"] = ("Z" if z else "") + ("G" if g else "") + ("P" if p else "")
            out["note"] = note
            if r["z_broken"]:
                out["flags"] += "◐"
            if stop:
                break
    out["ladder"] = " → ".join(out["rungs"])
    return out


def validate_zones(df: pd.DataFrame, zones: Iterable[Any], *, params: Optional[Dict[str, Any]] = None,
                   entry_depth: float = ENTRY_DEPTH, width_max_atr: Optional[float] = WIDTH_MAX_ATR,
                   min_age_bars: Optional[int] = MIN_AGE_BARS, min_margin_atr: Optional[float] = MIN_MARGIN_ATR,
                   min_dep_rvol: Optional[float] = MIN_DEP_RVOL, now_bar: Optional[int] = None,
                   symbol: str = "", tf: str = "", htf: bool = HTF_SCAN_ENABLED,
                   htf_tf: Optional[str] = None,
                   htf_checks: Optional[Iterable[str]] = None) -> pd.DataFrame:
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
    _PB_GAPS = None                              # 🎯 उसी TF के void गैप (imbalance) — एक बार बनेंगे
    n = len(df)
    j_now = n - 1 if now_bar is None else int(now_bar)

    # 🏔️🕳️ HTF जाँच के लिए तैयारी (ज़ोन/गैप उसी zscan से; validation पहले, यह उसके बाद)
    if htf and htf_busy():          # HTF scan के अंदर दोबारा HTF नहीं
        htf = False
    checks = tuple(c for c in (htf_checks if htf_checks is not None else HTF_CHECKS)
                   if str(c).upper() in ("Z", "G", "P"))
    symbol_key = str(symbol).replace(".NS", "") or str(symbol)
    ref_ts = _ts_at(df, j_now)

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

        # 🎯 1:5 playbook के आँकड़े — वही formula जो बैकटेस्ट में था (कोई नया data नहीं)
        bc0_ = max(1, int(getattr(z, "baseCount", 1) or 1))
        ab0 = max(0, int(getattr(z, "startBarIndex", i - bc0_) or 0))
        bb0 = min(n, max(ab0 + 1, i + 1))
        pb_base_lo = float(np.nanmin(l[ab0:bb0])) if bb0 > ab0 else float(l[i])
        pb_base_hi = float(np.nanmax(h[ab0:bb0])) if bb0 > ab0 else float(h[i])
        k5 = min(n - 1, i + 5)                       # base छोड़ने के 5 bars में चाल (ताक़तवर निकास)
        dep_atr = np.nan
        if k5 > i and np.isfinite(av) and av > 0:
            dep_atr = ((float(np.nanmax(cl[i + 1:k5 + 1])) - pb_base_hi) if dem
                       else (pb_base_lo - float(np.nanmin(cl[i + 1:k5 + 1])))) / av
        w0_ = max(0, i - 120)                        # पिछले 120 bars की सीमा तक जगह
        rlo_, rhi_ = float(np.nanmin(l[w0_:i + 1])), float(np.nanmax(h[w0_:i + 1]))
        room_atr = ((rhi_ - prox) if dem else (prox - rlo_)) / av if (np.isfinite(av) and av > 0) else np.nan
        rej_close = None
        if first_touch is not None:
            rej_close = bool(cl[first_touch] > prox) if dem else bool(cl[first_touch] < prox)
        if _PB_GAPS is None:                         # उसी TF का void गैप (imbalance) — एक बार
            try:
                _tmp = df.rename(columns={c["open"]: "open", c["high"]: "high", c["low"]: "low",
                                          c["close"]: "close"})
                _PB_GAPS = _htf_gap_arrays(_tmp[["open", "high", "low", "close"]])
            except Exception:                                    # noqa: BLE001
                _PB_GAPS = {}
        imbal = False
        if _PB_GAPS:
            upto_ = min(len(_PB_GAPS["vlo"]), i + 1)
            if upto_ > 0:
                ov = (np.minimum(pb_base_hi, _PB_GAPS["vhi"][:upto_])
                      - np.maximum(pb_base_lo, _PB_GAPS["vlo"][:upto_]))
                ok_ov = np.nan_to_num(ov, nan=-1.0) > 0
                same = ok_ov & (_PB_GAPS["up"][:upto_] if dem else _PB_GAPS["dn"][:upto_])
                imbal = bool(same.any())

        q1 = None if width_max_atr is None else bool(np.isfinite(width_atr) and width_atr <= width_max_atr)
        q2 = None if min_age_bars in (None, 0) else bool(age >= int(min_age_bars))
        q3 = None if min_margin_atr is None else bool(np.isfinite(margin_atr) and margin_atr >= min_margin_atr)
        q4_known = bool(np.isfinite(dv))
        q4 = None if min_dep_rvol is None else bool(q4_known and dv >= min_dep_rvol)
        score = int(sum(1 for x in (q1, q2, q3, q4) if x is True))
        _rules_here = {"width_max_atr": width_max_atr, "min_age_bars": min_age_bars,
                       "min_margin_atr": min_margin_atr, "min_dep_rvol": min_dep_rvol}
        grade, _need = grade_of((q1, q2, q3, q4), _rules_here)

        state = str(getattr(z, "state", "") or "")
        broken = "broken" in state.lower()
        verdict = ("✖ छोड़ें (ज़ोन टूट चुका)" if broken else
                   {"A": "✅ Trade (नियम पास)", "B": "◐ B (एक शर्त चूकी)",
                    "C": "✖ छोड़ें (दो या ज़्यादा शर्तें चूकीं)"}[grade])

        entry_deep = prox - float(entry_depth or 0.0) * width * (1 if dem else -1)
        sl = dist
        risk = abs(entry_deep - sl)
        tps = {kk: (entry_deep + rr * risk if dem else entry_deep - rr * risk) for kk, rr in TARGET_RR.items()}

        notes = []
        if q1 is False and np.isfinite(width_atr):
            notes.append(f"ज़ोन चौड़ा ({width_atr:.2f} ATR > {width_max_atr})")
        if q2 is False:
            notes.append(f"उम्र कम ({age} bars < {min_age_bars})")
        if q3 is False and np.isfinite(margin_atr):
            notes.append(f"margin कम ({margin_atr:.1f} ATR)")
        if q4 is False:
            if not q4_known:
                notes.append("volume उपलब्ध नहीं (RVOL नहीं निकला)")
            else:
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

        # LTF का base candle price-area (base candles: startBarIndex → createdBarIndex)
        bc0 = max(1, int(getattr(z, "baseCount", 1) or 1))
        ab = max(0, int(getattr(z, "startBarIndex", i - bc0) or 0))
        bb = min(n, max(ab + 1, i))
        base_lo = float(np.nanmin(l[ab:bb])) if bb > ab else float(l[i])
        base_hi = float(np.nanmax(h[ab:bb])) if bb > ab else float(h[i])
        hc = (htf_cascade(symbol_key, tf, base_lo, base_hi, ref_ts, dem, checks)
              if (htf and symbol_key) else None)
        htf_z = bool(hc and hc["z"])
        htf_g = bool(hc and hc["g"])
        htf_p = bool(hc and hc["p"])
        htf_ok = bool(htf_z or htf_g or htf_p)
        htf_match = str(hc["match_tf"]) if (hc and hc["match_tf"]) else ""
        htf_flags = str(hc["flags"]) if (hc and hc["flags"]) else ""
        htf_txt = ("·".join([x for x, on in (("Z", htf_z), ("G", htf_g), ("P", htf_p)) if on])
                   + (" · " + htf_match if htf_match else "")) if htf_ok else "—"

        marks = []
        if np.isfinite(pen) and pen >= DEEP_TOUCH_ATR:
            marks.append("🔻 गहरा touch")
        if str(tf) in MARK_SMALL_TFS:
            marks.append("⏱️ छोटा TF")
        if MARK_DBD and str(getattr(z, "patternType", "") or "").upper() == "DBD":
            marks.append("⚠️ DBD")
        if dem and np.isfinite(base_w) and base_w >= MARK_BASE_WEIGHT:
            marks.append("⭐ मज़बूत base")
        if htf_ok:
            marks.append("🏔️ " + htf_flags + (" · " + htf_match if htf_match else ""))

        _pb_row = playbook_check(tf, {"dep_atr": dep_atr, "room_atr": room_atr, "width_atr": width_atr,
                                      "touch_pen": pen, "age_bars": age, "base_cnt": int(bc),
                                      "imbal": imbal, "rej_close": rej_close, "dir": "Demand" if dem else "Supply"},
                                 alias=PLAYBOOK_ALIAS, depth=entry_depth)
        _pb_txt = ("— (इस TF का playbook नहीं)" if _pb_row.get("pb_pass") is None and not _pb_row.get("pb_rules")
                   else ("✔ पास" if _pb_row.get("pb_pass") is True
                         else ("✘ छूटा: " + ", ".join(_pb_row.get("pb_fail") or []) if _pb_row.get("pb_pass") is False
                               else "◐ जानकारी अधूरी")))

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
            "जगह (×जोखिम)": (round((room_atr / width_atr) / max(1e-9, 1.0 - float(entry_depth or 0.0)), 2)
                              if (np.isfinite(room_atr) and np.isfinite(width_atr) and width_atr > 0) else np.nan),
            "Q1": "—" if q1 is None else ("✔" if q1 else "✘"),
            "Q2": "—" if q2 is None else ("✔" if q2 else "✘"),
            "Q3": "—" if q3 is None else ("✔" if q3 else "✘"),
            "Q4": "—" if q4 is None else ("✔" if q4 else ("?" if not q4_known else "✘")),
            "ZQS": score, "Grade": grade, "निशान": " · ".join(marks), "फ़ैसला": verdict,
            "HTF (Z·G·P)": htf_txt,
            "HTF मिला (TF)": htf_match,
            "🎯 1:5 Playbook": _pb_txt,
            "_pb_pass": _pb_row.get("pb_pass"), "_pb_rules": _pb_row.get("pb_rules", ""),
            "_pb_note": _pb_row.get("pb_note", ""), "_pb_bt": _pb_row.get("pb_bt", ""),
            "_pb_weak": _pb_row.get("pb_weak", False), "_pb_depth": _pb_row.get("pb_depth"),
            "_dep_atr": round(dep_atr, 3) if np.isfinite(dep_atr) else np.nan,
            "_room_atr": round(room_atr, 3) if np.isfinite(room_atr) else np.nan,
            "_imbal": bool(imbal), "_rej_close": rej_close, "_base_cnt": int(bc),
            "_pb_checked": True,
            "_htf_z": htf_z, "htf_g": htf_g,
            "_htf_flags": htf_flags, "_htf_match": htf_match,
            "Entry (proximal)": round(prox, 2),
            "Entry (proximal से गहराई)": round(entry_deep, 2),
            # पुराना नाम — Zone_Scanner.py की इनलाइन table इसे पढ़ती है (एक ही मान)
            "Entry (30% गहराई)": round(entry_deep, 2),
            "SL (distal)": round(sl, 2),
            "TP 1:2": round(tps["1:2"], 2), "TP 1:3": round(tps["1:3"], 2), "TP 1:5": round(tps["1:5"], 2),
            "Risk (pts)": round(risk, 2),
            "Base weight": round(base_w, 2) if np.isfinite(base_w) else np.nan,
            "Touch penetration (ATR)": round(pen, 2) if np.isfinite(pen) else np.nan,
            "नोट": "; ".join(notes),
            "_zone": z, "_created_i": i, "_first_touch_i": first_touch,
            "_htf_ok": htf_ok, "_htf_checked": bool(hc is not None),
            "_htf_ladder": (hc["ladder"] if hc else ""),
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
        "entry_buffer": _num(g("Entry (proximal से गहराई)")),
        "sl_distal": _num(g("SL (distal)")),
        "tp2": _num(g("TP 1:2")), "tp3": _num(g("TP 1:3")), "tp5": _num(g("TP 1:5")),
        "risk_pts": _num(g("Risk (pts)")),
        "base_weight": _num(g("Base weight")),
        "touch_pen": _num(g("Touch penetration (ATR)")),
        "marks": g("निशान"),
        "htf_zone": g("HTF (Z·G·P)"),
        "htf_match_tf": g("HTF मिला (TF)") or "",
        "htf_z": bool(g("_htf_z") is True),
        "htf_g": bool(g("_htf_g") is True),
        "htf_p": bool(g("_htf_p") is True),
        "htf_flags": g("_htf_flags") or "",
        "htf_ok": bool(g("_htf_ok") is True),
        "htf_checked": bool(g("_htf_checked") is True),
        "room_atr": _num(g("_room_atr")),
        "dep_atr": _num(g("_dep_atr")),
        "imbal": g("_imbal"),
        "rej_close": g("_rej_close"),
        "base_cnt": _num(g("_base_cnt")),
        "pb_checked": bool(g("_pb_checked") is True),
        "pb_pass": g("_pb_pass"),
        "pb_rules": g("_pb_rules"),
        "pb_note": g("_pb_note"),
        "pb_bt": g("_pb_bt"),
        "pb_weak": bool(g("_pb_weak") is True),
        "pb_depth": g("_pb_depth"),
        "pb_col": g("🎯 1:5 Playbook"),
        "room_risk": _num(g("जगह (×जोखिम)")),
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
            "ZQS": r.get("zqs"), "Grade": r.get("grade"), "निशान": r.get("marks", ""),
            "जगह (×जोखिम)": r.get("room_risk"),
            "HTF (Z·G·P)": r.get("htf_zone") or "—",
            "HTF मिला (TF)": r.get("htf_match_tf") or "",
            "🎯 1:5 Playbook": _pb_cell(r),
            "फ़ैसला": r.get("verdict"),
            "Entry (proximal)": r.get("entry"), "Entry (proximal से गहराई)": r.get("entry_buffer"),
            "SL (distal)": r.get("sl_distal"),
            "TP 1:2": r.get("tp2"), "TP 1:3": r.get("tp3"), "TP 1:5": r.get("tp5"),
            "Risk (pts)": r.get("risk_pts"), "Base weight": r.get("base_weight"),
            "Touch penetration (ATR)": r.get("touch_pen"), "नोट": r.get("v_note", ""),
            "_zone": None,
        })
    return pd.DataFrame(recs, columns=["Asset", "TF"] + COLS_VIEW + ["_zone"])


def _pb_cell(row: Any) -> str:
    """Table के लिए playbook का हाल — पास / छूटा (कौन-सा नियम) / जानकारी नहीं."""
    g = row.get if hasattr(row, "get") else (lambda k, d=None: d)
    pas, rules = g("pb_pass"), str(g("pb_rules") or "")
    if pas is None and not rules:
        return "— (इस TF का playbook नहीं)"
    if pas is True:
        return "✔ पास" + (" ⚠️" if g("pb_weak") else "")
    if pas is False:
        return "✘ छूटा: " + ", ".join(g("pb_fail") or []) if g("pb_fail") else "✘ छूटा"
    return "◐ जानकारी अधूरी"


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
        pb_pass=int(vdf.get("🎯 1:5 Playbook", pd.Series(dtype=str)).astype(str).str.contains("✔").sum()),
    )


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


def _htf_badges(row: Any) -> str:
    """Z · G · P — जो नियम मिला वह चमकता है, बाक़ी हल्का. साथ में मिला हुआ TF."""
    g = row.get if hasattr(row, "get") else (lambda k, d=None: d)
    on = {"Z": bool(g("htf_z")), "G": bool(g("htf_g")), "P": bool(g("htf_p"))}
    parts = []
    for letter in ("Z", "G", "P"):
        if on[letter]:
            parts.append(f'<b style="color:{HTF_COLOUR[letter]}" title="{HTF_LETTER[letter]}">{letter}</b>')
        else:
            parts.append(f'<span style="color:#39456b">{letter}</span>')
    txt = " ".join(parts)
    tfx = str(g("htf_match_tf") or "")
    if tfx:
        txt += f' <span style="color:#8ba1c0;font-size:10.5px">{tfx}</span>'
    return txt


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
        f'<th>Risk %</th><th>Grade</th><th>ZQS</th><th>HTF (Z·G·P)</th><th>🎯 1:5 Playbook</th><th>निशान</th><th>{ENTRY_LABEL}</th>'
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
            f'<td data-label="HTF (Z·G·P)">{_htf_badges(row)}</td>'
            f'<td data-label="🎯 1:5 Playbook">{_pb_cell(row)}</td>'
            f'<td data-label="निशान">{row.get("marks") or "—"}</td>'
            f'<td data-label="{ENTRY_LABEL}">{_fmt2v(row.get("entry_buffer"))}</td>'
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
                 title: str = "🧪 Zone Validation",
                 show_title: bool = True,
                 rules: Optional[Dict[str, Any]] = None,
                 entry_depth: float = ENTRY_DEPTH) -> pd.DataFrame:
    """Streamlit section: ek hi table, scanner table ke format me.

    ``rules`` = aapke chune hue niyam (sidebar) — ज़रूरत पड़े तो कोई एक Z/G/P भी. Niyam yahin lagte hain, isliye
    scanner dobara chalane ki zaroorat nahi — toggle badalte hi table badal jaati hai.
    Koi naya data source nahi, koi metric box / chip / chart nahi.
    """
    import streamlit as st
    rows = list(rows or [])
    if not rows:
        st.info("Scanner table khaali hai — pehle scan chalaayein.")
        return pd.DataFrame()

    global ENTRY_LABEL
    _rules = dict(rules or {})
    _per_row = bool(_rules.get("playbook_per_row_depth", True))
    ENTRY_LABEL = ("Entry (playbook की गहराई)" if (_per_row and bool(_rules.get("playbook_on", PLAYBOOK_ON)))
                   else entry_label(entry_depth))
    _rules.setdefault("entry_depth", entry_depth)

    def _depth_for(row: Any) -> float:
        if not _per_row:
            return float(entry_depth or 0.0)
        _pb = playbook_for(row.get("tf"), _rules.get("playbook_alias"))
        if _pb is None:
            return float(entry_depth or 0.0)
        return float(_pb.get("depth") or 0.0)

    rows, _info = apply_rules(rows, _rules)
    rows = [apply_entry(r, _depth_for(r)) for r in rows]   # entry/SL/TP — दोबारा scan नहीं
    if not rows:
        st.info("Aapke चुने हुए नियमों से इस वक़्त कोई ज़ोन पास नहीं हुआ — साइडबार में नियम ढीले करें.")
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


# ==========================================================================
# NOTE — पुराना `--patch` / `--hooks` वाला हिस्सा हटा दिया गया है
# ==========================================================================
# वह हिस्सा app.py के अंदर validation section (tabs के बाद) जोड़ता था — वह layout
# आपने रद्द कर दिया था. अब navigation ऊपर के main menu से है और validation अपना
# अलग page है (pages/Zone_Validation.py), इसलिए यह file खुद कुछ नहीं जोड़ती.
# इस file के चार काम:
#   1) validate_zones()  — scanner के ज़ोन पर आपके चुने नियम लगाकर table बनाना
#   2) row_fields()      — हर ज़ोन की grade/ZQS/SL/TP जानकारी scanner row में भेजना
#   3) apply_rules()     — साइडबार के नियम तुरंत लागू करना (दोबारा scan नहीं)
#   4) render_table()    — scanner table के format में सिर्फ़ पास हुए ज़ोन दिखाना
# (वे पुराने हिस्से हटा दिए गए हैं जिनकी अब ज़रूरत नहीं: app.py में section जोड़ने
#  वाला patcher, पुराना render()/charts, validate_rows/render_universe आदि.)


# ==========================================================================
# local test (repo में चलाने की ज़रूरत नहीं)
# ==========================================================================
def _demo() -> int:
    """Local test — kisi bhi machine par surakshit (data na mile to sirf help dikhata hai)."""
    try:
        import pickle
        import sys
        _here = os.path.dirname(os.path.abspath(__file__))
        for _p in (_here, os.path.dirname(_here)):
            if _p and _p not in sys.path:
                sys.path.insert(0, _p)
        import zone_core as ZC

        for cand in ("/home/user/data/wf/tfs_b.pkl", os.path.join(os.getcwd(), "tfs_b.pkl")):
            if not os.path.exists(cand):
                continue
            tfs = pickle.load(open(cand, "rb"))
            frame = tfs["4h"]["RELIANCE"]
            zones = ZC.scan_zones(frame)
            vdf = validate_zones(frame, zones, symbol="RELIANCE.NS", tf="4h")
            show = ["बना (समय)", "ज़ोन", "पैटर्न", "उम्र (bars)", "चौड़ाई (ATR)", "Margin (ATR)", "Dep RVOL",
                    "जगह (×जोखिम)", "ZQS", "Grade", "🎯 1:5 Playbook", "Entry (proximal)", "SL (distal)",
                    "TP 1:3", "TP 1:5", "Base weight"]
            print(f"RELIANCE 4h: {len(zones)} zones -> validation table {vdf.shape}")
            print(vdf[show].to_string(index=False))
            print("summary:", validation_summary(vdf))
            return 0
    except Exception as exc:                                     # noqa: BLE001
        print(f"(local demo skip: {exc})")
    print("\nइस्तेमाल:")
    print("  python zone_validation.py --demo      # local test (RELIANCE 4h par niyam check)")
    return 0


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Zone validation layer (alag file)")
    ap.add_argument("--dir", default=None, help="repo folder (default: current folder)")
    ap.add_argument("--demo", action="store_true", help="local test (default)")
    args = ap.parse_args()

    if args.demo:
        raise SystemExit(_demo())

    raise SystemExit(_demo())        # koi flag na ho to demo/help hi dikh jata hai
