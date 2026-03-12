"""
Keyword-based NLP classification of news catalysts.
No ML dependencies — uses a keyword taxonomy to classify headlines.
"""
import re
import math
import datetime

# Catalyst type keywords and their base scores
CATALYST_TAXONOMY = {
    "EARNINGS": {
        "keywords": ["earnings", "eps", "beat", "miss", "revenue", "guidance",
                      "quarterly", "q1", "q2", "q3", "q4", "profit", "income"],
        "base_score": 90,
    },
    "FDA": {
        "keywords": ["fda", "approval", "trial", "phase 3", "phase 2", "nda",
                      "bla", "pdufa", "clinical", "drug"],
        "base_score": 85,
    },
    "MERGER": {
        "keywords": ["merger", "acquisition", "takeover", "buyout", "deal",
                      "acquire", "tender offer", "all-cash"],
        "base_score": 85,
    },
    "UPGRADE": {
        "keywords": ["upgrade", "price target", "overweight", "outperform",
                      "buy rating", "raises target", "initiates coverage"],
        "base_score": 65,
    },
    "DOWNGRADE": {
        "keywords": ["downgrade", "underperform", "sell rating", "reduces target",
                      "underweight", "cuts target"],
        "base_score": 65,
    },
    "SEC_FILING": {
        "keywords": ["sec", "8-k", "filing", "material", "10-q", "10-k",
                      "insider", "form 4"],
        "base_score": 70,
    },
    "LEGAL": {
        "keywords": ["lawsuit", "investigation", "subpoena", "fraud",
                      "class action", "settlement", "antitrust"],
        "base_score": 60,
    },
    "MACRO": {
        "keywords": ["fed", "fomc", "rate", "inflation", "cpi", "jobs",
                      "unemployment", "gdp", "tariff", "trade war"],
        "base_score": 55,
    },
    "SHORT_SQUEEZE": {
        "keywords": ["short squeeze", "gamma squeeze", "high short interest",
                      "shorts covering", "days to cover"],
        "base_score": 70,
    },
    "PRODUCT": {
        "keywords": ["launch", "new product", "partnership", "contract",
                      "ai", "breakthrough", "patent"],
        "base_score": 50,
    },
    "POLITICAL": {
        "keywords": ["tariff", "trade war", "sanctions", "executive order",
                      "regulation", "deregulation", "congress", "legislation",
                      "tax", "antitrust", "ban", "policy"],
        "base_score": 70,
    },
    "WAR_CONFLICT": {
        "keywords": ["war", "military", "missile", "airstrike", "invasion",
                      "ceasefire", "troops", "nato", "conflict", "escalation",
                      "territorial", "defense"],
        "base_score": 65,
    },
    "INFLUENCER": {
        "keywords": ["elon musk", "musk tweeted", "trump said", "powell said",
                      "cathie wood", "cramer", "roaring kitty", "buffett",
                      "ackman", "posted on x", "truth social"],
        "base_score": 55,
    },
    "SOCIAL_VIRAL": {
        "keywords": ["trending", "viral", "wsb", "wallstreetbets", "reddit",
                      "stocktwits", "meme stock", "retail investors", "apes",
                      "diamond hands", "to the moon"],
        "base_score": 50,
    },
    "GEOPOLITICAL": {
        "keywords": ["china", "taiwan", "russia", "ukraine", "iran", "oil embargo",
                      "red sea", "strait of hormuz", "south china sea", "nato",
                      "summit", "diplomatic", "sovereign"],
        "base_score": 60,
    },
}

# Direction keywords
BULLISH_KEYWORDS = [
    "beat", "exceed", "raise", "upgrade", "buy", "outperform", "surge",
    "soar", "rally", "jump", "approval", "positive", "strong", "growth",
    "record", "breakthrough", "win", "deal", "partnership", "bullish",
    "ceasefire", "peace", "deregulation", "rate cut", "dovish", "stimulus",
    "tax cut", "trade deal", "de-escalation",
]
BEARISH_KEYWORDS = [
    "miss", "cut", "downgrade", "sell", "underperform", "crash", "plunge",
    "drop", "fall", "decline", "reject", "negative", "weak", "loss",
    "lawsuit", "fraud", "investigation", "warning", "bearish", "delay",
    "tariff", "sanctions", "escalation", "war", "invasion", "hawkish",
    "rate hike", "ban", "embargo", "conflict", "attack", "missile",
]


