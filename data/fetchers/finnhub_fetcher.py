"""
Finnhub data fetcher — news, sentiment, earnings, financials.
Uses the Finnhub REST API with token-bucket rate limiting.
"""
import logging
import os
import time
import threading
from datetime import datetime, timedelta

import requests

from data.cache import cached
from config import settings

logger = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"

# ─────────────────────────────────────────────────────────────
#  Token-bucket rate limiter (60 calls per minute by default)
# ─────────────────────────────────────────────────────────────
_lock = threading.Lock()
_call_timestamps: list[float] = []


def _rate_limit() -> None:
    """
    Block until we can make another API call without exceeding
    FINNHUB_RATE_LIMIT calls per 60-second window.
    """
    max_calls = settings.FINNHUB_RATE_LIMIT  # 60
    window = 60.0  # seconds

    with _lock:
        now = time.time()
        cutoff = now - window
        # Purge timestamps older than the window
        while _call_timestamps and _call_timestamps[0] < cutoff:
            _call_timestamps.pop(0)

        if len(_call_timestamps) >= max_calls:
            # Must wait until the oldest call in the window expires
            sleep_for = _call_timestamps[0] - cutoff
            if sleep_for > 0:
                logger.debug("Finnhub rate limit: sleeping %.2fs", sleep_for)
                time.sleep(sleep_for)
            # Re-purge after sleep
            now = time.time()
            cutoff = now - window
            while _call_timestamps and _call_timestamps[0] < cutoff:
                _call_timestamps.pop(0)

        _call_timestamps.append(time.time())


def _get_api_key() -> str | None:
    """Return the Finnhub API key or None."""
    return os.environ.get("FINNHUB_KEY")


