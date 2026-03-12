#!/usr/bin/env python3
"""
Scalp Assistant — Headless Live Scanner
Runs continuously on a cloud VM (Oracle/AWS/etc.) with NO terminal UI.
Scans every N minutes during market hours, sends Telegram alerts only.

Usage:
    python3 -m scripts.live_scanner                    # default: scan every 15 min
    python3 -m scripts.live_scanner --interval 10      # scan every 10 min
    python3 -m scripts.live_scanner --asset crypto     # crypto only (24/7)
    python3 -m scripts.live_scanner --test             # send test alert and exit
"""
import argparse
import datetime
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

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
        from datetime import timezone, timedelta
        et = timezone(timedelta(hours=-5))  # EST (close enough for trading hours)
        now = datetime.datetime.now(et)
        weekday = now.weekday()  # Mon=0, Sun=6
        hour = now.hour
        minute = now.minute

        if weekday >= 5:
            return False  # Weekend
        if hour < 9 or (hour == 9 and minute < 0):
            return False  # Before 9 AM
        if hour > 16 or (hour == 16 and minute > 30):
            return False  # After 4:30 PM
        return True
    except Exception:
        return True  # Default to scanning if timezone calc fails


def is_crypto_hours() -> bool:
    """Crypto trades 24/7 but we limit scans to avoid noise."""
    try:
        from datetime import timezone, timedelta
        et = timezone(timedelta(hours=-5))
        now = datetime.datetime.now(et)
        # Skip 1 AM - 5 AM ET (lowest volume, least actionable)
        return not (1 <= now.hour < 5)
    except Exception:
        return True


def run_loop(interval_minutes: int = 15, asset_classes: list = None):
    """
    Main loop — scans at regular intervals during market hours.
    Sends alerts to Telegram. No terminal UI.
    """
    if not asset_classes:
        asset_classes = ["stocks", "etfs", "crypto"]

    crypto_only = asset_classes == ["crypto"]

    log.info("=" * 50)
    log.info("Scalp Assistant Live Scanner started")
    log.info("  Interval: %d minutes", interval_minutes)
    log.info("  Assets: %s", ", ".join(asset_classes))
    log.info("  Telegram: %s", "configured" if os.environ.get("TELEGRAM_BOT_TOKEN") else "NOT SET")
    log.info("=" * 50)

    # Send startup notification
    try:
        from signals.notifier import send_telegram
        send_telegram(
            f"🟢 <b>Scalp Assistant Live Scanner</b>\n"
            f"Started at {datetime.datetime.now().strftime('%b %d, %I:%M %p')}\n"
            f"Scanning: {', '.join(asset_classes)} every {interval_minutes} min"
        )
    except Exception:
        pass

    scan_count = 0
    consecutive_errors = 0

    while True:
        try:
            now = datetime.datetime.now()

            # Determine what to scan this cycle
            scan_these = []

            if crypto_only:
                if is_crypto_hours():
                    scan_these = ["crypto"]
            else:
                if is_market_hours():
                    scan_these = [ac for ac in asset_classes if ac != "crypto"]
                if "crypto" in asset_classes and is_crypto_hours():
                    scan_these.append("crypto")

            if not scan_these:
                log.info("Outside trading hours — sleeping %d min", interval_minutes)
                time.sleep(interval_minutes * 60)
                continue

            # Run the scan
            scan_count += 1
            log.info("─" * 40)
            log.info("Scan #%d — %s — %s", scan_count, now.strftime("%I:%M %p"), ", ".join(scan_these))

            run_full_scan(scan_these)

            consecutive_errors = 0
            log.info("Scan #%d complete — sleeping %d min", scan_count, interval_minutes)

        except Exception as e:
            consecutive_errors += 1
            log.error("Scan error (#%d consecutive): %s", consecutive_errors, e)

            # If too many consecutive errors, alert and back off
            if consecutive_errors >= 3:
                try:
                    from signals.notifier import send_telegram
                    send_telegram(
                        f"⚠️ <b>Scanner Error</b>\n"
                        f"{consecutive_errors} consecutive failures\n"
                        f"Last error: {str(e)[:200]}"
                    )
                except Exception:
                    pass

            # Exponential backoff on errors (max 30 min)
            backoff = min(interval_minutes * consecutive_errors, 30)
            log.info("Backing off %d min", backoff)
            time.sleep(backoff * 60)
            continue

        # Sleep until next cycle
        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scalp Assistant — Headless Live Scanner")
    parser.add_argument("--interval", type=int, default=15, help="Scan interval in minutes (default: 15)")
    parser.add_argument("--asset", type=str, default=None, help="Single asset class (stocks, etfs, crypto)")
    parser.add_argument("--test", action="store_true", help="Send test alert and exit")
    args = parser.parse_args()

    if args.test:
        send_test_alert()
    elif args.asset:
        run_loop(interval_minutes=args.interval, asset_classes=[args.asset])
    else:
        run_loop(interval_minutes=args.interval)
