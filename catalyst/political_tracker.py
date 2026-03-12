"""
Tracks political movements and their market impact.

Classifies political events into market-relevant categories using a
keyword taxonomy and assesses potential market direction.  Aggregates
signals from geopolitical RSS feeds and Reddit political discourse to
produce a unified political-risk pulse.
"""
import logging
from collections import Counter

from data.cache import cached

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional data-source imports (never fatal)
# ---------------------------------------------------------------------------
try:
    from data.fetchers.geopolitical_rss import (
        get_geopolitical_news,
        get_political_news,
        get_tariff_trade_news,
    )
except ImportError:
    get_geopolitical_news = None
    get_political_news = None
    get_tariff_trade_news = None

try:
    from data.fetchers.reddit_expanded import (
        get_political_discourse,
        get_economic_sentiment,
    )
except ImportError:
    get_political_discourse = None
    get_economic_sentiment = None

# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

POLITICAL_TAXONOMY = {
    "TARIFF_TRADE": {
        "keywords": [
            "tariff", "trade war", "sanctions", "embargo", "import duty",
            "export ban", "trade deal", "trade agreement", "wto", "nafta",
            "usmca",
        ],
        "affected_sectors": ["XLE", "XLI", "EEM", "FXI"],
        "base_impact": 80,
    },
    "REGULATION": {
        "keywords": [
            "regulation", "deregulation", "antitrust", "ftc", "sec rule",
            "dodd-frank", "legislation", "bill passed", "executive order",
            "ban",
        ],
        "affected_sectors": ["XLF", "XLK", "XLC"],
        "base_impact": 70,
    },
    "TAX_POLICY": {
        "keywords": [
            "tax cut", "tax hike", "corporate tax", "capital gains",
            "tax reform", "irs", "tax credit",
        ],
        "affected_sectors": ["SPY", "QQQ", "XLF"],
        "base_impact": 75,
    },
    "FED_MONETARY": {
        "keywords": [
            "fed", "fomc", "rate hike", "rate cut", "dovish", "hawkish",
            "quantitative", "taper", "powell", "yellen", "treasury secretary",
        ],
        "affected_sectors": ["XLF", "TLT", "GLD", "SPY"],
        "base_impact": 90,
    },
    "ELECTION": {
        "keywords": [
            "election", "poll", "candidate", "campaign", "vote", "ballot",
            "inauguration", "president", "congress", "senate", "house",
        ],
        "affected_sectors": ["SPY", "XLF", "XLV"],
        "base_impact": 65,
    },
    "GEOPOLITICAL_TENSION": {
        "keywords": [
            "nato", "alliance", "diplomatic", "summit", "treaty",
            "territorial", "sovereignty", "military buildup",
        ],
        "affected_sectors": ["XLE", "GLD", "XLI"],
        "base_impact": 70,
    },
    "CRYPTO_REGULATION": {
        "keywords": [
            "crypto regulation", "bitcoin ban", "stablecoin", "cbdc",
            "digital currency", "crypto executive order", "sec crypto",
        ],
        "affected_sectors": ["COIN", "MSTR", "MARA", "RIOT"],
        "base_impact": 75,
    },
}

# ---------------------------------------------------------------------------
# Direction keyword lists
# ---------------------------------------------------------------------------

BULLISH_SIGNALS = [
    "deregulation", "tax cut", "tax credit", "rate cut", "dovish",
    "trade deal", "trade agreement", "stimulus", "infrastructure",
    "bipartisan", "ceasefire", "peace", "de-escalation", "easing",
    "approval", "positive", "growth", "rally", "surge", "support",
    "pro-business", "incentive", "subsidy", "relief",
]

BEARISH_SIGNALS = [
    "tariff increase", "tariff hike", "trade war", "sanctions",
    "embargo", "export ban", "rate hike", "hawkish", "taper",
    "antitrust", "crackdown", "ban", "restriction", "shutdown",
    "impeachment", "investigation", "indictment", "default",
    "escalation", "invasion", "conflict", "war", "missile",
    "nuclear", "threat", "crash", "recession", "downgrade",
    "tax hike", "regulation", "bitcoin ban",
]

