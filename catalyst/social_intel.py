"""
Social Intelligence Aggregator -- unified social signal feed.

Merges X/Twitter-related signals (via news coverage), Stocktwits, Reddit,
and geopolitical news into a single social intel dict.  Because the X/Twitter
API costs $200/month, we track X conversations indirectly through:

  - News articles that quote or reference tweets
  - Stocktwits (free proxy for trading-focused social)
  - Reddit discussions (ApeWisdom + expanded Reddit, when available)

All public functions are cached (TTL 300 s) and fail gracefully so that a
single source outage never crashes the aggregator.
"""

import logging
import re
from typing import Optional

from data.cache import cached

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy / try-imports for modules that may not exist yet
# ---------------------------------------------------------------------------

# -- Stocktwits (already exists) --
try:
    from data.fetchers.stocktwits_fetcher import (
        get_stocktwits_sentiment,
        get_stocktwits_messages,
        get_social_buzz as _st_social_buzz,
    )
    _HAS_STOCKTWITS = True
except ImportError:
    _HAS_STOCKTWITS = False

# -- Reddit (basic, already exists) --
try:
    from data.fetchers.reddit_fetcher import (
        get_wsb_trending,
        get_ticker_social_score,
    )
    _HAS_REDDIT = True
except ImportError:
    _HAS_REDDIT = False

# -- Reddit expanded (may not exist yet) --
try:
    from data.fetchers.reddit_expanded import (
        get_subreddit_mentions,
        get_reddit_sentiment,
    )
    _HAS_REDDIT_EXPANDED = True
except ImportError:
    _HAS_REDDIT_EXPANDED = False

# -- Geopolitical RSS (already exists) --
try:
    from data.fetchers.geopolitical_rss import (
        get_political_news,
        get_war_conflict_news,
        get_geopolitical_news,
    )
    _HAS_GEO = True
except ImportError:
    _HAS_GEO = False

# -- News aggregator (existing catalyst module) --
try:
    from catalyst.news_aggregator import aggregate_news, get_market_catalysts
    _HAS_NEWS_AGG = True
except ImportError:
    _HAS_NEWS_AGG = False

# ---------------------------------------------------------------------------
# Known market-relevant influencers (lowercase handles/names)
# ---------------------------------------------------------------------------
KNOWN_INFLUENCERS: list[dict] = [
    {"handle": "elonmusk", "name": "Elon Musk", "platform": "X"},
    {"handle": "realdonaldtrump", "name": "Donald Trump", "platform": "Truth Social"},
    {"handle": "potus", "name": "POTUS", "platform": "X"},
    {"handle": "jimcramer", "name": "Jim Cramer", "platform": "X"},
    {"handle": "cathiewood", "name": "Cathie Wood", "platform": "X"},
    {"handle": "chaaborz", "name": "Chamath Palihapitiya", "platform": "X"},
    {"handle": "markminervini", "name": "Mark Minervini", "platform": "X"},
    {"handle": "citaborz", "name": "Citron Research", "platform": "X"},
    {"handle": "hindaborz", "name": "Hindenburg Research", "platform": "X"},
    {"handle": "muddywaters", "name": "Muddy Waters", "platform": "X"},
    {"handle": "klogg", "name": "Keith Gill (DFV)", "platform": "X"},
    {"handle": "wallstreetbets", "name": "WallStreetBets", "platform": "Reddit"},
]

# Patterns that indicate an article is referencing a tweet or social media post
_X_MENTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"\btweeted\b", re.IGNORECASE),
    re.compile(r"\btweet\b", re.IGNORECASE),
    re.compile(r"\bposted on X\b", re.IGNORECASE),
    re.compile(r"\bsaid on Twitter\b", re.IGNORECASE),
    re.compile(r"\bsaid on X\b", re.IGNORECASE),
    re.compile(r"\bTruth Social\b", re.IGNORECASE),
    re.compile(r"\bsocial media post\b", re.IGNORECASE),
    re.compile(r"\bsocial media\b", re.IGNORECASE),
    re.compile(r"@\w{1,30}", re.IGNORECASE),  # @username references
    re.compile(r"\bX post\b", re.IGNORECASE),
    re.compile(r"\bTwitter post\b", re.IGNORECASE),
    re.compile(r"\bwrote on X\b", re.IGNORECASE),
    re.compile(r"\bwrote on Twitter\b", re.IGNORECASE),
    re.compile(r"\bon his (Truth Social|X|Twitter)\b", re.IGNORECASE),
    re.compile(r"\bon her (Truth Social|X|Twitter)\b", re.IGNORECASE),
]

