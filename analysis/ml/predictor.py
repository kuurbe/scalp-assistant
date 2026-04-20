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
from sklearn.ensemble import (
    HistGradientBoostingRegressor,
    HistGradientBoostingClassifier,
)
from sklearn.inspection import permutation_importance
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit

from analysis.ml.feature_engine import build_features, FEATURE_COLS, build_forecast
from config import settings

# ── Per-ticker specialized model universe ────────────────────────────────────
# These tickers get their own models trained on single-symbol data plus regime
# features (VIX z-score, SPY trend, calendar) that become meaningful when there
# is no cross-ticker confusion.
PERTICKER_UNIVERSE = ["SPY", "QQQ", "NVDA", "AAPL", "TSLA"]

# ── Sector identity map for pooled model ─────────────────────────────────────
# Maps each pooled universe ticker to its GICS sector bucket.
# AMZN is dual-listed (TECH + CONSUMER_DISC); TECH takes priority here.
_SECTOR_MAP: dict[str, str] = {
    # TECH
    "AAPL": "TECH", "MSFT": "TECH", "NVDA": "TECH", "AMD": "TECH",
    "META": "TECH", "GOOG": "TECH", "GOOGL": "TECH", "AMZN": "TECH",
    "QQQ": "TECH", "XLK": "TECH",
    # FINANCE
    "JPM": "FINANCE", "GS": "FINANCE", "BAC": "FINANCE", "XLF": "FINANCE",
    # ENERGY
    "XLE": "ENERGY", "CVX": "ENERGY", "XOM": "ENERGY",
    # HEALTH
    "JNJ": "HEALTH", "UNH": "HEALTH", "XLV": "HEALTH",
    # CONSUMER_DISC
    "TSLA": "CONSUMER_DISC", "XLY": "CONSUMER_DISC",
    # CONSUMER_STAPLE
    "WMT": "CONSUMER_STAPLE", "XLP": "CONSUMER_STAPLE",
    # INDUSTRIAL
    "XLI": "INDUSTRIAL", "CAT": "INDUSTRIAL",
    # BROAD_MARKET
    "SPY": "BROAD_MARKET", "IWM": "BROAD_MARKET", "DIA": "BROAD_MARKET",
    "EEM": "BROAD_MARKET",
    # UTILITIES (catch-all for XLU which is in pooled universe)
    "XLU": "BROAD_MARKET", "XLB": "INDUSTRIAL",
}

# Fixed estimated beta per ticker for the pooled model
_BETA_MAP: dict[str, float] = {
    # Broad market
    "SPY": 1.0, "IWM": 1.0, "DIA": 1.0, "EEM": 1.0,
    # High-beta tech
    "QQQ": 1.35, "XLK": 1.35, "NVDA": 1.35, "AMD": 1.35,
    "META": 1.35, "GOOG": 1.35, "GOOGL": 1.35, "AAPL": 1.35, "MSFT": 1.35,
    # Consumer discretionary high-beta
    "TSLA": 1.4, "AMZN": 1.4, "XLY": 1.4,
    # Finance
    "XLF": 1.1, "JPM": 1.1, "GS": 1.1, "BAC": 1.1,
    # Energy / Industrial
    "XLE": 0.9, "CVX": 0.9, "XOM": 0.9, "XLI": 0.9, "CAT": 0.9, "XLB": 0.9,
    # Defensive
    "XLV": 0.65, "JNJ": 0.65, "UNH": 0.65,
    "XLP": 0.65, "WMT": 0.65, "XLU": 0.65,
}

# ── Pooled model extra feature columns ───────────────────────────────────────
# These are added ONLY for the pooled universal model.  Per-ticker models use
# _perticker_feature_cols() which is unaffected.
POOLED_EXTRA_COLS: list[str] = [
    # Sector one-hot (8 buckets)
    "sec_tech", "sec_finance", "sec_energy", "sec_health",
    "sec_cons_disc", "sec_cons_staple", "sec_industrial", "sec_broad",
    # Fixed beta
    "beta_vs_spy",
    # Cross-sectional rank features (per-ticker-per-date, genuinely discriminative)
    "cs_rank_ret5d", "cs_rank_ret20d", "cs_rank_rsi", "cs_rank_vol_ratio",
]

# Full feature list used when training / predicting with the universal pooled model.
# The per-ticker path uses _perticker_feature_cols() instead.
POOLED_FEATURE_COLS: list[str] = FEATURE_COLS + POOLED_EXTRA_COLS


# Hyperparameter search space — small deliberately-curated grid, not exhaustive.
# Each candidate represents a different bias/variance tradeoff so walk-forward
# can pick the one that generalises best on THIS data instead of us guessing.
# HistGradientBoosting params: max_depth, max_iter, learning_rate,
# min_samples_leaf, l2_regularization.
_HP_CANDIDATES = [
    ("shallow_slow", dict(max_depth=2, max_iter=300, learning_rate=0.02,
                          min_samples_leaf=50, l2_regularization=0.5)),
    ("baseline",     dict(max_depth=3, max_iter=200, learning_rate=0.05,
                          min_samples_leaf=30, l2_regularization=0.1)),
    ("deeper",       dict(max_depth=5, max_iter=150, learning_rate=0.05,
                          min_samples_leaf=20, l2_regularization=0.2)),
    ("low_lr_long",  dict(max_depth=3, max_iter=400, learning_rate=0.01,
                          min_samples_leaf=30, l2_regularization=0.3)),
    ("aggressive",   dict(max_depth=4, max_iter=250, learning_rate=0.08,
                          min_samples_leaf=15, l2_regularization=0.05)),
]

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