# Context-aware direction overrides: (keyword, direction, applies_to_types)
DIRECTIONAL_OVERRIDES = [
    # Tariff increase is bearish for importers / trade-sensitive sectors
    ("tariff increase", "BEARISH", {"TARIFF_TRADE"}),
    ("tariff hike", "BEARISH", {"TARIFF_TRADE"}),
    ("import duty", "BEARISH", {"TARIFF_TRADE"}),
    # Deregulation is bullish for the regulated sector
    ("deregulation", "BULLISH", {"REGULATION"}),
    # Rate cut is bullish for growth / tech
    ("rate cut", "BULLISH", {"FED_MONETARY"}),
    ("dovish", "BULLISH", {"FED_MONETARY"}),
    # Rate hike is bearish for growth / equities
    ("rate hike", "BEARISH", {"FED_MONETARY"}),
    ("hawkish", "BEARISH", {"FED_MONETARY"}),
    # Tax cut is bullish broadly
    ("tax cut", "BULLISH", {"TAX_POLICY"}),
    ("tax credit", "BULLISH", {"TAX_POLICY"}),
    # Tax hike is bearish
    ("tax hike", "BEARISH", {"TAX_POLICY"}),
    # Trade deal is bullish for trade-affected sectors
    ("trade deal", "BULLISH", {"TARIFF_TRADE"}),
    ("trade agreement", "BULLISH", {"TARIFF_TRADE"}),
    # Crypto ban is bearish for crypto
    ("bitcoin ban", "BEARISH", {"CRYPTO_REGULATION"}),
    ("crypto regulation", "BEARISH", {"CRYPTO_REGULATION"}),
]


# ---------------------------------------------------------------------------
# classify_political_event
# ---------------------------------------------------------------------------

def classify_political_event(headline: str, summary: str = "") -> dict:
    """
    Classify a political headline (and optional summary) into a market-
    relevant category with direction and impact score.

    Returns:
        {
            "type": str,              # e.g. "TARIFF_TRADE"
            "affected_sectors": list,  # e.g. ["XLE", "XLI", ...]
            "direction": str,          # BULLISH / BEARISH / NEUTRAL
            "impact_score": int,       # 0-100
            "confidence": float,       # 0.0-1.0
        }
    """
    if not headline:
        return {
            "type": "UNKNOWN",
            "affected_sectors": [],
            "direction": "NEUTRAL",
            "impact_score": 0,
            "confidence": 0.0,
        }

    text = f"{headline} {summary}".lower()

    # --- match taxonomy -------------------------------------------------
    best_type = "UNKNOWN"
    best_match_count = 0
    best_info = None

    for cat_type, info in POLITICAL_TAXONOMY.items():
        matches = sum(1 for kw in info["keywords"] if kw in text)
        if matches > best_match_count:
            best_match_count = matches
            best_type = cat_type
            best_info = info

    affected_sectors = best_info["affected_sectors"] if best_info else []
    base_impact = best_info["base_impact"] if best_info else 0

    # --- direction detection --------------------------------------------
    # First try context-aware overrides
    direction = None
    for keyword, dir_value, applicable_types in DIRECTIONAL_OVERRIDES:
        if keyword in text and best_type in applicable_types:
            direction = dir_value
            break

    # Fall back to generic signal counting
    if direction is None:
        bull_count = sum(1 for kw in BULLISH_SIGNALS if kw in text)
        bear_count = sum(1 for kw in BEARISH_SIGNALS if kw in text)

        if bull_count > bear_count:
            direction = "BULLISH"
        elif bear_count > bull_count:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

    # --- confidence & impact --------------------------------------------
    confidence = min(1.0, best_match_count / 3.0) if best_match_count > 0 else 0.0
    impact_score = min(100, round(base_impact * (0.5 + 0.5 * confidence)))

    return {
        "type": best_type,
        "affected_sectors": affected_sectors,
        "direction": direction,
        "impact_score": impact_score,
        "confidence": round(confidence, 2),
    }