# Pattern to extract @usernames from text
_USERNAME_PATTERN = re.compile(r"@(\w{1,30})")

# Political / market-moving keyword lists for relevance scoring
_POLITICAL_MARKET_KEYWORDS = [
    "tariff", "trade war", "sanctions", "fed ", "federal reserve",
    "interest rate", "regulation", "antitrust", "tax", "stimulus",
    "debt ceiling", "shutdown", "congress", "executive order",
    "sec ", "ftc ", "doj ", "ban", "restrict", "subsid",
]

_WAR_MARKET_KEYWORDS = [
    "oil", "crude", "energy", "supply chain", "shipping",
    "semiconductor", "chip", "defense", "military", "nato",
    "sanctions", "embargo", "nuclear", "missile", "drone",
    "strait", "pipeline", "rare earth", "commodity",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_text(item: dict) -> str:
    """Combine headline + summary into a searchable text blob."""
    headline = item.get("headline") or item.get("title") or ""
    summary = item.get("summary") or ""
    return f"{headline} {summary}".strip()


def _detect_platform(text: str) -> str:
    """Determine which social platform is referenced in *text*."""
    text_lower = text.lower()
    if "truth social" in text_lower:
        return "Truth Social"
    if "posted on x" in text_lower or "said on x" in text_lower or "wrote on x" in text_lower or "x post" in text_lower:
        return "X"
    if "twitter" in text_lower or "tweeted" in text_lower or "tweet" in text_lower:
        return "X/Twitter"
    if "@" in text:
        return "X/Twitter"
    return "social media"


def _extract_usernames(text: str) -> list[str]:
    """Pull all @username references from *text*."""
    return _USERNAME_PATTERN.findall(text)


def _keyword_relevance(text: str, keywords: list[str]) -> float:
    """Return 0-1 relevance score based on keyword density."""
    if not text:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw in text_lower)
    return min(1.0, hits / max(1, len(keywords) * 0.15))


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def extract_x_mentions(news_items: list[dict]) -> list[dict]:
    """Scan news headlines/summaries for references to tweets or X/social posts.

    Looks for patterns such as "tweeted", "posted on X", "said on Twitter",
    "Truth Social", "social media post", and ``@username`` references.

    Args:
        news_items: List of news dicts (must have ``headline`` or ``title``
            and optionally ``summary``, ``url``, ``source``).

    Returns:
        List of dicts, each containing::

            {
                "user":           str or None,   # @handle if found
                "content_hint":   str,            # headline text
                "source_article": str,            # article URL
                "platform":       str,            # "X", "Truth Social", etc.
                "source":         str,            # news source label
            }
    """
    mentions: list[dict] = []
    seen_headlines: set[str] = set()

    for item in (news_items or []):
        text = _safe_text(item)
        if not text:
            continue

        # Dedup by headline prefix
        dedup_key = text[:80].lower()
        if dedup_key in seen_headlines:
            continue

        # Check if any X-mention pattern matches
        matched = any(pat.search(text) for pat in _X_MENTION_PATTERNS)
        if not matched:
            continue

        seen_headlines.add(dedup_key)

        # Try to extract a username
        usernames = _extract_usernames(text)
        user = usernames[0] if usernames else None

        headline = item.get("headline") or item.get("title") or text[:120]

        mentions.append({
            "user": user,
            "content_hint": headline[:200],
            "source_article": item.get("url", ""),
            "platform": _detect_platform(text),
            "source": item.get("source", "unknown"),
        })

    return mentions


