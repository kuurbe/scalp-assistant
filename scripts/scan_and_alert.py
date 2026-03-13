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
from zoneinfo import ZoneInfo

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from signals.notifier import send_telegram, send_telegram_photo
from signals.recommendation import get_recommendation
from config import settings
from analysis.ml_confidence import compute_ml_confidence, get_confidence_tier, log_training_sample
from analysis.position_sizer import format_position_line
from signals.chart_generator import generate_alert_chart, generate_summary_chart, generate_candlestick_chart

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
    et = ZoneInfo("America/New_York")
    now = datetime.datetime.now(et).strftime("%b %d, %I:%M %p ET")
    return f"📡 <b>Scalp Assistant</b> — {now}\n{'━' * 30}"


def _format_option_alert(pick, rec: dict) -> str:
    """Format an options play alert (CALL or PUT)."""
    direction = pick.option_direction or "CALL"
    emoji = "🟢" if direction == "CALL" else "🔴"
    strike = pick.option_safe_strike or pick.price
    exp = pick.option_exp_long or pick.option_exp_short or "N/A"
    budget = pick.option_budget or "N/A"
    conf = rec.get("confidence", 0)

    # ML confidence
    ml_conf = compute_ml_confidence(pick)
    ml_tier = get_confidence_tier(ml_conf)

    # Support/resistance context
    levels = ""
    if pick.nearest_support > 0:
        levels = f"\n   Support: <code>${pick.nearest_support:.2f}</code>  |  Resistance: <code>${pick.nearest_resistance:.2f}</code>"

    # Risk/reward
    rr = ""
    if pick.entry_price > 0 and pick.risk_reward > 0:
        rr = f"\n   Entry: <code>${pick.entry_price:.2f}</code> → Stop: <code>${pick.stop_price:.2f}</code> → Target: <code>${pick.target_price:.2f}</code>  (R:R {pick.risk_reward:.1f}x)"

    # Position sizing
    pos_line = ""
    if pick.entry_price > 0 and pick.stop_price > 0:
        pos_line = format_position_line(pick.entry_price, pick.stop_price)
        if pos_line:
            pos_line = f"\n{pos_line}"

    reasons = rec.get("reasons", [])[:3]
    reasons_str = "\n".join(f"   • {r}" for r in reasons) if reasons else ""

    base = (
        f"\n{emoji} <b>{direction} — {pick.ticker}</b>  (Score: {pick.composite_score:.0f})\n"
        f"   Strike: <code>${strike:.0f}</code>  |  Exp: {exp}  |  Budget: {budget}\n"
        f"   Price: <code>${pick.price:.2f}</code> ({pick.pct_change:+.1f}%)  |  Confidence: {conf}%\n"
        f"   Regime: {pick.regime}  |  Phase: {pick.kinematic_phase}  |  RVOL: {pick.rel_volume:.1f}x\n"
        f"   ML Confidence: {ml_tier} ({ml_conf:.0f}%)"
        f"{levels}{rr}{pos_line}"
    )
    if reasons_str:
        base += f"\n{reasons_str}"
    return base


def _format_day_trade(pick, rec: dict) -> str:
    """Format a day trade alert."""
    signal = rec.get("signal", "HOLD")
    conf = rec.get("confidence", 0)
    dir_emoji = "📈" if pick.direction == "LONG" else "📉"

    # ML confidence
    ml_conf = compute_ml_confidence(pick)
    ml_tier = get_confidence_tier(ml_conf)

    levels = ""
    if pick.entry_price > 0:
        levels = f"\n   Entry: <code>${pick.entry_price:.2f}</code> → Stop: <code>${pick.stop_price:.2f}</code> → Target: <code>${pick.target_price:.2f}</code>  (R:R {pick.risk_reward:.1f}x)"

    # Position sizing
    pos_line = ""
    if pick.entry_price > 0 and pick.stop_price > 0:
        pos_line = format_position_line(pick.entry_price, pick.stop_price)
        if pos_line:
            pos_line = f"\n{pos_line}"

    reasons = rec.get("reasons", [])[:2]
    reasons_str = "\n".join(f"   • {r}" for r in reasons) if reasons else ""

    base = (
        f"\n{dir_emoji} <b>DAY TRADE — {pick.ticker}</b>  ({signal} {conf}%)\n"
        f"   Price: <code>${pick.price:.2f}</code> ({pick.pct_change:+.1f}%)  |  Score: {pick.composite_score:.0f}\n"
        f"   Phase: {pick.kinematic_phase}  |  RVOL: {pick.rel_volume:.1f}x  |  RSI: {pick.rsi:.0f}\n"
        f"   ML Confidence: {ml_tier} ({ml_conf:.0f}%)"
        f"{levels}{pos_line}"
    )
    if reasons_str:
        base += f"\n{reasons_str}"
    return base


