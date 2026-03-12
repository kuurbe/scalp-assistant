"""
CNN Fear & Greed Index fetcher.
Public API — no key required.
"""
import logging
import requests
from data.cache import cached

logger = logging.getLogger(__name__)

FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


def _rating_from_score(score: float) -> str:
    """Map 0-100 score to human-readable rating."""
    if score <= 20:
        return "Extreme Fear"
    if score <= 40:
        return "Fear"
    if score <= 60:
        return "Neutral"
    if score <= 80:
        return "Greed"
    return "Extreme Greed"


@cached(ttl=600)
def get_fear_greed() -> dict:
    """Fetch CNN Fear & Greed Index.

    Returns:
        {"score": 27, "rating": "Fear", "previous_close": 30,
         "one_week_ago": 35, "one_month_ago": 42, "one_year_ago": 55}
    """
    try:
        resp = requests.get(
            FEAR_GREED_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Referer": "https://edition.cnn.com/markets/fear-and-greed",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("Fear & Greed fetch failed: %s", e)
        return {}

    try:
        fg = data.get("fear_and_greed", {})
        score = float(fg.get("score", 0))
        prev = float(fg.get("previous_close", 0))
        one_week = float(fg.get("previous_1_week", 0))
        one_month = float(fg.get("previous_1_month", 0))
        one_year = float(fg.get("previous_1_year", 0))

        return {
            "score": round(score, 1),
            "rating": fg.get("rating", _rating_from_score(score)),
            "previous_close": round(prev, 1),
            "one_week_ago": round(one_week, 1),
            "one_month_ago": round(one_month, 1),
            "one_year_ago": round(one_year, 1),
        }
    except Exception as e:
        logger.error("Fear & Greed parse failed: %s", e)
        return {}
