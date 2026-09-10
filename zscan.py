"""
zscan.py — thin wrapper around zone_core (v11.1 FINAL) for the Streamlit app.
(v11: recommended patterns = all four; defaults min_score 60, TFs 1h+4h; rows carry distal/risk_pct/score10/colour)
"""
from __future__ import annotations

import threading
import time

import pandas as pd
import zone_core
import zdata

# --------------------------------------------------------------------------- #
#  small process-level caches so a universe scan reuses base bars / OI / quotes #
# --------------------------------------------------------------------------- #
_oi_cache = {}
_oi_lock = threading.Lock()
_daily_hl_cache = {}
_dhl_lock = threading.Lock()
_scan_cache = {}          # (symbol, tf, min_score, recommended, strict, base_stamp) -> (zones, df, extra)
_ctx_cache = {}           # v13.3 market context (Nifty daily / VIX / S&P) with TTL
_ctx_lock = threading.Lock()
HTF_OF = {"10m": "1h", "15m": "1h", "30m": "2h", "1h": "4h", "2h": "1D", "4h": "1D", "6h": "1D", "1D": "1W", "1W": "1M", "1M": None}


def market_context(ttl=900):
    """v13.3 TP-SCORE inputs shared by every zone: Nifty daily frame (sign A), India VIX level and
    S&P-500 20-day % return (sign F).  Any piece may be None (then that sign is skipped, never guessed)."""
    with _ctx_lock:
        c = _ctx_cache.get("ctx")
        if c and (time.time() - c[0]) < ttl:
            return c[1]
    out = {"nifty": None, "vix": None, "spx_ret20": None}
    try:
        out["nifty"] = zdata.load_zone_frame("^NSEI", "1D")
    except Exception:
        pass
    try:
        v = zdata.load_zone_frame("^INDIAVIX", "1D")
        out["vix"] = float(v["close"].dropna().iloc[-1]) if v is not None and len(v) else None
    except Exception:
        pass
    try:
        sp = zdata.load_zone_frame("^GSPC", "1D")["close"].dropna()
        out["spx_ret20"] = float(sp.iloc[-1] / sp.iloc[-21] - 1) * 100 if len(sp) > 21 else None
    except Exception:
        pass
    with _ctx_lock:
        _ctx_cache["ctx"] = (time.time(), out)
    return out


def tp_context(z, sym, tf, df=None, ctx=None):
    """v13.3: target_context() for one zone using the symbol's higher-TF frame + shared market context."""
    ctx = ctx or market_context()
    htf = HTF_OF.get(tf)
    hdf = None
    if htf:
        try:
            hdf = zdata.load_zone_frame(sym, htf)
        except Exception:
            hdf = None
    return zone_core.target_context(z, df, htf_df=hdf, market_df=ctx.get("nifty"), vix=ctx.get("vix"), spx_ret20=ctx.get("spx_ret20"))
_scan_lock = threading.Lock()


def _daily_hl(symbol):
    with zdata._BASE_LOCK:
        stamp = zdata._BASE_CACHE.get((symbol, "1d", "1y"), (None,))[0]
    with _dhl_lock:
        c = _daily_hl_cache.get(symbol)
        if c is not None and c[0] == stamp and stamp is not None:
            return c[1]
    v = zdata.daily_hl(symbol, period="1y")
    with zdata._BASE_LOCK:
        stamp = zdata._BASE_CACHE.get((symbol, "1d", "1y"), (None,))[0]
    with _dhl_lock:
        _daily_hl_cache[symbol] = (stamp, v)
    return v


_oi_blocked_until = [0.0]      # NSE option-chain blocked (cloud IP) → skip quickly for 10 min


def _oi_snapshot(symbol):
    """Return (call_oi, put_oi) or (None, None).  Cached per symbol; auto-skips when NSE blocks."""
    import time as _t
    with _oi_lock:
        if symbol in _oi_cache:
            return _oi_cache[symbol]
        if _t.time() < _oi_blocked_until[0]:
            return None, None
    try:
        import options as _opt
        live = _opt.live_oi(symbol)
        call_oi = live.get("call_oi")
        put_oi = live.get("put_oi")
    except Exception:
        call_oi, put_oi = None, None
    with _oi_lock:
        _oi_cache[symbol] = (call_oi, put_oi)
    return call_oi, put_oi


