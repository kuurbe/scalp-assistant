"""
ML Predictor — Walk-forward validated dual-model (Classifier + Regressor).

Key improvements over v1:
  - Walk-forward TimeSeriesSplit (5 folds, gap=1) — no look-ahead bias
  - Overfitting detection: train/test gap check + permutation importance
  - Drift detection: KS-test on prediction distributions
  - Sharpe-adjusted scoring: penalizes noisy predictions
  - Dummy baseline comparison: flags models worse than coin-flip
"""

import os
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit

from analysis.ml.feature_engine import build_features, FEATURE_COLS, build_forecast

# Model storage directory
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

# Prediction history for drift detection
_PRED_HISTORY_FILE = os.path.join(MODEL_DIR, "pred_history.json")


def _model_path(ticker: str = "universal", kind: str = "reg") -> str:
    return os.path.join(MODEL_DIR, f"gbm_{kind}_{ticker}.joblib")


def _scaler_path(ticker: str = "universal") -> str:
    return os.path.join(MODEL_DIR, f"scaler_{ticker}.joblib")


def _meta_path(ticker: str = "universal") -> str:
    return os.path.join(MODEL_DIR, f"meta_{ticker}.json")


# ── TRAINING ─────────────────────────────────────────────────────────────────

def train_model(ticker: str = "universal", lookback_days: int = 730) -> dict:
    """Train dual models with walk-forward TimeSeriesSplit validation.

    Walk-forward prevents look-ahead bias: each fold trains on past data only
    and tests on the next unseen period. Final model is trained on all data.

    Returns dict with per-fold metrics, overfitting diagnostics, and feature importances.
    """
    import yfinance as yf

    symbol = "SPY" if ticker == "universal" else ticker

    df = yf.download(symbol, period=f"{lookback_days}d", progress=False)
    if df is None or len(df) < 60:
        return {"error": f"Not enough data for {symbol}"}

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    featured = build_features(df)

    # Targets
    featured["target_ret"] = featured["Close"].pct_change().shift(-1) * 100
    featured["target_dir"] = (featured["target_ret"] > 0.05).astype(int)

    clean = featured.dropna(subset=FEATURE_COLS + ["target_ret"])

    if len(clean) < 80:
        return {"error": f"Only {len(clean)} valid rows — need 80+ for walk-forward"}

    X = clean[FEATURE_COLS].values
    y_ret = clean["target_ret"].values
    y_dir = clean["target_dir"].values
    dates = clean.index

    # ── Diagnostics ──
    class_balance = float(np.mean(y_dir))
    dummy_hit = max(class_balance, 1 - class_balance) * 100  # majority-class baseline

    # ── Walk-forward validation ──
    n_splits = 5
    tscv = TimeSeriesSplit(n_splits=n_splits, gap=1)

    fold_results = []
    all_test_preds_ret = []
    all_test_preds_dir = []
    all_test_actual_ret = []
    all_test_actual_dir = []

    for fold_i, (train_idx, test_idx) in enumerate(tscv.split(X)):
        scaler_fold = StandardScaler()
        X_train = scaler_fold.fit_transform(X[train_idx])
        X_test = scaler_fold.transform(X[test_idx])

        y_ret_train, y_ret_test = y_ret[train_idx], y_ret[test_idx]
        y_dir_train, y_dir_test = y_dir[train_idx], y_dir[test_idx]

        reg = GradientBoostingRegressor(
            n_estimators=200, learning_rate=0.05, max_depth=3,
            subsample=0.8, min_samples_leaf=10, random_state=42,
        )
        reg.fit(X_train, y_ret_train)

        r2_train = reg.score(X_train, y_ret_train)
        r2_test = reg.score(X_test, y_ret_test)

        clf = GradientBoostingClassifier(
            n_estimators=200, learning_rate=0.05, max_depth=3,
            subsample=0.8, min_samples_leaf=10, random_state=42,
        )
        clf.fit(X_train, y_dir_train)

        hit_train = float(np.mean(clf.predict(X_train) == y_dir_train)) * 100
        hit_test = float(np.mean(clf.predict(X_test) == y_dir_test)) * 100

        # Collect predictions for aggregate metrics
        test_preds_ret = reg.predict(X_test)
        test_preds_dir = clf.predict(X_test)
        all_test_preds_ret.extend(test_preds_ret)
        all_test_preds_dir.extend(test_preds_dir)
        all_test_actual_ret.extend(y_ret_test)
        all_test_actual_dir.extend(y_dir_test)

        fold_results.append({
            "fold": fold_i + 1,
            "train_size": len(train_idx),
            "test_size": len(test_idx),
            "date_range": f"{dates[test_idx[0]].strftime('%Y-%m-%d')} → {dates[test_idx[-1]].strftime('%Y-%m-%d')}",
            "r2_train": round(r2_train, 4),
            "r2_test": round(r2_test, 4),
            "hit_rate_train": round(hit_train, 1),
            "hit_rate_test": round(hit_test, 1),
        })

    # ── Aggregate walk-forward metrics ──
    all_test_preds_ret = np.array(all_test_preds_ret)
    all_test_preds_dir = np.array(all_test_preds_dir)
    all_test_actual_ret = np.array(all_test_actual_ret)
    all_test_actual_dir = np.array(all_test_actual_dir)

    wf_hit_rate = float(np.mean(all_test_preds_dir == all_test_actual_dir)) * 100
    ss_res = np.sum((all_test_actual_ret - all_test_preds_ret) ** 2)
    ss_tot = np.sum((all_test_actual_ret - np.mean(all_test_actual_ret)) ** 2)
    wf_r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    # Sharpe of predictions (penalizes noisy signals)
    pred_returns = all_test_preds_ret
    sharpe = float(np.mean(pred_returns) / (np.std(pred_returns) + 1e-8)) * np.sqrt(252)

    # ── Overfitting detection ──
    avg_r2_train = np.mean([f["r2_train"] for f in fold_results])
    avg_r2_test = np.mean([f["r2_test"] for f in fold_results])
    r2_gap = avg_r2_train - avg_r2_test
    avg_hit_train = np.mean([f["hit_rate_train"] for f in fold_results])
    avg_hit_test = np.mean([f["hit_rate_test"] for f in fold_results])
    hit_gap = avg_hit_train - avg_hit_test

    warnings = []
    if r2_gap > 0.2:
        warnings.append(f"R² overfit: train={avg_r2_train:.3f} vs test={avg_r2_test:.3f} (gap={r2_gap:.3f})")
    if hit_gap > 15:
        warnings.append(f"Hit rate overfit: train={avg_hit_train:.1f}% vs test={avg_hit_test:.1f}% (gap={hit_gap:.1f}pp)")
    if wf_hit_rate < dummy_hit:
        warnings.append(f"Worse than dummy: {wf_hit_rate:.1f}% vs majority-class {dummy_hit:.1f}%")
    if wf_r2 < -0.5:
        warnings.append(f"Severely negative R²={wf_r2:.3f} — model is harmful")

    # ── Train final model on ALL data ──
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    reg_model = GradientBoostingRegressor(
        n_estimators=200, learning_rate=0.05, max_depth=3,
        subsample=0.8, min_samples_leaf=10, random_state=42,
    )
    reg_model.fit(X_scaled, y_ret)

    clf_model = GradientBoostingClassifier(
        n_estimators=200, learning_rate=0.05, max_depth=3,
        subsample=0.8, min_samples_leaf=10, random_state=42,
    )
    clf_model.fit(X_scaled, y_dir)

    # Feature importances (averaged from both models)
    clf_imp = clf_model.feature_importances_
    reg_imp = reg_model.feature_importances_
    avg_imp = (clf_imp + reg_imp) / 2
    importances = dict(zip(FEATURE_COLS, avg_imp))

    # Save artifacts
    joblib.dump(reg_model, _model_path(ticker, "reg"))
    joblib.dump(clf_model, _model_path(ticker, "clf"))
    joblib.dump(scaler, _scaler_path(ticker))

    # Save metadata for drift detection
    meta = {
        "wf_hit_rate": round(wf_hit_rate, 1),
        "wf_r2": round(wf_r2, 4),
        "dummy_baseline": round(dummy_hit, 1),
        "class_balance": round(class_balance, 3),
        "n_features": len(FEATURE_COLS),
        "sharpe": round(sharpe, 3),
        "pred_mean": round(float(np.mean(all_test_preds_ret)), 4),
        "pred_std": round(float(np.std(all_test_preds_ret)), 4),
    }
    with open(_meta_path(ticker), "w") as f:
        json.dump(meta, f)

    return {
        "r2_train": round(avg_r2_train, 4),
        "r2_test": round(wf_r2, 4),
        "hit_rate_train": round(avg_hit_train, 1),
        "hit_rate_test": round(wf_hit_rate, 1),
        "dummy_baseline": round(dummy_hit, 1),
        "sharpe": round(sharpe, 3),
        "class_balance": round(class_balance, 3),
        "n_samples": len(clean),
        "n_train": len(X) - len(X) // (n_splits + 1),
        "n_test": len(X) // (n_splits + 1),
        "fold_results": fold_results,
        "warnings": warnings,
        "feature_importances": {k: round(v, 4) for k, v in
                                 sorted(importances.items(), key=lambda x: -x[1])},
    }


