"""
zone_core_merged_fixed.py — PERFORMANCE-FIXED ENGINE
=====================================================
यह file आपकी दी हुई `zone_core_merged.py` का ठीक किया हुआ (bug-fixed) version है।
Logic/behaviour bilkul same रखा गया है (RULE 1, RULE 2, RULE 3 unchanged) —
सिर्फ़ नीचे दिए गए performance bugs ठीक किए गए हैं:

BUG #1 (सबसे बड़ी वजह "बहुत स्लो" होने की):
    `_HTF_ZONE_CACHE` में key के तौर पर `id(h)` इस्तेमाल हो रहा था।
    हर `scan_zones()` call पर `_auto_higher_frames()` एक नया DataFrame object
    बनाता है, इसलिए `id(h)` हर बार अलग आता है => cache कभी hit ही नहीं होता,
    और हर call पर 8 higher-timeframes (30m..1mo) के लिए पूरा `ZoneEngine().run()`
    दोबारा (from scratch) चलता है। साथ ही `id()` reuse होने पर गलत zones cache
    से वापस मिलने का correctness-risk भी था।
    FIX: content-based fingerprint (len, first/last timestamp, close-checksum)
    को cache key बनाया — अब cache असल में काम करता है।

BUG #2 (extra overhead):
    `_auto_higher_frames(df, base_tf)` — जो resampling करके 30m/1h/2h/4h/6h/
    1d/1wk/1mo frames बनाता है — हर call पर पूरी history पर दोबारा चलता था।
    FIX: इसके output को भी fingerprint-based module-level cache में रखा गया।

BUG #3 (constant-factor slowness):
    ATR/TR calculation pure-Python loops से हो रहा था:
      - `_tr_at()` को हर bar के लिए list-comprehension में call किया जाता था
      - `ZoneEngine._rma()` एक हाथ से लिखा हुआ Python for-loop था
    यह base engine के अलावा हर higher-timeframe engine पर भी (कुल ~9 बार हर
    scan_zones() call में) चलता था।
    FIX: TR को NumPy से vectorize किया, और RMA (Wilder smoothing) को
    pandas के C-optimized `ewm(adjust=False)` से (SMA-seed रखते हुए) लागू
    किया — output गणितीय रूप से बिल्कुल identical है, बस बहुत तेज़ है।
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ============================== INPUTS (unchanged) ==============================
PINE_DEFAULTS: Dict[str, Any] = {
    "accountCapital": 25000.0, "riskPct": 0.5, "targetRR": 5.0, "slBufferAtr": 0.1,
    "atrPeriod": 14, "volSmaPeriod": 20, "legOutTrMult": 1.2, "legOutMinTrRatio": 1.0,
    "hqLegOutTrMult": 2.0, "hqLegInAtrMult": 1.5, "maxBaseAtrMult": 1.0, "maxWickPct": 0.30,
    "minBaseCountInput": 1, "maxBaseCountInput": 3, "legInMinAtrMult": 1.0,
    "minClvPct": 0.60, "legInToBaseSizeMult": 2.0,
    "legInMinBodyPct": 0.55,
    "useImbalance": True, "maxImbalanceMult": 1.0, "relaxGapCapOvernight": True,
    "genuineGapBonus": 10, "overnightGapBonus": 15, "rejectOppositeCoverPct": 0.50,
    "minValidScore": 40, "hqScoreThreshold": 90, "legOutBodyHeavyPct": 0.60,
    "testedLegOutRetracePct": 1.0,
    "testedOnProximal": True,
    "maxTestedCount": 2,
    "mtfEnabled": True,
    "mtfGapAtrMult": 0.25,
    "mtfPivotSwing": 2,
    "pivotGapBonus": True,
    "confluenceBonus": 15,
    "confluenceOverlap": 0.5,
    "rejectHtfGap": False, "requireSolidLegOut": False, "rejectSolidLegIn": False,
    "requireHtfConfluence": False, "mtfLegSolidPct": 0.65,
}

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")

TF_ORDER = ["15m", "30m", "1h", "2h", "4h", "6h", "1d", "1wk", "1mo"]
TF_LADDER = {
    "15m": ["30m", "1h", "2h", "4h", "6h", "1d", "1wk", "1mo"],
    "30m": ["1h", "2h", "4h", "6h", "1d", "1wk", "1mo"],
    "1h": ["2h", "4h", "6h", "1d", "1wk", "1mo"],
    "2h": ["4h", "6h", "1d", "1wk", "1mo"],
    "4h": ["6h", "1d", "1wk", "1mo"],
    "6h": ["1d", "1wk", "1mo"],
    "1d": ["1wk", "1mo"],
    "1wk": ["1mo"],
    "1mo": [],
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
    isHQ_base: bool = False
    isHQ_v4match: bool = False
    mtf_tf: str = ""
    mtf_overlap: float = float("nan")
    pgap_tf: str = ""


# ============================== FIXED helpers ==============================
def rma(series: np.ndarray, length: int) -> np.ndarray:
    """Wilder's RMA — अब pandas के C-optimized ewm() से vectorized (BUG #3 fix)।
    Output पुराने Python-loop version जैसा ही (SMA-seed + recursive) है, बस तेज़।"""
    n = len(series)
    out = np.full(n, np.nan)
    if n < length:
        return out
    seed = np.mean(series[:length])
    tail = series[length:]
    if len(tail) == 0:
        out[length - 1] = seed
        return out
    alpha = 1.0 / length
    s = pd.Series(np.concatenate(([seed], tail)))
    ema = s.ewm(alpha=alpha, adjust=False).mean().to_numpy()
    out[length - 1:] = ema
    return out


def _vectorized_true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """पहले हर bar के लिए Python function call (`_tr_at`) से TR निकाला जाता था।
    अब पूरी series एक साथ NumPy से (BUG #3 fix)। i=0 के लिए result वैसा ही
    रहता है क्योंकि close[0] हमेशा [low[0], high[0]] के अंदर होता है।"""
    prev_close = np.empty_like(close)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]
    rng = high - low
    tr = np.maximum(rng, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    return tr


def _prep_frame(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if df is None or len(df) == 0:
        return None
    if (df.index.tz is None and "volume" in df.columns and
        df["open"].notna().all() and df["high"].notna().all() and
        df["low"].notna().all() and df["close"].notna().all()):
        return df
    df = df.dropna(subset=["open", "high", "low", "close"]).copy()
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["volume"] = df["volume"].fillna(0.0)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
    return df


def infer_tf(df: pd.DataFrame) -> str:
    if len(df) < 2:
        return "1d"
    diff_secs = pd.Series(df.index).diff().dt.total_seconds().median()
    for tf, lim in (("15m", 1300), ("30m", 2600), ("1h", 5200),
                    ("2h", 10400), ("4h", 20800), ("6h", 31200),
                    ("1d", 130000), ("1wk", 900000)):
        if diff_secs <= lim:
            return tf
    return "1mo"


def resample_nse_session(df: pd.DataFrame, n_hours: int, session_start="09:15", session_end="15:30") -> pd.DataFrame:
    df = df.sort_index().copy()
    out_frames = []
    for _, day_df in df.groupby(df.index.date):
        day_df = day_df.between_time(session_start, session_end)
        if day_df.empty:
            continue
        agg = day_df.resample(f"{n_hours}h", origin="start", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        ).dropna(subset=["open"])
        out_frames.append(agg)
    return pd.concat(out_frames).sort_index() if out_frames else pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


def _frame_fingerprint(h: pd.DataFrame) -> tuple:
    """Content-based fingerprint — id(h) की जगह (BUG #1/#2 fix)। दो अलग calls
    में अगर डेटा वही है तो fingerprint भी वही रहेगा, चाहे DataFrame object नया
    (नया id()) ही क्यों न बना हो — इसीलिए cache असल में hit करता है।"""
    n = len(h)
    if n == 0:
        return (0, 0, 0, 0.0, 0.0)
    idx = h.index
    first_ts = int(idx[0].value)
    last_ts = int(idx[-1].value)
    close = h["close"].to_numpy(dtype=float)
    step = max(1, n // 64)
    sample = close[::step]
    checksum = float(np.nansum(sample))
    last_close = float(close[-1])
    return (n, first_ts, last_ts, round(checksum, 4), round(last_close, 6))


def _df_fingerprint(df: pd.DataFrame) -> tuple:
    return _frame_fingerprint(df)


_HIGHER_FRAMES_CACHE: Dict[Any, Any] = {}


def _auto_higher_frames(df: pd.DataFrame, base_tf: str) -> Dict[str, pd.DataFrame]:
    """FIX: base df+base_tf के fingerprint पर cached — इसलिए बार-बार वही data
    resample नहीं होता (BUG #2)।"""
    cache_key = (_df_fingerprint(df), base_tf)
    cached = _HIGHER_FRAMES_CACHE.get(cache_key)
    if cached is not None:
        return cached

    out: Dict[str, pd.DataFrame] = {}
    agg_dict = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df.columns:
        agg_dict["volume"] = "sum"
    for tgt in TF_LADDER.get(base_tf, []):
        r = None
        try:
            if tgt in ("30m", "1h"):
                m = 30 if tgt == "30m" else 60
                r = df.resample(f"{m}min", label="left", closed="left").agg(agg_dict).dropna(subset=["open"])
            elif tgt in ("2h", "4h", "6h"):
                r = resample_nse_session(df, int(tgt[:-1]))
            elif tgt == "1d":
                r = df.groupby(df.index.floor("1D")).agg(agg_dict).dropna(subset=["open"])
            elif tgt == "1wk":
                g = df.groupby(df.index.to_period("W-MON")).agg(agg_dict).dropna(subset=["open"])
                g.index = g.index.map(lambda p: p.start_time)
                r = g
            elif tgt == "1mo":
                g = df.groupby(df.index.to_period("M")).agg(agg_dict).dropna(subset=["open"])
                g.index = g.index.map(lambda p: p.start_time)
                r = g
        except Exception:
            r = None
        if r is not None and len(r) >= 6:
            out[tgt] = r

    _HIGHER_FRAMES_CACHE[cache_key] = out
    if len(_HIGHER_FRAMES_CACHE) > 256:
        _HIGHER_FRAMES_CACHE.pop(next(iter(_HIGHER_FRAMES_CACHE)))
    return out


_HTF_ZONE_CACHE: Dict[Any, Any] = {}


class MtfContext:
    """v4 का MTF context — merged file में केवल HQ HIGHLIGHTING के लिए (RULE 3)।
    यहां से कोई zone कभी remove/reject नहीं होता (RULE 2)।"""

    def __init__(self, df: pd.DataFrame, half_df: Optional[pd.DataFrame],
                 higher_frames: Dict[str, pd.DataFrame], base_tf: str, params: Dict[str, Any]):
        self.base_tf = base_tf
        self.ladder = [t for t in TF_LADDER.get(base_tf, []) if t in higher_frames and higher_frames[t] is not None and len(higher_frames[t]) >= 6]
        idx = df.index.astype(np.int64) // 10**6
        self.base_dur_ms = float(np.median(np.diff(idx))) if len(idx) > 2 else 0.0
        self.time_ms_arr = idx.to_numpy()

        self.gap: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
        self.pgap: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray, list]] = {}
        self.conf: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray, list]] = {}
        self.conf_overlap = float(params.get("confluenceOverlap", 0.5))

        swing = int(params.get("mtfPivotSwing", 2))
        gap_mult = float(params.get("mtfGapAtrMult", 0.25))
        engine_config = {k: v for k, v in params.items() if k in PINE_DEFAULTS}
        engine_config_key = str(sorted(engine_config.items()))

        for htf in self.ladder:
            h = _prep_frame(higher_frames[htf])
            if h is None or len(h) < 6:
                continue
            o = h["open"].to_numpy(float)
            h_ = h["high"].to_numpy(float)
            l = h["low"].to_numpy(float)
            c = h["close"].to_numpy(float)
            hm = h.index.astype(np.int64) // 10**6
            n = len(h)
            tr = _vectorized_true_range(h_, l, c)
            atr = rma(tr, 14)

            gap_flag = np.zeros(n, bool)
            if n > 1:
                g = np.abs(o[1:] - c[:-1])
                a = atr[1:]
                valid = np.isfinite(a) & (a > 0)
                valid_idx = np.where(valid)[0] + 1
                gap_flag[valid_idx] = g[valid] >= gap_mult * a[valid]
            self.gap[htf] = (hm.to_numpy(), gap_flag)

            plo = np.zeros(n, bool)
            phi = np.zeros(n, bool)
            if n > 2 * swing:
                mid_l = l[swing:n - swing]
                mid_h = h_[swing:n - swing]
                cl = np.ones(n - 2 * swing, bool)
                ch = np.ones(n - 2 * swing, bool)
                for s in range(1, swing + 1):
                    cl &= mid_l <= l[swing - s:n - swing - s]
                    cl &= mid_l <= l[swing + s:n - swing + s]
                    ch &= mid_h >= h_[swing - s:n - swing - s]
                    ch &= mid_h >= h_[swing + s:n - swing + s]
                plo[swing:n - swing] = cl
                phi[swing:n - swing] = ch

            pairs = []
            if n > 2:
                for p in np.where(plo | phi)[0]:
                    q = p + 1
                    if q >= n or not (np.isfinite(atr[q]) and atr[q] > 0):
                        continue
                    if plo[p] and o[q] > c[p] and (o[q] - c[p]) >= gap_mult * atr[q]:
                        pairs.append((int(q), float(c[p]), float(o[q]), 1))
                    if phi[p] and o[q] < c[p] and (c[p] - o[q]) >= gap_mult * atr[q]:
                        pairs.append((int(q), float(o[q]), float(c[p]), -1))
            self.pgap[htf] = (hm.to_numpy(), l, h_, pairs)

            if len(h) >= 30:
                # ===== BUG #1 FIX: id(h) की जगह content-fingerprint से cache key =====
                key = (htf, _frame_fingerprint(h), engine_config_key)
                cached = _HTF_ZONE_CACHE.get(key)
                if cached is None:
                    sub = ZoneEngine(h, mtf=None, **engine_config).run()
                    zs = [(z.createdBarIndex, bool(z.isDemand), z.proxVal, z.distVal) for z in sub if z.createdBarIndex < len(h)]
                    cached = (h, zs)
                    _HTF_ZONE_CACHE[key] = cached
                    if len(_HTF_ZONE_CACHE) > 512:
                        _HTF_ZONE_CACHE.pop(next(iter(_HTF_ZONE_CACHE)))
                self.conf[htf] = (hm.to_numpy(), l, h_, cached[1])

        self.half = None
        hd = _prep_frame(half_df)
        if hd is not None and len(hd) >= 4:
            self.half = ((hd.index.astype(np.int64) // 10**6).to_numpy(), hd["high"].to_numpy(float), hd["low"].to_numpy(float))

    def containing(self, arr: np.ndarray, t_ms: float) -> int:
        return int(np.searchsorted(arr, t_ms, side="right")) - 1

    def confidence_at(self, t_ms: float, demand: bool, zhi: float, zlo: float, cur_low: float, cur_high: float) -> Tuple[str, float]:
        depth = zhi - zlo
        if depth <= 0:
            return "", float("nan")
        for htf in self.ladder:
            if htf not in self.conf:
                continue
            hm, lows, highs, zs = self.conf[htf]
            k = self.containing(hm, t_ms)
            if k < 1:
                continue
            best = float("nan")
            for (j, zd, zp, zdv) in zs:
                if zd != demand or j >= k:
                    continue
                lo1, hi1 = min(zp, zdv), max(zp, zdv)
                ov = min(zhi, hi1) - max(zlo, lo1)
                if ov <= 0:
                    continue
                if demand:
                    seg = lows[j + 1:k]
                    m = min(float(seg.min()) if len(seg) else float("inf"), cur_low)
                    if m <= zdv:
                        continue
                else:
                    seg = highs[j + 1:k]
                    m = max(float(seg.max()) if len(seg) else float("-inf"), cur_high)
                    if m >= zdv:
                        continue
                r = ov / depth
                if not np.isfinite(best) or r > best:
                    best = r
            if np.isfinite(best):
                return htf, float(best)
        return "", float("nan")

    def pivot_gap_at(self, t_ms: float, demand: bool, zlo: float, zhi: float) -> Tuple[str, float]:
        want = 1 if demand else -1
        for htf in self.ladder:
            if htf not in self.pgap:
                continue
            hm, lows, highs, pairs = self.pgap[htf]
            k = self.containing(hm, t_ms)
            if k < 1:
                continue
            best = float("nan")
            for (q, wlo, whi, d) in pairs:
                if d != want or q > k:
                    continue
                ov = min(zhi, whi) - max(zlo, wlo)
                if ov <= 0:
                    continue
                seg_lo, seg_hi = lows[q + 1:k], highs[q + 1:k]
                if len(seg_lo) and bool(np.any((seg_lo <= wlo) & (seg_hi >= whi))):
                    continue
                r = ov / max(zhi - zlo, 1e-12)
                if not np.isfinite(best) or r > best:
                    best = r
            if np.isfinite(best):
                return htf, float(best)
        return "", float("nan")


# ============================== ENGINE (logic unchanged, indicators vectorized) ==============================
class ZoneEngine:
    def __init__(self, df: pd.DataFrame, mtf: Optional[MtfContext] = None, **kwargs):
        if df is None or len(df) == 0:
            raise ValueError("इनपुट DataFrame खाली है — ज़ोन स्कैन करने के लिए OHLCV डेटा चाहिए।")

        work_df = df.copy()
        work_df.columns = [str(c).strip().lower() for c in work_df.columns]
        missing_cols = [c for c in REQUIRED_COLUMNS if c not in work_df.columns]
        if missing_cols:
            raise ValueError(f"DataFrame में आवश्यक कॉलम नहीं मिले: {missing_cols}")
        if not isinstance(work_df.index, pd.DatetimeIndex):
            raise TypeError("DataFrame का index pandas DatetimeIndex होना चाहिए (टाइमस्टैम्प के साथ)।")

        work_df = work_df.sort_index()
        work_df = work_df[~work_df.index.duplicated(keep="last")]
        self.df = work_df
        self.mtf = mtf

        for k, v in PINE_DEFAULTS.items():
            setattr(self, k, kwargs.get(k, v))

        HARD_MAX_BASE_COUNT = 3
        self.minBaseCount = max(1, min(self.minBaseCountInput, self.maxBaseCountInput))
        self.maxBaseCount = max(self.minBaseCount, min(self.maxBaseCountInput, HARD_MAX_BASE_COUNT))

        self.open = self.df["open"].to_numpy(dtype=float)
        self.high = self.df["high"].to_numpy(dtype=float)
        self.low = self.df["low"].to_numpy(dtype=float)
        self.close = self.df["close"].to_numpy(dtype=float)
        self.volume = self.df["volume"].to_numpy(dtype=float)
        self.n = len(self.df)
        self.dayofweek = self.df.index.dayofweek.to_numpy()
        self.time_ms = self.df.index.asi8 // 10**6
        self.active_zones: List[Zone] = []
        self._prepare_indicators()

    def _tr_at(self, pos: int) -> float:
        # अब केवल reference/compat के लिए रखा गया है (BUG #3 fix से main path
        # पर अब यह call ही नहीं होता — देखें _prepare_indicators)
        if pos < 0: return np.nan
        hi, lo = self.high[pos], self.low[pos]
        rng = hi - lo
        if pos > 0:
            prev_close = self.close[pos - 1]
            rng = max(rng, max(abs(hi - prev_close), abs(lo - prev_close)))
        return rng

    def _rma(self, series: np.ndarray, length: int) -> np.ndarray:
        # BUG #3 FIX: पुराना हाथ से लिखा Python for-loop हटाकर module-level
        # vectorized rma() (pandas ewm आधारित) इस्तेमाल किया — output identical।
        return rma(series, length)

    def _prepare_indicators(self):
        # BUG #3 FIX: list-comprehension से हर bar पर _tr_at() call करने की
        # जगह पूरी series को एक साथ NumPy से vectorize किया।
        self.current_tr = _vectorized_true_range(self.high, self.low, self.close)
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

            passesGapCap = True
            if self.useImbalance and hasGenuineGap and not (self.relaxGapCapOvernight and isOvernight):
                maxAllowedGap = self.maxImbalanceMult * self.atr_val[pos_legOut]
                passesGapCap = gapSize <= maxAllowedGap

            legOutBodyHigh, legOutBodyLow = max(legOutOpen, legOutClose), min(legOutOpen, legOutClose)
            if (legOutBodyLow <= minBaseLow) and (legOutBodyHigh >= maxBaseHigh) and not hasGenuineGap: continue

            isRBR = legInIsBull and (bullClv >= self.minClvPct) and isDemandLegOut
            isDBR = legInIsBear and (bearClv >= self.minClvPct) and isDemandLegOut
            isDBD = legInIsBear and (bearClv >= self.minClvPct) and isSupplyLegOut
            isRBD = legInIsBull and (bullClv >= self.minClvPct) and isSupplyLegOut

            if not ((isRBR or isDBR or isDBD or isRBD) and isLegOutExplosive and isLegOutWickValid
                    and passesTRHierarchy and passesVolume and hasImbalance and passesGapCap): continue

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

            isHQ_base = densityScore >= self.hqScoreThreshold
            zoneFoundOnThisBar = True

            proxVal = maxBaseHigh if isDemandLegOut else minBaseLow
            distVal = minBaseLow if isDemandLegOut else maxBaseHigh
            slVal = (distVal - self.slBufferAtr * self.atr_val[i]) if isDemandLegOut else (distVal + self.slBufferAtr * self.atr_val[i])
            riskPerShare = abs(proxVal - slVal)
            tpVal = (proxVal + riskPerShare * self.targetRR) if isDemandLegOut else (proxVal - riskPerShare * self.targetRR)
            legOutMidLevel = (legOutHigh - self.testedLegOutRetracePct * (legOutHigh - legOutLow)) if isDemandLegOut else (legOutLow + self.testedLegOutRetracePct * (legOutHigh - legOutLow))

            isDuplicate, checked = False, 0
            for checkZ in reversed(self.active_zones):
                checked += 1
                if checkZ.state != "Broken" and checkZ.isDemand == isDemandLegOut and abs(checkZ.proxVal - proxVal) < (self.atr_val[i] * 0.25):
                    isDuplicate = True
                    break
                if checked >= 11: break
            if isDuplicate: continue

            mtf_tf, mtf_ov, pgap_tf = "", float("nan"), ""
            if self.mtf is not None:
                t_ms = int(self.time_ms[i])
                conf_tf, conf_ov = self.mtf.confidence_at(t_ms, isDemandLegOut, maxBaseHigh, minBaseLow, self.low[i], self.high[i])
                if conf_tf and np.isfinite(conf_ov) and conf_ov >= self.confluenceOverlap:
                    mtf_tf, mtf_ov = conf_tf, float(conf_ov)
                if self.pivotGapBonus:
                    pg_tf, pg_ov = self.mtf.pivot_gap_at(t_ms, isDemandLegOut, min(distVal, legOutLow), max(proxVal, legOutHigh))
                    if pg_tf:
                        pgap_tf = pg_tf
            isHQ_v4match = bool(mtf_tf or pgap_tf)
            isHQ = bool(isHQ_v4match) if self.mtf is not None else bool(isHQ_base)

            boxBorderColor, boxFillColor = ("green", ("green", 0.15)) if isDemandLegOut else ("red", ("red", 0.15))
            newZone = Zone(
                proxVal=proxVal, distVal=distVal, slVal=slVal, tpVal=tpVal, isDemand=isDemandLegOut, isHQ=isHQ,
                densityScore=densityScore, patternType="RBR" if isRBR else ("DBR" if isDBR else ("DBD" if isDBD else "RBD")),
                zoneCategory="Continuation" if (isRBR or isDBD) else "Reversal", state="Fresh", touchCount=0,
                startBarIndex=i - bCount, createdBarIndex=i, baseCount=bCount, legOutHigh=legOutHigh, legOutLow=legOutLow,
                legOutMidLevel=legOutMidLevel, isOvernight=isOvernight, legInTR=legInTR, legOutTR=legOutTR,
                zoneBox=Box(left=i - bCount - 1, top=proxVal, right=i + 15, bottom=distVal, border_color=boxBorderColor, bgcolor=boxFillColor),
                timestamp=self.df.index[i], riskPct=(riskPerShare / proxVal * 100.0) if proxVal else float("nan"),
                score10=densityScore / 10.0, baseColourOK=hasOppositeColorBase,
                legInVolX=(legInVol / self.vol_sma[pos_legIn] if self.vol_sma[pos_legIn] and not np.isnan(self.vol_sma[pos_legIn]) else float("nan")),
                legOutVolX=(legOutVol / self.vol_sma[pos_legOut] if self.vol_sma[pos_legOut] and not np.isnan(self.vol_sma[pos_legOut]) else float("nan")),
                gapToLegIn=gapSize,
                isHQ_base=isHQ_base, isHQ_v4match=isHQ_v4match,
                mtf_tf=mtf_tf, mtf_overlap=mtf_ov, pgap_tf=pgap_tf,
            )
            self.active_zones.append(newZone)

    def _update_zone_states(self, i):
        if not self.active_zones: return
        lo_t, hi_t = self.low[i], self.high[i]

        for z in reversed(self.active_zones):
            test_level = z.proxVal if self.testedOnProximal else z.legOutMidLevel
            if z.state == "Fresh":
                if z.isDemand:
                    if lo_t <= z.distVal: z.state = "Broken"
                    elif lo_t <= test_level: z.state, z.touchCount = "Tested", z.touchCount + 1
                else:
                    if hi_t >= z.distVal: z.state = "Broken"
                    elif hi_t >= test_level: z.state, z.touchCount = "Tested", z.touchCount + 1
            elif z.state == "Tested":
                if z.isDemand:
                    if lo_t <= z.distVal: z.state = "Broken"
                    elif lo_t <= test_level: z.touchCount += 1
                else:
                    if hi_t >= z.distVal: z.state = "Broken"
                    elif hi_t >= test_level: z.touchCount += 1

            if z.state == "Tested" and z.touchCount > self.maxTestedCount: z.state = "Broken"
            if z.state == "Broken": z.zoneBox.set_bgcolor(("gray", 0.05)); z.zoneBox.set_border_color(("gray", 0.20))
            else: z.zoneBox.set_right(i + 15)

    def run(self) -> List[Zone]:
        min_bar = max(self.atrPeriod, self.maxBaseCount + 3, 11)
        for i in range(min_bar, self.n):
            if not np.isnan(self.atr_val[i]): self._scan_bar(i)
            self._update_zone_states(i)
        return self.active_zones


# ============================== public API ==============================
def settings(**overrides) -> Dict[str, Any]:
    result = dict(PINE_DEFAULTS)
    result.update(overrides)
    return result


def scan_zones(df: pd.DataFrame, params: Optional[Dict[str, Any]] = None,
               half_df: Optional[pd.DataFrame] = None,
               higher_frames: Optional[Dict[str, pd.DataFrame]] = None,
               base_tf: Optional[str] = None) -> List[Zone]:
    config = settings(**(params or {}))
    engine_config = {key: value for key, value in config.items() if key in PINE_DEFAULTS}

    mtf = None
    if config.get("mtfEnabled"):
        work = _prep_frame(df)
        if work is None or len(work) == 0:
            raise ValueError("इनपुट DataFrame खाली है।")
        df = work
        if base_tf is None:
            base_tf = infer_tf(df)
        if higher_frames is None:
            higher_frames = _auto_higher_frames(df, base_tf)  # अब fingerprint-cached (BUG #2 fix)
        mtf = MtfContext(df, half_df, higher_frames, base_tf, engine_config)

    return ZoneEngine(df, mtf=mtf, **engine_config).run()


def recommended_trade_setup() -> Dict[str, Any]:
    return {"patterns": ["RBR", "DBR", "DBD", "RBD"], "targetRR": PINE_DEFAULTS["targetRR"], "risk_pct": PINE_DEFAULTS["riskPct"], "capital": PINE_DEFAULTS["accountCapital"], "slBufferAtr": PINE_DEFAULTS["slBufferAtr"], "entry_mode": "prox"}


def backtest_summary(zones: List[Zone], df: pd.DataFrame) -> Dict[str, Any]:
    active = [z for z in zones if z.state in ("Fresh", "Tested")]
    return {"n_zones": len(zones), "n_active": len(active), "n_broken": sum(z.state == "Broken" for z in zones), "avg_score": (sum(z.densityScore for z in zones) / len(zones) if zones else 0.0)}


def realistic_roi(zones: List[Zone], df: pd.DataFrame, rr: float = 5.0, risk_pct: float = 0.5, capital: float = 25000.0, patterns: Optional[List[str]] = None, buffer: float = 0.1, entry_mode: str = "prox", max_hold: int = 40) -> Dict[str, Any]:
    selected = [z for z in zones if not patterns or z.patternType in patterns]
    return {"n_trades": 0, "win_pct": 0.0, "net_roi_pct": 0.0, "sample_zones": len(selected), "risk_pct": risk_pct, "capital": capital, "targetRR": rr}


def latest_active_zones(zones: List[Zone]) -> List[Zone]:
    return [z for z in zones if z.state in ("Fresh", "Tested")]


def get_zone_alerts(zones: List[Zone], price: float) -> List[Zone]:
    return [z for z in latest_active_zones(zones) if min(z.proxVal, z.distVal) <= price <= max(z.proxVal, z.distVal)]
