"""
Tracks influential content creators, fintwit personalities, and political figures
whose statements move markets. Since we cannot directly access X/Twitter for free,
we track these influencers through news coverage of their statements.
"""
import re
from data.cache import cached

# ---------------------------------------------------------------------------
# Try-imports for optional data sources
# ---------------------------------------------------------------------------
try:
    from catalyst.news_aggregator import aggregate_news
except Exception:
    aggregate_news = None

try:
    from data.fetchers.geopolitical_rss import get_geopolitical_news
except Exception:
    get_geopolitical_news = None

try:
    from data.fetchers.stocktwits_fetcher import get_stocktwits_trending
except Exception:
    get_stocktwits_trending = None


# ---------------------------------------------------------------------------
# Curated list of market-moving influencers
# ---------------------------------------------------------------------------
MARKET_INFLUENCERS = {
    # Political figures
    "POLITICAL": {
        "trump": {
            "name": "Donald Trump",
            "platform": "Truth Social/X",
            "impact": 95,
            "sectors": ["SPY", "QQQ", "XLE", "MSTR"],
        },
        "biden": {
            "name": "Joe Biden",
            "platform": "Official/X",
            "impact": 85,
            "sectors": ["SPY", "XLE", "XLV"],
        },
        "powell": {
            "name": "Jerome Powell",
            "platform": "Fed/Press",
            "impact": 95,
            "sectors": ["SPY", "XLF", "TLT", "GLD"],
        },
        "yellen": {
            "name": "Janet Yellen",
            "platform": "Treasury",
            "impact": 80,
            "sectors": ["SPY", "XLF"],
        },
        "gensler": {
            "name": "Gary Gensler",
            "platform": "SEC/X",
            "impact": 70,
            "sectors": ["COIN", "XLF"],
        },
        "warren": {
            "name": "Elizabeth Warren",
            "platform": "X/Senate",
            "impact": 65,
            "sectors": ["XLF", "COIN"],
        },
    },
    # Finance / Fintwit influencers
    "FINTWIT": {
        "cramer": {
            "name": "Jim Cramer",
            "platform": "CNBC/X",
            "impact": 60,
            "note": "inverse_cramer",
        },
        "cathie_wood": {
            "name": "Cathie Wood",
            "platform": "X/ARK",
            "impact": 70,
            "sectors": ["ARKK", "TSLA", "COIN"],
        },
        "chamath": {
            "name": "Chamath Palihapitiya",
            "platform": "X/Podcast",
            "impact": 65,
            "sectors": ["SOFI", "SPCE"],
        },
        "burry": {
            "name": "Michael Burry",
            "platform": "X/13F",
            "impact": 75,
            "sectors": [],
        },
        "ackman": {
            "name": "Bill Ackman",
            "platform": "X",
            "impact": 80,
            "sectors": [],
        },
        "dalio": {
            "name": "Ray Dalio",
            "platform": "LinkedIn/Press",
            "impact": 75,
            "sectors": ["GLD", "TLT"],
        },
        "buffett": {
            "name": "Warren Buffett",
            "platform": "Press/BRK",
            "impact": 90,
            "sectors": [],
        },
        "dimon": {
            "name": "Jamie Dimon",
            "platform": "JPM/Press",
            "impact": 80,
            "sectors": ["XLF", "JPM"],
        },
    },
    # Tech / Content Creator influencers
    "TECH_CREATORS": {
        "elon": {
            "name": "Elon Musk",
            "platform": "X",
            "impact": 95,
            "sectors": ["TSLA", "DOGE", "MSTR", "TWTR"],
        },
        "zuck": {
            "name": "Mark Zuckerberg",
            "platform": "Threads/Meta",
            "impact": 70,
            "sectors": ["META"],
        },
        "altman": {
            "name": "Sam Altman",
            "platform": "X",
            "impact": 80,
            "sectors": ["MSFT", "NVDA"],
        },
        "nadella": {
            "name": "Satya Nadella",
            "platform": "X/Press",
            "impact": 75,
            "sectors": ["MSFT"],
        },
        "cook": {
            "name": "Tim Cook",
            "platform": "Press",
            "impact": 70,
            "sectors": ["AAPL"],
        },
        "roaring_kitty": {
            "name": "Roaring Kitty/DFV",
            "platform": "X/Reddit",
            "impact": 85,
            "sectors": ["GME", "AMC"],
        },
        "mr_beast": {
            "name": "MrBeast",
            "platform": "YouTube/X",
            "impact": 40,
            "sectors": [],
        },
    },
}


