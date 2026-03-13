"""
ML Confidence Filter v2.0 — Real RandomForest + heuristic fallback.

Strategy:
1. Collects feature vectors from every scan into a training log
2. After enough samples (200+), trains a RandomForest on historical outcomes
3. Falls back to improved heuristic when not enough training data
4. Predicts probability of profitable move (>0.5% in next session)
"""
import json
import logging
import os
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

# Feature names for the model
FEATURE_NAMES = [
    "composite_score", "physics_score", "technical_score",
    "catalyst_score", "statistical_score", "social_score",
    "rsi", "rel_volume", "pct_change", "hurst", "entropy",
    "risk_reward", "kinematic_phase_num", "regime_num",
    "energy_v2_score",
]

PHASE_MAP = {"REVERSAL": 0, "DECEL": 1, "CRUISE": 2, "IGNITION": 3, "ACCELERATION": 3}
REGIME_MAP = {
    "RANDOM": 0, "CHOPPY": 0, "NOISY_TREND": 1, "MEAN_REVERTING": 1,
    "CLEAN_REVERSION": 2, "STRONG_TREND": 3, "TRENDING": 2,
}

TRAINING_LOG = Path(os.path.dirname(__file__)).parent / "logs" / "ml_training.jsonl"
MODEL_PATH = Path(os.path.dirname(__file__)).parent / "models" / "rf_confidence.pkl"

_cached_model = None
_cached_model_mtime = 0


def _extract_features(scored_ticker) -> np.ndarray:
    """Extract feature vector from a ScoredTicker."""
    phase = getattr(scored_ticker, "kinematic_phase", "CRUISE")
    regime = getattr(scored_ticker, "regime", "RANDOM")
    energy_v2 = getattr(scored_ticker, "energy_v2_score", 0.0)

    return np.array([
        getattr(scored_ticker, "composite_score", 50),
        getattr(scored_ticker, "physics_score", 50),
        getattr(scored_ticker, "technical_score", 50),
        getattr(scored_ticker, "catalyst_score", 50),
        getattr(scored_ticker, "statistical_score", 50),
        getattr(scored_ticker, "social_score", 50),
        getattr(scored_ticker, "rsi", 50),
        getattr(scored_ticker, "rel_volume", 1.0),
        getattr(scored_ticker, "pct_change", 0.0),
        getattr(scored_ticker, "hurst", 0.5),
        getattr(scored_ticker, "entropy", 0.5),
        getattr(scored_ticker, "risk_reward", 1.0),
        PHASE_MAP.get(phase, 2),
        REGIME_MAP.get(regime, 0),
        energy_v2,
    ], dtype=float)


def log_training_sample(scored_ticker, outcome: float = None):
    """
    Log a feature vector for future model training.
    Call this after each scan with the ticker's features.
    Outcome (if known) = actual pct change in next session.
    """
    try:
        TRAINING_LOG.parent.mkdir(parents=True, exist_ok=True)
        features = _extract_features(scored_ticker).tolist()
        record = {
            "ticker": getattr(scored_ticker, "ticker", "?"),
            "features": features,
            "outcome": outcome,  # None until we backfill
        }
        with open(TRAINING_LOG, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def _load_model():
    """Load cached RandomForest model if it exists and is fresh."""
    global _cached_model, _cached_model_mtime
    try:
        if not MODEL_PATH.exists():
            return None
        mtime = MODEL_PATH.stat().st_mtime
        if _cached_model is not None and mtime == _cached_model_mtime:
            return _cached_model
        import joblib
        _cached_model = joblib.load(MODEL_PATH)
        _cached_model_mtime = mtime
        logger.info("Loaded ML model from %s", MODEL_PATH)
        return _cached_model
    except Exception:
        return None


def train_model(min_samples: int = 200) -> bool:
    """
    Train RandomForest on collected training data.
    Call periodically (e.g., weekly) or when enough data accumulates.
    Returns True if model was trained and saved.
    """
    try:
        if not TRAINING_LOG.exists():
            return False

        # Load training data
        X, y = [], []
        with open(TRAINING_LOG) as f:
            for line in f:
                record = json.loads(line.strip())
                if record.get("outcome") is not None:
                    X.append(record["features"])
                    # Binary: 1 if profitable (>0.5% move in our direction), 0 otherwise
                    y.append(1 if record["outcome"] > 0.5 else 0)

        if len(X) < min_samples:
            logger.info("Not enough labeled samples (%d/%d)", len(X), min_samples)
            return False

        from sklearn.ensemble import RandomForestClassifier
        import joblib

        X = np.array(X)
        y = np.array(y)

        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=8,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X, y)

        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, MODEL_PATH)
        logger.info("ML model trained on %d samples, saved to %s", len(X), MODEL_PATH)
        return True

    except Exception:
        logger.debug("Model training failed", exc_info=True)
        return False


