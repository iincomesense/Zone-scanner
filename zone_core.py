# -*- coding: utf-8 -*-
"""
zone_core.py — v14.0  (MERGED: zone_core engine/API  +  FINAL 12-RULE core detection)
=====================================================================================================
  YEH FILE DOON KA MERGE HAI:
    (1) zone_core.py engine/API  — Zone, settings(), scan_zones(), get_zone_alerts(),
        latest_active_zones(), realistic_roi(), simulate(), backtest_summary(), target_context(),
        state-machine, MTF  — aapke app (aap.py/options.py/zscan.py) ke liye SAME public API.
    (2) FINAL 12-RULE core (4-study, Nifty50 x 9TF, data-validated)  — leg-in / boring / leg-out
        candle ke RULES bilkul FINAL spec ke: leg-in (non-doji, wick<=50%, lower wick<=25%,
        close-strong 60%, TR>=ATR), boring 1-3 (body<=20% classic UOC, TR<ATR), leg-out (non-doji,
        wick<=45%, body>leg-in ladder, TR>=1.5x boring, close-strong 60%, TR>ATR), band<=0.75%,
        SL=distal buffer 0, N1 ladder / N2 white area / N3 trap / N4 DBR-RBD open / N5 ATR / N6 wick-fresh,
        RR 1:3, 10-candle exit window.
  DETECTION CORE ab FINAL 12-RULE spec hi hai (default). Entry/exit engine (state-machine / simulate)
  zone_core.py ka hi hai (confirm-close entry; wick-fresh kill = Broken on distal touch).
  Saare 12-rule thresholds params se tunable: liWickTotal, liLowerMax, liCloseStrong, boringBodyMax,
  loFilledMax, loTrBoring, loCloseStrong, bandMaxPct, trapCoverLimit. (Purane v13.3 params bhi retained
  settings() ke liye; jo naye core se supersede huye unhe detection ignore karta hai.)
=====================================================================================================
zone_core.py — v13.3  (v13.2 + TARGET-CONTEXT study: "zone target kyon deta hai" — highlight layer, koi naya gate nahi)
=====================================================================================================
█████████████████████████████████████████████████████████████████████████████████████████████████████
█  v13.3  TARGET STUDY (REPORT14) — 282 (v12.1) + 148 (v13.2) trades, 10m...1D-10y, 176 stocks          █
█  sawaal: TP dene wale zone mein entry ke samay kya alag tha?  jawaab = 6 signs, har ek PDF ke kisi niyam ka data-roop █
█████████████████████████████████████████████████████████████████████████████████████████████████████
   sign A: MARKET  Nifty daily close > EMA20 (demand) / < (supply)
   sign B: HTF     higher-TF close > EMA20 (demand) / < (supply)
   sign C: LEG-IN  leg-in candle volume >= 20-bar avg (arrival)
   sign D: RETEST  retest (entry) candle volume < 1.3 x avg (quiet)
   sign E: SLOPE   own-TF EMA20 rising (demand) / falling (supply)
   sign F: MACRO   demand -> VIX >= 16.5 ya S&P 20-day return < 0 ; supply -> VIX < 16.5
   TP-SCORE = A+B+C+D+E+F (0-6): HIGH (>=4) 56% | LOW (<=2) 19%  (v13.2)
   API: target_context(zone, df, htf_df=None, market_df=None, vix=None, spx_ret20=None)
        -> dict(score, max, label, A..F, why)
=====================================================================================================
zone_core.py — v13.2  (v13.1 + CONFIRM-STRENGTH rule from the all-TF SL study)
=====================================================================================================
   25. CONFIRM STRENGTH (minEntrySlipR 0.2, sabhi TF): confirm-close proximal se kam-se-kam 0.2 x risk aage band ho.
   1h 46.5 -> 50.0 %, 4h 43.3 -> 47.8 %, 1D-10y 32.5 -> 37.5 %.  entryStatus "Failed-WeakConfirm".
=====================================================================================================
zone_core.py — v13.1  (v12.1 FINAL + 10m/15m footprint/context rules + VOLUME-STRUCTURE rules)
=====================================================================================================
   22. LEG-OUT >= 1.2 x LEG-IN volume (legOutVolOverLegIn, intraday TFs 10m...6h).
   23. RETEST VOLUME <= 0.8 x leg-out volume (maxRetestVolOverLegOut, 10m/15m).
   24. LEG-IN >= boring volume (legInVolOverBase 1.0) — sirf WIN-RATE preset.
   PRESET_V121 = dict(autoTF=False, legOutVolOverLegIn=None) -> v12.1 ka hub-hu behaviour.
=====================================================================================================
zone_core.py — v13.0  (v12.1 FINAL + 10m/15m "institutional footprint / context" rules)
=====================================================================================================
   17. NO FOOTPRINT : legOutVolMin 1.3   18. WEAK OPEN : minGapLegIn -0.02
   19. RETURN TOO SOON : minRetestBars 4 (LTF)   20. WRONG REGIME : atrRegime 0.9-1.3
   21. LOCATION : maxPrevDayLoc 0.5
=====================================================================================================
zone_core.py — v12.1 FINAL  (Surat-Festiva PDF rulebook + validated v10.3 filters + RETEST-QUALITY entry rules)
GitHub / Streamlit-ready build — drop-in replacement for the old v10.x zone_core.py
(same public API used by zscan.py: settings(), scan_zones(), scan_winrate(), recommended_trade_setup(),
 realistic_roi(), backtest_summary(), latest_active_zones(), get_zone_alerts(), diagnose_bar(), ...)

kya badla (backtest-validated, Nifty-49, Jan-Sep 2026, RR 1:3):
  1. ZONE MARKING  : proximal = boring BODY edge (DZ: body-high, SZ: body-low), distal = boring wick extreme.
  2. STOP-LOSS     = distal line par hi, koi ATR buffer nahi.
  3. ENTRY         = "confirm": price proximal chhue aur wahi candle proximal ke bahar close kare -> us close par entry.
  4. FILTERS       : v10.3 density score 45-75; leg-out >= 1.3x leg-in.
  5. SCORE         : Notes p.14 ka 10-point score card har zone mein stored.
  6. DAILY preset  : scan_daily().
  7. BORING COUNT  : max 3 boring candles.  8. BORING COLOUR : DZ mein laal / SZ mein hari.
  9. RETEST DEPTH  : maxPenetration 0.5.  10. RETEST TIMING : minRetestBars 2.
  11. STATE MACHINE : zone.state Fresh / Tested / Failed / Broken.
  12. WIN-RATE preset: + trapGuard + maxPenetration 0.4.
  13. GAP RULE : maxGapLegIn 1.0.  14. ADVERSE GAP : noAdverseGap.
  15. ENTRY DISTANCE : maxEntrySlipR 2.0.  16. DENSITY BAND : 45-75.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import numpy as np
import pandas as pd

__version__ = "v14.0"

# =============================================================================
# SECTION 1: RULES / PARAMS
# =============================================================================

DEFAULT_PARAMS = dict(
    # ---------- risk / money ----------
    accountCapital=25000.0,
    riskPct=0.5,
    targetRR=3.0,                  # FINAL 1:3
    slBufferAtr=0.0,               # FINAL: NO buffer
    # ---------- indicators ----------
    atrPeriod=14,
    volSmaPeriod=20,
    # ---------- FINAL 12-RULE SPEC (data-validated core) ----------
    liWickTotal=0.50,          # R2: leg-in total wick <= 50% TR
    liLowerMax=0.25,           # R3: leg-in LOWER wick <= 25% TR (sabse powerful)
    liCloseStrong=0.60,        # R7: leg-in close strong-half (green CLV>=0.6 / red CLV<=0.4)
    boringBodyMax=0.20,        # R11: boring body <= 20% TR (classic UOC), count 1-3
    loFilledMax=0.45,          # leg-out total wick <= 45% TR (base)
    loTrBoring=1.5,            # R9: leg-out TR >= 1.5 x boring[0] TR
    loCloseStrong=0.60,        # R10: leg-out close strong-half 60%
    bandMaxPct=0.75,           # R8: zone band <= 0.75% of entry (STOP CONTROL)
    trapCoverLimit=0.5,        # N3: leg-in body ka 50% cover = trap
    # ---------- LEG-IN ----------
    legInMinBodyPct=0.60,          # body/range
    legInMinClv=0.60,              # close position in its own direction
    legInToBaseMult=1.5,           # leg-in TR >= k x max boring TR
    legInMinAtr=0.0,
    legInWickRequired=False,
    legInMinWickPct=0.0,
    rejectOppCoverPct=0.10,
    noGapLegInBase=False,
    legInMaxLowerWickPct=None,     # v13.4/FINAL12 R3: leg-in LOWER wick <= x x TR (None = off)
    legInMaxClosingWickPct=None,   # v13.4/FINAL12 R4: leg-in CLOSING-SIDE wick <= x x TR (None = off)
    # ---------- BASE / BORING ----------
    minBase=1, maxBase=3,
    maxBaseAtrMult=1.0,
    maxBaseBodyPct=None,
    baseColourMode="require",
    baseWickRequired=False,
    baseMinWickPct=0.0,
    # ---------- LEG-OUT ----------
    legOutTrMult=1.2,
    legOutMinBodyPct=0.0,
    legOutMaxWickPct=0.40,
    legOutToLegInRatio=1.3,
    legOutVolGate=False,
    gapBaseLegOut="none",
    trapGuard=False,
    freshBoring=False,
    imbalance=True,
    engulfGate=True,
    legOutCoverRR=None,
    legOutMinClv=None,             # v13.4/FINAL12 R10: leg-out close position (own dir) >= x (None = off)
    legOutToBaseMult=None,         # v13.4/FINAL12 R9: leg-out TR >= k x max boring TR (None = off)
    # ---------- ZONE MARKING / SL ----------
    proxMode="body",
    proxBodyEdge="near",
    distMode="wick",
    slMode="distal",
    slProxAtr=0.3,
    fitRR=None,
    minRiskAtr=0.15,
    # ---------- v10.3 DENSITY SCORE ----------
    useDensity=True, minDensity=45, maxDensity=75,
    hqScoreThreshold=90,
    # ---------- Notes p.14 10-POINT SCORE ----------
    useScore=False, minScore=5, maxScore=None,
    # ---------- v12.1 GAP / SIZE / ENTRY-DISTANCE ----------
    maxGapLegIn=1.0,
    maxGapRisk=None,
    noAdverseGap=True,
    maxRiskPct=None,
    maxRiskAtr=None,
    maxEntrySlipR=2.0,
    minEntrySlipR=0.2,
    htfTrendEma=None,
    htfTrendAt="entry",
    # ---------- v12 RETEST-QUALITY ENTRY RULES ----------
    maxPenetration=0.5,
    minRetestBars=2,
    # ---------- v13 INSTITUTIONAL-FOOTPRINT / CONTEXT ----------
    legOutVolMin=None,
    legOutVolOverLegIn=1.2,
    baseVolMax=None,
    legInVolOverBase=None,
    maxRetestVolOverLegOut=None,
    minGapLegIn=None,
    atrRegimeMin=None, atrRegimeMax=None,
    atrRegimePeriod=50,
    maxPrevDayLoc=None,
    ltfOverrides=dict(legOutVolMin=1.3, minGapLegIn=-0.02, atrRegimeMin=0.9, atrRegimeMax=1.3,
                      minRetestBars=4, maxPrevDayLoc=0.5,
                      maxRetestVolOverLegOut=0.8),
    dailyOverrides=dict(legOutVolOverLegIn=None),
    autoTF=True,
    maxRetestBars=None,
    # ---------- CONTEXT ----------
    opposingZoneRR=None,
    followUpLookback=0,
    htfZones=None,
    requireFollowUp=False,
    trendEma=None,
    demandOnly=False,
    duplicateAtr=0.25,
    maxTouches=2,
)

_ALIASES = {
    "maxWickPct": "legOutMaxWickPct",
    "legOutMinTrRatio": "legOutToLegInRatio",
    "legInToBaseSizeMultSingleBase": "legInToBaseMult",
    "legInToBaseSizeMult": None,
    "minValidScore": "minDensity",
    "maxBaseCount": "maxBase",
    "minBaseCount": "minBase",
    "minClvPct": "legInMinClv",
    "rejectOppositeCoverPct": "rejectOppCoverPct",
    "legInMinAtrMult": "legInMinAtr",
    "volume_gate": "legOutVolGate",
    "score_gate": "useDensity",
}
_HARD_MAX_BASE_COUNT = 3

# ---------------- PRESETS (backtested) ----------------
PRESET_FINAL   = {}
PRESET_V121    = dict(autoTF=False, legOutVolOverLegIn=None, minEntrySlipR=None)
PRESET_WINRATE = dict(trapGuard=True, maxPenetration=0.4, legInVolOverBase=1.0)
PRESET_V103    = dict(proxMode="wick", slBufferAtr=0.25)
PRESET_DAILY   = dict(useDensity=False, rejectOppCoverPct=None, legInToBaseMult=1.2, legOutToLegInRatio=1.0,
                      legOutTrMult=1.0, legInMinBodyPct=0.5, maxBase=3, freshBoring=True,
                      useScore=True, minScore=5, demandOnly=True, baseColourMode="any",
                      legOutVolOverLegIn=None, minEntrySlipR=None)
# v14.0 — DEFAULT detection ab FINAL 12-RULE core hi hai (scan_zones default).
# PRESET_FINAL12 ab NO-OP hai (explicitness/compat ke liye) — naya core default mein hi hai.
PRESET_FINAL12 = dict()

ENTRY_MODE = "confirm"
EVAL_RR = [1.0, 1.5, 2.0, 3.0, 5.0]

_IR_BROKER = 0.0003; _IR_BROKER_CAP = 20.0; _IR_STT = 0.00025; _IR_EXCH = 0.0000297
_IR_SEBI = 0.000001; _IR_GST = 0.18; _IR_STAMP = 0.00003


def settings():
    p = dict(DEFAULT_PARAMS)
    p["_version"] = __version__
    return p


def change_log():
    return [
        ("v14.0", "v13.4", "DETECTION CORE", "Merged FINAL 12-RULE spec as the core detection: leg-in/boring/leg-out candle rules = 4-study FINAL spec. API/engine (state-machine, simulate, ROI, alerts) unchanged; all old params retained (inert where superseded)."),
        ("v13.4", "-", "PRESET_FINAL12", "12-rule FINAL spec (4-study) as opt-in preset + 4 optional params (default OFF). Default = v13.3 unchanged."),
        ("proxMode", "wick", "body", "Proximal = boring BODY edge (Notes p.3 type-b)."),
        ("slBufferAtr", 0.25, 0.0, "SL exactly on distal line, no buffer."),
        ("entry_mode", "prox/mid", "confirm", "Touch proximal + close back beyond proximal -> entry at that close."),
        ("targetRR", 5.0, 3.0, "RR 1:3 validated."),
        ("legOutToLegInRatio", 0.9, 1.3, "v10.3 validated leg-out >= 1.3x leg-in."),
        ("maxDensity", None, 75, "Reject 'too perfect' zones (>75 density)."),
        ("maxBase", 2, 3, "v12: up to 3 boring candles allowed (user rule)."),
        ("baseColourMode", "any", "require", "v12: boring colour mandatory (Notes p.4)."),
        ("maxPenetration", "-", 0.5, "v12: first retest wick stays in outer 50% of zone."),
        ("minRetestBars", "-", 2, "v12: retest on very next candle = Failed zone."),
        ("state", "Fresh/Tested/Broken", "+Failed", "v12: first retest broke entry rule = dead."),
        ("maxGapLegIn", None, 1.0, "v12.1: boring->leg-out body gap <= 1x leg-in TR."),
        ("noAdverseGap", False, True, "v12.1: opening leg-out gapping against zone direction rejected."),
        ("maxEntrySlipR", None, 2.0, "v12.1: confirm-close <= 2R beyond proximal."),
        ("minDensity", 60, 45, "v12.1: 45-75 band."),
        ("volume_gate", True, False, "Leg-out volume gate off."),
        ("gap/trap/wick gates", "-", "OFF", "PDF Day-1 T3/T5 rules: no edge on NSE intraday."),
        ("scan_winrate", "DBD-only score>=50", "boring colour + ratio 1.5", "Colour is not regime-dependent."),
        ("scan_daily", "-", "new", "Daily preset: fresh boring + 10pt score>=5, demand only."),
        ("legOutVolMin (LTF)", None, 1.3, "v13: 10m/15m leg-out volume >= 1.3x avg20."),
        ("minGapLegIn (LTF)", None, -0.02, "v13: 10m/15m leg-out opening against zone rejected."),
        ("minRetestBars (LTF)", 2, 4, "v13: 10m/15m retest within 3 candles = Failed-EarlyRetest."),
        ("atrRegime (LTF)", None, "0.9-1.3", "v13: 10m/15m ATR14/SMA50 outside band rejected."),
        ("maxPrevDayLoc (LTF)", None, 0.5, "v13: 10m/15m DZ in lower half of prev day range."),
        ("autoTF", "-", True, "v13: LTF overrides auto-applied when bar <= 15 min."),
        ("legOutVolOverLegIn", None, 1.2, "v13.1 all TFs: leg-out volume >= 1.2x leg-in volume."),
        ("maxRetestVolOverLegOut (LTF)", None, 0.8, "v13.1 10m/15m: first retest volume <= 0.8x leg-out."),
        ("legInVolOverBase (WINRATE)", None, 1.0, "v13.1 scan_winrate: leg-in volume >= boring volume."),
        ("minEntrySlipR", None, 0.2, "v13.2 all TFs: confirm-close >= 0.2R beyond proximal."),
        ("TP-SCORE (target_context)", None, "A..F", "v13.3 highlight layer, no gate."),
    ]


def _resolve_params(params):
    p = dict(DEFAULT_PARAMS)
    for k, v in (params or {}).items():
        if k in p:
            p[k] = v
        elif k in _ALIASES:
            if _ALIASES[k] is not None:
                p[_ALIASES[k]] = v
    p["maxBase"] = max(1, min(int(p["maxBase"]), _HARD_MAX_BASE_COUNT))
    p["minBase"] = max(1, min(int(p["minBase"]), p["maxBase"]))
    return p


# =============================================================================
# SECTION 2: DATA STRUCTURES
# =============================================================================

@dataclass
class Zone:
    proxVal: float
    distVal: float
    slVal: float
    tpVal: float
    isDemand: bool
    isHQ: bool = False
    densityScore: int = 0
    patternType: str = ""
    zoneCategory: str = ""
    state: str = "Fresh"
    touchCount: int = 0
    originalDensityScore: int = 0
    startBarIndex: int = 0
    createdBarIndex: int = 0
    baseCount: int = 0
    timestamp: object = None
    legOutHigh: float = 0.0
    legOutLow: float = 0.0
    legOutMidLevel: float = 0.0
    isOvernightGap: bool = False
    legInTR: float = 0.0
    legOutTR: float = 0.0
    hasGenuineGap: bool = False
    hasBodyGap: bool = False
    gapSize: float = 0.0
    reformedAfterBreak: bool = False
    isMTFConfluence: bool = False
    isNestedInBiggerTF: bool = False
    confluenceTFs: list = field(default_factory=list)
    baseHigh: float = 0.0
    baseLow: float = 0.0
    baseBodyHigh: float = 0.0
    baseBodyLow: float = 0.0
    baseColourOK: bool = False
    freshBoring: bool = False
    legOutCoverR: float = 0.0
    followUp: bool = False
    score10: int = 0
    scoreCard: dict = field(default_factory=dict)
    maxPenetration: float = 0.5
    minRetestBars: int = 2
    entryStatus: str = "Waiting"
    entryPrice: float = 0.0
    entryBarIndex: int = -1
    retestBarIndex: int = -1
    retestPen: float = 0.0
    gapToLegIn: float = 0.0
    gapToRisk: float = 0.0
    maxEntrySlipR: object = None
    legOutVol: float = 0.0
    minEntrySlipR: object = None
    htfTrendEma: object = None
    maxRetestVolOverLegOut: object = None
    retestVolRatio: float = 0.0
    legInVolX: float = float("nan")
    legOutVolX: float = float("nan")
    baseVolX: float = float("nan")
    legOutOverLegIn: float = float("nan")
    retestVolX: float = float("nan")
    emaSlopeOK: object = None
    entryMode: str = ENTRY_MODE

    @property
    def density(self): return self.densityScore
    @property
    def score(self): return self.score10
    @property
    def riskPct(self): return 100.0 * abs(self.proxVal - self.slVal) / self.proxVal if self.proxVal else 0.0


def _zone_range(z): return min(z.proxVal, z.distVal), max(z.proxVal, z.distVal)
def _ranges_overlap(a_lo, a_hi, b_lo, b_hi): return max(a_lo, b_lo) <= min(a_hi, b_hi)
def _ranges_nested(ilo, ihi, olo, ohi): return olo <= ilo and ihi <= ohi


# =============================================================================
# SECTION 3: INDICATOR HELPERS
# =============================================================================

def _true_range(h, l, c):
    n = len(h); tr = np.empty(n); tr[0] = h[0] - l[0]
    if n > 1:
        tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    return tr


def _wilder_atr_from_tr(tr, period):
    n = len(tr); atr = np.full(n, np.nan)
    if n >= period:
        seed = tr[:period].mean(); atr[period - 1] = seed
        if n > period:
            sm = pd.Series(tr[period:]).ewm(alpha=1.0 / period, adjust=False).mean().to_numpy()
            atr[period:] = np.concatenate([[seed], sm[1:]])
    return atr


def _bar_dates_array(df):
    idx = df.index
    if isinstance(idx, pd.DatetimeIndex):
        return idx.date
    try:
        return pd.to_datetime(idx).date
    except Exception:
        return None


def _resolve_start_bar_for_lookback(df, lookback_months):
    n = len(df)
    if lookback_months is None or lookback_months <= 0 or n == 0:
        return 0
    idx = df.index
    if isinstance(idx, pd.DatetimeIndex):
        cutoff = idx[-1] - pd.DateOffset(months=lookback_months)
        return int(max(0, idx.searchsorted(cutoff, side="left")))
    return int(max(0, n - int(round(lookback_months * 21))))


def _cols(df):
    m = {c.lower(): c for c in df.columns}
    o = df[m["open"]].to_numpy(float); h = df[m["high"]].to_numpy(float)
    l = df[m["low"]].to_numpy(float); c = df[m["close"]].to_numpy(float)
    v = df[m["volume"]].to_numpy(float) if "volume" in m else np.zeros(len(df))
    return o, h, l, c, np.nan_to_num(v)


def _prep(df, p):
    o, h, l, c, v = _cols(df)
    tr = _true_range(h, l, c)
    atr = _wilder_atr_from_tr(tr, p["atrPeriod"])
    vol_sma = pd.Series(v).rolling(p["volSmaPeriod"]).mean().to_numpy()
    return o, h, l, c, v, tr, atr, vol_sma


def _cost(buy_turn, sell_turn):
    br = min(_IR_BROKER * buy_turn, _IR_BROKER_CAP) + min(_IR_BROKER * sell_turn, _IR_BROKER_CAP)
    return br + _IR_STT * sell_turn + _IR_EXCH * (buy_turn + sell_turn) + _IR_SEBI * (buy_turn + sell_turn) + \
        _IR_GST * (br + _IR_EXCH * (buy_turn + sell_turn) + _IR_SEBI * (buy_turn + sell_turn)) + _IR_STAMP * buy_turn


cost = _cost


# =============================================================================
# SECTION 4: CORE SCANNING ENGINE
# =============================================================================

def bar_minutes(df) -> Optional[float]:
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex) or len(idx) < 3:
        return None
    d = np.diff(idx.values[-200:]).astype("timedelta64[s]").astype(float) / 60.0
    d = d[d > 0]
    return float(np.median(d)) if len(d) else None


def _apply_tf_overrides(df, p):
    if not p.get("autoTF"):
        return p
    bm = bar_minutes(df)
    if bm is None:
        return p
    if bm <= 15.5 and p.get("ltfOverrides"):
        q = dict(p); q.update(p["ltfOverrides"]); return q
    if bm >= 1439 and p.get("dailyOverrides"):
        q = dict(p); q.update(p["dailyOverrides"]); return q
    return p


def _prev_day_range(h, l, dates):
    n = len(h); ph = np.full(n, np.nan); pl = np.full(n, np.nan)
    if dates is None:
        return ph, pl
    cur = dates[0]; dh = -np.inf; dl = np.inf; prevH = np.nan; prevL = np.nan
    for i in range(n):
        if dates[i] != cur:
            prevH, prevL = dh, dl; dh = -np.inf; dl = np.inf; cur = dates[i]
        ph[i] = prevH; pl[i] = prevL
        dh = max(dh, h[i]); dl = min(dl, l[i])
    return ph, pl


def scan_zones(df: pd.DataFrame, params: Optional[dict] = None,
               lookback_months: Optional[float] = None) -> List[Zone]:
    p = _resolve_params(params)
    p = _apply_tf_overrides(df, p)
    o, h, l, c, v, tr, atr, volSma = _prep(df, p)
    n = len(df)
    dates = _bar_dates_array(df)
    vv = np.where(v > 0, v, np.nan)
    volAvg = pd.Series(vv).rolling(p["volSmaPeriod"], min_periods=max(5, p["volSmaPeriod"] // 2)).mean().shift(1).to_numpy()
    atrReg = atr / pd.Series(atr).rolling(int(p["atrRegimePeriod"])).mean().to_numpy() if (p["atrRegimeMin"] is not None or p["atrRegimeMax"] is not None) else None
    pdLoc = _prev_day_range(h, l, dates) if (p["maxPrevDayLoc"] is not None and dates is not None) else None
    bodyH = np.maximum(o, c); bodyL = np.minimum(o, c); rng = h - l
    safe = np.where(rng > 0, rng, 1.0)
    bodyPct = np.where(rng > 0, np.abs(c - o) / safe, 0.0)
    upW = np.where(rng > 0, (h - bodyH) / safe, 0.0); loW = np.where(rng > 0, (bodyL - l) / safe, 0.0)
    ema = pd.Series(c).ewm(span=p["trendEma"], adjust=False).mean().to_numpy() if p["trendEma"] else None
    hema = pd.Series(c).ewm(span=int(p["htfTrendEma"]), adjust=False).mean().to_numpy() if p["htfTrendEma"] else None
    e20 = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
    atrSma = pd.Series(tr).rolling(p["atrPeriod"], min_periods=p["atrPeriod"]).mean().to_numpy()  # N5 ATR (simple mean, = zone_scan)
    htf = p["htfZones"] or []
    zones: List[Zone] = []; active: List[Zone] = []
    start = max(p["atrPeriod"], p["maxBase"] + 3, 11)
    record_from = max(start, _resolve_start_bar_for_lookback(df, lookback_months))

    for t in range(start, n):
        if np.isnan(atr[t]):
            continue
        found = False
        for bc in range(p["minBase"], p["maxBase"] + 1):
            if found:
                break
            li = t - bc - 1; pv = li - 1
            if li < 1 or rng[li] <= 0:
                continue
            a = atrSma[li]
            if np.isnan(a) or a <= 0:
                continue
            # ============ LEG-IN (12-rule: R1 non-doji, R2 wick<=50%, R3 lower<=25%, R4 closing<=25%, R7 close-strong 60%) ============
            liBull = c[li] > o[li]; liBear = o[li] > c[li]
            if not (liBull or liBear):
                continue
            if (upW[li] + loW[li]) > p["liWickTotal"]:
                continue
            if loW[li] > p["liLowerMax"]:
                continue
            if (upW[li] if liBull else loW[li]) > p["liWickTotal"] / 2:
                continue
            clv = (c[li] - l[li]) / rng[li] if liBull else (h[li] - c[li]) / rng[li]
            if clv < p["liCloseStrong"]:
                continue
            # ============ BORING / BASE (R11: 1-3 candles, body<=20% classic UOC) ============
            bidx = list(range(t - bc, t))
            if any(bodyPct[b] > p["boringBodyMax"] for b in bidx):
                continue
            b0 = bidx[0]
            bH = h[bidx].max(); bL = l[bidx].min(); bBH = bodyH[bidx].max(); bBL = bodyL[bidx].min()
            # ============ LEG-OUT (base: non-doji, wick<=45%; R9 TR>=1.5x boring; R10 close-strong 60%) ============
            if rng[t] <= 0:
                continue
            isD = c[t] > o[t]; isS = o[t] > c[t]
            if not (isD or isS):
                continue
            if (upW[t] + loW[t]) > p["loFilledMax"]:
                continue
            # ============ N1 strict body ladder: boring[0] < leg-in < leg-out ============
            b0body = abs(c[b0] - o[b0]); liBody = abs(c[li] - o[li]); loBody = abs(c[t] - o[t])
            if not (liBody > b0body and loBody > liBody):
                continue
            # ============ N5 ATR(14) volatility (no lookahead, at leg-in): li TR>=ATR, boring TR<ATR, lo TR>ATR ============
            if not ((h[li] - l[li]) >= a and all((h[b] - l[b]) < a for b in bidx) and (h[t] - l[t]) > a):
                continue
            if (h[t] - l[t]) < p["loTrBoring"] * (h[b0] - l[b0]):
                continue
            outClv = (c[t] - l[t]) / rng[t] if isD else (h[t] - c[t]) / rng[t]
            if outClv < p["loCloseStrong"]:
                continue
            pat = ("RBR" if liBull else "DBR") if isD else ("DBD" if liBear else "RBD")
            # ============ N2 white area (leg-out body must not intrude into boring->leg-out gap band) ============
            band_lo, band_hi = sorted((c[bidx[-1]], o[t]))
            bod_lo, bod_hi = sorted((o[t], c[t]))
            if bod_lo < band_hi and bod_hi > band_lo:
                continue
            # ============ N3 trap: candle behind leg-in (alag colour + leg-in body ka >50% cover) ============
            if pv >= 0:
                pvBull = c[pv] > o[pv]; pvBear = o[pv] > c[pv]
                pvCol = "green" if pvBull else ("red" if pvBear else "doji")
                if pvCol != ("green" if liBull else "red"):
                    span = bodyH[li] - bodyL[li]
                    if span > 0:
                        overlap = min(bodyH[pv], bodyH[li]) - max(bodyL[pv], bodyL[li])
                        if overlap / span > p["trapCoverLimit"]:
                            continue
            # ============ N4 DBR/RBD: leg-out ki open leg-in ke body range ke andar ============
            if pat in ("DBR", "RBD") and not (bodyL[li] <= o[t] <= bodyH[li]):
                continue
            # ============ ZONE LINES (compute_lines: prox=boring body edge, dist=boring wick extreme) ============
            prox = bBH if isD else bBL
            dist = bL if isD else bH
            risk = abs(prox - dist)
            if risk <= 0:
                continue
            # ============ R8 band <= 0.75% of entry (STOP CONTROL) ============
            if 100.0 * risk / prox > p["bandMaxPct"]:
                continue
            # ============ R12 SL = DISTAL (boring wick extreme), buffer 0 ============
            sl = dist - p["slBufferAtr"] * atr[t] if isD else dist + p["slBufferAtr"] * atr[t]
            overnight = dates is not None and dates[t] != dates[t - 1]
            coverR = ((h[t] - prox) if isD else (prox - l[t])) / risk
            # ============ DUPLICATE (same-side prox within 0.25 ATR dedup) ============
            dup = False
            for cz in reversed(zones[-15:]):
                if cz.state != "Broken" and cz.isDemand == isD and abs(cz.proxVal - prox) < atr[t] * p["duplicateAtr"]:
                    dup = True; break
            if dup:
                continue
            found = True
            tp = prox + risk * p["targetRR"] if isD else prox - risk * p["targetRR"]
            # ---- 12-rule institutional QUALITY SCORE (0-100) — display/ranking ONLY (NOT a detection gate) ----
            # base 50; + powerful leg-out cover, + leg-out volume arrival, + 1 boring (cleaner), + tight band.
            _sc = 50
            if coverR >= 5: _sc += 20
            elif coverR >= 3: _sc += 12
            elif coverR >= 1.5: _sc += 6
            _lovX = (v[t] / v[li]) if (v[t] > 0 and v[li] > 0) else 0.0
            if _lovX >= 2.0: _sc += 12
            elif _lovX >= 1.5: _sc += 8
            elif _lovX >= 1.2: _sc += 4
            if bc == 1: _sc += 8
            if 100.0 * risk / prox < 0.25: _sc += 5
            dens = int(min(100, _sc))
            z = Zone(proxVal=prox, distVal=dist, slVal=sl, tpVal=tp, isDemand=isD,
                     isHQ=(dens >= 85), densityScore=dens, patternType=pat,
                     zoneCategory="Continuation" if pat in ("RBR", "DBD") else "Reversal",
                     originalDensityScore=dens, startBarIndex=t - bc, createdBarIndex=t, baseCount=bc,
                     timestamp=df.index[t], legOutHigh=h[t], legOutLow=l[t],
                     legOutMidLevel=(h[t] + l[t]) / 2, isOvernightGap=overnight, legInTR=tr[li], legOutTR=tr[t],
                     hasGenuineGap=False, hasBodyGap=False, gapSize=0.0, reformedAfterBreak=False,
                     baseHigh=bH, baseLow=bL, baseBodyHigh=bBH, baseBodyLow=bBL, baseColourOK=False,
                     freshBoring=True, legOutCoverR=coverR, followUp=False, score10=min(10, dens // 10), scoreCard={},
                     maxPenetration=p["maxPenetration"], minRetestBars=p["minRetestBars"],
                     gapToLegIn=0.0, gapToRisk=0.0, maxEntrySlipR=p["maxEntrySlipR"],
                     legOutVol=float(v[t]) if v[t] > 0 else 0.0, maxRetestVolOverLegOut=p["maxRetestVolOverLegOut"],
                     minEntrySlipR=p["minEntrySlipR"], htfTrendEma=None)
            va = volAvg[t] if (t < len(volAvg) and not np.isnan(volAvg[t]) and volAvg[t] > 0) else np.nan
            bVol = np.nanmean(vv[bidx]) if np.any(~np.isnan(vv[bidx])) else np.nan
            if not np.isnan(va):
                z.legOutVolX = float(v[t] / va) if v[t] > 0 else np.nan
                z.legInVolX = float(v[li] / va) if v[li] > 0 else np.nan
                z.baseVolX = float(bVol / va) if not np.isnan(bVol) else np.nan
            z.legOutOverLegIn = float(v[t] / v[li]) if (v[t] > 0 and v[li] > 0) else np.nan
            zones.append(z); active.append(z)
        # ---------------- STATE MACHINE ----------------
        if active:
            keep = []
            for z in active:
                if z.createdBarIndex >= t:
                    keep.append(z); continue
                if z.isDemand:
                    broke = l[t] <= z.distVal; touch = l[t] <= z.proxVal; wasIn = l[t - 1] <= z.proxVal
                else:
                    broke = h[t] >= z.distVal; touch = h[t] >= z.proxVal; wasIn = h[t - 1] >= z.proxVal
                if broke:
                    z.state = "Broken"
                    if z.entryStatus == "Waiting":
                        z.entryStatus = "Failed-BrokeThrough"
                elif touch and z.state == "Fresh":
                    rk = abs(z.proxVal - z.slVal)
                    pen = ((z.proxVal - l[t]) if z.isDemand else (h[t] - z.proxVal)) / rk if rk > 0 else 1.0
                    bars = t - z.createdBarIndex
                    closeOK = (c[t] > z.proxVal) if z.isDemand else (c[t] < z.proxVal)
                    z.retestBarIndex = t; z.retestPen = pen; z.touchCount += 1
                    slip = ((c[t] - z.proxVal) if z.isDemand else (z.proxVal - c[t])) / rk if rk > 0 else 0.0
                    slipOK = z.maxEntrySlipR is None or slip <= z.maxEntrySlipR
                    z.retestVolRatio = (v[t] / z.legOutVol) if (z.legOutVol > 0 and v[t] > 0) else 0.0
                    volOK = z.maxRetestVolOverLegOut is None or z.legOutVol <= 0 or v[t] <= 0 or z.retestVolRatio <= z.maxRetestVolOverLegOut
                    strongOK = z.minEntrySlipR is None or slip >= z.minEntrySlipR
                    trendOK = hema is None or z.htfTrendEma is None or t < z.htfTrendEma or ((c[t] > hema[t]) if z.isDemand else (c[t] < hema[t]))
                    if bars < z.minRetestBars or pen > z.maxPenetration or not closeOK or not slipOK or not volOK or not strongOK or not trendOK:
                        z.state = "Failed"
                        z.entryStatus = ("Failed-EarlyRetest" if bars < z.minRetestBars else
                                         "Failed-DeepRetest" if pen > z.maxPenetration else
                                         "Failed-CloseInside" if not closeOK else
                                         "Failed-Slip" if not slipOK else
                                         "Failed-HeavyRetest" if not volOK else
                                         "Failed-WeakConfirm" if not strongOK else "Failed-AgainstTrend")
                    else:
                        z.state = "Tested"; z.entryStatus = "Triggered"; z.entryPrice = c[t]; z.entryBarIndex = t
                        va = volAvg[t] if (not np.isnan(volAvg[t]) and volAvg[t] > 0) else np.nan
                        z.retestVolX = float(v[t] / va) if (v[t] > 0 and not np.isnan(va)) else np.nan
                        z.emaSlopeOK = bool(((e20[t] - e20[max(0, t - 5)]) > 0) == z.isDemand) if t >= 25 else None
                elif touch and not (z.state == "Tested" and wasIn):
                    z.state = "Tested"; z.touchCount += 1
                    if z.touchCount > p["maxTouches"]:
                        z.state = "Broken"
                if z.state not in ("Broken", "Failed"):
                    keep.append(z)
            active = keep
    if lookback_months is None:
        return zones
    return [z for z in zones if z.createdBarIndex >= record_from]


def scan_winrate(df, patterns=None, min_score=None, params=None):
    p = dict(PRESET_WINRATE); p.update(params or {})
    if min_score is not None:
        p["minDensity"] = min_score
    zs = scan_zones(df, params=p)
    return [z for z in zs if z.patternType in patterns] if patterns else zs


def scan_daily(df, params=None):
    p = dict(PRESET_DAILY); p.update(params or {}); return scan_zones(df, p)


WINRATE = dict(patterns=["RBR", "DBR", "DBD", "RBD"], min_score=45, prefer_tfs=["15m", "1h"])


# =============================================================================
# SECTION 5: ALERTS / MTF / TAGS
# =============================================================================

def latest_active_zones(zones: List[Zone], include_tested: bool = True) -> List[Zone]:
    states = {"Fresh"} | ({"Tested"} if include_tested else set())
    return [z for z in zones if z.state in states]


def get_zone_alerts(zones, current_price, min_proximity_pct=0.0, max_proximity_pct=1.0,
                    include_tested=True) -> List[Dict[str, Any]]:
    alerts = []
    for z in latest_active_zones(zones, include_tested=include_tested):
        if z.proxVal <= 0:
            continue
        diff = (current_price - z.proxVal) / z.proxVal if z.isDemand else (z.proxVal - current_price) / z.proxVal
        if not (min_proximity_pct <= diff <= max_proximity_pct):
            continue
        alerts.append({
            "direction": "DEMAND" if z.isDemand else "SUPPLY", "pattern": z.patternType, "category": z.zoneCategory,
            "entry": z.proxVal, "proximal": z.proxVal, "distal": z.distVal, "sl": z.slVal, "tp": z.tpVal,
            "risk_pct": z.riskPct, "is_hq": z.isHQ, "score": z.densityScore, "score10": z.score10,
            "colour_ok": z.baseColourOK, "legout_cover_R": round(z.legOutCoverR, 1),
            "touch_count": z.touchCount, "is_overnight_gap": z.isOvernightGap,
            "legInTR": z.legInTR, "legOutTR": z.legOutTR, "distance_pct": diff * 100, "state": z.state,
            "timestamp": z.timestamp, "reformed_after_break": z.reformedAfterBreak,
            "is_mtf_confluence": z.isMTFConfluence, "is_nested_in_bigger_tf": z.isNestedInBiggerTF,
            "confluence_tfs": z.confluenceTFs,
            "entry_status": z.entryStatus, "entry_price": z.entryPrice, "base_count": z.baseCount,
            "entry_rule": (f"confirm-close: first candle touching proximal must stay in outer {int(z.maxPenetration*100)}% of zone, "
                           f"come >= {z.minRetestBars} candles after leg-out and CLOSE back beyond proximal; enter at that close"),
        })
    alerts.sort(key=lambda a: (-int(a["is_hq"]), a["distance_pct"]))
    return alerts


def flag_multi_timeframe_confluence(zones_by_timeframe, tf_order_small_to_large, only_active=True):
    for tf_zones in zones_by_timeframe.values():
        for z in tf_zones:
            z.isMTFConfluence = False; z.isNestedInBiggerTF = False; z.confluenceTFs = []
    for i, small_tf in enumerate(tf_order_small_to_large):
        for zs in zones_by_timeframe.get(small_tf, []):
            if only_active and zs.state not in ("Fresh", "Tested"):
                continue
            s_lo, s_hi = _zone_range(zs)
            for big_tf in tf_order_small_to_large[i + 1:]:
                for zb in zones_by_timeframe.get(big_tf, []):
                    if only_active and zb.state not in ("Fresh", "Tested"):
                        continue
                    if zb.isDemand != zs.isDemand:
                        continue
                    b_lo, b_hi = _zone_range(zb)
                    if _ranges_overlap(s_lo, s_hi, b_lo, b_hi):
                        zs.isMTFConfluence = True
                        if big_tf not in zs.confluenceTFs:
                            zs.confluenceTFs.append(big_tf)
                        if _ranges_nested(s_lo, s_hi, b_lo, b_hi):
                            zs.isNestedInBiggerTF = True


def zone_log(zones: List[Zone], df: pd.DataFrame = None) -> List[Dict[str, Any]]:
    rows = []
    for z in zones:
        why = {"Waiting": "Fresh — retest abhi nahi aayi", "Triggered": "Entry mili (confirm-close)",
               "Failed-EarlyRetest": f"Retest leg-out ke {z.minRetestBars} candle se pehle aayi",
               "Failed-DeepRetest": f"Retest wick zone ke {int(z.maxPenetration*100)} % se gehri gayi ({z.retestPen:.0%})",
               "Failed-CloseInside": "Retest candle zone ke andar close hui", "Failed-Slip": "Confirm-close proximal se 2R se door",
               "Failed-HeavyRetest": "Retest candle ka volume leg-out se bhari",
               "Failed-WeakConfirm": "Confirm-close proximal se 0.2R se kam aage",
               "Failed-AgainstTrend": "HTF EMA trend ke viruddh entry",
               "Failed-BrokeThrough": "Pehla touch seedhe distal ke paar — limit entry hoti to SL"}.get(z.entryStatus, z.entryStatus)
        rows.append({"time": z.timestamp, "pattern": z.patternType, "side": "Demand" if z.isDemand else "Supply",
                     "proximal": round(z.proxVal, 2), "distal": round(z.distVal, 2), "sl": round(z.slVal, 2), "tp": round(z.tpVal, 2),
                     "risk_pct": round(z.riskPct, 2), "density": z.densityScore, "score10": z.score10, "boring": z.baseCount,
                     "colour_ok": z.baseColourOK, "gap_x_legin": round(z.gapToLegIn, 2), "state": z.state,
                     "legin_vol_x": None if np.isnan(z.legInVolX) else round(z.legInVolX, 2), "legout_vol_x": None if np.isnan(z.legOutVolX) else round(z.legOutVolX, 2),
                     "retest_vol_x": None if np.isnan(z.retestVolX) else round(z.retestVolX, 2), "ema_slope_ok": z.emaSlopeOK,
                     "entry_status": z.entryStatus, "entry_price": round(z.entryPrice, 2) if z.entryPrice else None,
                     "entry_time": (df.index[z.entryBarIndex] if (df is not None and z.entryBarIndex >= 0) else None),
                     "why": why})
    return rows


def zone_highlight_tags(z: Zone) -> List[str]:
    tags = []
    if z.isHQ: tags.append("HQ")
    if z.baseColourOK: tags.append("Boring-Colour")
    if z.legOutCoverR >= 5: tags.append("Powerful-1:5")
    if z.freshBoring: tags.append("Fresh-Boring")
    if z.entryStatus == "Triggered": tags.append("Entry-Triggered")
    if z.baseCount == 1: tags.append("1-Boring")
    if z.hasGenuineGap: tags.append("Gap")
    if z.isOvernightGap: tags.append("Overnight")
    if z.score10 >= 7: tags.append("Score7+")
    if z.reformedAfterBreak: tags.append("Reformed-after-Break")
    if not np.isnan(z.legInVolX) and z.legInVolX >= 1.0: tags.append("LegIn-Vol")
    if not np.isnan(z.retestVolX): tags.append("Quiet-Retest" if z.retestVolX < 1.3 else "Heavy-Retest")
    if z.isNestedInBiggerTF: tags.append(f"Nested-in-{'/'.join(z.confluenceTFs)}")
    elif z.isMTFConfluence: tags.append(f"MTF-{'/'.join(z.confluenceTFs)}")
    return tags


# =============================================================================
# SECTION 5b: v13.3 TARGET-CONTEXT
# =============================================================================
TP_SIGNS = {
    "A": ("Nifty daily close EMA20 ke sahi taraf (demand upar / supply neeche)", (40, 28), (49, 42)),
    "B": ("Higher-TF close EMA20 ke sahi taraf (poori ho chuki HTF candle)", (39, 30), (52, 38)),
    "C": ("Leg-in candle volume >= 20-bar average (institutional arrival)", (42, 29), (52, 43)),
    "D": ("Retest candle volume < 1.3 x average (shaant retest)", (38, 26), (52, 28)),
    "E": ("Own-TF EMA20 slope zone ki disha mein (5 bar)", (37, 32), (50, 42)),
    "F": ("Macro regime: demand -> VIX >= 16.5 ya S&P 20d < 0; supply -> VIX < 16.5", (42, 27), (56, 33)),
}
TP_SCORE_HIGH = 4
TP_SCORE_LOW = 2


def _last_completed_idx(index, at):
    if at is None:
        return len(index) - 1
    t = pd.Timestamp(at)
    tz = getattr(index, "tz", None)
    if tz is not None and t.tz is None: t = t.tz_localize(tz)
    if tz is None and t.tz is not None: t = t.tz_convert(None)
    return int(index.searchsorted(t, side="right")) - 2


def _ema_side(df, at, is_demand, span=20):
    if df is None or len(df) < span + 2:
        return None
    c = df["close"].to_numpy(float) if "close" in df.columns else df["Close"].to_numpy(float)
    j = _last_completed_idx(df.index, at)
    if j < span:
        return None
    e = pd.Series(c).ewm(span=span, adjust=False).mean().to_numpy()
    return int((c[j] > e[j]) == bool(is_demand))


def target_context(z: "Zone", df: pd.DataFrame = None, htf_df: pd.DataFrame = None, market_df: pd.DataFrame = None,
                   vix: Optional[float] = None, spx_ret20: Optional[float] = None, at=None) -> Dict[str, Any]:
    if at is None and df is not None and z.entryBarIndex >= 0:
        at = df.index[z.entryBarIndex]
    r: Dict[str, Any] = {}
    r["A"] = _ema_side(market_df, at, z.isDemand) if market_df is not None else None
    r["B"] = _ema_side(htf_df, at, z.isDemand) if htf_df is not None else None
    r["C"] = None if (z.legInVolX is None or np.isnan(z.legInVolX)) else int(z.legInVolX >= 1.0)
    r["D"] = None if (z.retestVolX is None or np.isnan(z.retestVolX)) else int(z.retestVolX < 1.3)
    if z.emaSlopeOK is not None:
        r["E"] = int(bool(z.emaSlopeOK))
    elif df is not None and len(df) > 30:
        c = df["close"].to_numpy(float); e = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
        r["E"] = int(((e[-1] - e[-6]) > 0) == z.isDemand)
    else:
        r["E"] = None
    if vix is None and spx_ret20 is None:
        r["F"] = None
    elif z.isDemand:
        r["F"] = int((vix is not None and vix >= 16.5) or (spx_ret20 is not None and spx_ret20 < 0))
    else:
        r["F"] = int(vix < 16.5) if vix is not None else None
    known = [k for k in "ABCDEF" if r[k] is not None]
    r["score"] = int(sum(r[k] for k in known)); r["max"] = len(known)
    sc6 = r["score"] * 6.0 / r["max"] if r["max"] else 0.0
    r["label"] = "TP-High" if (r["max"] >= 3 and sc6 >= TP_SCORE_HIGH) else ("TP-Low" if (r["max"] >= 3 and sc6 <= TP_SCORE_LOW) else "TP-Mid")
    r["why"] = [("[OK] " if r[k] else "[XX] ") + TP_SIGNS[k][0] for k in known]
    r["facts"] = dict(legInVolX=z.legInVolX, legOutVolX=z.legOutVolX, baseVolX=z.baseVolX, legOutOverLegIn=z.legOutOverLegIn,
                      retestVolX=z.retestVolX, emaSlopeOK=z.emaSlopeOK)
    return r


def target_tags(ctx: Dict[str, Any]) -> List[str]:
    if not ctx or not ctx.get("max"):
        return []
    icon = {"TP-High": "TP-HIGH ", "TP-Low": "TP-LOW ", "TP-Mid": ""}[ctx["label"]]
    return [f"{icon}{ctx['label']} {ctx['score']}/{ctx['max']}",
            "".join(k + ("Y" if ctx[k] else "N") for k in "ABCDEF" if ctx[k] is not None)]


def target_study_table() -> List[Dict[str, Any]]:
    return [dict(sign=k, meaning=v[0], v121_yes=v[1][0], v121_no=v[1][1], v132_yes=v[2][0], v132_no=v[2][1]) for k, v in TP_SIGNS.items()]


# =============================================================================
# SECTION 6: DIAGNOSTICS / BACKTEST / EXECUTION MODEL
# =============================================================================

def diagnose_bar(df: pd.DataFrame, at_index, params: Optional[dict] = None) -> List[Dict[str, Any]]:
    """12-rule core ke saath bar-level diagnostic (t = leg-out index)."""
    p = _apply_tf_overrides(df, _resolve_params(params))
    o, h, l, c, v, tr, atr, volSma = _prep(df, p)
    t = int(at_index) if isinstance(at_index, (int, np.integer)) else int(df.index.get_loc(at_index))
    bodyH = np.maximum(o, c); bodyL = np.minimum(o, c); rng = h - l
    upW = np.where(rng > 0, (h - bodyH) / np.where(rng > 0, rng, 1.0), 0.0)
    loW = np.where(rng > 0, (bodyL - l) / np.where(rng > 0, rng, 1.0), 0.0)
    bodyPct = np.where(rng > 0, np.abs(c - o) / np.where(rng > 0, rng, 1.0), 0.0)
    atrSma = pd.Series(tr).rolling(p["atrPeriod"], min_periods=p["atrPeriod"]).mean().to_numpy()
    reports = []
    for bc in range(p["minBase"], p["maxBase"] + 1):
        rep = {"baseCount": bc, "legOutTimestamp": df.index[t]}
        li = t - bc - 1
        if li < 1 or rng[li] <= 0 or rng[t] <= 0:
            rep["result"] = "SKIP"; reports.append(rep); continue
        bidx = list(range(t - bc, t)); b0 = bidx[0]
        liBull = c[li] > o[li]; isD = c[t] > o[t]; isS = o[t] > c[t]
        a = atrSma[li]
        rep["R1_legin_non_doji"] = bool((c[li] != o[li]))
        rep["R2_legin_wick50"] = bool((upW[li] + loW[li]) <= p["liWickTotal"])
        rep["R3_legin_lower25"] = bool(loW[li] <= p["liLowerMax"])
        rep["R4_legin_closing25"] = bool(((upW[li] if liBull else loW[li]) <= p["liWickTotal"] / 2))
        clv = (c[li] - l[li]) / rng[li] if liBull else (h[li] - c[li]) / rng[li]
        rep["R7_legin_close60"] = bool(clv >= p["liCloseStrong"])
        rep["R11_boring_body20"] = all(bodyPct[b] <= p["boringBodyMax"] for b in bidx)
        rep["legout_non_doji"] = bool(c[t] != o[t])
        rep["legout_wick45"] = bool((upW[t] + loW[t]) <= p["loFilledMax"])
        rep["N1_ladder"] = bool(abs(c[li] - o[li]) > abs(c[b0] - o[b0]) and abs(c[t] - o[t]) > abs(c[li] - o[li]))
        rep["N5_atr"] = (not np.isnan(a)) and a > 0 and (h[li] - l[li]) >= a and all((h[b] - l[b]) < a for b in bidx) and (h[t] - l[t]) > a
        rep["R9_legout_tr1_5base"] = bool((h[t] - l[t]) >= p["loTrBoring"] * (h[b0] - l[b0]))
        outClv = (c[t] - l[t]) / rng[t] if isD else (h[t] - c[t]) / rng[t]
        rep["R10_legout_close60"] = bool(outClv >= p["loCloseStrong"])
        band_lo, band_hi = sorted((c[bidx[-1]], o[t])); bod_lo, bod_hi = sorted((o[t], c[t]))
        rep["N2_white_area"] = not (bod_lo < band_hi and bod_hi > band_lo)
        pv = li - 1; pvBull = c[pv] > o[pv]; pvBear = o[pv] > c[pv]
        pvCol = "green" if pvBull else ("red" if pvBear else "doji"); liCol = "green" if liBull else "red"
        rep["N3_no_trap"] = True
        if pvCol != liCol:
            span = bodyH[li] - bodyL[li]
            if span > 0:
                ov = min(bodyH[pv], bodyH[li]) - max(bodyL[pv], bodyL[li])
                rep["N3_no_trap"] = bool(ov / span <= p["trapCoverLimit"])
        pat = ("RBR" if liBull else "DBR") if isD else ("DBD" if liBear else "RBD")
        rep["N4_dbrrbd_open"] = True if pat not in ("DBR", "RBD") else bool(bodyL[li] <= o[t] <= bodyH[li])
        bH = h[bidx].max(); bL = l[bidx].min(); bBH = bodyH[bidx].max(); bBL = bodyL[bidx].min()
        prox = bBH if isD else bBL; dist = bL if isD else bH; risk = abs(prox - dist)
        rep["proximal"] = prox; rep["distal(SL)"] = dist; rep["sl"] = dist
        rep["risk_pct"] = 100 * risk / prox if prox else 0.0
        rep["R8_band_ok"] = bool(100 * risk / prox <= p["bandMaxPct"]) if prox else False
        rep["pattern"] = pat
        rep["FINAL_VALID"] = bool(rep["R1_legin_non_doji"] and rep["R2_legin_wick50"] and rep["R3_legin_lower25"]
                                  and rep["R4_legin_closing25"] and rep["R7_legin_close60"] and rep["R11_boring_body20"]
                                  and rep["legout_non_doji"] and rep["legout_wick45"] and rep["N1_ladder"] and rep["N5_atr"]
                                  and rep["R9_legout_tr1_5base"] and rep["R10_legout_close60"] and rep["N2_white_area"]
                                  and rep["N3_no_trap"] and rep["N4_dbrrbd_open"] and rep["R8_band_ok"])
        reports.append(rep)
    return reports



_hema_cache = {}


def simulate(zones, df, rr=3.0, max_hold=30, entry=ENTRY_MODE, start=None, end=None,
             max_pen=None, min_bars=None, max_bars=None, max_slip=None):
    o, hh, ll, cc, vv = _cols(df); n = len(hh); out = []
    tz = getattr(df.index, "tz", None)
    st = pd.Timestamp(start).tz_localize(tz) if (start is not None and tz is not None and pd.Timestamp(start).tz is None) else (pd.Timestamp(start) if start is not None else None)
    en = pd.Timestamp(end).tz_localize(tz) if (end is not None and tz is not None and pd.Timestamp(end).tz is None) else (pd.Timestamp(end) if end is not None else None)
    for z in zones:
        if st is not None and z.timestamp < st:
            continue
        if en is not None and z.timestamp > en:
            continue
        d = z.isDemand; sl = z.slVal
        line = z.proxVal if entry != "mid" else (min(z.proxVal, z.distVal) + 0.5 * abs(z.proxVal - z.distVal))
        if abs(line - sl) <= 0:
            continue
        s = z.createdBarIndex + 1; e = min(s + max_hold, n); ent = None; ei = None; done = False
        if entry == "legout":
            ent = cc[z.createdBarIndex]; ei = z.createdBarIndex
            if (ent <= line) if d else (ent >= line):
                continue
        for i in range(s, e):
            if ent is None:
                touch = (ll[i] <= line) if d else (hh[i] >= line)
                if not touch:
                    continue
                hitsl = (ll[i] <= sl) if d else (hh[i] >= sl)
                if entry in ("limit", "prox", "mid"):
                    ent = line; ei = i
                    if hitsl:
                        risk = abs(ent - sl)
                        out.append(dict(timestamp=z.timestamp, side="LONG" if d else "SHORT", pattern=z.patternType, entry=ent, sl=sl,
                                        tp=ent + rr * risk if d else ent - rr * risk, entry_idx=i, exit_idx=i, bars=i - z.createdBarIndex,
                                        outcome="SL", net_r=-1.0, risk=risk, risk_pct=100 * risk / ent, zone=z)); done = True; break
                else:
                    if hitsl or not ((cc[i] > line) if d else (cc[i] < line)):
                        break
                    mp = z.maxPenetration if max_pen is None else max_pen
                    mb = z.minRetestBars if min_bars is None else min_bars
                    pen = ((line - ll[i]) if d else (hh[i] - line)) / abs(line - sl)
                    bars = i - z.createdBarIndex
                    ms = z.maxEntrySlipR if max_slip is None else max_slip
                    slip = ((cc[i] - line) if d else (line - cc[i])) / abs(line - sl)
                    mrv = getattr(z, "maxRetestVolOverLegOut", None); lov = getattr(z, "legOutVol", 0.0)
                    heavy = mrv is not None and lov > 0 and vv[i] > 0 and vv[i] > mrv * lov
                    mns = getattr(z, "minEntrySlipR", None); weak = mns is not None and slip < mns
                    hte = getattr(z, "htfTrendEma", None); against = False
                    if hte is not None and i >= hte:
                        if _hema_cache.get(("k", id(df), hte)) is None:
                            _hema_cache[("k", id(df), hte)] = pd.Series(cc).ewm(span=int(hte), adjust=False).mean().to_numpy()
                        he = _hema_cache[("k", id(df), hte)]
                        against = (cc[i] < he[i]) if d else (cc[i] > he[i])
                    if pen > mp or bars < mb or (max_bars is not None and bars > max_bars) or (ms is not None and slip > ms) or heavy or weak or against:
                        break
                    ent = cc[i]; ei = i; continue
            risk = abs(ent - sl); tp = ent + rr * risk if d else ent - rr * risk
            if (ll[i] <= sl) if d else (hh[i] >= sl):
                out.append(dict(timestamp=z.timestamp, side="LONG" if d else "SHORT", pattern=z.patternType, entry=ent, sl=sl, tp=tp, entry_idx=ei, exit_idx=i,
                                bars=i - z.createdBarIndex, outcome="SL", net_r=-1.0, risk=risk, risk_pct=100 * risk / ent, zone=z)); done = True; break
            if (hh[i] >= tp) if d else (ll[i] <= tp):
                out.append(dict(timestamp=z.timestamp, side="LONG" if d else "SHORT", pattern=z.patternType, entry=ent, sl=sl, tp=tp, entry_idx=ei, exit_idx=i,
                                bars=i - z.createdBarIndex, outcome="TP", net_r=rr, risk=risk, risk_pct=100 * risk / ent, zone=z)); done = True; break
        if ent is not None and not done:
            risk = abs(ent - sl); r = ((cc[e - 1] - ent) if d else (ent - cc[e - 1])) / risk
            out.append(dict(timestamp=z.timestamp, side="LONG" if d else "SHORT", pattern=z.patternType, entry=ent, sl=sl,
                            tp=ent + rr * risk if d else ent - rr * risk, entry_idx=ei, exit_idx=e - 1, bars=e - 1 - z.createdBarIndex,
                            outcome="TIME", net_r=r, risk=risk, risk_pct=100 * risk / ent, zone=z))
    return out


def realistic_roi(zones, df, rr=3.0, risk_pct=0.005, capital=25000.0, max_hold=30,
                  start=None, end=None, patterns=None, buffer=None, entry_mode=ENTRY_MODE):
    zs = [z for z in zones if (not patterns or z.patternType in patterns)]
    if buffer is not None:
        o, hh, ll, cc, _ = _cols(df); atr = _wilder_atr_from_tr(_true_range(hh, ll, cc), 14)
        import copy
        zs2 = []
        for z in zs:
            a = atr[z.createdBarIndex]
            if np.isnan(a):
                zs2.append(z); continue
            z2 = copy.copy(z); z2.slVal = z.distVal - buffer * a if z.isDemand else z.distVal + buffer * a; zs2.append(z2)
        zs = zs2
    trades = simulate(zs, df, rr=rr, max_hold=max_hold, entry=entry_mode, start=start, end=end)
    if not trades:
        return {"n_trades": 0}
    rows = []
    for t in trades:
        shares = max(1, int(capital * risk_pct / max(t["risk"], 1e-9))); pos = shares * t["entry"]
        if pos > capital:
            shares = max(1, int(capital / max(t["entry"], 1e-9))); pos = shares * t["entry"]
        gross = t["net_r"] * t["risk"] * shares; cst = _cost(pos, pos)
        rows.append({**{k: v for k, v in t.items() if k != "zone"}, "shares": shares, "gross": gross, "cost": cst, "net": gross - cst})
    dfr = pd.DataFrame(rows); n = len(dfr); wins = int((dfr.net_r > 0).sum())
    return {"n_trades": n, "wins": wins, "win_pct": 100 * wins / n, "breakeven_win_pct": 100.0 / (1.0 + rr),
            "gross_pnl": dfr.gross.sum(), "cost_pnl": dfr.cost.sum(), "net_pnl": dfr.net.sum(),
            "net_roi_pct": 100 * dfr.net.sum() / capital, "gross_ev_R": dfr.net_r.mean(), "total_R": dfr.net_r.sum(),
            "avg_hold_bars": dfr.bars.mean(), "avg_risk_pct": dfr.risk_pct.mean(),
            "outcome_counts": dfr.outcome.value_counts().to_dict(), "avg_cost": dfr.cost.mean(),
            "avg_size": (dfr.entry * dfr.shares).mean(), "trades": rows}


def _zone_outcome(z, hh, ll, cc, lookback):
    ci = z.createdBarIndex; s = ci + 1; e = min(ci + 1 + lookback, len(hh))
    if s >= e:
        return None
    prox, sl, dist = z.proxVal, z.slVal, z.distVal; d = z.isDemand
    risk = (prox - sl) if d else (sl - prox)
    if risk <= 0:
        return None
    tested = False; wins = set(); mfe = 0.0
    for i in range(s, e):
        if (cc[i] < dist) if d else (cc[i] > dist):
            break
        if (ll[i] <= prox) if d else (hh[i] >= prox):
            tested = True
        if tested:
            mfe = max(mfe, ((hh[i] - prox) if d else (prox - ll[i])) / risk)
            for k in EVAL_RR:
                if k not in wins and ((hh[i] >= prox + k * risk) if d else (ll[i] <= prox - k * risk)):
                    wins.add(k)
    return tested, wins, mfe


def backtest_summary(zones, df, lookback=30):
    _, hh, ll, cc, _ = _cols(df); rows = []
    for z in zones:
        r = _zone_outcome(z, hh, ll, cc, lookback)
        if r is None:
            continue
        tested, wins, mfe = r
        rows.append({"tested": int(tested), "hq": int(z.isHQ), "score": z.densityScore, "mfe": mfe,
                     **{f"w{int(k * 10)}": int(k in wins) for k in EVAL_RR}})
    if not rows:
        return {"zones": 0}
    res = pd.DataFrame(rows); n = len(res); tested = int(res.tested.sum()); t = res[res.tested == 1]
    out = {"zones": n, "tested": tested, "tested_pct": 100 * tested / n}
    for k in EVAL_RR:
        col = f"w{int(k * 10)}"; out[f"win_{k}R_tested"] = 100 * t[col].sum() / tested if tested else float("nan")
    out["avg_mfe_tested"] = t.mfe.mean() if tested else float("nan")
    out["hq_pct"] = 100 * res.hq.sum() / n; out["avg_score"] = res.score.mean()
    return out


def recommended_trade_setup():
    return {
        "patterns": ["RBR", "DBR", "DBD", "RBD"],
        "min_score": 45, "max_score": 75,
        "timeframes": ["1h", "4h"],
        "entry_mode": "confirm",
        "exit_mode": "target",
        "slBufferAtr": 0.0,
        "targetRR": 3.0,
        "max_hold": 30,
        "risk_pct": 0.005,
        "capital": 25000.0,
        "winrate_preset": PRESET_WINRATE,
        "maxPenetration": 0.5, "minRetestBars": 2, "maxBase": 3, "baseColour": "require",
        "maxGapLegIn": 1.0, "noAdverseGap": True, "maxEntrySlipR": 2.0,
        "note": ("v14.0 FINAL 12-RULE CORE: leg-in (non-doji, wick<=50%, lower wick<=25%, close-strong 60%, TR>=ATR); "
                 "boring 1-3 (body<=20% classic UOC, TR<ATR); leg-out (non-doji, wick<=45%, body>leg-in ladder, "
                 "TR>=1.5x boring, close-strong 60%, TR>ATR); band<=0.75%; SL=distal buffer 0; RR 1:3; wick-fresh kill. "
                 "Zone lines: proximal=boring body edge, distal=boring wick extreme. Entry engine = zone_core confirm-close."),
    }


# =============================================================================
# SECTION 7: EXTRA VALIDATION LAYERS (API compatibility — all verdicts HARMFUL/neutral)
# =============================================================================

EXTRA_LAYER_DEFAULTS = dict(layer_A=False, layer_B=False, layer_C=False, layer_D=False,
                            half_legin_body_min=0.65, swing_lookback=3, htf_gap_window=8, mid_tol=0.001)


def extra_layer_verdict():
    return [
        ("A", "half-TF leg-in body >= 65%", "HARMFUL", "crops winners"),
        ("B", "half-TF leg-out middle-break + swing", "MIXED/neutral", "no reliable edge"),
        ("C", "HTF zone-in-zone confirmation", "HARMFUL", "keeps worst zones"),
        ("D", "HTF 2-candle opening-gap overlap", "MIXED/neutral", "no reliable edge"),
    ]


def apply_extra_validation(zones, ltf_df, half_df=None, htf_df=None, htf_zones=None, params=None):
    p = dict(EXTRA_LAYER_DEFAULTS); p.update(params or {})
    if not any(p[f"layer_{L}"] for L in "ABCD"):
        return list(zones), [{"A": None, "B": None, "C": None, "D": None, "kept": True} for _ in zones]
    if p["layer_C"] and htf_zones is None and htf_df is not None:
        htf_zones = scan_zones(htf_df)
    kept, report = [], []
    for z in zones:
        zr = {"A": None, "B": None, "C": None, "D": None}
        if p["layer_C"] and htf_zones is not None:
            zr["C"] = any(hz.isDemand == z.isDemand and hz.timestamp <= z.timestamp and
                          _ranges_overlap(*_zone_range(z), *_zone_range(hz)) for hz in htf_zones)
        ok = all(zr[L] is None or zr[L] for L in "ABCD" if p[f"layer_{L}"])
        zr["kept"] = ok; report.append(zr)
        if ok:
            kept.append(z)
    return kept, report


if __name__ == "__main__":
    import sys
    df = pd.read_csv(sys.argv[1], index_col=0, parse_dates=True)
    zs = scan_zones(df); tr = simulate(zs, df)
    print(f"{__version__}: zones={len(zs)} trades={len(tr)} win={100 * np.mean([t['net_r'] > 0 for t in tr]) if tr else 0:.1f}%")
    for t in tr[-8:]:
        print(t["timestamp"], t["side"], round(t["entry"], 2), "SL", round(t["sl"], 2), "TP", round(t["tp"], 2), t["outcome"], round(t["net_r"], 2))
