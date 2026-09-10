# -*- coding: utf-8 -*-
"""
zone_core.py — v15.0-pine  (Pine Script v6 "Zone" indicator ka 1:1 detection core, aapke app ke liye)
=====================================================================================================
  YEH FILE ka DETECTION CORE ab PINE SCRIPT v6 "Zone" indicator ka BILKUL same (1:1) port hai —
  same parameters, same checks (same order), same scoring, same zone levels, same state machine:

    • LEG-IN   : body_pct >= legInMinBodyPct(0.60); opposite-colour prev overlap >=
                 rejectOppositeCoverPct(0.50) -> reject; legInTR >= legInMinAtrMult*ATR(1.0);
                 legInTR >= (1.5 if 1 base else legInToBaseSizeMult 2.0) * maxBaseTR.
    • BASE     : 1-3 candles, har base TR <= maxBaseAtrMult*ATR(1.0); maxBaseTR > 0.
    • LEG-OUT  : directional; TR >= legOutTrMult*ATR(1.2); wick_pct <= maxWickPct(0.30);
                 TR >= legOutMinTrRatio*legInTR(1.0) AND legInTR > maxBaseTR; vol > leg-in vol.
    • IMBALANCE: demand legOutLow>maxBaseHigh / supply legOutHigh<minBaseLow (genuine gap)
                 OR leg-out close beyond leg-in extreme  -> REQUIRED.
    • ENGULF   : leg-out BODY poore base ko engulf karta hai BUT genuine gap nahi -> reject.
    • CLASSIFY : RBR/DBR/DBD/RBD via leg-in colour + CLV>=minClvPct(0.60) + leg-out direction.
                 zoneCategory = Continuation(RBR/DBD) / Reversal(DBR/RBD).
    • SCORING  : Pine ke exact bonuses (0-125); gate minValidScore(40); HQ hqScoreThreshold(90).
    • LEVELS   : demand proxVal=maxBaseHigh, distVal=minBaseLow ; supply vice-versa.
                 SL = distal ∓ slBufferAtr*ATR(0.1); TP = proxVal ± risk*targetRR(5.0).
                 legOutMidLevel = testedLegOutRetracePct(0.50) retrace of leg-out.
    • STATE    : Fresh -> Tested (price @ legOutMidLevel, touchCount++) -> Broken (@ distal ya
                 touchCount > maxTestedCount(2)).
    • DEDUP    : same direction AND |proxVal diff| < duplicateAtr(0.25)*ATR (last 11 non-Broken).

  ZONE CORE ENGINE / PUBLIC API BILKUL SAME (aapke app zscan.py/app.py/options.py ke liye):
    Zone, settings(), scan_zones(), scan_winrate(), scan_daily(), latest_active_zones(),
    get_zone_alerts(), flag_multi_timeframe_confluence(), zone_log(), zone_highlight_tags(),
    target_context() (v13.3 TP-SCORE), simulate(), realistic_roi(), backtest_summary(),
    recommended_trade_setup(), diagnose_bar(), apply_extra_validation(), _cost().
  ATR = Pine ta.rma (Wilder RMA). Entry/exit engine (simulate/realistic_roi) zone_core ka hi hai.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import numpy as np
import pandas as pd

__version__ = "v15.0-pine"

# =============================================================================
# SECTION 1: RULES / PARAMS  (Pine v6 defaults + retained old params for compat)
# =============================================================================

DEFAULT_PARAMS = dict(
    # ---------- risk / money (Pine v6) ----------
    accountCapital=25000.0,
    riskPct=0.5,
    targetRR=5.0,                   # PINE v6: Target RR = 5.0
    slBufferAtr=0.1,                # PINE v6: SL Buffer ATR = 0.1
    # ---------- indicators ----------
    atrPeriod=14,
    volSmaPeriod=20,
    # ---------- PINE v6 CORE (1:1) ----------
    legInMinBodyPct=0.60,           # Pine "Leg-In Min Body %"
    minClvPct=0.60,                 # Pine "Min CLV %"
    legInToBaseSizeMult=2.0,        # Pine "Leg-In to Base Size Multiplier" (2-3 base; 1 base = 1.5)
    legInMinAtrMult=1.0,            # Pine "Leg-In Min ATR Multiplier"
    maxBaseAtrMult=1.0,             # Pine "Max Base TR ATR Multiplier"
    maxWickPct=0.30,                # Pine "Max Wick %" (leg-out total wick)
    minBase=1, maxBase=3,           # Pine Min/Max Base Count (HARD_MAX_BASE_COUNT=3)
    legOutTrMult=1.2,               # Pine "Leg-Out TR Multiplier"
    legOutMinTrRatio=1.0,           # Pine "Leg-Out Min TR Ratio vs Leg-In"
    hqLegInAtrMult=1.5,             # Pine "HQ Leg-In ATR Multiplier"
    hqLegOutTrMult=2.0,             # Pine "HQ Leg-Out TR Multiplier"
    useImbalance=True,              # Pine "Use Imbalance"
    genuineGapBonus=10,             # Pine "Genuine Gap Score Bonus"
    overnightGapBonus=15,           # Pine "Overnight Gap Score Bonus"
    rejectOppositeCoverPct=0.50,    # Pine "Reject Opposite Cover %"
    minValidScore=40,               # Pine "Min Valid Score" (gate)
    hqScoreThreshold=90,            # Pine "HQ Score Threshold"
    legOutBodyHeavyPct=0.60,        # Pine "Leg-Out Body Heavy Pressure %"
    testedLegOutRetracePct=0.50,    # Pine "Tested Leg-Out Retrace %"
    maxTestedCount=2,               # Pine "Max Tested Count"
    # ---------- retained (inert under Pine core; zscan/compat) ----------
    liWickTotal=0.50, liLowerMax=0.25, liCloseStrong=0.60, boringBodyMax=0.20,
    loFilledMax=0.45, loTrBoring=1.5, loCloseStrong=0.60, bandMaxPct=0.75, trapCoverLimit=0.5,
    legInMinClv=0.60, legInToBaseMult=1.5, legInMinAtr=0.0, rejectOppCoverPct=0.10,
    legOutMaxWickPct=0.40, legOutToLegInRatio=1.3, legOutVolGate=False, gapBaseLegOut="none",
    trapGuard=False, freshBoring=False, imbalance=True, engulfGate=True, legOutMinClv=None,
    legOutToBaseMult=None, proxMode="body", proxBodyEdge="near", distMode="wick", slMode="distal",
    slProxAtr=0.3, fitRR=None, minRiskAtr=0.15,
    useDensity=True, minDensity=45, maxDensity=75, useScore=False, minScore=5, maxScore=None,
    maxGapLegIn=1.0, maxGapRisk=None, noAdverseGap=True, maxRiskPct=None, maxRiskAtr=None,
    maxEntrySlipR=2.0, minEntrySlipR=0.2, htfTrendEma=None, htfTrendAt="entry",
    maxPenetration=0.5, minRetestBars=2, legOutVolMin=None, legOutVolOverLegIn=1.2,
    baseVolMax=None, legInVolOverBase=None, maxRetestVolOverLegOut=None, minGapLegIn=None,
    atrRegimeMin=None, atrRegimeMax=None, atrRegimePeriod=50, maxPrevDayLoc=None,
    ltfOverrides=dict(legOutVolMin=1.3, minGapLegIn=-0.02, atrRegimeMin=0.9, atrRegimeMax=1.3,
                      minRetestBars=4, maxPrevDayLoc=0.5, maxRetestVolOverLegOut=0.8),
    dailyOverrides=dict(legOutVolOverLegIn=None), autoTF=True, maxRetestBars=None,
    opposingZoneRR=None, followUpLookback=0, htfZones=None, requireFollowUp=False,
    trendEma=None, demandOnly=False, duplicateAtr=0.25, maxTouches=2,
)

_ALIASES = {
    "maxWickPct": "maxWickPct",
    "legOutMinTrRatio": "legOutMinTrRatio",
    "legInToBaseSizeMultSingleBase": "legInToBaseSizeMult",
    "minValidScore": "minValidScore",
    "maxBaseCount": "maxBase",
    "minBaseCount": "minBase",
    "minClvPct": "minClvPct",
    "rejectOppositeCoverPct": "rejectOppositeCoverPct",
    "legInMinAtrMult": "legInMinAtrMult",
    "volume_gate": "legOutVolGate",
    "score_gate": "useDensity",
}
_HARD_MAX_BASE_COUNT = 3

# ---------------- PRESETS ----------------
PRESET_FINAL   = {}
PRESET_V121    = dict(autoTF=False, legOutVolOverLegIn=None, minEntrySlipR=None)
PRESET_WINRATE = dict(legInVolOverBase=1.0)
PRESET_V103    = dict()
PRESET_DAILY   = dict(demandOnly=True)
# v15.0 — DEFAULT detection ab PINE v6 core hi hai (scan_zones default).
PRESET_FINAL12 = dict()   # no-op (compat)

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
        ("v15.0", "v14.0", "DETECTION CORE", "Merged Pine Script v6 'Zone' indicator as the 1:1 detection core: exact Pine params/checks/order/scoring/levels/state-machine. API/engine (Zone, settings, scan_zones, alerts, MTF, target_context, simulate, realistic_roi) UNCHANGED. targetRR 3.0->5.0, slBufferAtr 0.0->0.1, ATR = ta.rma (Wilder), proximal = base wick extreme, minValidScore=40 gate, HQ=90."),
        ("v14.0", "v13.4", "DETECTION CORE", "Merged FINAL 12-RULE spec as the core detection (superseded by v15.0 Pine core)."),
    ]


def _resolve_params(params):
    p = dict(DEFAULT_PARAMS)
    for k, v in (params or {}).items():
        if k in p:
            p[k] = v
        elif k in _ALIASES:
            tgt = _ALIASES[k]
            if tgt:
                p[tgt] = v
    p["maxBase"] = max(1, min(int(p["maxBase"]), _HARD_MAX_BASE_COUNT))
    p["minBase"] = max(1, min(int(p["minBase"]), p["maxBase"]))
    return p


# =============================================================================
# SECTION 2: DATA STRUCTURES  (UNCHANGED — app API)
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


def _rma(series, length):
    """Pine ta.rma (custom_atr): SMA seed + Wilder recursion (identical to pine_zone_v6.rma)."""
    n = len(series); out = np.full(n, np.nan)
    if n < length:
        return out
    out[length - 1] = np.mean(series[:length])
    for i in range(length, n):
        out[i] = (series[i] + (length - 1) * out[i - 1]) / length
    return out


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
    atr = _rma(tr, p["atrPeriod"])           # PINE v6: ATR = ta.rma (Wilder)
    vol_sma = pd.Series(v).rolling(p["volSmaPeriod"]).mean().to_numpy()
    return o, h, l, c, v, tr, atr, vol_sma


def _cost(buy_turn, sell_turn):
    br = min(_IR_BROKER * buy_turn, _IR_BROKER_CAP) + min(_IR_BROKER * sell_turn, _IR_BROKER_CAP)
    return br + _IR_STT * sell_turn + _IR_EXCH * (buy_turn + sell_turn) + _IR_SEBI * (buy_turn + sell_turn) + \
        _IR_GST * (br + _IR_EXCH * (buy_turn + sell_turn) + _IR_SEBI * (buy_turn + sell_turn)) + _IR_STAMP * buy_turn


cost = _cost


# =============================================================================
# SECTION 4: CORE SCANNING ENGINE  (PINE v6 detection + state machine)
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
    bodyH = np.maximum(o, c); bodyL = np.minimum(o, c); rng = h - l
    safe = np.where(rng > 0, rng, 1.0)
    bodyPct = np.where(rng > 0, np.abs(c - o) / safe, 0.0)
    upW = np.where(rng > 0, (h - bodyH) / safe, 0.0); loW = np.where(rng > 0, (bodyL - l) / safe, 0.0)
    e20 = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
    zones: List[Zone] = []; active: List[Zone] = []
    start = max(p["atrPeriod"], p["maxBase"] + 3, 11)      # Pine: bar_index >= max(atrPeriod, maxBase+3, 11)
    record_from = max(start, _resolve_start_bar_for_lookback(df, lookback_months))

    for t in range(start, n):
        if np.isnan(atr[t]):
            continue
        found = False
        for bc in range(p["minBase"], p["maxBase"] + 1):
            if found:
                break
            legOutIdx = 0
            legInIdx = bc + 1
            prevIdx = legInIdx + 1
            li = t - legInIdx          # leg-in index (chronological)
            pv = t - prevIdx           # candle before leg-in
            if li < 1 or pv < 0 or rng[li] <= 0:
                continue
            a_legIn = atr[li]
            if np.isnan(a_legIn) or a_legIn <= 0:
                continue

            # ================= LEG-IN (Pine) =================
            legInTR = tr[li]
            legInRng = rng[li]
            if legInRng <= 0 or bodyPct[li] < p["legInMinBodyPct"]:
                continue
            liBull = c[li] > o[li]; liBear = o[li] > c[li]
            if not (liBull or liBear):
                continue
            pvBull = c[pv] > o[pv]; pvBear = o[pv] > c[pv]
            isOppositeColor = (liBull and pvBear) or (liBear and pvBull)
            if isOppositeColor:
                pBH, pBL = bodyH[pv], bodyL[pv]
                overlap = max(0.0, min(pBH, h[li]) - max(pBL, l[li]))
                if overlap / legInRng >= p["rejectOppositeCoverPct"]:
                    continue
            bullClv = (c[li] - l[li]) / legInRng
            bearClv = (h[li] - c[li]) / legInRng

            # ================= BASE (Pine: 1-3, har base TR <= maxBaseAtrMult*ATR) =================
            bidx = list(range(t - bc, t))
            allBaseValid = True
            maxBaseTR = 0.0; maxBaseHigh = -1.0; minBaseLow = 1000000000.0
            for b in range(1, bc + 1):
                kb = t - b
                a_b = atr[kb]
                if np.isnan(a_b):
                    allBaseValid = False; break
                bTR = tr[kb]
                if bTR > (p["maxBaseAtrMult"] * a_b):
                    allBaseValid = False; break
                if bTR > maxBaseTR: maxBaseTR = bTR
                if h[kb] > maxBaseHigh: maxBaseHigh = h[kb]
                if l[kb] < minBaseLow: minBaseLow = l[kb]
            if (not allBaseValid) or maxBaseTR == 0:
                continue
            effMult = 1.5 if bc == 1 else p["legInToBaseSizeMult"]
            if legInTR < (effMult * maxBaseTR):
                continue
            if legInTR < (p["legInMinAtrMult"] * a_legIn):
                continue

            # ================= LEG-OUT (Pine) =================
            a_now = atr[t]
            legOutTR = tr[t]
            legOutHigh, legOutLow, legOutClose, legOutOpen = h[t], l[t], c[t], o[t]
            legOutVol = v[t]
            isD = c[t] > o[t]; isS = o[t] > c[t]
            if not (isD or isS):
                continue
            isLegOutExplosive = legOutTR >= (p["legOutTrMult"] * a_now)
            isLegOutWickValid = (upW[t] + loW[t]) <= p["maxWickPct"]
            passesTRHierarchy = (legOutTR >= p["legOutMinTrRatio"] * legInTR) and (legInTR > maxBaseTR)
            passesVolume = legOutVol > v[li]
            overnight = dates is not None and dates[t] != dates[t - 1]

            # ================= IMBALANCE & GAP (Pine) =================
            hasImbalance = True; hasGenuineGap = False; gapSize = 0.0
            if p["useImbalance"]:
                if isD:
                    hasGenuineGap = legOutLow > maxBaseHigh
                    hasImbalance = hasGenuineGap or (legOutClose > h[li])
                    gapSize = max(0.0, legOutLow - maxBaseHigh)
                elif isS:
                    hasGenuineGap = legOutHigh < minBaseLow
                    hasImbalance = hasGenuineGap or (legOutClose < l[li])
                    gapSize = max(0.0, minBaseLow - legOutHigh)

            # ================= ENGULF GUARD (Pine) =================
            loBH, loBL = max(legOutOpen, legOutClose), min(legOutOpen, legOutClose)
            legOutBodyEngulfsBase = (loBL <= minBaseLow) and (loBH >= maxBaseHigh)
            if legOutBodyEngulfsBase and not hasGenuineGap:
                continue

            # ================= CLASSIFICATION (Pine) =================
            isRBR = liBull and (bullClv >= p["minClvPct"]) and isD
            isDBR = liBear and (bearClv >= p["minClvPct"]) and isD
            isDBD = liBear and (bearClv >= p["minClvPct"]) and isS
            isRBD = liBull and (bullClv >= p["minClvPct"]) and isS
            isValid = ((isRBR or isDBR or isDBD or isRBD) and isLegOutExplosive and isLegOutWickValid
                       and passesTRHierarchy and passesVolume and hasImbalance)
            if not isValid:
                continue

            # ================= SCORING (Pine exact bonuses, 0-125) =================
            densityScore = 0
            if bc == 1:
                densityScore += 15
            if legInTR >= (p["hqLegInAtrMult"] * a_legIn):
                densityScore += 10
            if legOutTR >= (p["hqLegOutTrMult"] * legInTR):
                densityScore += 15
            if (legInTR >= 2.0 * maxBaseTR) and (legOutTR >= 2.0 * legInTR):
                densityScore += 15
            if not np.isnan(volSma[t]) and legOutVol > volSma[t]:
                densityScore += 10
            if isD:
                legOutBodyPos = (legOutClose - legOutLow) / rng[t] if rng[t] > 0 else 0.0
                if isDBR:
                    if (legOutBodyPos >= 0.80) or (bodyPct[t] >= p["legOutBodyHeavyPct"]):
                        densityScore += 15
                else:
                    if legOutBodyPos >= 0.80:
                        densityScore += 15
            else:
                legOutBodyPos = (legOutHigh - legOutClose) / rng[t] if rng[t] > 0 else 0.0
                if legOutBodyPos >= 0.80:
                    densityScore += 15
            hasOppositeColorBase = False
            for b in range(1, bc + 1):
                kb = t - b
                if isD and c[kb] < o[kb]:
                    hasOppositeColorBase = True; break
                elif isS and c[kb] > o[kb]:
                    hasOppositeColorBase = True; break
            if hasOppositeColorBase:
                densityScore += 10
            densityScore += 10
            if hasGenuineGap:
                densityScore += p["genuineGapBonus"]
            if overnight and hasGenuineGap:
                densityScore += p["overnightGapBonus"]
            if densityScore < p["minValidScore"]:
                continue
            isHQZone = densityScore >= p["hqScoreThreshold"]
            found = True

            # ================= ZONE LEVELS (Pine: base WICK extremes) =================
            proxVal = maxBaseHigh if isD else minBaseLow
            distVal = minBaseLow if isD else maxBaseHigh
            slVal = (distVal - p["slBufferAtr"] * a_now) if isD else (distVal + p["slBufferAtr"] * a_now)
            risk = abs(proxVal - slVal)
            if risk <= 0:
                continue
            tpVal = (proxVal + risk * p["targetRR"]) if isD else (proxVal - risk * p["targetRR"])
            legOutMidLevel = ((legOutHigh - p["testedLegOutRetracePct"] * (legOutHigh - legOutLow)) if isD
                              else (legOutLow + p["testedLegOutRetracePct"] * (legOutHigh - legOutLow)))

            # ================= DUPLICATE (Pine: 0.25*ATR, same dir, last 11 non-Broken) =================
            dup = False; checked = 0
            for cz in reversed(zones):
                if cz.state == "Broken":
                    continue
                if cz.isDemand == isD and abs(cz.proxVal - proxVal) < (a_now * p["duplicateAtr"]):
                    dup = True; break
                checked += 1
                if checked >= 11:
                    break
            if dup:
                continue

            pat = "RBR" if isRBR else ("DBR" if isDBR else ("DBD" if isDBD else "RBD"))
            zoneCat = "Continuation" if (isRBR or isDBD) else "Reversal"
            coverR = ((h[t] - proxVal) if isD else (proxVal - l[t])) / risk if risk > 0 else 0.0
            z = Zone(proxVal=proxVal, distVal=distVal, slVal=slVal, tpVal=tpVal, isDemand=isD,
                     isHQ=isHQZone, densityScore=densityScore, originalDensityScore=densityScore,
                     patternType=pat, zoneCategory=zoneCat, startBarIndex=t - bc, createdBarIndex=t,
                     baseCount=bc, timestamp=df.index[t], legOutHigh=legOutHigh, legOutLow=legOutLow,
                     legOutMidLevel=legOutMidLevel, isOvernightGap=overnight, legInTR=legInTR, legOutTR=legOutTR,
                     hasGenuineGap=hasGenuineGap, gapSize=gapSize, baseHigh=maxBaseHigh, baseLow=minBaseLow,
                     baseBodyHigh=float(bodyH[bidx].max()), baseBodyLow=float(bodyL[bidx].min()),
                     baseColourOK=True, freshBoring=True, legOutCoverR=coverR,
                     score10=min(10, densityScore // 10),
                     maxPenetration=p["maxPenetration"], minRetestBars=p["minRetestBars"],
                     maxEntrySlipR=p["maxEntrySlipR"], legOutVol=float(legOutVol),
                     maxRetestVolOverLegOut=p["maxRetestVolOverLegOut"], minEntrySlipR=p["minEntrySlipR"],
                     htfTrendEma=None)
            va = volAvg[t] if (t < len(volAvg) and not np.isnan(volAvg[t]) and volAvg[t] > 0) else np.nan
            if not np.isnan(va):
                z.legOutVolX = float(v[t] / va) if v[t] > 0 else np.nan
                z.legInVolX = float(v[li] / va) if v[li] > 0 else np.nan
                bVol = np.nanmean(vv[bidx]) if np.any(~np.isnan(vv[bidx])) else np.nan
                z.baseVolX = float(bVol / va) if not np.isnan(bVol) else np.nan
            z.legOutOverLegIn = float(v[t] / v[li]) if (v[t] > 0 and v[li] > 0) else np.nan
            zones.append(z); active.append(z)

        # ---------------- STATE MACHINE (Pine v6: Fresh -> Tested @ legOutMidLevel -> Broken @ distal) ----------------
        if active:
            lo_t, hi_t = l[t], h[t]
            keep = []
            for z in active:
                if z.state == "Fresh":
                    if z.isDemand:
                        if lo_t <= z.distVal:
                            z.state = "Broken"
                        elif lo_t <= z.legOutMidLevel:
                            z.state = "Tested"; z.touchCount += 1
                    else:
                        if hi_t >= z.distVal:
                            z.state = "Broken"
                        elif hi_t >= z.legOutMidLevel:
                            z.state = "Tested"; z.touchCount += 1
                elif z.state == "Tested":
                    if z.isDemand:
                        if lo_t <= z.distVal:
                            z.state = "Broken"
                        elif lo_t <= z.legOutMidLevel:
                            z.touchCount += 1
                    else:
                        if hi_t >= z.distVal:
                            z.state = "Broken"
                        elif hi_t >= z.legOutMidLevel:
                            z.touchCount += 1
                if z.state == "Tested" and z.touchCount > p["maxTestedCount"]:
                    z.state = "Broken"
                # ---- app-compat: first test -> entry fill + TP-SCORE inputs (C/D/E) ----
                if z.state == "Tested" and z.entryBarIndex < 0:
                    z.entryBarIndex = t
                    z.entryPrice = float(c[t])
                    z.entryStatus = "Triggered"
                    z.retestBarIndex = t
                    rk = abs(z.proxVal - z.slVal)
                    z.retestPen = ((z.proxVal - l[t]) if z.isDemand else (h[t] - z.proxVal)) / rk if rk > 0 else 0.0
                    if t < len(volAvg) and not np.isnan(volAvg[t]) and volAvg[t] > 0 and v[t] > 0:
                        z.retestVolX = float(v[t] / volAvg[t])
                    z.emaSlopeOK = bool(((e20[t] - e20[max(0, t - 5)]) > 0) == z.isDemand) if t >= 5 else None
                if z.state == "Broken" and z.entryStatus == "Waiting":
                    z.entryStatus = "Failed-BrokeThrough"
                if z.state not in ("Broken", "Failed"):
                    keep.append(z)
            active = keep

    if lookback_months is None:
        return zones
    return [z for z in zones if z.createdBarIndex >= record_from]


def scan_winrate(df, patterns=None, min_score=None, params=None):
    p = dict(PRESET_WINRATE); p.update(params or {})
    if min_score is not None:
        p["minValidScore"] = min_score
    zs = scan_zones(df, params=p)
    return [z for z in zs if z.patternType in patterns] if patterns else zs


def scan_daily(df, params=None):
    p = dict(PRESET_DAILY); p.update(params or {}); return scan_zones(df, p)


WINRATE = dict(patterns=["RBR", "DBR", "DBD", "RBD"], min_score=40, prefer_tfs=["15m", "1h"])


# =============================================================================
# SECTION 5: ALERTS / MTF / TAGS  (UNCHANGED — app API)
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
            "entry_rule": (f"Pine v6: zone = leg-in + {z.baseCount} boring + leg-out; entry line = base edge (proximal); "
                           f"SL = distal ∓ {0.1}xATR; target 1:{5.0}; retest level = legOutMidLevel (50% retrace)."),
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
        why = {"Waiting": "Fresh — retest abhi nahi aayi", "Triggered": "Entry mili (Pine retest @ legOutMidLevel)",
               "Failed-BrokeThrough": "Price distal ke paar — SL"}.get(z.entryStatus, z.entryStatus)
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
    if z.legOutCoverR >= 5: tags.append("Powerful-1:5")
    if z.freshBoring: tags.append("Fresh-Boring")
    if z.entryStatus == "Triggered": tags.append("Entry-Triggered")
    if z.baseCount == 1: tags.append("1-Boring")
    if z.hasGenuineGap: tags.append("Gap")
    if z.isOvernightGap: tags.append("Overnight")
    if z.score10 >= 7: tags.append("Score7+")
    if not np.isnan(z.legInVolX) and z.legInVolX >= 1.0: tags.append("LegIn-Vol")
    if not np.isnan(z.retestVolX): tags.append("Quiet-Retest" if z.retestVolX < 1.3 else "Heavy-Retest")
    if z.isNestedInBiggerTF: tags.append(f"Nested-in-{'/'.join(z.confluenceTFs)}")
    elif z.isMTFConfluence: tags.append(f"MTF-{'/'.join(z.confluenceTFs)}")
    return tags


# =============================================================================
# SECTION 5b: v13.3 TARGET-CONTEXT  (UNCHANGED — app API: TP-SCORE)
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
    """Pine v6 core ke saath bar-level diagnostic (t = leg-out index)."""
    p = _apply_tf_overrides(df, _resolve_params(params))
    o, h, l, c, v, tr, atr, volSma = _prep(df, p)
    t = int(at_index) if isinstance(at_index, (int, np.integer)) else int(df.index.get_loc(at_index))
    bodyH = np.maximum(o, c); bodyL = np.minimum(o, c); rng = h - l
    upW = np.where(rng > 0, (h - bodyH) / np.where(rng > 0, rng, 1.0), 0.0)
    loW = np.where(rng > 0, (bodyL - l) / np.where(rng > 0, rng, 1.0), 0.0)
    bodyPct = np.where(rng > 0, np.abs(c - o) / np.where(rng > 0, rng, 1.0), 0.0)
    reports = []
    for bc in range(p["minBase"], p["maxBase"] + 1):
        rep = {"baseCount": bc, "legOutTimestamp": df.index[t]}
        li = t - bc - 1; pv = li - 1
        if li < 1 or pv < 0 or rng[li] <= 0 or rng[t] <= 0:
            rep["result"] = "SKIP"; reports.append(rep); continue
        a_legIn = atr[li]
        liBull = c[li] > o[li]; liBear = o[li] > c[li]
        isD = c[t] > o[t]; isS = o[t] > c[t]
        legInTR = tr[li]; legInRng = rng[li]
        rep["legIn_body_pct"] = bool(bodyPct[li] >= p["legInMinBodyPct"])
        bullClv = (c[li] - l[li]) / legInRng; bearClv = (h[li] - c[li]) / legInRng
        pvBull = c[pv] > o[pv]; pvBear = o[pv] > c[pv]
        opp = (liBull and pvBear) or (liBear and pvBull)
        rep["legIn_overlap_ok"] = True
        if opp:
            ov = max(0.0, min(bodyH[pv], h[li]) - max(bodyL[pv], l[li]))
            rep["legIn_overlap_ok"] = bool(ov / legInRng < p["rejectOppositeCoverPct"])
        rep["legIn_min_atr"] = bool(legInTR >= p["legInMinAtrMult"] * a_legIn) if not np.isnan(a_legIn) else False
        bidx = list(range(t - bc, t)); a_b_ok = True; maxBaseTR = 0.0; maxBaseHigh = -1.0; minBaseLow = 1e9
        for b in range(1, bc + 1):
            kb = t - b
            if np.isnan(atr[kb]) or tr[kb] > p["maxBaseAtrMult"] * atr[kb]:
                a_b_ok = False; break
            maxBaseTR = max(maxBaseTR, tr[kb]); maxBaseHigh = max(maxBaseHigh, h[kb]); minBaseLow = min(minBaseLow, l[kb])
        effMult = 1.5 if bc == 1 else p["legInToBaseSizeMult"]
        rep["base_ok"] = bool(a_b_ok and maxBaseTR > 0)
        rep["legIn_to_base_size"] = bool(legInTR >= effMult * maxBaseTR) if (a_b_ok and maxBaseTR > 0) else False
        a_now = atr[t]
        rep["legOut_explosive"] = bool(tr[t] >= p["legOutTrMult"] * a_now)
        rep["legOut_wick30"] = bool((upW[t] + loW[t]) <= p["maxWickPct"])
        rep["legOut_tr_hierarchy"] = bool((tr[t] >= p["legOutMinTrRatio"] * legInTR) and (legInTR > maxBaseTR))
        rep["legOut_volume"] = bool(v[t] > v[li])
        if isD:
            rep["imbalance"] = bool((l[t] > maxBaseHigh) or (c[t] > h[li]))
        elif isS:
            rep["imbalance"] = bool((h[t] < minBaseLow) or (c[t] < l[li]))
        else:
            rep["imbalance"] = False
        loBH, loBL = max(o[t], c[t]), min(o[t], c[t])
        rep["engulf_guard"] = bool(not ((loBL <= minBaseLow and loBH >= maxBaseHigh) and not ((l[t] > maxBaseHigh) if isD else (h[t] < minBaseLow))))
        isRBR = liBull and (bullClv >= p["minClvPct"]) and isD
        isDBR = liBear and (bearClv >= p["minClvPct"]) and isD
        isDBD = liBear and (bearClv >= p["minClvPct"]) and isS
        isRBD = liBull and (bullClv >= p["minClvPct"]) and isS
        pat = "RBR" if isRBR else ("DBR" if isDBR else ("DBD" if isDBD else "RBD"))
        rep["pattern"] = pat
        bH = h[bidx].max(); bL = l[bidx].min()
        prox = maxBaseHigh if isD else minBaseLow
        dist = minBaseLow if isD else maxBaseHigh
        rep["proximal"] = prox; rep["distal(SL)"] = dist
        sl = dist - p["slBufferAtr"] * a_now if isD else dist + p["slBufferAtr"] * a_now
        rep["sl"] = sl
        risk = abs(prox - sl)
        rep["risk_pct"] = 100 * risk / prox if prox else 0.0
        rep["FINAL_VALID"] = bool(rep["legIn_body_pct"] and rep["legIn_overlap_ok"] and rep["legIn_min_atr"]
                                  and rep["base_ok"] and rep["legIn_to_base_size"] and rep["legOut_explosive"]
                                  and rep["legOut_wick30"] and rep["legOut_tr_hierarchy"] and rep["legOut_volume"]
                                  and rep["imbalance"] and rep["engulf_guard"] and (isRBR or isDBR or isDBD or isRBD))
        reports.append(rep)
    return reports


_hema_cache = {}


def simulate(zones, df, rr=5.0, max_hold=30, entry=ENTRY_MODE, start=None, end=None,
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


def realistic_roi(zones, df, rr=5.0, risk_pct=0.005, capital=25000.0, max_hold=30,
                  start=None, end=None, patterns=None, buffer=None, entry_mode=ENTRY_MODE):
    zs = [z for z in zones if (not patterns or z.patternType in patterns)]
    if buffer is not None:
        o, hh, ll, cc, _ = _cols(df); atr = _rma(_true_range(hh, ll, cc), p["atrPeriod"] if False else 14)
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
        "min_score": 40, "max_score": 125,
        "timeframes": ["1h", "4h"],
        "entry_mode": "confirm",
        "exit_mode": "target",
        "slBufferAtr": 0.1,
        "targetRR": 5.0,
        "max_hold": 30,
        "risk_pct": 0.005,
        "capital": 25000.0,
        "winrate_preset": PRESET_WINRATE,
        "maxBase": 3, "minBase": 1, "minValidScore": 40, "hqScoreThreshold": 90,
        "note": ("v15.0 PINE v6 CORE (1:1): leg-in (body>=60%, opp-overlap<50%, TR>=1xATR, TR>=1.5/2.0x base), "
                 "base 1-3 (each TR<=1xATR), leg-out (TR>=1.2xATR, wick<=30%, TR>=1x leg-in, vol>leg-in), "
                 "imbalance/gap required, engulf-guard, RBR/DBR/DBD/RBD via CLV>=60%, score 0-125 gate>=40 HQ>=90. "
                 "Zone lines: proximal=base wick extreme, distal=base opposite wick, SL=distal∓0.1xATR, TP=1:5. "
                 "State: Fresh->Tested(@legOutMidLevel)->Broken(@distal). ATR=ta.rma. Entry engine = zone_core confirm-close."),
    }


# =============================================================================
# SECTION 7: EXTRA VALIDATION LAYERS  (UNCHANGED — API compatibility)
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
