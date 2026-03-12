#!/usr/bin/env python3
"""
Scalp Assistant — Automated Scanner & Alert Dispatcher
Runs on a schedule (GitHub Actions or local cron) to scan all asset classes,
detect trade setups, and send Telegram alerts for:
  • Option plays (calls/puts) with strikes, expiry, budget
  • Day trade setups (high score + IGNITION/high volume)
  • Swing trade setups (trending regime + strong score)

Usage:
    python3 -m scripts.scan_and_alert                  # full scan
    python3 -m scripts.scan_and_alert --asset stocks    # stocks only
    python3 -m scripts.scan_and_alert --test            # send test alert
"""
import argparse
import datetime
import logging
import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from signals.notifier import send_telegram
from signals.recommendation import get_recommendation
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scanner")


# ─────────────────────────────────────────────────────────────
#  Alert formatting — clean Telegram HTML messages
# ─────────────────────────────────────────────────────────────

def _header() -> str:
    now = datetime.datetime.now().strftime("%b %d, %I:%M %p")
    return f"📡 <b>Scalp Assistant</b> — {now}\n{'━' * 30}"


def _format_option_alert(pick, rec: dict) -> str:
    """Format an options play alert (CALL or PUT)."""
    direction = pick.option_direction or "CALL"
    emoji = "🟢" if direction == "CALL" else "🔴"
    strike = pick.option_safe_strike or pick.price
    exp = pick.option_exp_long or pick.option_exp_short or "N/A"
    budget = pick.option_budget or "N/A"
    conf = rec.get("confidence", 0)

    # Support/resistance context
    levels = ""
    if pick.nearest_support > 0:
        levels = f"\n   Support: <code>${pick.nearest_support:.2f}</code>  |  Resistance: <code>${pick.nearest_resistance:.2f}</code>"

    # Risk/reward
    rr = ""
    if pick.entry_price > 0 and pick.risk_reward > 0:
        rr = f"\n   Entry: <code>${pick.entry_price:.2f}</code> → Stop: <code>${pick.stop_price:.2f}</code> → Target: <code>${pick.target_price:.2f}</code>  (R:R {pick.risk_reward:.1f}x)"

    reasons = rec.get("reasons", [])[:3]
    reasons_str = "\n".join(f"   • {r}" for r in reasons) if reasons else ""

    return (
        f"\n{emoji} <b>{direction} — {pick.ticker}</b>  (Score: {pick.composite_score:.0f})\n"
        f"   Strike: <code>${strike:.0f}</code>  |  Exp: {exp}  |  Budget: {budget}\n"
        f"   Price: <code>${pick.price:.2f}</code> ({pick.pct_change:+.1f}%)  |  Confidence: {conf}%\n"
        f"   Regime: {pick.regime}  |  Phase: {pick.kinematic_phase}  |  RVOL: {pick.rel_volume:.1f}x"
        f"{levels}{rr}"
        f"\n{reasons_str}" if reasons_str else
        f"\n{emoji} <b>{direction} — {pick.ticker}</b>  (Score: {pick.composite_score:.0f})\n"
        f"   Strike: <code>${strike:.0f}</code>  |  Exp: {exp}  |  Budget: {budget}\n"
        f"   Price: <code>${pick.price:.2f}</code> ({pick.pct_change:+.1f}%)  |  Confidence: {conf}%\n"
        f"   Regime: {pick.regime}  |  Phase: {pick.kinematic_phase}  |  RVOL: {pick.rel_volume:.1f}x"
        f"{levels}{rr}"
    )


