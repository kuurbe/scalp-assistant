#!/usr/bin/env python3
"""
Scalp Assistant — Headless Live Scanner
Runs continuously on a cloud VM (Oracle/AWS/etc.) with NO terminal UI.

Dual-loop architecture:
  - Stock/ETF loop: scans every 15 min during market hours
  - Crypto loop: scans every 5 min, 24/7

Crypto alerts route to a separate Telegram channel (TELEGRAM_CRYPTO_CHAT_ID).

Usage:
    python3 -m scripts.live_scanner                    # default: stocks + etfs + crypto
    python3 -m scripts.live_scanner --interval 10      # stock scan every 10 min
    python3 -m scripts.live_scanner --asset crypto     # crypto only (24/7)
    python3 -m scripts.live_scanner --test             # send test alert and exit
"""
import argparse
import datetime
import logging
import os
import sys
import threading
import time
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from config import settings
from scripts.scan_and_alert import run_full_scan, send_test_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("live_scanner")


def is_market_hours() -> bool:
    """Check if US markets are open (9:00 AM - 4:30 PM ET, Mon-Fri)."""
    try:
        et = ZoneInfo("America/New_York")
        now = datetime.datetime.now(et)
        weekday = now.weekday()
        hour = now.hour
        minute = now.minute

        if weekday >= 5:
            return False
        if hour < 9:
            return False
        if hour > 16 or (hour == 16 and minute > 30):
            return False
        return True
    except Exception:
        return True


def _send_startup_notification(asset_classes: list, stock_interval: int, crypto_interval: int):
    """Send startup notification to relevant Telegram channels."""
    try:
        from signals.notifier import send_telegram
        now_str = datetime.datetime.now().strftime('%b %d, %I:%M %p')

        has_crypto = "crypto" in asset_classes
        stock_classes = [ac for ac in asset_classes if ac != "crypto"]

        # Notify default channel
        if stock_classes:
            send_telegram(
                f"🟢 <b>Scalp Assistant Live Scanner</b>\n"
                f"Started at {now_str}\n"
                f"Scanning: {', '.join(stock_classes)} every {stock_interval} min (market hours)"
            )

        # Notify crypto channel
        if has_crypto:
            crypto_chat = settings.get_secret("TELEGRAM_CRYPTO_CHAT_ID")
            send_telegram(
                f"🟢 <b>Scalp Assistant Crypto Scanner</b>\n"
                f"Started at {now_str}\n"
                f"Scanning: crypto every {crypto_interval} min (24/7)\n"
                f"Stablecoin depeg monitoring: active",
                chat_id=crypto_chat,
            )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
#  Stock/ETF Loop — market hours only
# ─────────────────────────────────────────────────────────────

def _stock_loop(interval_minutes: int, asset_classes: list):
    """Main loop for stocks/ETFs. Runs during market hours only."""
    scan_count = 0
    consecutive_errors = 0

    while True:
        try:
            if not is_market_hours():
                log.info("[Stocks] Outside market hours — sleeping %d min", interval_minutes)
                time.sleep(interval_minutes * 60)
                continue

            scan_count += 1
            now = datetime.datetime.now()
            log.info("─" * 40)
            log.info("[Stocks] Scan #%d — %s — %s", scan_count, now.strftime("%I:%M %p"), ", ".join(asset_classes))

            run_full_scan(asset_classes)

            consecutive_errors = 0
            log.info("[Stocks] Scan #%d complete — sleeping %d min", scan_count, interval_minutes)

        except Exception as e:
            consecutive_errors += 1
            log.error("[Stocks] Scan error (#%d): %s", consecutive_errors, e)

            if consecutive_errors >= 3:
                try:
                    from signals.notifier import send_telegram
                    send_telegram(
                        f"⚠️ <b>Stock Scanner Error</b>\n"
                        f"{consecutive_errors} consecutive failures\n"
                        f"Last error: {str(e)[:200]}"
                    )
                except Exception:
                    pass

            backoff = min(interval_minutes * consecutive_errors, 30)
            log.info("[Stocks] Backing off %d min", backoff)
            time.sleep(backoff * 60)
            continue

        time.sleep(interval_minutes * 60)


# ─────────────────────────────────────────────────────────────
#  Crypto Loop — 24/7, faster cycle
# ─────────────────────────────────────────────────────────────

def _crypto_loop(interval_minutes: int):
    """Crypto scanning loop. Runs 24/7 with its own interval."""
    scan_count = 0
    consecutive_errors = 0

    while True:
        try:
            scan_count += 1
            now = datetime.datetime.now()
            log.info("─" * 40)
            log.info("[Crypto] Scan #%d — %s", scan_count, now.strftime("%I:%M %p"))

            run_full_scan(["crypto"])

            consecutive_errors = 0
            log.info("[Crypto] Scan #%d complete — sleeping %d min", scan_count, interval_minutes)

        except Exception as e:
            consecutive_errors += 1
            log.error("[Crypto] Scan error (#%d): %s", consecutive_errors, e)

            if consecutive_errors >= 3:
                try:
                    from signals.notifier import send_telegram
                    crypto_chat = settings.get_secret("TELEGRAM_CRYPTO_CHAT_ID")
                    send_telegram(
                        f"⚠️ <b>Crypto Scanner Error</b>\n"
                        f"{consecutive_errors} consecutive failures\n"
                        f"Last error: {str(e)[:200]}",
                        chat_id=crypto_chat,
                    )
                except Exception:
                    pass

            backoff = min(interval_minutes * consecutive_errors, 15)
            log.info("[Crypto] Backing off %d min", backoff)
            time.sleep(backoff * 60)
            continue

        time.sleep(interval_minutes * 60)