def compute_social_score(
    stocktwits_data: dict,
    reddit_data: dict,
    x_mentions: list,
    political: list,
    war: list,
) -> float:
    """Compute a weighted 0-100 composite social score.

    Weights:
      - 30%  Stocktwits sentiment intensity
      - 25%  Reddit buzz / trending
      - 20%  X mention volume via news
      - 15%  Political catalyst relevance
      - 10%  War/conflict market impact

    Args:
        stocktwits_data: Dict from ``get_stocktwits_sentiment`` or similar.
        reddit_data:     Dict from ``get_ticker_social_score`` or similar.
        x_mentions:      List of X-mention dicts from ``extract_x_mentions``.
        political:       List of political news items.
        war:             List of war/conflict news items.

    Returns:
        Float between 0 and 100.
    """
    # -- Stocktwits (30%) --
    # Use absolute sentiment score (0-100) + message volume signal
    st_sentiment = abs(stocktwits_data.get("sentiment_score", 0))  # 0-100
    st_volume = min(30, stocktwits_data.get("total_messages", 0))  # cap at 30
    st_trending_bonus = 20 if stocktwits_data.get("trending", False) else 0
    stocktwits_component = min(100, st_sentiment + (st_volume / 30) * 20 + st_trending_bonus)

    # -- Reddit (25%) --
    reddit_rank = reddit_data.get("rank")
    reddit_mentions = reddit_data.get("mentions", 0)
    reddit_trending = reddit_data.get("is_trending", False)

    reddit_component = 0.0
    if reddit_trending and reddit_rank is not None:
        # Higher rank = lower number = more buzz
        reddit_component = max(0, 100 - (reddit_rank - 1) * 3)
    elif reddit_mentions > 0:
        reddit_component = min(60, reddit_mentions * 2)

    # -- X mentions from news (20%) --
    x_count = len(x_mentions) if x_mentions else 0
    # Each mention is worth ~15 points, capped at 100
    x_component = min(100, x_count * 15)

    # -- Political catalyst (15%) --
    if political:
        # Score based on volume + market keyword relevance
        relevance_scores = [
            _keyword_relevance(_safe_text(item), _POLITICAL_MARKET_KEYWORDS)
            for item in political[:20]
        ]
        avg_relevance = sum(relevance_scores) / max(1, len(relevance_scores))
        volume_factor = min(1.0, len(political) / 10.0)
        political_component = min(100, (avg_relevance * 60 + volume_factor * 40))
    else:
        political_component = 0.0

    # -- War/conflict (10%) --
    if war:
        relevance_scores = [
            _keyword_relevance(_safe_text(item), _WAR_MARKET_KEYWORDS)
            for item in war[:20]
        ]
        avg_relevance = sum(relevance_scores) / max(1, len(relevance_scores))
        volume_factor = min(1.0, len(war) / 10.0)
        war_component = min(100, (avg_relevance * 60 + volume_factor * 40))
    else:
        war_component = 0.0

    # Weighted sum
    score = (
        stocktwits_component * 0.30
        + reddit_component * 0.25
        + x_component * 0.20
        + political_component * 0.15
        + war_component * 0.10
    )

    return round(min(100.0, max(0.0, score)), 1)


def _detect_influencer_mentions(news_items: list[dict]) -> list[dict]:
    """Scan news for mentions of known market influencers.

    Returns list of dicts: {name, handle, platform, headline, source, url}.
    """
    results: list[dict] = []
    seen: set[str] = set()

    for item in (news_items or []):
        text = _safe_text(item).lower()
        if not text:
            continue

        for influencer in KNOWN_INFLUENCERS:
            name_lower = influencer["name"].lower()
            handle_lower = influencer["handle"].lower()

            if name_lower in text or f"@{handle_lower}" in text:
                dedup_key = f"{influencer['handle']}:{item.get('url', '')}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                headline = item.get("headline") or item.get("title") or ""
                results.append({
                    "name": influencer["name"],
                    "handle": influencer["handle"],
                    "platform": influencer["platform"],
                    "headline": headline[:200],
                    "source": item.get("source", "unknown"),
                    "url": item.get("url", ""),
                })

    return results


