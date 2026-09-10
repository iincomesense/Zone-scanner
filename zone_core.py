"""
================================================================================
ZONE CORE  -  Pine Script v6 "Zone" Indicator का Exact Python Conversion
Original Indicator: © iincomesense (MPL-2.0)
--------------------------------------------------------------------------------
SECTION A (ऊपर): ZoneEngine + Box + Zone(core fields) — यह बिल्कुल वही है जो
आपने पेस्ट किया था। एक भी rule/threshold/condition नहीं बदला गया है।

SECTION B (नीचे, साफ अलग किया हुआ): "COMPATIBILITY LAYER" — यह सिर्फ इसलिए
जोड़ा गया है ताकि zscan.py/app.py (जिन्हें settings(), scan_zones(),
recommended_trade_setup() जैसे functions चाहिए) crash न हों। यहां कोई भी
नया detection rule/threshold नहीं जोड़ा गया — सिर्फ पहले से मौजूद values
(densityScore, proxVal, slVal, volume, आदि) को expose/format किया गया है।
================================================================================
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional


# ==============================================================================
# SECTION A — बिल्कुल Pine Script v6 जैसा (आपकी पेस्ट की हुई फाइल से UNCHANGED)
# ==============================================================================

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
    # ---------------- Pine v6 CORE FIELDS (UNCHANGED, koi default nahi) ----------------
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
    # ---------------- COMPATIBILITY-ONLY FIELDS (naye, defaults ke saath) ----------------
    # NOTE: Yeh fields Pine v6 ke DETECTION LOGIC ka HISSA NAHI hain. Inhe sirf
    # app.py/zscan.py ke display-columns (jaise "Score10", "Entry status")
    # crash na hon isliye jodha gaya hai. Values SECTION B me, ZoneEngine.run()
    # ke BAAD, already-computed cheezon se hi bharai jaati hain — koi nayi
    # detection condition nahi.
    riskPct: float = 0.0
    score10: int = 0
    baseColourOK: bool = True
    timestamp: object = None
    entryStatus: str = ""
    entryPrice: Optional[float] = None
    gapToLegIn: float = 0.0
    legInVolX: float = float("nan")
    legOutVolX: float = float("nan")
    retestVolX: float = float("nan")


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
# NSE SESSION-ANCHORED N-HOUR RESAMPLER  (आपकी फाइल में पहले से मौजूद, unchanged)
# ==============================================================================
def resample_nse_session(df: pd.DataFrame, n_hours: int,
                          session_start="09:15", session_end="15:30") -> pd.DataFrame:
    """
    1m/5m/15m/60m OHLCV data ko NSE session (9:15 AM anchor) ke hisaab se
    N-hour bars me convert karta hai — bilkul TradingView jaisa.
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


# ==============================================================================
# SECTION B — COMPATIBILITY LAYER (नया हिस्सा — सिर्फ zscan.py/app.py को crash
# होने से बचाने के लिए)
# --------------------------------------------------------------------------
# ⚠️ यहां से नीचे कोई भी function ZoneEngine के DETECTION LOGIC (Section A) को
# नहीं छूता। सिर्फ पहले से मौजूद values (densityScore, proxVal, slVal, volume
# आदि) को अलग नाम/फॉर्मेट में expose किया गया है ताकि zscan.py के मौजूदा calls
# (जो अभी crash हो रहे थे) काम करने लगें।
# ==============================================================================