# ---------------------------------------------------------------------------
# Internal: build lookup tables for fast matching
# ---------------------------------------------------------------------------

# Map lowercased name fragments -> (category, key, info)
_NAME_PATTERNS: list[tuple[re.Pattern, str, str, dict]] = []


def _build_patterns():
    """Pre-compile regex patterns for every influencer name variant."""
    if _NAME_PATTERNS:
        return
    for category, members in MARKET_INFLUENCERS.items():
        for key, info in members.items():
            full_name = info["name"]
            # Build list of name fragments to search for
            variants = set()
            variants.add(full_name.lower())
            # Last name (most common in headlines)
            parts = full_name.split()
            if len(parts) >= 2:
                variants.add(parts[-1].lower())
            # Handle special cases
            if key == "elon":
                variants.update(["elon", "musk", "elon musk"])
            elif key == "roaring_kitty":
                variants.update(["roaring kitty", "dfv", "deepfuckingvalue", "keith gill"])
            elif key == "cathie_wood":
                variants.update(["cathie wood", "cathie", "ark invest"])
            elif key == "mr_beast":
                variants.update(["mrbeast", "mr beast", "jimmy donaldson"])
            elif key == "cramer":
                variants.update(["jim cramer", "cramer", "mad money"])
            elif key == "powell":
                variants.update(["jerome powell", "fed chair", "fed chairman"])
            elif key == "buffett":
                # Distinguish from Jimmy Buffett via context
                variants.update(["warren buffett", "berkshire"])
            elif key == "warren":
                variants.update(["elizabeth warren", "senator warren"])
            elif key == "chamath":
                variants.update(["chamath", "palihapitiya"])

            for v in variants:
                # Word-boundary match to reduce false positives
                pattern = re.compile(r"\b" + re.escape(v) + r"\b", re.IGNORECASE)
                _NAME_PATTERNS.append((pattern, category, key, info))


# Sentiment keywords for direction detection
_BULLISH_WORDS = {
    "buy", "bullish", "long", "upgrade", "positive", "optimistic",
    "rally", "surge", "soar", "boost", "growth", "opportunity",
    "breakout", "moon", "rocket", "support", "calls", "upside",
    "rip", "pump", "strong", "love", "great", "amazing", "incredible",
}
_BEARISH_WORDS = {
    "sell", "bearish", "short", "downgrade", "negative", "pessimistic",
    "crash", "plunge", "dump", "collapse", "risk", "warning",
    "bubble", "overvalued", "puts", "downside", "fade", "weak",
    "terrible", "disaster", "crisis", "recession", "fear", "tank",
}