def _format_swing_trade(pick, rec: dict) -> str:
    """Format a swing trade alert."""
    signal = rec.get("signal", "HOLD")
    conf = rec.get("confidence", 0)
    dir_emoji = "🔵" if pick.direction == "LONG" else "🟠"

    # ML confidence
    ml_conf = compute_ml_confidence(pick)
    ml_tier = get_confidence_tier(ml_conf)

    # Swing trades show option play if available
    option_line = ""
    if pick.option_exp_short and pick.option_exp_short != "N/A":
        option_line = f"\n   Option: {pick.option_direction} <code>${pick.option_safe_strike:.0f}</code> exp {pick.option_exp_long}  |  Budget: {pick.option_budget}"

    levels = ""
    if pick.nearest_support > 0:
        levels = f"\n   Support: <code>${pick.nearest_support:.2f}</code>  |  Resistance: <code>${pick.nearest_resistance:.2f}</code>"

    # Position sizing
    pos_line = ""
    if getattr(pick, 'entry_price', 0) > 0 and getattr(pick, 'stop_price', 0) > 0:
        pos_line = format_position_line(pick.entry_price, pick.stop_price)
        if pos_line:
            pos_line = f"\n{pos_line}"

    reasons = rec.get("reasons", [])[:2]
    reasons_str = "\n".join(f"   • {r}" for r in reasons) if reasons else ""

    base = (
        f"\n{dir_emoji} <b>SWING — {pick.ticker}</b>  ({signal} {conf}%)\n"
        f"   Price: <code>${pick.price:.2f}</code> ({pick.pct_change:+.1f}%)  |  Score: {pick.composite_score:.0f}\n"
        f"   Regime: {pick.regime}  |  Hurst: {pick.hurst:.2f}  |  RVOL: {pick.rel_volume:.1f}x\n"
        f"   ML Confidence: {ml_tier} ({ml_conf:.0f}%)"
        f"{option_line}{levels}{pos_line}"
    )
    if reasons_str:
        base += f"\n{reasons_str}"
    return base


# ─────────────────────────────────────────────────────────────
#  Confluence scoring — multi-factor confirmation system
#  Only alerts on trades with REAL confluence, not single signals
# ─────────────────────────────────────────────────────────────

def _get_trading_window(asset_class: str = "stocks") -> str:
    """Return current trading window: 'prime', 'active', 'dead', 'closed'.

    For stocks/ETFs:
      Prime:  9:30-11:00 AM ET — highest win-rate window
      Active: 11:00-11:30 AM, 2:00-4:00 PM ET
      Dead:   11:30 AM-2:00 PM ET — chop zone, only A+ setups
      Closed: outside market hours

    For crypto: always 'active' (24/7 market), except 1-5 AM ET = 'dead'
    """
    try:
        et = ZoneInfo("America/New_York")
        now = datetime.datetime.now(et)
        h, m = now.hour, now.minute
        t = h * 60 + m  # minutes since midnight

        # Crypto trades 24/7
        if asset_class == "crypto":
            if 1 <= h < 5:
                return "dead"  # lowest volume window
            return "active"

        if now.weekday() >= 5:
            return "closed"
        if t < 9 * 60 + 30 or t > 16 * 60:
            return "closed"
        if t <= 11 * 60:         # 9:30 - 11:00
            return "prime"
        if t <= 11 * 60 + 30:    # 11:00 - 11:30
            return "active"
        if t <= 14 * 60:         # 11:30 - 2:00
            return "dead"
        return "active"           # 2:00 - 4:00
    except Exception:
        return "active"


