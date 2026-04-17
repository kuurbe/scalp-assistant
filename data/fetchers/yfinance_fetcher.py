"""
yfinance data fetcher — OHLCV, options, ticker info, pre-market.
Uses the yfinance library for all Yahoo Finance data.
"""
from __future__ import annotations
import logging
import threading
import time
import pandas as pd
import yfinance as yf

from data.cache import cached
from config import settings

logger = logging.getLogger(__name__)

# yfinance maintains a shared SQLite cache (~/Library/Caches/py-yfinance/tkr-tz.db,
# cookies.db) that is NOT safe for concurrent access from ThreadPoolExecutor workers.
# Symptoms without this lock:
#   - OperationalError('unable to open database file')
#   - 'NoneType' object is not subscriptable
# Both bubble up from inside yfinance's cookie/timezone lookup path when two threads
# race on the SQLite file. Serializing cache-touching calls eliminates both.
# The actual HTTP fetch is NOT held under the lock — we release before network I/O
# by using yfinance's normal API (which reads cache briefly, then fetches).
_YF_CACHE_LOCK = threading.Lock()


def _safe_ticker(symbol: str):
    """Create a yf.Ticker under the cache lock to avoid SQLite contention."""
    with _YF_CACHE_LOCK:
        return yf.Ticker(symbol)


def _safe_history(ticker_obj, **kwargs) -> "pd.DataFrame | None":
    """
    Call Ticker.history() with lock + retry on transient SQLite errors.
    Returns None on permanent failure.
    """
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with _YF_CACHE_LOCK:
                df = ticker_obj.history(**kwargs)
            return df
        except Exception as e:
            msg = str(e).lower()
            # Transient SQLite-related failures: brief backoff + retry
            if "database" in msg or "subscriptable" in msg or "locked" in msg:
                last_err = e
                time.sleep(0.1 * (attempt + 1))
                continue
            raise
    if last_err:
        logger.debug("history() giving up after 3 retries: %s", last_err)
    return None


def safe_yf_download(tickers, **kwargs):
    """
    Thread-safe drop-in replacement for `yfinance.download()`.

    Fixes:
      - Forces threads=False so yf.download doesn't spawn its own threads
        that would race on the SQLite cookie/tz cache.
      - Holds _YF_CACHE_LOCK for the duration of the call.
      - Silences progress and retries once on transient SQLite errors.

    Use this from ANY module that was previously calling yf.download()
    directly. Same return type as yf.download.
    """
    import yfinance as _yf
    # Force single-threaded fetch — parallel HTTP fetches are fine at the
    # application level (app uses ThreadPoolExecutor), but yfinance's internal
    # thread pool collides with the cache.
    kwargs.setdefault("threads", False)
    kwargs.setdefault("progress", False)

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with _YF_CACHE_LOCK:
                return _yf.download(tickers, **kwargs)
        except Exception as e:
            msg = str(e).lower()
            if "database" in msg or "subscriptable" in msg or "locked" in msg:
                last_err = e
                time.sleep(0.2 * (attempt + 1))
                continue
            raise
    if last_err:
        logger.warning("safe_yf_download failed after 3 retries: %s", last_err)
    return None


@cached(ttl=settings.CACHE_TTL_SECONDS)
def get_daily_ohlcv(ticker: str, period: str = None) -> pd.DataFrame | None:
    """
    Fetch daily OHLCV data for a ticker.

    Args:
        ticker: Stock symbol (e.g. "AAPL").
        period: yfinance period string. Defaults to settings.YFINANCE_DAILY_PERIOD.

    Returns:
        DataFrame with Open, High, Low, Close, Volume columns, or None on failure.
    """
    if period is None:
        period = settings.YFINANCE_DAILY_PERIOD
    try:
        t = _safe_ticker(ticker)
        df = _safe_history(t, period=period, interval="1d", auto_adjust=True)
        if df is None or df.empty:
            logger.warning("No daily data returned for %s", ticker)
            return None
        # Keep only the standard OHLCV columns
        cols = ["Open", "High", "Low", "Close", "Volume"]
        df = df[[c for c in cols if c in df.columns]]
        return df
    except Exception as e:
        logger.error("get_daily_ohlcv(%s) failed: %s", ticker, e)
        return None


@cached(ttl=60)
def get_intraday_ohlcv(
    ticker: str,
    period: str = None,
    interval: str = None,
) -> pd.DataFrame | None:
    """
    Fetch intraday OHLCV data including pre/post market.

    Args:
        ticker: Stock symbol.
        period: yfinance period string. Defaults to settings.YFINANCE_INTRADAY_PERIOD.
        interval: Bar size. Defaults to settings.YFINANCE_INTRADAY_INTERVAL.

    Returns:
        DataFrame with OHLCV columns (includes pre/post market bars), or None.
    """
    if period is None:
        period = settings.YFINANCE_INTRADAY_PERIOD
    if interval is None:
        interval = settings.YFINANCE_INTRADAY_INTERVAL
    try:
        # Auto-detect: disable prepost for crypto/forex (meaningless for 24/7 markets)
        use_prepost = not (ticker.endswith("-USD") or "=X" in ticker or ticker == "DX-Y.NYB")
        t = _safe_ticker(ticker)
        df = _safe_history(
            t,
            period=period,
            interval=interval,
            prepost=use_prepost,
            auto_adjust=True,
        )
        if df is None or df.empty:
            logger.warning("No intraday data returned for %s", ticker)
            return None
        cols = ["Open", "High", "Low", "Close", "Volume"]
        df = df[[c for c in cols if c in df.columns]]
        return df
    except Exception as e:
        logger.error("get_intraday_ohlcv(%s) failed: %s", ticker, e)
        return None