def _detect_direction(text: str) -> str:
    """Detect BULLISH/BEARISH/NEUTRAL from text keywords."""
    text_lower = text.lower()
    bull_count = sum(1 for w in _BULLISH_WORDS if w in text_lower)
    bear_count = sum(1 for w in _BEARISH_WORDS if w in text_lower)
    if bull_count > bear_count and bull_count >= 1:
        return "BULLISH"
    elif bear_count > bull_count and bear_count >= 1:
        return "BEARISH"
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_influencer_mentions(news_items: list[dict]) -> list[dict]:
    """
    Scan news headlines and summaries for influencer name mentions.

    Parameters
    ----------
    news_items : list[dict]
        Each dict should contain at least 'headline' and optionally 'summary'.

    Returns
    -------
    list[dict]
        Each match: {influencer_key, name, category, headline, direction,
                     impact_score, affected_tickers, platform}
    """
    try:
        _build_patterns()
    except Exception:
        return []

    mentions: list[dict] = []
    seen: set[tuple[str, str]] = set()  # (influencer_key, headline[:80])

    for item in (news_items or []):
        try:
            headline = item.get("headline", "") or ""
            summary = item.get("summary", "") or ""
            combined = f"{headline} {summary}"
            if not combined.strip():
                continue

            for pattern, category, key, info in _NAME_PATTERNS:
                if not pattern.search(combined):
                    continue

                # Deduplicate: same influencer + same headline
                dedup_key = (key, headline[:80])
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                direction = _detect_direction(combined)
                affected_tickers = list(info.get("sectors", []))

                # --- Special logic: Inverse Cramer ---
                note = info.get("note", "")
                inverse_cramer = False
                if note == "inverse_cramer" and direction == "BULLISH":
                    inverse_cramer = True

                # --- Special logic: Elon + crypto/TSLA/DOGE ---
                elon_crypto_alert = False
                if key == "elon":
                    crypto_terms = ["crypto", "bitcoin", "btc", "doge", "dogecoin", "tesla", "tsla"]
                    if any(t in combined.lower() for t in crypto_terms):
                        elon_crypto_alert = True

                # --- Special logic: Roaring Kitty / DFV meme stock alert ---
                meme_stock_alert = False
                if key == "roaring_kitty":
                    meme_stock_alert = True
                    # Ensure GME and AMC are always in affected tickers
                    for meme in ("GME", "AMC"):
                        if meme not in affected_tickers:
                            affected_tickers.append(meme)

                # --- Political figure -> sector mapping ---
                if category == "POLITICAL":
                    _enrich_political_tickers(combined, affected_tickers)

                mention = {
                    "influencer_key": key,
                    "name": info["name"],
                    "category": category,
                    "headline": headline,
                    "direction": direction,
                    "impact_score": info.get("impact", 50),
                    "affected_tickers": affected_tickers,
                    "platform": info.get("platform", "Unknown"),
                }

                if inverse_cramer:
                    mention["inverse_cramer"] = True
                    mention["contrarian_signal"] = (
                        "BEARISH" if direction == "BULLISH" else "BULLISH"
                    )

                if elon_crypto_alert:
                    mention["elon_crypto_alert"] = True

                if meme_stock_alert:
                    mention["meme_stock_alert"] = True

                mentions.append(mention)
        except Exception:
            continue

    # Sort by impact score descending
    mentions.sort(key=lambda m: m.get("impact_score", 0), reverse=True)
    return mentions


def _enrich_political_tickers(text: str, tickers: list[str]):
    """Add sector-specific tickers when a political figure mentions certain topics."""
    text_lower = text.lower()
    sector_map = {
        "energy": ["XLE", "XOP", "USO"],
        "oil": ["XLE", "XOP", "USO"],
        "gas": ["XLE", "UNG"],
        "tariff": ["SPY", "QQQ", "EEM"],
        "trade": ["SPY", "QQQ", "EEM"],
        "china": ["FXI", "KWEB", "EEM"],
        "crypto": ["COIN", "MSTR", "BITO"],
        "bitcoin": ["COIN", "MSTR", "BITO"],
        "regulation": ["XLF", "COIN"],
        "bank": ["XLF", "KRE"],
        "rate": ["TLT", "XLF", "GLD"],
        "interest rate": ["TLT", "XLF", "GLD"],
        "inflation": ["GLD", "TLT", "TIPS"],
        "healthcare": ["XLV", "XBI"],
        "pharma": ["XLV", "XBI"],
        "tech": ["QQQ", "XLK"],
        "defense": ["XAR", "ITA"],
        "military": ["XAR", "ITA"],
    }
    for keyword, sector_tickers in sector_map.items():
        if keyword in text_lower:
            for t in sector_tickers:
                if t not in tickers:
                    tickers.append(t)


