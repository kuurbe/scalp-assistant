"""
Geopolitical / political / war-conflict RSS aggregator.

Aggregates free RSS feeds from Reuters, AP, BBC, Al Jazeera, CNBC, and
Google News custom searches.  All feeds are fetched independently so a
single source failure never crashes the aggregator.
"""
import logging
import ssl
from datetime import datetime
from typing import Optional

import feedparser

from data.cache import cached

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SSL workaround for macOS
# ---------------------------------------------------------------------------
if hasattr(ssl, "_create_unverified_context"):
    ssl._create_default_https_context = ssl._create_unverified_context

# ---------------------------------------------------------------------------
# Feed URLs grouped by category
# ---------------------------------------------------------------------------
POLITICAL_FEEDS: list[tuple[str, str]] = [
    # (url, human-readable source label)
    ("https://feeds.reuters.com/Reuters/politicsNews", "Reuters Politics"),
    (
        "https://search.cnbc.com/rs/search/combinedcms/view.xml"
        "?partnerId=wrss01&id=10000113",
        "CNBC Politics",
    ),
    (
        "https://news.google.com/rss/search"
        "?q=congress+legislation+regulation+policy&hl=en-US",
        "Google News - Policy",
    ),
]

WAR_CONFLICT_FEEDS: list[tuple[str, str]] = [
    (
        "https://news.google.com/rss/search"
        "?q=ukraine+russia+war+conflict&hl=en-US",
        "Google News - Ukraine/Russia",
    ),
    (
        "https://news.google.com/rss/search"
        "?q=middle+east+oil+conflict&hl=en-US",
        "Google News - Middle East",
    ),
    (
        "https://news.google.com/rss/search"
        "?q=china+taiwan+geopolitical&hl=en-US",
        "Google News - China/Taiwan",
    ),
]

TARIFF_TRADE_FEEDS: list[tuple[str, str]] = [
    (
        "https://news.google.com/rss/search"
        "?q=tariff+trade+war+sanctions&hl=en-US",
        "Google News - Tariffs/Trade",
    ),
]

GENERAL_GEO_FEEDS: list[tuple[str, str]] = [
    ("https://feeds.reuters.com/Reuters/worldNews", "Reuters World"),
    ("https://rsshub.app/apnews/topics/apf-topnews", "AP Top News"),
    ("http://feeds.bbci.co.uk/news/world/rss.xml", "BBC World"),
    ("https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_published(entry) -> Optional[str]:
    """Extract a publication date as an ISO-format string."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6]).isoformat()
        except (TypeError, ValueError):
            pass
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            return datetime(*entry.updated_parsed[:6]).isoformat()
        except (TypeError, ValueError):
            pass
    # Fall back to the raw string if present
    return entry.get("published") or entry.get("updated")


def _fetch_feed(url: str, source_label: str, category: str) -> list[dict]:
    """Parse a single RSS feed, returning normalised article dicts.

    Never raises; returns an empty list on any failure.
    """
    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            logger.debug(
                "feedparser error for %s (%s): %s",
                source_label,
                url,
                feed.bozo_exception,
            )
            return []

        articles: list[dict] = []
        for entry in feed.entries:
            articles.append(
                {
                    "headline": entry.get("title", "").strip(),
                    "summary": (entry.get("summary") or "").strip(),
                    "source": source_label,
                    "published": _parse_published(entry),
                    "url": entry.get("link", ""),
                    "category": category,
                }
            )
        return articles

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "RSS feed fetch failed for %s (%s): %s", source_label, url, exc
        )
        return []


def _aggregate_feeds(
    feeds: list[tuple[str, str]],
    category: str,
    max_items: int,
) -> list[dict]:
    """Fetch *feeds* in sequence, merge results, and trim to *max_items*."""
    all_articles: list[dict] = []
    for url, label in feeds:
        all_articles.extend(_fetch_feed(url, label, category))
    # Sort newest-first (entries without a date sink to the bottom)
    all_articles.sort(key=lambda a: a.get("published") or "", reverse=True)
    return all_articles[:max_items]


def _deduplicate(articles: list[dict]) -> list[dict]:
    """Remove near-duplicate headlines (first 60 lower-cased chars)."""
    seen: set[str] = set()
    unique: list[dict] = []
    for article in articles:
        key = article["headline"][:60].lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(article)
    return unique


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@cached(ttl=300)
def get_political_news(max_items: int = 50) -> list[dict]:
    """Aggregate political RSS feeds.

    Returns:
        List of dicts with keys: headline, summary, source, published, url,
        category (always ``"POLITICS"``).
    """
    return _aggregate_feeds(POLITICAL_FEEDS, "POLITICS", max_items)


@cached(ttl=300)
def get_war_conflict_news(max_items: int = 50) -> list[dict]:
    """Aggregate war / conflict RSS feeds.

    Returns:
        List of dicts with keys: headline, summary, source, published, url,
        category (always ``"WAR_CONFLICT"``).
    """
    return _aggregate_feeds(WAR_CONFLICT_FEEDS, "WAR_CONFLICT", max_items)


@cached(ttl=300)
def get_tariff_trade_news(max_items: int = 30) -> list[dict]:
    """Aggregate tariff / trade / sanctions RSS feeds.

    Returns:
        List of dicts with keys: headline, summary, source, published, url,
        category (always ``"TARIFF_TRADE"``).
    """
    return _aggregate_feeds(TARIFF_TRADE_FEEDS, "TARIFF_TRADE", max_items)


@cached(ttl=300)
def get_geopolitical_news(max_items: int = 100) -> list[dict]:
    """Merge **all** geopolitical feeds, deduplicate, and sort by recency.

    Combines political, war/conflict, tariff/trade, and general world-news
    feeds into a single stream.

    Returns:
        Deduplicated list of dicts sorted newest-first, trimmed to
        *max_items*.
    """
    all_articles: list[dict] = []

    # Political feeds
    for url, label in POLITICAL_FEEDS:
        all_articles.extend(_fetch_feed(url, label, "POLITICS"))

    # War / conflict feeds
    for url, label in WAR_CONFLICT_FEEDS:
        all_articles.extend(_fetch_feed(url, label, "WAR_CONFLICT"))

    # Tariff / trade feeds
    for url, label in TARIFF_TRADE_FEEDS:
        all_articles.extend(_fetch_feed(url, label, "TARIFF_TRADE"))

    # General world-news feeds
    for url, label in GENERAL_GEO_FEEDS:
        all_articles.extend(_fetch_feed(url, label, "GEOPOLITICAL"))

    # Deduplicate and sort
    all_articles = _deduplicate(all_articles)
    all_articles.sort(key=lambda a: a.get("published") or "", reverse=True)

    return all_articles[:max_items]