def settings() -> dict:
    """
    ZoneEngine ke Pine v6 EXACT default parameters (Section 1) ka dict.
    zscan.scan() isko lekar override karta hai (min_score, strict-mode).
    NOTE: yahan ki values badalne se Pine v6 ke asli indicator defaults nahi
    badalte — yeh sirf ek convenience wrapper hai.
    """
    return dict(
        accountCapital=25000.0, riskPct=0.5, targetRR=5.0, slBufferAtr=0.1,
        atrPeriod=14, volSmaPeriod=20, legOutTrMult=1.2, legOutMinTrRatio=1.0,
        hqLegOutTrMult=2.0, hqLegInAtrMult=1.5, maxBaseAtrMult=1.0, maxWickPct=0.30,
        minBaseCountInput=1, maxBaseCountInput=3, legInMinAtrMult=1.0, minClvPct=0.60,
        legInToBaseSizeMult=2.0, legInMinBodyPct=0.60, useImbalance=True,
        maxImbalanceMult=1.0, relaxGapCapOvernight=True, genuineGapBonus=10,
        overnightGapBonus=15, rejectOppositeCoverPct=0.50, minValidScore=40,
        hqScoreThreshold=90, legOutBodyHeavyPct=0.60, testedLegOutRetracePct=0.50,
        maxTestedCount=2,
    )


def scan_zones(df: pd.DataFrame, params: dict = None) -> List[Zone]:
    """
    zscan.py ka main entry point (`zone_core.scan_zones(df, params=params)`).
    Params dict me se SIRF wahi keys li jaati hain jo ZoneEngine.__init__
    (Pine v6 exact) accept karta hai. Koi bhi extra/unknown key (jaise
    zscan.py ke strict-mode ke "volume_gate", "legInToBaseSizeMultSingleBase"
    placeholder keys) chup-chaap ignore ho jaati hain — isse ZoneEngine ka
    Pine v6 logic kabhi silently nahi badalta.
    """
    import inspect
    params = dict(params if params is not None else settings())
    valid_keys = set(inspect.signature(ZoneEngine.__init__).parameters) - {"self", "df"}
    engine_kwargs = {k: v for k, v in params.items() if k in valid_keys}
    engine = ZoneEngine(df, **engine_kwargs)
    zones = engine.run()
    _annotate_zone_extras(zones, df, engine)
    return zones


def _annotate_zone_extras(zones: List[Zone], df: pd.DataFrame, engine: "ZoneEngine") -> None:
    """
    ⚠️ Yeh function ZoneEngine ke Section 4 (detection) ko BILKUL NAHI chhoo
    ta — sirf already-computed values (volume, vol_sma, densityScore,
    proxVal/slVal, state) ko Zone object ki naye display-fields me daalta
    hai, taaki app.py ke table columns crash na hon.
    """
    for z in zones:
        # timestamp — Pine v6 ke apne hi createdBarIndex se
        try:
            z.timestamp = df.index[z.createdBarIndex]
        except Exception:
            z.timestamp = None

        # riskPct — proxVal/slVal se hi (Pine v6 ke apne levels, koi naya formula nahi)
        z.riskPct = round(abs(z.proxVal - z.slVal) / z.proxVal * 100, 3) if z.proxVal else 0.0

        # score10 — sirf densityScore (0-100) ko 0-10 scale me dikhana
        z.score10 = max(0, min(10, round(z.densityScore / 10)))

        # entryStatus — Pine v6 ke apne "state" field (Fresh/Tested/Broken,
        # jo _update_zone_states se hi aata hai) ka naam app.py ki terminology
        # me map karna. KOI NAYA STATE-TRANSITION RULE NAHI JODA GAYA.
        if z.state == "Fresh":
            z.entryStatus = "Waiting"
        elif z.state == "Tested":
            z.entryStatus = "Triggered"
            z.entryPrice = z.proxVal
        elif z.state == "Broken":
            z.entryStatus = "Failed-Broken"

        # legInVolX / legOutVolX — legIn/legOut ki bar-position Pine v6 ki
        # apni hi indexing se nikalte hain: legOutIdx=0 -> pos=createdBarIndex;
        # legInIdx=bCount+1 -> pos = startBarIndex - 1 (startBarIndex = i-bCount)
        pos_legOut = z.createdBarIndex
        pos_legIn = z.startBarIndex - 1
        try:
            vs_out = engine.vol_sma[pos_legOut]
            legOutVol = engine.volume[pos_legOut]
            z.legOutVolX = round(legOutVol / vs_out, 2) if vs_out and vs_out == vs_out else float("nan")
        except Exception:
            z.legOutVolX = float("nan")
        try:
            vs_in = engine.vol_sma[pos_legIn]
            legInVol = engine.volume[pos_legIn]
            z.legInVolX = round(legInVol / vs_in, 2) if vs_in and vs_in == vs_in else float("nan")
        except Exception:
            z.legInVolX = float("nan")

        # gapToLegIn — legOutTR/legInTR ka farak (dono Pine v6 me already
        # Zone fields hain) — sirf display ke liye proxy value
        z.gapToLegIn = round(abs(z.legOutTR - z.legInTR), 2)

        # baseColourOK — Pine v6 me "hasOppositeColorBase" scoring bonus ke
        # liye already calculate hoti hai par Zone me store nahi hoti. Yahan
        # base colours dobara reconstruct karna precise nahi hoga, isliye
        # safe default True rakha gaya hai — ZoneEngine ke scoring/detection
        # par iska KOI ASAR NAHI hai.

        # retestVolX — Pine v6 ke state-machine me sirf touchCount badhta hai,
        # kis exact bar par yeh nahi track hota — isliye NaN hi rehne diya
        # gaya hai (app.py isse gracefully "—" dikhata hai).


