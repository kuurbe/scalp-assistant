"""
RSS news fetcher — Yahoo Finance RSS feeds via feedparser.
"""
import logging
from datetime import datetime

import ssl
import feedparser

from data.cache import cached
from config import settings

logger = logging.getLogger(__name__)

# Fix SSL certificate issues on macOS
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

YAHOO_RSS_TICKER_URL = (
    "https://feeds.finance.yahoo.com/rss/2.0/headline"
    "?s={ticker}&region=US&lang=en-US"
)
YAHOO_RSS_MARKET_URL = (
    "https://feeds.finance.yahoo.com/rss/2.0/headline"
    "?s=^GSPC,^DJI,^IXIC&region=US&lang=en-US"
)


def _parse_feed(url: str) -> list[dict]:
    """
    Parse an RSS feed URL and return a list of article dicts.

    Returns:
        List of dicts with title, published, link, summary.
    """
    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            logger.warning("feedparser error for %s: %s", url, feed.bozo_exception)
            return []

        results = []
        for entry in feed.entries:
            # Parse publication date into ISO format
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6]).isoformat()
                except (TypeError, ValueError):
                    published = entry.get("published")
            elif hasattr(entry, "published"):
                published = entry.published

            results.append({
                "title": entry.get("title", ""),
                "published": published,
                "link": entry.get("link", ""),
                "summary": entry.get("summary", ""),
            })
        return results
    except Exception as e:
        logger.error("RSS feed parsing failed for %s: %s", url, e)
        return []


@cached(ttl=settings.NEWS_CACHE_TTL)
def get_yahoo_rss_news(ticker: str) -> list[dict]:
    """
    Fetch Yahoo Finance RSS news for a specific ticker.

    Args:
        ticker: Stock symbol (e.g. "AAPL").

    Returns:
        List of dicts with title, published, link, summary.
    """
    url = YAHOO_RSS_TICKER_URL.format(ticker=ticker)
    return _parse_feed(url)


@cached(ttl=settings.NEWS_CACHE_TTL)
def get_market_rss_news() -> list[dict]:
    """
    Fetch Yahoo Finance RSS news for major market indices.

    Returns:
        List of dicts with title, published, link, summary.
    """
    return _parse_feed(YAHOO_RSS_MARKET_URL)
