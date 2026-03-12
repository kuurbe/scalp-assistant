"""
Score calibration based on historical prediction accuracy.
Adjusts future composite scores using observed accuracy per score range.
"""
import logging
import os
import json

logger = logging.getLogger(__name__)

CALIBRATION_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs", "calibration.json"
)


def compute_calibration_factors(accuracy_data: dict = None) -> dict:
    """
    Compute calibration adjustments from historical accuracy.

    If scores 55-65 historically win 42%, they need a penalty.
    If scores 80+ historically win 75%, they get a slight boost.

    Returns dict mapping score range to multiplier, e.g.:
        {"40-50": 0.85, "50-60": 0.92, "60-70": 1.0, "70-80": 1.05, "80-100": 1.10}
    """
    if accuracy_data is None:
        try:
            from analysis.predictions.tracker import compute_prediction_accuracy
            accuracy_data = compute_prediction_accuracy()
        except Exception:
            return {}

    by_score = accuracy_data.get("by_score_range", {})
    if not by_score:
        return {}

    factors = {}
    for score_range, data in by_score.items():
        if not isinstance(data, dict):
            continue

        win_rate = data.get("win_rate", 50)
        total = data.get("total", 0)

        # Need at least 10 predictions in a range to calibrate
        if total < 10:
            factors[score_range] = 1.0
            continue

        # Calibration logic:
        # Win rate 50% = break even = multiplier 1.0
        # Win rate 60% = slight boost = multiplier 1.05
        # Win rate 40% = penalty = multiplier 0.90
        # Linear interpolation: multiplier = 0.5 + (win_rate / 100)
        # Clamped to [0.75, 1.25]
        raw_factor = 0.5 + (win_rate / 100)
        factor = max(0.75, min(1.25, raw_factor))
        factors[score_range] = round(factor, 3)

    return factors


def apply_calibration(composite_score: float, calibration_factors: dict = None) -> float:
    """
    Apply calibration factor to a composite score.
    Returns adjusted score, clamped to [0, 100].
    """
    if calibration_factors is None:
        calibration_factors = load_calibration()

    if not calibration_factors:
        return composite_score

    # Determine which range this score falls into
    score_range = _get_score_range(composite_score)
    factor = calibration_factors.get(score_range, 1.0)

    adjusted = composite_score * factor
    return max(0, min(100, round(adjusted, 1)))


def _get_score_range(score: float) -> str:
    """Map a score to its range bucket."""
    if score < 50:
        return "40-50"
    elif score < 60:
        return "50-60"
    elif score < 70:
        return "60-70"
    elif score < 80:
        return "70-80"
    else:
        return "80-100"


def save_calibration(factors: dict):
    """Save calibration factors to disk."""
    try:
        os.makedirs(os.path.dirname(CALIBRATION_FILE), exist_ok=True)
        with open(CALIBRATION_FILE, "w") as f:
            json.dump(factors, f, indent=2)
        logger.debug("Saved calibration factors: %s", factors)
    except Exception as e:
        logger.warning("Failed to save calibration: %s", e)


def load_calibration() -> dict:
    """Load calibration factors from disk."""
    try:
        if os.path.exists(CALIBRATION_FILE):
            with open(CALIBRATION_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def recalibrate() -> dict:
    """
    Full recalibration cycle:
    1. Compute factors from historical accuracy
    2. Save to disk
    3. Return factors

    Suggested to run after each batch of predictions is evaluated.
    """
    factors = compute_calibration_factors()
    if factors:
        save_calibration(factors)
        logger.info("Recalibrated: %s", factors)
    return factors


def get_weight_suggestions(accuracy_data: dict = None) -> dict:
    """
    Suggest weight rebalancing based on which sub-scores best predict wins.

    Returns dict like:
        {"physics": 0.28, "technical": 0.20, "catalyst": 0.22, "statistical": 0.15, "social": 0.15}
    """
    if accuracy_data is None:
        try:
            from analysis.predictions.tracker import compute_prediction_accuracy
            accuracy_data = compute_prediction_accuracy()
        except Exception:
            return {}

    # This is a placeholder for future ML-based weight optimization.
    # For now, return current weights with a note about which regimes work best.
    by_regime = accuracy_data.get("by_regime", {})
    suggestions = {}

    if by_regime:
        best_regime = max(by_regime.items(),
                          key=lambda x: x[1].get("win_rate", 0) if isinstance(x[1], dict) else 0,
                          default=None)
        if best_regime:
            suggestions["best_performing_regime"] = best_regime[0]
            suggestions["best_regime_win_rate"] = (
                best_regime[1].get("win_rate", 0) if isinstance(best_regime[1], dict) else 0
            )

    overall = accuracy_data.get("overall_win_rate", 0)
    if overall > 55:
        suggestions["recommendation"] = "Current weights performing well, no changes needed"
    elif overall > 45:
        suggestions["recommendation"] = "Marginal performance — consider increasing physics/statistical weight"
    else:
        suggestions["recommendation"] = "Below breakeven — consider reducing catalyst/social weight"

    return suggestions
