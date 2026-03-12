"""
Forward price targets combining GBM probability + Fibonacci extensions + ATR.
"""


def compute_price_targets(
    current_price: float,
    levels_data: dict,
    atr: float = None,
    gbm_result: dict = None,
    direction: str = "LONG",
) -> dict:
    """
    Compute conservative and aggressive price targets.
    Returns: {conservative_target, aggressive_target, stop_price,
              risk_reward, where_headed: str}
    """
    nearest_r = levels_data.get("nearest_resistance")
    nearest_s = levels_data.get("nearest_support")

    # Default ATR-based targets if no level data
    if atr is None or atr <= 0:
        atr = current_price * 0.02  # fallback 2%

    if direction == "LONG":
        stop = nearest_s if nearest_s else current_price - atr * 1.5
        conservative = nearest_r if nearest_r else current_price + atr * 2.0
        aggressive = current_price + atr * 3.0

        # Use GBM median if available
        if gbm_result and gbm_result.get("median_final_price"):
            gbm_target = gbm_result["median_final_price"]
            if gbm_target > current_price:
                aggressive = max(aggressive, gbm_target)
    else:
        stop = nearest_r if nearest_r else current_price + atr * 1.5
        conservative = nearest_s if nearest_s else current_price - atr * 2.0
        aggressive = current_price - atr * 3.0

        if gbm_result and gbm_result.get("median_final_price"):
            gbm_target = gbm_result["median_final_price"]
            if gbm_target < current_price:
                aggressive = min(aggressive, gbm_target)

    # Risk/reward
    risk = abs(current_price - stop)
    reward = abs(conservative - current_price)
    rr = reward / risk if risk > 0 else 0

    # Build narrative
    upside_pct = ((conservative - current_price) / current_price) * 100 if direction == "LONG" else ((current_price - conservative) / current_price) * 100
    agg_pct = ((aggressive - current_price) / current_price) * 100 if direction == "LONG" else ((current_price - aggressive) / current_price) * 100

    parts = [
        f"Conservative: ${conservative:.2f} ({upside_pct:+.1f}%)",
        f"Aggressive: ${aggressive:.2f} ({agg_pct:+.1f}%)",
        f"Stop: ${stop:.2f} (R:R {rr:.1f}x)",
    ]
    if gbm_result:
        p_target = gbm_result.get("p_hit_target", 0) * 100
        parts.append(f"GBM: {p_target:.0f}% chance of hitting target")

    return {
        "conservative_target": round(conservative, 2),
        "aggressive_target": round(aggressive, 2),
        "stop_price": round(stop, 2),
        "risk_reward": round(rr, 2),
        "where_headed": " | ".join(parts),
    }
