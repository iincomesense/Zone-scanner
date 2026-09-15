"""
zscan.py — thin wrapper around zone_core for the Streamlit app.

Zone density/HQ scoring has been removed. The former min_score argument and
legacy score fields are retained only for API compatibility with older callers;
all score values are neutral (0/False) and are never used for validation or
sorting.
"""
from __future__ import annotations

import threading
import time

import pandas as pd
import zone_core
import zdata


# --------------------------------------------------------------------------- #
# Small process-level caches so a universe scan reuses base bars / OI / quotes #
# --------------------------------------------------------------------------- #
_oi_cache = {}
_oi_lock = threading.Lock()
_daily_hl_cache = {}
_dhl_lock = threading.Lock()
_scan_cache = {}          # (symbol, tf, recommended, strict, capital, stamp) -> result
_ctx_cache = {}           # market context with TTL
_ctx_lock = threading.Lock()
HTF_OF = {
    "10m": "1h",
    "15m": "1h",
    "30m": "2h",
    "1h": "4h",
    "2h": "1D",
    "4h": "1D",
    "6h": "1D",
    "1D": "1W",
    "1W": "1M",
    "1M": None,
}


# --------------------------------------------------------------------------- #
# Market context / target context                                             #
# --------------------------------------------------------------------------- #
def market_context(ttl=900):
    """Return shared market-context inputs used by target_context()."""
    with _ctx_lock:
        cached = _ctx_cache.get("ctx")
        if cached and (time.time() - cached[0]) < ttl:
            return cached[1]

    output = {"nifty": None, "vix": None, "spx_ret20": None}
    try:
        output["nifty"] = zdata.load_zone_frame("^NSEI", "1D")
    except Exception:
        pass
    try:
        vix_df = zdata.load_zone_frame("^INDIAVIX", "1D")
        output["vix"] = (
            float(vix_df["close"].dropna().iloc[-1])
            if vix_df is not None and len(vix_df)
            else None
        )
    except Exception:
        pass
    try:
        sp_df = zdata.load_zone_frame("^GSPC", "1D")["close"].dropna()
        output["spx_ret20"] = (
            float(sp_df.iloc[-1] / sp_df.iloc[-21] - 1) * 100
            if len(sp_df) > 21
            else None
        )
    except Exception:
        pass

    with _ctx_lock:
        _ctx_cache["ctx"] = (time.time(), output)
    return output


def tp_context(z, sym, tf, df=None, ctx=None):
    """Return target_context() for one zone."""
    ctx = ctx or market_context()
    htf = HTF_OF.get(tf)
    htf_df = None
    if htf:
        try:
            htf_df = zdata.load_zone_frame(sym, htf)
        except Exception:
            htf_df = None

    return zone_core.target_context(
        z,
        df,
        htf_df=htf_df,
        market_df=ctx.get("nifty"),
        vix=ctx.get("vix"),
        spx_ret20=ctx.get("spx_ret20"),
    )


_scan_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Daily high/low and OI helpers                                                #
# --------------------------------------------------------------------------- #
def _daily_hl(symbol):
    with zdata._BASE_LOCK:
        stamp = zdata._BASE_CACHE.get(
            (symbol, "1d", "1y"),
            (None,),
        )[0]

    with _dhl_lock:
        cached = _daily_hl_cache.get(symbol)
        if cached is not None and cached[0] == stamp and stamp is not None:
            return cached[1]

    value = zdata.daily_hl(symbol, period="1y")
    with zdata._BASE_LOCK:
        stamp = zdata._BASE_CACHE.get(
            (symbol, "1d", "1y"),
            (None,),
        )[0]
    with _dhl_lock:
        _daily_hl_cache[symbol] = (stamp, value)
    return value


_oi_blocked_until = [0.0]


def _oi_snapshot(symbol):
    """Return (call_oi, put_oi) or (None, None)."""
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
    """Fetch option-chain OI in parallel, skipping a blocked NSE endpoint."""
    import time as _t
    from concurrent.futures import ThreadPoolExecutor

    now = _t.time()
    with _oi_lock:
        if now < _oi_blocked_until[0]:
            return
        stale = [
            symbol
            for symbol in symbols
            if symbol not in _oi_cache
            or (
                _oi_cache.get(symbol, (None, None))[0] is None
                and _oi_cache.get(symbol, (None, None))[1] is None
            )
        ]
        if not stale:
            return

    probe = _oi_snapshot(stale[0])
    if probe[0] is None:
        with _oi_lock:
            _oi_blocked_until[0] = now + 600
            for symbol in stale:
                _oi_cache.setdefault(symbol, (None, None))
        return

    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(_oi_snapshot, stale[1:]))


