"""
FINRA short volume fetcher — daily RegSHO short sale data.
Downloads the daily consolidated short volume file from FINRA.
"""
from __future__ import annotations
import io
import logging
from datetime import datetime, timedelta

import requests

from data.cache import cached
from config import settings

logger = logging.getLogger(__name__)

FINRA_SHORT_URL = (
    "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date}.txt"
)


def _get_trade_date(date: str | None = None) -> str:
    """
    Return the target trade date in YYYYMMDD format.
    Defaults to the most recent weekday (yesterday, skipping weekends).

    Args:
        date: Optional date string in YYYYMMDD format.

    Returns:
        Date string in YYYYMMDD format.
    """
    if date:
        return date

    today = datetime.utcnow().date()
    # Default to yesterday
    target = today - timedelta(days=1)
    # Skip weekends: Saturday -> Friday, Sunday -> Friday
    if target.weekday() == 5:  # Saturday
        target = target - timedelta(days=1)
    elif target.weekday() == 6:  # Sunday
        target = target - timedelta(days=2)
    return target.strftime("%Y%m%d")


@cached(ttl=3600)  # Cache the full day's file for 1 hour
def _fetch_daily_file(date_str: str) -> dict[str, dict] | None:
    """
    Download and parse the full FINRA daily short volume file.

    Args:
        date_str: Date in YYYYMMDD format.

    Returns:
        Dict mapping ticker -> {short_volume, total_volume, short_ratio},
        or None on failure.
    """
    url = FINRA_SHORT_URL.format(date=date_str)
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to fetch FINRA file for %s: %s", date_str, e)
        # If the requested date failed (maybe holiday), try one day earlier
        try:
            dt = datetime.strptime(date_str, "%Y%m%d").date()
            fallback = dt - timedelta(days=1)
            if fallback.weekday() == 6:  # Sunday
                fallback = fallback - timedelta(days=2)
            elif fallback.weekday() == 5:  # Saturday
                fallback = fallback - timedelta(days=1)
            fallback_str = fallback.strftime("%Y%m%d")
            fallback_url = FINRA_SHORT_URL.format(date=fallback_str)
            resp = requests.get(fallback_url, timeout=15)
            resp.raise_for_status()
            logger.info("Used fallback date %s for FINRA data", fallback_str)
        except requests.RequestException as e2:
            logger.error("FINRA fallback also failed: %s", e2)
            return None

    try:
        data: dict[str, dict] = {}
        text = resp.text

        for line in text.strip().split("\n"):
            # Skip header row
            if line.startswith("Date") or not line.strip():
                continue

            parts = line.split("|")
            if len(parts) < 5:
                continue

            # Format: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
            symbol = parts[1].strip().upper()
            try:
                short_vol = int(parts[2].strip())
                short_exempt = int(parts[3].strip())
                total_vol = int(parts[4].strip())
            except (ValueError, IndexError):
                continue

            total_short = short_vol + short_exempt

            # Aggregate across markets (some tickers appear multiple times)
            if symbol in data:
                data[symbol]["short_volume"] += total_short
                data[symbol]["total_volume"] += total_vol
            else:
                data[symbol] = {
                    "short_volume": total_short,
                    "total_volume": total_vol,
                }

        # Compute ratios after aggregation
        for symbol, entry in data.items():
            total = entry["total_volume"]
            entry["short_ratio"] = round(
                entry["short_volume"] / total, 4
            ) if total > 0 else 0.0

        return data if data else None
    except Exception as e:
        logger.error("Failed to parse FINRA short volume file: %s", e)
        return None


@cached(ttl=settings.CACHE_TTL_SECONDS)
def get_short_volume(ticker: str, date: str | None = None) -> dict | None:
    """
    Get short volume data for a specific ticker.

    Args:
        ticker: Stock symbol (e.g. "AAPL").
        date: Optional date in YYYYMMDD format. Defaults to most recent
              trading day (yesterday, skipping weekends).

    Returns:
        Dict with:
            short_volume (int): Total short volume for the day
            total_volume (int): Total volume for the day
            short_ratio (float): short_volume / total_volume
            date (str): The date of the data in YYYYMMDD format
        Returns None on failure or if ticker not found.
    """
    date_str = _get_trade_date(date)
    daily_data = _fetch_daily_file(date_str)

    if daily_data is None:
        return None

    ticker_upper = ticker.upper()
    entry = daily_data.get(ticker_upper)

    if entry is None:
        logger.debug("Ticker %s not found in FINRA data for %s", ticker, date_str)
        return None

    return {
        "short_volume": entry["short_volume"],
        "total_volume": entry["total_volume"],
        "short_ratio": entry["short_ratio"],
        "date": date_str,
    }
