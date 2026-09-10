"""
zdata.py — self-contained live data loader for the zone screener.

Fetches base bars from Yahoo Finance and resamples to the requested timeframe
exactly the way the backtest path did (prep_data.resample).  Being
self-contained, the app deploys standalone on Streamlit Cloud without the cached
CSV set.

Supported timeframes: 10m · 15m · 30m · 75m · 1h · 2h · 4h · 6h · 8h · 1D · 1W · 1M
Universe: NSE F&O stocks with market-cap >= ₹45,000 Cr (live NSE list + yfinance mcap, bundled fallback)
"""
from __future__ import annotations

import time
import threading
import pandas as pd
import yfinance as yf

# ─────────────────────────────────────────────────────────────────────────────
#  UNIVERSE = NSE F&O (Nifty-futures) stocks with market-cap >= MIN_MCAP_CR
#  1) live: NSE master-quote API (F&O symbol list) + yfinance fast_info marketCap
#  2) fallback: bundled snapshot below (NSE F&O list + market-cap in ₹ Cr, 06-Sep-2026)
#  Refreshed at most once a day (cached).  Nothing here touches zone rules.
# ─────────────────────────────────────────────────────────────────────────────
import json
import os

MIN_MCAP_CR = 45000            # ₹ 45,000 Cr