@cached(ttl=settings.CACHE_TTL_SECONDS)
def get_ticker_info(ticker: str) -> dict | None:
    """
    Fetch key fundamental / reference data for a ticker.

    Returns:
        Dict with shortRatio, shortPercentOfFloat, marketCap, sector,
        fiftyTwoWeekHigh, fiftyTwoWeekLow, averageVolume, currentPrice.
    """
    fields = [
        "shortRatio",
        "shortPercentOfFloat",
        "marketCap",
        "sector",
        "fiftyTwoWeekHigh",
        "fiftyTwoWeekLow",
        "averageVolume",
        "currentPrice",
    ]
    try:
        t = _safe_ticker(ticker)
        with _YF_CACHE_LOCK:
            info = t.info or {}
        result = {f: info.get(f) for f in fields}
        return result
    except Exception as e:
        logger.error("get_ticker_info(%s) failed: %s", ticker, e)
        return None


@cached(ttl=settings.CACHE_TTL_SECONDS)
def get_options_chain(ticker: str) -> dict | None:
    """
    Fetch the options chain for the nearest expiration date.

    Returns:
        Dict with keys 'expiry' (str), 'calls' (DataFrame), 'puts' (DataFrame),
        or None on failure.
    """
    try:
        t = _safe_ticker(ticker)
        with _YF_CACHE_LOCK:
            expirations = t.options
        if not expirations:
            logger.warning("No options expirations for %s", ticker)
            return None
        nearest = expirations[0]
        with _YF_CACHE_LOCK:
            chain = t.option_chain(nearest)
        return {
            "expiry": nearest,
            "calls": chain.calls,
            "puts": chain.puts,
        }
    except Exception as e:
        logger.error("get_options_chain(%s) failed: %s", ticker, e)
        return None


@cached(ttl=settings.CACHE_TTL_SECONDS)
def batch_download(
    tickers: list[str],
    period: str = None,
    interval: str = "1d",
) -> dict[str, pd.DataFrame] | None:
    """
    Download OHLCV data for multiple tickers in a single call.

    Args:
        tickers: List of stock symbols.
        period: yfinance period string. Defaults to settings.YFINANCE_DAILY_PERIOD.
        interval: Bar size (default "1d").

    Returns:
        Dict mapping ticker -> DataFrame, or None on failure.
    """
    if period is None:
        period = settings.YFINANCE_DAILY_PERIOD
    try:
        data = safe_yf_download(
            tickers,
            period=period,
            interval=interval,
            group_by="ticker",
            auto_adjust=True,
        )
        if data is None or data.empty:
            logger.warning("batch_download returned no data")
            return None

        result: dict[str, pd.DataFrame] = {}
        cols = ["Open", "High", "Low", "Close", "Volume"]

        if len(tickers) == 1:
            # yf.download returns flat columns for a single ticker
            ticker = tickers[0]
            available = [c for c in cols if c in data.columns]
            df = data[available].dropna(how="all")
            if not df.empty:
                result[ticker] = df
        else:
            for ticker in tickers:
                try:
                    df = data[ticker]
                    available = [c for c in cols if c in df.columns]
                    df = df[available].dropna(how="all")
                    if not df.empty:
                        result[ticker] = df
                except (KeyError, TypeError):
                    logger.debug("No data for %s in batch download", ticker)

        return result if result else None
    except Exception as e:
        logger.error("batch_download failed: %s", e)
        return None


@cached(ttl=60)
def get_pre_market_data(ticker: str) -> dict | None:
    """
    Fetch pre-market price, change, and volume.

    Returns:
        Dict with preMarketPrice, preMarketChange, preMarketVolume,
        or None on failure.
    """
    try:
        t = _safe_ticker(ticker)
        with _YF_CACHE_LOCK:
            info = t.info or {}

        pre_price = info.get("preMarketPrice")
        regular_price = info.get("regularMarketPreviousClose")

        pre_change = None
        if pre_price is not None and regular_price is not None and regular_price != 0:
            pre_change = round((pre_price - regular_price) / regular_price * 100, 2)

        # Pre-market volume is not always available; fall back to None
        pre_volume = info.get("preMarketVolume")

        return {
            "preMarketPrice": pre_price,
            "preMarketChange": pre_change,
            "preMarketVolume": pre_volume,
        }
    except Exception as e:
        logger.error("get_pre_market_data(%s) failed: %s", ticker, e)
        return None