def recommended_trade_setup() -> dict:
    """
    zscan.py isko 'recommended' filter (patterns list) aur ROI-calc
    (targetRR, risk_pct, capital, slBufferAtr) ke liye use karta hai.
    Saari values Pine v6 ke apne hi input defaults se li gayi hain — koi
    nayi/alag value nahi ghadi gayi. entry_mode='prox' kyunki Pine v6 me
    entry hamesha proxVal (base high/low edge) par hoti hai.
    """
    s = settings()
    return {
        "patterns": ["RBR", "DBR", "DBD", "RBD"],   # Pine v6 ke sabhi 4 valid pattern types
        "targetRR": s["targetRR"],
        "risk_pct": s["riskPct"],
        "capital": s["accountCapital"],
        "slBufferAtr": s["slBufferAtr"],
        "entry_mode": "prox",
    }


def realistic_roi(zones: List[Zone], df: pd.DataFrame, rr: float = 5.0,
                  risk_pct: float = 0.5, capital: float = 25000.0,
                  patterns: Optional[List[str]] = None, buffer: float = 0.1,
                  entry_mode: str = "prox", max_hold: int = 40) -> dict:
    """
    Forward-walk backtest — Pine v6 ke apne hi proxVal/slVal/tpVal levels use
    karke (koi naya SL/TP formula nahi ghada gaya, wahi values jo ZoneEngine
    Section 4 me nikalta hai). Har zone ke createdBarIndex ke baad max_hold
    bars tak dekhte hain: SL (distal) pehle touch hota hai ya TP.
    """
    patterns = patterns or ["RBR", "DBR", "DBD", "RBD"]
    if df is None or df.empty or not zones:
        return {"n_trades": 0, "win_pct": 0.0, "net_roi_pct": 0.0}

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    trades = []

    for z in zones:
        if z.patternType not in patterns:
            continue
        risk_amt = capital * (risk_pct / 100.0)
        start = z.createdBarIndex + 1
        for j in range(start, min(start + max_hold, n)):
            if z.isDemand:
                if lows[j] <= z.slVal:
                    trades.append(-risk_amt)
                    break
                if highs[j] >= z.tpVal:
                    trades.append(risk_amt * rr)
                    break
            else:
                if highs[j] >= z.slVal:
                    trades.append(-risk_amt)
                    break
                if lows[j] <= z.tpVal:
                    trades.append(risk_amt * rr)
                    break

    n_trades = len(trades)
    wins = sum(1 for t in trades if t > 0)
    net = sum(trades)
    return {
        "n_trades": n_trades,
        "win_pct": round(wins / n_trades * 100, 1) if n_trades else 0.0,
        "net_roi_pct": round(net / capital * 100, 2) if capital else 0.0,
    }