def _gather_news_items() -> list[dict]:
    """Collect news from all available sources for influencer scanning."""
    all_news: list[dict] = []

    # General market news via aggregator
    if aggregate_news is not None:
        for ticker in ("SPY", "QQQ"):
            try:
                items = aggregate_news(ticker, max_age_hours=12)
                if items:
                    all_news.extend(items)
            except Exception:
                pass

    # Geopolitical RSS
    if get_geopolitical_news is not None:
        try:
            geo_items = get_geopolitical_news()
            if geo_items:
                all_news.extend(geo_items)
        except Exception:
            pass

    # StockTwits trending (may contain influencer chatter)
    if get_stocktwits_trending is not None:
        try:
            st_items = get_stocktwits_trending()
            if st_items:
                all_news.extend(st_items)
        except Exception:
            pass

    return all_news


@cached(ttl=300)
def get_influencer_pulse() -> dict:
    """
    Main entry point: scan recent news for influencer mentions and build a
    comprehensive signal overview.

    Returns
    -------
    dict
        {
            active_influencers: list[dict],   # who is making noise
            top_signal: dict,                  # highest impact mention
            elon_alert: bool,                  # Elon mentioned (special flag)
            political_voices: list[dict],      # political figure statements
            fintwit_consensus: str,            # BULLISH/BEARISH/MIXED/QUIET
            affected_tickers: dict,            # {ticker: [influencer mentions]}
            summary: str,                      # 1-line narrative
        }
    """
    try:
        news_items = _gather_news_items()
        mentions = detect_influencer_mentions(news_items)

        # Active influencers
        active_influencers = mentions

        # Top signal: highest impact
        top_signal = mentions[0] if mentions else {}

        # Elon alert
        elon_alert = any(m["influencer_key"] == "elon" for m in mentions)

        # Political voices
        political_voices = [m for m in mentions if m["category"] == "POLITICAL"]

        # Fintwit consensus
        fintwit_mentions = [m for m in mentions if m["category"] == "FINTWIT"]
        fintwit_consensus = _compute_consensus(fintwit_mentions)

        # Affected tickers map: {ticker: [list of mentions referencing it]}
        affected_tickers: dict[str, list[dict]] = {}
        for m in mentions:
            for ticker in m.get("affected_tickers", []):
                affected_tickers.setdefault(ticker, []).append({
                    "influencer": m["name"],
                    "direction": m["direction"],
                    "impact_score": m["impact_score"],
                    "headline": m["headline"],
                })

        # Summary narrative
        summary = _build_summary(mentions, elon_alert, political_voices, fintwit_consensus)

        return {
            "active_influencers": active_influencers,
            "top_signal": top_signal,
            "elon_alert": elon_alert,
            "political_voices": political_voices,
            "fintwit_consensus": fintwit_consensus,
            "affected_tickers": affected_tickers,
            "summary": summary,
        }
    except Exception:
        return {
            "active_influencers": [],
            "top_signal": {},
            "elon_alert": False,
            "political_voices": [],
            "fintwit_consensus": "QUIET",
            "affected_tickers": {},
            "summary": "No influencer signals detected.",
        }


def _compute_consensus(fintwit_mentions: list[dict]) -> str:
    """Determine overall fintwit direction from mentions."""
    if not fintwit_mentions:
        return "QUIET"

    bullish = sum(1 for m in fintwit_mentions if m.get("direction") == "BULLISH")
    bearish = sum(1 for m in fintwit_mentions if m.get("direction") == "BEARISH")
    total = len(fintwit_mentions)

    if total == 0:
        return "QUIET"
    if bullish > bearish and bullish / total >= 0.6:
        return "BULLISH"
    if bearish > bullish and bearish / total >= 0.6:
        return "BEARISH"
    if bullish > 0 or bearish > 0:
        return "MIXED"
    return "QUIET"