def _fetch_stocktwits_data(ticker: Optional[str]) -> dict:
    """Safely fetch Stocktwits data for a ticker."""
    if not _HAS_STOCKTWITS or not ticker:
        return {
            "sentiment_score": 0.0,
            "bullish_pct": 0.0,
            "bearish_pct": 0.0,
            "total_messages": 0,
            "trending": False,
            "messages": [],
        }
    try:
        sentiment = get_stocktwits_sentiment(ticker)
        messages = get_stocktwits_messages(ticker, limit=20)
        return {
            **sentiment,
            "messages": messages,
        }
    except Exception as exc:
        logger.error("Stocktwits fetch failed for %s: %s", ticker, exc)
        return {
            "sentiment_score": 0.0,
            "bullish_pct": 0.0,
            "bearish_pct": 0.0,
            "total_messages": 0,
            "trending": False,
            "messages": [],
        }


def _fetch_reddit_data(ticker: Optional[str]) -> dict:
    """Safely fetch Reddit data for a ticker."""
    default = {
        "rank": None,
        "mentions": 0,
        "mention_surge": False,
        "is_trending": False,
        "expanded": {},
    }

    if not ticker:
        return default

    # Basic Reddit data
    if _HAS_REDDIT:
        try:
            trending = get_wsb_trending()
            reddit_basic = get_ticker_social_score(ticker, trending)
            default.update(reddit_basic)
        except Exception as exc:
            logger.error("Reddit basic fetch failed for %s: %s", ticker, exc)

    # Expanded Reddit data (if module exists)
    if _HAS_REDDIT_EXPANDED:
        try:
            expanded = get_reddit_sentiment(ticker)
            default["expanded"] = expanded or {}
        except Exception as exc:
            logger.error("Reddit expanded fetch failed for %s: %s", ticker, exc)

    return default


def _fetch_political_news() -> list[dict]:
    """Safely fetch political news."""
    if not _HAS_GEO:
        return []
    try:
        return get_political_news(max_items=30) or []
    except Exception as exc:
        logger.error("Political news fetch failed: %s", exc)
        return []


def _fetch_war_news() -> list[dict]:
    """Safely fetch war/conflict news."""
    if not _HAS_GEO:
        return []
    try:
        return get_war_conflict_news(max_items=30) or []
    except Exception as exc:
        logger.error("War/conflict news fetch failed: %s", exc)
        return []