def backtest_summary(zones: List[Zone], df: pd.DataFrame) -> dict:
    """Sirf ginti/aggregation — koi detection rule nahi, sirf reporting."""
    return {
        "total": len(zones),
        "fresh": sum(1 for z in zones if z.state == "Fresh"),
        "tested": sum(1 for z in zones if z.state == "Tested"),
        "broken": sum(1 for z in zones if z.state == "Broken"),
        "hq": sum(1 for z in zones if z.isHQ),
    }


def latest_active_zones(zones: List[Zone]) -> List[Zone]:
    """Fresh/Tested zones hi 'active' maani jaati hain — Pine v6 ke apne state se."""
    return [z for z in zones if z.state in ("Fresh", "Tested")]


def get_zone_alerts(zones: List[Zone], price: float, tolerance_pct: float = 0.5) -> List[Zone]:
    """Current price ke us tolerance% ke andar wali active zones."""
    out = []
    for z in zones:
        if z.state not in ("Fresh", "Tested") or not z.proxVal:
            continue
        if abs(price - z.proxVal) / z.proxVal * 100 <= tolerance_pct:
            out.append(z)
    return out


def target_context(z: Zone, df: Optional[pd.DataFrame] = None,
                   htf_df: Optional[pd.DataFrame] = None,
                   market_df: Optional[pd.DataFrame] = None,
                   vix: Optional[float] = None,
                   spx_ret20: Optional[float] = None) -> dict:
    """
    ⚠️ Yeh Pine v6 indicator ka HISSA NAHI hai — app.py ke "TP-Score" display
    badge (🎯/⚠) ke liye ek ALAG, optional analytics overlay hai. Ismein koi
    bhi cheez Zone ke DETECTION (Section A) ko affect nahi karti.
    """
    def _ema(s, span):
        return s.ewm(span=span, adjust=False).mean()

    signs, why = {}, []

    if market_df is not None and len(market_df) > 20 and "close" in market_df:
        side = market_df["close"].iloc[-1] > _ema(market_df["close"], 20).iloc[-1]
        signs["A"] = (side == z.isDemand)
        why.append(f"A: Nifty {'>' if side else '<'} EMA20")
    else:
        signs["A"] = None

    if htf_df is not None and len(htf_df) > 20 and "close" in htf_df:
        sideh = htf_df["close"].iloc[-1] > _ema(htf_df["close"], 20).iloc[-1]
        signs["B"] = (sideh == z.isDemand)
        why.append(f"B: HTF {'>' if sideh else '<'} EMA20")
    else:
        signs["B"] = None

    c = getattr(z, "legInVolX", float("nan"))
    signs["C"] = (c >= 1.0) if c == c else None
    if signs["C"] is not None:
        why.append(f"C: legInVolX={c}")

    r = getattr(z, "retestVolX", float("nan"))
    signs["D"] = (r < 1.3) if r == r else None
    if signs["D"] is not None:
        why.append(f"D: retestVolX={r}")

    if df is not None and len(df) > 21 and "close" in df:
        e = _ema(df["close"], 20)
        slope_up = e.iloc[-1] > e.iloc[-6]
        signs["E"] = (slope_up == z.isDemand)
        why.append(f"E: ownTF EMA20 slope {'up' if slope_up else 'down'}")
    else:
        signs["E"] = None

    if vix is not None:
        f_val = (vix >= 16.5 or (spx_ret20 is not None and spx_ret20 < 0)) if z.isDemand else (vix < 16.5)
        signs["F"] = f_val
        why.append(f"F: VIX={vix} spx20d={spx_ret20}")
    else:
        signs["F"] = None

    known = {k: v for k, v in signs.items() if v is not None}
    score = sum(1 for v in known.values() if v)
    mx = len(known)
    label = None
    if mx:
        label = "TP-High" if score / mx >= (4 / 6) else ("TP-Low" if score <= 2 else "TP-Mid")

    out = {"score": score, "max": mx, "label": label, "why": why}
    out.update(signs)
    return out