def classify_catalyst(headline: str) -> dict:
    """
    Classify a news headline into a catalyst type with direction.
    Returns: {type, direction, confidence, base_score}
    """
    if not headline:
        return {"type": "UNKNOWN", "direction": "NEUTRAL", "confidence": 0.0, "base_score": 0}

    headline_lower = headline.lower()

    best_type = "UNKNOWN"
    best_score = 0
    best_match_count = 0

    for cat_type, info in CATALYST_TAXONOMY.items():
        matches = sum(1 for kw in info["keywords"] if kw in headline_lower)
        if matches > best_match_count:
            best_match_count = matches
            best_type = cat_type
            best_score = info["base_score"]

    # Determine direction
    bull_count = sum(1 for kw in BULLISH_KEYWORDS if kw in headline_lower)
    bear_count = sum(1 for kw in BEARISH_KEYWORDS if kw in headline_lower)

    if bull_count > bear_count:
        direction = "BULLISH"
    elif bear_count > bull_count:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    # Confidence based on keyword density
    confidence = min(1.0, best_match_count / 3.0)

    return {
        "type": best_type,
        "direction": direction,
        "confidence": confidence,
        "base_score": best_score,
    }


def score_catalysts(news_list: list[dict]) -> dict:
    """
    Score a list of news items and produce a catalyst summary.
    Returns: {catalyst_score: 0-100, top_catalyst: str, catalyst_age_hours: float,
              direction: str, summary: str}
    """
    if not news_list:
        return {
            "catalyst_score": 0,
            "top_catalyst": "NO_CATALYST",
            "catalyst_age_hours": 999,
            "direction": "NEUTRAL",
            "summary": "No recent catalysts detected",
        }

    best = None
    best_adjusted_score = 0

    for item in news_list:
        classification = classify_catalyst(item.get("headline", ""))

        # Time decay: half-life of 6 hours
        age_hours = _compute_age_hours(item.get("published"))
        time_decay = math.exp(-age_hours / 6.0) if age_hours < 999 else 0.01

        adjusted_score = classification["base_score"] * time_decay * (0.5 + 0.5 * classification["confidence"])

        if adjusted_score > best_adjusted_score:
            best_adjusted_score = adjusted_score
            best = {
                "classification": classification,
                "headline": item.get("headline", ""),
                "age_hours": age_hours,
                "adjusted_score": adjusted_score,
            }

    if not best:
        return {
            "catalyst_score": 0,
            "top_catalyst": "NO_CATALYST",
            "catalyst_age_hours": 999,
            "direction": "NEUTRAL",
            "summary": "No recent catalysts detected",
        }

    return {
        "catalyst_score": min(100, round(best["adjusted_score"])),
        "top_catalyst": best["classification"]["type"],
        "catalyst_age_hours": round(best["age_hours"], 1),
        "direction": best["classification"]["direction"],
        "summary": _build_summary(best),
    }


def _compute_age_hours(published) -> float:
    """Compute age in hours from a published timestamp."""
    now = datetime.datetime.now()
    if isinstance(published, (int, float)):
        try:
            dt = datetime.datetime.fromtimestamp(published)
            return max(0, (now - dt).total_seconds() / 3600)
        except Exception:
            return 999
    if isinstance(published, str):
        try:
            dt = datetime.datetime.fromisoformat(published.replace("Z", "+00:00"))
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            return max(0, (now - dt).total_seconds() / 3600)
        except Exception:
            return 999
    if isinstance(published, datetime.datetime):
        if published.tzinfo:
            published = published.replace(tzinfo=None)
        return max(0, (now - published).total_seconds() / 3600)
    return 999


def _build_summary(best: dict) -> str:
    """Build a 1-line human-readable catalyst summary."""
    cat_type = best["classification"]["type"]
    direction = best["classification"]["direction"]
    headline = best["headline"]
    age = best["age_hours"]

    # Truncate headline
    short_headline = headline[:80] + "..." if len(headline) > 80 else headline

    age_str = f"{age:.0f}h ago" if age < 48 else f"{age/24:.0f}d ago"
    dir_emoji = {"BULLISH": "+", "BEARISH": "-", "NEUTRAL": "~"}.get(direction, "~")

    return f"[{dir_emoji}] {cat_type}: {short_headline} ({age_str})"
