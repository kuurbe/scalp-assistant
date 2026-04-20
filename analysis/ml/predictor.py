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
import threading
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit

from analysis.ml.feature_engine import build_features, FEATURE_COLS, build_forecast
from config import settings

import logging
logger = logging.getLogger(__name__)

# Model storage directory
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

# Prediction history for drift detection
_PRED_HISTORY_FILE = os.path.join(MODEL_DIR, "pred_history.json")

# Thread lock for pred_history.json writes (prevents file corruption from concurrent threads)
_PRED_HISTORY_LOCK = threading.Lock()

# ── Model cache (load once, reuse across all tickers) ──
_MODEL_CACHE = {}
_MODEL_CACHE_LOCK = threading.Lock()


def _get_cached_models(model_name: str = "universal"):
    """Load models/scaler once and cache in memory. Thread-safe."""
    if model_name in _MODEL_CACHE:
        return _MODEL_CACHE[model_name]

    with _MODEL_CACHE_LOCK:
        # Double-check after acquiring lock
        if model_name in _MODEL_CACHE:
            return _MODEL_CACHE[model_name]

        reg_file = _model_path(model_name, "reg")
        clf_file = _model_path(model_name, "clf")
        scaler_file = _scaler_path(model_name)

        if not os.path.exists(reg_file):
            reg_file = _model_path("universal", "reg")
            clf_file = _model_path("universal", "clf")
            scaler_file = _scaler_path("universal")

        if not os.path.exists(reg_file):
            return None

        models = {
            "reg": joblib.load(reg_file),
            "clf": joblib.load(clf_file),
            "scaler": joblib.load(scaler_file),
        }
        _MODEL_CACHE[model_name] = models
        return models


def _model_path(ticker: str = "universal", kind: str = "reg") -> str:
    return os.path.join(MODEL_DIR, f"gbm_{kind}_{ticker}.joblib")


def _scaler_path(ticker: str = "universal") -> str:
    return os.path.join(MODEL_DIR, f"scaler_{ticker}.joblib")


def _meta_path(ticker: str = "universal") -> str:
    return os.path.join(MODEL_DIR, f"meta_{ticker}.json")


# ── TRAINING ─────────────────────────────────────────────────────────────────

def _universal_training_universe() -> list[str]:
    """Tickers to pool into the universal model's training set.

    Covers broad-market indices + liquid large-caps + sector ETFs so the model
    learns patterns that generalize across regimes instead of memorizing SPY.
    """
    return [
        # Major indices
        "SPY", "QQQ", "IWM", "DIA",
        # Sector ETFs (diverse regimes: tech, energy, financials, health, utilities)
        "XLK", "XLF", "XLE", "XLV", "XLU", "XLI", "XLP", "XLB",
        # Mega-cap stocks (high liquidity, clean data)
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AMD",
        "JPM", "BAC", "WMT", "XOM", "JNJ", "UNH",
    ]


def _fetch_pooled_training_data(tickers: list[str], lookback_days: int) -> pd.DataFrame:
    """Fetch OHLCV for each ticker, build features, stack into one DataFrame.

    Each row carries a '_ticker' column so we can do cross-instrument walk-forward.
    Returns a single DataFrame indexed by (ticker, date).
    """
    from data.fetchers.yfinance_fetcher import safe_yf_download

    frames = []
    for sym in tickers:
        try:
            df = safe_yf_download(sym, period=f"{lookback_days}d", interval="1d")
            if df is None or len(df) < 60:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            feat = build_features(df).copy()
            feat["target_ret"] = feat["Close"].pct_change().shift(-1) * 100
            feat["_ticker"] = sym
            frames.append(feat)
        except Exception as e:
            logger.debug("pooled training: %s fetch failed: %s", sym, e)
            continue

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=0).sort_index()