def _format_day_trade(pick, rec: dict) -> str:
    """Format a day trade alert."""
    signal = rec.get("signal", "HOLD")
    conf = rec.get("confidence", 0)
    dir_emoji = "📈" if pick.direction == "LONG" else "📉"

    levels = ""
    if pick.entry_price > 0:
        levels = f"\n   Entry: <code>${pick.entry_price:.2f}</code> → Stop: <code>${pick.stop_price:.2f}</code> → Target: <code>${pick.target_price:.2f}</code>  (R:R {pick.risk_reward:.1f}x)"

    reasons = rec.get("reasons", [])[:2]
    reasons_str = "\n".join(f"   • {r}" for r in reasons) if reasons else ""

    return (
        f"\n{dir_emoji} <b>DAY TRADE — {pick.ticker}</b>  ({signal} {conf}%)\n"
        f"   Price: <code>${pick.price:.2f}</code> ({pick.pct_change:+.1f}%)  |  Score: {pick.composite_score:.0f}\n"
        f"   Phase: {pick.kinematic_phase}  |  RVOL: {pick.rel_volume:.1f}x  |  RSI: {pick.rsi:.0f}"
        f"{levels}"
        f"\n{reasons_str}" if reasons_str else
        f"\n{dir_emoji} <b>DAY TRADE — {pick.ticker}</b>  ({signal} {conf}%)\n"
        f"   Price: <code>${pick.price:.2f}</code> ({pick.pct_change:+.1f}%)  |  Score: {pick.composite_score:.0f}\n"
        f"   Phase: {pick.kinematic_phase}  |  RVOL: {pick.rel_volume:.1f}x  |  RSI: {pick.rsi:.0f}"
        f"{levels}"
    )


def _format_swing_trade(pick, rec: dict) -> str:
    """Format a swing trade alert."""
    signal = rec.get("signal", "HOLD")
    conf = rec.get("confidence", 0)
    dir_emoji = "🔵" if pick.direction == "LONG" else "🟠"

    # Swing trades show option play if available
    option_line = ""
    if pick.option_exp_short and pick.option_exp_short != "N/A":
        option_line = f"\n   Option: {pick.option_direction} <code>${pick.option_safe_strike:.0f}</code> exp {pick.option_exp_long}  |  Budget: {pick.option_budget}"

    levels = ""
    if pick.nearest_support > 0:
        levels = f"\n   Support: <code>${pick.nearest_support:.2f}</code>  |  Resistance: <code>${pick.nearest_resistance:.2f}</code>"

    reasons = rec.get("reasons", [])[:2]
    reasons_str = "\n".join(f"   • {r}" for r in reasons) if reasons else ""

    return (
        f"\n{dir_emoji} <b>SWING — {pick.ticker}</b>  ({signal} {conf}%)\n"
        f"   Price: <code>${pick.price:.2f}</code> ({pick.pct_change:+.1f}%)  |  Score: {pick.composite_score:.0f}\n"
        f"   Regime: {pick.regime}  |  Hurst: {pick.hurst:.2f}  |  RVOL: {pick.rel_volume:.1f}x"
        f"{option_line}{levels}"
        f"\n{reasons_str}" if reasons_str else
        f"\n{dir_emoji} <b>SWING — {pick.ticker}</b>  ({signal} {conf}%)\n"
        f"   Price: <code>${pick.price:.2f}</code> ({pick.pct_change:+.1f}%)  |  Score: {pick.composite_score:.0f}\n"
        f"   Regime: {pick.regime}  |  Hurst: {pick.hurst:.2f}  |  RVOL: {pick.rel_volume:.1f}x"
        f"{option_line}{levels}"
    )


# ─────────────────────────────────────────────────────────────
#  Classification — categorize each scored ticker
# ─────────────────────────────────────────────────────────────

