import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Pine Script v6 और आपके TradingView स्क्रीनशॉट के बिल्कुल सटीक डिफ़ॉल्ट पैरामीटर्स
PINE_DEFAULTS: Dict[str, Any] = {
    "accountCapital": 25000.0, "riskPct": 0.5, "targetRR": 5.0, "slBufferAtr": 0.1,
    "atrPeriod": 14, "volSmaPeriod": 20, "legOutTrMult": 1.2, "legOutMinTrRatio": 1.0,
    "hqLegOutTrMult": 2.0, "hqLegInAtrMult": 1.5, "maxBaseAtrMult": 1.0, "maxWickPct": 0.30,
    "minBaseCountInput": 1, "maxBaseCountInput": 3, "legInMinAtrMult": 1.0,
    "minClvPct": 0.60, "legInToBaseSizeMult": 2.0, 
    "legInMinBodyPct": 0.55,  # स्क्रीनशॉट के अनुसार (Pine में 0.60 था)
    "useImbalance": True, "maxImbalanceMult": 1.0, "relaxGapCapOvernight": True,
    "genuineGapBonus": 10, "overnightGapBonus": 15, "rejectOppositeCoverPct": 0.50,
    "minValidScore": 40, "hqScoreThreshold": 90, "legOutBodyHeavyPct": 0.60,
    "testedLegOutRetracePct": 0.90,  # स्क्रीनशॉट के अनुसार (Pine में 0.50 था)
    "maxTestedCount": 2,
}

@dataclass
class Box:
    left: int; top: float; right: int; bottom: float; border_color: object; bgcolor: object
    def set_right(self, right): self.right = right
    def set_bgcolor(self, color): self.bgcolor = color
    def set_border_color(self, color): self.border_color = color

@dataclass
class Zone:
    proxVal: float; distVal: float; slVal: float; tpVal: float; isDemand: bool; isHQ: bool
    densityScore: int; patternType: str; zoneCategory: str; state: str; touchCount: int
    startBarIndex: int; createdBarIndex: int; baseCount: int; legOutHigh: float
    legOutLow: float; legOutMidLevel: float; isOvernight: bool; legInTR: float
    legOutTR: float; zoneBox: Box; timestamp: object = None; riskPct: float = float("nan")
    score10: float = float("nan"); baseColourOK: bool = False; legInVolX: float = float("nan")
    legOutVolX: float = float("nan"); retestVolX: float = float("nan")
    entryStatus: str = ""; entryPrice: float = 0.0; gapToLegIn: float = 0.0

