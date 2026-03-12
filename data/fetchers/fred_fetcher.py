"""
FRED macro data fetcher — federal funds rate, yield curve, VIX, consumer sentiment.
Uses the fredapi library for Federal Reserve Economic Data.
"""
import logging
import os
import ssl

# Fix macOS SSL certificate issues
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

from data.cache import cached
from config import settings

logger = logging.getLogger(__name__)

_DEFAULT_CONTEXT = {
    "fed_rate": None,
    "yield_curve_spread": None,
    "vix": None,
    "consumer_sentiment": None,
    "macro_regime": "NEUTRAL",
}


def _get_fred_client():
    """
    Create and return a Fred client, or None if no API key is available.
    Import is deferred so the module loads even if fredapi isn't installed.
    """
    api_key = os.environ.get("FRED_KEY")
    if not api_key:
        logger.warning("FRED_KEY not set — returning default macro context")
        return None
    try:
        from fredapi import Fred
        return Fred(api_key=api_key)
    except ImportError:
        logger.error("fredapi library not installed — pip install fredapi")
        return None
    except Exception as e:
        logger.error("Failed to create Fred client: %s", e)
        return None


def _fetch_latest_value(fred, series_id: str) -> float | None:
    """
    Fetch the most recent non-NaN value for a FRED series.

    Args:
        fred: Fred client instance.
        series_id: FRED series identifier.

    Returns:
        Most recent float value, or None on failure.
    """
    try:
        series = fred.get_series(series_id)
        if series is None or series.empty:
            return None
        # Drop NaN values and get the last one
        series = series.dropna()
        if series.empty:
            return None
        return round(float(series.iloc[-1]), 4)
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
    fred = _get_fred_client()
    if fred is None:
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
            result[key] = _fetch_latest_value(fred, series_id)

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
