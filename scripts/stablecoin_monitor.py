"""
Stablecoin Depeg Monitor — lightweight module for detecting stablecoin price deviations.

Runs on the crypto scan loop. Alerts on deviations from $1.00 peg.
No full scoring pipeline — just price + volume checks.

Usage:
    python3 -m scripts.stablecoin_monitor --test   # print current prices
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings

log = logging.getLogger("stablecoin_monitor")


def scan_stablecoins() -> list:
    """Batch-fetch stablecoin prices and detect depeg events.

    Returns list of dicts for coins above warning threshold:
    [{"ticker": "USDT-USD", "price": 0.994, "deviation": 0.006,
      "severity": "WARN", "volume_spike": 2.1}, ...]
    """
    from data.fetchers.yfinance_fetcher import safe_yf_download

    universe = settings.STABLECOIN_UNIVERSE
    if not universe:
        return []

    events = []

    try:
        data = safe_yf_download(universe, period="8d", interval="1d",
                                auto_adjust=True)
        if data is None or data.empty:
            return []

        import pandas as pd
        is_multi = isinstance(data.columns, pd.MultiIndex)

        for ticker in universe:
            try:
                if is_multi:
                    available = data.columns.get_level_values(1).unique()
                    if ticker not in available:
                        continue
                    close = data.xs(ticker, level=1, axis=1)["Close"].dropna()
                    volume = data.xs(ticker, level=1, axis=1)["Volume"].dropna()
                else:
                    close = data["Close"].dropna()
                    volume = data["Volume"].dropna()

                if len(close) < 2:
                    continue

                price = float(close.iloc[-1])
                deviation = abs(price - settings.STABLECOIN_PEG_PRICE)

                # Classify severity
                if deviation >= settings.STABLECOIN_EMERGENCY_DEVIATION:
                    severity = "EMERGENCY"
                elif deviation >= settings.STABLECOIN_ALERT_DEVIATION:
                    severity = "ALERT"
                elif deviation >= settings.STABLECOIN_WARN_DEVIATION:
                    severity = "WARN"
                else:
                    continue  # Within normal range

                # Volume spike detection
                volume_spike = 1.0
                if len(volume) > 2:
                    avg_vol = float(volume.iloc[:-1].mean())
                    today_vol = float(volume.iloc[-1])
                    if avg_vol > 0:
                        volume_spike = round(today_vol / avg_vol, 1)

                events.append({
                    "ticker": ticker,
                    "name": ticker.replace("-USD", ""),
                    "price": round(price, 4),
                    "deviation": round(deviation, 4),
                    "deviation_pct": round(deviation / settings.STABLECOIN_PEG_PRICE * 100, 2),
                    "severity": severity,
                    "volume_spike": volume_spike,
                    "direction": "ABOVE" if price > settings.STABLECOIN_PEG_PRICE else "BELOW",
                })

            except Exception:
                continue

    except Exception as e:
        log.warning("Stablecoin scan failed: %s", e)

    # Sort by severity (EMERGENCY first)
    severity_order = {"EMERGENCY": 0, "ALERT": 1, "WARN": 2}
    events.sort(key=lambda x: severity_order.get(x["severity"], 3))
    return events


def format_stablecoin_alert(event: dict) -> str:
    """Format a stablecoin depeg alert as Telegram HTML."""
    severity = event["severity"]
    emoji = {"EMERGENCY": "🚨", "ALERT": "🔴", "WARN": "🟡"}.get(severity, "⚪")
    name = event["name"]
    price = event["price"]
    dev_pct = event["deviation_pct"]
    direction = event["direction"]
    vol_spike = event["volume_spike"]

    vol_line = f"  Volume: {vol_spike:.1f}x avg" if vol_spike > 1.5 else ""

    return (
        f"{emoji} <b>DEPEG {severity} — {name}</b>\n"
        f"  Price: <code>${price:.4f}</code> ({direction} peg by {dev_pct:.2f}%)\n"
        f"  Peg: $1.0000{vol_line}"
    )


def dispatch_stablecoin_alerts(events: list) -> None:
    """Send stablecoin depeg alerts to the crypto Telegram channel."""
    if not events:
        return

    try:
        from signals.notifier import send_telegram
        import datetime
        from zoneinfo import ZoneInfo

        crypto_chat = settings.get_secret("TELEGRAM_CRYPTO_CHAT_ID")

        et = ZoneInfo("America/New_York")
        now = datetime.datetime.now(et).strftime("%b %d, %I:%M %p ET")

        msg = f"📡 <b>Stablecoin Monitor</b> — {now}\n{'━' * 30}\n"
        for event in events:
            msg += "\n" + format_stablecoin_alert(event)

        msg += f"\n\n{'━' * 30}\n⚠️ <i>Monitor only — verify on-chain before acting.</i>"
        send_telegram(msg, chat_id=crypto_chat)
        log.info("Sent %d stablecoin depeg alerts", len(events))

    except Exception as e:
        log.warning("Failed to send stablecoin alerts: %s", e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Stablecoin Depeg Monitor")
    parser.add_argument("--test", action="store_true", help="Print current stablecoin prices")
    args = parser.parse_args()

    if args.test:
        print("Scanning stablecoins...")
        events = scan_stablecoins()
        if events:
            for e in events:
                print(format_stablecoin_alert(e).replace("<b>", "").replace("</b>", "")
                      .replace("<code>", "").replace("</code>", "")
                      .replace("<i>", "").replace("</i>", ""))
        else:
            print("All stablecoins within normal range (±0.5% of $1.00)")
    else:
        events = scan_stablecoins()
        dispatch_stablecoin_alerts(events)
