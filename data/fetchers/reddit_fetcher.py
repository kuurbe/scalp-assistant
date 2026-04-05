"""
Reddit / social sentiment fetcher — WSB trending tickers via Ape Wisdom API.
No authentication required.
"""
from __future__ import annotations
import logging

import requests

from data.cache import cached
from config import settings

logger = logging.getLogger(__name__)

APEWISDOM_URL = "https://apewisdom.io/api/v1.0/filter/all-stocks"


@cached(ttl=settings.REDDIT_CACHE_TTL)
def get_wsb_trending() -> dict[str, dict]:
    """
    Fetch currently trending stock tickers from WallStreetBets
    and related subreddits via the Ape Wisdom API.

    Returns:
        Dict mapping ticker (str) -> {
            rank (int): Position in the trending list (1-based),
            mentions (int): Number of mentions in the last 24h,
            upvotes (int): Total upvotes on mentioning posts,
        }.
        Returns empty dict on failure.
    """
    try:
        resp = requests.get(APEWISDOM_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error("Failed to fetch Ape Wisdom data: %s", e)
        return {}
    except (ValueError, KeyError) as e:
        logger.error("Failed to parse Ape Wisdom response: %s", e)
        return {}

    results_list = data.get("results", [])
    if not results_list:
        logger.warning("Ape Wisdom returned no results")
        return {}

    trending: dict[str, dict] = {}
    for item in results_list:
        ticker = item.get("ticker", "").upper()
        if not ticker:
            continue
        rank = item.get("rank", 0)
        mentions = item.get("mentions", 0)
        upvotes = item.get("upvotes", 0)

        trending[ticker] = {
            "rank": rank,
            "mentions": mentions,
            "upvotes": upvotes,
        }

    return trending


def get_ticker_social_score(ticker: str, trending_data: dict[str, dict] | None = None) -> dict:
    """
    Calculate a social sentiment score for a specific ticker.

    Args:
        ticker: Stock symbol (e.g. "AAPL").
        trending_data: Pre-fetched trending data from get_wsb_trending().
                       If None, will fetch fresh data.

    Returns:
        Dict with:
            rank (int | None): Position in trending list, or None if not trending
            mentions (int): Number of mentions (0 if not found)
            mention_surge (bool): True if ticker is in top 25 by rank
            is_trending (bool): True if ticker appears in the trending data
    """
    if trending_data is None:
        trending_data = get_wsb_trending()

    ticker_upper = ticker.upper()
    entry = trending_data.get(ticker_upper)

    if entry is None:
        return {
            "rank": None,
            "mentions": 0,
            "mention_surge": False,
            "is_trending": False,
        }

    rank = entry.get("rank")
    mentions = entry.get("mentions", 0)

    return {
        "rank": rank,
        "mentions": mentions,
        "mention_surge": rank is not None and rank <= 25,
        "is_trending": True,
    }
