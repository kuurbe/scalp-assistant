#!/usr/bin/env python3
"""
TV Snapshot Collector — daily TradingView indicator snapshots.

Captures RSI, MACD, Stochastic, Bollinger, ADX, Volume from TradingView
for top tickers and stores to CSV. After ~90 days of collection, this data
can train models directly on TV-sourced values instead of computed equivalents.

Usage:
    python3 -m scripts.collect_tv_snapshots              # collect for top 20 tickers
    python3 -m scripts.collect_tv_snapshots --tickers SPY NVDA TSLA
    python3 -m scripts.collect_tv_snapshots --dry-run    # show what would be collected

Schedule: weekdays at 4:05 PM ET (after market close).
"""
import argparse
import csv
import datetime
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("tv_snapshots")

SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "tv_snapshots.csv",
)

# Default top tickers for daily collection
DEFAULT_TICKERS = [
    "SPY", "QQQ", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META",
    "GOOGL", "AMD", "NFLX", "JPM", "V", "XOM", "COIN",
    "BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD", "XRP-USD",
]

SNAPSHOT_FIELDS = [
    "date", "ticker", "rsi", "macd_hist", "stoch_k",
    "bb_pct_b", "adx", "volume", "close",
]


def collect_snapshot(ticker: str) -> dict:
    """Collect a single ticker's TV indicator snapshot."""
    from signals.tradingview_bridge import get_tv_indicators, map_ticker_to_tv

    tv_symbol = map_ticker_to_tv(ticker)
    tv_vals = get_tv_indicators(ticker)

    if not tv_vals:
        return {}

    # Extract indicator values with flexible key matching
    def _get(keys, default=0.0):
        for k in keys:
            if k in tv_vals:
                try:
                    return float(tv_vals[k])
                except (ValueError, TypeError):
                    continue
        return default

    return {
        "date": datetime.date.today().isoformat(),
        "ticker": ticker,
        "rsi": round(_get(["RSI", "Relative Strength Index"]), 2),
        "macd_hist": round(_get(["Histogram", "MACD-hist", "Hist"]), 4),
        "stoch_k": round(_get(["Stoch %K", "%K", "Stochastic"]), 2),
        "bb_pct_b": 0.0,  # Not directly available from TV data window
        "adx": round(_get(["ADX", "Average Directional Index"]), 2),
        "volume": round(_get(["Volume", "Vol"]), 0),
        "close": round(_get(["Close", "Last", "close"]), 2),
    }


def collect_all(tickers: list, dry_run: bool = False) -> int:
    """Collect snapshots for all tickers and append to CSV."""
    from signals.tradingview_bridge import is_tv_available

    if not is_tv_available():
        log.error("TradingView not available (CDP not reachable). Exiting.")
        return 0

    delay_sec = getattr(settings, "TV_BATCH_DELAY_MS", 2000) / 1000.0
    collected = 0

    # Ensure data dir exists
    os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)

    # Check if file exists to determine if header needed
    write_header = not os.path.exists(SNAPSHOT_FILE)

    rows = []
    for i, ticker in enumerate(tickers):
        log.info("[%d/%d] Collecting %s...", i + 1, len(tickers), ticker)

        if dry_run:
            log.info("  (dry run — skipped)")
            collected += 1
            continue

        try:
            snapshot = collect_snapshot(ticker)
            if snapshot:
                rows.append(snapshot)
                collected += 1
                log.info("  RSI=%.1f MACD_Hist=%.4f Stoch=%.1f ADX=%.1f",
                         snapshot["rsi"], snapshot["macd_hist"],
                         snapshot["stoch_k"], snapshot["adx"])
            else:
                log.warning("  No data returned for %s", ticker)
        except Exception as e:
            log.warning("  Error collecting %s: %s", ticker, e)

        if i < len(tickers) - 1:
            time.sleep(delay_sec)

    # Write to CSV
    if rows and not dry_run:
        try:
            with open(SNAPSHOT_FILE, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=SNAPSHOT_FIELDS)
                if write_header:
                    writer.writeheader()
                writer.writerows(rows)
            log.info("Wrote %d snapshots to %s", len(rows), SNAPSHOT_FILE)
        except Exception as e:
            log.error("Failed to write snapshots: %s", e)

    return collected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TV Snapshot Collector")
    parser.add_argument("--tickers", nargs="+", default=None, help="Specific tickers to collect")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be collected")
    args = parser.parse_args()

    tickers = args.tickers or DEFAULT_TICKERS
    log.info("Collecting TV snapshots for %d tickers", len(tickers))

    count = collect_all(tickers, dry_run=args.dry_run)
    log.info("Done. Collected %d/%d snapshots.", count, len(tickers))