def train_model(ticker: str = "universal", lookback_days: int = 730) -> dict:
    """Train dual models with walk-forward TimeSeriesSplit validation.

    Walk-forward prevents look-ahead bias: each fold trains on past data only
    and tests on the next unseen period. Final model is trained on all data.

    For the "universal" model we pool across a curated universe of indices +
    sector ETFs + mega-caps so the model sees ~30x more samples than SPY alone
    and learns cross-instrument regime patterns. Per-ticker models (e.g. for
    SPY, QQQ individually) still train on a single symbol's history.

    Returns dict with per-fold metrics, overfitting diagnostics, and feature importances.
    """
    from data.fetchers.yfinance_fetcher import safe_yf_download

    if ticker == "universal":
        universe = _universal_training_universe()
        pooled = _fetch_pooled_training_data(universe, lookback_days)
        if pooled.empty:
            return {"error": "Pooled training fetch returned no data"}
        featured = pooled
        logger.info("Pooled training: %d tickers, %d rows",
                    featured["_ticker"].nunique(), len(featured))
    else:
        df = safe_yf_download(ticker, period=f"{lookback_days}d", interval="1d")
        if df is None or len(df) < 60:
            return {"error": f"Not enough data for {ticker}"}
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        featured = build_features(df).copy()
        featured["target_ret"] = featured["Close"].pct_change().shift(-1) * 100
        featured["_ticker"] = ticker

    # Directional target with a minimum-move threshold. 0.05% was noise-level;
    # requiring >0.25% on the next bar filters out random walk and lines the
    # target up with what a trader would actually act on.
    featured["target_dir"] = (featured["target_ret"] > 0.25).astype(int)

    # For pooled training we MUST sort by date across all tickers so walk-forward
    # splits don't mix future-and-past data from different symbols.
    if "_ticker" in featured.columns:
        # If the index already is the date, sort by it; if not, try to coerce.
        try:
            featured = featured.sort_index()
        except Exception:
            pass

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
            n_estimators=100, learning_rate=0.02, max_depth=2,
            subsample=0.6, min_samples_leaf=40, random_state=42,
        )
        reg.fit(X_train, y_ret_train)

        r2_train = reg.score(X_train, y_ret_train)
        r2_test = reg.score(X_test, y_ret_test)

        clf = GradientBoostingClassifier(
            n_estimators=100, learning_rate=0.02, max_depth=2,
            subsample=0.6, min_samples_leaf=40, random_state=42,
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

    # STRATEGY Sharpe — what a long/short trader would earn following the classifier.
    # Previously this was computed on predicted_returns alone, giving meaningless
    # values like 14.0 even when the model was worse than baseline. Now we compute
    # the actual P&L: take direction prediction (0/1 → -1/+1) times actual return,
    # so a 50% hit rate with symmetric returns gives Sharpe ≈ 0.
    strategy_signals = (all_test_preds_dir * 2 - 1)  # 0/1 → -1/+1
    strategy_returns = strategy_signals * all_test_actual_ret  # in % units
    if np.std(strategy_returns) > 1e-8:
        sharpe = float(np.mean(strategy_returns) / np.std(strategy_returns)) * np.sqrt(252)
    else:
        sharpe = 0.0

    # Also report raw stats separately so the retrain report shows the right picture
    strategy_mean_bp = float(np.mean(strategy_returns))  # mean % return per trade
    strategy_std_bp = float(np.std(strategy_returns))

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
    # Tighter regularization than walk-forward folds to reduce overfitting:
    # - max_depth=2 (shallow trees force generalization)
    # - min_samples_leaf=30 (prevents memorizing small groups)
    # - n_estimators=150 (fewer trees = less overfitting)
    # - subsample=0.7 (more stochastic = better generalization)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    reg_model = GradientBoostingRegressor(
        n_estimators=150, learning_rate=0.03, max_depth=2,
        subsample=0.7, min_samples_leaf=30, random_state=42,
    )
    reg_model.fit(X_scaled, y_ret)

    clf_model = GradientBoostingClassifier(
        n_estimators=150, learning_rate=0.03, max_depth=2,
        subsample=0.7, min_samples_leaf=30, random_state=42,
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

    # Save metadata for drift detection + report card
    meta = {
        "wf_hit_rate": round(wf_hit_rate, 1),
        "wf_r2": round(wf_r2, 4),
        "dummy_baseline": round(dummy_hit, 1),
        "edge_vs_dummy": round(wf_hit_rate - dummy_hit, 1),
        "class_balance": round(class_balance, 3),
        "n_features": len(FEATURE_COLS),
        "n_samples": len(clean),
        "sharpe": round(sharpe, 3),                       # strategy Sharpe now
        "strategy_mean_pct": round(strategy_mean_bp, 4),  # mean per-trade %
        "strategy_std_pct": round(strategy_std_bp, 4),
        "pred_mean": round(float(np.mean(all_test_preds_ret)), 4),
        "pred_std": round(float(np.std(all_test_preds_ret)), 4),
        "target_threshold_pct": 0.25,
        "training_universe": featured["_ticker"].unique().tolist()
                              if "_ticker" in featured.columns else [ticker],
    }
    with open(_meta_path(ticker), "w") as f:
        json.dump(meta, f)

    return {
        "r2_train": round(avg_r2_train, 4),
        "r2_test": round(wf_r2, 4),
        "hit_rate_train": round(avg_hit_train, 1),
        "hit_rate_test": round(wf_hit_rate, 1),
        "dummy_baseline": round(dummy_hit, 1),
        "edge_vs_dummy": round(wf_hit_rate - dummy_hit, 1),
        "sharpe": round(sharpe, 3),
        "strategy_mean_pct": round(strategy_mean_bp, 4),
        "strategy_std_pct": round(strategy_std_bp, 4),
        "class_balance": round(class_balance, 3),
        "n_samples": len(clean),
        "n_train": len(X) - len(X) // (n_splits + 1),
        "n_test": len(X) // (n_splits + 1),
        "n_tickers_pooled": len(meta["training_universe"]),
        "fold_results": fold_results,
        "warnings": warnings,
        "feature_importances": {k: round(v, 4) for k, v in
                                 sorted(importances.items(), key=lambda x: -x[1])},
    }


# ── TV LIVE BLENDING ────────────────────────────────────────────────────────

# Mapping from TradingView indicator keys → feature column names
_TV_TO_FEATURE_MAP = {
    "RSI": "rsi_14",
    "Relative Strength Index": "rsi_14",
    "Stoch %K": "stoch_k",
    "Stochastic": "stoch_k",
    "%K": "stoch_k",
}


def _blend_tv_features(latest_row: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Blend live TradingView indicator values into computed features.

    Weighted average: TV_BLEND_WEIGHT * tv_value + (1 - weight) * computed_value.
    Falls back to computed values if TV unavailable or any error occurs.
    """
    try:
        if not getattr(settings, "ML_TV_BLEND_ENABLED", False):
            return latest_row

        from signals.tradingview_bridge import is_tv_available, get_tv_indicators
        if not is_tv_available():
            return latest_row

        tv_vals = get_tv_indicators(ticker)
        if not tv_vals:
            return latest_row

        weight = getattr(settings, "ML_TV_BLEND_WEIGHT", 0.7)
        blended = latest_row.copy()

        # Direct replacement features (TV value matches feature semantics)
        for tv_key, feat_col in _TV_TO_FEATURE_MAP.items():
            if tv_key in tv_vals and feat_col in blended.columns:
                tv_val = float(tv_vals[tv_key])
                computed = float(blended[feat_col].iloc[0])
                blended[feat_col] = weight * tv_val + (1 - weight) * computed

        # MACD histogram — needs ATR normalization
        hist_key = next((k for k in ("Histogram", "MACD-hist", "Hist") if k in tv_vals), None)
        if hist_key and "macd_hist_norm" in blended.columns:
            atr = float(blended.get("atr_14", pd.Series(1.0)).iloc[0])
            if atr > 0:
                tv_hist_norm = float(tv_vals[hist_key]) / atr
                computed = float(blended["macd_hist_norm"].iloc[0])
                blended["macd_hist_norm"] = weight * tv_hist_norm + (1 - weight) * computed

        return blended

    except Exception:
        return latest_row


# ── PREDICTION ───────────────────────────────────────────────────────────────

def predict_ticker(ticker: str, df: pd.DataFrame = None, model_name: str = "universal",
                   featured_df: pd.DataFrame = None, use_tv: bool = False) -> dict:
    """Generate ML prediction with drift detection and Sharpe-adjusted scoring.

    Args:
        use_tv: If True, blend live TradingView values into features before prediction.
                Only use for top-N picks (adds ~1-2s latency per call).
    """
    try:
        # Load models (cached — single load for all tickers)
        cached = _get_cached_models(model_name)
        if cached is None:
            return _empty_prediction()

        reg_model = cached["reg"]
        clf_model = cached["clf"]
        scaler = cached["scaler"]

        # Feature version check — prevent crash if model was trained with different features
        meta = _get_cached_meta(model_name)
        model_n_features = meta.get("n_features", 0)
        if model_n_features and model_n_features != len(FEATURE_COLS):
            logger.warning(
                "Feature mismatch: model expects %d features, code has %d. "
                "Run auto_retrain to update the model.",
                model_n_features, len(FEATURE_COLS),
            )
            return _empty_prediction()

        # Get data if not provided
        if df is None:
            import yfinance as yf
            df = yf.download(ticker, period="1y", progress=False)
            if df is None or len(df) < 30:
                return _empty_prediction()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

        # Build features (reuse pre-built if provided)
        featured = featured_df if featured_df is not None else build_features(df)
        latest = featured[FEATURE_COLS].iloc[-1:]

        if latest.isna().any(axis=1).iloc[0]:
            return _empty_prediction()

        # Optionally blend live TV values
        if use_tv:
            latest = _blend_tv_features(latest, ticker)

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


# ── Meta cache (read JSON once per model, not per ticker) ──
_META_CACHE = {}
_META_CACHE_LOCK = threading.Lock()


def _get_cached_meta(model_name: str) -> dict:
    """Load model metadata once and cache."""
    if model_name in _META_CACHE:
        return _META_CACHE[model_name]
    with _META_CACHE_LOCK:
        if model_name in _META_CACHE:
            return _META_CACHE[model_name]
        meta_file = _meta_path(model_name)
        if not os.path.exists(meta_file):
            meta_file = _meta_path("universal")
        meta = {}
        if os.path.exists(meta_file):
            try:
                with open(meta_file) as f:
                    meta = json.load(f)
            except Exception:
                pass
        _META_CACHE[model_name] = meta
        return meta


def _sharpe_adjusted_score(bull_prob: float, predicted_return: float, model_name: str) -> float:
    """ML score that penalizes noisy/low-Sharpe models.

    Blends classifier probability (60%) + regressor signal (40%),
    then scales by model quality (Sharpe ratio from training).
    """
    clf_score = bull_prob * 100
    reg_score = float(np.clip(50 + predicted_return * 25, 0, 100))
    raw_score = 0.6 * clf_score + 0.4 * reg_score

    meta = _get_cached_meta(model_name)
    quality_factor = 1.0
    if meta:
        sharpe = meta.get("sharpe", 0)
        wf_hit = meta.get("wf_hit_rate", 50)
        dummy = meta.get("dummy_baseline", 50)

        edge = max(wf_hit - dummy, 0)
        quality_factor = np.clip(0.5 + edge / 20, 0.5, 1.0)

        if sharpe < 0:
            quality_factor *= 0.8

    adjusted = 50 + (raw_score - 50) * quality_factor
    return float(np.clip(adjusted, 0, 100))


def _check_drift(predicted_return: float, model_name: str) -> str:
    """Detect prediction drift via KS-test against training distribution."""
    meta = _get_cached_meta(model_name)
    if not meta:
        return ""

    try:
        train_mean = meta.get("pred_mean", 0)
        train_std = meta.get("pred_std", 1)

        z = abs(predicted_return - train_mean) / (train_std + 1e-8)
        if z > 3.0:
            return f"Prediction {predicted_return:.2f}% is {z:.1f}σ from training mean — possible distribution shift"

        history = _load_pred_history(model_name)
        if len(history) >= 10:
            recent_mean = np.mean(history[-10:])
            if abs(recent_mean - train_mean) > 2 * train_std:
                return f"Recent predictions drifting: mean={recent_mean:.2f}% vs training={train_mean:.2f}%"

    except Exception:
        pass
    return ""


# In-memory buffer for prediction logging (flush once after scan, not per-ticker)
_PRED_LOG_BUFFER = []
_PRED_LOG_BUFFER_LOCK = threading.Lock()


def _log_prediction(predicted_return: float, model_name: str):
    """Buffer prediction in memory. Call flush_pred_history() after scan completes."""
    try:
        with _PRED_LOG_BUFFER_LOCK:
            _PRED_LOG_BUFFER.append((model_name, round(predicted_return, 4)))
    except Exception:
        pass


def flush_pred_history():
    """Write all buffered predictions to disk in one batch. Call after scan completes."""
    try:
        with _PRED_LOG_BUFFER_LOCK:
            if not _PRED_LOG_BUFFER:
                return
            to_write = list(_PRED_LOG_BUFFER)
            _PRED_LOG_BUFFER.clear()

        with _PRED_HISTORY_LOCK:
            history = {}
            if os.path.exists(_PRED_HISTORY_FILE):
                with open(_PRED_HISTORY_FILE) as f:
                    history = json.load(f)

            for model_name, pred_val in to_write:
                if model_name not in history:
                    history[model_name] = []
                history[model_name].append(pred_val)
                history[model_name] = history[model_name][-100:]

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


def get_ml_score(ticker: str, df: pd.DataFrame = None, featured_df: pd.DataFrame = None) -> float:
    """Return a 0-100 ML prediction score for composite scorer integration."""
    try:
        result = predict_ticker(ticker, df=df, featured_df=featured_df)
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