def classify_setup(pick, rec: dict) -> list:
    """
    Classify a scored ticker into trade types.
    Returns list of: 'option_call', 'option_put', 'day_trade', 'swing'
    """
    types = []
    score = pick.composite_score
    signal = rec.get("signal", "HOLD")

    # DAY TRADE: momentum phase + elevated volume + decent score
    is_day = (
        pick.kinematic_phase in ("IGNITION", "ACCELERATION")
        and pick.rel_volume >= 1.5
        and score >= 48
    )
    if is_day:
        types.append("day_trade")

    # SWING: Trending regime + decent score
    is_swing = (
        pick.regime in ("STRONG_TREND", "CLEAN_REVERSION", "NOISY_TREND")
        and score >= 45
        and pick.kinematic_phase not in ("IGNITION",)
    )
    if is_swing:
        types.append("swing")

    # OPTIONS: option available + either signal or high-momentum day trade
    has_option = (
        pick.option_exp_short
        and pick.option_exp_short != "N/A"
        and score >= 48
    )
    if has_option and signal in ("BUY", "SELL"):
        opt_type = "option_call" if pick.option_direction == "CALL" else "option_put"
        types.append(opt_type)
    elif has_option and is_day:
        opt_type = "option_call" if pick.direction == "LONG" else "option_put"
        types.append(opt_type)
    elif has_option and is_swing and score >= 50:
        # Swing trades with options attached
        opt_type = "option_call" if pick.option_direction == "CALL" else "option_put"
        types.append(opt_type)

    return types


# ─────────────────────────────────────────────────────────────
#  Scanner — runs the full pipeline
# ─────────────────────────────────────────────────────────────

def scan_asset_class(asset_class: str) -> dict:
    """
    Scan an asset class and return categorized alerts.
    Returns: {
        'option_calls': [formatted_str, ...],
        'option_puts': [formatted_str, ...],
        'day_trades': [formatted_str, ...],
        'swings': [formatted_str, ...],
    }
    """
    from dashboard.data_bridge import scan_universe

    log.info("Scanning %s...", asset_class)
    try:
        picks = scan_universe(asset_class)
    except Exception as e:
        log.error("Failed to scan %s: %s", asset_class, e)
        return {"option_calls": [], "option_puts": [], "day_trades": [], "swings": []}

    if not picks:
        log.info("  No results for %s", asset_class)
        return {"option_calls": [], "option_puts": [], "day_trades": [], "swings": []}

    log.info("  %d tickers scored for %s", len(picks), asset_class)

    results = {"option_calls": [], "option_puts": [], "day_trades": [], "swings": []}

    for pick in picks:
        try:
            rec = get_recommendation(pick)
            types = classify_setup(pick, rec)

            for t in types:
                if t == "option_call":
                    results["option_calls"].append(_format_option_alert(pick, rec))
                elif t == "option_put":
                    results["option_puts"].append(_format_option_alert(pick, rec))
                elif t == "day_trade":
                    results["day_trades"].append(_format_day_trade(pick, rec))
                elif t == "swing":
                    results["swings"].append(_format_swing_trade(pick, rec))
        except Exception as e:
            log.warning("  Error processing %s: %s", getattr(pick, "ticker", "?"), e)

    return results


def run_full_scan(asset_classes: list = None) -> None:
    """Run the full scan across asset classes and dispatch alerts."""
    if not asset_classes:
        asset_classes = ["stocks", "etfs", "crypto"]

    all_results = {
        "option_calls": [],
        "option_puts": [],
        "day_trades": [],
        "swings": [],
    }

    for ac in asset_classes:
        results = scan_asset_class(ac)
        for key in all_results:
            all_results[key].extend(results[key])

    # Build and send Telegram messages by category
    _dispatch_alerts(all_results)


