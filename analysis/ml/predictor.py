"""
ML Predictor — Dual-model approach: Classifier for direction + Regressor for magnitude.

Provides:
  - train_model(): Train both models on historical data
  - predict_ticker(): Generate next-day prediction with directional probability
  - get_ml_score(): Return 0-100 score for composite scorer integration
"""

import os
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler

from analysis.ml.feature_engine import build_features, FEATURE_COLS, build_forecast

# Model storage directory
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models")
os.makedirs(MODEL_DIR, exist_ok=True)


def _model_path(ticker: str = "universal", kind: str = "reg") -> str:
    return os.path.join(MODEL_DIR, f"gbm_{kind}_{ticker}.joblib")


def _scaler_path(ticker: str = "universal") -> str:
    return os.path.join(MODEL_DIR, f"scaler_{ticker}.joblib")


def train_model(ticker: str = "universal", lookback_days: int = 365) -> dict:
    """Train dual models (classifier + regressor) on historical data.

    The classifier predicts direction (up/down) — optimized for hit rate.
    The regressor predicts magnitude — used for price targets.

    Parameters
    ----------
    ticker : str
        Ticker symbol, or "universal" to train on SPY as a general model.
    lookback_days : int
        Days of history to use for training.

    Returns
    -------
    dict with keys: r2_train, r2_test, hit_rate_train, hit_rate_test, n_samples, feature_importances
    """
    import yfinance as yf

    symbol = "SPY" if ticker == "universal" else ticker

    # Download data
    df = yf.download(symbol, period=f"{lookback_days}d", progress=False)
    if df is None or len(df) < 60:
        return {"error": f"Not enough data for {symbol}"}

    # Handle MultiIndex columns from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    featured = build_features(df)

    # Target: next-day % return
    featured["target_ret"] = featured["Close"].pct_change().shift(-1) * 100
    # Directional target: 1 = up (>0.05%), 0 = down/flat
    featured["target_dir"] = (featured["target_ret"] > 0.05).astype(int)

    clean = featured.dropna(subset=FEATURE_COLS + ["target_ret"])

    if len(clean) < 40:
        return {"error": f"Only {len(clean)} valid rows after feature engineering"}

    X = clean[FEATURE_COLS].values
    y_ret = clean["target_ret"].values
    y_dir = clean["target_dir"].values

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Time-series split (no shuffle)
    split = int(len(X_scaled) * 0.8)
    X_train, X_test = X_scaled[:split], X_scaled[split:]
    y_ret_train, y_ret_test = y_ret[:split], y_ret[split:]
    y_dir_train, y_dir_test = y_dir[:split], y_dir[split:]

    # ── Regressor (magnitude) ──
    reg_model = GradientBoostingRegressor(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=3,  # Reduced from 4 to prevent overfitting
        subsample=0.8,
        min_samples_leaf=10,
        random_state=42,
    )
    reg_model.fit(X_train, y_ret_train)

    r2_train = reg_model.score(X_train, y_ret_train)
    r2_test = reg_model.score(X_test, y_ret_test)

    # ── Classifier (direction) ──
    clf_model = GradientBoostingClassifier(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=3,
        subsample=0.8,
        min_samples_leaf=10,
        random_state=42,
    )
    clf_model.fit(X_train, y_dir_train)

    hit_rate_train = float(np.mean(clf_model.predict(X_train) == y_dir_train)) * 100
    hit_rate_test = float(np.mean(clf_model.predict(X_test) == y_dir_test)) * 100

    # Save all artifacts
    joblib.dump(reg_model, _model_path(ticker, "reg"))
    joblib.dump(clf_model, _model_path(ticker, "clf"))
    joblib.dump(scaler, _scaler_path(ticker))

    importances = dict(zip(FEATURE_COLS, clf_model.feature_importances_))

    return {
        "r2_train": round(r2_train, 4),
        "r2_test": round(r2_test, 4),
        "hit_rate_train": round(hit_rate_train, 1),
        "hit_rate_test": round(hit_rate_test, 1),
        "n_samples": len(clean),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "feature_importances": {k: round(v, 4) for k, v in
                                 sorted(importances.items(), key=lambda x: -x[1])},
    }


