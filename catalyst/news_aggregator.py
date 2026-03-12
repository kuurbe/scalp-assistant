"""
Merges all news sources into a unified, deduplicated, time-sorted feed.
Sources: Finnhub REST + Yahoo RSS + SEC EDGAR 8-K filings.
"""
import datetime
from data.cache import cached


def _deduplicate(news_list: list[dict]) -> list[dict]:
    """Remove duplicate headlines using exact + fuzzy matching."""
    seen_titles = set()
    unique = []
    for item in news_list:
        title_lower = item.get("headline", "").lower().strip()
        # Simple dedup: skip if title already seen (or very similar)
        short_key = title_lower[:60]
        if short_key and short_key not in seen_titles:
            seen_titles.add(short_key)
            unique.append(item)
    return unique


@cached(ttl=180)
def aggregate_news(ticker: str, max_age_hours: int = 24) -> list[dict]:
    """
    Aggregate news from all available sources for a ticker.
    Returns list of {headline, source, published, url, ticker} sorted by recency.
    """
    all_news = []
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=max_age_hours)

    # Finnhub company news
    try:
        from data.fetchers.finnhub_fetcher import get_company_news
        finnhub_news = get_company_news(ticker, days_back=max(1, max_age_hours // 24 + 1))
        if finnhub_news:
            for item in finnhub_news:
                all_news.append({
                    "headline": item.get("headline", ""),
                    "summary": item.get("summary", ""),
                    "source": f"Finnhub/{item.get('source', 'unknown')}",
                    "published": item.get("datetime"),
                    "url": item.get("url", ""),
                    "ticker": ticker,
                })
    except Exception:
        pass

    # Yahoo RSS
    try:
        from data.fetchers.rss_fetcher import get_yahoo_rss_news
        rss_news = get_yahoo_rss_news(ticker)
        if rss_news:
            for item in rss_news:
                all_news.append({
                    "headline": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "source": "Yahoo RSS",
                    "published": item.get("published"),
                    "url": item.get("link", ""),
                    "ticker": ticker,
                })
    except Exception:
        pass

    # SEC EDGAR 8-K filings
    try:
        from data.fetchers.edgar_fetcher import get_recent_8k_filings
        filings = get_recent_8k_filings(ticker, days_back=max(1, max_age_hours // 24 + 1))
        if filings:
            for filing in filings:
                all_news.append({
                    "headline": f"SEC 8-K Filing: {filing.get('description', 'Material Event')}",
                    "summary": f"Items: {', '.join(filing.get('items', []))}",
                    "source": "SEC EDGAR",
                    "published": filing.get("filedAt"),
                    "url": filing.get("url", ""),
                    "ticker": ticker,
                })
    except Exception:
        pass

    # Stocktwits messages as news items
    try:
        from data.fetchers.stocktwits_fetcher import get_stocktwits_messages
        st_msgs = get_stocktwits_messages(ticker, limit=10)
        if st_msgs:
            for msg in st_msgs:
                sentiment_tag = f" [{msg.get('sentiment', 'neutral').upper()}]" if msg.get('sentiment') else ""
                all_news.append({
                    "headline": f"StockTwits: {msg.get('body', '')[:120]}{sentiment_tag}",
                    "summary": msg.get("body", ""),
                    "source": f"StockTwits/@{msg.get('username', 'anon')}",
                    "published": msg.get("created_at"),
                    "url": "",
                    "ticker": ticker,
                })
    except Exception:
        pass

    # Deduplicate and sort by recency
    unique = _deduplicate(all_news)

    # Sort by published time (most recent first), handle missing dates
    def sort_key(item):
        pub = item.get("published")
        if isinstance(pub, (int, float)):
            return -pub
        if isinstance(pub, str):
            try:
                dt = datetime.datetime.fromisoformat(pub.replace("Z", "+00:00"))
                return -dt.timestamp()
            except Exception:
                pass
        if isinstance(pub, datetime.datetime):
            return -pub.timestamp()
        return 0

    unique.sort(key=sort_key)
    return unique


@cached(ttl=300)
def get_market_catalysts(max_age_hours: int = 4) -> list[dict]:
    """Get broad market news that affects all tickers."""
    all_news = []

    try:
        from data.fetchers.finnhub_fetcher import get_market_news
        market_news = get_market_news()
        if market_news:
            for item in market_news:
                all_news.append({
                    "headline": item.get("headline", ""),
                    "summary": item.get("summary", ""),
                    "source": f"Finnhub/{item.get('source', '')}",
                    "published": item.get("datetime"),
                    "url": item.get("url", ""),
                    "ticker": "MARKET",
                })
    except Exception:
        pass

    try:
        from data.fetchers.rss_fetcher import get_market_rss_news
        rss_news = get_market_rss_news()
        if rss_news:
            for item in rss_news:
                all_news.append({
                    "headline": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "source": "Yahoo RSS",
                    "published": item.get("published"),
                    "url": item.get("link", ""),
                    "ticker": "MARKET",
                })
    except Exception:
        pass

    # Geopolitical news (political + war/conflict)
    try:
        from data.fetchers.geopolitical_rss import get_geopolitical_news
        geo_news = get_geopolitical_news(max_items=30)
        if geo_news:
            for item in geo_news:
                all_news.append({
                    "headline": item.get("headline", ""),
                    "summary": item.get("summary", ""),
                    "source": f"Geo/{item.get('source', 'RSS')}",
                    "published": item.get("published"),
                    "url": item.get("url", ""),
                    "ticker": "MARKET",
                })
    except Exception:
        pass

    return _deduplicate(all_news)