def _dispatch_alerts(results: dict) -> None:
    """Send categorized alerts to Telegram."""
    calls = results["option_calls"][:8]
    puts = results["option_puts"][:5]
    days = results["day_trades"][:8]
    swings = results["swings"][:8]

    total = len(calls) + len(puts) + len(days) + len(swings)

    if total == 0:
        log.info("No actionable setups found — no alerts to send.")
        # Send a quiet "nothing found" update only at market open
        now = datetime.datetime.now()
        if now.hour == 9 and now.minute < 45:
            send_telegram(f"{_header()}\n\n😴 No actionable setups this scan.\nMarkets may be quiet — will scan again shortly.")
        return

    # ── Option Alerts (calls + puts together) ──
    if calls or puts:
        msg = f"{_header()}\n\n<b>🎯 OPTIONS PLAYS</b>"
        if calls:
            msg += f"\n\n<b>CALLS ({len(calls)})</b>"
            msg += "".join(calls)
        if puts:
            msg += f"\n\n<b>PUTS ({len(puts)})</b>"
            msg += "".join(puts)
        msg += f"\n\n{'━' * 30}\n⚠️ <i>Not financial advice. Always manage risk.</i>"
        send_telegram(msg)
        log.info("Sent %d option alerts", len(calls) + len(puts))

    # ── Day Trade Alerts ──
    if days:
        msg = f"{_header()}\n\n<b>⚡ DAY TRADES</b>\n<i>High momentum, intraday setups</i>"
        msg += "".join(days)
        msg += f"\n\n{'━' * 30}\n⚠️ <i>Tight stops. Exit same day.</i>"
        send_telegram(msg)
        log.info("Sent %d day trade alerts", len(days))

    # ── Swing Trade Alerts ──
    if swings:
        msg = f"{_header()}\n\n<b>🔵 SWING TRADES</b>\n<i>Multi-day trending setups</i>"
        msg += "".join(swings)
        msg += f"\n\n{'━' * 30}\n⚠️ <i>Hold 2-10 days. Trail stops.</i>"
        send_telegram(msg)
        log.info("Sent %d swing trade alerts", len(swings))

    # ── Summary ──
    summary = (
        f"{_header()}\n\n"
        f"<b>📊 SCAN SUMMARY</b>\n"
        f"   Calls: {len(calls)}  |  Puts: {len(puts)}\n"
        f"   Day Trades: {len(days)}  |  Swings: {len(swings)}\n"
        f"   Total Setups: {total}"
    )
    send_telegram(summary)


# ─────────────────────────────────────────────────────────────
#  Test mode — send a realistic sample alert
# ─────────────────────────────────────────────────────────────

