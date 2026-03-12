"""
BUY / HOLD / SELL recommendation engine.
Thin layer on existing composite scores + signals.
Tighter logic: multiple confirming signals required for BUY/SELL.
"""
import logging

logger = logging.getLogger(__name__)


def get_recommendation(scored_ticker) -> dict:
    """Generate actionable BUY/HOLD/SELL recommendation from a ScoredTicker.

    Signal logic:
        BUY  = score >= 60 + at least 2 bullish confirmations
        SELL = score >= 50 + at least 2 bearish confirmations
        HOLD = everything else

    Args:
        scored_ticker: ScoredTicker dataclass instance

    Returns:
        {"signal": "BUY"|"HOLD"|"SELL", "confidence": 0-100,
         "reasons": [...], "action": "CALL $185 Apr 11" | "Accumulate" | ...}
    """
    t = scored_ticker
    score = getattr(t, "composite_score", 0) or 0
    phase = (getattr(t, "kinematic_phase", "") or "").upper()
    regime = (getattr(t, "regime", "") or "").upper()
    direction = (getattr(t, "option_direction", "") or "").upper()
    pct_change = getattr(t, "pct_change", 0) or 0
    rsi = getattr(t, "rsi", 50) or 50
    rel_volume = getattr(t, "rel_volume", 1.0) or 1.0
    asset_class = getattr(t, "asset_class", "stocks") or "stocks"

    reasons = []
    action = ""

    # ── Count bullish confirmations ───────────────────────
    bull_signals = 0
    bull_reasons = []

    if phase == "IGNITION":
        bull_signals += 1
        bull_reasons.append("Momentum ignition")
    if pct_change < -2.0 and regime in ("MEAN_REVERTING", "CLEAN_REVERSION", "RISK_ON", "NEUTRAL", "UNKNOWN"):
        bull_signals += 1
        bull_reasons.append(f"Dip {pct_change:+.1f}%")
    if rsi < 35:
        bull_signals += 1
        bull_reasons.append(f"Oversold RSI {rsi:.0f}")
    if rel_volume >= 2.0 and pct_change > 0:
        bull_signals += 1
        bull_reasons.append(f"High volume {rel_volume:.1f}x")
    if regime in ("CLEAN_TREND", "RISK_ON") and pct_change > 0:
        bull_signals += 1
        bull_reasons.append(f"Trending regime")

    # ── Count bearish confirmations ───────────────────────
    bear_signals = 0
    bear_reasons = []

    if direction == "PUT":
        bear_signals += 1
        bear_reasons.append("PUT signal")
    if rsi > 70:
        bear_signals += 1
        bear_reasons.append(f"Overbought RSI {rsi:.0f}")
    if pct_change > 3.0:
        bear_signals += 1
        bear_reasons.append(f"Extended +{pct_change:.1f}%")
    if regime in ("RISK_OFF", "VOLATILE") and pct_change < 0:
        bear_signals += 1
        bear_reasons.append("Risk-off regime")

    # ── Decision logic (requires 2+ confirmations) ────────

    # BUY: score >= 60 AND at least 2 bullish confirmations
    if score >= 60 and bull_signals >= 2:
        signal = "BUY"
        reasons = [f"Score {score:.0f}/100"] + bull_reasons

        opt_dir = getattr(t, "option_direction", "")
        safe_strike = getattr(t, "option_safe_strike", None)
        exp_short = getattr(t, "option_exp_short", "")
        has_options = asset_class in ("stocks", "etfs")

        if has_options and opt_dir and safe_strike:
            action = f"{opt_dir} ${safe_strike} {exp_short}"
        elif any("Dip" in r for r in bull_reasons):
            action = "Accumulate on dip"
        else:
            action = "Enter long position"

        confidence = min(95, score + bull_signals * 3)

    # SELL: score >= 50 AND at least 2 bearish confirmations
    elif score >= 50 and bear_signals >= 2:
        signal = "SELL"
        reasons = [f"Score {score:.0f}/100"] + bear_reasons

        opt_dir = getattr(t, "option_direction", "")
        safe_strike = getattr(t, "option_safe_strike", None)
        exp_short = getattr(t, "option_exp_short", "")
        has_options = asset_class in ("stocks", "etfs")

        if has_options and opt_dir == "PUT" and safe_strike:
            action = f"PUT ${safe_strike} {exp_short}"
        else:
            action = "Take profits / reduce position"

        confidence = min(90, score + bear_signals * 3)

    # HOLD: everything else
    else:
        signal = "HOLD"
        if score >= 55:
            reasons.append(f"Score {score:.0f} — approaching buy zone")
            action = "Watch for entry signal"
        elif score >= 40:
            reasons.append(f"Score {score:.0f} — neutral")
            action = "Monitor for signal"
        else:
            reasons.append(f"Score {score:.0f} — weak setup")
            action = "Avoid or wait"

        if bull_signals == 1:
            reasons.append(f"1 bullish hint: {bull_reasons[0] if bull_reasons else 'weak'}")
        if bear_signals == 1:
            reasons.append(f"1 bearish hint: {bear_reasons[0] if bear_reasons else 'weak'}")

        confidence = max(30, min(70, score))

    return {
        "signal": signal,
        "confidence": round(confidence),
        "reasons": reasons,
        "action": action,
    }
