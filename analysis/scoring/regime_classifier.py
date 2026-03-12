"""
Combines Hurst exponent + Shannon entropy to classify the current market regime.
Determines whether to use momentum, mean-reversion, or skip strategies.
"""
from config import settings


def classify_stock_regime(daily_prices, intraday_prices=None) -> dict:
    """
    Classify the current regime for a stock.
    Returns: {regime, confidence, preferred_strategy, tradeable, hurst, entropy}
    """
    try:
        from analysis.physics.hurst import compute_hurst, classify_regime
        from analysis.physics.entropy import compute_entropy, entropy_filter

        # Hurst on daily data (structural regime)
        H = compute_hurst(daily_prices)
        hurst_info = classify_regime(H)

        # Entropy on intraday if available, else daily
        prices_for_entropy = intraday_prices if intraday_prices is not None and len(intraday_prices) > 20 else daily_prices
        returns = prices_for_entropy.pct_change().dropna()
        entropy_val = compute_entropy(returns) if len(returns) > 10 else 0.5
        is_tradeable = entropy_val < settings.ENTROPY_MAX_CHAOS

        # Regime matrix
        regime = hurst_info["regime"]
        if H > settings.HURST_TREND_THRESHOLD and entropy_val < 0.6:
            regime = "STRONG_TREND"
            strategy = "MOMENTUM"
            confidence = "HIGH"
        elif H > settings.HURST_TREND_THRESHOLD and entropy_val >= 0.6:
            regime = "NOISY_TREND"
            strategy = "MOMENTUM"
            confidence = "MEDIUM"
        elif H < settings.HURST_REVERT_THRESHOLD and entropy_val < 0.6:
            regime = "CLEAN_REVERSION"
            strategy = "MEAN_REVERSION"
            confidence = "HIGH"
        elif H < settings.HURST_REVERT_THRESHOLD and entropy_val >= 0.6:
            regime = "CHOPPY"
            strategy = "SKIP"
            confidence = "LOW"
            is_tradeable = False
        else:
            regime = "RANDOM"
            strategy = "SKIP"
            confidence = "LOW"

        return {
            "regime": regime,
            "confidence": confidence,
            "preferred_strategy": strategy,
            "tradeable": is_tradeable,
            "hurst": round(H, 3),
            "entropy": round(entropy_val, 3),
        }
    except Exception:
        return {
            "regime": "UNKNOWN",
            "confidence": "LOW",
            "preferred_strategy": "SKIP",
            "tradeable": True,
            "hurst": 0.5,
            "entropy": 0.5,
        }
