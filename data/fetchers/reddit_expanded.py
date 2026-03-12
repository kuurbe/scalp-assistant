"""
Expanded Reddit fetcher — political, world news, and economic discussions
via Reddit's public JSON API (no authentication required).
"""
import logging
import re
import time
from datetime import datetime, timezone

import requests

from data.cache import cached

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "ScalpAssistant/3.0 (educational trading tool)"}
REQUEST_TIMEOUT = 15

BASE_URL = "https://www.reddit.com"

SUBREDDIT_CONFIGS = {
    "worldnews": 50,
    "politics": 50,
    "economics": 30,
    "geopolitics": 30,
    "stockmarket": 30,
    "investing": 30,
}

SEARCH_URL = f"{BASE_URL}/search.json"

# Score thresholds
MIN_SCORE_HOT = 50
MIN_SCORE_SEARCH = 10

# War / conflict keywords used for search queries
WAR_KEYWORDS = [
    "war",
    "conflict",
    "military",
    "invasion",
    "troops",
    "missile",
    "airstrike",
    "ceasefire",
    "sanctions",
    "NATO",
    "nuclear threat",
]

# Known common tickers to cross-reference against (avoids false positives
# from common English words like "A", "I", "FOR", "THE", etc.)
KNOWN_TICKERS = {
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA",
    "BRK", "JPM", "JNJ", "UNH", "V", "MA", "PG", "HD", "DIS", "BAC",
    "XOM", "CVX", "ABBV", "PFE", "KO", "PEP", "MRK", "COST", "TMO",
    "AVGO", "CSCO", "ACN", "ABT", "DHR", "MCD", "TXN", "NEE", "WMT",
    "LIN", "AMD", "PM", "UPS", "LOW", "HON", "INTC", "COP", "AMGN",
    "IBM", "CAT", "BA", "GE", "GS", "MS", "BLK", "SCHW", "AXP",
    "SPGI", "DE", "NOW", "ISRG", "AMAT", "BKNG", "ADI", "MDLZ",
    "GILD", "LRCX", "REGN", "MMC", "CB", "VRTX", "ZTS", "PYPL",
    "SYK", "CME", "CI", "SO", "DUK", "CL", "BDX", "EQIX", "ITW",
    "MU", "SNPS", "CDNS", "KLAC", "AON", "SHW", "FIS", "ICE",
    "NFLX", "ABNB", "COIN", "RIVN", "LCID", "PLTR", "SOFI", "HOOD",
    "NIO", "BABA", "TSM", "SHOP", "SQ", "ROKU", "SNAP", "PINS",
    "UBER", "LYFT", "DASH", "RBLX", "DKNG", "CRWD", "SNOW", "NET",
    "PANW", "ZS", "OKTA", "DDOG", "MDB", "SMCI", "ARM", "MARA",
    "RIOT", "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "ARKK",
    "XLF", "XLE", "XLK", "XLV", "XLI", "GLD", "SLV", "TLT",
}

# Single-letter tickers that are valid (to avoid filtering out "V", etc.)
VALID_SINGLE_LETTER = {"V", "X", "F"}

# Common English words that look like tickers but are not
TICKER_BLACKLIST = {
    "A", "I", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "HE",
    "IF", "IN", "IS", "IT", "ME", "MY", "NO", "OF", "OK", "ON", "OR",
    "SO", "TO", "UP", "US", "WE", "THE", "AND", "FOR", "ARE", "BUT",
    "NOT", "YOU", "ALL", "ANY", "CAN", "HER", "WAS", "ONE", "OUR",
    "OUT", "HAD", "HAS", "HIS", "HOW", "ITS", "MAY", "NEW", "NOW",
    "OLD", "SEE", "WAY", "WHO", "DID", "GET", "LET", "SAY", "SHE",
    "TOO", "USE", "DAD", "MOM", "WAR", "GDP", "CEO", "IMF", "FED",
    "NATO", "FBI", "CIA", "DOJ", "SEC", "FDA", "EPA", "CDC", "WHO",
    "USA", "UK", "EU", "UN", "GOP", "DEM", "GOP", "RNC", "DNC",
    "CNN", "FOX", "BBC", "NBC", "ABC", "CBS", "NPR", "AP", "WSJ",
    "NYT", "WTF", "OMG", "LOL", "IMO", "TIL", "PSA", "ELI", "AMA",
    "EDIT", "THIS", "THAT", "WITH", "HAVE", "FROM", "THEY", "BEEN",
    "SAID", "EACH", "JUST", "LIKE", "OVER", "SUCH", "THAN", "THEM",
    "VERY", "WHEN", "WHAT", "YOUR", "WILL", "MORE", "SOME", "ONLY",
    "ALSO", "BACK", "LONG", "MUCH", "MOST", "GOOD", "LAST", "HIGH",
}

_TICKER_PATTERN = re.compile(r"\b\$?([A-Z]{1,5})\b")