def _fmt_oi(value):
    """Format an OI count the Indian way (Cr / L / raw)."""
    if value is None:
        return "—"
    value = float(value)
    if value >= 1e7:
        return f"{value / 1e7:.2f}Cr"
    if value >= 1e5:
        return f"{value / 1e5:.2f}L"
    return f"{value:,.0f}"


def oi_bias(symbol, is_demand):
    """Return the Put/Call OI bias for a zone direction."""
    call_oi, put_oi = _oi_snapshot(symbol)
    if call_oi is None or put_oi is None or call_oi == 0:
        return {}

    put_text, call_text = _fmt_oi(put_oi), _fmt_oi(call_oi)
    if is_demand:
        aligned = put_oi > call_oi
        return {
            "label": f"P {put_text} {'>' if aligned else '<'} C {call_text}",
            "aligned": aligned,
            "put": put_oi,
            "call": call_oi,
        }

    aligned = call_oi > put_oi
    return {
        "label": f"C {call_text} {'>' if aligned else '<'} P {put_text}",
        "aligned": aligned,
        "put": put_oi,
        "call": call_oi,
    }


# --------------------------------------------------------------------------- #
# EOD band helpers                                                             #
# --------------------------------------------------------------------------- #
def eod_band(symbol):
    """Return the last completed daily-candle band or None."""
    high, low = _daily_hl(symbol)
    if high is None or low is None:
        return None
    return {
        "hi": high,
        "lo": low,
        "eod_hi": high * 1.10,
        "eod_lo": low * 0.90,
    }


def eod_zone_filter(zones, symbol):
    """Keep zones overlapping the EOD band."""
    band = eod_band(symbol)
    if band is None:
        return zones, None

    kept = []
    for zone in zones:
        zone_low = min(zone.proxVal, zone.distVal)
        zone_high = max(zone.proxVal, zone.distVal)
        if zone_high >= band["eod_lo"] and zone_low <= band["eod_hi"]:
            kept.append(zone)
    return kept, band


# --------------------------------------------------------------------------- #
# Single-symbol scan                                                           #
# --------------------------------------------------------------------------- #
def scan(
    symbol,
    timeframe="2h",
    min_score=0,
    recommended=False,
    strict=False,
    lookback_months=None,
    start=None,
    accountCapital=None,
):
    """Return (zones, df, summary_dict).

    ``min_score`` remains in the signature only for old callers. It is ignored
    because zone scoring has been removed.
    """
    del min_score

    df = zdata.load_zone_frame(symbol, timeframe, start=start)
    cache_key = None
    if start is None and lookback_months is None:
        cfg = zdata.TF_CONFIG.get(timeframe) or zdata.TF_CONFIG.get(
            zdata.normalize_tf(timeframe)
        )
        with zdata._BASE_LOCK:
            stamp = zdata._BASE_CACHE.get(
                (symbol, cfg["interval"], cfg["period"]),
                (None,),
            )[0]

        capital_key = (
            None if accountCapital is None else float(accountCapital)
        )
        cache_key = (
            symbol,
            timeframe,
            bool(recommended),
            bool(strict),
            capital_key,
            stamp,
        )
        with _scan_lock:
            cached = _scan_cache.get(cache_key)
        if cached is not None:
            return cached

    params = zone_core.settings(accountCapital=accountCapital)
    if strict:
        params.update(
            {
                "volume_gate": True,
                "legInMinAtrMult": 1.0,
                "maxWickPct": 0.30,
                "legInToBaseSizeMult": 2.0,
                "legInToBaseSizeMultSingleBase": 1.5,
                "legOutMinTrRatio": 1.0,
            }
        )

    # No minValidScore is inserted here. It was removed from zone_core.
    zones = zone_core.scan_zones(
        df,
        params=params,
        accountCapital=accountCapital,
    )

    if recommended:
        recommendation = zone_core.recommended_trade_setup(
            accountCapital=accountCapital
        )
        zones_all = zones
        zones = [
            zone
            for zone in zones_all
            if zone.patternType in recommendation["patterns"]
        ]
        roi = zone_core.realistic_roi(
            zones_all,
            df,
            rr=recommendation["targetRR"],
            risk_pct=recommendation["risk_pct"],
            capital=recommendation["capital"],
            patterns=recommendation["patterns"],
            buffer=recommendation["slBufferAtr"],
            entry_mode=recommendation.get("entry_mode", "prox"),
            max_hold=40,
        )
        result = (
            zones,
            df,
            {"recommended": recommendation, "roi": roi},
        )
    else:
        result = (zones, df, zone_core.backtest_summary(zones, df))

    if cache_key is not None:
        with _scan_lock:
            if len(_scan_cache) > 6000:
                _scan_cache.clear()
            _scan_cache[cache_key] = result
    return result