FO_MCAP_SNAPSHOT = {
    "360ONE": 46340,
    "ABB": 157024,
    "ABCAPITAL": 110843,
    "ADANIENSOL": 172388,
    "ADANIENT": 397724,
    "ADANIGREEN": 214347,
    "ADANIPORTS": 393355,
    "ADANIPOWER": 399579,
    "ALKEM": 62054,
    "AMBER": 26359,
    "AMBUJACEM": 100635,
    "ANGELONE": 27392,
    "APLAPOLLO": 62473,
    "APOLLOHOSP": 124374,
    "ASHOKLEY": 99268,
    "ASIANPAINT": 242278,
    "ASTRAL": 40107,
    "ATHERENERG": 62822,
    "AUBANK": 79769,
    "AUROPHARMA": 95116,
    "AXISBANK": 396295,
    "BAJAJ-AUTO": 327539,
    "BAJAJFINSV": 315248,
    "BAJAJHLDNG": 124226,
    "BAJFINANCE": 659728,
    "BANDHANBNK": 26575,
    "BANKBARODA": 123596,
    "BANKINDIA": 66014,
    "BDL": 46004,
    "BEL": 296302,
    "BHARATFORG": 93514,
    "BHARTIARTL": 1147913,
    "BHEL": 150112,
    "BIOCON": 64708,
    "BLUESTARCO": 30510,
    "BOSCHLTD": 138101,
    "BPCL": 134886,
    "BRITANNIA": 122879,
    "BSE": 138482,
    "CAMS": 18593,
    "CANBK": 113837,
    "CDSL": 29147,
    "CGPOWER": 140373,
    "CHOLAFIN": 157053,
    "CIPLA": 111888,
    "COALINDIA": 255969,
    "COCHINSHIP": 39438,
    "COFORGE": 87391,
    "COLPAL": 49752,
    "CONCOR": 38690,
    "CROMPTON": 14965,
    "CUMMINSIND": 139570,
    "DABUR": 67570,
    "DELHIVERY": 34299,
    "DIVISLAB": 241576,
    "DIXON": 86582,
    "DLF": 168792,
    "DMART": 245897,
    "DRREDDY": 95877,
    "EICHERMOT": 209474,
    "ETERNAL": 297104,
    "FEDERALBNK": 84707,
    "FORCEMOT": 23058,
    "FORTIS": 68324,
    "GAIL": 114012,
    "GLENMARK": 68784,
    "GMRAIRPORT": 102897,
    "GODFRYPHLP": 31992,
    "GODREJCP": 89846,
    "GODREJPROP": 59703,
    "GRASIM": 225316,
    "GVT&D": 110261,
    "HAL": 324757,
    "HAVELLS": 72421,
    "HCLTECH": 349964,
    "HDFCAMC": 105414,
    "HDFCBANK": 1097417,
    "HDFCLIFE": 118681,
    "HEROMOTOCO": 106075,
    "HINDALCO": 224426,
    "HINDPETRO": 75857,
    "HINDUNILVR": 463668,
    "HINDZINC": 253942,
    "HYUNDAI": 179165,
    "ICICIBANK": 1021468,
    "ICICIGI": 75440,
    "ICICIPRULI": 71698,
    "IDEA": 162731,
    "IDFCFIRSTB": 74759,
    "IEX": 10580,
    "INDHOTEL": 104156,
    "INDIANB": 118492,
    "INDIGO": 192444,
    "INDUSINDBK": 78576,
    "INDUSTOWER": 99370,
    "INFY": 457664,
    "INOXWIND": 12858,
    "IOC": 194308,
    "IREDA": 31924,
    "IRFC": 108991,
    "ITC": 330912,
    "JINDALSTEL": 118537,
    "JIOFIN": 158145,
    "JSWENERGY": 98921,
    "JSWSTEEL": 323410,
    "JUBLFOOD": 31746,
    "KALYANKJIL": 61841,
    "KAYNES": 24187,
    "KEI": 46366,
    "KFINTECH": 16058,
    "KOTAKBANK": 422278,
    "KPITTECH": 15665,
    "LAURUSLABS": 99417,
    "LICHSGFIN": 30916,
    "LICI": 262709,
    "LODHA": 122069,
    "LT": 545407,
    "LTF": 78690,
    "LTM": 135008,
    "LUPIN": 96483,
    "M&M": 380642,
    "MAHABANK": 66109,
    "MANAPPURAM": 31909,
    "MANKIND": 96153,
    "MARICO": 105658,
    "MARUTI": 399103,
    "MAXHEALTH": 95852,
    "MAZDOCK": 99837,
    "MCX": 83364,
    "MFSL": 53156,
    "MOTHERSON": 169237,
    "MOTILALOFS": 62461,
    "MPHASIS": 46216,
    "MUTHOOTFIN": 116980,
    "NAM-INDIA": 74208,
    "NATIONALUM": 68708,
    "NAUKRI": 85488,
    "NBCC": 23382,
    "NESTLEIND": 271989,
    "NHPC": 76593,
    "NMDC": 74467,
    "NTPC": 322414,
    "NYKAA": 95264,
    "OBEROIRLTY": 68197,
    "OFSS": 105005,
    "OIL": 79427,
    "ONGC": 295196,
    "PAGEIND": 40489,
    "PATANJALI": 37260,
    "PAYTM": 106396,
    "PERSISTENT": 88161,
    "PETRONET": 43215,
    "PFC": 117352,
    "PGEL": 16110,
    "PHOENIXLTD": 69461,
    "PIDILITIND": 165863,
    "PIIND": 37396,
    "PNB": 134467,
    "PNBHOUSING": 30410,
    "POLICYBZR": 84831,
    "POLYCAB": 125027,
    "POWERGRID": 247396,
    "POWERINDIA": 141072,
    "PREMIERENE": 45235,
    "PRESTIGE": 68357,
    "RADICO": 60212,
    "RBLBANK": 64229,
    "RECLTD": 83921,
    "RELIANCE": 1788993,
    "RVNL": 44305,
    "SAGILITY": 21918,
    "SAIL": 81289,
    "SBICARD": 62642,
    "SBILIFE": 178095,
    "SBIN": 937923,
    "SHREECEM": 86071,
    "SHRIRAMFIN": 244946,
    "SIEMENS": 141629,
    "SOLARINDS": 194056,
    "SONACOMS": 49244,
    "SRF": 75495,
    "SUNPHARMA": 455634,
    "SUPREMEIND": 44161,
    "SUZLON": 62337,
    "SWIGGY": 72338,
    "TATACONSUM": 99959,
    "TATAELXSI": 22166,
    "TATAPOWER": 117588,
    "TATASTEEL": 235503,
    "TCS": 833607,
    "TECHM": 141469,
    "TIINDIA": 52226,
    "TITAN": 445431,
    "TMPV": 114722,
    "TORNTPHARM": 184745,
    "TRENT": 152131,
    "TVSMOTOR": 196416,
    "ULTRACEMCO": 335589,
    "UNIONBANK": 142916,
    "UNITDSPR": 104499,
    "UNOMINDA": 72166,
    "UPL": 49208,
    "VBL": 137869,
    "VEDL": 106250,
    "VMM": 49725,
    "VOLTAS": 38714,
    "WAAREEENER": 75796,
    "WIPRO": 174508,
    "YESBANK": 70623,
    "ZYDUSLIFE": 111720,
}


def _to_sym(n):
    return n.strip().replace("_", "-") + ".NS"


