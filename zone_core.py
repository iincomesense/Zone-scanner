# -*- coding: utf-8 -*-
"""
pine_zone_v6.py — Pine Script® v6 "Zone" indicator ka BILKUL same (1:1) Python port
====================================================================================
© iincomesense  (original Pine v6, Mozilla Public License 2.0)

Yeh file Pine v6 code ko line-by-line translate karti hai:
  • SAME parameter names + defaults (Pine ke inputs)
  • SAME helper functions (true_range, custom_atr, tr, wick_pct, body_pct, ...)
  • SAME scanning engine (SECTION 4) — har check same order mein
  • SAME zone state tracking (SECTION 5) — Fresh/Tested/Broken + touchCount
  • SAME box drawing (SECTION 6) — matplotlib se Pine ke box.new/set_right/
    set_bgcolor ka exact equivalent

Koi logic change/interpretation NAHI — sirf Pine → Python syntax translation.

USAGE:
    python pine_zone_v6.py path/to/OHLCV.csv            # chart + zones
    from pine_zone_v6 import Params, Bar, scan, plot_zones, candles_from_dataframe
    bars  = candles_from_dataframe(df)                  # pandas OHLCV (DatetimeIndex)
    zones = scan(bars)                                  # list[Zone]
    plot_zones(bars, zones, "RELIANCE.NS 1h")           # chart
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import List, Optional

# ==============================================================================
# 1. PARAMETERS & CONSTANTS   (Pine ke exact input names + defaults)
# ==============================================================================
@dataclass
class Params:
    accountCapital         = 25000.0
    riskPct                = 0.5
    targetRR               = 5.0
    slBufferAtr            = 0.1

    atrPeriod              = 14
    volSmaPeriod           = 20
    legOutTrMult           = 1.2
    legOutMinTrRatio       = 1.0
    hqLegOutTrMult         = 2.0
    hqLegInAtrMult         = 1.5
    maxBaseAtrMult         = 1.0
    maxWickPct             = 0.30

    minBaseCountInput      = 1
    maxBaseCountInput      = 3
    legInMinAtrMult        = 1.0
    minClvPct              = 0.60
    legInToBaseSizeMult    = 2.0
    legInMinBodyPct        = 0.60

    useImbalance           = True
    maxImbalanceMult       = 1.0
    relaxGapCapOvernight   = True
    genuineGapBonus        = 10
    overnightGapBonus      = 15
    rejectOppositeCoverPct = 0.50

    minValidScore          = 40
    hqScoreThreshold       = 90
    legOutBodyHeavyPct     = 0.60

    testedLegOutRetracePct = 0.50
    maxTestedCount         = 2

    HARD_MAX_BASE_COUNT    = 3
    minBaseCount           = 1      # __post_init__ mein compute (Pine same)
    maxBaseCount           = 3

    def __post_init__(self):
        # Pine: minBaseCount = math.max(1, math.min(minBaseCountInput, maxBaseCountInput))
        self.minBaseCount = max(1, min(self.minBaseCountInput, self.maxBaseCountInput))
        # Pine: maxBaseCount = math.min(maxBaseCountInput, HARD_MAX_BASE_COUNT)
        self.maxBaseCount = min(self.maxBaseCountInput, self.HARD_MAX_BASE_COUNT)


# ==============================================================================
# 2. HELPER FUNCTIONS & ARRAYS (v9.0 Gap-Aware True Range)
# ==============================================================================
@dataclass
class Bar:
    """Ek OHLCV bar + Pine ke `time` (ms epoch) aur `dayofweek`."""
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    time_ms: int = 0          # Pine `time` (milliseconds)
    dayofweek: int = 0        # Pine `dayofweek` (0=Sun..6=Sat)

    @property
    def is_bull(self) -> bool:
        return self.close > self.open

    @property
    def is_bear(self) -> bool:
        return self.open > self.close


def true_range(b: Bar, prev_close: Optional[float] = None) -> float:
    """Pine true_range(): TR = max(H-L, |H-prevClose|, |L-prevClose|)."""
    tr = b.high - b.low
    if prev_close is not None:
        tr = max(tr, abs(b.high - prev_close), abs(b.low - prev_close))
    return tr


def _tr_series(bars: List[Bar]) -> List[float]:
    """current_tr har bar ke liye (prev_close = pichli bar ka close)."""
    out = []
    for i, b in enumerate(bars):
        pc = bars[i - 1].close if i > 0 else None
        out.append(true_range(b, pc))
    return out


def _rma(series: List[float], length: int) -> List[Optional[float]]:
    """Pine ta.rma (custom_atr): SMA seed + Wilder recursion."""
    n = len(series)
    out: List[Optional[float]] = [None] * n
    if n < length:
        return out
    out[length - 1] = sum(series[:length]) / length
    for i in range(length, n):
        out[i] = (series[i] + (length - 1) * out[i - 1]) / length
    return out


def _sma(series: List[float], length: int) -> List[Optional[float]]:
    """Pine ta.sma (vol_sma)."""
    n = len(series)
    out: List[Optional[float]] = [None] * n
    if n < length:
        return out
    s = sum(series[:length])
    out[length - 1] = s / length
    for i in range(length, n):
        s += series[i] - series[i - length]
        out[i] = s / length
    return out


def wick_pct(b: Bar) -> float:
    """Pine wick_pct(idx)."""
    rng = b.high - b.low
    if rng == 0:
        return 0.0
    wicks = (b.high - max(b.open, b.close)) + (min(b.open, b.close) - b.low)
    return wicks / rng


def body_pct(b: Bar) -> float:
    """Pine body_pct(idx)."""
    rng = b.high - b.low
    if rng == 0:
        return 0.0
    return abs(b.close - b.open) / rng


def body_high_low(b: Bar):
    """Pine body_high_low(idx) -> [bodyHigh, bodyLow]."""
    return max(b.open, b.close), min(b.open, b.close)


def is_overnight_gap(bars: List[Bar], bar_index: int) -> bool:
    """Pine isOvernightGap(): dayofweek != dayofweek[1] OR time - time[1] > 86400000."""
    if bar_index < 1:
        return False
    return (bars[bar_index].dayofweek != bars[bar_index - 1].dayofweek
            or (bars[bar_index].time_ms - bars[bar_index - 1].time_ms) > 86400000)


# ==============================================================================
# 3. TYPES & COLLECTIONS
# ==============================================================================
@dataclass
class Zone:
    """Pine ka `type Zone` — bilkul same fields."""
    proxVal: float
    distVal: float
    slVal: float
    tpVal: float
    isDemand: bool
    isHQ: bool
    densityScore: int
    patternType: str
    zoneCategory: str
    state: str
    touchCount: int
    startBarIndex: int
    createdBarIndex: int
    baseCount: int
    legOutHigh: float
    legOutLow: float
    legOutMidLevel: float
    isOvernight: bool
    legInTR: float
    legOutTR: float
    box: Optional[object] = None     # Pine zBox (plot ke liye; data mein None)

    @property
    def side(self) -> str:
        return "demand" if self.isDemand else "supply"

    @property
    def kind(self) -> str:
        return self.patternType


# ==============================================================================
# 4. SCANNING ENGINE   (Pine SECTION 4, line-by-line)
# ==============================================================================
def scan(bars: List[Bar], p: Optional[Params] = None) -> List[Zone]:
    if p is None:
        p = Params()
    n = len(bars)
    current_tr = _tr_series(bars)          # Pine current_tr
    atr_series = _rma(current_tr, p.atrPeriod)  # Pine atr_val (custom_atr)
    vol_sma_series = _sma([b.volume for b in bars], p.volSmaPeriod)  # Pine vol_sma

    warmup = max(p.atrPeriod, p.maxBaseCount + 3, 11)   # Pine bar_index >= ...
    active_zones: List[Zone] = []

    for bar_index in range(n):
        # ------------------------------------------------------------------
        # PINE: if bar_index >= math.max(atrPeriod, maxBaseCount+3, 11)
        #       and not na(atr_val)
        # ------------------------------------------------------------------
        if bar_index >= warmup and atr_series[bar_index] is not None:
            zoneFoundOnThisBar = False
            for bCount in range(p.minBaseCount, p.maxBaseCount + 1):
                if zoneFoundOnThisBar:
                    break

                legOutIdx = 0
                legInIdx = bCount + 1
                prevIdx = legInIdx + 1

                li_bar = bars[bar_index - legInIdx]
                lo_bar = bars[bar_index - legOutIdx]
                prev_bar = bars[bar_index - prevIdx]

                atr_legIn = atr_series[bar_index - legInIdx]
                if atr_legIn is None:
                    continue

                # ---------------- LEG-IN ----------------
                legInTR = current_tr[bar_index - legInIdx]
                legInLow = li_bar.low
                legInHigh = li_bar.high
                legInClose = li_bar.close
                legInVol = li_bar.volume
                legInRng = legInHigh - legInLow

                legInIsBull = li_bar.is_bull
                legInIsBear = li_bar.is_bear

                if legInRng == 0 or body_pct(li_bar) < p.legInMinBodyPct:
                    continue

                prevIsBull = prev_bar.is_bull
                prevIsBear = prev_bar.is_bear
                isOppositeColor = (legInIsBull and prevIsBear) or (legInIsBear and prevIsBull)

                shouldRejectOverlap = False
                if isOppositeColor:
                    prevBodyHigh, prevBodyLow = body_high_low(prev_bar)
                    overlap = max(0.0, min(prevBodyHigh, legInHigh) - max(prevBodyLow, legInLow))
                    coverPct = overlap / legInRng
                    if coverPct >= p.rejectOppositeCoverPct:
                        shouldRejectOverlap = True
                if shouldRejectOverlap:
                    continue

                bullClv = (legInClose - legInLow) / legInRng
                bearClv = (legInHigh - legInClose) / legInRng

                # ---------------- BASE ----------------
                allBaseValid = True
                maxBaseTR = 0.0
                maxBaseHigh = -1.0
                minBaseLow = 1000000000.0
                hasOppositeColorBase = False

                for b in range(1, bCount + 1):
                    base_bar = bars[bar_index - b]
                    atr_b = atr_series[bar_index - b]
                    if atr_b is None:
                        allBaseValid = False
                        break
                    bTR = current_tr[bar_index - b]
                    if bTR > (p.maxBaseAtrMult * atr_b):
                        allBaseValid = False
                        break
                    if bTR > maxBaseTR:
                        maxBaseTR = bTR
                    if base_bar.high > maxBaseHigh:
                        maxBaseHigh = base_bar.high
                    if base_bar.low < minBaseLow:
                        minBaseLow = base_bar.low

                if (not allBaseValid) or maxBaseTR == 0:
                    continue

                effectiveBaseSizeMult = 1.5 if bCount == 1 else p.legInToBaseSizeMult
                if legInTR < (effectiveBaseSizeMult * maxBaseTR):
                    continue

                validLegIn = legInTR >= (p.legInMinAtrMult * atr_legIn)
                if not validLegIn:
                    continue

                # ---------------- LEG-OUT ----------------
                atr_now = atr_series[bar_index]
                legOutTR = current_tr[bar_index - legOutIdx]
                legOutHigh = lo_bar.high
                legOutLow = lo_bar.low
                legOutClose = lo_bar.close
                legOutOpen = lo_bar.open
                legOutVol = lo_bar.volume

                isDemandLegOut = lo_bar.is_bull
                isSupplyLegOut = lo_bar.is_bear
                if not (isDemandLegOut or isSupplyLegOut):
                    continue

                isLegOutExplosive = legOutTR >= (p.legOutTrMult * atr_now)
                isLegOutWickValid = wick_pct(lo_bar) <= p.maxWickPct
                passesTRHierarchy = (legOutTR >= p.legOutMinTrRatio * legInTR) and (legInTR > maxBaseTR)
                passesVolume = legOutVol > legInVol
                isOvernight = is_overnight_gap(bars, bar_index)

                # ---------------- IMBALANCE & GAP ----------------
                hasImbalance = True
                hasGenuineGap = False
                gapSize = 0.0
                if p.useImbalance:
                    if isDemandLegOut:
                        hasGenuineGap = legOutLow > maxBaseHigh
                        gapCond = hasGenuineGap or (legOutClose > legInHigh)
                        gapSize = max(0.0, legOutLow - maxBaseHigh)
                        hasImbalance = gapCond
                    elif isSupplyLegOut:
                        hasGenuineGap = legOutHigh < minBaseLow
                        gapCond = hasGenuineGap or (legOutClose < legInLow)
                        gapSize = max(0.0, minBaseLow - legOutHigh)
                        hasImbalance = gapCond

                # ---------------- ENGULF CHECK ----------------
                legOutBodyHigh = max(legOutOpen, legOutClose)
                legOutBodyLow = min(legOutOpen, legOutClose)
                legOutBodyEngulfsBase = (legOutBodyLow <= minBaseLow) and (legOutBodyHigh >= maxBaseHigh)
                if legOutBodyEngulfsBase and not hasGenuineGap:
                    continue

                # ---------------- CLASSIFICATION ----------------
                isRBR = legInIsBull and (bullClv >= p.minClvPct) and isDemandLegOut
                isDBR = legInIsBear and (bearClv >= p.minClvPct) and isDemandLegOut
                isDBD = legInIsBear and (bearClv >= p.minClvPct) and isSupplyLegOut
                isRBD = legInIsBull and (bullClv >= p.minClvPct) and isSupplyLegOut

                isValid = ((isRBR or isDBR or isDBD or isRBD) and isLegOutExplosive
                           and isLegOutWickValid and passesTRHierarchy and passesVolume
                           and hasImbalance)
                if not isValid:
                    continue

                # ---------------- SCORING ----------------
                densityScore = 0
                if bCount == 1:
                    densityScore += 15
                if legInTR >= (p.hqLegInAtrMult * atr_legIn):
                    densityScore += 10
                if legOutTR >= (p.hqLegOutTrMult * legInTR):
                    densityScore += 15
                if (legInTR >= 2.0 * maxBaseTR) and (legOutTR >= 2.0 * legInTR):
                    densityScore += 15
                vol_sma_legOut = vol_sma_series[bar_index - legOutIdx]
                if vol_sma_legOut is not None and legOutVol > vol_sma_legOut:
                    densityScore += 10
                if isDemandLegOut:
                    legOutBodyPos = ((legOutClose - legOutLow) / (legOutHigh - legOutLow)
                                     if (legOutHigh - legOutLow) > 0 else 0)
                    legOutOwnBodyPct = body_pct(lo_bar)
                    if isDBR:
                        if (legOutBodyPos >= 0.80) or (legOutOwnBodyPct >= p.legOutBodyHeavyPct):
                            densityScore += 15
                    else:
                        if legOutBodyPos >= 0.80:
                            densityScore += 15
                else:
                    legOutBodyPos = ((legOutHigh - legOutClose) / (legOutHigh - legOutLow)
                                     if (legOutHigh - legOutLow) > 0 else 0)
                    if legOutBodyPos >= 0.80:
                        densityScore += 15

                for b in range(1, bCount + 1):
                    base_bar = bars[bar_index - b]
                    if isDemandLegOut and base_bar.is_bear:
                        hasOppositeColorBase = True
                        break
                    elif isSupplyLegOut and base_bar.is_bull:
                        hasOppositeColorBase = True
                        break
                if hasOppositeColorBase:
                    densityScore += 10

                densityScore += 10
                if hasGenuineGap:
                    densityScore += p.genuineGapBonus
                if isOvernight and hasGenuineGap:
                    densityScore += p.overnightGapBonus

                if densityScore < p.minValidScore:
                    continue

                isHQZone = densityScore >= p.hqScoreThreshold
                zoneFoundOnThisBar = True

                # ---------------- ZONE LEVELS ----------------
                proxVal = maxBaseHigh if isDemandLegOut else minBaseLow
                distVal = minBaseLow if isDemandLegOut else maxBaseHigh
                slVal = (distVal - p.slBufferAtr * atr_now) if isDemandLegOut else (distVal + p.slBufferAtr * atr_now)
                riskPerShare = abs(proxVal - slVal)
                tpVal = (proxVal + riskPerShare * p.targetRR) if isDemandLegOut else (proxVal - riskPerShare * p.targetRR)
                legOutMidLevel = ((legOutHigh - p.testedLegOutRetracePct * (legOutHigh - legOutLow))
                                  if isDemandLegOut
                                  else (legOutLow + p.testedLegOutRetracePct * (legOutHigh - legOutLow)))

                # ---------------- DUPLICATE CHECK ----------------
                isDuplicate = False
                checked = 0
                if len(active_zones) > 0:
                    for i in range(len(active_zones) - 1, -1, -1):
                        checkZ = active_zones[i]
                        if checkZ.state == "Broken":
                            continue
                        if checkZ.isDemand == isDemandLegOut and abs(checkZ.proxVal - proxVal) < (atr_now * 0.25):
                            isDuplicate = True
                            break
                        checked += 1
                        if checked >= 11:
                            break
                if isDuplicate:
                    continue

                patternType = "RBR" if isRBR else ("DBR" if isDBR else ("DBD" if isDBD else "RBD"))
                zoneCat = "Continuation" if (isRBR or isDBD) else "Reversal"

                # ---------------- DRAWING BOXES ON CHART (Pine box.new) --------
                # (actual box object plot_zones mein banayega; data-only run mein None)
                newZone = Zone(
                    proxVal, distVal, slVal, tpVal, isDemandLegOut, isHQZone, densityScore,
                    patternType, zoneCat, "Fresh", 0, bar_index - bCount, bar_index, bCount,
                    legOutHigh, legOutLow, legOutMidLevel, isOvernight, legInTR, legOutTR, None)
                active_zones.append(newZone)

        # ------------------------------------------------------------------
        # PINE SECTION 5: ZONE STATE TRACKING & BOX UPDATES
        # ------------------------------------------------------------------
        if len(active_zones) > 0:
            lo_t = bars[bar_index].low
            hi_t = bars[bar_index].high
            for i in range(len(active_zones) - 1, -1, -1):
                z = active_zones[i]
                if z.state == "Fresh":
                    if z.isDemand:
                        if lo_t <= z.distVal:
                            z.state = "Broken"
                        elif lo_t <= z.legOutMidLevel:
                            z.state = "Tested"
                            z.touchCount += 1
                    else:
                        if hi_t >= z.distVal:
                            z.state = "Broken"
                        elif hi_t >= z.legOutMidLevel:
                            z.state = "Tested"
                            z.touchCount += 1
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
                if z.state == "Tested" and z.touchCount > p.maxTestedCount:
                    z.state = "Broken"
                # Pine box.set_bgcolor / box.set_right  ->  plot_zones mein reflect

    return active_zones


# ==============================================================================
# 6. PLOTTING  (Pine box.new / box.set_right / box.set_bgcolor ka equivalent)
# ==============================================================================
def plot_zones(bars: List[Bar], zones: List[Zone], title: str = "",
               save_path: Optional[str] = None) -> None:
    """Candlestick chart + zone boxes (Pine jaise: green=demand, red=supply,
    grey=broken; box leg-in se 15 bars aage, top=proxVal, bottom=distVal)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except Exception as e:                                    # pragma: no cover
        print(f"[plot] matplotlib available nahi ({e}) — sirf zones return kiye.")
        return

    n = len(bars)
    fig, ax = plt.subplots(figsize=(16, 8))

    # --- candlesticks ---
    w = 0.6
    for i, b in enumerate(bars):
        color = "#26a69a" if b.is_bull else "#ef5350"
        ax.vlines(i, b.low, b.high, color=color, linewidth=0.8, zorder=2)
        body_lo, body_hi = min(b.open, b.close), max(b.open, b.close)
        if body_hi == body_lo:
            body_hi = body_lo + 1e-9
        ax.add_patch(mpatches.Rectangle((i - w / 2, body_lo), w, body_hi - body_lo,
                                        facecolor=color, edgecolor=color, zorder=3))

    # --- zone boxes (Pine box.new: left=bar_index-bCount-1, right=+15, top=prox, bottom=dist)
    for z in zones:
        left = z.startBarIndex - 1
        right = min(n - 1, z.createdBarIndex + 15)
        if z.state == "Broken":
            edge, fill = "#9e9e9e", "#616161"
        elif z.isDemand:
            edge, fill = "#00e676", "#00e67619"
        else:
            edge, fill = "#ff1744", "#ff174419"
        ax.add_patch(mpatches.Rectangle((left, z.distVal), right - left,
                                        z.proxVal - z.distVal,
                                        facecolor=fill, edgecolor=edge,
                                        linewidth=1.4, zorder=4))
        tag = f"{z.patternType} {z.state}({z.touchCount}) S{z.densityScore}{' ★HQ' if z.isHQ else ''}"
        ax.text(left, z.proxVal, f" {tag}", fontsize=7, va="bottom",
                color=edge, zorder=5)

    step = max(1, n // 12)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([str(bars[i].time_ms) for i in range(0, n, step)], rotation=30, fontsize=7)
    ax.set_title(f"Zone (Pine v6 port) — {title}   |   zones: {len(zones)}", fontsize=12)
    ax.set_facecolor("#0e1117")
    fig.patch.set_facecolor("#0e1117")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors="#c9d1d9")
    ax.grid(True, alpha=0.15, color="#8ba1c0")
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=110, facecolor=fig.get_facecolor())
        print(f"[plot] saved -> {save_path}")
    else:
        plt.show()


