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
from analysis.options_math import compute_option_probabilities
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
    """Format an options play alert (CALL or PUT) with Black-Scholes probabilities."""
    direction = pick.option_direction or "CALL"
    emoji = "🟢" if direction == "CALL" else "🔴"
    strike = pick.option_safe_strike or pick.price
    exp = pick.option_exp_long or pick.option_exp_short or "N/A"
    budget = pick.option_budget or "N/A"
    conf = rec.get("confidence", 0)

    # ML confidence
    ml_conf = compute_ml_confidence(pick)
    ml_tier = get_confidence_tier(ml_conf)

    # Black-Scholes probability
    bs = compute_option_probabilities(pick)
    bs_line = ""
    if bs.get("safe_prob_itm"):
        bs_line = f"\n   P(ITM): {bs['safe_prob_itm']:.0f}%  |  Δ: {bs['safe_delta']:.2f}  |  IV: {bs.get('iv_est', 0):.0f}%"

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
        f"{bs_line}{levels}{rr}{pos_line}"
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
#  Crypto-specific alert formatters
# ─────────────────────────────────────────────────────────────

def _format_crypto_trade(pick, rec: dict) -> str:
    """Format a short-term crypto trade alert with whale/quant signals."""
    signal = rec.get("signal", "HOLD")
    conf = rec.get("confidence", 0)
    dir_emoji = "📈" if pick.direction == "LONG" else "📉"

    ml_conf = compute_ml_confidence(pick)
    ml_tier = get_confidence_tier(ml_conf)

    # Whale badges
    whale_badges = []
    if getattr(pick, "whale_golden_sweep", False):
        whale_badges.append("⚡ Golden Sweep")
    elif getattr(pick, "whale_sweep_detected", False):
        whale_badges.append("🐋 Sweep")
    if getattr(pick, "whale_volume_sigma", 0) >= 2.5:
        whale_badges.append(f"📊 Vol {pick.whale_volume_sigma:.1f}σ")
    whale_line = f"\n   Whale: {' | '.join(whale_badges)}" if whale_badges else ""

    # Quant signals
    quant_line = ""
    q_score = getattr(pick, "quant_score", 0)
    q_aligned = getattr(pick, "quant_aligned", False)
    q_n = getattr(pick, "quant_n_agreeing", 0)
    if q_score > 0:
        align_badge = "✅" if q_aligned else "⚠️"
        quant_line = f"\n   Quant: {align_badge} {q_n}/6 aligned (score {q_score:.0f})"

    # BTC correlation
    btc_corr = getattr(pick, "btc_correlation_20d", 0)
    btc_line = f"\n   BTC Corr: {btc_corr:.2f}" if btc_corr != 0 else ""

    # Entry/stop/target
    levels = ""
    if getattr(pick, "entry_price", 0) > 0:
        levels = f"\n   Entry: <code>${pick.entry_price:.2f}</code> → Stop: <code>${pick.stop_price:.2f}</code> → Target: <code>${pick.target_price:.2f}</code>  (R:R {pick.risk_reward:.1f}x)"

    # Position sizing (Kelly)
    kelly = getattr(pick, "kelly_fraction", 0)
    kelly_line = f"\n   Kelly Size: {kelly*100:.1f}% of bankroll" if kelly > 0.01 else ""

    reasons = rec.get("reasons", [])[:2]
    reasons_str = "\n".join(f"   • {r}" for r in reasons) if reasons else ""

    base = (
        f"\n{dir_emoji} <b>CRYPTO TRADE — {pick.ticker.replace('-USD', '')}</b>  ({signal} {conf}%)\n"
        f"   Price: <code>${pick.price:.2f}</code> ({pick.pct_change:+.1f}%)  |  Score: {pick.composite_score:.0f}\n"
        f"   Phase: {pick.kinematic_phase}  |  RVOL: {pick.rel_volume:.1f}x  |  RSI: {pick.rsi:.0f}\n"
        f"   ML: {ml_tier} ({ml_conf:.0f}%)"
        f"{whale_line}{quant_line}{btc_line}{levels}{kelly_line}"
    )
    if reasons_str:
        base += f"\n{reasons_str}"
    return base


