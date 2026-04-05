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


def _extract_ticker_from_batch(data, ticker: str, cols: list) -> "pd.DataFrame | None":
    """Extract a single ticker's OHLCV from a yfinance batch download.

    yfinance returns MultiIndex columns: (Price, Ticker) for multi-ticker downloads,
    or flat columns for single-ticker downloads.
    """
    import pandas as pd
    try:
        if isinstance(data.columns, pd.MultiIndex):
            # MultiIndex: levels are (Price, Ticker) — e.g. ('Close', 'AAPL')
            available_tickers = data.columns.get_level_values(1).unique()
            if ticker not in available_tickers:
                return None
            # Slice: get all price columns for this ticker
            df = data.xs(ticker, level=1, axis=1)
            available = [c for c in cols if c in df.columns]
            df = df[available].dropna(how="all")
        else:
            # Flat columns (single ticker download)
            available = [c for c in cols if c in data.columns]
            df = data[available].dropna(how="all")
        return df if not df.empty else None
    except Exception:
        return None


def _batch_fetch_ohlcv(universe: list) -> tuple:
    """Batch-download daily and intraday OHLCV for all tickers at once.

    Returns (daily_dict, intraday_dict) where each maps ticker -> DataFrame.
    Falls back gracefully if batch download fails.
    """
    import yfinance as yf
    from config import settings

    daily_dict = {}
    intraday_dict = {}
    cols = ["Open", "High", "Low", "Close", "Volume"]

    # Batch daily download (1 API call for all tickers)
    try:
        period = getattr(settings, "YFINANCE_DAILY_PERIOD", "1y")
        data = yf.download(universe, period=period, interval="1d",
                           auto_adjust=True, threads=True, progress=False)
        if data is not None and not data.empty:
            for ticker in universe:
                df = _extract_ticker_from_batch(data, ticker, cols)
                if df is not None and len(df) >= 20:
                    daily_dict[ticker] = df
    except Exception as e:
        logger.warning("Batch daily download failed: %s", e)

    # Batch intraday download (1 API call for all tickers)
    try:
        intra_period = getattr(settings, "YFINANCE_INTRADAY_PERIOD", "5d")
        intra_interval = getattr(settings, "YFINANCE_INTRADAY_INTERVAL", "1m")
        data = yf.download(universe, period=intra_period, interval=intra_interval,
                           auto_adjust=True, threads=True, progress=False, prepost=True)
        if data is not None and not data.empty:
            for ticker in universe:
                df = _extract_ticker_from_batch(data, ticker, cols)
                if df is not None:
                    intraday_dict[ticker] = df
    except Exception as e:
        logger.warning("Batch intraday download failed: %s", e)

    logger.info("Batch fetch: %d/%d daily, %d/%d intraday",
                len(daily_dict), len(universe), len(intraday_dict), len(universe))
    return daily_dict, intraday_dict


def _prewarm_imports():
    """Pre-load heavy modules before spawning threads.

    Python's import lock serializes imports across threads.
    Loading everything upfront avoids 12 threads fighting over it.
    """
    try:
        import joblib  # noqa
        import numpy  # noqa
        from analysis.ml.feature_engine import build_features, FEATURE_COLS  # noqa
        from analysis.ml.predictor import predict_ticker  # noqa
        from analysis.quant_formulas import compute_quant_signals  # noqa
        from analysis.physics.kinematics import compute_kinematics  # noqa
        from analysis.scoring.regime_classifier import classify_stock_regime  # noqa
        from analysis.technical.cvd import get_cvd_signal  # noqa
        from analysis.technical.obv import detect_obv_divergence  # noqa
        from analysis.technical.candlestick import detect_all_patterns  # noqa
        from analysis.physics.ou_process import get_ou_score  # noqa
        from analysis.physics.hurst import get_hurst_score  # noqa
        from analysis.physics.entropy import get_predictability_score  # noqa
        from analysis.physics.kalman import get_kalman_score  # noqa
        from analysis.statistical.garch import get_garch_score  # noqa
        from analysis.statistical.zscore import get_zscore_signal  # noqa
        from analysis.statistical.gbm_monte_carlo import get_gbm_score  # noqa

        # Pre-load the ML models into the cache (avoids 12 threads hitting disk)
        from analysis.ml.predictor import _get_cached_models
        _get_cached_models("universal")
    except Exception:
        pass


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

    # Pre-warm imports and ML models BEFORE spawning threads
    # Python's import lock serializes threaded imports — this avoids the 15s+ penalty
    _prewarm_imports()

    # Pre-warm all shared data concurrently (parallel fetches)
    shared = _prefetch_shared_data(asset_class)
    macro_regime = shared.get("macro", "NEUTRAL")
    reddit_data = shared.get("reddit", {})
    short_data = {}
    political_pulse = shared.get("political", {})
    war_watch = shared.get("war", {})
    influencer_pulse = shared.get("influencer", {})

    # Batch download all OHLCV data upfront (2 API calls instead of 192)
    daily_dict, intraday_dict = _batch_fetch_ohlcv(universe)

    results = []
    success_count = 0
    fail_count = 0

    # For crypto: pass BTC daily data for correlation computation
    btc_daily = daily_dict.get("BTC-USD") if asset_class == "crypto" else None

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {
            pool.submit(
                _analyze_ticker, ticker, macro_regime, reddit_data, short_data,
                political_pulse, war_watch, influencer_pulse, asset_class,
                daily_dict.get(ticker), intraday_dict.get(ticker), btc_daily
            ): ticker
            for ticker in universe
        }
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result(timeout=45)
                if result:
                    results.append(result)
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                fail_count += 1
                logger.debug("Ticker %s failed: %s", ticker, e)

    logger.info("Scan %s: %d scored, %d failed, %d total",
                asset_class, success_count, fail_count, len(universe))

    # Flush buffered prediction history (one disk write instead of N)
    try:
        from analysis.ml.predictor import flush_pred_history
        flush_pred_history()
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