def predict_ticker(ticker: str, df: pd.DataFrame = None, model_name: str = "universal") -> dict:
    """Generate ML prediction using dual model (classifier + regressor).

    Parameters
    ----------
    ticker : str
        Ticker symbol.
    df : pd.DataFrame, optional
        Pre-fetched OHLCV data. If None, fetches via yfinance.
    model_name : str
        Which model to use ("universal" or a specific ticker).

    Returns
    -------
    dict with: predicted_return, confidence, direction, bull_prob, ml_score, forecast_10d
    """
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

        # Legacy fallback: old single-model format
        if not os.path.exists(reg_file):
            old_model = os.path.join(MODEL_DIR, f"gbm_{model_name}.joblib")
            if not os.path.exists(old_model):
                old_model = os.path.join(MODEL_DIR, "gbm_universal.joblib")
            if os.path.exists(old_model):
                return _predict_legacy(ticker, df, old_model, scaler_file)
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

        # Regressor: predicted return magnitude
        predicted_return = float(reg_model.predict(X)[0])

        # Classifier: directional probability
        bull_prob = float(clf_model.predict_proba(X)[0][1])  # P(up)
        direction_pred = clf_model.predict(X)[0]

        # Direction from classifier (more reliable than regressor sign)
        if bull_prob > 0.6:
            direction = "BULL"
        elif bull_prob < 0.4:
            direction = "BEAR"
        else:
            direction = "NEUTRAL"

        # Confidence = distance from 50% (higher = more certain)
        confidence = float(np.clip(abs(bull_prob - 0.5) * 200, 10, 95))

        # ML score: blend classifier probability (60%) + regressor signal (40%)
        clf_score = bull_prob * 100  # 0-100 where 100 = definitely going up
        reg_score = float(np.clip(50 + predicted_return * 25, 0, 100))
        ml_score = 0.6 * clf_score + 0.4 * reg_score

        # Regressor ensemble std for prediction interval
        tree_preds = np.array([
            est.predict(X)[0] for est in reg_model.estimators_.ravel()
        ])
        pred_std = float(np.std(tree_preds))

        # Kinematic forecast
        forecast = build_forecast(df, n_days=10)

        return {
            "predicted_return": round(predicted_return, 4),
            "bull_prob": round(bull_prob, 4),
            "confidence": round(confidence, 1),
            "direction": direction,
            "ml_score": round(ml_score, 1),
            "pred_std": round(pred_std, 4),
            "forecast_10d": forecast.to_dict("records"),
        }

    except Exception:
        return _empty_prediction()


def _predict_legacy(ticker, df, model_file, scaler_file):
    """Fallback for old single-model format."""
    try:
        model = joblib.load(model_file)
        scaler = joblib.load(scaler_file)

        if df is None:
            import yfinance as yf
            df = yf.download(ticker, period="120d", progress=False)
            if df is None or len(df) < 30:
                return _empty_prediction()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

        featured = build_features(df)
        latest = featured[FEATURE_COLS].iloc[-1:]
        if latest.isna().any(axis=1).iloc[0]:
            return _empty_prediction()

        X = scaler.transform(latest.values)
        predicted_return = float(model.predict(X)[0])
        direction = "BULL" if predicted_return > 0.1 else ("BEAR" if predicted_return < -0.1 else "NEUTRAL")
        ml_score = float(np.clip(50 + predicted_return * 25, 0, 100))
        forecast = build_forecast(df, n_days=10)

        return {
            "predicted_return": round(predicted_return, 4),
            "bull_prob": 0.5,
            "confidence": 50.0,
            "direction": direction,
            "ml_score": round(ml_score, 1),
            "pred_std": 0.0,
            "forecast_10d": forecast.to_dict("records"),
        }
    except Exception:
        return _empty_prediction()


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