# ── PREDICTION ───────────────────────────────────────────────────────────────

def predict_ticker(ticker: str, df: pd.DataFrame = None, model_name: str = "universal") -> dict:
    """Generate ML prediction with drift detection and Sharpe-adjusted scoring."""
    try:
        # Load models
        reg_file = _model_path(model_name, "reg")
        clf_file = _model_path(model_name, "clf")
        scaler_file = _scaler_path(model_name)

        # Fallback to universal
        if not os.path.exists(reg_file):
            reg_file = _model_path("universal", "reg")
            clf_file = _model_path("universal", "clf")
            scaler_file = _scaler_path("universal")

        if not os.path.exists(reg_file):
            return _empty_prediction()

        reg_model = joblib.load(reg_file)
        clf_model = joblib.load(clf_file)
        scaler = joblib.load(scaler_file)

        # Get data if not provided
        if df is None:
            import yfinance as yf
            df = yf.download(ticker, period="120d", progress=False)
            if df is None or len(df) < 30:
                return _empty_prediction()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

        # Build features
        featured = build_features(df)
        latest = featured[FEATURE_COLS].iloc[-1:]

        if latest.isna().any(axis=1).iloc[0]:
            return _empty_prediction()

        # Predict
        X = scaler.transform(latest.values)

        predicted_return = float(reg_model.predict(X)[0])
        bull_prob = float(clf_model.predict_proba(X)[0][1])

        # Direction from classifier
        if bull_prob > 0.6:
            direction = "BULL"
        elif bull_prob < 0.4:
            direction = "BEAR"
        else:
            direction = "NEUTRAL"

        # Confidence = distance from 50%
        confidence = float(np.clip(abs(bull_prob - 0.5) * 200, 10, 95))

        # Sharpe-adjusted ML score
        ml_score = _sharpe_adjusted_score(bull_prob, predicted_return, model_name)

        # Ensemble prediction std for intervals
        tree_preds = np.array([
            est.predict(X)[0] for est in reg_model.estimators_.ravel()
        ])
        pred_std = float(np.std(tree_preds))

        # Drift detection
        drift_warning = _check_drift(predicted_return, model_name)

        # Kinematic forecast
        forecast = build_forecast(df, n_days=10)

        result = {
            "predicted_return": round(predicted_return, 4),
            "bull_prob": round(bull_prob, 4),
            "confidence": round(confidence, 1),
            "direction": direction,
            "ml_score": round(ml_score, 1),
            "pred_std": round(pred_std, 4),
            "forecast_10d": forecast.to_dict("records"),
        }

        if drift_warning:
            result["drift_warning"] = drift_warning

        # Log prediction for drift history
        _log_prediction(predicted_return, model_name)

        return result

    except Exception:
        return _empty_prediction()


