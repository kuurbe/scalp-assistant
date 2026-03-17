"""
Bridge between the Streamlit dashboard and the existing analysis pipeline.
All analysis logic stays in the original modules — this just orchestrates.
"""
import sys
import os
import logging

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Shared executor for pre-warming data concurrently
_PREFETCH_POOL = ThreadPoolExecutor(max_workers=4)


def _prefetch_shared_data(asset_class: str) -> dict:
    """Fetch macro, political, war, influencer data concurrently.
    Returns a dict with all shared context needed by _analyze_ticker.
    """
    futures = {}
    futures["macro"] = _PREFETCH_POOL.submit(get_macro_regime)
    futures["political"] = _PREFETCH_POOL.submit(get_political_pulse)
    futures["war"] = _PREFETCH_POOL.submit(get_war_watch)
    futures["influencer"] = _PREFETCH_POOL.submit(get_influencer_pulse)

    if asset_class in ("stocks", "etfs"):
        from modes.morning_scan import _fetch_reddit
        futures["reddit"] = _PREFETCH_POOL.submit(_fetch_reddit)

    results = {}
    for key, future in futures.items():
        try:
            results[key] = future.result(timeout=15)
        except Exception:
            results[key] = {} if key != "macro" else "NEUTRAL"

    return results


@st.cache_data(ttl=300, show_spinner=False)
def scan_universe(asset_class: str) -> list:
    """Run the full analysis pipeline on an asset class universe.
    Returns list of ScoredTicker-like dicts (serializable for Streamlit cache).
    """
    from config import settings

    cfg = settings.ASSET_CLASS_CONFIG.get(asset_class, {})
    universe = settings.get_universe(asset_class)

    if not universe:
        return []

    from modes.morning_scan import _analyze_ticker

    # Pre-warm all shared data concurrently (parallel fetches)
    shared = _prefetch_shared_data(asset_class)
    macro_regime = shared.get("macro", "NEUTRAL")
    reddit_data = shared.get("reddit", {})
    short_data = {}
    political_pulse = shared.get("political", {})
    war_watch = shared.get("war", {})
    influencer_pulse = shared.get("influencer", {})

    results = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {
            pool.submit(
                _analyze_ticker, ticker, macro_regime, reddit_data, short_data,
                political_pulse, war_watch, influencer_pulse, asset_class
            ): ticker
            for ticker in universe
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception:
                pass

    results.sort(key=lambda x: x.composite_score, reverse=True)
    return results


@st.cache_data(ttl=300, show_spinner=False)
def get_macro_context() -> dict:
    """Fetch macro context from FRED."""
    try:
        from data.fetchers.fred_fetcher import get_macro_context as _get_macro
        ctx = _get_macro()
        # Fallback VIX
        if not ctx.get("vix") or (isinstance(ctx.get("vix"), float) and __import__("math").isnan(ctx["vix"])):
            try:
                import yfinance as yf
                h = yf.Ticker("^VIX").history(period="2d")
                if len(h) > 0:
                    val = float(h["Close"].iloc[-1])
                    ctx["vix"] = round(val, 2) if not __import__("math").isnan(val) else 0
            except Exception:
                ctx["vix"] = 0
        return ctx
    except Exception:
        return {"vix": 0, "macro_regime": "NEUTRAL"}


def get_macro_regime() -> str:
    """Get just the macro regime string."""
    return get_macro_context().get("macro_regime", "NEUTRAL")


@st.cache_data(ttl=300, show_spinner=False)
def get_expanded_macro() -> dict:
    """Fetch expanded FRED macro data for the macro dashboard."""
    try:
        from config import settings
        from data.fetchers.fred_fetcher import _get_fred_client, _fetch_latest_value
        fred = _get_fred_client()
        if fred is None:
            return {}

        result = {}
        for series_id, key in settings.FRED_SERIES_EXPANDED.items():
            result[key] = _fetch_latest_value(fred, series_id)
        return result
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def get_political_pulse() -> dict:
    try:
        from catalyst.political_tracker import get_political_pulse as _get
        return _get() or {}
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def get_war_watch() -> dict:
    try:
        from catalyst.war_tracker import get_war_watch as _get
        return _get() or {}
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def get_influencer_pulse() -> dict:
    try:
        from catalyst.influencer_tracker import get_influencer_pulse as _get
        return _get() or {}
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def get_social_intel() -> dict:
    try:
        from catalyst.social_intel import get_social_intel as _get
        return _get() or {}
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def get_prediction_accuracy() -> dict:
    """Get prediction accuracy metrics."""
    try:
        from analysis.predictions.tracker import compute_prediction_accuracy
        return compute_prediction_accuracy()
    except Exception:
        return {"overall_win_rate": 0, "wins": 0, "losses": 0, "total": 0}


@st.cache_data(ttl=300, show_spinner=False)
def get_achievements() -> list:
    """Get earned achievements."""
    try:
        from output.achievements import get_all_achievements
        return get_all_achievements()
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def get_fear_greed() -> dict:
    """Get CNN Fear & Greed Index."""
    try:
        from data.fetchers.fear_greed_fetcher import get_fear_greed as _get
        return _get() or {}
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def get_crypto_global() -> dict:
    """Get global crypto market stats from CoinGecko."""
    try:
        from data.fetchers.coingecko_fetcher import get_global_crypto as _get
        return _get() or {}
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def get_trending_coins() -> list:
    """Get trending coins from CoinGecko."""
    try:
        from data.fetchers.coingecko_fetcher import get_trending_coins as _get
        return _get() or []
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def get_crypto_fear_greed() -> dict:
    """Get crypto-specific Fear & Greed from Alternative.me."""
    try:
        from data.fetchers.coingecko_fetcher import get_crypto_fear_greed as _get
        return _get() or {}
    except Exception:
        return {}


@st.cache_data(ttl=900, show_spinner=False)
def get_insider_summary(symbol: str) -> dict:
    """Get insider trading summary for a symbol."""
    try:
        from data.fetchers.insider_fetcher import get_insider_summary as _get
        return _get(symbol) or {}
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def get_pcr(symbol: str) -> dict:
    """Get put/call ratio for a symbol."""
    try:
        from analysis.options.pcr_analyzer import get_pcr as _get
        return _get(symbol) or {}
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def get_event_contracts() -> list:
    """Get prediction market / event contract data."""
    try:
        from data.fetchers.events_fetcher import get_prediction_market_events
        return get_prediction_market_events()
    except Exception:
        return []


@st.cache_data(ttl=180, show_spinner=False)
def get_market_news() -> list:
    """Get aggregated market news from all sources (Finnhub + Yahoo RSS + geopolitical)."""
    try:
        from catalyst.news_aggregator import get_market_catalysts
        news = get_market_catalysts(max_age_hours=12)
        return news[:30] if news else []
    except Exception:
        return []


@st.cache_data(ttl=180, show_spinner=False)
def get_ticker_news(ticker: str) -> list:
    """Get aggregated news for a specific ticker."""
    try:
        from catalyst.news_aggregator import aggregate_news
        news = aggregate_news(ticker, max_age_hours=24)
        return news[:15] if news else []
    except Exception:
        return []
