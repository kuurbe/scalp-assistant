"""
Catalyst quality scoring from aggregated news/filings/sentiment.
"""


def compute_catalyst_score(
    news_score: float = 0,
    sentiment_score: float = 0,
    reddit_trending: bool = False,
    short_ratio: float = 0,
) -> float:
    """
    Weighted catalyst composite.
    news_score: 0-100 from catalyst_detector
    sentiment_score: -100 to +100 from sentiment_tracker
    Returns: 0-100 score.
    """
    # Normalize sentiment to 0-100 range
    norm_sentiment = (sentiment_score + 100) / 2  # maps [-100,100] to [0,100]

    raw = (
        0.50 * news_score +
        0.30 * norm_sentiment +
        0.10 * (80 if reddit_trending else 0) +
        0.10 * min(100, short_ratio * 200)  # high short ratio = squeeze potential
    )

    return max(0, min(100, round(raw, 1)))
