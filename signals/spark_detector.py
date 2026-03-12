"""
Spark detector — identifies momentum ignition events.
A spark fires when: kinematic IGNITION + CVD spike + volume surge + price > VWAP.
"""
import datetime
from config import settings


def detect_spark(
    ticker: str,
    kinematic_phase: str,
    accel_z: float = 0,
    cvd_signal: dict = None,
    rel_volume: float = 0,
    price: float = 0,
    vwap: float = 0,
    obv_divergence: str = "NONE",
    has_catalyst: bool = False,
) -> dict:
    """
    Detect momentum ignition (spark).
    Returns: {is_spark, confidence, explanation, price_at_spark}
    """
    reasons = []
    score = 0

    # Required conditions
    is_ignition = kinematic_phase == "IGNITION"
    has_vol_surge = rel_volume >= settings.SPARK_VOLUME_MULT
    above_vwap = price > vwap if vwap > 0 else True
    has_cvd_spike = (cvd_signal or {}).get("institutional_spike", False)

    if is_ignition:
        score += 30
        reasons.append(f"Kinematic IGNITION (accel z={accel_z:.1f})")
    if has_vol_surge:
        score += 25
        reasons.append(f"Volume surge {rel_volume:.1f}x avg")
    if above_vwap:
        score += 15
        reasons.append("Price above VWAP")
    if has_cvd_spike:
        score += 15
        reasons.append("CVD institutional spike")

    # Optional boosters
    if obv_divergence != "BEARISH":
        score += 5
        reasons.append("OBV confirming")
    if has_catalyst:
        score += 10
        reasons.append("Catalyst present")

    is_spark = is_ignition and has_vol_surge and above_vwap
    confidence = min(100, score)

    return {
        "is_spark": is_spark,
        "confidence": confidence,
        "spark_time": datetime.datetime.now().strftime("%H:%M"),
        "price_at_spark": price,
        "explanation": reasons,
    }
