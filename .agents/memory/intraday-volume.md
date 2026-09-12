---
name: Intraday opening volume
description: Data-source behavior that affects volume-gated zone detection on NSE intraday bars.
---

Yahoo Finance can return `volume=0` for the first NSE session candle in a historical 60-minute series even when TradingView has a real opening-candle volume. Treat that value as missing for volume-gate decisions; do not award the volume score bonus unless a positive volume is available.

**Why:** A valid ICICIBANK 1-hour DBR setup was rejected only because Yahoo reported the leg-out opening candle as zero volume, while the TradingView reference showed the same candle with real volume.

**How to apply:** Preserve the normal `legOutVolume > legInVolume` comparison when both volumes are positive. Handle zero/NaN leg-out volume as unknown at the data-boundary or scanner rule, and keep a regression case for an opening-candle setup.