# ==============================================================================
# INPUT HELPER  (pandas OHLCV DatetimeIndex -> List[Bar])
# ==============================================================================
def candles_from_dataframe(df) -> List[Bar]:
    out: List[Bar] = []
    has_vol = "volume" in getattr(df, "columns", [])
    for ts, row in df.iterrows():
        try:
            t = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            time_ms = int(t.timestamp() * 1000) if hasattr(t, "timestamp") else 0
            dow = t.weekday() if hasattr(t, "weekday") else 0
        except Exception:
            time_ms, dow = 0, 0
        out.append(Bar(
            open=float(row["open"]), high=float(row["high"]),
            low=float(row["low"]), close=float(row["close"]),
            volume=float(row["volume"]) if has_vol else 0.0,
            time_ms=time_ms, dayofweek=dow))
    return out


# ==============================================================================
# SELF-TEST / CLI
# ==============================================================================
def _mk(o, h, l, c, v=0.0, t=0, dow=0) -> Bar:
    return Bar(open=o, high=h, low=l, close=c, volume=v, time_ms=t, dayofweek=dow)


def self_test() -> None:
    print("=" * 72)
    print("pine_zone_v6.py SELF-TEST (Pine v6 1:1 port)")
    print("=" * 72)
    bars: List[Bar] = []
    for k in range(20):                                    # warmup (ATR stable)
        bars.append(_mk(100.0, 101.0, 99.0, 100.0, v=100.0, t=k, dow=k % 7))
    bars.append(_mk(105.0, 105.2, 99.8, 100.0, v=500.0, t=20, dow=0))   # leg-in RED
    bars.append(_mk(100.0, 100.5, 99.9, 100.3, v=100.0, t=21, dow=1))   # base
    bars.append(_mk(101.0, 108.5, 101.5, 108.0, v=2000.0, t=22, dow=2)) # leg-out GREEN
    bars.append(_mk(108.0, 109.0, 106.0, 107.0, v=800.0, t=23, dow=3))  # next bar
    zones = scan(bars)
    print(f"Detected zones: {len(zones)}")
    for z in zones:
        print(f"  {z.side}/{z.patternType} cat={z.zoneCategory} state={z.state} "
              f"touch={z.touchCount} score={z.densityScore} HQ={z.isHQ} base={z.baseCount}")
        print(f"    prox={z.proxVal:.2f} dist={z.distVal:.2f} sl={z.slVal:.2f} "
              f"tp={z.tpVal:.2f} midLevel={z.legOutMidLevel:.2f}")
    assert any(z.patternType == "DBR" and z.isDemand for z in zones), "DBR demand zone nahi mila"
    print("\nOK — Pine v6 logic match (DBR demand zone detected).")


if __name__ == "__main__":
    import sys
    import os
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        import pandas as pd
        fp = sys.argv[1]
        df = pd.read_csv(fp, index_col=0, parse_dates=True)
        for col in ("open", "high", "low", "close"):
            if col not in df.columns:
                df = df.rename(columns={c.lower(): c for c in df.columns})
        bars = candles_from_dataframe(df)
        zones = scan(bars)
        print(f"{os.path.basename(fp)}: {len(zones)} zones")
        for z in zones[-8:]:
            print(f"  {z.patternType} {z.side:6s} {z.state:7s} touch={z.touchCount} "
                  f"S{z.densityScore} prox={z.proxVal:.2f} sl={z.slVal:.2f} tp={z.tpVal:.2f}")
        out = os.path.splitext(fp)[0] + "_pine_v6.png"
        plot_zones(bars, zones, title=os.path.basename(fp), save_path=out)
    else:
        self_test()