def _format_crypto_investment(pick, rec: dict) -> str:
    """Format a longer-term crypto investment opportunity."""
    conf = rec.get("confidence", 0)
    hurst = getattr(pick, "hurst", 0.5)

    # Investment label based on signal strength
    score = pick.composite_score
    if score >= 65 and hurst >= 0.55:
        label = "ACCUMULATE"
        emoji = "💎"
    elif score >= 55:
        label = "WATCH"
        emoji = "👀"
    else:
        label = "MONITOR"
        emoji = "📋"

    # Quant alignment
    q_aligned = getattr(pick, "quant_aligned", False)
    q_n = getattr(pick, "quant_n_agreeing", 0)
    align_badge = f"✅ {q_n}/6" if q_aligned else f"⚠️ {q_n}/6"

    # BTC correlation
    btc_corr = getattr(pick, "btc_correlation_20d", 0)
    btc_line = f"  |  BTC Corr: {btc_corr:.2f}" if btc_corr != 0 else ""

    # Regime context
    regime = getattr(pick, "regime", "UNKNOWN")

    reasons = rec.get("reasons", [])[:2]
    reasons_str = "\n".join(f"   • {r}" for r in reasons) if reasons else ""

    base = (
        f"\n{emoji} <b>{label} — {pick.ticker.replace('-USD', '')}</b>  (Conf: {conf}%)\n"
        f"   Price: <code>${pick.price:.2f}</code> ({pick.pct_change:+.1f}%)  |  Score: {pick.composite_score:.0f}\n"
        f"   Regime: {regime}  |  Hurst: {hurst:.2f}  |  Quant: {align_badge}{btc_line}"
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

    # 8. TradingView indicator confirmation
    tv_conf = getattr(pick, "tv_confirmation", 0)
    if tv_conf >= 80:
        points += 1.5
        flags.append(f"TV confirmed ({tv_conf:.0f}%)")
    elif tv_conf >= 60:
        points += 1.0
        flags.append(f"TV partial ({tv_conf:.0f}%)")
    elif tv_conf >= 40:
        points += 0.5
        flags.append(f"TV weak ({tv_conf:.0f}%)")

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

    # CRYPTO INVESTMENT: strong long-term signals (no options for crypto)
    if asset_class == "crypto":
        hurst = getattr(pick, "hurst", 0.5)
        if (pick.regime in ("STRONG_TREND", "CLEAN_REVERSION")
                and hurst >= 0.55 and score >= 55 and "day_trade" not in types):
            types.append("investment")
        return types

    # OPTIONS: attach if available and signal is clear (stocks/ETFs only)
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

    # Enrich top candidates with TradingView confirmation scores
    try:
        from signals.tradingview_bridge import is_tv_available, get_tv_indicators, compute_tv_confirmation
        if is_tv_available():
            tv_max = getattr(settings, "TV_MAX_CANDIDATES", 15)
            top_candidates = [p for p in picks if p.composite_score >= 40][:tv_max]
            if top_candidates:
                log.info("  TV confirming %d candidates...", len(top_candidates))
                for pick in top_candidates:
                    tv_vals = get_tv_indicators(pick.ticker)
                    if tv_vals:
                        pick.tv_confirmation = compute_tv_confirmation(pick, tv_vals)
                log.info("  TV confirmation done")
    except Exception as e:
        log.debug("TV confirmation skipped: %s", e)

    results = {"option_calls": [], "option_puts": [], "day_trades": [], "swings": [],
                "investments": [], "top_picks": []}

    is_crypto = asset_class == "crypto"

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
                    formatter = _format_crypto_trade if is_crypto else _format_day_trade
                    results["day_trades"].append(formatter(pick, rec))
                elif t == "swing":
                    formatter = _format_crypto_investment if is_crypto else _format_swing_trade
                    results["swings"].append(formatter(pick, rec))
                elif t == "investment":
                    results["investments"].append(_format_crypto_investment(pick, rec))

            # Track top picks for summary chart
            if types:
                results["top_picks"].append((
                    pick.ticker, pick.composite_score, pick.pct_change, pick
                ))
        except Exception as e:
            log.warning("  Error processing %s: %s", getattr(pick, "ticker", "?"), e)

    # Run stablecoin depeg check alongside crypto scans
    if asset_class == "crypto":
        try:
            from scripts.stablecoin_monitor import scan_stablecoins, dispatch_stablecoin_alerts
            stable_events = scan_stablecoins()
            if stable_events:
                dispatch_stablecoin_alerts(stable_events)
                log.info("  %d stablecoin depeg events detected", len(stable_events))
        except Exception as e:
            log.debug("Stablecoin monitor error: %s", e)

    return results


def run_full_scan(asset_classes: list = None) -> None:
    """Run the full scan across asset classes and dispatch alerts.

    Dispatches per asset class so crypto alerts route to the crypto Telegram channel.
    """
    if not asset_classes:
        asset_classes = ["stocks", "etfs", "crypto"]

    for ac in asset_classes:
        results = scan_asset_class(ac)
        _dispatch_alerts(results, asset_class=ac)


def _send_candlestick_for_pick(pick, chat_id=None) -> None:
    """Send a chart for a top pick via Telegram. Tries TradingView first, falls back to matplotlib."""
    # Try TradingView screenshot first (professional chart with indicators + levels)
    try:
        from signals.tradingview_bridge import capture_trade_screenshot, is_tv_available
        if is_tv_available():
            is_crypto = getattr(pick, "asset_class", "") == "crypto"
            tf = settings.TV_SCREENSHOT_TIMEFRAME_CRYPTO if is_crypto else settings.TV_SCREENSHOT_TIMEFRAME_STOCKS
            png = capture_trade_screenshot(
                pick.ticker, tf,
                entry=getattr(pick, "entry_price", 0),
                stop=getattr(pick, "stop_price", 0),
                target=getattr(pick, "target_price", 0),
            )
            if png:
                caption = (
                    f"📊 {pick.ticker} — TradingView {tf}min"
                    f" | Score {getattr(pick, 'composite_score', 0):.0f}"
                    f" | {getattr(pick, 'kinematic_phase', '')}"
                )
                send_telegram_photo(png, caption=caption, chat_id=chat_id)
                return
    except Exception:
        log.debug("TV screenshot fallback for %s", getattr(pick, "ticker", "?"))

    # Fallback: matplotlib candlestick
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
            send_telegram_photo(chart, caption=f"📊 {pick.ticker} — Candlestick Chart", chat_id=chat_id)
    except Exception as e:
        log.debug("Candlestick chart failed for %s: %s", getattr(pick, "ticker", "?"), e)


_daily_alert_count = {}  # Per-asset-class: {"stocks": {"date": ..., "count": 0}, ...}

def _check_daily_cap(asset_class: str = "stocks") -> int:
    """Return remaining alert slots today for this asset class."""
    et = ZoneInfo("America/New_York")
    today = datetime.datetime.now(et).date()

    if asset_class not in _daily_alert_count:
        _daily_alert_count[asset_class] = {"date": None, "count": 0}

    entry = _daily_alert_count[asset_class]
    if entry["date"] != today:
        entry["date"] = today
        entry["count"] = 0

    cap = settings.DAILY_ALERT_CAP_CRYPTO if asset_class in ("crypto", "stablecoins") else settings.DAILY_ALERT_CAP_STOCKS
    return max(0, cap - entry["count"])


def _get_crypto_chat_id():
    """Get the crypto Telegram chat ID, falling back to default."""
    crypto_chat = settings.get_secret("TELEGRAM_CRYPTO_CHAT_ID")
    return crypto_chat if crypto_chat else None


def _dispatch_alerts(results: dict, asset_class: str = "stocks") -> None:
    """Send categorized alerts to Telegram. Routes crypto to separate channel."""
    remaining = _check_daily_cap(asset_class)
    if remaining <= 0:
        log.info("Daily alert cap reached for %s — suppressing.", asset_class)
        return

    is_crypto = asset_class in ("crypto", "stablecoins")
    chat_id = _get_crypto_chat_id() if is_crypto else None

    # Hard caps per scan
    calls = results.get("option_calls", [])[:2]
    puts = results.get("option_puts", [])[:1]
    days = results.get("day_trades", [])[:3 if is_crypto else 2]
    swings = results.get("swings", [])[:3]
    investments = results.get("investments", [])[:3]

    total = len(calls) + len(puts) + len(days) + len(swings) + len(investments)

    if total == 0:
        log.info("No actionable setups for %s — no alerts.", asset_class)
        if not is_crypto:
            et = ZoneInfo("America/New_York")
            now = datetime.datetime.now(et)
            if now.hour == 9 and now.minute < 45:
                send_telegram(f"{_header()}\n\n😴 No actionable setups this scan.\nMarkets may be quiet — will scan again shortly.")
        return

    # Trim to daily cap
    if total > remaining:
        budget = remaining
        days = days[:budget]; budget -= len(days)
        investments = investments[:max(0, budget)]; budget -= len(investments)
        calls = calls[:max(0, budget)]; budget -= len(calls)
        puts = puts[:max(0, budget)]; budget -= len(puts)
        swings = swings[:max(0, budget)]

    # ── Option Alerts (stocks/ETFs only) ──
    if calls or puts:
        msg = f"{_header()}\n\n<b>🎯 OPTIONS PLAYS</b>"
        if calls:
            msg += f"\n\n<b>CALLS ({len(calls)})</b>"
            msg += "".join(calls)
        if puts:
            msg += f"\n\n<b>PUTS ({len(puts)})</b>"
            msg += "".join(puts)
        msg += f"\n\n{'━' * 30}\n⚠️ <i>Not financial advice. Always manage risk.</i>"
        send_telegram(msg, chat_id=chat_id)
        log.info("Sent %d option alerts", len(calls) + len(puts))

    # ── Day Trade / Crypto Trade Alerts ──
    if days:
        if is_crypto:
            msg = f"{_header()}\n\n<b>⚡ CRYPTO TRADES</b>\n<i>Short-term momentum setups</i>"
        else:
            msg = f"{_header()}\n\n<b>⚡ DAY TRADES</b>\n<i>High momentum, intraday setups</i>"
        msg += "".join(days)
        msg += f"\n\n{'━' * 30}\n⚠️ <i>Tight stops. Manage risk.</i>"
        send_telegram(msg, chat_id=chat_id)
        log.info("Sent %d %s trade alerts", len(days), "crypto" if is_crypto else "day")

    # ── Swing / Investment Alerts ──
    if swings:
        if is_crypto:
            msg = f"{_header()}\n\n<b>🔵 CRYPTO SWING</b>\n<i>Multi-day trending setups</i>"
        else:
            msg = f"{_header()}\n\n<b>🔵 SWING TRADES</b>\n<i>Multi-day trending setups</i>"
        msg += "".join(swings)
        msg += f"\n\n{'━' * 30}\n⚠️ <i>Hold 2-10 days. Trail stops.</i>"
        send_telegram(msg, chat_id=chat_id)
        log.info("Sent %d swing alerts", len(swings))

    # ── Crypto Investment Opportunities ──
    if investments:
        msg = f"{_header()}\n\n<b>💎 INVESTMENT OPPORTUNITIES</b>\n<i>Longer-term accumulation signals</i>"
        msg += "".join(investments)
        msg += f"\n\n{'━' * 30}\n⚠️ <i>DYOR. DCA recommended over lump sum.</i>"
        send_telegram(msg, chat_id=chat_id)
        log.info("Sent %d investment alerts", len(investments))

    # ── Summary with chart ──
    summary_parts = []
    if calls or puts:
        summary_parts.append(f"Calls: {len(calls)}  |  Puts: {len(puts)}")
    if days:
        label = "Crypto Trades" if is_crypto else "Day Trades"
        summary_parts.append(f"{label}: {len(days)}")
    if swings:
        summary_parts.append(f"Swings: {len(swings)}")
    if investments:
        summary_parts.append(f"Investments: {len(investments)}")

    summary = (
        f"{_header()}\n\n"
        f"<b>📊 {'CRYPTO' if is_crypto else 'SCAN'} SUMMARY</b>\n"
        f"   {'  |  '.join(summary_parts)}\n"
        f"   Total Setups: {total}"
    )

    top_picks = results.get("top_picks", [])
    if top_picks:
        top_picks.sort(key=lambda x: x[1], reverse=True)
        chart_data = [(t[0], t[1], t[2]) for t in top_picks[:10]]
        chart_bytes = generate_summary_chart(chart_data)
        if chart_bytes:
            send_telegram_photo(chart_bytes, caption=summary, chat_id=chat_id)
            log.info("Sent summary with chart (%d top picks)", len(chart_data))
        else:
            send_telegram(summary, chat_id=chat_id)

        for _, _, _, pick in top_picks[:3]:
            _send_candlestick_for_pick(pick, chat_id=chat_id)

        # Create TradingView price alerts for top 3 picks at entry/stop/target
        try:
            from signals.tradingview_bridge import create_price_alerts, is_tv_available
            if is_tv_available():
                for _, score, _, pick in top_picks[:3]:
                    tier = "A+" if score >= 55 else "A"
                    n = create_price_alerts(
                        pick.ticker,
                        entry=getattr(pick, "entry_price", 0),
                        stop=getattr(pick, "stop_price", 0),
                        target=getattr(pick, "target_price", 0),
                        label=f"{tier} {getattr(pick, 'kinematic_phase', '')}",
                    )
                    if n:
                        log.info("  Created %d TV alerts for %s", n, pick.ticker)
        except Exception:
            log.debug("TV alert creation skipped")
    else:
        send_telegram(summary, chat_id=chat_id)

    # Track daily count
    _daily_alert_count.setdefault(asset_class, {"date": None, "count": 0})
    _daily_alert_count[asset_class]["count"] += total

    # ── Scalp Hot List (stocks/ETFs only, market hours) ──
    if asset_class in ("stocks", "etfs") and getattr(settings, "SCALP_ENABLED", False):
        try:
            hot = _build_scalp_hot_list(picks)
            if hot:
                msg = _format_hot_list_alert(hot)
                send_telegram(msg, chat_id=chat_id)
                log.info("Sent scalp hot list (%d tickers)", len(hot))
                # Store for scalp monitoring loop
                global _current_hot_list
                _current_hot_list = hot
        except Exception as e:
            log.debug("Hot list generation failed: %s", e)


# ─────────────────────────────────────────────────────────────
#  Scalp Hot List
# ─────────────────────────────────────────────────────────────

_current_hot_list = []  # Shared with scalp monitoring loop


def get_current_hot_list() -> list:
    """Return the current scalp hot list (called by scalp_engine)."""
    return _current_hot_list


def _build_scalp_hot_list(picks: list) -> list:
    """Filter scored tickers down to scalp-ready candidates."""
    min_rvol = getattr(settings, "SCALP_MIN_RVOL", 2.0)
    min_rr = getattr(settings, "SCALP_MIN_RR", 1.5)
    max_list = getattr(settings, "SCALP_MAX_HOT_LIST", 8)

    hot = []
    for pick in picks:
        phase = getattr(pick, "kinematic_phase", "")
        if phase not in ("IGNITION", "ACCELERATION"):
            continue
        if getattr(pick, "rel_volume", 0) < min_rvol:
            continue
        if getattr(pick, "risk_reward", 0) < min_rr:
            continue
        if getattr(pick, "composite_score", 0) < 40:
            continue
        hot.append(pick)

    hot.sort(key=lambda p: p.composite_score, reverse=True)
    return hot[:max_list]


def _format_hot_list_alert(hot_list: list) -> str:
    """Format a simplified scalp watchlist for Telegram."""
    et = ZoneInfo("America/New_York")
    now = datetime.datetime.now(et).strftime("%I:%M %p")

    lines = [
        f"<b>SCALP WATCHLIST</b> — {now} ET",
        f"{'━' * 28}",
    ]

    for i, pick in enumerate(hot_list, 1):
        ticker = pick.ticker
        price = getattr(pick, "price", 0)
        pct = getattr(pick, "pct_change", 0)
        phase = getattr(pick, "kinematic_phase", "")
        rvol = getattr(pick, "rel_volume", 0)
        entry = getattr(pick, "entry_price", 0)
        stop = getattr(pick, "stop_price", 0)
        target = getattr(pick, "target_price", 0)

        # Plain English momentum description
        if phase == "IGNITION":
            desc = "Momentum igniting, heavy volume"
        elif phase == "ACCELERATION":
            desc = "Accelerating, strong push"
        else:
            desc = "Active momentum"

        if rvol >= 3.0:
            desc += ", volume surge"

        arrow = "+" if pct >= 0 else ""
        lines.append(f"\n<b>{i}. {ticker}</b>  <code>${price:.2f}</code> ({arrow}{pct:.1f}%)")
        lines.append(f"   {desc}")
        if entry > 0 and stop > 0 and target > 0:
            lines.append(f"   Buy: <code>${entry:.2f}</code>  Stop: <code>${stop:.2f}</code>  Target: <code>${target:.2f}</code>")

        # Options hint if available
        if getattr(pick, "option_exp_short", "") and pick.option_exp_short != "N/A":
            strike = getattr(pick, "option_safe_strike", 0)
            direction = getattr(pick, "option_direction", "CALL")
            lines.append(f"   Option: {direction} <code>${strike:.0f}</code> exp {pick.option_exp_short}")

    lines.append(f"\n{'━' * 28}")
    lines.append("<i>Watch for pullbacks to buy zone. Tight stops.</i>")
    return "\n".join(lines)


def _format_scalp_entry(setup) -> str:
    """Format a simplified scalp entry alert."""
    ticker = setup.ticker
    price = setup.entry_price
    setup_names = {
        "VWAP_PULLBACK": "Pulling back to support",
        "MOMENTUM_BREAK": "Breaking out with volume",
        "ORB_BREAKOUT": "Opening range breakout",
        "IV_CRUSH_PUT": "Overbought, expecting pullback",
        "GAMMA_SQUEEZE_CALL": "Gamma squeeze building",
        "VWAP_RECLAIM_CALL": "Reclaiming VWAP with volume",
        "BREAKDOWN_PUT": "Breaking down with momentum",
        "BOLLINGER_SQUEEZE": "Volatility squeeze breakout",
    }
    reason = setup_names.get(setup.setup_type, setup.setup_type)

    lines = [
        f"<b>SCALP — Buy {ticker} now</b>",
        f"{'━' * 28}",
        f"Price: <code>${price:.2f}</code> — {reason}",
        f"Stop: <code>${setup.stop_price:.2f}</code>",
        f"Target 1: <code>${setup.target_1:.2f}</code> (take half off)",
        f"Target 2: <code>${setup.target_2:.2f}</code> (let rest ride)",
    ]

    if setup.risk_reward > 0:
        lines.append(f"Reward: {setup.risk_reward:.1f}x your risk")

    if setup.urgency == "FADING":
        lines.append("\n<i>Momentum fading — be quick or skip</i>")
    elif setup.urgency == "NOW":
        lines.append("\n<i>Strong setup — act now</i>")

    return "\n".join(lines)


def _format_options_scalp(setup) -> str:
    """Format a plain English options scalp alert with dollar P&L at each target.

    No jargon — dollar amounts, what happens at each price, and risk warnings.
    """
    scenarios = getattr(setup, "pnl_scenarios", {}) or {}
    iv_rank = getattr(setup, "iv_rank", 0)
    spread_pct = getattr(setup, "spread_pct", 0)

    # Setup reason in plain English
    setup_reasons = {
        "IV_CRUSH_PUT": "overbought + expensive premium, expecting pullback",
        "GAMMA_SQUEEZE_CALL": "approaching max pain, market makers hedging",
        "VWAP_RECLAIM_CALL": "reclaiming VWAP with volume, intraday reversal",
        "BREAKDOWN_PUT": "breaking below support with momentum",
        "BOLLINGER_SQUEEZE": "volatility squeeze breakout",
        "VWAP_PULLBACK": "pulling back to support",
        "MOMENTUM_BREAK": "breaking out with volume",
        "ORB_BREAKOUT": "opening range breakout",
    }
    reason = setup_reasons.get(setup.setup_type, setup.setup_type.replace("_", " ").lower())

    lines = [
        f"<b>OPTIONS SCALP — {setup.option_contract}</b>",
        f"{'━' * 28}",
        f"{setup.ticker} is {reason} at <code>${setup.entry_price:.2f}</code>",
    ]

    # Use P&L scenarios if available (real dollar amounts)
    if scenarios:
        cost = scenarios.get("entry_cost", 0)
        cost_100 = scenarios.get("entry_cost_100", 0)
        if cost > 0:
            lines.append(f"Cost: ~<code>${cost:.2f}</code> (<code>${cost_100:.0f}</code>/contract)")

        # Target 1 (50% scale-out)
        t1 = scenarios.get("at_target_1", {})
        if t1:
            profit_sign = "+" if t1.get("profit_dollars", 0) >= 0 else ""
            lines.append(
                f"\nIf {setup.ticker} hits <code>${t1['underlying_price']:.2f}</code> → "
                f"option ~<code>${t1['option_value']:.2f}</code> "
                f"({t1['profit_pct']:+.0f}%, {profit_sign}<code>${t1['profit_dollars']:.0f}</code>/contract)"
            )

        # Target 2 (full exit)
        t2 = scenarios.get("at_target_2", {})
        if t2:
            profit_sign = "+" if t2.get("profit_dollars", 0) >= 0 else ""
            lines.append(
                f"If {setup.ticker} hits <code>${t2['underlying_price']:.2f}</code> → "
                f"option ~<code>${t2['option_value']:.2f}</code> "
                f"({t2['profit_pct']:+.0f}%, {profit_sign}<code>${t2['profit_dollars']:.0f}</code>/contract)"
            )

        # Stop
        st = scenarios.get("at_stop", {})
        if st:
            lines.append(
                f"Stop: {setup.ticker} {'below' if 'call' in setup.option_contract.lower() else 'above'} "
                f"<code>${st['underlying_price']:.2f}</code> → "
                f"option ~<code>${st['option_value']:.2f}</code> ({st['loss_pct']:+.0f}%)"
            )

        # Time decay
        td = scenarios.get("time_decay", {})
        hr_cost = abs(td.get("1hr", 0)) if td else 0
        if hr_cost > 0.01:
            lines.append(f"\nTime decay: ~<code>${hr_cost:.2f}</code>/hr per contract")

        # IV crush warning
        iv_crush = scenarios.get("iv_crush_5pct", 0)
        if iv_crush < -10:
            lines.append(f"IV crush risk: <code>${abs(iv_crush):.0f}</code>/contract if vol drops 5%")

        # Gamma warning
        if scenarios.get("gamma_warning"):
            lines.append("⚡ Gamma zone — moves fast both ways, size small")

    else:
        # Fallback: use greeks-based estimate (legacy)
        greeks = setup.greeks or {}
        cost = greeks.get("cost_per_contract", 0)
        est_profit = greeks.get("expected_profit", 0)
        est_pct = greeks.get("expected_pct", 0)

        if cost > 0 and est_profit > 0:
            lines.append(f"Option: ~<code>${cost:.2f}</code> → ~<code>${cost + est_profit:.2f}</code> (+{est_pct:.0f}%)")
        if cost > 0:
            lines.append(f"Cost: <code>${cost * 100:.0f}</code> per contract")
        lines.append(f"Exit if stock moves past <code>${setup.stop_price:.2f}</code>")

    # IV Rank + Spread summary
    meta_parts = []
    if iv_rank > 0:
        iv_label = "cheap" if iv_rank < 30 else "fair" if iv_rank < 60 else "expensive"
        meta_parts.append(f"IV Rank: {iv_rank:.0f}% ({iv_label})")
    if spread_pct > 0:
        spread_label = "tight" if spread_pct < 0.05 else "okay" if spread_pct < 0.10 else "wide"
        meta_parts.append(f"Spread: {spread_pct:.1%} ({spread_label})")
    if meta_parts:
        lines.append(f"\n{' | '.join(meta_parts)}")

    # Urgency
    if setup.urgency == "NOW":
        lines.append(f"\n<b>ACT NOW</b> — momentum igniting")
    elif setup.urgency == "FADING":
        lines.append(f"\n<i>Momentum fading — be quick or skip</i>")

    return "\n".join(lines)


def _dispatch_scalp_alerts(setups: list) -> None:
    """Send scalp alerts to Telegram with screenshots."""
    remaining = _check_daily_cap("scalps")
    if remaining <= 0:
        return

    for setup in setups[:remaining]:
        # Check cooldown
        try:
            from signals.notification_config import should_notify
            if not should_notify("HIGH", setup.ticker):
                continue
        except Exception:
            pass

        # Format alert
        if setup.option_contract:
            msg = _format_options_scalp(setup)
        else:
            msg = _format_scalp_entry(setup)

        send_telegram(f"{_header()}\n\n{msg}")

        # Send TV screenshot if available
        if setup.screenshot_png:
            send_telegram_photo(
                setup.screenshot_png,
                caption=f"SCALP — {setup.ticker} {setup.setup_type.replace('_', ' ').title()}"
            )

        log.info("Sent scalp alert: %s %s", setup.ticker, setup.setup_type)

    _daily_alert_count.setdefault("scalps", {"date": None, "count": 0})
    _daily_alert_count["scalps"]["count"] += len(setups)


# ─────────────────────────────────────────────────────────────
#  Test mode — send a realistic sample alert
# ─────────────────────────────────────────────────────────────

def send_test_alert() -> None:
    """Send a realistic test alert to verify Telegram is working."""
    et = ZoneInfo("America/New_York")
    now = datetime.datetime.now(et).strftime("%b %d, %I:%M %p ET")

    # Dynamic expiry dates so the test alert never shows stale dates
    _today = datetime.date.today()
    _days_to_fri = (4 - _today.weekday()) % 7 or 7
    _exp1 = (_today + datetime.timedelta(days=_days_to_fri)).strftime("%b %d")
    _exp2 = (_today + datetime.timedelta(days=_days_to_fri + 7)).strftime("%b %d")

    msg = (
        f"📡 <b>Scalp Assistant</b> — {now}\n"
        f"{'━' * 30}\n\n"
        f"<b>🎯 OPTIONS PLAYS</b>\n\n"
        f"<b>CALLS (2)</b>\n\n"
        f"🟢 <b>CALL — TSLA</b>  (Score: 72)\n"
        f"   Strike: <code>$420</code>  |  Exp: {_exp1}  |  Budget: $100-$300\n"
        f"   Price: <code>$407.82</code> (+2.1%)  |  Confidence: 78%\n"
        f"   Regime: STRONG_TREND  |  Phase: IGNITION  |  RVOL: 3.2x\n"
        f"   Support: <code>$395.50</code>  |  Resistance: <code>$425.00</code>\n"
        f"   Entry: <code>$407.82</code> → Stop: <code>$395.50</code> → Target: <code>$425.00</code>  (R:R 1.4x)\n"
        f"   • Momentum ignition with volume surge\n"
        f"   • RSI recovering from oversold\n\n"
        f"🟢 <b>CALL — HIMS</b>  (Score: 68)\n"
        f"   Strike: <code>$27</code>  |  Exp: {_exp1}  |  Budget: $40-$100\n"
        f"   Price: <code>$25.88</code> (+10.3%)  |  Confidence: 71%\n"
        f"   Regime: CLEAN_REVERSION  |  Phase: ACCELERATION  |  RVOL: 4.1x\n"
        f"   • Strong catalyst + volume breakout\n\n"
        f"<b>PUTS (1)</b>\n\n"
        f"🔴 <b>PUT — BBIO</b>  (Score: 61)\n"
        f"   Strike: <code>$68</code>  |  Exp: {_exp1}  |  Budget: $80-$180\n"
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
        f"   Option: CALL <code>$50</code> exp {_exp2}  |  Budget: $80-$180\n"
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