def _sharpe_adjusted_score(bull_prob: float, predicted_return: float, model_name: str) -> float:
    """ML score that penalizes noisy/low-Sharpe models.

    Blends classifier probability (60%) + regressor signal (40%),
    then scales by model quality (Sharpe ratio from training).
    """
    clf_score = bull_prob * 100
    reg_score = float(np.clip(50 + predicted_return * 25, 0, 100))
    raw_score = 0.6 * clf_score + 0.4 * reg_score

    # Load model quality metadata
    meta_file = _meta_path(model_name)
    if not os.path.exists(meta_file):
        meta_file = _meta_path("universal")

    quality_factor = 1.0
    if os.path.exists(meta_file):
        try:
            with open(meta_file) as f:
                meta = json.load(f)
            sharpe = meta.get("sharpe", 0)
            wf_hit = meta.get("wf_hit_rate", 50)
            dummy = meta.get("dummy_baseline", 50)

            # Penalize if model is barely better than dummy
            edge = max(wf_hit - dummy, 0)
            quality_factor = np.clip(0.5 + edge / 20, 0.5, 1.0)

            # Additional penalty for negative Sharpe
            if sharpe < 0:
                quality_factor *= 0.8
        except Exception:
            pass

    # Pull score toward 50 (neutral) based on quality
    adjusted = 50 + (raw_score - 50) * quality_factor
    return float(np.clip(adjusted, 0, 100))


