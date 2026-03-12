"""
Physics-based momentum composite score.
Combines kinematics, Kalman trend, CVD, OBV, VWAP position.
"""


def compute_momentum_score(
    kinematic_score: float = 0,
    kalman_score: float = 0,
    cvd_score: float = 0,
    obv_score: float = 0,
    vwap_score: float = 0,
    regime: str = "UNKNOWN",
    vol_regime: str = "NORMAL",
) -> float:
    """
    Weighted physics-based momentum composite.
    All input scores should be 0-100.
    Returns: 0-100 score.
    """
    raw = (
        0.30 * kinematic_score +
        0.20 * kalman_score +
        0.20 * cvd_score +
        0.15 * obv_score +
        0.15 * vwap_score
    )

    # Regime adjustments
    if regime == "NOISY_TREND":
        raw *= 0.85
    elif regime in ("CHOPPY", "RANDOM"):
        raw *= 0.5

    # Volatility expansion bonus
    if vol_regime == "HIGH_VOL":
        raw *= 1.15
    elif vol_regime == "LOW_VOL":
        raw *= 0.9

    return max(0, min(100, round(raw, 1)))