def _finnhub_get(endpoint: str, params: dict | None = None) -> dict | list | None:
    """
    Generic GET against the Finnhub API.
    Applies rate limiting and attaches the token.
    Returns parsed JSON or None on failure.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.debug("FINNHUB_KEY not set — skipping Finnhub request")
        return None

    _rate_limit()

    params = params or {}
    params["token"] = api_key
    url = f"{FINNHUB_BASE}/{endpoint}"

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.debug("Finnhub %s failed: %s", endpoint, e)
        return None


# ─────────────────────────────────────────────────────────────
#  Public fetcher functions
# ─────────────────────────────────────────────────────────────


@cached(ttl=settings.NEWS_CACHE_TTL)
def get_company_news(ticker: str, days_back: int = 3) -> list[dict]:
    """
    Fetch recent company news for a ticker.

    Args:
        ticker: Stock symbol.
        days_back: How many days of news to fetch (default 3).

    Returns:
        List of dicts with headline, summary, source, url, datetime.
    """
    today = datetime.utcnow().date()
    from_date = (today - timedelta(days=days_back)).isoformat()
    to_date = today.isoformat()

    data = _finnhub_get(
        "company-news",
        {"symbol": ticker, "from": from_date, "to": to_date},
    )
    if not data or not isinstance(data, list):
        return []

    results = []
    for item in data:
        results.append({
            "headline": item.get("headline", ""),
            "summary": item.get("summary", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "datetime": datetime.utcfromtimestamp(
                item.get("datetime", 0)
            ).isoformat() if item.get("datetime") else None,
        })
    return results


@cached(ttl=settings.NEWS_CACHE_TTL)
def get_market_news(category: str = "general") -> list[dict]:
    """
    Fetch general market news.

    Args:
        category: "general", "forex", "crypto", or "merger".

    Returns:
        List of dicts with headline, summary, source, url, datetime.
    """
    data = _finnhub_get("news", {"category": category})
    if not data or not isinstance(data, list):
        return []

    results = []
    for item in data:
        results.append({
            "headline": item.get("headline", ""),
            "summary": item.get("summary", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "datetime": datetime.utcfromtimestamp(
                item.get("datetime", 0)
            ).isoformat() if item.get("datetime") else None,
        })
    return results


@cached(ttl=settings.NEWS_CACHE_TTL)
def get_news_sentiment(ticker: str) -> dict:
    """
    Fetch aggregated news sentiment for a ticker.

    Returns:
        Dict with 'buzz' (articlesInLastWeek, weeklyAverage, buzz) and
        'sentiment' (bearishPercent, bullishPercent, companyNewsScore).
        Empty dict on failure.
    """
    data = _finnhub_get("news-sentiment", {"symbol": ticker})
    if not data or not isinstance(data, dict):
        return {}

    return {
        "buzz": data.get("buzz", {}),
        "sentiment": data.get("sentiment", {}),
        "company_news_score": data.get("companyNewsScore"),
        "sector_average_bullish_percent": data.get("sectorAverageBullishPercent"),
        "sector_average_news_score": data.get("sectorAverageNewsScore"),
    }


@cached(ttl=settings.NEWS_CACHE_TTL)
def get_social_sentiment(ticker: str) -> dict:
    """
    Fetch social sentiment (Reddit, Twitter) for a ticker.

    Returns:
        Dict with 'reddit' and 'twitter' sub-dicts containing
        mention counts and sentiment scores. Empty dict on failure.
    """
    data = _finnhub_get("stock/social-sentiment", {"symbol": ticker})
    if not data or not isinstance(data, dict):
        return {}

    reddit_data = data.get("reddit", [])
    twitter_data = data.get("twitter", [])

    # Aggregate the most recent entries
    reddit_summary = {"mentions": 0, "positive_mentions": 0, "negative_mentions": 0}
    for entry in reddit_data[-24:]:  # Last 24 hours
        reddit_summary["mentions"] += entry.get("mention", 0)
        reddit_summary["positive_mentions"] += entry.get("positiveMention", 0)
        reddit_summary["negative_mentions"] += entry.get("negativeMention", 0)

    twitter_summary = {"mentions": 0, "positive_mentions": 0, "negative_mentions": 0}
    for entry in twitter_data[-24:]:
        twitter_summary["mentions"] += entry.get("mention", 0)
        twitter_summary["positive_mentions"] += entry.get("positiveMention", 0)
        twitter_summary["negative_mentions"] += entry.get("negativeMention", 0)

    return {
        "reddit": reddit_summary,
        "twitter": twitter_summary,
    }


@cached(ttl=settings.CACHE_TTL_SECONDS)
def get_earnings_calendar(from_date: str, to_date: str) -> list[dict]:
    """
    Fetch earnings calendar between two dates.

    Args:
        from_date: Start date in YYYY-MM-DD format.
        to_date: End date in YYYY-MM-DD format.

    Returns:
        List of dicts with symbol, date, epsActual, epsEstimate,
        revenueActual, revenueEstimate, hour. Empty list on failure.
    """
    data = _finnhub_get(
        "calendar/earnings",
        {"from": from_date, "to": to_date},
    )
    if not data or not isinstance(data, dict):
        return []

    earnings = data.get("earningsCalendar", [])
    results = []
    for item in earnings:
        results.append({
            "symbol": item.get("symbol", ""),
            "date": item.get("date", ""),
            "epsActual": item.get("epsActual"),
            "epsEstimate": item.get("epsEstimate"),
            "revenueActual": item.get("revenueActual"),
            "revenueEstimate": item.get("revenueEstimate"),
            "hour": item.get("hour", ""),
        })
    return results


@cached(ttl=settings.CACHE_TTL_SECONDS)
def get_basic_financials(ticker: str) -> dict:
    """
    Fetch basic financial metrics for a ticker.

    Returns:
        Dict with 52WeekHigh, 52WeekLow, beta, 10DayAverageTradingVolume,
        revenueGrowthQuarterlyYoy, etc. Empty dict on failure.
    """
    data = _finnhub_get("stock/metric", {"symbol": ticker, "metric": "all"})
    if not data or not isinstance(data, dict):
        return {}

    metric = data.get("metric", {})
    if not metric:
        return {}

    return {
        "52WeekHigh": metric.get("52WeekHigh"),
        "52WeekLow": metric.get("52WeekLow"),
        "beta": metric.get("beta"),
        "10DayAverageTradingVolume": metric.get("10DayAverageTradingVolume"),
        "revenueGrowthQuarterlyYoy": metric.get("revenueGrowthQuarterlyYoy"),
        "epsGrowthQuarterlyYoy": metric.get("epsGrowthQuarterlyYoy"),
        "roeTTM": metric.get("roeTTM"),
        "debtEquityQuarterly": metric.get("totalDebt/totalEquityQuarterly"),
        "currentRatioQuarterly": metric.get("currentRatioQuarterly"),
        "revenueGrowth3Y": metric.get("revenueGrowth3Y"),
    }