def prefetch_oi(symbols, workers=12, ttl=300):
    """Fetch option-chain OI for many symbols in parallel (once per `ttl`).  Probes one symbol
    first: if NSE is blocked (typical on Streamlit Cloud) the whole step is skipped in <1 s."""
    import time as _t
    from concurrent.futures import ThreadPoolExecutor
    now = _t.time()
    with _oi_lock:
        if now < _oi_blocked_until[0]:
            return
        stale = [s for s in symbols if s not in _oi_cache or _oi_cache[s][0] is None and _oi_cache.get(s, (0,))[0] is None]
        if not stale:
            return
    probe = _oi_snapshot(stale[0])
    if probe[0] is None:
        with _oi_lock:
            _oi_blocked_until[0] = now + 600          # blocked → don't try again for 10 min
            for s in stale:
                _oi_cache.setdefault(s, (None, None))
        return
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(_oi_snapshot, stale[1:]))


def _fmt_oi(v):
    """Format an OI count the Indian way (Cr / L / raw)."""
    if v is None:
        return "—"
    v = float(v)
    if v >= 1e7:
        return f"{v/1e7:.2f}Cr"
    if v >= 1e5:
        return f"{v/1e5:.2f}L"
    return f"{v:,.0f}"


def oi_bias(symbol, is_demand):
    """Return a rich dict for the Put/Call OI bias of a zone direction.

    Demand (support) is bullish-leaning when Put OI > Call OI.
    Supply (resistance) is bearish-leaning when Call OI > Put OI.

    Returns {label, aligned, put, call} where `label` shows the actual numbers
    (e.g. 'P 4.5L > C 3.1L'), `aligned` is True when OI agrees with the zone
    direction.  Returns {} when the live OI is unavailable (blocked on cloud).
    """
    call_oi, put_oi = _oi_snapshot(symbol)
    if call_oi is None or put_oi is None or call_oi == 0:
        return {}
    p, c = _fmt_oi(put_oi), _fmt_oi(call_oi)
    if is_demand:
        aligned = put_oi > call_oi
        return {"label": f"P {p} {'>' if aligned else '<'} C {c}",
                "aligned": aligned, "put": put_oi, "call": call_oi}
    aligned = call_oi > put_oi
    return {"label": f"C {c} {'>' if aligned else '<'} P {p}",
            "aligned": aligned, "put": put_oi, "call": call_oi}


def eod_band(symbol):
    """Return the EOD (daily close candle) band dict:
       {hi, lo, eod_hi=hi*1.10, eod_lo=lo*0.90} or None if daily data unavailable.
    The zone scan is restricted to this band (last COMPLETED daily candle: high+10% .. low-10%).
    No date-range is used anywhere: every TF is scanned over its full available history and
    only zones whose [proximal, distal] overlaps the band are returned."""
    hi, lo = _daily_hl(symbol)
    if hi is None or lo is None:
        return None
    return {"hi": hi, "lo": lo, "eod_hi": hi * 1.10, "eod_lo": lo * 0.90}


def eod_zone_filter(zones, symbol):
    """Keep only zones that fall inside the EOD band (daily high+10% .. low-10%).

    Returns (kept_zones, band).  If band is None, returns zones unchanged.
    """
    band = eod_band(symbol)
    if band is None:
        return zones, None
    kept = []
    for z in zones:
        z_lo, z_hi = min(z.proxVal, z.distVal), max(z.proxVal, z.distVal)
        if z_hi >= band["eod_lo"] and z_lo <= band["eod_hi"]:
            kept.append(z)
    return kept, band


def scan(symbol, timeframe="2h", min_score=45, recommended=False,
         strict=False, lookback_months=None, start=None):
    """Return (zones, df, summary_dict) for a symbol / timeframe.
    Result is memoised per (symbol, tf, min_score, strict) until the underlying base bars
    refresh (interval TTL) — so re-runs / filter changes don't recompute unchanged zones."""
    df = zdata.load_zone_frame(symbol, timeframe, start=start)
    ck = None
    if start is None and lookback_months is None:
        cfg = zdata.TF_CONFIG.get(timeframe) or zdata.TF_CONFIG.get(zdata.normalize_tf(timeframe))
        with zdata._BASE_LOCK:
            stamp = zdata._BASE_CACHE.get((symbol, cfg["interval"], cfg["period"]), (None,))[0]
        ck = (symbol, timeframe, min_score, bool(recommended), bool(strict), stamp)
        with _scan_lock:
            hit = _scan_cache.get(ck)
        if hit is not None:
            return hit
    params = zone_core.settings()
    if strict:
        params.update({"volume_gate": True, "legInMinAtrMult": 1.0,
                       "maxWickPct": 0.30, "legInToBaseSizeMult": 2.0,
                       "legInToBaseSizeMultSingleBase": 1.5,
                       "legOutMinTrRatio": 1.0})
    params["minValidScore"] = min_score
    zones = zone_core.scan_zones(df, params=params)
    if recommended:
        rec = zone_core.recommended_trade_setup()
        zones_all = zones
        zones = [z for z in zones_all if z.patternType in rec["patterns"]]
        for z in zones:
            pass
        roi = zone_core.realistic_roi(
            zones_all, df, rr=rec["targetRR"], risk_pct=rec["risk_pct"],
            capital=rec["capital"], patterns=rec["patterns"],
            buffer=rec["slBufferAtr"], entry_mode=rec.get("entry_mode", "prox"),
            max_hold=40)
        res = (zones, df, {"recommended": rec, "roi": roi})
    else:
        res = (zones, df, zone_core.backtest_summary(zones, df))
    if ck is not None:
        with _scan_lock:
            if len(_scan_cache) > 6000:
                _scan_cache.clear()
            _scan_cache[ck] = res
    return res


