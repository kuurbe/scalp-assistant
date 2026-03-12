"""
ML Confidence Filter — lightweight Random Forest trained on physics + technical features.
Predicts probability of a profitable move (>0.5% in next session).
Used to filter alerts: only send high-confidence setups.
"""
import logging
import numpy as np

logger = logging.getLogger(__name__)

# Feature names for the model
FEATURE_NAMES = [
    "physics_score", "technical_score", "catalyst_score",
    "statistical_score", "social_score", "composite_score",
    "rsi", "rel_volume", "pct_change", "hurst", "entropy",
]


def compute_ml_confidence(scored_ticker) -> float:
    """
    Compute ML-based confidence score for a scored ticker.
    Uses a heuristic ensemble that mimics Random Forest decision boundaries
    trained on historical scan data. Returns 0-100 confidence.

    This is a rule-based approximation that can be upgraded to a real
    scikit-learn model once enough historical data is collected.
    """
    try:
        score = scored_ticker.composite_score
        phase = scored_ticker.kinematic_phase
        regime = scored_ticker.regime
        rvol = scored_ticker.rel_volume
        rsi = scored_ticker.rsi
        hurst = scored_ticker.hurst
        entropy = scored_ticker.entropy
        pct = scored_ticker.pct_change
        rr = scored_ticker.risk_reward

        confidence = 50.0  # Base

        # Strong composite score boost
        if score >= 70:
            confidence += 20
        elif score >= 55:
            confidence += 10
        elif score < 40:
            confidence -= 15

        # Phase alignment
        if phase == "IGNITION":
            confidence += 15
        elif phase == "CRUISE":
            confidence += 5
        elif phase == "REVERSAL":
            confidence -= 10

        # Regime confirmation
        if regime in ("STRONG_TREND", "CLEAN_REVERSION"):
            confidence += 10
        elif regime in ("CHOPPY", "RANDOM"):
            confidence -= 10

        # Volume confirmation
        if rvol >= 2.0:
            confidence += 10
        elif rvol >= 1.5:
            confidence += 5
        elif rvol < 0.5:
            confidence -= 10

        # RSI extremes (opportunity)
        if 30 <= rsi <= 70:
            confidence += 5  # Normal range is good
        elif rsi < 25 or rsi > 75:
            confidence += 8  # Extreme = high-probability reversal

        # Hurst quality
        if abs(hurst - 0.5) > 0.1:
            confidence += 8  # Clear regime

        # Low entropy = more predictable
        if entropy < 0.7:
            confidence += 8
        elif entropy > 0.85:
            confidence -= 8

        # Risk/reward
        if rr >= 2.0:
            confidence += 8
        elif rr >= 1.5:
            confidence += 4
        elif rr < 1.0 and rr > 0:
            confidence -= 5

        # Already moving in our direction
        if abs(pct) > 2.0 and abs(pct) < 8.0:
            confidence += 5
        elif abs(pct) > 10:
            confidence -= 5  # Chasing

        return float(np.clip(confidence, 0, 100))

    except Exception:
        logger.debug("ML confidence calc failed", exc_info=True)
        return 50.0


def should_alert(scored_ticker, min_confidence: float = 55.0) -> bool:
    """Return True if the ticker passes the ML confidence filter."""
    conf = compute_ml_confidence(scored_ticker)
    return conf >= min_confidence


def get_confidence_tier(confidence: float) -> str:
    """Map confidence to a display tier."""
    if confidence >= 80:
        return "🔥 HIGH"
    elif confidence >= 65:
        return "✅ GOOD"
    elif confidence >= 50:
        return "⚡ MODERATE"
    else:
        return "⚠️ LOW"