def _build_summary(
    mentions: list[dict],
    elon_alert: bool,
    political_voices: list[dict],
    fintwit_consensus: str,
) -> str:
    """Build a one-line narrative summarizing the influencer landscape."""
    if not mentions:
        return "No influencer signals detected."

    parts: list[str] = []

    # Count unique influencers
    unique_names = {m["name"] for m in mentions}
    parts.append(f"{len(unique_names)} influencer(s) active")

    if elon_alert:
        parts.append("Elon alert triggered")

    if political_voices:
        pol_names = list({m["name"] for m in political_voices})
        parts.append(f"Political: {', '.join(pol_names[:3])}")

    if fintwit_consensus != "QUIET":
        parts.append(f"Fintwit: {fintwit_consensus}")

    # Check for special flags
    meme_alerts = [m for m in mentions if m.get("meme_stock_alert")]
    if meme_alerts:
        parts.append("MEME STOCK ALERT (Roaring Kitty)")

    cramer_contrarian = [m for m in mentions if m.get("inverse_cramer")]
    if cramer_contrarian:
        parts.append("Inverse Cramer signal active")

    return " | ".join(parts) + "."


def get_ticker_influencer_exposure(ticker: str, influencer_data: dict | None = None) -> float:
    """
    Returns a 0-100 score based on how much influencer attention a ticker is getting.

    Parameters
    ----------
    ticker : str
        The stock/ETF ticker symbol.
    influencer_data : dict or None
        Pre-fetched result from get_influencer_pulse(). If None, fetches fresh data.

    Returns
    -------
    float
        Exposure score from 0 (no attention) to 100 (maximum influencer focus).
    """
    try:
        if influencer_data is None:
            influencer_data = get_influencer_pulse()

        ticker_upper = ticker.upper()
        affected = influencer_data.get("affected_tickers", {})

        if ticker_upper not in affected:
            # Check if any influencer has this ticker in their default sectors
            base_score = _get_static_ticker_relevance(ticker_upper)
            return base_score

        ticker_mentions = affected[ticker_upper]
        if not ticker_mentions:
            return 0.0

        # Score components:
        # 1. Number of distinct influencers mentioning it (up to 40 pts)
        unique_influencers = {m["influencer"] for m in ticker_mentions}
        count_score = min(40.0, len(unique_influencers) * 10.0)

        # 2. Highest impact score among mentioners (up to 35 pts)
        max_impact = max((m.get("impact_score", 0) for m in ticker_mentions), default=0)
        impact_score = (max_impact / 100.0) * 35.0

        # 3. Directional agreement bonus (up to 15 pts)
        directions = [m.get("direction", "NEUTRAL") for m in ticker_mentions]
        if len(directions) >= 2:
            dominant = max(set(directions), key=directions.count)
            agreement_ratio = directions.count(dominant) / len(directions)
            agreement_score = agreement_ratio * 15.0
        else:
            agreement_score = 5.0  # single mention gets a small bonus

        # 4. Special event bonuses (up to 10 pts)
        special_bonus = 0.0
        for m in ticker_mentions:
            if "elon_crypto_alert" in m and ticker_upper in ("TSLA", "DOGE", "MSTR"):
                special_bonus = max(special_bonus, 10.0)
            if "meme_stock_alert" in m and ticker_upper in ("GME", "AMC"):
                special_bonus = max(special_bonus, 10.0)
            if "inverse_cramer" in m:
                special_bonus = max(special_bonus, 5.0)

        total = count_score + impact_score + agreement_score + special_bonus
        return min(100.0, round(total, 1))

    except Exception:
        return 0.0


def _get_static_ticker_relevance(ticker: str) -> float:
    """
    Check if a ticker appears in any influencer's default sector list.
    Returns a small baseline score (0-15) if it does.
    """
    score = 0.0
    for _category, members in MARKET_INFLUENCERS.items():
        for _key, info in members.items():
            if ticker in info.get("sectors", []):
                # Weight by influencer impact
                score += info.get("impact", 50) * 0.05
    return min(15.0, round(score, 1))