def send_test_alert() -> None:
    """Send a realistic test alert to verify Telegram is working."""
    now = datetime.datetime.now().strftime("%b %d, %I:%M %p")

    msg = (
        f"📡 <b>Scalp Assistant</b> — {now}\n"
        f"{'━' * 30}\n\n"
        f"<b>🎯 OPTIONS PLAYS</b>\n\n"
        f"<b>CALLS (2)</b>\n\n"
        f"🟢 <b>CALL — TSLA</b>  (Score: 72)\n"
        f"   Strike: <code>$420</code>  |  Exp: Mar 21  |  Budget: $100-$300\n"
        f"   Price: <code>$407.82</code> (+2.1%)  |  Confidence: 78%\n"
        f"   Regime: STRONG_TREND  |  Phase: IGNITION  |  RVOL: 3.2x\n"
        f"   Support: <code>$395.50</code>  |  Resistance: <code>$425.00</code>\n"
        f"   Entry: <code>$407.82</code> → Stop: <code>$395.50</code> → Target: <code>$425.00</code>  (R:R 1.4x)\n"
        f"   • Momentum ignition with volume surge\n"
        f"   • RSI recovering from oversold\n\n"
        f"🟢 <b>CALL — HIMS</b>  (Score: 68)\n"
        f"   Strike: <code>$27</code>  |  Exp: Mar 21  |  Budget: $40-$100\n"
        f"   Price: <code>$25.88</code> (+10.3%)  |  Confidence: 71%\n"
        f"   Regime: CLEAN_REVERSION  |  Phase: ACCELERATION  |  RVOL: 4.1x\n"
        f"   • Strong catalyst + volume breakout\n\n"
        f"<b>PUTS (1)</b>\n\n"
        f"🔴 <b>PUT — BBIO</b>  (Score: 61)\n"
        f"   Strike: <code>$68</code>  |  Exp: Mar 21  |  Budget: $80-$180\n"
        f"   Price: <code>$71.39</code> (-3.9%)  |  Confidence: 65%\n"
        f"   Regime: RANDOM  |  Phase: DECEL  |  RVOL: 0.8x\n"
        f"   • Overbought RSI + weakening momentum\n\n"
        f"{'━' * 30}\n"
        f"⚠️ <i>Not financial advice. Always manage risk.</i>"
    )
    ok1 = send_telegram(msg)

    msg2 = (
        f"📡 <b>Scalp Assistant</b> — {now}\n"
        f"{'━' * 30}\n\n"
        f"<b>⚡ DAY TRADES</b>\n"
        f"<i>High momentum, intraday setups</i>\n\n"
        f"📈 <b>DAY TRADE — XLE</b>  (BUY 76%)\n"
        f"   Price: <code>$56.98</code> (+2.5%)  |  Score: 53\n"
        f"   Phase: IGNITION  |  RVOL: 3.9x  |  RSI: 58\n"
        f"   Entry: <code>$56.98</code> → Stop: <code>$56.20</code> → Target: <code>$58.50</code>  (R:R 1.9x)\n"
        f"   • Energy sector momentum + geopolitical catalyst\n\n"
        f"📈 <b>DAY TRADE — ORCL</b>  (BUY 70%)\n"
        f"   Price: <code>$163.12</code> (+9.2%)  |  Score: 65\n"
        f"   Phase: ACCELERATION  |  RVOL: 3.0x  |  RSI: 71\n"
        f"   Entry: <code>$163.12</code> → Stop: <code>$158.00</code> → Target: <code>$172.00</code>  (R:R 1.7x)\n"
        f"   • Earnings beat + institutional buying\n\n"
        f"{'━' * 30}\n"
        f"⚠️ <i>Tight stops. Exit same day.</i>"
    )
    ok2 = send_telegram(msg2)

    msg3 = (
        f"📡 <b>Scalp Assistant</b> — {now}\n"
        f"{'━' * 30}\n\n"
        f"<b>🔵 SWING TRADES</b>\n"
        f"<i>Multi-day trending setups</i>\n\n"
        f"🔵 <b>SWING — INTC</b>  (BUY 68%)\n"
        f"   Price: <code>$47.98</code> (+2.6%)  |  Score: 59\n"
        f"   Regime: STRONG_TREND  |  Hurst: 0.62  |  RVOL: 1.8x\n"
        f"   Option: CALL <code>$50</code> exp Mar 28  |  Budget: $80-$180\n"
        f"   Support: <code>$46.20</code>  |  Resistance: <code>$50.50</code>\n"
        f"   • Trending regime with institutional accumulation\n\n"
        f"🔵 <b>SWING — MARA</b>  (BUY 64%)\n"
        f"   Price: <code>$18.45</code> (+5.1%)  |  Score: 56\n"
        f"   Regime: STRONG_TREND  |  Hurst: 0.58  |  RVOL: 2.1x\n"
        f"   • Crypto momentum + BTC breakout correlation\n\n"
        f"{'━' * 30}\n"
        f"⚠️ <i>Hold 2-10 days. Trail stops.</i>"
    )
    ok3 = send_telegram(msg3)

    msg4 = (
        f"📡 <b>Scalp Assistant</b> — {now}\n\n"
        f"<b>📊 SCAN SUMMARY</b>\n"
        f"   Calls: 2  |  Puts: 1\n"
        f"   Day Trades: 2  |  Swings: 2\n"
        f"   Total Setups: 7\n\n"
        f"{'━' * 30}\n"
        f"✅ <i>This was a test alert. Your Telegram is working!</i>"
    )
    ok4 = send_telegram(msg4)

    if all([ok1, ok2, ok3, ok4]):
        log.info("✅ All 4 test alerts sent successfully!")
    else:
        log.error("❌ Some alerts failed: options=%s day=%s swing=%s summary=%s", ok1, ok2, ok3, ok4)


# ─────────────────────────────────────────────────────────────
#  CLI entry point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scalp Assistant Scanner & Alerter")
    parser.add_argument("--test", action="store_true", help="Send test alerts to Telegram")
    parser.add_argument("--asset", type=str, default=None, help="Scan specific asset class (stocks, etfs, crypto)")
    parser.add_argument("--all", action="store_true", help="Scan all asset classes")
    args = parser.parse_args()

    if args.test:
        send_test_alert()
    elif args.asset:
        run_full_scan([args.asset])
    else:
        run_full_scan(["stocks", "etfs", "crypto"])