def _utc_to_readable(utc_ts: float) -> str:
    """Convert a Unix timestamp to a human-readable UTC string."""
    try:
        dt = datetime.fromtimestamp(utc_ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (OSError, ValueError, TypeError):
        return ""


def _extract_tickers(title: str) -> list[str]:
    """
    Extract potential stock ticker symbols from a post title.
    Uses regex to find uppercase words and cross-references against
    the known tickers set while filtering out common English words.
    """
    matches = _TICKER_PATTERN.findall(title.upper())
    tickers = []
    seen = set()
    for match in matches:
        if match in seen:
            continue
        seen.add(match)
        if match in TICKER_BLACKLIST:
            continue
        if len(match) == 1 and match not in VALID_SINGLE_LETTER:
            continue
        if match in KNOWN_TICKERS:
            tickers.append(match)
    return tickers


def _parse_post(post_data: dict) -> dict:
    """Parse a single Reddit post's JSON data into a clean dict."""
    d = post_data.get("data", {})
    return {
        "title": d.get("title", ""),
        "score": d.get("score", 0),
        "num_comments": d.get("num_comments", 0),
        "url": d.get("url", ""),
        "permalink": f"https://www.reddit.com{d.get('permalink', '')}",
        "created_utc": d.get("created_utc", 0),
        "created_readable": _utc_to_readable(d.get("created_utc", 0)),
        "subreddit": d.get("subreddit", ""),
        "upvote_ratio": d.get("upvote_ratio", 0.0),
        "tickers_mentioned": _extract_tickers(d.get("title", "")),
    }


def _fetch_json(url: str, params: dict | None = None) -> dict | None:
    """
    Fetch JSON from a Reddit endpoint with error handling
    and rate-limit awareness.
    """
    try:
        resp = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            logger.warning(
                "Reddit rate limit hit, backing off %ds", retry_after
            )
            time.sleep(min(retry_after, 30))
            resp = requests.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error("Reddit API request failed for %s: %s", url, e)
        return None
    except (ValueError, KeyError) as e:
        logger.error("Failed to parse Reddit JSON from %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@cached(ttl=600)
def get_subreddit_posts(subreddit: str, limit: int = 50) -> list[dict]:
    """
    Fetch hot posts from a subreddit using Reddit's public JSON API.

    Args:
        subreddit: Subreddit name (without r/ prefix).
        limit: Maximum number of posts to fetch (max 100).

    Returns:
        List of post dicts sorted by score descending,
        filtered to score > MIN_SCORE_HOT. Returns empty list on error.
    """
    url = f"{BASE_URL}/r/{subreddit}/hot.json"
    data = _fetch_json(url, params={"limit": min(limit, 100)})
    if data is None:
        return []

    children = data.get("data", {}).get("children", [])
    posts = [_parse_post(child) for child in children]
    posts = [p for p in posts if p["score"] >= MIN_SCORE_HOT]
    posts.sort(key=lambda p: p["score"], reverse=True)
    return posts


@cached(ttl=600)
def get_political_discourse() -> list[dict]:
    """
    Pull hot posts from r/politics and r/worldnews, merged and
    sorted by score descending.

    Returns:
        Combined list of post dicts from political subreddits.
    """
    posts = []
    for sub in ("politics", "worldnews"):
        posts.extend(get_subreddit_posts(sub, limit=50))
    posts.sort(key=lambda p: p["score"], reverse=True)
    return posts


@cached(ttl=600)
def get_war_discussion() -> list[dict]:
    """
    Search for war/conflict-related keywords across Reddit.

    Returns:
        List of post dicts matching war/conflict themes,
        sorted by score descending.
    """
    all_posts = []
    seen_urls = set()

    for keyword in WAR_KEYWORDS:
        results = search_reddit(keyword, limit=25)
        for post in results:
            if post["url"] not in seen_urls:
                seen_urls.add(post["url"])
                all_posts.append(post)

    all_posts.sort(key=lambda p: p["score"], reverse=True)
    return all_posts


@cached(ttl=600)
def get_economic_sentiment() -> list[dict]:
    """
    Pull hot posts from r/economics, r/stockmarket, and r/investing,
    merged and sorted by score descending.

    Returns:
        Combined list of post dicts from economic/financial subreddits.
    """
    posts = []
    for sub, limit in (("economics", 30), ("stockmarket", 30), ("investing", 30)):
        posts.extend(get_subreddit_posts(sub, limit=limit))
    posts.sort(key=lambda p: p["score"], reverse=True)
    return posts


@cached(ttl=600)
def get_trending_topics() -> dict:
    """
    Extract trending topic keywords from top post titles across
    political, economic, and conflict subreddits.

    Returns:
        Dict with keys 'political', 'economic', 'conflict', each
        containing a list of representative topic strings (up to 10 each).
    """
    trending = {
        "political": [],
        "economic": [],
        "conflict": [],
    }

    # Political topics from top posts
    political_posts = get_political_discourse()
    for post in political_posts[:10]:
        title = post.get("title", "")
        if title:
            trending["political"].append(title)

    # Economic topics from top posts
    economic_posts = get_economic_sentiment()
    for post in economic_posts[:10]:
        title = post.get("title", "")
        if title:
            trending["economic"].append(title)

    # Conflict topics from war discussions
    conflict_posts = get_war_discussion()
    for post in conflict_posts[:10]:
        title = post.get("title", "")
        if title:
            trending["conflict"].append(title)

    return trending


@cached(ttl=600)
def search_reddit(query: str, limit: int = 25) -> list[dict]:
    """
    Search Reddit for posts matching a query.

    Args:
        query: Search query string.
        limit: Maximum number of results (max 100).

    Returns:
        List of post dicts sorted by score descending,
        filtered to score > MIN_SCORE_SEARCH. Returns empty list on error.
    """
    data = _fetch_json(
        SEARCH_URL,
        params={"q": query, "sort": "new", "limit": min(limit, 100)},
    )
    if data is None:
        return []

    children = data.get("data", {}).get("children", [])
    posts = [_parse_post(child) for child in children]
    posts = [p for p in posts if p["score"] >= MIN_SCORE_SEARCH]
    posts.sort(key=lambda p: p["score"], reverse=True)
    return posts