def _nse_fo_list(timeout=12):
    """Live NSE F&O stock symbols (master-quote). Returns [] on failure."""
    try:
        import requests
        H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
             "Accept": "*/*", "Referer": "https://www.nseindia.com/"}
        s = requests.Session()
        s.get("https://www.nseindia.com", headers=H, timeout=timeout)
        r = s.get("https://www.nseindia.com/api/master-quote", headers=H, timeout=timeout)
        lst = r.json()
        if isinstance(lst, list) and len(lst) > 100:
            return [str(x).strip() for x in lst if str(x).strip()]
    except Exception:
        pass
    return []


def _mcap_cr(sym_ns):
    try:
        v = yf.Ticker(sym_ns).fast_info.get("marketCap")
        return float(v) / 1e7 if v else None
    except Exception:
        return None


_UNIV_CACHE = {"day": None, "syms": None, "mcap": None, "source": None}
_UNIV_LOCK = threading.Lock()
_UNIV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".universe_cache.json")


def build_universe(min_mcap_cr=MIN_MCAP_CR, live=True, force=False):
    """Return (symbols_ns_sorted_by_mcap_desc, mcap_dict_cr, source_str).
    F&O list from NSE (live) ∪ bundled snapshot; market-cap from yfinance (live) else snapshot.
    Cached for the calendar day (memory + small json file)."""
    day = time.strftime("%Y-%m-%d")
    with _UNIV_LOCK:
        if not force and _UNIV_CACHE["day"] == day and _UNIV_CACHE["syms"]:
            return _UNIV_CACHE["syms"], _UNIV_CACHE["mcap"], _UNIV_CACHE["source"]
        if not force:
            try:
                d = json.load(open(_UNIV_FILE))
                if d.get("day") == day and d.get("min_mcap_cr") == min_mcap_cr and d.get("syms"):
                    _UNIV_CACHE.update(day=day, syms=d["syms"], mcap=d["mcap"], source=d["source"] + " (file cache)")
                    return _UNIV_CACHE["syms"], _UNIV_CACHE["mcap"], _UNIV_CACHE["source"]
            except Exception:
                pass
    names = _nse_fo_list() if live else []
    source = "NSE F&O live" if names else "bundled F&O snapshot"
    if not names:
        names = list(FO_MCAP_SNAPSHOT.keys())
    mcap = {}
    n_live = 0
    live_vals = {}
    if live:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=16) as ex:          # 176 tickers in ~2 s (was ~20 s sequential)
            live_vals = dict(zip(names, ex.map(lambda n: _mcap_cr(_to_sym(n)), names)))
    for n in names:
        s = _to_sym(n)
        v = live_vals.get(n)
        if v is not None:
            n_live += 1
        else:
            v = float(FO_MCAP_SNAPSHOT.get(n, 0) or 0)
        mcap[s] = v
    source += f" · mcap yfinance {n_live}/{len(names)}" if live else " · mcap snapshot"
    syms = sorted([s for s, v in mcap.items() if v and v >= min_mcap_cr], key=lambda s: -mcap[s])
    with _UNIV_LOCK:
        _UNIV_CACHE.update(day=day, syms=syms, mcap=mcap, source=source)
        try:
            json.dump({"day": day, "min_mcap_cr": min_mcap_cr, "syms": syms, "mcap": mcap, "source": source},
                      open(_UNIV_FILE, "w"))
        except Exception:
            pass
    return syms, mcap, source


def universe_snapshot(min_mcap_cr=MIN_MCAP_CR):
    """Offline universe from the bundled snapshot (no network) — used at import time."""
    mc = {_to_sym(n): float(v) for n, v in FO_MCAP_SNAPSHOT.items()}
    return sorted([s for s, v in mc.items() if v >= min_mcap_cr], key=lambda s: -mc[s]), mc


# import-time defaults (offline); aap.py calls build_universe() for the live list
FUT_STOCKS, MCAP_CR = universe_snapshot()
ALL_FO_STOCKS = [_to_sym(n) for n in FO_MCAP_SNAPSHOT]
INDEX_INSTR = ["^NSEI"]
NIFTY_FUT_STOCKS = FUT_STOCKS  # alias
STOCK_CHOICES = FUT_STOCKS + ["^NSEI"]
DEFAULT_UNIVERSE = list(FUT_STOCKS)   # ALL mcap>=45k stocks by default (user rule)

# --------------------------------------------------------------------------- #
TIMEFRAMES = ["10m", "15m", "30m", "75m", "1h", "2h", "4h", "6h", "8h", "1D", "1W", "1M"]

