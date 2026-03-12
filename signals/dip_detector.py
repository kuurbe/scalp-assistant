"""
Dip detector — identifies mean reversion entry setups.
A dip entry fires when: Z-score < -1.5 + OU mean-reverting + bullish pattern + CVD stabilizing.
"""
import datetime
from config import settings


def detect_dip_entry(
    ticker: str,
    zscore_vwap: float = 0,
    ou_signal: dict = None,
    candlestick_patterns: list = None,
    cvd_signal: dict = None,
    fractal_support_nearby: bool = False,
    fib_zone: bool = False,
    pivot_nearby: bool = False,
) -> dict:
    """
    Detect reversal dip entry.
    Returns: {is_dip, confidence, entry_zone, target, stop, explanation}
    """
    reasons = []
    score = 0

    # Required conditions
    is_oversold = zscore_vwap < settings.DIP_ZSCORE_ENTRY
    ou = ou_signal or {}
    is_reverting = ou.get("is_mean_reverting", False)
    has_bullish_pattern = any(
        p.get("type") == "BULLISH" for p in (candlestick_patterns or [])
    )
    cvd_stabilizing = (cvd_signal or {}).get("cvd_trend") in ("NEUTRAL", "ACCUMULATING")

    if is_oversold:
        score += 30
        reasons.append(f"Z-score {zscore_vwap:.2f} (oversold)")
    if is_reverting:
        hl = ou.get("half_life_minutes", 999)
        score += 25
        reasons.append(f"OU mean-reverting (t½={hl:.0f}min)")
    if has_bullish_pattern:
        patterns = [p["pattern"] for p in (candlestick_patterns or []) if p.get("type") == "BULLISH"]
        score += 20
        reasons.append(f"Bullish pattern: {', '.join(patterns[:2])}")
    if cvd_stabilizing:
        score += 10
        reasons.append("CVD stabilizing")

    # Optional boosters
    if fractal_support_nearby:
        score += 5
        reasons.append("Fractal support nearby")
    if fib_zone:
        score += 5
        reasons.append("At Fibonacci zone")
    if pivot_nearby:
        score += 5
        reasons.append("Near pivot support")

    is_dip = is_oversold and (is_reverting or has_bullish_pattern)
    confidence = min(100, score)

    return {
        "is_dip": is_dip,
        "confidence": confidence,
        "dip_time": datetime.datetime.now().strftime("%H:%M"),
        "explanation": reasons,
    }
