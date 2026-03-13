"""
ML Feature Engine — Kinematics + Volatility + Momentum + Cross-Asset feature pipeline.

Generates features per ticker from raw OHLCV data:
  - Linear regression (velocity, r², trend direction)
  - Kinematic quadratic (acceleration, residuals)
  - Momentum (5/10/20-day returns, daily % change)
  - Rolling stats (5/10/20 day mean, std)
  - Derived force (mean deviation, z-score)
  - Regime indicator (60-day trend direction)
  - Cross-asset (VIX level, VIX change, TLT return — fetched once, cached)
  - Volatility ensembles (Yang-Zhang, GJR-GARCH proxy, HAR-RV, LPV, super hybrid)
  - Volume-price (OBV slope, VWAP deviation)

Includes trend validation via ADF stationarity tests.
"""

import numpy as np
import pandas as pd
from scipy import stats


# ── 1. KINEMATICS FEATURES ─────────────────────────────────────────────────

def compute_kinematic_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute linear regression + quadratic fit features from close prices."""
    out = df.copy()
    close = out["Close"].values.astype(float)
    t = np.arange(len(close))

    if len(close) < 10:
        for col in _KINEMATIC_COLS:
            out[col] = 0.0
        return out

    slope, intercept, r_value, p_value, std_err = stats.linregress(t, close)
    out["linear_velocity"] = slope
    out["linear_residual"] = close - (slope * t + intercept)
    out["r_squared"] = r_value ** 2
    out["trend_direction"] = np.sign(slope)

    coeffs = np.polyfit(t, close, 2)
    out["acceleration"] = 2 * coeffs[0]
    out["quad_residual"] = close - np.polyval(coeffs, t)

    return out


_KINEMATIC_COLS = [
    "linear_velocity", "linear_residual", "r_squared",
    "trend_direction", "acceleration", "quad_residual",
]


# ── 2. MOMENTUM + REGIME FEATURES ──────────────────────────────────────────

def compute_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute rate of change, rolling stats, regime indicator, and volume-price."""
    out = df.copy()
    c = out["Close"]

    # Multi-period momentum (returns, not diffs — scale-invariant)
    out["ret_5d"] = c.pct_change(5) * 100
    out["ret_10d"] = c.pct_change(10) * 100
    out["ret_20d"] = c.pct_change(20) * 100
    out["pct_change_1d"] = c.pct_change(1) * 100

    # Rolling stats
    out["rolling_std_5"] = c.pct_change().rolling(5).std() * 100
    out["rolling_std_10"] = c.pct_change().rolling(10).std() * 100
    out["rolling_std_20"] = c.pct_change().rolling(20).std() * 100

    # Z-score (mean reversion signal)
    mean_20 = c.rolling(20).mean()
    std_20 = c.rolling(20).std().replace(0, np.nan)
    out["z_score_20"] = ((c - mean_20) / std_20).fillna(0)

    # Regime indicator: rolling 60-day return sign (trend vs mean-reversion context)
    out["regime_60d"] = np.sign(c.pct_change(60)).fillna(0)

    # Volume-price features (if volume available)
    if "Volume" in out.columns:
        vol = out["Volume"].astype(float)
        # OBV slope (5-day linear regression of cumulative OBV)
        obv = (np.sign(c.diff()) * vol).cumsum()
        if len(obv) >= 5:
            obv_slope = obv.rolling(5).apply(
                lambda x: stats.linregress(range(len(x)), x)[0] if len(x) == 5 else 0,
                raw=False
            )
            out["obv_slope_5"] = obv_slope
        else:
            out["obv_slope_5"] = 0.0

        # Relative volume (vs 20-day mean)
        avg_vol = vol.rolling(20, min_periods=5).mean()
        out["rel_volume"] = (vol / avg_vol.replace(0, np.nan)).fillna(1.0)
    else:
        out["obv_slope_5"] = 0.0
        out["rel_volume"] = 1.0

    return out


# ── 3. CROSS-ASSET FEATURES ────────────────────────────────────────────────

_CROSS_ASSET_CACHE = {}