TF_CONFIG = {
    "10m": dict(interval="5m",  period="60d", rule="10min"),
    "15m": dict(interval="15m", period="60d", rule="15min"),
    "30m": dict(interval="30m", period="60d", rule="30min"),
    "75m": dict(interval="15m", period="60d", rule="75min"),
    "1h":  dict(interval="60m", period="2y",  rule="60min"),
    "2h":  dict(interval="60m", period="2y",  rule="2h"),
    "4h":  dict(interval="60m", period="2y",  rule="4h"),
    "6h":  dict(interval="60m", period="2y",  rule="6h"),
    "8h":  dict(interval="60m", period="2y",  rule="8h"),
    "1D":  dict(interval="1d",  period="2y",  rule="1D"),
    "1W":  dict(interval="1wk", period="10y", rule="1W"),
    "1M":  dict(interval="1mo", period="max", rule="1ME"),
}

# small process-level so a universe scan reuses base bars across TFs.
# Value: (fetched_at_epoch, df).  TTL per interval keeps intraday bars LIVE
# while letting slow timeframes (daily/weekly/monthly) stay cached longer.
_BASE_CACHE = {}
_BASE_LOCK = threading.Lock()
_ZF_CACHE = {}          # (symbol, tf) -> (base_stamp, resampled frame)
_ZF_LOCK = threading.Lock()
_BASE_TTL = {"5m": 120, "15m": 120, "30m": 120, "60m": 300, "1d": 900, "1wk": 3600, "1mo": 3600}  # seconds