# --------------------------------------------------------------------------- #
# Universe scan                                                                #
# --------------------------------------------------------------------------- #
def scan_universe_zones(
    timeframes=("10m", "15m", "1h", "2h", "4h", "6h", "1D", "1W", "1M"),
    min_score=0,
    recommended=True,
    strict=False,
    active_only=False,
    eod_filter=False,
    symbols=None,
    accountCapital=None,
):
    """Scan the selected universe and return a flat list of valid zones.

    ``min_score`` is accepted for compatibility but is ignored. Legacy output
    keys ``score10``, ``score`` and ``hq`` are neutral values only, so older
    consumers do not fail while migrating away from score-based display.
    """
    import options as _opt
    import tv as _tv

    recommendation_patterns = zone_core.recommended_trade_setup(
        accountCapital=accountCapital
    )["patterns"]
    all_zones = []

    if symbols:
        universe = list(symbols)
    else:
        try:
            universe, _, _ = zdata.build_universe()
        except Exception:
            universe = list(zdata.FUT_STOCKS)

    try:
        zdata.prefetch_for_timeframes(universe, timeframes)
    except Exception:
        pass
    try:
        prefetch_oi(universe)
    except Exception:
        pass

    def _scan_symbol(sym):
        output = []
        eod_lo = eod_hi = None
        if eod_filter:
            high, low = _daily_hl(sym)
            if high is not None and low is not None:
                eod_hi = high * 1.10
                eod_lo = low * 0.90

        links = _opt.deep_links(sym)
        chain = links[0]["url"] if links else ""
        market_ctx = market_context()

        for tf in timeframes:
            try:
                zones, df, extra = scan(
                    sym,
                    tf,
                    min_score=0,
                    recommended=recommended,
                    strict=strict,
                    accountCapital=accountCapital,
                )
                last = (
                    float(df["close"].iloc[-1])
                    if df is not None and len(df)
                    else None
                )
                tv_url = _tv.chart_url(sym, tf)

                for zone in zones:
                    if active_only and zone.state not in ("Fresh", "Tested"):
                        continue
                    if (
                        recommended
                        and zone.patternType not in recommendation_patterns
                    ):
                        continue

                    zone_low = min(zone.proxVal, zone.distVal)
                    zone_high = max(zone.proxVal, zone.distVal)
                    in_band = True
                    if eod_filter and eod_lo is not None:
                        in_band = zone_high >= eod_lo and zone_low <= eod_hi
                    if eod_filter and not in_band:
                        continue

                    try:
                        target_context = tp_context(
                            zone,
                            sym,
                            tf,
                            df,
                            market_ctx,
                        )
                    except Exception:
                        target_context = {}

                    output.append(
                        {
                            "tp_score": target_context.get("score"),
                            "tp_max": target_context.get("max"),
                            "tp_label": target_context.get("label", ""),
                            "tp_signs": "".join(
                                key
                                + ("✓" if target_context.get(key) else "✗")
                                for key in "ABCDEF"
                                if target_context.get(key) is not None
                            ),
                            "tp_why": " | ".join(
                                target_context.get("why", [])
                            ),
                            "legin_vol_x": (
                                None
                                if zone.legInVolX != zone.legInVolX
                                else round(zone.legInVolX, 2)
                            ),
                            "legout_vol_x": (
                                None
                                if zone.legOutVolX != zone.legOutVolX
                                else round(zone.legOutVolX, 2)
                            ),
                            "retest_vol_x": (
                                None
                                if zone.retestVolX != zone.retestVolX
                                else round(zone.retestVolX, 2)
                            ),
                            "symbol": sym,
                            "tf": tf,
                            "pattern": zone.patternType,
                            "dir": "Demand" if zone.isDemand else "Supply",
                            "entry": round(zone.proxVal, 2),
                            "distal": round(zone.distVal, 2),
                            "sl": round(zone.slVal, 2),
                            "tp": round(zone.tpVal, 2),
                            "risk_pct": round(zone.riskPct, 2),
                            # Neutral legacy values; no score is calculated.
                            "score10": 0.0,
                            "colour": False,
                            "score": 0,
                            "hq": False,
                            "state": zone.state,
                            "touches": zone.touchCount,
                            "last": last,
                            "ts": str(zone.timestamp)[:16],
                            "chain": chain,
                            "tv": tv_url,
                            "oi": oi_bias(sym, zone.isDemand),
                            "eod_lo": eod_lo,
                            "eod_hi": eod_hi,
                            "in_band": in_band,
                            "entry_status": getattr(zone, "entryStatus", ""),
                            "entry_price": round(
                                getattr(zone, "entryPrice", 0.0) or 0.0,
                                2,
                            ) or None,
                            "boring": getattr(zone, "baseCount", 0),
                            "gap_x_legin": round(
                                getattr(zone, "gapToLegIn", 0.0),
                                2,
                            ),
                            "mcap_cr": zdata.MCAP_CR.get(sym),
                        }
                    )
            except Exception:
                continue
        return output

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=4) as executor:
        for output in executor.map(_scan_symbol, universe):
            all_zones.extend(output)

    # Score-based sorting removed. The Streamlit layer performs its own
    # near/upcoming sort. Keep a deterministic fallback order here.
    all_zones.sort(
        key=lambda row: (
            row.get("symbol", ""),
            row.get("tf", ""),
            row.get("ts", ""),
        )
    )
    return all_zones