# ---------------------------------------------------------------------------
# get_political_pulse
# ---------------------------------------------------------------------------

@cached(ttl=300)
def get_political_pulse() -> dict:
    """
    Aggregate recent political news from RSS feeds and Reddit, classify
    each event, and return a market-oriented political pulse.

    Returns:
        {
            "events": list[dict],
            "dominant_theme": str,
            "market_direction": str,
            "affected_tickers": list[str],
            "risk_level": str,
            "summary": str,
        }
    """
    raw_articles = _fetch_all_political_news()

    if not raw_articles:
        return {
            "events": [],
            "dominant_theme": "NONE",
            "market_direction": "NEUTRAL",
            "affected_tickers": [],
            "risk_level": "LOW",
            "summary": "No political signals detected",
        }

    # Classify every article
    events = []
    for article in raw_articles:
        classification = classify_political_event(
            article.get("headline") or article.get("title", ""),
            article.get("summary", ""),
        )
        if classification["type"] == "UNKNOWN":
            continue
        events.append({
            **classification,
            "headline": article.get("headline") or article.get("title", ""),
            "source": article.get("source", ""),
            "published": article.get("published", ""),
        })

    if not events:
        return {
            "events": [],
            "dominant_theme": "NONE",
            "market_direction": "NEUTRAL",
            "affected_tickers": [],
            "risk_level": "LOW",
            "summary": "No classified political events",
        }

    # --- dominant theme -------------------------------------------------
    type_counts = Counter(e["type"] for e in events)
    dominant_theme = type_counts.most_common(1)[0][0]

    # --- aggregate market direction -------------------------------------
    bull = sum(1 for e in events if e["direction"] == "BULLISH")
    bear = sum(1 for e in events if e["direction"] == "BEARISH")
    if bull > bear * 1.25:
        market_direction = "BULLISH"
    elif bear > bull * 1.25:
        market_direction = "BEARISH"
    else:
        market_direction = "NEUTRAL"

    # --- affected tickers -----------------------------------------------
    ticker_counts: Counter = Counter()
    for e in events:
        for t in e.get("affected_sectors", []):
            ticker_counts[t] += 1
    affected_tickers = [t for t, _ in ticker_counts.most_common(10)]

    # --- risk level -----------------------------------------------------
    avg_impact = sum(e["impact_score"] for e in events) / len(events)
    high_impact_count = sum(1 for e in events if e["impact_score"] >= 75)
    if avg_impact >= 80 or high_impact_count >= 5:
        risk_level = "EXTREME"
    elif avg_impact >= 65 or high_impact_count >= 3:
        risk_level = "HIGH"
    elif avg_impact >= 45 or high_impact_count >= 1:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    # --- summary --------------------------------------------------------
    summary = _build_pulse_summary(
        dominant_theme, market_direction, risk_level, len(events),
    )

    return {
        "events": events,
        "dominant_theme": dominant_theme,
        "market_direction": market_direction,
        "affected_tickers": affected_tickers,
        "risk_level": risk_level,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# get_ticker_political_exposure
# ---------------------------------------------------------------------------

def get_ticker_political_exposure(
    ticker: str,
    political_events: list,
) -> float:
    """
    Compute a 0-100 score representing how exposed *ticker* is to the
    supplied political events, based on sector/ETF overlap.

    Args:
        ticker: Stock ticker symbol (e.g. ``"AAPL"``).
        political_events: List of classified political-event dicts (as
            returned by ``classify_political_event`` or within the
            ``get_political_pulse()["events"]`` list).

    Returns:
        Float score in the range ``[0, 100]``.
    """
    if not political_events:
        return 0.0

    total_weight = 0.0
    matched_weight = 0.0

    ticker_upper = ticker.upper()

    for event in political_events:
        try:
            impact = event.get("impact_score", 0)
            sectors = event.get("affected_sectors", [])
            if not sectors:
                continue

            total_weight += impact

            if ticker_upper in sectors:
                matched_weight += impact
        except Exception:
            continue

    if total_weight == 0:
        return 0.0

    exposure = (matched_weight / total_weight) * 100.0
    return round(min(100.0, max(0.0, exposure)), 1)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_all_political_news() -> list[dict]:
    """
    Collect political news from all available sources.  Each source is
    tried independently so one failure never prevents the others.
    """
    articles: list[dict] = []

    # Geopolitical RSS (combined feed)
    if get_geopolitical_news is not None:
        try:
            geo = get_geopolitical_news(max_items=80)
            if geo:
                articles.extend(geo)
        except Exception as exc:
            logger.warning("geopolitical_rss failed: %s", exc)

    # Tariff / trade-specific RSS
    if get_tariff_trade_news is not None:
        try:
            tariff = get_tariff_trade_news(max_items=30)
            if tariff:
                articles.extend(tariff)
        except Exception as exc:
            logger.warning("tariff_trade RSS failed: %s", exc)

    # Political RSS
    if get_political_news is not None:
        try:
            pol = get_political_news(max_items=40)
            if pol:
                articles.extend(pol)
        except Exception as exc:
            logger.warning("political RSS failed: %s", exc)

    # Reddit political discourse
    if get_political_discourse is not None:
        try:
            reddit_pol = get_political_discourse()
            if reddit_pol:
                for post in reddit_pol:
                    articles.append({
                        "headline": post.get("title", ""),
                        "summary": "",
                        "source": f"Reddit r/{post.get('subreddit', 'politics')}",
                        "published": post.get("created_readable", ""),
                    })
        except Exception as exc:
            logger.warning("reddit political discourse failed: %s", exc)

    # Reddit economic sentiment
    if get_economic_sentiment is not None:
        try:
            reddit_econ = get_economic_sentiment()
            if reddit_econ:
                for post in reddit_econ:
                    articles.append({
                        "headline": post.get("title", ""),
                        "summary": "",
                        "source": f"Reddit r/{post.get('subreddit', 'economics')}",
                        "published": post.get("created_readable", ""),
                    })
        except Exception as exc:
            logger.warning("reddit economic sentiment failed: %s", exc)

    # Deduplicate by headline prefix
    articles = _deduplicate(articles)
    return articles


def _deduplicate(articles: list[dict]) -> list[dict]:
    """Remove near-duplicate articles by the first 60 lower-cased chars."""
    seen: set[str] = set()
    unique: list[dict] = []
    for article in articles:
        headline = (
            article.get("headline") or article.get("title") or ""
        )
        key = headline[:60].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(article)
    return unique


def _build_pulse_summary(
    dominant_theme: str,
    market_direction: str,
    risk_level: str,
    event_count: int,
) -> str:
    """Build a concise 1-line political-pulse narrative."""
    theme_labels = {
        "TARIFF_TRADE": "trade/tariff activity",
        "REGULATION": "regulatory developments",
        "TAX_POLICY": "tax-policy signals",
        "FED_MONETARY": "Fed/monetary-policy signals",
        "ELECTION": "election-related chatter",
        "GEOPOLITICAL_TENSION": "geopolitical tensions",
        "CRYPTO_REGULATION": "crypto-regulation headlines",
    }
    theme_str = theme_labels.get(dominant_theme, dominant_theme.lower())

    dir_map = {
        "BULLISH": "leaning bullish",
        "BEARISH": "leaning bearish",
        "NEUTRAL": "mixed/neutral",
    }
    dir_str = dir_map.get(market_direction, "unclear")

    return (
        f"{event_count} political events detected; dominant theme is "
        f"{theme_str}. Market outlook {dir_str}, risk level {risk_level}."
    )