def compute_ml_confidence(scored_ticker) -> float:
    """
    Compute ML-based confidence score (0-100).
    Uses trained RandomForest if available, falls back to improved heuristic.
    """
    try:
        # Try real ML model first
        model = _load_model()
        if model is not None:
            features = _extract_features(scored_ticker).reshape(1, -1)
            prob = model.predict_proba(features)[0]
            # Index 1 = probability of profitable outcome
            ml_prob = prob[1] if len(prob) > 1 else prob[0]
            return float(np.clip(ml_prob * 100, 0, 100))
    except Exception:
        pass

    # ── Improved heuristic fallback ──
    return _heuristic_confidence(scored_ticker)


def _heuristic_confidence(scored_ticker) -> float:
    """
    Improved heuristic confidence — weighted multi-factor score.
    Each factor contributes proportionally instead of flat bonuses.
    """
    try:
        score = getattr(scored_ticker, "composite_score", 50)
        phase = getattr(scored_ticker, "kinematic_phase", "CRUISE")
        regime = getattr(scored_ticker, "regime", "RANDOM")
        rvol = getattr(scored_ticker, "rel_volume", 1.0)
        rsi = getattr(scored_ticker, "rsi", 50)
        hurst = getattr(scored_ticker, "hurst", 0.5)
        entropy = getattr(scored_ticker, "entropy", 0.5)
        pct = getattr(scored_ticker, "pct_change", 0.0)
        rr = getattr(scored_ticker, "risk_reward", 1.0)
        energy_v2 = getattr(scored_ticker, "energy_v2_score", 0.0)

        confidence = 30.0  # Lower base for more dynamic range

        # Score quality (0-25 pts)
        if score >= 70:
            confidence += 25
        elif score >= 60:
            confidence += 18
        elif score >= 50:
            confidence += 10
        elif score < 40:
            confidence -= 10

        # Phase alignment (0-18 pts)
        if phase == "IGNITION":
            confidence += 18
        elif phase == "CRUISE":
            confidence += 8
        elif phase == "DECEL":
            confidence -= 5
        elif phase == "REVERSAL":
            confidence -= 12

        # Regime confirmation (0-12 pts)
        if regime in ("STRONG_TREND", "CLEAN_REVERSION"):
            confidence += 12
        elif regime in ("NOISY_TREND", "MEAN_REVERTING"):
            confidence += 5
        elif regime in ("CHOPPY", "RANDOM"):
            confidence -= 8

        # Volume confirmation (0-12 pts)
        if rvol >= 3.0:
            confidence += 12
        elif rvol >= 2.0:
            confidence += 10
        elif rvol >= 1.5:
            confidence += 6
        elif rvol < 0.5:
            confidence -= 8

        # RSI context (0-8 pts)
        if 30 <= rsi <= 70:
            confidence += 4
        elif rsi < 25 or rsi > 75:
            confidence += 8  # Extreme = high-probability reversal
        elif rsi < 30 or rsi > 70:
            confidence += 6

        # Hurst clarity (0-8 pts)
        hurst_dist = abs(hurst - 0.5)
        if hurst_dist > 0.15:
            confidence += 8
        elif hurst_dist > 0.08:
            confidence += 4

        # Entropy predictability (0-8 pts)
        if entropy < 0.5:
            confidence += 8
        elif entropy < 0.7:
            confidence += 5
        elif entropy > 0.85:
            confidence -= 8

        # Risk/reward (0-10 pts)
        if rr >= 3.0:
            confidence += 10
        elif rr >= 2.0:
            confidence += 8
        elif rr >= 1.5:
            confidence += 4
        elif 0 < rr < 1.0:
            confidence -= 5

        # Energy v2 boost (0-10 pts) — new physics engine
        if energy_v2 >= 75:
            confidence += 10
        elif energy_v2 >= 60:
            confidence += 6
        elif energy_v2 >= 45:
            confidence += 3

        # Move quality (not chasing)
        if 1.0 < abs(pct) < 5.0:
            confidence += 4
        elif abs(pct) > 10:
            confidence -= 8  # Chasing

        # Black-Scholes probability boost (0-8 pts)
        # If option play exists, use BS P(ITM) to validate the trade direction
        try:
            from analysis.options_math import compute_option_probabilities
            bs = compute_option_probabilities(scored_ticker)
            prob_itm = bs.get("safe_prob_itm", 0)
            if prob_itm > 0:
                if 40 <= prob_itm <= 70:
                    confidence += 8    # Sweet spot: good odds, not fully priced in
                elif 25 <= prob_itm < 40:
                    confidence += 4    # Decent odds for OTM
                elif prob_itm > 70:
                    confidence += 3    # High prob but expensive premium
                elif prob_itm < 15:
                    confidence -= 5    # Lottery ticket, low edge
        except Exception:
            pass

        return float(np.clip(confidence, 0, 100))

    except Exception:
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