class ZoneEngine:
    def __init__(self, df: pd.DataFrame, **kwargs):
        self.df = df.copy()
        
        for k, v in PINE_DEFAULTS.items():
            setattr(self, k, kwargs.get(k, v))
            
        HARD_MAX_BASE_COUNT = 3
        self.minBaseCount = max(1, min(self.minBaseCountInput, self.maxBaseCountInput))
        self.maxBaseCount = min(self.maxBaseCountInput, HARD_MAX_BASE_COUNT)

        self.open = self.df["open"].to_numpy(dtype=float)
        self.high = self.df["high"].to_numpy(dtype=float)
        self.low = self.df["low"].to_numpy(dtype=float)
        self.close = self.df["close"].to_numpy(dtype=float)
        self.volume = self.df["volume"].to_numpy(dtype=float)
        self.n = len(self.df)
        self.dayofweek = self.df.index.dayofweek.to_numpy()
        self.time_ms = (self.df.index.astype(np.int64) // 10**6)
        self.active_zones: List[Zone] = []
        self._prepare_indicators()

    def _tr_at(self, pos: int) -> float:
        if pos < 0: return np.nan
        hi, lo = self.high[pos], self.low[pos]
        rng = hi - lo
        if pos > 0:
            prev_close = self.close[pos - 1]
            rng = max(rng, max(abs(hi - prev_close), abs(lo - prev_close)))
        return rng

    def _rma(self, series: np.ndarray, length: int) -> np.ndarray:
        n = len(series)
        result = np.full(n, np.nan)
        for i in range(length - 1, n):
            if np.isnan(result[i - 1]) if i > 0 else True:
                result[i] = np.mean(series[i - length + 1: i + 1])
            else:
                result[i] = (series[i] - result[i - 1]) / length + result[i - 1]
        return result

    def _prepare_indicators(self):
        self.current_tr = np.array([self._tr_at(i) for i in range(self.n)])
        self.atr_val = self._rma(self.current_tr, self.atrPeriod)
        self.vol_sma = self.df["volume"].rolling(self.volSmaPeriod).mean().to_numpy()

    def _tr(self, i, idx): return self._tr_at(i - idx)
    def _is_bull(self, i, idx): pos = i - idx; return self.close[pos] > self.open[pos]
    def _is_bear(self, i, idx): pos = i - idx; return self.open[pos] > self.close[pos]
    def _body_high_low(self, i, idx): pos = i - idx; return max(self.open[pos], self.close[pos]), min(self.open[pos], self.close[pos])
    
    def _wick_pct(self, i, idx):
        pos = i - idx
        rng = self.high[pos] - self.low[pos]
        return ((self.high[pos] - max(self.open[pos], self.close[pos])) + (min(self.open[pos], self.close[pos]) - self.low[pos])) / rng if rng != 0 else 0.0

    def _body_pct(self, i, idx):
        pos = i - idx
        rng = self.high[pos] - self.low[pos]
        return abs(self.close[pos] - self.open[pos]) / rng if rng != 0 else 0.0

    def _is_overnight_gap(self, i):
        if i == 0: return False
        return bool(self.dayofweek[i] != self.dayofweek[i - 1] or (self.time_ms[i] - self.time_ms[i - 1]) > 86400000)

    def _scan_bar(self, i):
        zoneFoundOnThisBar = False
        for bCount in range(self.minBaseCount, self.maxBaseCount + 1):
            if zoneFoundOnThisBar: break
            
            legOutIdx, legInIdx, prevIdx = 0, bCount + 1, bCount + 2
            pos_legIn = i - legInIdx
            if pos_legIn < 0 or np.isnan(self.atr_val[pos_legIn]): continue

            legInTR, legInLow, legInHigh = self._tr(i, legInIdx), self.low[pos_legIn], self.high[pos_legIn]
            legInClose, legInVol, legInRng = self.close[pos_legIn], self.volume[pos_legIn], legInHigh - legInLow
            legInIsBull, legInIsBear = self._is_bull(i, legInIdx), self._is_bear(i, legInIdx)

            if legInRng == 0 or self._body_pct(i, legInIdx) < self.legInMinBodyPct: continue
            
            pos_prev = i - prevIdx
            if pos_prev < 0: continue

            # --- Pine Script Exact Logic: Opposite Color Overlap (Without Doji bypass) ---
            if (legInIsBull and self._is_bear(i, prevIdx)) or (legInIsBear and self._is_bull(i, prevIdx)):
                prevBodyHigh, prevBodyLow = self._body_high_low(i, prevIdx)
                overlap = max(0.0, min(prevBodyHigh, legInHigh) - max(prevBodyLow, legInLow))
                if overlap / legInRng >= self.rejectOppositeCoverPct: 
                    continue

            bullClv, bearClv = (legInClose - legInLow) / legInRng, (legInHigh - legInClose) / legInRng

            allBaseValid, maxBaseTR, maxBaseHigh, minBaseLow, hasOppositeColorBase = True, 0.0, -1.0, 1_000_000_000.0, False
            for b in range(1, bCount + 1):
                pos_b = i - b
                if pos_b < 0 or np.isnan(self.atr_val[pos_b]): allBaseValid = False; break
                bTR = self._tr(i, b)
                if bTR > (self.maxBaseAtrMult * self.atr_val[pos_b]): allBaseValid = False; break
                if bTR > maxBaseTR: maxBaseTR = bTR
                if self.high[pos_b] > maxBaseHigh: maxBaseHigh = self.high[pos_b]
                if self.low[pos_b] < minBaseLow: minBaseLow = self.low[pos_b]

            if not allBaseValid or maxBaseTR == 0: continue
            
            effectiveBaseSizeMult = 1.5 if bCount == 1 else self.legInToBaseSizeMult
            if legInTR < (effectiveBaseSizeMult * maxBaseTR) or legInTR < (self.legInMinAtrMult * self.atr_val[pos_legIn]): continue

            pos_legOut = i - legOutIdx
            legOutTR, legOutHigh, legOutLow = self._tr(i, legOutIdx), self.high[pos_legOut], self.low[pos_legOut]
            legOutClose, legOutOpen, legOutVol = self.close[pos_legOut], self.open[pos_legOut], self.volume[pos_legOut]
            isDemandLegOut, isSupplyLegOut = self._is_bull(i, legOutIdx), self._is_bear(i, legOutIdx)

            if not (isDemandLegOut or isSupplyLegOut): continue

            # --- Pine Script Exact Logic: isLegOutExplosive uses ATR ---
            isLegOutExplosive = legOutTR >= (self.legOutTrMult * self.atr_val[pos_legOut])
            
            isLegOutWickValid = self._wick_pct(i, legOutIdx) <= self.maxWickPct
            passesTRHierarchy = (legOutTR >= self.legOutMinTrRatio * legInTR) and (legInTR > maxBaseTR)
            
            legOutVolumeMissing = not np.isfinite(legOutVol) or legOutVol <= 0
            passesVolume = legOutVolumeMissing or legOutVol > legInVol
            isOvernight = self._is_overnight_gap(i)

            hasImbalance, hasGenuineGap, gapSize = True, False, 0.0
            if self.useImbalance:
                if isDemandLegOut:
                    hasGenuineGap = legOutLow > maxBaseHigh
                    hasImbalance = hasGenuineGap or (legOutClose > legInHigh)
                    gapSize = max(0.0, legOutLow - maxBaseHigh)
                elif isSupplyLegOut:
                    hasGenuineGap = legOutHigh < minBaseLow
                    hasImbalance = hasGenuineGap or (legOutClose < legInLow)
                    gapSize = max(0.0, minBaseLow - legOutHigh)

            legOutBodyHigh, legOutBodyLow = max(legOutOpen, legOutClose), min(legOutOpen, legOutClose)
            if (legOutBodyLow <= minBaseLow) and (legOutBodyHigh >= maxBaseHigh) and not hasGenuineGap: continue

            isRBR = legInIsBull and (bullClv >= self.minClvPct) and isDemandLegOut
            isDBR = legInIsBear and (bearClv >= self.minClvPct) and isDemandLegOut
            isDBD = legInIsBear and (bearClv >= self.minClvPct) and isSupplyLegOut
            isRBD = legInIsBull and (bullClv >= self.minClvPct) and isSupplyLegOut

            if not ((isRBR or isDBR or isDBD or isRBD) and isLegOutExplosive and isLegOutWickValid and passesTRHierarchy and passesVolume and hasImbalance): continue

            densityScore = 15 if bCount == 1 else 0
            if legInTR >= (self.hqLegInAtrMult * self.atr_val[pos_legIn]): densityScore += 10
            if legOutTR >= (self.hqLegOutTrMult * legInTR): densityScore += 15
            if (legInTR >= 2.0 * maxBaseTR) and (legOutTR >= 2.0 * legInTR): densityScore += 15
            if legOutVol > self.vol_sma[pos_legOut]: densityScore += 10

            if isDemandLegOut:
                legOutBodyPos = ((legOutClose - legOutLow) / (legOutHigh - legOutLow)) if (legOutHigh - legOutLow) > 0 else 0
                if isDBR and ((legOutBodyPos >= 0.80) or (self._body_pct(i, legOutIdx) >= self.legOutBodyHeavyPct)): densityScore += 15
                elif not isDBR and legOutBodyPos >= 0.80: densityScore += 15
            else:
                legOutBodyPos = ((legOutHigh - legOutClose) / (legOutHigh - legOutLow)) if (legOutHigh - legOutLow) > 0 else 0
                if legOutBodyPos >= 0.80: densityScore += 15

            for b in range(1, bCount + 1):
                if (isDemandLegOut and self._is_bear(i, b)) or (isSupplyLegOut and self._is_bull(i, b)):
                    hasOppositeColorBase = True
                    break

            if hasOppositeColorBase: densityScore += 10
            densityScore += 10
            if hasGenuineGap: densityScore += self.genuineGapBonus
            if isOvernight and hasGenuineGap: densityScore += self.overnightGapBonus

            if densityScore < self.minValidScore: continue
            
            isHQZone = densityScore >= self.hqScoreThreshold
            zoneFoundOnThisBar = True

            proxVal = maxBaseHigh if isDemandLegOut else minBaseLow
            distVal = minBaseLow if isDemandLegOut else maxBaseHigh
            slVal = (distVal - self.slBufferAtr * self.atr_val[i]) if isDemandLegOut else (distVal + self.slBufferAtr * self.atr_val[i])
            riskPerShare = abs(proxVal - slVal)
            tpVal = (proxVal + riskPerShare * self.targetRR) if isDemandLegOut else (proxVal - riskPerShare * self.targetRR)
            legOutMidLevel = (legOutHigh - self.testedLegOutRetracePct * (legOutHigh - legOutLow)) if isDemandLegOut else (legOutLow + self.testedLegOutRetracePct * (legOutHigh - legOutLow))

            isDuplicate, checked = False, 0
            for checkZ in reversed(self.active_zones):
                if checkZ.state == "Broken": continue
                if checkZ.isDemand == isDemandLegOut and abs(checkZ.proxVal - proxVal) < (self.atr_val[i] * 0.25):
                    isDuplicate = True
                    break
                if (checked := checked + 1) >= 11: break
            if isDuplicate: continue

            boxBorderColor, boxFillColor = ("green", ("green", 0.15)) if isDemandLegOut else ("red", ("red", 0.15))
            newZone = Zone(
                proxVal=proxVal, distVal=distVal, slVal=slVal, tpVal=tpVal, isDemand=isDemandLegOut, isHQ=isHQZone,
                densityScore=densityScore, patternType="RBR" if isRBR else ("DBR" if isDBR else ("DBD" if isDBD else "RBD")),
                zoneCategory="Continuation" if (isRBR or isDBD) else "Reversal", state="Fresh", touchCount=0,
                startBarIndex=i - bCount, createdBarIndex=i, baseCount=bCount, legOutHigh=legOutHigh, legOutLow=legOutLow,
                legOutMidLevel=legOutMidLevel, isOvernight=isOvernight, legInTR=legInTR, legOutTR=legOutTR,
                zoneBox=Box(left=i - bCount - 1, top=proxVal, right=i + 15, bottom=distVal, border_color=boxBorderColor, bgcolor=boxFillColor),
                timestamp=self.df.index[i], riskPct=(riskPerShare / proxVal * 100.0) if proxVal else float("nan"),
                score10=densityScore / 10.0, baseColourOK=hasOppositeColorBase,
                legInVolX=(legInVol / self.vol_sma[pos_legIn] if self.vol_sma[pos_legIn] and not np.isnan(self.vol_sma[pos_legIn]) else float("nan")),
                legOutVolX=(legOutVol / self.vol_sma[pos_legOut] if self.vol_sma[pos_legOut] and not np.isnan(self.vol_sma[pos_legOut]) else float("nan")),
                gapToLegIn=gapSize
            )
            self.active_zones.append(newZone)

    def _update_zone_states(self, i):
        if not self.active_zones: return
        lo_t, hi_t = self.low[i], self.high[i]

        for z in reversed(self.active_zones):
            if z.state == "Fresh":
                if z.isDemand:
                    if lo_t <= z.distVal: z.state = "Broken"
                    elif lo_t <= z.legOutMidLevel: z.state, z.touchCount = "Tested", z.touchCount + 1
                else:
                    if hi_t >= z.distVal: z.state = "Broken"
                    elif hi_t >= z.legOutMidLevel: z.state, z.touchCount = "Tested", z.touchCount + 1
            elif z.state == "Tested":
                if z.isDemand:
                    if lo_t <= z.distVal: z.state = "Broken"
                    elif lo_t <= z.legOutMidLevel: z.touchCount += 1
                else:
                    if hi_t >= z.distVal: z.state = "Broken"
                    elif hi_t >= z.legOutMidLevel: z.touchCount += 1

            if z.state == "Tested" and z.touchCount > self.maxTestedCount: z.state = "Broken"
            if z.state == "Broken": z.zoneBox.set_bgcolor(("gray", 0.05)); z.zoneBox.set_border_color(("gray", 0.20))
            else: z.zoneBox.set_right(i + 15)

    def run(self) -> List[Zone]:
        min_bar = max(self.atrPeriod, self.maxBaseCount + 3, 11)
        for i in range(min_bar, self.n):
            if not np.isnan(self.atr_val[i]): self._scan_bar(i)
            self._update_zone_states(i)
        return self.active_zones

def settings(**overrides) -> Dict[str, Any]:
    result = dict(PINE_DEFAULTS)
    result.update(overrides)
    return result

def scan_zones(df: pd.DataFrame, params: Optional[Dict[str, Any]] = None) -> List[Zone]:
    config = settings(**(params or {}))
    engine_config = {key: value for key, value in config.items() if key in PINE_DEFAULTS}
    return ZoneEngine(df, **engine_config).run()

def recommended_trade_setup() -> Dict[str, Any]:
    return {"patterns": ["RBR", "DBR", "DBD", "RBD"], "targetRR": PINE_DEFAULTS["targetRR"], "risk_pct": PINE_DEFAULTS["riskPct"], "capital": PINE_DEFAULTS["accountCapital"], "slBufferAtr": PINE_DEFAULTS["slBufferAtr"], "entry_mode": "prox"}

def backtest_summary(zones: List[Zone], df: pd.DataFrame) -> Dict[str, Any]:
    active = [z for z in zones if z.state in ("Fresh", "Tested")]
    return {"n_zones": len(zones), "n_active": len(active), "n_broken": sum(z.state == "Broken" for z in zones), "avg_score": (sum(z.densityScore for z in zones) / len(zones) if zones else 0.0)}

def realistic_roi(zones: List[Zone], df: pd.DataFrame, rr: float = 5.0, risk_pct: float = 0.5, capital: float = 25000.0, patterns: Optional[List[str]] = None, buffer: float = 0.1, entry_mode: str = "prox", max_hold: int = 40) -> Dict[str, Any]:
    selected = [z for z in zones if not patterns or z.patternType in patterns]
    return {"n_trades": 0, "win_pct": 0.0, "net_roi_pct": 0.0, "sample_zones": len(selected), "risk_pct": risk_pct, "capital": capital, "targetRR": rr}

def target_context(zone: Zone, df: Optional[pd.DataFrame] = None, htf_df: Optional[pd.DataFrame] = None, market_df: Optional[pd.DataFrame] = None, vix: Optional[float] = None, spx_ret20: Optional[float] = None) -> Dict[str, Any]:
    return {"score": None, "max": 6, "label": "—", "why": [], "A": None, "B": None, "C": None, "D": None, "E": None, "F": None}

def latest_active_zones(zones: List[Zone]) -> List[Zone]:
    return [z for z in zones if z.state in ("Fresh", "Tested")]

def get_zone_alerts(zones: List[Zone], price: float) -> List[Zone]:
    return [z for z in latest_active_zones(zones) if min(z.proxVal, z.distVal) <= price <= max(z.proxVal, z.distVal)]

def resample_nse_session(df: pd.DataFrame, n_hours: int, session_start="09:15", session_end="15:30") -> pd.DataFrame:
    df = df.sort_index().copy()
    out_frames = []
    for _, day_df in df.groupby(df.index.date):
        day_df = day_df.between_time(session_start, session_end)
        if day_df.empty: continue
        agg = day_df.resample(f"{n_hours}H", origin="start", label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["open"])
        out_frames.append(agg)
    return pd.concat(out_frames).sort_index() if out_frames else pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
