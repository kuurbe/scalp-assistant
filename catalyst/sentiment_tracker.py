"""
Aggregates sentiment signals from Finnhub social sentiment + Reddit/ApeWisdom mentions.
"""
from data.cache import cached


@cached(ttl=300)
def get_combined_sentiment(ticker: str) -> dict:
    """
    Combine Finnhub sentiment + Reddit social data into a single sentiment view.
    Returns: {
        sentiment_score: float (-100 to +100),
        social_buzz: float (0-100),
        direction: "BULLISH"/"BEARISH"/"NEUTRAL",
        reddit_trending: bool,
        reddit_rank: int or None,
        mention_surge: float,
        summary: str,
    }
    """
    finnhub_sentiment = _get_finnhub_sentiment(ticker)
    reddit_data = _get_reddit_data(ticker)

    # Compute combined sentiment score
    # Finnhub: bullish% - bearish% maps to [-100, +100]
    fh_score = finnhub_sentiment.get("score", 0)

    # Reddit: mention surge as excitement indicator
    reddit_surge = reddit_data.get("mention_surge", 0)
    reddit_rank = reddit_data.get("rank")
    reddit_trending = reddit_data.get("is_trending", False)

    # Social buzz: 0-100 based on reddit activity + finnhub buzz
    buzz = min(100, finnhub_sentiment.get("buzz", 0) * 20 + (50 if reddit_trending else 0))

    # Weighted sentiment
    sentiment_score = fh_score * 0.6 + (reddit_surge * 10 if reddit_trending else 0) * 0.4
    sentiment_score = max(-100, min(100, sentiment_score))

    if sentiment_score > 20:
        direction = "BULLISH"
    elif sentiment_score < -20:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    parts = []
    if reddit_trending and reddit_rank:
        parts.append(f"Reddit #{reddit_rank}")
    if finnhub_sentiment.get("buzz", 0) > 2:
        parts.append(f"High news buzz")
    if not parts:
        parts.append("Normal activity")

    return {
        "sentiment_score": round(sentiment_score, 1),
        "social_buzz": round(buzz, 1),
        "direction": direction,
        "reddit_trending": reddit_trending,
        "reddit_rank": reddit_rank,
        "mention_surge": round(reddit_surge, 2),
        "summary": " | ".join(parts),
    }


def _get_finnhub_sentiment(ticker: str) -> dict:
    """Get Finnhub news sentiment data."""
    try:
        from data.fetchers.finnhub_fetcher import get_news_sentiment
        data = get_news_sentiment(ticker)
        if data:
            sentiment = data.get("sentiment", {})
            buzz = data.get("buzz", {})
            bull = sentiment.get("bullishPercent", 0.5)
            bear = sentiment.get("bearishPercent", 0.5)
            return {
                "score": (bull - bear) * 100,
                "buzz": buzz.get("buzz", 0),
            }
    except Exception:
        pass
    return {"score": 0, "buzz": 0}


def _get_reddit_data(ticker: str) -> dict:
    """Get Reddit/ApeWisdom social data."""
    try:
        from data.fetchers.reddit_fetcher import get_wsb_trending, get_ticker_social_score
        trending = get_wsb_trending()
        if trending:
            return get_ticker_social_score(ticker, trending)
    except Exception:
        pass
    return {"rank": None, "mentions": 0, "mention_surge": 0, "is_trending": False}