# ─────────────────────────────────────────────────────────────
#  Scalp Monitoring Loop — 2 min cycle, hot list only
# ─────────────────────────────────────────────────────────────

def _scalp_loop(interval_seconds: int = None):
    """Fast inner loop monitoring scalp hot list tickers via TradingView.

    Runs every 2 minutes during market hours. Only checks tickers that the
    15-min scan identified as scalp-ready (IGNITION/ACCELERATION + volume).
    """
    interval = interval_seconds or getattr(settings, "SCALP_MONITOR_INTERVAL_SEC", 120)
    scan_count = 0
    consecutive_errors = 0

    while True:
        try:
            if not is_market_hours():
                time.sleep(interval)
                continue

            # Get hot list from the most recent stock scan
            try:
                from scripts.scan_and_alert import get_current_hot_list, _dispatch_scalp_alerts
            except ImportError:
                time.sleep(interval)
                continue

            hot_list = get_current_hot_list()
            if not hot_list:
                time.sleep(interval)
                continue

            scan_count += 1
            log.info("[Scalp] Monitor #%d — %d hot tickers", scan_count, len(hot_list))

            from signals.scalp_engine import monitor_hot_list
            setups = monitor_hot_list(hot_list)

            if setups:
                log.info("[Scalp] Found %d scalp entries", len(setups))
                _dispatch_scalp_alerts(setups)

            consecutive_errors = 0

        except Exception as e:
            consecutive_errors += 1
            log.error("[Scalp] Monitor error (#%d): %s", consecutive_errors, e)
            if consecutive_errors >= 5:
                log.warning("[Scalp] Too many errors, pausing 10 min")
                time.sleep(600)
                consecutive_errors = 0
                continue

        time.sleep(interval)


# ─────────────────────────────────────────────────────────────
#  Main entry — dual-loop orchestrator
# ─────────────────────────────────────────────────────────────

def run_loop(interval_minutes: int = None, asset_classes: list = None):
    """
    Main entry point. Launches dual loops:
      - Stock/ETF loop on the main thread (market hours, 15 min default)
      - Crypto loop on a daemon thread (24/7, 5 min default)

    If only crypto is requested, runs crypto on main thread.
    """
    if not asset_classes:
        asset_classes = ["stocks", "etfs", "crypto"]

    stock_interval = interval_minutes or settings.STOCK_SCAN_INTERVAL_MIN
    crypto_interval = getattr(settings, "CRYPTO_SCAN_INTERVAL_MIN", 5)

    has_crypto = "crypto" in asset_classes
    stock_classes = [ac for ac in asset_classes if ac != "crypto"]

    log.info("=" * 50)
    log.info("Scalp Assistant Live Scanner started")
    log.info("  Stock assets: %s (every %d min)", ", ".join(stock_classes) if stock_classes else "none", stock_interval)
    log.info("  Crypto: %s (every %d min, 24/7)", "enabled" if has_crypto else "disabled", crypto_interval)
    log.info("  Telegram default: %s", "configured" if os.environ.get("TELEGRAM_BOT_TOKEN") else "NOT SET")
    log.info("  Telegram crypto: %s", "configured" if os.environ.get("TELEGRAM_CRYPTO_CHAT_ID") else "using default")
    log.info("=" * 50)

    _send_startup_notification(asset_classes, stock_interval, crypto_interval)

    # Launch scalp monitoring loop if enabled
    scalp_enabled = getattr(settings, "SCALP_ENABLED", False) and stock_classes
    if scalp_enabled:
        scalp_thread = threading.Thread(
            target=_scalp_loop,
            daemon=True,
            name="scalp-monitor",
        )
        scalp_thread.start()
        log.info("Scalp monitor thread started (every %ds)", getattr(settings, "SCALP_MONITOR_INTERVAL_SEC", 120))

    if has_crypto and stock_classes:
        # Dual-loop: crypto on daemon thread, stocks on main thread
        crypto_thread = threading.Thread(
            target=_crypto_loop,
            args=(crypto_interval,),
            daemon=True,
            name="crypto-scanner",
        )
        crypto_thread.start()
        log.info("Crypto scanner thread started (daemon)")
        _stock_loop(stock_interval, stock_classes)

    elif has_crypto:
        # Crypto-only mode: run on main thread
        _crypto_loop(crypto_interval)

    else:
        # Stocks/ETFs only
        _stock_loop(stock_interval, stock_classes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scalp Assistant — Headless Live Scanner")
    parser.add_argument("--interval", type=int, default=None, help="Stock scan interval in minutes (default: from settings)")
    parser.add_argument("--asset", type=str, default=None, help="Single asset class (stocks, etfs, crypto)")
    parser.add_argument("--test", action="store_true", help="Send test alert and exit")
    args = parser.parse_args()

    if args.test:
        send_test_alert()
    elif args.asset:
        run_loop(interval_minutes=args.interval, asset_classes=[args.asset])
    else:
        run_loop(interval_minutes=args.interval)
