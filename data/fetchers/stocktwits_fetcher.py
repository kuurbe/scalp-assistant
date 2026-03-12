"""
Stocktwits social sentiment fetcher — public API, no authentication required.
Rate limit: 200 requests/hour (unauthenticated).
"""
import logging
import ssl
import time

if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

import requests

from data.cache import cached

logger = logging.getLogger(__name__)

BASE_URL = "https://api.stocktwits.com/api/2"
SYMBOL_STREAM_URL = f"{BASE_URL}/streams/symbol/{{symbol}}.json"
TRENDING_SYMBOLS_URL = f"{BASE_URL}/trending/symbols.json"
TRENDING_STREAM_URL = f"{BASE_URL}/streams/trending.json"

# Rate-limit tracking (200 req/hr unauthenticated)
_rate_limit_state = {
    "requests": [],
    "max_per_hour": 200,
}


def _check_rate_limit() -> bool:
    """
    Return True if we are safe to make a request, False if we should back off.
    Tracks a sliding window of timestamps over the last hour.
    """
    now = time.time()
    cutoff = now - 3600
    _rate_limit_state["requests"] = [
        t for t in _rate_limit_state["requests"] if t > cutoff
    ]
    if len(_rate_limit_state["requests"]) >= _rate_limit_state["max_per_hour"]:
        logger.warning("Stocktwits rate limit approaching — backing off")
        return False
    _rate_limit_state["requests"].append(now)
    return True


