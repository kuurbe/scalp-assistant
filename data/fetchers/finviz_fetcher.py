"""
Market movers fetcher — free screener via Yahoo Finance public API.

Replaces Finviz (now JS-rendered, requires Elite for CSV).
Yahoo Finance's predefined screeners are free, real-time, no auth required.

Two uses:
1. get_finviz_movers()    → top momentum tickers right now (name kept for compat)
2. augment_universe()     → adds new movers not in the static universe
"""
from __future__ import annotations
import logging
import time

import requests

logger = logging.getLogger(__name__)

_CACHE: dict = {"ts": 0.0, "tickers": []}
_CACHE_TTL = 300  # 5 min

_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}

_YF_SCREENER = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"

# Yahoo Finance predefined screener IDs
_SCREENER_IDS = ["day_gainers", "most_actives"]


def get_finviz_movers(
    min_change_pct: float = 2.0,
    min_avg_volume: int = 500_000,
) -> list[str]:
    """
    Return today's top momentum tickers from Yahoo Finance screeners.
    Results cached 5 minutes.
    """
    now = time.time()
    if now - _CACHE["ts"] < _CACHE_TTL and _CACHE["tickers"]:
        return _CACHE["tickers"]

    tickers: list[str] = []
    seen: set[str] = set()

    for scr_id in _SCREENER_IDS:
        try:
            resp = requests.get(
                _YF_SCREENER,
                params={"scrIds": scr_id, "count": 50,
                        "fields": "symbol,regularMarketChangePercent,averageDailyVolume3Month"},
                headers=_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            quotes = (
                resp.json()
                .get("finance", {})
                .get("result", [{}])[0]
                .get("quotes", [])
            )
            for q in quotes:
                sym = (q.get("symbol") or "").upper().strip()
                if not sym or sym in seen:
                    continue
                pct = q.get("regularMarketChangePercent") or 0
                avg_vol = q.get("averageDailyVolume3Month") or 0
                if pct >= min_change_pct and avg_vol >= min_avg_volume:
                    tickers.append(sym)
                    seen.add(sym)
        except Exception as e:
            logger.warning("Yahoo screener %s failed: %s", scr_id, e)

    _CACHE["ts"] = now
    _CACHE["tickers"] = tickers
    logger.info("Movers screener: %d tickers (≥%.0f%% today)", len(tickers), min_change_pct)
    return tickers


def augment_universe(universe: list[str], max_new: int = 20) -> list[str]:
    """Add Yahoo Finance movers not already in `universe`. Deduped, order-preserving."""
    try:
        movers = get_finviz_movers()
        existing = set(universe)
        new_tickers = [t for t in movers if t not in existing][:max_new]
        if new_tickers:
            logger.info("Screener augmented universe +%d: %s", len(new_tickers), new_tickers[:10])
        return universe + new_tickers
    except Exception as e:
        logger.warning("augment_universe failed: %s", e)
        return universe