def _fetch_base(sym, interval, period):
    """Fetch + normalise base OHLCV bars, cached per (sym, interval, period)
    with an interval-aware freshness TTL (so intraday bars refresh live)."""
    key = (sym, interval, period)
    ttl = _BASE_TTL.get(interval, 300)
    with _BASE_LOCK:
        cached = _BASE_CACHE.get(key)
        if cached and (time.time() - cached[0]) < ttl:
            return cached[1].copy()
    try:                                   # fast direct Yahoo chart call (~0.1 s)
        df = _yahoo_chart(sym, interval, period)
        with _BASE_LOCK:
            _BASE_CACHE[key] = (time.time(), df.copy())
        return df
    except Exception:
        pass
    df = yf.download(sym, interval=interval, progress=False, auto_adjust=False,
                     period=period)
    if df is None or len(df) == 0:
        raise RuntimeError(f"no data for {sym} @ {interval}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.reset_index()
    ts_col = "Datetime" if "Datetime" in df.columns else "Date"
    df["timestamp"] = pd.to_datetime(df[ts_col])
    df = df[["timestamp", "Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).sort_values("timestamp")
    with _BASE_LOCK:
        _BASE_CACHE[key] = (time.time(), df.copy())
    return df


def _normalise_one(df):
    df = df.reset_index()
    ts_col = "Datetime" if "Datetime" in df.columns else ("Date" if "Date" in df.columns else df.columns[0])
    df["timestamp"] = pd.to_datetime(df[ts_col])
    df = df[["timestamp", "Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).sort_values("timestamp")


# ── FAST PATH: direct Yahoo chart API (same data yfinance uses, verified identical) ─────────
# One tiny JSON request per symbol/interval (~0.1 s) run on a thread-pool → the whole
# 176-stock universe for one interval downloads in ~1-2 s instead of 10-15 s.
_YH_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_YH_LOCAL = threading.local()


def _yh_session():
    import requests
    s = getattr(_YH_LOCAL, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": _YH_UA, "Accept": "application/json"})
        _YH_LOCAL.s = s
    return s


def _yahoo_chart(sym, interval, period, timeout=15):
    """Direct Yahoo v8 chart → normalised lowercase OHLCV frame (raises on failure)."""
    r = _yh_session().get(
        f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}",
        params={"interval": interval, "range": period, "includePrePost": "false"},
        timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    res = r.json()["chart"]["result"][0]
    ts = res.get("timestamp") or []
    if not ts:
        raise RuntimeError("empty")
    q = res["indicators"]["quote"][0]
    tz = res.get("meta", {}).get("exchangeTimezoneName", "Asia/Kolkata")
    idx = pd.to_datetime(ts, unit="s", utc=True).tz_convert(tz)
    if interval in ("1d", "1wk", "1mo"):
        idx = idx.tz_localize(None).normalize()           # same shape as yfinance daily (tz-naive dates)
    df = pd.DataFrame({"timestamp": idx, "open": q.get("open"), "high": q.get("high"),
                       "low": q.get("low"), "close": q.get("close"), "volume": q.get("volume")})
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.drop_duplicates("timestamp", keep="last").sort_values("timestamp").reset_index(drop=True)
    if len(df) == 0:
        raise RuntimeError("no rows")
    return df


def _fetch_many(pairs, workers=32):
    """pairs = [(sym, interval, period), ...] → fills _BASE_CACHE in parallel.
    Direct Yahoo first; anything that fails falls back to a yfinance batch download."""
    from concurrent.futures import ThreadPoolExecutor
    failed = []

    def one(p):
        sym, interval, period = p
        try:
            df = _yahoo_chart(sym, interval, period)
            with _BASE_LOCK:
                _BASE_CACHE[(sym, interval, period)] = (time.time(), df)
        except Exception:
            failed.append(p)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, pairs))
    # fallback (rare: 429 / transient) → yfinance batch per (interval, period)
    groups = {}
    for sym, interval, period in failed:
        groups.setdefault((interval, period), []).append(sym)
    for (interval, period), syms in groups.items():
        _yf_batch(syms, interval, period)


def _yf_batch(symbols, interval, period, chunk=40):
    for i in range(0, len(symbols), chunk):
        batch = symbols[i:i + chunk]
        try:
            raw = yf.download(batch, interval=interval, period=period, progress=False,
                              auto_adjust=False, group_by="ticker", threads=True)
        except Exception:
            continue
        if raw is None or len(raw) == 0:
            continue
        for s in batch:
            try:
                d = raw[s] if isinstance(raw.columns, pd.MultiIndex) else raw
                d = d.dropna(how="all")
                if len(d) == 0:
                    continue
                df = _normalise_one(d)
                with _BASE_LOCK:
                    _BASE_CACHE[(s, interval, period)] = (time.time(), df)
            except Exception:
                continue


def prefetch_base(symbols, interval, period, chunk=40):
    """Fill the per-symbol cache for one base interval (only symbols whose cache is stale)."""
    need = []
    now = time.time()
    ttl = _BASE_TTL.get(interval, 300)
    with _BASE_LOCK:
        for s in symbols:
            c = _BASE_CACHE.get((s, interval, period))
            if not (c and (now - c[0]) < ttl):
                need.append(s)
    if need:
        _fetch_many([(s, interval, period) for s in need])


def prefetch_for_timeframes(symbols, timeframes):
    """Prefetch every base interval needed by the given timeframes — ALL symbols × ALL intervals
    in ONE thread-pool (176 stocks × 6 intervals ≈ 5-8 s cold, ~2-3 s on refresh)."""
    keys = []
    seen = set()
    for tf in list(timeframes):
        cfg = TF_CONFIG.get(tf) or TF_CONFIG.get(normalize_tf(tf))
        if not cfg:
            continue
        key = (cfg["interval"], cfg["period"])
        if key not in seen:
            seen.add(key)
            keys.append(key)
    if ("1d", "1y") not in seen:
        keys.append(("1d", "1y"))            # EOD band (daily_hl)
    now = time.time()
    pairs = []
    with _BASE_LOCK:
        for interval, period in keys:
            ttl = _BASE_TTL.get(interval, 300)
            for s in symbols:
                c = _BASE_CACHE.get((s, interval, period))
                if not (c and (now - c[0]) < ttl):
                    pairs.append((s, interval, period))
    if pairs:
        _fetch_many(pairs)


def fetch_1h(sym, start=None, end=None, period="2y"):
    """Back-compat alias: 1h bars (lowercase ohlcv)."""
    df = _fetch_base(sym, "60m", period)
    if start is not None:
        df = _trim(df, start)
    return df


def _trim(df, start):
    try:
        st = pd.Timestamp(start)
        if df["timestamp"].dt.tz is not None and st.tz is None:
            st = st.tz_localize(df["timestamp"].dt.tz)
        df = df[df["timestamp"] >= st]
    except Exception:
        pass
    return df


def _session_resample(df, hours):
    """NSE-session aligned N-hour bars (same as the backtest): buckets start 09:15 and the LAST
    bucket absorbs the session remainder (e.g. 2h → 09:15, 11:15, 13:15–15:30; 6h/8h → one bar per session)."""
    import numpy as _np
    d = df.sort_values("timestamp")
    ts = d["timestamp"]
    day = ts.dt.normalize()
    mins = _np.asarray(((ts - day).dt.total_seconds() / 60 - 555), dtype=int)   # minutes since 09:15
    bucket = _np.clip(mins // (hours * 60), 0, max(0, (360 - 1) // (hours * 60)))
    g = d.groupby([day.values, bucket], sort=True)
    out = g.agg(timestamp=("timestamp", "first"), open=("open", "first"), high=("high", "max"),
                low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
    out = out.set_index("timestamp")
    out.index = pd.DatetimeIndex(out.index)
    out.index.name = "timestamp"
    return out[["open", "high", "low", "close", "volume"]].dropna(subset=["open", "high", "low", "close"]).sort_index()


def resample(df, rule):
    if rule in ("2h", "4h", "6h", "8h"):
        return _session_resample(df, int(rule[:-1]))
    s = df.set_index("timestamp")
    kw = {}
    if rule.endswith("min"):
        kw = dict(origin="start_day", offset="9h15min")   # NSE session starts 09:15 → bars align to 09:15
    agg = s.resample(rule, **kw).agg({"open": "first", "high": "max", "low": "min",
                                      "close": "last", "volume": "sum"})
    agg = agg.dropna(subset=["open", "high", "low", "close"])
    agg.index = pd.to_datetime(agg.index)
    agg.index.name = "timestamp"
    return agg.sort_index()


def load_zone_frame(symbol, timeframe, **kw):
    """Return a DatetimeIndex + lowercase-ohlcv DataFrame ready for zone_core.scan_zones.

    Supports all TIMEFRAMES.  ``kw`` may carry ``start`` / ``lookback_months``.
    """
    if timeframe not in TF_CONFIG:
        timeframe = normalize_tf(timeframe)
    cfg = TF_CONFIG[timeframe]
    key = (symbol, cfg["interval"], cfg["period"])
    df = _fetch_base(symbol, cfg["interval"], cfg["period"])
    with _BASE_LOCK:
        stamp = _BASE_CACHE.get(key, (None,))[0]
    start = kw.get("start")
    if start is None:                           # resample cache: reuse until the base bars refresh
        with _ZF_LOCK:
            c = _ZF_CACHE.get((symbol, timeframe))
        if c and c[0] == stamp:
            return c[1].copy()
    else:
        df = _trim(df, start)
    rule = cfg["rule"]
    # if the base is already the requested granularity, avoid a redundant resample
    if cfg["interval"] in ("1wk", "1mo") or (rule == "1D" and cfg["interval"] == "1d"):
        out = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]].sort_index()
        out.index = pd.to_datetime(out.index); out.index.name = "timestamp"
    else:
        out = resample(df, rule)
    if start is None:
        with _ZF_LOCK:
            _ZF_CACHE[(symbol, timeframe)] = (stamp, out.copy())
    return out


def normalize_tf(tf):
    m = {"daily": "1D", "day": "1D", "d": "1D", "weekly": "1W", "week": "1W",
         "w": "1W", "monthly": "1M", "month": "1M", "m": "1M",
         "1h": "1h", "60m": "1h", "60min": "1h",
         "75m": "75m", "75min": "75m", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h"}
    tf = str(tf).lower().replace(" ", "")
    return m.get(tf, tf)


def daily_hl(symbol, period="1y"):
    """Return (high, low) of the most recent COMPLETED daily (EOD close) candle for the band filter.
    During market hours yfinance's last daily row is today's live (incomplete) bar → use the previous row."""
    try:
        df = _fetch_base(symbol, "1d", period)
        last = df.iloc[-1]
        ts = pd.Timestamp(last["timestamp"])
        now = pd.Timestamp.now(tz="Asia/Kolkata")
        if ts.tzinfo is None:
            ts = ts.tz_localize("Asia/Kolkata")
        if ts.normalize() == now.normalize() and now.time() < pd.Timestamp("15:30").time() and len(df) > 1:
            last = df.iloc[-2]
        return float(last["high"]), float(last["low"])
    except Exception:
        return None, None


if __name__ == "__main__":
    for tf in TIMEFRAMES:
        try:
            d = load_zone_frame("RELIANCE.NS", tf)
            print(f"{tf:5s} bars={len(d)}")
        except Exception as e:
            print(f"{tf:5s} ERR {str(e)[:70]}")
    print("daily_hl:", daily_hl("RELIANCE.NS"))
