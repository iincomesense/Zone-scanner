"""
================================================================================
ZONE CORE  -  Pine Script v6 "Zone" Indicator का Exact Python Conversion
Original Indicator: © iincomesense (MPL-2.0)
--------------------------------------------------------------------------------
NOTE: यह फाइल दिए गए Pine Script v6 कोड का line-by-line verified conversion है।
हर rule, condition, threshold, scoring logic बिल्कुल वैसी ही रखी गई है।
सिर्फ debug=True करने पर हर reject point पर reason print होता है (logic पर
कोई असर नहीं पड़ता)।
================================================================================
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Box:
    left: int
    top: float
    right: int
    bottom: float
    border_color: object
    bgcolor: object

    def set_right(self, right):
        self.right = right

    def set_bgcolor(self, color):
        self.bgcolor = color

    def set_border_color(self, color):
        self.border_color = color


@dataclass
class Zone:
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
    zoneBox: Box


class ZoneEngine:
    def __init__(
        self,
        df: pd.DataFrame,
        # ---------------- Pine Script Inputs (Section 1) — बिल्कुल वही defaults ----------------
        accountCapital=25000.0,
        riskPct=0.5,
        targetRR=5.0,
        slBufferAtr=0.1,
        atrPeriod=14,
        volSmaPeriod=20,
        legOutTrMult=1.2,
        legOutMinTrRatio=1.0,
        hqLegOutTrMult=2.0,
        hqLegInAtrMult=1.5,
        maxBaseAtrMult=1.0,
        maxWickPct=0.30,
        minBaseCountInput=1,
        maxBaseCountInput=3,
        legInMinAtrMult=1.0,
        minClvPct=0.60,
        legInToBaseSizeMult=2.0,
        legInMinBodyPct=0.60,
        useImbalance=True,
        maxImbalanceMult=1.0,          # Pine में declared, पर logic में unused (Pine जैसा ही)
        relaxGapCapOvernight=True,     # Pine में declared, पर logic में unused (Pine जैसा ही)
        genuineGapBonus=10,
        overnightGapBonus=15,
        rejectOppositeCoverPct=0.50,
        minValidScore=40,
        hqScoreThreshold=90,
        legOutBodyHeavyPct=0.60,
        testedLegOutRetracePct=0.50,
        maxTestedCount=2,
        # ---------------- सिर्फ debugging हेतु (logic पर कोई असर नहीं) ----------------
        debug: bool = False,
        debug_bar_indices: Optional[List[int]] = None,
    ):
        self.df = df.copy()
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(self.df.columns):
            raise ValueError(f"df में ये columns होने चाहिए: {required}")
        if not isinstance(self.df.index, pd.DatetimeIndex):
            raise ValueError("df का index DatetimeIndex होना चाहिए")

        self.accountCapital = accountCapital
        self.riskPct = riskPct
        self.targetRR = targetRR
        self.slBufferAtr = slBufferAtr
        self.atrPeriod = atrPeriod
        self.volSmaPeriod = volSmaPeriod
        self.legOutTrMult = legOutTrMult
        self.legOutMinTrRatio = legOutMinTrRatio
        self.hqLegOutTrMult = hqLegOutTrMult
        self.hqLegInAtrMult = hqLegInAtrMult
        self.maxBaseAtrMult = maxBaseAtrMult
        self.maxWickPct = maxWickPct
        self.legInMinAtrMult = legInMinAtrMult
        self.minClvPct = minClvPct
        self.legInToBaseSizeMult = legInToBaseSizeMult
        self.legInMinBodyPct = legInMinBodyPct
        self.useImbalance = useImbalance
        self.maxImbalanceMult = maxImbalanceMult
        self.relaxGapCapOvernight = relaxGapCapOvernight
        self.genuineGapBonus = genuineGapBonus
        self.overnightGapBonus = overnightGapBonus
        self.rejectOppositeCoverPct = rejectOppositeCoverPct
        self.minValidScore = minValidScore
        self.hqScoreThreshold = hqScoreThreshold
        self.legOutBodyHeavyPct = legOutBodyHeavyPct
        self.testedLegOutRetracePct = testedLegOutRetracePct
        self.maxTestedCount = maxTestedCount

        # Pine: HARD_MAX_BASE_COUNT = 3
        HARD_MAX_BASE_COUNT = 3
        self.minBaseCount = max(1, min(minBaseCountInput, maxBaseCountInput))
        self.maxBaseCount = min(maxBaseCountInput, HARD_MAX_BASE_COUNT)

        self.open = self.df["open"].to_numpy(dtype=float)
        self.high = self.df["high"].to_numpy(dtype=float)
        self.low = self.df["low"].to_numpy(dtype=float)
        self.close = self.df["close"].to_numpy(dtype=float)
        self.volume = self.df["volume"].to_numpy(dtype=float)
        self.n = len(self.df)

        self.dayofweek = self.df.index.dayofweek.to_numpy()
        self.time_ms = (self.df.index.astype(np.int64) // 10**6)

        self.active_zones: List[Zone] = []

        self.debug = debug
        self.debug_bar_indices = set(debug_bar_indices) if debug_bar_indices else None

        self._prepare_indicators()

    def _dbg(self, i, bCount, msg):
        if not self.debug:
            return
        if self.debug_bar_indices is not None and i not in self.debug_bar_indices:
            return
        ts = self.df.index[i]
        print(f"[DEBUG] bar={i} ({ts}) bCount={bCount} -> {msg}")

    # ==========================================================================
    # 2. HELPER FUNCTIONS & INDICATORS  (Pine Section 2 — गैप-अवेयर TR)
    # ==========================================================================
    def _tr_at(self, pos: int) -> float:
        """Pine: true_range()  ->  current bar ka gap-aware TR"""
        if pos < 0:
            return np.nan
        hi = self.high[pos]
        lo = self.low[pos]
        rng = hi - lo
        if pos > 0:
            prev_close = self.close[pos - 1]
            rng = max(rng, max(abs(hi - prev_close), abs(lo - prev_close)))
        return rng

    def _rma(self, series: np.ndarray, length: int) -> np.ndarray:
        """Pine: ta.rma(source, length) — SMA seed + recursive RMA"""
        n = len(series)
        result = np.full(n, np.nan)
        for i in range(n):
            if i < length - 1:
                continue
            if np.isnan(result[i - 1]) if i > 0 else True:
                window = series[i - length + 1: i + 1]
                result[i] = np.mean(window)
            else:
                result[i] = (series[i] - result[i - 1]) / length + result[i - 1]
        return result

    def _prepare_indicators(self):
        self.current_tr = np.array([self._tr_at(i) for i in range(self.n)])
        self.atr_val = self._rma(self.current_tr, self.atrPeriod)
        self.vol_sma = self.df["volume"].rolling(self.volSmaPeriod).mean().to_numpy()

    def _tr(self, i, idx):
        """Pine: tr(idx) -> lagged TR using close[idx+1] as prev_close"""
        return self._tr_at(i - idx)

    def _is_bull(self, i, idx):
        pos = i - idx
        return self.close[pos] > self.open[pos]

    def _is_bear(self, i, idx):
        pos = i - idx
        return self.open[pos] > self.close[pos]

    def _wick_pct(self, i, idx):
        pos = i - idx
        rng = self.high[pos] - self.low[pos]
        if rng == 0:
            return 0.0
        wicks = (self.high[pos] - max(self.open[pos], self.close[pos])) + \
                (min(self.open[pos], self.close[pos]) - self.low[pos])
        return wicks / rng

    def _body_pct(self, i, idx):
        pos = i - idx
        rng = self.high[pos] - self.low[pos]
        if rng == 0:
            return 0.0
        return abs(self.close[pos] - self.open[pos]) / rng

    def _body_high_low(self, i, idx):
        pos = i - idx
        return max(self.open[pos], self.close[pos]), min(self.open[pos], self.close[pos])

    def _is_overnight_gap(self, i):
        """Pine: isOvernightGap() -> dayofweek != dayofweek[1] or time-time[1] > 86400000"""
        if i == 0:
            return False
        dow_diff = self.dayofweek[i] != self.dayofweek[i - 1]
        time_diff = (self.time_ms[i] - self.time_ms[i - 1]) > 86400000
        return bool(dow_diff or time_diff)

    # ==========================================================================
    # 4. SCANNING ENGINE  (Pine Section 4 — बिल्कुल exact conversion)
    # ==========================================================================
    def _scan_bar(self, i):
        zoneFoundOnThisBar = False

        for bCount in range(self.minBaseCount, self.maxBaseCount + 1):
            if zoneFoundOnThisBar:
                break

            legOutIdx = 0
            legInIdx = bCount + 1
            prevIdx = legInIdx + 1

            pos_legIn = i - legInIdx
            if pos_legIn < 0 or np.isnan(self.atr_val[pos_legIn]):
                self._dbg(i, bCount, "REJECT: na(atr_val[legInIdx])")
                continue

            # ---------------- LEG-IN ----------------
            legInTR = self._tr(i, legInIdx)
            legInLow = self.low[pos_legIn]
            legInHigh = self.high[pos_legIn]
            legInClose = self.close[pos_legIn]
            legInVol = self.volume[pos_legIn]
            legInRng = legInHigh - legInLow

            legInIsBull = self._is_bull(i, legInIdx)
            legInIsBear = self._is_bear(i, legInIdx)

            if legInRng == 0 or self._body_pct(i, legInIdx) < self.legInMinBodyPct:
                self._dbg(i, bCount, f"REJECT: legInRng==0 or body_pct={self._body_pct(i, legInIdx):.3f} < {self.legInMinBodyPct}")
                continue

            pos_prev = i - prevIdx
            if pos_prev < 0:
                self._dbg(i, bCount, "REJECT: prevIdx out of range")
                continue

            prevIsBull = self._is_bull(i, prevIdx)
            prevIsBear = self._is_bear(i, prevIdx)
            isOppositeColor = (legInIsBull and prevIsBear) or (legInIsBear and prevIsBull)

            shouldRejectOverlap = False
            if isOppositeColor:
                prevBodyHigh, prevBodyLow = self._body_high_low(i, prevIdx)
                overlap = max(0.0, min(prevBodyHigh, legInHigh) - max(prevBodyLow, legInLow))
                coverPct = overlap / legInRng
                if coverPct >= self.rejectOppositeCoverPct:
                    shouldRejectOverlap = True
                    self._dbg(i, bCount, f"REJECT: opposite-color overlap {coverPct:.2f} >= {self.rejectOppositeCoverPct}")

            if shouldRejectOverlap:
                continue

            bullClv = (legInClose - legInLow) / legInRng
            bearClv = (legInHigh - legInClose) / legInRng

            # ---------------- BASE ----------------
            allBaseValid = True
            maxBaseTR = 0.0
            maxBaseHigh = -1.0
            minBaseLow = 1_000_000_000.0
            hasOppositeColorBase = False

            for b in range(1, bCount + 1):
                pos_b = i - b
                if pos_b < 0 or np.isnan(self.atr_val[pos_b]):
                    allBaseValid = False
                    self._dbg(i, bCount, f"REJECT: base[{b}] na(atr_val)")
                    break

                bTR = self._tr(i, b)
                if bTR > (self.maxBaseAtrMult * self.atr_val[pos_b]):
                    allBaseValid = False
                    self._dbg(i, bCount, f"REJECT: base[{b}] TR={bTR:.2f} > maxBaseAtrMult*ATR={self.maxBaseAtrMult*self.atr_val[pos_b]:.2f}")
                    break

                if bTR > maxBaseTR:
                    maxBaseTR = bTR
                if self.high[pos_b] > maxBaseHigh:
                    maxBaseHigh = self.high[pos_b]
                if self.low[pos_b] < minBaseLow:
                    minBaseLow = self.low[pos_b]

            if not allBaseValid or maxBaseTR == 0:
                continue

            # अपडेटेड नियम: bCount==1 -> 1.5, नहीं तो legInToBaseSizeMult
            effectiveBaseSizeMult = 1.5 if bCount == 1 else self.legInToBaseSizeMult
            if legInTR < (effectiveBaseSizeMult * maxBaseTR):
                self._dbg(i, bCount, f"REJECT: legInTR={legInTR:.2f} < {effectiveBaseSizeMult}*maxBaseTR={effectiveBaseSizeMult*maxBaseTR:.2f}")
                continue

            validLegIn = legInTR >= (self.legInMinAtrMult * self.atr_val[pos_legIn])
            if not validLegIn:
                self._dbg(i, bCount, f"REJECT: legInTR={legInTR:.2f} < legInMinAtrMult*ATR={self.legInMinAtrMult*self.atr_val[pos_legIn]:.2f}")
                continue

            # ---------------- LEG-OUT ----------------
            pos_legOut = i - legOutIdx
            legOutTR = self._tr(i, legOutIdx)
            legOutHigh = self.high[pos_legOut]
            legOutLow = self.low[pos_legOut]
            legOutClose = self.close[pos_legOut]
            legOutOpen = self.open[pos_legOut]
            legOutVol = self.volume[pos_legOut]

            isDemandLegOut = self._is_bull(i, legOutIdx)
            isSupplyLegOut = self._is_bear(i, legOutIdx)

            if not (isDemandLegOut or isSupplyLegOut):
                self._dbg(i, bCount, "REJECT: legOut doji")
                continue

            isLegOutExplosive = legOutTR >= (self.legOutTrMult * self.atr_val[pos_legOut])
            isLegOutWickValid = self._wick_pct(i, legOutIdx) <= self.maxWickPct
            passesTRHierarchy = (legOutTR >= self.legOutMinTrRatio * legInTR) and (legInTR > maxBaseTR)
            passesVolume = legOutVol > legInVol

            isOvernight = self._is_overnight_gap(i)

            # ---------------- IMBALANCE & GAP ----------------
            hasImbalance = True
            hasGenuineGap = False
            gapSize = 0.0

            if self.useImbalance:
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
                self._dbg(i, bCount, f"REJECT: engulfsBase(body {legOutBodyLow:.2f}-{legOutBodyHigh:.2f} vs base {minBaseLow:.2f}-{maxBaseHigh:.2f}) & no genuine gap")
                continue

            # ---------------- CLASSIFICATION ----------------
            isRBR = legInIsBull and (bullClv >= self.minClvPct) and isDemandLegOut
            isDBR = legInIsBear and (bearClv >= self.minClvPct) and isDemandLegOut
            isDBD = legInIsBear and (bearClv >= self.minClvPct) and isSupplyLegOut
            isRBD = legInIsBull and (bullClv >= self.minClvPct) and isSupplyLegOut

            isValid = (isRBR or isDBR or isDBD or isRBD) and isLegOutExplosive and isLegOutWickValid \
                and passesTRHierarchy and passesVolume and hasImbalance

            if not isValid:
                self._dbg(i, bCount,
                    f"REJECT: RBR={isRBR} DBR={isDBR} DBD={isDBD} RBD={isRBD} | "
                    f"explosive={isLegOutExplosive}(TR={legOutTR:.2f} need>={self.legOutTrMult*self.atr_val[pos_legOut]:.2f}) "
                    f"wick={isLegOutWickValid}({self._wick_pct(i,legOutIdx):.2f}<={self.maxWickPct}) "
                    f"trHier={passesTRHierarchy} vol={passesVolume}({legOutVol}>{legInVol}) "
                    f"imbalance={hasImbalance} bullClv={bullClv:.2f} bearClv={bearClv:.2f}")
                continue

            # ---------------- SCORING ----------------
            densityScore = 0

            if bCount == 1:
                densityScore += 15
            if legInTR >= (self.hqLegInAtrMult * self.atr_val[pos_legIn]):
                densityScore += 10
            if legOutTR >= (self.hqLegOutTrMult * legInTR):
                densityScore += 15
            if (legInTR >= 2.0 * maxBaseTR) and (legOutTR >= 2.0 * legInTR):
                densityScore += 15
            if legOutVol > self.vol_sma[pos_legOut]:
                densityScore += 10

            if isDemandLegOut:
                legOutBodyPos = ((legOutClose - legOutLow) / (legOutHigh - legOutLow)
                                  if (legOutHigh - legOutLow) > 0 else 0)
                legOutOwnBodyPct = self._body_pct(i, legOutIdx)
                if isDBR:
                    if (legOutBodyPos >= 0.80) or (legOutOwnBodyPct >= self.legOutBodyHeavyPct):
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
                if isDemandLegOut and self._is_bear(i, b):
                    hasOppositeColorBase = True
                    break
                elif isSupplyLegOut and self._is_bull(i, b):
                    hasOppositeColorBase = True
                    break

            if hasOppositeColorBase:
                densityScore += 10

            densityScore += 10

            if hasGenuineGap:
                densityScore += self.genuineGapBonus
            if isOvernight and hasGenuineGap:
                densityScore += self.overnightGapBonus

            if densityScore < self.minValidScore:
                self._dbg(i, bCount, f"REJECT: densityScore={densityScore} < minValidScore={self.minValidScore}")
                continue

            isHQZone = densityScore >= self.hqScoreThreshold
            zoneFoundOnThisBar = True
            self._dbg(i, bCount, f"✅ ZONE FOUND score={densityScore} HQ={isHQZone}")

            # ---------------- ZONE LEVELS ----------------
            proxVal = maxBaseHigh if isDemandLegOut else minBaseLow
            distVal = minBaseLow if isDemandLegOut else maxBaseHigh

            slVal = (distVal - self.slBufferAtr * self.atr_val[i]) if isDemandLegOut \
                else (distVal + self.slBufferAtr * self.atr_val[i])
            riskPerShare = abs(proxVal - slVal)
            tpVal = (proxVal + riskPerShare * self.targetRR) if isDemandLegOut \
                else (proxVal - riskPerShare * self.targetRR)

            legOutMidLevel = (legOutHigh - self.testedLegOutRetracePct * (legOutHigh - legOutLow)) \
                if isDemandLegOut else (legOutLow + self.testedLegOutRetracePct * (legOutHigh - legOutLow))

            # ---------------- DUPLICATE CHECK ----------------
            isDuplicate = False
            checked = 0
            if len(self.active_zones) > 0:
                for zi in range(len(self.active_zones) - 1, -1, -1):
                    checkZ = self.active_zones[zi]
                    if checkZ.state == "Broken":
                        continue
                    if checkZ.isDemand == isDemandLegOut and \
                            abs(checkZ.proxVal - proxVal) < (self.atr_val[i] * 0.25):
                        isDuplicate = True
                        break
                    checked += 1
                    if checked >= 11:
                        break

            if isDuplicate:
                self._dbg(i, bCount, "SKIPPED: duplicate zone")
                continue

            patternType = "RBR" if isRBR else ("DBR" if isDBR else ("DBD" if isDBD else "RBD"))
            zoneCat = "Continuation" if (isRBR or isDBD) else "Reversal"

            boxBorderColor = "green" if isDemandLegOut else "red"
            boxFillColor = ("green", 0.15) if isDemandLegOut else ("red", 0.15)

            zBox = Box(
                left=i - bCount - 1,
                top=proxVal,
                right=i + 15,
                bottom=distVal,
                border_color=boxBorderColor,
                bgcolor=boxFillColor,
            )

            newZone = Zone(
                proxVal=proxVal, distVal=distVal, slVal=slVal, tpVal=tpVal,
                isDemand=isDemandLegOut, isHQ=isHQZone, densityScore=densityScore,
                patternType=patternType, zoneCategory=zoneCat, state="Fresh",
                touchCount=0, startBarIndex=i - bCount, createdBarIndex=i,
                baseCount=bCount, legOutHigh=legOutHigh, legOutLow=legOutLow,
                legOutMidLevel=legOutMidLevel, isOvernight=isOvernight,
                legInTR=legInTR, legOutTR=legOutTR, zoneBox=zBox,
            )

            self.active_zones.append(newZone)

    # ==========================================================================
    # 5. ZONE STATE TRACKING & BOX UPDATES  (Pine Section 5)
    # ==========================================================================
    def _update_zone_states(self, i):
        if len(self.active_zones) == 0:
            return

        lo_t = self.low[i]
        hi_t = self.high[i]

        for zi in range(len(self.active_zones) - 1, -1, -1):
            z = self.active_zones[zi]

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

            if z.state == "Tested" and z.touchCount > self.maxTestedCount:
                z.state = "Broken"

            if z.state == "Broken":
                z.zoneBox.set_bgcolor(("gray", 0.05))
                z.zoneBox.set_border_color(("gray", 0.20))
            else:
                z.zoneBox.set_right(i + 15)

    def run(self) -> List[Zone]:
        min_bar = max(self.atrPeriod, self.maxBaseCount + 3, 11)

        for i in range(self.n):
            if i >= min_bar and not np.isnan(self.atr_val[i]):
                self._scan_bar(i)
            self._update_zone_states(i)

        return self.active_zones


# ==============================================================================
# NSE SESSION-ANCHORED N-HOUR RESAMPLER
# Root Cause Fix: TradingView "2h" chart NSE session 9:15 se anchor karke bane
# hote hain. yfinance sirf max "60m" deta hai (native 120m/2h NHI hai NSE ke
# liye). Isliye 60m data ko session-anchored tareeke se 2h/3h/4h me convert
# karna zaroori hai, taaki candle boundaries TradingView jaisi hi bane.
# ==============================================================================
def resample_nse_session(df: pd.DataFrame, n_hours: int,
                          session_start="09:15", session_end="15:30") -> pd.DataFrame:
    """
    1m/5m/15m/60m OHLCV data ko NSE session (9:15 AM anchor) ke hisaab se
    N-hour bars me convert karta hai — bilkul TradingView jaisa.

    Example n_hours=2 -> bars: 09:15-11:15, 11:15-13:15, 13:15-15:15, 15:15-15:30
    """
    df = df.sort_index().copy()
    out_frames = []

    for _, day_df in df.groupby(df.index.date):
        day_df = day_df.between_time(session_start, session_end)
        if day_df.empty:
            continue
        agg = day_df.resample(
            f"{n_hours}H", origin="start", label="left", closed="left"
        ).agg({
            "open": "first", "high": "max",
            "low": "min", "close": "last", "volume": "sum"
        })
        agg = agg.dropna(subset=["open"])
        out_frames.append(agg)

    if not out_frames:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    result = pd.concat(out_frames).sort_index()
    return result