def _compute_confluence(pick, rec: dict) -> dict:
    """Compute multi-factor confluence score for a setup.

    Returns dict with:
      - confluence_points: int (number of confirming factors, 0-7)
      - tier: 'A+', 'A', 'B', 'C' (only A+/A get alerted)
      - flags: list of confirmation signals met
      - suppressed: bool (if a suppression condition is active)
      - suppress_reason: str
    """
    score = pick.composite_score
    phase = pick.kinematic_phase
    regime = pick.regime
    rvol = pick.rel_volume
    rsi = pick.rsi
    rr = pick.risk_reward
    pct = pick.pct_change
    ml_conf = compute_ml_confidence(pick)
    signal = rec.get("signal", "HOLD")

    flags = []
    points = 0

    # ── SUPPRESSION CHECKS (hard kills — never alert) ──
    # Chasing: stock already moved 7%+ today — too late (4+ ATR move)
    if abs(pct) > 7.0:
        return {"confluence_points": 0, "tier": "C", "flags": [],
                "suppressed": True, "suppress_reason": f"Chasing ({pct:+.1f}% move)"}

    # R:R too low — no edge if risk > reward
    if 0 < rr < 1.0:
        return {"confluence_points": 0, "tier": "C", "flags": [],
                "suppressed": True, "suppress_reason": f"Bad R:R ({rr:.1f}x)"}

    # RSI extreme chasing: RSI > 80 for longs, < 20 for shorts
    if pick.direction == "LONG" and rsi > 80:
        return {"confluence_points": 0, "tier": "C", "flags": [],
                "suppressed": True, "suppress_reason": f"Overbought RSI ({rsi:.0f})"}

    # Random/Choppy regime — no edge UNLESS strong momentum + volume override
    # Crypto and high-momentum movers can still alert if volume + phase confirm
    if regime in ("RANDOM", "CHOPPY"):
        has_momentum_override = (
            phase in ("IGNITION", "ACCELERATION")
            and rvol >= 2.0
            and abs(pct) >= 2.0
        )
        if not has_momentum_override:
            return {"confluence_points": 0, "tier": "C", "flags": [],
                    "suppressed": True, "suppress_reason": f"No edge ({regime} regime)"}

    # Dead volume — nobody participating
    if rvol < 0.8 and phase not in ("IGNITION", "ACCELERATION"):
        return {"confluence_points": 0, "tier": "C", "flags": [],
                "suppressed": True, "suppress_reason": f"Dead volume ({rvol:.1f}x RVOL)"}

    # Low entropy = unpredictable
    entropy = getattr(pick, "entropy", 0.5)
    if entropy > 0.85:
        return {"confluence_points": 0, "tier": "C", "flags": [],
                "suppressed": True, "suppress_reason": f"Unpredictable (entropy {entropy:.2f})"}

    # ── CONFLUENCE FACTORS (each adds 1 point) ──

    # 1. Trend alignment — regime confirms direction
    if regime in ("STRONG_TREND", "CLEAN_REVERSION"):
        points += 1
        flags.append("Trending regime")
    elif regime == "NOISY_TREND":
        points += 0.5
        flags.append("Weak trend")

    # 2. Momentum phase — IGNITION or ACCELERATION
    if phase in ("IGNITION", "ACCELERATION"):
        points += 1
        flags.append(f"{phase} phase")
    elif phase == "CRUISE":
        points += 0.5
        flags.append("Cruise phase")

    # 3. Volume confirmation — RVOL ≥ 1.5 (normalized for time of day)
    if rvol >= 2.5:
        points += 1.5
        flags.append(f"Strong volume ({rvol:.1f}x)")
    elif rvol >= 1.5:
        points += 1
        flags.append(f"Volume confirmed ({rvol:.1f}x)")
    elif rvol >= 1.0:
        points += 0.5
        flags.append(f"Avg volume ({rvol:.1f}x)")

    # 4. Risk:Reward ≥ 1.5
    if rr >= 2.5:
        points += 1.5
        flags.append(f"R:R {rr:.1f}x")
    elif rr >= 1.5:
        points += 1
        flags.append(f"R:R {rr:.1f}x")

    # 5. ML confidence ≥ 60
    if ml_conf >= 75:
        points += 1.5
        flags.append(f"ML high ({ml_conf:.0f}%)")
    elif ml_conf >= 60:
        points += 1
        flags.append(f"ML good ({ml_conf:.0f}%)")
    elif ml_conf >= 50:
        points += 0.5
        flags.append(f"ML moderate ({ml_conf:.0f}%)")

    # 6. RSI in sweet spot (not extreme — 30-65 for longs, 35-70 for shorts)
    if pick.direction == "LONG" and 30 <= rsi <= 65:
        points += 1
        flags.append(f"RSI sweet spot ({rsi:.0f})")
    elif pick.direction == "SHORT" and 35 <= rsi <= 70:
        points += 1
        flags.append(f"RSI sweet spot ({rsi:.0f})")

    # 7. Score quality
    if score >= 55:
        points += 1.5
        flags.append(f"Strong score ({score:.0f})")
    elif score >= 45:
        points += 1
        flags.append(f"Good score ({score:.0f})")
    elif score >= 38:
        points += 0.5
        flags.append(f"Decent score ({score:.0f})")

    # ── TIER ASSIGNMENT ──
    # A+: 5+ confluence points — alert always (even dead zone)
    # A:  3.5+ confluence points — alert during prime + active windows
    # B:  2+ points — watchlist only, no alert
    # C:  <2 points — skip entirely
    if points >= 5:
        tier = "A+"
    elif points >= 3.5:
        tier = "A"
    elif points >= 2:
        tier = "B"
    else:
        tier = "C"

    return {
        "confluence_points": points,
        "tier": tier,
        "flags": flags,
        "suppressed": False,
        "suppress_reason": "",
    }