def _api_get(url: str, params: dict | None = None) -> dict | None:
    """
    Make a GET request to the Stocktwits API with rate-limit awareness.
    Returns parsed JSON dict on success, None on any failure.
    """
    if not _check_rate_limit():
        logger.warning("Stocktwits rate limit reached, skipping request: %s", url)
        return None
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 429:
            logger.warning("Stocktwits 429 rate limited — backing off")
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.debug("Stocktwits API request failed (%s): %s", url, e)
        return None
    except (ValueError, KeyError) as e:
        logger.debug("Stocktwits API response parse error (%s): %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

@cached(ttl=300)
def get_stocktwits_messages(ticker: str, limit: int = 30) -> list[dict]:
    """
    Fetch recent Stocktwits messages for a given ticker symbol.

    Args:
        ticker: Stock symbol (e.g. "AAPL").
        limit:  Maximum number of messages to return (max 30 per API page).

    Returns:
        List of dicts, each containing:
            body (str):       Message text.
            username (str):   Author username.
            sentiment (str):  "Bullish", "Bearish", or "None".
            created_at (str): ISO timestamp string.
            likes (int):      Number of likes on the message.
        Returns empty list on failure.
    """
    url = SYMBOL_STREAM_URL.format(symbol=ticker.upper())
    data = _api_get(url)
    if data is None:
        return []

    messages_raw = data.get("messages", [])
    results: list[dict] = []

    for msg in messages_raw:
        if len(results) >= limit:
            break

        # Parse sentiment from entities.sentiment.basic
        sentiment = "None"
        entities = msg.get("entities", {})
        if entities:
            sentiment_obj = entities.get("sentiment")
            if sentiment_obj and isinstance(sentiment_obj, dict):
                sentiment = sentiment_obj.get("basic", "None")

        likes = 0
        likes_obj = msg.get("likes", {})
        if isinstance(likes_obj, dict):
            likes = likes_obj.get("total", 0)
        elif isinstance(likes_obj, (int, float)):
            likes = int(likes_obj)

        user_obj = msg.get("user", {})
        username = user_obj.get("username", "unknown") if isinstance(user_obj, dict) else "unknown"

        results.append({
            "body": msg.get("body", ""),
            "username": username,
            "sentiment": sentiment,
            "created_at": msg.get("created_at", ""),
            "likes": likes,
        })

    return results


@cached(ttl=300)
def get_trending_tickers() -> list[dict]:
    """
    Fetch currently trending ticker symbols from Stocktwits.

    Returns:
        List of dicts, each containing:
            symbol (str):          Ticker symbol.
            title (str):           Company / asset name.
            watchlist_count (int): Number of users watching this symbol.
        Returns empty list on failure.
    """
    data = _api_get(TRENDING_SYMBOLS_URL)
    if data is None:
        return []

    symbols_raw = data.get("symbols", [])
    results: list[dict] = []

    for sym in symbols_raw:
        results.append({
            "symbol": sym.get("symbol", ""),
            "title": sym.get("title", ""),
            "watchlist_count": sym.get("watchlist_count", 0),
        })

    return results


@cached(ttl=300)
def get_stocktwits_sentiment(ticker: str) -> dict:
    """
    Calculate aggregated sentiment metrics for a ticker based on recent messages.

    Args:
        ticker: Stock symbol (e.g. "AAPL").

    Returns:
        Dict containing:
            bullish_pct (float):     Percentage of messages tagged Bullish.
            bearish_pct (float):     Percentage of messages tagged Bearish.
            total_messages (int):    Total messages analysed.
            sentiment_score (float): Score from -100 (all bearish) to +100 (all bullish).
            trending (bool):         Whether the ticker appears in trending symbols.
    """
    default = {
        "bullish_pct": 0.0,
        "bearish_pct": 0.0,
        "total_messages": 0,
        "sentiment_score": 0.0,
        "trending": False,
    }

    messages = get_stocktwits_messages(ticker, limit=30)
    if not messages:
        return default

    bullish = sum(1 for m in messages if m["sentiment"] == "Bullish")
    bearish = sum(1 for m in messages if m["sentiment"] == "Bearish")
    total = len(messages)
    tagged = bullish + bearish

    bullish_pct = round((bullish / tagged) * 100, 1) if tagged > 0 else 0.0
    bearish_pct = round((bearish / tagged) * 100, 1) if tagged > 0 else 0.0

    # Sentiment score: +100 = all bullish, -100 = all bearish, 0 = neutral/even
    if tagged > 0:
        sentiment_score = round(((bullish - bearish) / tagged) * 100, 1)
    else:
        sentiment_score = 0.0

    # Check if ticker is in trending list
    trending = False
    trending_tickers = get_trending_tickers()
    ticker_upper = ticker.upper()
    for sym in trending_tickers:
        if sym.get("symbol", "").upper() == ticker_upper:
            trending = True
            break

    return {
        "bullish_pct": bullish_pct,
        "bearish_pct": bearish_pct,
        "total_messages": total,
        "sentiment_score": sentiment_score,
        "trending": trending,
    }


@cached(ttl=300)
def get_social_buzz(ticker: str) -> dict:
    """
    Get social buzz metrics for a ticker: message volume, sentiment direction,
    and notable users (most-liked posters).

    Args:
        ticker: Stock symbol (e.g. "AAPL").

    Returns:
        Dict containing:
            message_volume (int):        Number of recent messages found.
            sentiment_direction (str):   "bullish", "bearish", or "neutral".
            notable_users (list[str]):   Usernames of top contributors by likes.
    """
    default = {
        "message_volume": 0,
        "sentiment_direction": "neutral",
        "notable_users": [],
    }

    messages = get_stocktwits_messages(ticker, limit=30)
    if not messages:
        return default

    # Sentiment direction
    bullish = sum(1 for m in messages if m["sentiment"] == "Bullish")
    bearish = sum(1 for m in messages if m["sentiment"] == "Bearish")

    if bullish > bearish:
        direction = "bullish"
    elif bearish > bullish:
        direction = "bearish"
    else:
        direction = "neutral"

    # Notable users: pick unique usernames with highest-liked messages
    sorted_msgs = sorted(messages, key=lambda m: m.get("likes", 0), reverse=True)
    seen: set[str] = set()
    notable: list[str] = []
    for m in sorted_msgs:
        uname = m.get("username", "")
        if uname and uname != "unknown" and uname not in seen:
            seen.add(uname)
            notable.append(uname)
        if len(notable) >= 5:
            break

    return {
        "message_volume": len(messages),
        "sentiment_direction": direction,
        "notable_users": notable,
    }