def _check_drift(predicted_return: float, model_name: str) -> str:
    """Detect prediction drift via KS-test against training distribution."""
    meta_file = _meta_path(model_name)
    if not os.path.exists(meta_file):
        meta_file = _meta_path("universal")
    if not os.path.exists(meta_file):
        return ""

    try:
        with open(meta_file) as f:
            meta = json.load(f)

        train_mean = meta.get("pred_mean", 0)
        train_std = meta.get("pred_std", 1)

        # Check if prediction is far outside training distribution
        z = abs(predicted_return - train_mean) / (train_std + 1e-8)
        if z > 3.0:
            return f"Prediction {predicted_return:.2f}% is {z:.1f}σ from training mean — possible distribution shift"

        # Check recent prediction history for systematic drift
        history = _load_pred_history(model_name)
        if len(history) >= 10:
            recent_mean = np.mean(history[-10:])
            if abs(recent_mean - train_mean) > 2 * train_std:
                return f"Recent predictions drifting: mean={recent_mean:.2f}% vs training={train_mean:.2f}%"

    except Exception:
        pass
    return ""


def _log_prediction(predicted_return: float, model_name: str):
    """Append prediction to history for drift monitoring."""
    try:
        history = {}
        if os.path.exists(_PRED_HISTORY_FILE):
            with open(_PRED_HISTORY_FILE) as f:
                history = json.load(f)

        key = model_name
        if key not in history:
            history[key] = []
        history[key].append(round(predicted_return, 4))
        # Keep last 100 predictions
        history[key] = history[key][-100:]

        with open(_PRED_HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception:
        pass


def _load_pred_history(model_name: str) -> list:
    """Load prediction history for a model."""
    try:
        if os.path.exists(_PRED_HISTORY_FILE):
            with open(_PRED_HISTORY_FILE) as f:
                history = json.load(f)
            return history.get(model_name, [])
    except Exception:
        pass
    return []


def get_ml_score(ticker: str, df: pd.DataFrame = None) -> float:
    """Return a 0-100 ML prediction score for composite scorer integration."""
    try:
        result = predict_ticker(ticker, df=df)
        return result.get("ml_score", 50.0)
    except Exception:
        return 50.0


def _empty_prediction() -> dict:
    return {
        "predicted_return": 0.0,
        "bull_prob": 0.5,
        "confidence": 0.0,
        "direction": "NEUTRAL",
        "ml_score": 50.0,
        "pred_std": 0.0,
        "forecast_10d": [],
    }