def compute_cross_asset_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add VIX level, VIX 1-day change, and TLT return as features.

    These are fetched once and cached for the session. If fetch fails,
    defaults to 0 (graceful degradation).
    """
    out = df.copy()
    n = len(out)

    # Try to fetch cross-asset data (cached)
    vix_data = _fetch_cross_asset("^VIX", n)
    tlt_data = _fetch_cross_asset("TLT", n)

    if vix_data is not None and len(vix_data) >= n:
        out["vix_level"] = vix_data["Close"].reindex(out.index).fillna(method="ffill").fillna(20.0).values
        out["vix_change_1d"] = pd.Series(out["vix_level"]).pct_change().fillna(0).values * 100
    else:
        out["vix_level"] = 20.0
        out["vix_change_1d"] = 0.0

    if tlt_data is not None and len(tlt_data) >= n:
        tlt_close = tlt_data["Close"].reindex(out.index).fillna(method="ffill")
        out["tlt_ret_1d"] = tlt_close.pct_change().fillna(0).values * 100
    else:
        out["tlt_ret_1d"] = 0.0

    return out


def _fetch_cross_asset(symbol: str, min_bars: int) -> pd.DataFrame:
    """Fetch cross-asset data with caching."""
    global _CROSS_ASSET_CACHE
    if symbol in _CROSS_ASSET_CACHE:
        return _CROSS_ASSET_CACHE[symbol]
    try:
        import yfinance as yf
        data = yf.download(symbol, period="200d", progress=False)
        if data is not None and isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        _CROSS_ASSET_CACHE[symbol] = data
        return data
    except Exception:
        return None


# ── 4. VOLATILITY FEATURES ─────────────────────────────────────────────────

def compute_volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute range-based and GARCH-family volatility estimators."""
    out = df.copy()
    n = len(out)

    if n < 20:
        for col in _VOL_COLS:
            out[col] = 0.0
        return out

    h = np.log(out["High"] / out["Open"]).values
    l = np.log(out["Low"] / out["Open"]).values
    c_o = np.log(out["Close"] / out["Open"]).values
    o_c_prev = np.log(out["Open"] / out["Close"].shift(1)).fillna(0).values
    window = 20

    # Parkinson
    hl = np.log(out["High"] / out["Low"]).values
    park_var = pd.Series(hl ** 2 / (4 * np.log(2)), index=out.index)
    out["vol_parkinson"] = np.sqrt(park_var.rolling(window, min_periods=5).mean()) * np.sqrt(252) * 100

    # Garman-Klass
    gk_var = 0.5 * hl ** 2 - (2 * np.log(2) - 1) * c_o ** 2
    gk_series = pd.Series(gk_var, index=out.index)
    out["vol_garman_klass"] = np.sqrt(gk_series.rolling(window, min_periods=5).mean().clip(lower=0)) * np.sqrt(252) * 100

    # Rogers-Satchell
    rs_var = h * (h - c_o) + l * (l - c_o)
    rs_series = pd.Series(rs_var, index=out.index)
    out["vol_rogers_satchell"] = np.sqrt(rs_series.rolling(window, min_periods=5).mean().clip(lower=0)) * np.sqrt(252) * 100

    # Yang-Zhang
    o_var = pd.Series(o_c_prev ** 2, index=out.index).rolling(window, min_periods=5).mean()
    c_var = pd.Series(c_o ** 2, index=out.index).rolling(window, min_periods=5).mean()
    rs_var_roll = rs_series.rolling(window, min_periods=5).mean()
    k = 0.34 / (1.34 + (window + 1) / (window - 1))
    yz_var = o_var + k * c_var + (1 - k) * rs_var_roll
    out["vol_yang_zhang"] = np.sqrt(yz_var.clip(lower=0)) * np.sqrt(252) * 100

    # Fast GARCH proxies via ewm
    log_ret = np.log(out["Close"] / out["Close"].shift(1)).fillna(0)
    ewm_var = (log_ret ** 2).ewm(span=20, min_periods=5).mean()
    neg_ret = log_ret.clip(upper=0)
    ewm_var_neg = (neg_ret ** 2).ewm(span=20, min_periods=5).mean()
    leverage = (log_ret < 0).astype(float) * (log_ret ** 2)
    ewm_leverage = leverage.ewm(span=20, min_periods=5).mean()

    out["vol_garch11"] = np.sqrt(ewm_var) * np.sqrt(252) * 100
    out["vol_egarch"] = np.sqrt(0.6 * ewm_var + 0.4 * ewm_var_neg) * np.sqrt(252) * 100
    out["vol_gjr_garch"] = np.sqrt(0.7 * ewm_var + 0.3 * ewm_leverage) * np.sqrt(252) * 100

    # HAR-RV
    rv_daily = log_ret ** 2
    rv_5d = rv_daily.rolling(5).mean()
    rv_22d = rv_daily.rolling(22).mean()
    out["vol_har_rv"] = np.sqrt(
        0.2 * rv_daily + 0.4 * rv_5d.fillna(0) + 0.4 * rv_22d.fillna(0)
    ) * np.sqrt(252) * 100

    # Vol-of-vol (rolling std of realized vol — measures vol regime stability)
    out["vol_of_vol"] = out["vol_har_rv"].rolling(10, min_periods=3).std().fillna(0)

    # Grouped ensembles
    out["vol_lpv_ensemble"] = (
        out["vol_parkinson"].fillna(0) +
        out["vol_garman_klass"].fillna(0) +
        out["vol_rogers_satchell"].fillna(0)
    ) / 3

    out["vol_super_hybrid"] = (
        0.35 * out["vol_yang_zhang"].fillna(0) +
        0.25 * out["vol_gjr_garch"].fillna(0) +
        0.25 * out["vol_har_rv"].fillna(0) +
        0.15 * out["vol_lpv_ensemble"].fillna(0)
    )

    return out