def classify_setup(pick, rec: dict, asset_class: str = "stocks") -> list:
    """Classify a scored ticker into trade types using confluence scoring.

    Only returns types for HIGH CONFIDENCE setups:
    - A+ tier: always alert (any market window)
    - A tier: alert during prime/active windows only
    - B/C tier: never alert (watchlist only)
    """
    confluence = _compute_confluence(pick, rec)

    # Suppressed — hard kill
    if confluence["suppressed"]:
        return []

    tier = confluence["tier"]
    window = _get_trading_window(asset_class=asset_class)

    # Only A+ and A tiers get alerts
    if tier == "C" or tier == "B":
        return []

    # A tier only alerts during prime/active windows (not dead zone)
    if tier == "A" and window == "dead":
        return []

    # Closed market — no alerts
    if window == "closed":
        return []

    # ── Classify trade type ──
    types = []
    score = pick.composite_score
    signal = rec.get("signal", "HOLD")
    phase = pick.kinematic_phase

    # DAY TRADE: momentum phase + volume
    if phase in ("IGNITION", "ACCELERATION") and pick.rel_volume >= 1.5:
        types.append("day_trade")

    # SWING: trending regime without ignition
    if pick.regime in ("STRONG_TREND", "CLEAN_REVERSION", "NOISY_TREND") and phase != "IGNITION":
        types.append("swing")

    # If neither day nor swing matched but confluence is high, default to swing
    if not types and tier == "A+":
        types.append("swing")

    # OPTIONS: attach if available and signal is clear
    has_option = (
        pick.option_exp_short
        and pick.option_exp_short != "N/A"
        and score >= 40
    )
    if has_option and signal in ("BUY", "SELL"):
        opt_type = "option_call" if pick.option_direction == "CALL" else "option_put"
        types.append(opt_type)
    elif has_option and "day_trade" in types:
        opt_type = "option_call" if pick.direction == "LONG" else "option_put"
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
        'top_picks': [(ticker, score, pct_change, pick), ...],
    }
    """
    from dashboard.data_bridge import scan_universe

    log.info("Scanning %s...", asset_class)
    try:
        picks = scan_universe(asset_class)
    except Exception as e:
        log.error("Failed to scan %s: %s", asset_class, e)
        return {"option_calls": [], "option_puts": [], "day_trades": [], "swings": [], "top_picks": []}

    if not picks:
        log.info("  No results for %s", asset_class)
        return {"option_calls": [], "option_puts": [], "day_trades": [], "swings": [], "top_picks": []}

    log.info("  %d tickers scored for %s", len(picks), asset_class)

    results = {"option_calls": [], "option_puts": [], "day_trades": [], "swings": [], "top_picks": []}

    for pick in picks:
        try:
            rec = get_recommendation(pick)
            types = classify_setup(pick, rec, asset_class=asset_class)

            # Log for ML training (features logged now, outcome backfilled later)
            log_training_sample(pick)

            for t in types:
                if t == "option_call":
                    results["option_calls"].append(_format_option_alert(pick, rec))
                elif t == "option_put":
                    results["option_puts"].append(_format_option_alert(pick, rec))
                elif t == "day_trade":
                    results["day_trades"].append(_format_day_trade(pick, rec))
                elif t == "swing":
                    results["swings"].append(_format_swing_trade(pick, rec))

            # Track top picks for summary chart
            if types:
                results["top_picks"].append((
                    pick.ticker, pick.composite_score, pick.pct_change, pick
                ))
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
        "top_picks": [],
    }

    for ac in asset_classes:
        results = scan_asset_class(ac)
        for key in all_results:
            all_results[key].extend(results.get(key, []))

    # Build and send Telegram messages by category
    _dispatch_alerts(all_results)


def _send_candlestick_for_pick(pick) -> None:
    """Fetch OHLCV and send a candlestick chart for a top pick via Telegram."""
    try:
        import yfinance as yf
        df = yf.download(pick.ticker, period="3mo", interval="1d", progress=False)
        if df is None or len(df) < 10:
            return
        chart = generate_candlestick_chart(
            ticker=pick.ticker,
            df=df,
            entry=getattr(pick, "entry_price", None),
            stop=getattr(pick, "stop_price", None),
            target=getattr(pick, "target_price", None),
            score=getattr(pick, "composite_score", None),
            phase=getattr(pick, "kinematic_phase", None),
            energy_regime=getattr(pick, "energy_regime", None),
        )
        if chart:
            send_telegram_photo(chart, caption=f"📊 {pick.ticker} — Candlestick Chart")
    except Exception as e:
        log.debug("Candlestick chart failed for %s: %s", getattr(pick, "ticker", "?"), e)


_daily_alert_count = {"date": None, "count": 0}

def _check_daily_cap() -> int:
    """Return remaining alert slots today. Cap: 15 alerts/day."""
    et = ZoneInfo("America/New_York")
    today = datetime.datetime.now(et).date()
    if _daily_alert_count["date"] != today:
        _daily_alert_count["date"] = today
        _daily_alert_count["count"] = 0
    return max(0, 15 - _daily_alert_count["count"])


def _dispatch_alerts(results: dict) -> None:
    """Send categorized alerts to Telegram. Capped to avoid spam."""
    remaining = _check_daily_cap()
    if remaining <= 0:
        log.info("Daily alert cap reached (15) — suppressing all alerts.")
        return

    # Hard caps per scan: max 2 options, 2 day trades, 3 swings = 7 max
    calls = results["option_calls"][:2]
    puts = results["option_puts"][:1]
    days = results["day_trades"][:2]
    swings = results["swings"][:3]

    total = len(calls) + len(puts) + len(days) + len(swings)

    if total == 0:
        log.info("No actionable setups found — no alerts to send.")
        # Send a quiet "nothing found" update only at market open (ET)
        et = ZoneInfo("America/New_York")
        now = datetime.datetime.now(et)
        if now.hour == 9 and now.minute < 45:
            send_telegram(f"{_header()}\n\n😴 No actionable setups this scan.\nMarkets may be quiet — will scan again shortly.")
        return

    # Trim to daily cap
    total_alerts = len(calls) + len(puts) + len(days) + len(swings)
    if total_alerts > remaining:
        # Prioritize: day trades > options > swings
        budget = remaining
        days = days[:budget]; budget -= len(days)
        calls = calls[:max(0,budget)]; budget -= len(calls)
        puts = puts[:max(0,budget)]; budget -= len(puts)
        swings = swings[:max(0,budget)]

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

    # ── Summary with chart ──
    summary = (
        f"{_header()}\n\n"
        f"<b>📊 SCAN SUMMARY</b>\n"
        f"   Calls: {len(calls)}  |  Puts: {len(puts)}\n"
        f"   Day Trades: {len(days)}  |  Swings: {len(swings)}\n"
        f"   Total Setups: {total}"
    )

    # Try to send summary chart
    top_picks = results.get("top_picks", [])
    if top_picks:
        # Sort by score, take top 10 for chart
        top_picks.sort(key=lambda x: x[1], reverse=True)
        chart_data = [(t[0], t[1], t[2]) for t in top_picks[:10]]
        chart_bytes = generate_summary_chart(chart_data)
        if chart_bytes:
            send_telegram_photo(chart_bytes, caption=summary)
            log.info("Sent summary with chart (%d top picks)", len(chart_data))
        else:
            send_telegram(summary)

        # Send candlestick charts for top 3 picks
        for _, _, _, pick in top_picks[:3]:
            _send_candlestick_for_pick(pick)
    else:
        send_telegram(summary)

    # Track daily count
    _daily_alert_count["count"] += total


# ─────────────────────────────────────────────────────────────
#  Test mode — send a realistic sample alert
# ─────────────────────────────────────────────────────────────

def send_test_alert() -> None:
    """Send a realistic test alert to verify Telegram is working."""
    et = ZoneInfo("America/New_York")
    now = datetime.datetime.now(et).strftime("%b %d, %I:%M %p ET")

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