def _fetch_all_news(ticker: Optional[str]) -> list[dict]:
    """Fetch all available news for X-mention scanning."""
    all_news: list[dict] = []

    # Ticker-specific news
    if _HAS_NEWS_AGG and ticker:
        try:
            ticker_news = aggregate_news(ticker, max_age_hours=24)
            if ticker_news:
                all_news.extend(ticker_news)
        except Exception as exc:
            logger.error("News aggregation failed for %s: %s", ticker, exc)

    # Market-wide news
    if _HAS_NEWS_AGG:
        try:
            market_news = get_market_catalysts(max_age_hours=12)
            if market_news:
                all_news.extend(market_news)
        except Exception as exc:
            logger.error("Market catalyst news failed: %s", exc)

    # Geopolitical news (all categories)
    if _HAS_GEO:
        try:
            geo_news = get_geopolitical_news(max_items=50)
            if geo_news:
                all_news.extend(geo_news)
        except Exception as exc:
            logger.error("Geopolitical news failed: %s", exc)

    return all_news


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@cached(ttl=300)
def get_social_narrative(ticker: str = None) -> str:
    """Build a human-readable 1-2 sentence narrative of social trends.

    Example output::

        "X buzzing about NVDA earnings beat; Reddit WSB bullish;
         political tension rising over China tariffs"

    Args:
        ticker: Optional stock symbol to focus the narrative on.

    Returns:
        A short (1-2 sentence) narrative string.
    """
    parts: list[str] = []

    # Stocktwits signal
    if _HAS_STOCKTWITS and ticker:
        try:
            st = get_stocktwits_sentiment(ticker)
            if st.get("total_messages", 0) > 0:
                direction = "bullish" if st.get("sentiment_score", 0) > 10 else (
                    "bearish" if st.get("sentiment_score", 0) < -10 else "mixed"
                )
                trending_tag = " (trending)" if st.get("trending") else ""
                parts.append(f"Stocktwits {direction} on {ticker}{trending_tag}")
        except Exception:
            pass

    # Reddit signal
    if _HAS_REDDIT and ticker:
        try:
            trending = get_wsb_trending()
            rd = get_ticker_social_score(ticker, trending)
            if rd.get("is_trending"):
                rank = rd.get("rank", "?")
                parts.append(f"Reddit WSB #{rank}")
        except Exception:
            pass

    # X/tweet mentions from news
    all_news = _fetch_all_news(ticker)
    x_mentions = extract_x_mentions(all_news)
    if x_mentions:
        # Summarise most notable mention
        first = x_mentions[0]
        user_tag = f"@{first['user']}" if first.get("user") else first.get("platform", "X")
        hint = first.get("content_hint", "")[:60]
        parts.append(f"X buzz via {user_tag}: {hint}")

    # Political pulse
    political = _fetch_political_news()
    if political:
        top = political[0]
        headline = (top.get("headline") or "")[:50]
        relevance = _keyword_relevance(_safe_text(top), _POLITICAL_MARKET_KEYWORDS)
        if relevance > 0.1:
            parts.append(f"political tension: {headline}")

    # War/conflict
    war = _fetch_war_news()
    if war:
        top = war[0]
        headline = (top.get("headline") or "")[:50]
        relevance = _keyword_relevance(_safe_text(top), _WAR_MARKET_KEYWORDS)
        if relevance > 0.1:
            parts.append(f"conflict watch: {headline}")

    if not parts:
        return "No notable social signals detected" + (f" for {ticker}" if ticker else "")

    return "; ".join(parts)


@cached(ttl=300)
def get_social_intel(ticker: str = None) -> dict:
    """Main entry point -- unified social intelligence feed.

    Aggregates X/Twitter references from news coverage, Stocktwits sentiment,
    Reddit buzz, political news, and war/conflict news into a single dict.

    Args:
        ticker: Optional stock symbol (e.g. ``"AAPL"``).  When provided,
            ticker-specific signals are included alongside market-wide data.

    Returns:
        Dict with keys::

            x_mentions:         list[dict]  -- tweet references from news
            stocktwits:         dict        -- ST sentiment + messages
            reddit_buzz:        dict        -- Reddit mentions
            political_pulse:    list[dict]  -- political news affecting markets
            war_watch:          list[dict]  -- conflict news affecting markets
            influencer_signals: list[dict]  -- known influencer mentions
            social_score:       float       -- 0-100 composite score
            narrative:          str         -- 1-2 sentence summary
    """
    # 1. Gather all news for X-mention extraction
    all_news = _fetch_all_news(ticker)

    # 2. Extract X/Twitter mentions from news
    x_mentions = extract_x_mentions(all_news)

    # 3. Stocktwits data
    stocktwits_data = _fetch_stocktwits_data(ticker)

    # 4. Reddit data
    reddit_data = _fetch_reddit_data(ticker)

    # 5. Political news
    political = _fetch_political_news()

    # 6. War/conflict news
    war = _fetch_war_news()

    # 7. Influencer signals from all news
    influencer_signals = _detect_influencer_mentions(all_news)

    # 8. Composite social score
    social_score = compute_social_score(
        stocktwits_data=stocktwits_data,
        reddit_data=reddit_data,
        x_mentions=x_mentions,
        political=political,
        war=war,
    )

    # 9. Narrative summary
    narrative = get_social_narrative(ticker)

    return {
        "x_mentions": x_mentions,
        "stocktwits": stocktwits_data,
        "reddit_buzz": reddit_data,
        "political_pulse": political,
        "war_watch": war,
        "influencer_signals": influencer_signals,
        "social_score": social_score,
        "narrative": narrative,
    }