_VOL_COLS = [
    "vol_parkinson", "vol_garman_klass", "vol_rogers_satchell",
    "vol_yang_zhang", "vol_garch11", "vol_egarch", "vol_gjr_garch",
    "vol_har_rv", "vol_of_vol", "vol_lpv_ensemble", "vol_super_hybrid",
]


# ── 5. MASTER FEATURE BUILDER ──────────────────────────────────────────────

# Final feature list — pruned to high-signal features only
# Removed: linear_fit, quad_fit, initial_velocity, rolling_mean_5/10 (price-level = leakage risk)
# Added: regime_60d, vix_level, vix_change_1d, tlt_ret_1d, obv_slope_5, rel_volume, vol_of_vol
FEATURE_COLS = [
    # Kinematics (scale-invariant)
    "linear_velocity", "r_squared", "trend_direction",
    "acceleration", "linear_residual", "quad_residual",
    # Momentum (return-based, not price-level)
    "ret_5d", "ret_10d", "ret_20d", "pct_change_1d",
    # Rolling vol stats
    "rolling_std_5", "rolling_std_10", "rolling_std_20",
    # Derived
    "z_score_20", "regime_60d",
    # Cross-asset
    "vix_level", "vix_change_1d", "tlt_ret_1d",
    # Volume-price
    "obv_slope_5", "rel_volume",
    # Volatility (grouped)
    "vol_yang_zhang", "vol_gjr_garch", "vol_har_rv",
    "vol_lpv_ensemble", "vol_super_hybrid", "vol_of_vol",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Full feature pipeline: kinematics + momentum + cross-asset + volatility."""
    out = compute_kinematic_features(df)
    out = compute_momentum_features(out)
    out = compute_cross_asset_features(out)
    out = compute_volatility_features(out)
    return out


def get_feature_matrix(df: pd.DataFrame) -> tuple:
    """Build features and return (X, y) ready for training.

    X = feature matrix (FEATURE_COLS)
    y = next-day return (%) — what the model predicts
    """
    featured = build_features(df)
    featured["target"] = featured["Close"].pct_change().shift(-1) * 100
    clean = featured.dropna(subset=FEATURE_COLS + ["target"])
    X = clean[FEATURE_COLS]
    y = clean["target"]
    return X, y


def build_forecast(df: pd.DataFrame, n_days: int = 10) -> pd.DataFrame:
    """Generate kinematic extrapolation forecasts."""
    close = df["Close"].values.astype(float)
    t = np.arange(len(close))

    slope, intercept, _, _, _ = stats.linregress(t, close)
    coeffs = np.polyfit(t, close, 2)

    t_future = np.arange(len(close), len(close) + n_days)
    linear_forecast = slope * t_future + intercept
    kinematic_forecast = np.polyval(coeffs, t_future)

    return pd.DataFrame({
        "day": range(1, n_days + 1),
        "linear_pred": linear_forecast,
        "kinematic_pred": kinematic_forecast,
        "avg_pred": (linear_forecast + kinematic_forecast) / 2,
    })


# ── 6. TREND VALIDATION ────────────────────────────────────────────────────

def validate_trends(df: pd.DataFrame) -> dict:
    """Run ADF stationarity tests on key trend features.

    Returns dict of {feature: {adf_stat, p_value, is_spurious}}.
    If p_value > 0.05, the feature is non-stationary (potential spurious trend).
    """
    results = {}
    trend_cols = ["ret_20d", "regime_60d", "z_score_20"]

    for col in trend_cols:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if len(series) < 30:
            continue
        try:
            from statsmodels.tsa.stattools import adfuller
            adf_result = adfuller(series, autolag="AIC")
            results[col] = {
                "adf_stat": round(float(adf_result[0]), 4),
                "p_value": round(float(adf_result[1]), 4),
                "is_spurious": adf_result[1] > 0.05,
            }
        except Exception:
            results[col] = {"adf_stat": 0, "p_value": 1.0, "is_spurious": True}

    return results