# --------------------------------------------------------------------------- #
# Convenience wrappers                                                         #
# --------------------------------------------------------------------------- #
def active_zones(zones):
    return zone_core.latest_active_zones(zones)


def alerts(zones, price):
    return zone_core.get_zone_alerts(zones, price)


def top_zones(zones, price, limit=10):
    candidates = [
        zone for zone in zones if zone.state in ("Fresh", "Tested")
    ]

    def distance(zone):
        if not zone.proxVal:
            return float("inf")
        return abs(zone.proxVal - price) / abs(zone.proxVal)

    candidates.sort(key=distance)
    return candidates[:limit]


def zone_to_row(z, price):
    distance_pct = (price - z.proxVal) / z.proxVal * 100
    if not z.isDemand:
        distance_pct = (z.proxVal - price) / z.proxVal * 100

    return {
        "pattern": z.patternType,
        "cat": z.zoneCategory,
        "dir": "DEMAND" if z.isDemand else "SUPPLY",
        "entry": round(z.proxVal, 2),
        "sl": round(z.slVal, 2),
        "tp": round(z.tpVal, 2),
        # Legacy neutral values only; no score calculation.
        "score": 0,
        "hq": False,
        "touches": z.touchCount,
        "state": z.state,
        "dist%": round(distance_pct, 2),
        "ts": z.timestamp,
    }


def scan_universe(
    timeframes=("1h", "4h"),
    min_score=0,
    recommended=True,
    strict=False,
    eod_filter=False,
    symbols=None,
    accountCapital=None,
):
    """Scan NSE stocks across the selected timeframes.

    ``min_score`` remains for compatibility and is ignored.
    """
    import options as _opt
    import tv as _tv

    rows = []
    universe = list(symbols) if symbols else list(zdata.FUT_STOCKS)

    for sym in universe:
        for tf in timeframes:
            try:
                zones, df, extra = scan(
                    sym,
                    tf,
                    min_score=0,
                    recommended=recommended,
                    strict=strict,
                    accountCapital=accountCapital,
                )
                last = (
                    float(df["close"].iloc[-1])
                    if df is not None and len(df)
                    else None
                )
                active = [
                    zone for zone in zones
                    if zone.state in ("Fresh", "Tested")
                ]

                if active and last is not None:
                    best = min(
                        active,
                        key=lambda zone: (
                            abs(zone.proxVal - last) / abs(zone.proxVal)
                            if zone.proxVal
                            else float("inf")
                        ),
                    )
                else:
                    best = active[0] if active else None

                roi = extra.get("roi", {}) if isinstance(extra, dict) else {}
                links = _opt.deep_links(sym)
                chain = links[0]["url"] if links else ""
                rows.append(
                    {
                        "symbol": sym,
                        "tf": tf,
                        "zones": len(zones),
                        "active": len(active),
                        # Legacy neutral value; selection is proximity-based.
                        "best_score": 0 if best else None,
                        "best_dir": (
                            "Demand" if best.isDemand else "Supply"
                        ) if best else None,
                        "best_pat": best.patternType if best else None,
                        "last": last,
                        "roi_n": roi.get("n_trades"),
                        "roi_pct": roi.get("net_roi_pct"),
                        "chain": chain,
                        "tv": _tv.chart_url(sym, tf),
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "symbol": sym,
                        "tf": tf,
                        "zones": 0,
                        "active": 0,
                        "best_score": None,
                        "best_dir": None,
                        "best_pat": None,
                        "last": None,
                        "roi_n": None,
                        "roi_pct": None,
                        "chain": "",
                        "tv": _tv.chart_url(sym, tf),
                        "error": str(exc)[:60],
                    }
                )
    return rows