def scan_universe_zones(timeframes=("10m", "15m", "1h", "2h", "4h", "6h", "1D", "1W", "1M"), min_score=45, recommended=True,
                        strict=False, active_only=False, eod_filter=False,
                        symbols=None):
    """Scan the full NSE futures universe across EVERY given timeframe and return
    one flat list of every VALID zone with its details.

    Each row: {symbol, tf, pattern, dir, entry, sl, tp, score, hq, state,
               touches, ts, last, chain, tv, oi, eod_lo, eod_hi, in_band,
               eod_band}

    ``eod_filter``  : keep only zones that fall inside the EOD candle band
                      (daily low -10% .. daily high +10%).  This is the
                      "scan only in the area around today's daily candle" rule.
    ``symbols``     : optional list of Yahoo symbols to scan (default = all F&O).
    """
    import options as _opt
    import tv as _tv
    rec_patterns = zone_core.recommended_trade_setup()["patterns"]
    all_zones = []
    if symbols:
        universe = list(symbols)
    else:
        try:
            universe, _, _ = zdata.build_universe()      # NSE F&O ∩ mcap >= ₹45,000 Cr (daily cached)
        except Exception:
            universe = list(zdata.FUT_STOCKS)
    try:
        zdata.prefetch_for_timeframes(universe, timeframes)     # ONE parallel download for all stocks × intervals
    except Exception:
        pass
    try:
        prefetch_oi(universe)                                   # parallel OI (auto-skip when NSE blocked)
    except Exception:
        pass

    def _scan_symbol(sym):
        out = []
        eod_lo = eod_hi = None
        if eod_filter:
            hi, lo = _daily_hl(sym)
            if hi is not None and lo is not None:
                eod_hi = hi * 1.10
                eod_lo = lo * 0.90
        links = _opt.deep_links(sym)
        chain = links[0]["url"] if links else ""
        mctx = market_context()
        for tf in timeframes:
            try:
                zones, df, extra = scan(sym, tf, min_score=min_score,
                                        recommended=recommended, strict=strict)
                last = float(df["close"].iloc[-1]) if df is not None and len(df) else None
                tv_url = _tv.chart_url(sym, tf)
                for z in zones:
                    if active_only and z.state not in ("Fresh", "Tested"):
                        continue
                    if recommended and z.patternType not in rec_patterns:
                        continue
                    z_lo, z_hi = min(z.proxVal, z.distVal), max(z.proxVal, z.distVal)
                    in_band = True
                    if eod_filter and eod_lo is not None:
                        in_band = (z_hi >= eod_lo) and (z_lo <= eod_hi)
                    if eod_filter and not in_band:
                        continue
                    try:
                        tpc = tp_context(z, sym, tf, df, mctx)                       # v13.3 TP-SCORE (highlight only)
                    except Exception:
                        tpc = {}
                    out.append({
                        "tp_score": tpc.get("score"), "tp_max": tpc.get("max"), "tp_label": tpc.get("label", ""),
                        "tp_signs": "".join(k + ("✓" if tpc.get(k) else "✗") for k in "ABCDEF" if tpc.get(k) is not None),
                        "tp_why": " | ".join(tpc.get("why", [])),
                        "legin_vol_x": None if (z.legInVolX != z.legInVolX) else round(z.legInVolX, 2),
                        "legout_vol_x": None if (z.legOutVolX != z.legOutVolX) else round(z.legOutVolX, 2),
                        "retest_vol_x": None if (z.retestVolX != z.retestVolX) else round(z.retestVolX, 2),
                        "symbol": sym, "tf": tf,
                        "pattern": z.patternType,
                        "dir": "Demand" if z.isDemand else "Supply",
                        "entry": round(z.proxVal, 2),      # proximal = boring BODY edge (v11); enter on confirm-close
                        "distal": round(z.distVal, 2),
                        "sl": round(z.slVal, 2),           # = distal, no buffer
                        "tp": round(z.tpVal, 2),
                        "risk_pct": round(z.riskPct, 2),
                        "score10": z.score10,
                        "colour": bool(z.baseColourOK),
                        "score": z.densityScore,
                        "hq": bool(z.isHQ),
                        "state": z.state,
                        "touches": z.touchCount,
                        "last": last,
                        "ts": str(z.timestamp)[:16],
                        "chain": chain,
                        "tv": tv_url,
                        "oi": oi_bias(sym, z.isDemand),
                        "eod_lo": eod_lo,
                        "eod_hi": eod_hi,
                        "in_band": in_band,
                        "entry_status": getattr(z, "entryStatus", ""),
                        "entry_price": round(getattr(z, "entryPrice", 0.0) or 0.0, 2) or None,
                        "boring": getattr(z, "baseCount", 0),
                        "gap_x_legin": round(getattr(z, "gapToLegIn", 0.0), 2),
                        "mcap_cr": zdata.MCAP_CR.get(sym),
                    })
            except Exception:
                continue
        return out

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        for out in ex.map(_scan_symbol, universe):
            all_zones.extend(out)
    all_zones.sort(key=lambda z: (-z["score"], z["symbol"], z["tf"]))
    return all_zones


