"""
yfinance data fetcher — OHLCV, options, ticker info, pre-market.
Uses the yfinance library for all Yahoo Finance data.
"""
from __future__ import annotations
import logging
import pandas as pd
import yfinance as yf

from data.cache import cached
from config import settings

logger = logging.getLogger(__name__)


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
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval="1d", auto_adjust=True)
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
        t = yf.Ticker(ticker)
        df = t.history(
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
        t = yf.Ticker(ticker)
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
        t = yf.Ticker(ticker)
        expirations = t.options
        if not expirations:
            logger.warning("No options expirations for %s", ticker)
            return None
        nearest = expirations[0]
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
        data = yf.download(
            tickers,
            period=period,
            interval=interval,
            group_by="ticker",
            auto_adjust=True,
            threads=True,
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
        t = yf.Ticker(ticker)
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
