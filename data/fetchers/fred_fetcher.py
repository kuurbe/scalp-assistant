"""
FRED macro data fetcher — federal funds rate, yield curve, VIX, consumer sentiment.
Uses direct FRED REST API via requests (avoids fredapi SSL hangs on macOS).
"""
from __future__ import annotations
import logging
import os

import requests
from data.cache import cached
from config import settings

logger = logging.getLogger(__name__)

FRED_API_BASE = "https://api.stlouisfed.org/fred/series/observations"

_DEFAULT_CONTEXT = {
    "fed_rate": None,
    "yield_curve_spread": None,
    "vix": None,
    "consumer_sentiment": None,
    "macro_regime": "NEUTRAL",
}


def _get_fred_client():
    """
    Return the FRED API key string, or None if not set.
    Kept for backward compatibility with data_bridge imports.
    """
    from config.settings import get_secret
    api_key = get_secret("FRED_KEY")
    if not api_key:
        logger.warning("FRED_KEY not set — returning default macro context")
        return None
    return api_key


def _fetch_latest_value(fred_key, series_id: str) -> float | None:
    """
    Fetch the most recent non-NaN value for a FRED series via REST API.

    Args:
        fred_key: FRED API key string (from _get_fred_client).
        series_id: FRED series identifier.

    Returns:
        Most recent float value, or None on failure.
    """
    try:
        resp = requests.get(
            FRED_API_BASE,
            params={
                "series_id": series_id,
                "api_key": fred_key,
                "file_type": "json",
                "limit": 5,
                "sort_order": "desc",
            },
            timeout=8,
        )
        resp.raise_for_status()
        observations = resp.json().get("observations", [])
        for obs in observations:
            val = obs.get("value", ".")
            if val != ".":
                return round(float(val), 4)
        return None
    except Exception as e:
        logger.debug("Failed to fetch FRED series %s: %s", series_id, e)
        return None


def _determine_regime(
    fed_rate: float | None,
    yield_curve_spread: float | None,
    vix: float | None,
    consumer_sentiment: float | None,
) -> str:
    """
    Determine the macro regime based on available indicators.

    Returns:
        "RISK_ON", "RISK_OFF", or "NEUTRAL".

    Logic:
        - RISK_OFF if yield curve is inverted (spread < 0) AND VIX > 25
        - RISK_OFF if VIX > 30 (extreme fear regardless)
        - RISK_ON if yield curve spread > 0.5 AND VIX < 18 AND sentiment > 70
        - NEUTRAL otherwise
    """
    risk_off_signals = 0
    risk_on_signals = 0

    # Yield curve inversion is a recession signal
    if yield_curve_spread is not None:
        if yield_curve_spread < 0:
            risk_off_signals += 1
        elif yield_curve_spread > 0.5:
            risk_on_signals += 1

    # VIX thresholds
    if vix is not None:
        if vix > 30:
            risk_off_signals += 2  # Strong signal
        elif vix > 25:
            risk_off_signals += 1
        elif vix < 18:
            risk_on_signals += 1
        elif vix < 14:
            risk_on_signals += 2  # Very calm

    # Consumer sentiment
    if consumer_sentiment is not None:
        if consumer_sentiment < 60:
            risk_off_signals += 1
        elif consumer_sentiment > 70:
            risk_on_signals += 1

    if risk_off_signals >= 2:
        return "RISK_OFF"
    elif risk_on_signals >= 2:
        return "RISK_ON"
    return "NEUTRAL"


@cached(ttl=settings.CACHE_TTL_SECONDS)
def get_macro_context() -> dict:
    """
    Fetch current macro context from FRED.

    Uses the series defined in settings.FRED_SERIES:
        - FEDFUNDS: Federal Funds Effective Rate
        - T10Y2Y: 10-Year minus 2-Year Treasury spread
        - VIXCLS: CBOE VIX
        - UMCSENT: University of Michigan Consumer Sentiment

    Returns:
        Dict with:
            fed_rate (float | None): Current federal funds rate
            yield_curve_spread (float | None): 10Y-2Y spread
            vix (float | None): Current VIX level
            consumer_sentiment (float | None): Latest consumer sentiment
            macro_regime (str): "RISK_ON", "RISK_OFF", or "NEUTRAL"
    """
    fred_key = _get_fred_client()
    if fred_key is None:
        return dict(_DEFAULT_CONTEXT)

    try:
        # Map settings series IDs to our output keys
        series_map = {
            "FEDFUNDS": "fed_rate",
            "T10Y2Y": "yield_curve_spread",
            "VIXCLS": "vix",
            "UMCSENT": "consumer_sentiment",
        }

        result = {}
        for series_id in settings.FRED_SERIES:
            key = series_map.get(series_id, series_id.lower())
            result[key] = _fetch_latest_value(fred_key, series_id)

        result["macro_regime"] = _determine_regime(
            result.get("fed_rate"),
            result.get("yield_curve_spread"),
            result.get("vix"),
            result.get("consumer_sentiment"),
        )

        return result
    except Exception as e:
        logger.error("get_macro_context failed: %s", e)
        return dict(_DEFAULT_CONTEXT)