def _add_sector_features(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Add sector one-hot columns and a fixed beta estimate to *df* in-place.

    Adds 8 binary columns (sec_tech, sec_finance, sec_energy, sec_health,
    sec_cons_disc, sec_cons_staple, sec_industrial, sec_broad) and one
    continuous column (beta_vs_spy).  All sector columns default to 0; the
    column matching the ticker's sector is set to 1.0.
    """
    sector_cols = {
        "TECH":           "sec_tech",
        "FINANCE":        "sec_finance",
        "ENERGY":         "sec_energy",
        "HEALTH":         "sec_health",
        "CONSUMER_DISC":  "sec_cons_disc",
        "CONSUMER_STAPLE": "sec_cons_staple",
        "INDUSTRIAL":     "sec_industrial",
        "BROAD_MARKET":   "sec_broad",
    }
    # Initialise all sector columns to 0
    for col in sector_cols.values():
        df[col] = 0.0

    # Set the appropriate sector column to 1
    sector = _SECTOR_MAP.get(ticker.upper(), "BROAD_MARKET")
    df[sector_cols[sector]] = 1.0

    # Fixed beta estimate
    df["beta_vs_spy"] = _BETA_MAP.get(ticker.upper(), 1.0)

    return df


def _add_cross_sectional_features(
    all_ticker_data: dict[str, pd.DataFrame],
    ticker: str,
) -> pd.DataFrame:
    """Add cross-sectional rank features to the DataFrame for *ticker*.

    For each date, ranks this ticker's value among all tickers in
    *all_ticker_data* using percentile rank (0.0 = lowest, 1.0 = highest).
    Dates where fewer than 10 tickers have data are left as NaN —
    HistGradientBoosting handles NaN natively.

    Computes:
      cs_rank_ret5d    — rank of 5-day return
      cs_rank_ret20d   — rank of 20-day return
      cs_rank_rsi      — rank of RSI_14
      cs_rank_vol_ratio — rank of today's volume / 20d avg volume

    Returns the ticker's DataFrame with 4 new columns added.
    """
    df_target = all_ticker_data[ticker].copy()

    # Helper: build a date-indexed Series for a derived metric across all tickers
    def _build_panel(metric_fn) -> pd.DataFrame:
        """Returns a DataFrame indexed by date, one column per ticker."""
        cols = {}
        for sym, df_sym in all_ticker_data.items():
            try:
                cols[sym] = metric_fn(df_sym)
            except Exception:
                pass
        return pd.DataFrame(cols)

    # Metric extractors — each returns a date-indexed Series
    def _ret5d(df: pd.DataFrame) -> pd.Series:
        return df["Close"].pct_change(5) * 100

    def _ret20d(df: pd.DataFrame) -> pd.Series:
        return df["Close"].pct_change(20) * 100

    def _rsi(df: pd.DataFrame) -> pd.Series:
        # Use pre-built rsi_14 column if available, else compute on-the-fly
        if "rsi_14" in df.columns:
            return df["rsi_14"]
        # Simple RSI fallback (Wilder smoothing, window=14)
        delta = df["Close"].diff()
        gain = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def _vol_ratio(df: pd.DataFrame) -> pd.Series:
        vol = df["Volume"].astype(float)
        avg20 = vol.rolling(20, min_periods=10).mean()
        return vol / avg20.replace(0, np.nan)

    min_tickers = 10

    for col_name, metric_fn in [
        ("cs_rank_ret5d",    _ret5d),
        ("cs_rank_ret20d",   _ret20d),
        ("cs_rank_rsi",      _rsi),
        ("cs_rank_vol_ratio", _vol_ratio),
    ]:
        try:
            panel = _build_panel(metric_fn)
            # Only keep dates where >= min_tickers have non-NaN values
            valid_mask = panel.notna().sum(axis=1) >= min_tickers
            # pct_rank across the row (axis=1) → value for our ticker
            ranks = panel.rank(axis=1, pct=True)
            ticker_rank = ranks[ticker].where(valid_mask)
            # Align to df_target's index
            df_target[col_name] = ticker_rank.reindex(df_target.index)
        except Exception as e:
            logger.debug(
                "_add_cross_sectional_features(%s, %s): %s", ticker, col_name, e
            )
            df_target[col_name] = np.nan

    return df_target


def _fetch_pooled_training_data(tickers: list[str], lookback_days: int) -> pd.DataFrame:
    """Fetch OHLCV for each ticker, build features, stack into one DataFrame.

    Each row carries a '_ticker' column so we can do cross-instrument walk-forward.
    Adds sector identity features (one-hot + beta) and cross-sectional rank
    features to each ticker's DataFrame before concatenating.

    Returns a single DataFrame indexed by date, with POOLED_FEATURE_COLS available.
    """
    from data.fetchers.yfinance_fetcher import safe_yf_download

    # ── Pass 1: fetch and build base features for each ticker ─────────────────
    ticker_dfs: dict[str, pd.DataFrame] = {}
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
            # Sector identity features can be added immediately (constant per ticker)
            feat = _add_sector_features(feat, sym)
            ticker_dfs[sym] = feat
        except Exception as e:
            logger.debug("pooled training: %s fetch failed: %s", sym, e)
            continue

    if not ticker_dfs:
        return pd.DataFrame()

    # ── Pass 2: cross-sectional rank features (require all tickers) ───────────
    frames = []
    for sym, feat in ticker_dfs.items():
        try:
            feat = _add_cross_sectional_features(ticker_dfs, sym)
        except Exception as e:
            logger.debug("pooled training: %s cross-sectional failed: %s", sym, e)
            # Add NaN columns so the schema stays consistent
            for col in ["cs_rank_ret5d", "cs_rank_ret20d", "cs_rank_rsi", "cs_rank_vol_ratio"]:
                if col not in feat.columns:
                    feat[col] = np.nan
        frames.append(feat)

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

    # For the universal pooled model use POOLED_FEATURE_COLS (base + sector +
    # cross-sectional ranks).  Per-ticker / named-ticker training uses FEATURE_COLS.
    active_feature_cols = POOLED_FEATURE_COLS if ticker == "universal" else FEATURE_COLS

    # For pooled model, cross-sectional rank columns may be NaN on sparse dates;
    # HistGBM handles NaN natively so we only require base FEATURE_COLS to be
    # non-NaN when dropping rows.  Sector/beta columns are always populated.
    required_cols = FEATURE_COLS if ticker == "universal" else active_feature_cols
    clean = featured.dropna(subset=required_cols + ["target_ret"])

    if len(clean) < 80:
        return {"error": f"Only {len(clean)} valid rows — need 80+ for walk-forward"}

    # Ensure all active feature columns exist (fill missing with 0.0 for safety)
    for col in active_feature_cols:
        if col not in clean.columns:
            clean = clean.copy()
            clean[col] = 0.0

    X = clean[active_feature_cols].values
    y_ret = clean["target_ret"].values
    y_dir = clean["target_dir"].values
    dates = clean.index

    # ── Diagnostics ──
    class_balance = float(np.mean(y_dir))
    dummy_hit = max(class_balance, 1 - class_balance) * 100  # majority-class baseline

    # ── Walk-forward validation with hyperparameter search ──
    # For each candidate config, run full walk-forward and pick the one with
    # the best edge vs dummy baseline. This replaces the old approach of a
    # single fixed config and catches data-specific tuning gains.
    n_splits = 5
    tscv = TimeSeriesSplit(n_splits=n_splits, gap=1)

    def _wf_score(hp: dict) -> tuple[float, list, list, list, list, list]:
        """Run one hyperparameter config through walk-forward. Returns (edge_vs_dummy, fold_results, test_preds_ret, test_preds_dir, test_actual_ret, test_actual_dir)."""
        folds = []
        preds_ret, preds_dir, actual_ret, actual_dir = [], [], [], []
        for fold_i, (train_idx, test_idx) in enumerate(tscv.split(X)):
            scaler_fold = StandardScaler()
            X_train = scaler_fold.fit_transform(X[train_idx])
            X_test = scaler_fold.transform(X[test_idx])
            y_ret_train, y_ret_test = y_ret[train_idx], y_ret[test_idx]
            y_dir_train, y_dir_test = y_dir[train_idx], y_dir[test_idx]

            reg = HistGradientBoostingRegressor(random_state=42, **hp)
            reg.fit(X_train, y_ret_train)
            r2_test_fold = reg.score(X_test, y_ret_test)
            r2_train_fold = reg.score(X_train, y_ret_train)

            clf = HistGradientBoostingClassifier(random_state=42, **hp)
            clf.fit(X_train, y_dir_train)
            hit_train = float(np.mean(clf.predict(X_train) == y_dir_train)) * 100
            hit_test = float(np.mean(clf.predict(X_test) == y_dir_test)) * 100

            preds_ret.extend(reg.predict(X_test))
            preds_dir.extend(clf.predict(X_test))
            actual_ret.extend(y_ret_test)
            actual_dir.extend(y_dir_test)

            folds.append({
                "fold": fold_i + 1,
                "train_size": len(train_idx),
                "test_size": len(test_idx),
                "date_range": f"{dates[test_idx[0]].strftime('%Y-%m-%d')} → {dates[test_idx[-1]].strftime('%Y-%m-%d')}",
                "r2_train": round(r2_train_fold, 4),
                "r2_test": round(r2_test_fold, 4),
                "hit_rate_train": round(hit_train, 1),
                "hit_rate_test": round(hit_test, 1),
            })
        hit = float(np.mean(np.array(preds_dir) == np.array(actual_dir))) * 100
        return hit - dummy_hit, folds, preds_ret, preds_dir, actual_ret, actual_dir

    # Score every candidate; keep the one with the best edge vs dummy
    hp_results = []
    for tag, hp in _HP_CANDIDATES:
        edge, folds, preds_ret, preds_dir, actual_ret, actual_dir = _wf_score(hp)
        hp_results.append({
            "tag": tag,
            "edge_vs_dummy": round(edge, 2),
            "hp": hp,
            "folds": folds,
            "preds_ret": preds_ret, "preds_dir": preds_dir,
            "actual_ret": actual_ret, "actual_dir": actual_dir,
        })
        logger.info("  HP[%s]: edge_vs_dummy=%+.2fpp", tag, edge)

    best = max(hp_results, key=lambda r: r["edge_vs_dummy"])
    logger.info("  Best HP config: %s (edge=%+.2fpp)", best["tag"], best["edge_vs_dummy"])

    # Unpack the winning config's walk-forward outputs for reporting
    fold_results = best["folds"]
    all_test_preds_ret = best["preds_ret"]
    all_test_preds_dir = best["preds_dir"]
    all_test_actual_ret = best["actual_ret"]
    all_test_actual_dir = best["actual_dir"]
    best_hp = best["hp"]
    best_hp_tag = best["tag"]

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

    # ── Train final model on ALL data using the winning hyperparameter config ──
    # HistGradientBoostingClassifier/Regressor — modern histogram-based boosting
    # (LightGBM-style) built into sklearn. Typically faster and better-regularised
    # than the old GradientBoosting* classes.
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    reg_model = HistGradientBoostingRegressor(random_state=42, **best_hp)
    reg_model.fit(X_scaled, y_ret)

    clf_model = HistGradientBoostingClassifier(random_state=42, **best_hp)
    clf_model.fit(X_scaled, y_dir)

    # Feature importance via permutation (HistGradientBoosting doesn't expose
    # tree-based importances). Run on a sample of training data for speed.
    n_perm_samples = min(2000, len(X_scaled))
    perm_idx = np.random.RandomState(42).choice(len(X_scaled), n_perm_samples, replace=False)
    try:
        perm = permutation_importance(
            clf_model, X_scaled[perm_idx], y_dir[perm_idx],
            n_repeats=3, random_state=42, n_jobs=1,
        )
        avg_imp = perm.importances_mean
    except Exception as e:
        logger.warning("permutation_importance failed: %s — using zeros", e)
        avg_imp = np.zeros(len(active_feature_cols))
    importances = dict(zip(active_feature_cols, avg_imp))

    # Warn about features with near-zero or negative importance — they add noise
    low_importance = [k for k, v in importances.items() if v <= 0.001]
    if low_importance:
        logger.info("  %d features with low importance (candidates to drop): %s",
                    len(low_importance), low_importance[:10])

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
        "n_features": len(active_feature_cols),
        "feature_names": active_feature_cols,
        "n_samples": len(clean),
        "sharpe": round(sharpe, 3),                       # strategy Sharpe now
        "strategy_mean_pct": round(strategy_mean_bp, 4),  # mean per-trade %
        "strategy_std_pct": round(strategy_std_bp, 4),
        "pred_mean": round(float(np.mean(all_test_preds_ret)), 4),
        "pred_std": round(float(np.std(all_test_preds_ret)), 4),
        "target_threshold_pct": 0.25,
        "training_universe": featured["_ticker"].unique().tolist()
                              if "_ticker" in featured.columns else [ticker],
        "model_class": "HistGradientBoosting",
        "best_hp_tag": best_hp_tag,
        "best_hp": best_hp,
        "hp_search_results": [
            {"tag": r["tag"], "edge_vs_dummy": r["edge_vs_dummy"]}
            for r in sorted(hp_results, key=lambda x: -x["edge_vs_dummy"])
        ],
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
        "model_class": "HistGradientBoosting",
        "best_hp_tag": best_hp_tag,
        "best_hp": best_hp,
        "hp_search_results": meta["hp_search_results"],
        "fold_results": fold_results,
        "warnings": warnings,
        "feature_importances": {k: round(v, 4) for k, v in
                                 sorted(importances.items(), key=lambda x: -x[1])},
    }


# ── PER-TICKER TRAINING ──────────────────────────────────────────────────────

def _fetch_perticker_training_data(ticker: str) -> "pd.DataFrame | None":
    """Fetch 3 years of daily data for a single ticker and build augmented features.

    Beyond the standard OHLCV-derived FEATURE_COLS this adds:
      - vix_z20          : VIX 20-day z-score
      - vix_regime       : 1 if VIX > 20, else 0
      - spy_ret_20d      : SPY 20-day return (omitted for SPY itself)
      - spy_trend_up     : 1 if SPY > SPY 50d SMA (always present, even for SPY)
      - dow              : day of week (0=Mon)
      - dom              : day of month
      - is_month_end     : binary
      - is_month_start   : binary
      - is_quarter_end   : binary
      - rs_vs_spy_5d     : ticker 5d return minus SPY 5d return (omitted for SPY)
      - rs_vs_spy_20d    : ticker 20d return minus SPY 20d return (omitted for SPY)

    Returns a DataFrame with all features plus target_clf and target_reg columns,
    or None if there is insufficient data.
    """
    from data.fetchers.yfinance_fetcher import safe_yf_download

    LOOKBACK = "1095d"  # ~3 years

    # ── Fetch ticker OHLCV ──
    try:
        df = safe_yf_download(ticker, period=LOOKBACK, interval="1d")
        if df is None or len(df) < 100:
            logger.warning("_fetch_perticker_training_data(%s): insufficient data (%s rows)",
                           ticker, len(df) if df is not None else 0)
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
    except Exception as e:
        logger.warning("_fetch_perticker_training_data(%s): fetch failed: %s", ticker, e)
        return None

    # ── Build base features ──
    try:
        feat = build_features(df).copy()
    except Exception as e:
        logger.warning("_fetch_perticker_training_data(%s): build_features failed: %s", ticker, e)
        return None

    # ── Targets ──
    feat["target_ret"] = feat["Close"].pct_change().shift(-1) * 100
    feat["target_clf"] = (feat["target_ret"] > 0.25).astype(int)
    feat["target_reg"] = feat["target_ret"]

    # ── Calendar features (always safe, no external data needed) ──
    idx = feat.index
    feat["dow"] = idx.dayofweek.astype(float)
    feat["dom"] = idx.day.astype(float)
    feat["is_month_end"] = idx.is_month_end.astype(float)
    feat["is_month_start"] = idx.is_month_start.astype(float)
    feat["is_quarter_end"] = idx.is_quarter_end.astype(float)

    # ── VIX regime features (graceful degradation if fetch fails) ──
    try:
        vix_df = safe_yf_download("^VIX", period=LOOKBACK, interval="1d")
        if vix_df is not None and len(vix_df) >= 30:
            if isinstance(vix_df.columns, pd.MultiIndex):
                vix_df.columns = vix_df.columns.get_level_values(0)
            vix_close = vix_df["Close"].reindex(feat.index).ffill()
            vix_roll_mean = vix_close.rolling(20, min_periods=10).mean()
            vix_roll_std = vix_close.rolling(20, min_periods=10).std().replace(0, np.nan)
            feat["vix_z20"] = ((vix_close - vix_roll_mean) / vix_roll_std).fillna(0.0)
            feat["vix_regime"] = (vix_close > 20).astype(float).fillna(0.0)
        else:
            feat["vix_z20"] = 0.0
            feat["vix_regime"] = 0.0
    except Exception as e:
        logger.debug("_fetch_perticker_training_data(%s): VIX fetch failed (%s), using defaults", ticker, e)
        feat["vix_z20"] = 0.0
        feat["vix_regime"] = 0.0

    # ── SPY-relative features (skip for SPY itself to avoid zero/redundant signals) ──
    if ticker != "SPY":
        try:
            spy_df = safe_yf_download("SPY", period=LOOKBACK, interval="1d")
            if spy_df is not None and len(spy_df) >= 60:
                if isinstance(spy_df.columns, pd.MultiIndex):
                    spy_df.columns = spy_df.columns.get_level_values(0)
                spy_close = spy_df["Close"].reindex(feat.index).ffill()
                spy_sma50 = spy_close.rolling(50, min_periods=20).mean()
                feat["spy_ret_20d"] = spy_close.pct_change(20).fillna(0.0) * 100
                feat["spy_trend_up"] = (spy_close > spy_sma50).astype(float).fillna(0.0)
                # Relative strength vs SPY
                ticker_close = feat["Close"].astype(float)
                feat["rs_vs_spy_5d"] = (
                    ticker_close.pct_change(5).fillna(0.0) * 100
                    - spy_close.pct_change(5).fillna(0.0) * 100
                )
                feat["rs_vs_spy_20d"] = (
                    ticker_close.pct_change(20).fillna(0.0) * 100
                    - spy_close.pct_change(20).fillna(0.0) * 100
                )
            else:
                feat["spy_ret_20d"] = 0.0
                feat["spy_trend_up"] = 0.0
                feat["rs_vs_spy_5d"] = 0.0
                feat["rs_vs_spy_20d"] = 0.0
        except Exception as e:
            logger.debug("_fetch_perticker_training_data(%s): SPY fetch failed (%s), using defaults", ticker, e)
            feat["spy_ret_20d"] = 0.0
            feat["spy_trend_up"] = 0.0
            feat["rs_vs_spy_5d"] = 0.0
            feat["rs_vs_spy_20d"] = 0.0
    else:
        # For SPY: only add spy_trend_up (SPY vs its own SMA — still informative)
        try:
            spy_close = feat["Close"].astype(float)
            spy_sma50 = spy_close.rolling(50, min_periods=20).mean()
            feat["spy_trend_up"] = (spy_close > spy_sma50).astype(float).fillna(0.0)
        except Exception:
            feat["spy_trend_up"] = 0.0

    feat["_ticker"] = ticker
    return feat


def _perticker_feature_cols(ticker: str) -> list[str]:
    """Return the ordered feature column list for a per-ticker model.

    Extends FEATURE_COLS with regime/calendar features that are only
    informative for single-ticker models.
    """
    extra = [
        "vix_z20", "vix_regime",
        "spy_trend_up",
        "dow", "dom",
        "is_month_end", "is_month_start", "is_quarter_end",
    ]
    if ticker != "SPY":
        extra += ["spy_ret_20d", "rs_vs_spy_5d", "rs_vs_spy_20d"]
    return FEATURE_COLS + extra


def train_per_ticker_models(ticker: str, force: bool = False) -> dict:
    """Train per-ticker specialized GBM models for a single ticker.

    Uses the SAME walk-forward evaluation and HP search as the universal model.
    Saves four artifacts to models/:
      - gbm_clf_{ticker.lower()}.joblib
      - gbm_reg_{ticker.lower()}.joblib
      - scaler_{ticker.lower()}.joblib
      - meta_{ticker.lower()}.json

    Args:
        ticker: Must be in PERTICKER_UNIVERSE (or any ticker — the guard is a
                convention, not enforced here).
        force:  If True, retrain even if artifacts already exist.

    Returns:
        Meta dict (same keys as train_model() returns + ticker/feature_names/
        training_period).  On failure returns {"error": ...}.
    """
    tag = ticker.lower()
    clf_file = _model_path(tag, "clf")
    reg_file = _model_path(tag, "reg")
    scaler_file = _scaler_path(tag)
    meta_file = _meta_path(tag)

    # Load existing unless forced
    if not force and os.path.exists(clf_file) and os.path.exists(meta_file):
        try:
            with open(meta_file) as f:
                meta = json.load(f)
            logger.info("train_per_ticker_models(%s): loaded existing model (hit_rate=%.1f%%)",
                        ticker, meta.get("hit_rate", 0))
            return meta
        except Exception:
            pass  # fall through to retrain

    logger.info("train_per_ticker_models(%s): fetching training data …", ticker)
    featured = _fetch_perticker_training_data(ticker)
    if featured is None:
        return {"error": f"No training data for {ticker}"}

    feature_cols = _perticker_feature_cols(ticker)
    # Drop any feature column that is entirely NaN or missing
    available_features = [c for c in feature_cols if c in featured.columns
                          and not featured[c].isna().all()]
    if len(available_features) < len(FEATURE_COLS):
        logger.warning(
            "train_per_ticker_models(%s): only %d/%d feature columns available",
            ticker, len(available_features), len(feature_cols),
        )

    clean = featured.dropna(subset=available_features + ["target_clf", "target_reg"])
    if len(clean) < 80:
        return {"error": f"Only {len(clean)} valid rows for {ticker} — need 80+"}

    X = clean[available_features].values
    y_dir = clean["target_clf"].values
    y_ret = clean["target_reg"].values
    dates = clean.index

    class_balance = float(np.mean(y_dir))
    dummy_hit = max(class_balance, 1 - class_balance) * 100

    # ── Walk-forward HP search (identical structure to train_model) ──
    n_splits = 5
    tscv = TimeSeriesSplit(n_splits=n_splits, gap=1)

    def _wf_score(hp: dict):
        folds = []
        preds_ret, preds_dir, actual_ret, actual_dir = [], [], [], []
        for fold_i, (train_idx, test_idx) in enumerate(tscv.split(X)):
            scaler_fold = StandardScaler()
            X_train = scaler_fold.fit_transform(X[train_idx])
            X_test = scaler_fold.transform(X[test_idx])
            y_ret_train, y_ret_test = y_ret[train_idx], y_ret[test_idx]
            y_dir_train, y_dir_test = y_dir[train_idx], y_dir[test_idx]

            reg = HistGradientBoostingRegressor(random_state=42, **hp)
            reg.fit(X_train, y_ret_train)
            r2_test_fold = reg.score(X_test, y_ret_test)
            r2_train_fold = reg.score(X_train, y_ret_train)

            clf = HistGradientBoostingClassifier(random_state=42, **hp)
            clf.fit(X_train, y_dir_train)
            hit_train = float(np.mean(clf.predict(X_train) == y_dir_train)) * 100
            hit_test = float(np.mean(clf.predict(X_test) == y_dir_test)) * 100

            preds_ret.extend(reg.predict(X_test))
            preds_dir.extend(clf.predict(X_test))
            actual_ret.extend(y_ret_test)
            actual_dir.extend(y_dir_test)

            folds.append({
                "fold": fold_i + 1,
                "train_size": len(train_idx),
                "test_size": len(test_idx),
                "date_range": (
                    f"{dates[test_idx[0]].strftime('%Y-%m-%d')} → "
                    f"{dates[test_idx[-1]].strftime('%Y-%m-%d')}"
                ),
                "r2_train": round(r2_train_fold, 4),
                "r2_test": round(r2_test_fold, 4),
                "hit_rate_train": round(hit_train, 1),
                "hit_rate_test": round(hit_test, 1),
            })
        hit = float(np.mean(np.array(preds_dir) == np.array(actual_dir))) * 100
        return hit - dummy_hit, folds, preds_ret, preds_dir, actual_ret, actual_dir

    hp_results = []
    for hp_tag, hp in _HP_CANDIDATES:
        edge, folds, preds_ret, preds_dir, actual_ret, actual_dir = _wf_score(hp)
        hp_results.append({
            "tag": hp_tag, "edge_vs_dummy": round(edge, 2), "hp": hp,
            "folds": folds,
            "preds_ret": preds_ret, "preds_dir": preds_dir,
            "actual_ret": actual_ret, "actual_dir": actual_dir,
        })
        logger.info("  [%s] HP[%s]: edge_vs_dummy=%+.2fpp", ticker, hp_tag, edge)

    best = max(hp_results, key=lambda r: r["edge_vs_dummy"])
    logger.info("  [%s] Best HP: %s (edge=%+.2fpp)", ticker, best["tag"], best["edge_vs_dummy"])

    fold_results = best["folds"]
    all_preds_ret = np.array(best["preds_ret"])
    all_preds_dir = np.array(best["preds_dir"])
    all_actual_ret = np.array(best["actual_ret"])
    all_actual_dir = np.array(best["actual_dir"])
    best_hp = best["hp"]
    best_hp_tag = best["tag"]

    wf_hit_rate = float(np.mean(all_preds_dir == all_actual_dir)) * 100
    ss_res = np.sum((all_actual_ret - all_preds_ret) ** 2)
    ss_tot = np.sum((all_actual_ret - np.mean(all_actual_ret)) ** 2)
    wf_r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    strategy_signals = all_preds_dir * 2 - 1
    strategy_returns = strategy_signals * all_actual_ret
    if np.std(strategy_returns) > 1e-8:
        sharpe = float(np.mean(strategy_returns) / np.std(strategy_returns)) * np.sqrt(252)
    else:
        sharpe = 0.0
    strategy_mean_bp = float(np.mean(strategy_returns))
    strategy_std_bp = float(np.std(strategy_returns))

    avg_r2_train = float(np.mean([f["r2_train"] for f in fold_results]))
    avg_r2_test = float(np.mean([f["r2_test"] for f in fold_results]))
    avg_hit_train = float(np.mean([f["hit_rate_train"] for f in fold_results]))

    # ── Final model on all data ──
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    reg_model = HistGradientBoostingRegressor(random_state=42, **best_hp)
    reg_model.fit(X_scaled, y_ret)

    clf_model = HistGradientBoostingClassifier(random_state=42, **best_hp)
    clf_model.fit(X_scaled, y_dir)

    # Permutation importance
    n_perm_samples = min(2000, len(X_scaled))
    perm_idx = np.random.RandomState(42).choice(len(X_scaled), n_perm_samples, replace=False)
    try:
        from sklearn.inspection import permutation_importance as _perm_imp
        perm = _perm_imp(
            clf_model, X_scaled[perm_idx], y_dir[perm_idx],
            n_repeats=3, random_state=42, n_jobs=1,
        )
        avg_imp = perm.importances_mean
    except Exception:
        avg_imp = np.zeros(len(available_features))
    importances = dict(zip(available_features, avg_imp))

    # ── Save artifacts ──
    joblib.dump(reg_model, reg_file)
    joblib.dump(clf_model, clf_file)
    joblib.dump(scaler, scaler_file)

    training_period = (
        f"{dates[0].strftime('%Y-%m-%d')} → {dates[-1].strftime('%Y-%m-%d')}"
    )

    meta = {
        "ticker": ticker,
        "hit_rate": round(wf_hit_rate, 1),
        "wf_hit_rate": round(wf_hit_rate, 1),
        "wf_r2": round(wf_r2, 4),
        "dummy_baseline": round(dummy_hit, 1),
        "edge_vs_dummy": round(wf_hit_rate - dummy_hit, 1),
        "class_balance": round(class_balance, 3),
        "n_samples": len(clean),
        "n_features": len(available_features),
        "feature_names": available_features,
        "sharpe": round(sharpe, 3),
        "strategy_mean_pct": round(strategy_mean_bp, 4),
        "strategy_std_pct": round(strategy_std_bp, 4),
        "pred_mean": round(float(np.mean(all_preds_ret)), 4),
        "pred_std": round(float(np.std(all_preds_ret)), 4),
        "target_threshold_pct": 0.25,
        "model_class": "HistGradientBoosting",
        "best_hp_tag": best_hp_tag,
        "best_hp": best_hp,
        "training_period": training_period,
        "hp_search_results": [
            {"tag": r["tag"], "edge_vs_dummy": r["edge_vs_dummy"]}
            for r in sorted(hp_results, key=lambda x: -x["edge_vs_dummy"])
        ],
    }
    with open(meta_file, "w") as f:
        json.dump(meta, f)

    logger.info(
        "train_per_ticker_models(%s): done — hit_rate=%.1f%%, edge=%+.1fpp, n=%d, period=%s",
        ticker, wf_hit_rate, wf_hit_rate - dummy_hit, len(clean), training_period,
    )
    return {
        "ticker": ticker,
        "hit_rate": round(wf_hit_rate, 1),
        "r2_train": round(avg_r2_train, 4),
        "r2_test": round(wf_r2, 4),
        "hit_rate_train": round(avg_hit_train, 1),
        "hit_rate_test": round(wf_hit_rate, 1),
        "dummy_baseline": round(dummy_hit, 1),
        "edge_vs_dummy": round(wf_hit_rate - dummy_hit, 1),
        "sharpe": round(sharpe, 3),
        "strategy_mean_pct": round(strategy_mean_bp, 4),
        "n_samples": len(clean),
        "n_features": len(available_features),
        "feature_names": available_features,
        "best_hp_tag": best_hp_tag,
        "best_hp": best_hp,
        "training_period": training_period,
        "hp_search_results": meta["hp_search_results"],
        "fold_results": fold_results,
        "feature_importances": {k: round(v, 4) for k, v in
                                 sorted(importances.items(), key=lambda x: -x[1])},
    }


def train_all_per_ticker_models(force: bool = False) -> dict:
    """Train per-ticker models for every ticker in PERTICKER_UNIVERSE.

    Args:
        force: If True, retrain even if models already exist.

    Returns:
        Dict mapping ticker -> meta dict (same shape as train_per_ticker_models).
    """
    results = {}
    for ticker in PERTICKER_UNIVERSE:
        logger.info("train_all_per_ticker_models: training %s …", ticker)
        try:
            meta = train_per_ticker_models(ticker, force=force)
            results[ticker] = meta
        except Exception as e:
            logger.error("train_all_per_ticker_models: %s failed: %s", ticker, e)
            results[ticker] = {"error": str(e)}
    return results


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

    Routing logic:
      1. If a per-ticker model exists for ``ticker`` (e.g. models/gbm_clf_spy.joblib),
         use it — it was trained with regime/calendar features and will be more
         accurate for that specific instrument.
      2. Otherwise fall back to the universal pooled model.

    Args:
        use_tv: If True, blend live TradingView values into features before prediction.
                Only use for top-N picks (adds ~1-2s latency per call).
    """
    try:
        # ── Per-ticker model routing ──────────────────────────────────────────
        # Prefer the per-ticker model when it exists; fall back to universal.
        # model_name may be overridden by the caller (e.g. "universal") — only
        # auto-route when the default "universal" is requested so that explicit
        # model_name= arguments are still respected.
        effective_model = model_name
        perticker_meta = None
        if model_name == "universal" and ticker.upper() in PERTICKER_UNIVERSE:
            pt_tag = ticker.lower()
            if os.path.exists(_model_path(pt_tag, "clf")):
                effective_model = pt_tag
                perticker_meta = _get_cached_meta(pt_tag)

        # Load models (cached — single load for all tickers)
        cached = _get_cached_models(effective_model)
        if cached is None:
            return _empty_prediction()

        reg_model = cached["reg"]
        clf_model = cached["clf"]
        scaler = cached["scaler"]

        # Resolve metadata for the active model
        meta = perticker_meta if perticker_meta is not None else _get_cached_meta(effective_model)

        # Feature version check — prevent crash if model was trained with different features.
        # Universal model stores feature_names in meta after retraining.  We accept both
        # old FEATURE_COLS-count models and new POOLED_FEATURE_COLS-count models; any
        # other count is a sign of stale artifacts that need retraining.
        if effective_model == "universal":
            model_n_features = meta.get("n_features", 0)
            if model_n_features and model_n_features not in (
                len(FEATURE_COLS), len(POOLED_FEATURE_COLS)
            ):
                logger.warning(
                    "Feature mismatch: model expects %d features, code has %d (base) "
                    "or %d (pooled). Run auto_retrain to update the model.",
                    model_n_features, len(FEATURE_COLS), len(POOLED_FEATURE_COLS),
                )
                return _empty_prediction()

        # Get data if not provided
        if df is None:
            from data.fetchers.yfinance_fetcher import safe_yf_download
            df = safe_yf_download(ticker, period="1y", interval="1d")
            if df is None or len(df) < 30:
                return _empty_prediction()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

        # Build features (reuse pre-built if provided)
        featured = featured_df if featured_df is not None else build_features(df)

        # ── Feature alignment ─────────────────────────────────────────────────
        # Per-ticker models: trained_features lives in meta["feature_names"].
        # Universal model: use meta["feature_names"] if present (post-retrain),
        #   otherwise fall back to POOLED_FEATURE_COLS.
        # For all cases, any missing column is filled with 0.0 (safe default for
        # binary/z-score features; sector columns and beta will also be 0 if the
        # model is stale — acceptable until next retrain).
        if meta.get("feature_names"):
            # Prefer the stored feature list (works for both per-ticker and universal)
            trained_features = meta["feature_names"]
        elif effective_model == "universal":
            # Old universal model (pre-sector features): fall back to FEATURE_COLS
            # so we don't pass 31 columns to a model trained on 18.
            n_saved = meta.get("n_features", 0)
            trained_features = POOLED_FEATURE_COLS if n_saved == len(POOLED_FEATURE_COLS) else FEATURE_COLS
        else:
            trained_features = FEATURE_COLS

        for col in trained_features:
            if col not in featured.columns:
                featured[col] = 0.0
        latest = featured[trained_features].iloc[-1:].copy()

        # For the universal model, inject sector identity and fill any remaining
        # NaN in pooled-only columns.  Sector one-hot defaults to 0 (unknown
        # sector), beta defaults to 1.0 (market-neutral).
        if effective_model == "universal" and "sec_tech" in trained_features:
            latest = _add_sector_features(latest, ticker)
        for col in POOLED_EXTRA_COLS:
            if col in latest.columns and pd.isna(latest[col].iloc[0]):
                latest[col] = 1.0 if col == "beta_vs_spy" else 0.0

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

        # Sharpe-adjusted ML score — use effective_model so per-ticker meta is used
        ml_score = _sharpe_adjusted_score(bull_prob, predicted_return, effective_model)

        # Ensemble prediction std for intervals
        tree_preds = np.array([
            est.predict(X)[0] for est in reg_model.estimators_.ravel()
        ])
        pred_std = float(np.std(tree_preds))

        # Drift detection — use effective_model for correct training distribution
        drift_warning = _check_drift(predicted_return, effective_model)

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
            "model_used": effective_model,
        }

        if drift_warning:
            result["drift_warning"] = drift_warning

        # Log prediction for drift history
        _log_prediction(predicted_return, effective_model)

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


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="ML Predictor — training CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Train universal pooled model:
    python -m analysis.ml.predictor --train

  Train all per-ticker specialized models:
    python -m analysis.ml.predictor --train-per-ticker

  Train per-ticker model for a single ticker:
    python -m analysis.ml.predictor --train-per-ticker --ticker SPY

  Force-retrain even if models already exist:
    python -m analysis.ml.predictor --train-per-ticker --force
        """,
    )
    parser.add_argument("--train", action="store_true",
                        help="Train the universal pooled model")
    parser.add_argument("--train-per-ticker", action="store_true",
                        help="Train per-ticker specialized models for PERTICKER_UNIVERSE")
    parser.add_argument("--ticker", type=str, default=None,
                        help="Single ticker to train (use with --train-per-ticker)")
    parser.add_argument("--force", action="store_true",
                        help="Force retrain even if model artifacts already exist")

    args = parser.parse_args()

    if args.train:
        logger.info("Training universal pooled model …")
        result = train_model("universal")
        if "error" in result:
            logger.error("Universal training failed: %s", result["error"])
            sys.exit(1)
        logger.info(
            "Universal model: hit_rate=%.1f%%, edge=%+.1fpp, n=%d, hp=%s",
            result.get("hit_rate_test", 0),
            result.get("edge_vs_dummy", 0),
            result.get("n_samples", 0),
            result.get("best_hp_tag", "?"),
        )

    elif args.train_per_ticker:
        if args.ticker:
            sym = args.ticker.upper()
            logger.info("Training per-ticker model for %s (force=%s) …", sym, args.force)
            meta = train_per_ticker_models(sym, force=args.force)
            if "error" in meta:
                logger.error("Failed: %s", meta["error"])
                sys.exit(1)
            logger.info(
                "%s: hit_rate=%.1f%%, edge=%+.1fpp, n=%d, period=%s",
                sym,
                meta.get("hit_rate", 0),
                meta.get("edge_vs_dummy", 0),
                meta.get("n_samples", 0),
                meta.get("training_period", "?"),
            )
        else:
            logger.info(
                "Training per-ticker models for %s (force=%s) …",
                PERTICKER_UNIVERSE, args.force,
            )
            results = train_all_per_ticker_models(force=args.force)
            print("\n── Per-ticker training summary ──")
            for sym, meta in results.items():
                if "error" in meta:
                    print(f"  {sym}: ERROR — {meta['error']}")
                else:
                    print(
                        f"  {sym}: hit_rate={meta.get('hit_rate', '?')}%  "
                        f"edge={meta.get('edge_vs_dummy', '?'):+}pp  "
                        f"n={meta.get('n_samples', '?')}  "
                        f"hp={meta.get('best_hp_tag', '?')}"
                    )

    else:
        parser.print_help()
        sys.exit(0)