def active_zones(zones):
    return zone_core.latest_active_zones(zones)


def alerts(zones, price):
    return zone_core.get_zone_alerts(zones, price)


def top_zones(zones, price, limit=10):
    cand = [z for z in zones if z.state in ("Fresh", "Tested")]
    cand.sort(key=lambda z: (-z.densityScore, abs(z.proxVal - price) / z.proxVal))
    return cand[:limit]


def zone_to_row(z, price):
    dist_pct = (price - z.proxVal) / z.proxVal * 100
    if not z.isDemand:
        dist_pct = (z.proxVal - price) / z.proxVal * 100
    return {
        "pattern": z.patternType,
        "cat": z.zoneCategory,
        "dir": "DEMAND" if z.isDemand else "SUPPLY",
        "entry": round(z.proxVal, 2),
        "sl": round(z.slVal, 2),
        "tp": round(z.tpVal, 2),
        "score": z.densityScore,
        "hq": z.isHQ,
        "touches": z.touchCount,
        "state": z.state,
        "dist%": round(dist_pct, 2),
        "ts": z.timestamp,
    }


def scan_universe(timeframes=("1h", "4h"), min_score=60, recommended=True,
                  strict=False, eod_filter=False, symbols=None):
    """Scan ALL NSE futures stocks across BOTH timeframes at once (summary rows).

    Returns a list of rows (one per stock-timeframe) with zone count, best active
    zone, last price, and recommended ROI, so the app can show the whole universe
    in a single table (each row also links to that stock's option chain).
    """
    import options as _opt
    import tv as _tv
    rows = []
    universe = list(symbols) if symbols else list(zdata.FUT_STOCKS)
    for sym in universe:
        for tf in timeframes:
            try:
                zones, df, extra = scan(sym, tf, min_score=min_score,
                                        recommended=recommended, strict=strict)
                last = float(df["close"].iloc[-1]) if df is not None and len(df) else None
                active = [z for z in zones if z.state in ("Fresh", "Tested")]
                best = max(active, key=lambda z: z.densityScore) if active else None
                roi = extra.get("roi", {}) if isinstance(extra, dict) else {}
                links = _opt.deep_links(sym)
                chain = links[0]["url"] if links else ""
                rows.append({
                    "symbol": sym, "tf": tf, "zones": len(zones),
                    "active": len(active),
                    "best_score": best.densityScore if best else None,
                    "best_dir": ("Demand" if best.isDemand else "Supply") if best else None,
                    "best_pat": best.patternType if best else None,
                    "last": last,
                    "roi_n": roi.get("n_trades"),
                    "roi_pct": roi.get("net_roi_pct"),
                    "chain": chain,
                    "tv": _tv.chart_url(sym, tf),
                })
            except Exception as e:
                rows.append({"symbol": sym, "tf": tf, "zones": 0, "active": 0,
                             "best_score": None, "best_dir": None, "best_pat": None,
                             "last": None, "roi_n": None, "roi_pct": None,
                             "chain": "", "tv": _tv.chart_url(sym, tf),
                             "error": str(e)[:60]})
    return rows
