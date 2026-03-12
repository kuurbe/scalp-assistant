"""
ML Feature Engine — Kinematics + Volatility + Momentum feature pipeline.

Generates 25 features per ticker from raw OHLCV data:
  - Linear regression (velocity, r², trend direction)
  - Kinematic quadratic (acceleration, initial velocity, residuals)
  - Momentum (3/5/10-day rate of change, daily % change)
  - Rolling stats (5/10 day mean, std)
  - Derived force (mean deviation, z-score)
  - Volatility (Parkinson, Garman-Klass, Rogers-Satchell, Yang-Zhang, GARCH ensemble, HAR-RV, super hybrid)
"""

import numpy as np
import pandas as pd
from scipy import stats


# ── 1. KINEMATICS FEATURES ─────────────────────────────────────────────────

def compute_kinematic_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute linear regression + quadratic fit features from close prices.

    Parameters
    ----------
    df : pd.DataFrame
        Must have 'Close' column. At least 20 rows recommended.

    Returns
    -------
    pd.DataFrame with kinematic feature columns added.
    """
    out = df.copy()
    close = out["Close"].values.astype(float)
    t = np.arange(len(close))

    if len(close) < 10:
        for col in _KINEMATIC_COLS:
            out[col] = 0.0
        return out

    # Linear regression
    slope, intercept, r_value, p_value, std_err = stats.linregress(t, close)
    out["linear_velocity"] = slope
    out["linear_fit"] = slope * t + intercept
    out["linear_residual"] = close - out["linear_fit"].values
    out["r_squared"] = r_value ** 2
    out["trend_direction"] = np.sign(slope)

    # Quadratic (kinematic) fit
    coeffs = np.polyfit(t, close, 2)
    a_phys = 2 * coeffs[0]
    out["acceleration"] = a_phys
    out["initial_velocity"] = coeffs[1]
    out["quad_fit"] = np.polyval(coeffs, t)
    out["quad_residual"] = close - out["quad_fit"].values

    return out


_KINEMATIC_COLS = [
    "linear_velocity", "linear_fit", "linear_residual", "r_squared",
    "trend_direction", "acceleration", "initial_velocity", "quad_fit",
    "quad_residual",
]


# ── 2. MOMENTUM FEATURES ───────────────────────────────────────────────────

def compute_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute rate of change and rolling stats."""
    out = df.copy()
    c = out["Close"]

    out["momentum_3d"] = c.diff(3)
    out["momentum_5d"] = c.diff(5)
    out["momentum_10d"] = c.diff(10)
    out["pct_change_1d"] = c.pct_change(1) * 100

    out["rolling_mean_5"] = c.rolling(5).mean()
    out["rolling_mean_10"] = c.rolling(10).mean()
    out["rolling_std_5"] = c.rolling(5).std()
    out["rolling_std_10"] = c.rolling(10).std()

    out["price_vs_mean5"] = c - out["rolling_mean_5"]
    out["price_vs_mean10"] = c - out["rolling_mean_10"]
    out["z_score_10"] = out["price_vs_mean10"] / out["rolling_std_10"].replace(0, np.nan)
    out["z_score_10"] = out["z_score_10"].fillna(0)

    return out


# ── 3. VOLATILITY FEATURES ─────────────────────────────────────────────────

def compute_volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute range-based and GARCH-family volatility estimators.

    Uses Parkinson, Garman-Klass, Rogers-Satchell, Yang-Zhang,
    then groups into LPV ensemble + GARCH ensemble + super hybrid.
    """
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

    # GARCH-family volatility — use fast realized-vol proxy to avoid slow arch fits
    log_ret_garch = np.log(out["Close"] / out["Close"].shift(1)).fillna(0)
    rv_base = log_ret_garch.rolling(20, min_periods=5).std() * np.sqrt(252) * 100

    # Fast GARCH proxy: ewm variance captures volatility clustering without arch library
    ewm_var = (log_ret_garch ** 2).ewm(span=20, min_periods=5).mean()
    out["vol_garch11"] = np.sqrt(ewm_var) * np.sqrt(252) * 100

    # EGARCH proxy: asymmetric — downside moves get more weight
    neg_ret = log_ret_garch.clip(upper=0)
    ewm_var_neg = (neg_ret ** 2).ewm(span=20, min_periods=5).mean()
    out["vol_egarch"] = np.sqrt(0.6 * ewm_var + 0.4 * ewm_var_neg) * np.sqrt(252) * 100

    # GJR-GARCH proxy: leverage effect
    leverage = (log_ret_garch < 0).astype(float) * (log_ret_garch ** 2)
    ewm_leverage = leverage.ewm(span=20, min_periods=5).mean()
    out["vol_gjr_garch"] = np.sqrt(0.7 * ewm_var + 0.3 * ewm_leverage) * np.sqrt(252) * 100

    # HAR-RV (Heterogeneous Autoregressive Realized Volatility)
    log_ret = np.log(out["Close"] / out["Close"].shift(1)).fillna(0)
    rv_daily = log_ret ** 2
    rv_5d = rv_daily.rolling(5).mean()
    rv_22d = rv_daily.rolling(22).mean()
    out["vol_har_rv"] = np.sqrt(
        0.2 * rv_daily + 0.4 * rv_5d.fillna(0) + 0.4 * rv_22d.fillna(0)
    ) * np.sqrt(252) * 100

    # ── GROUPED ENSEMBLES ──

    # LPV Range Ensemble = average(Parkinson, GK, RS)
    out["vol_lpv_ensemble"] = (
        out["vol_parkinson"].fillna(0) +
        out["vol_garman_klass"].fillna(0) +
        out["vol_rogers_satchell"].fillna(0)
    ) / 3

    # GARCH Family Ensemble
    out["vol_garch_ensemble"] = (
        out["vol_garch11"].fillna(0) +
        out["vol_egarch"].fillna(0) +
        out["vol_gjr_garch"].fillna(0)
    ) / 3

    # Super Hybrid = weighted blend
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
    "vol_har_rv", "vol_lpv_ensemble", "vol_garch_ensemble", "vol_super_hybrid",
]


# ── 4. MASTER FEATURE BUILDER ──────────────────────────────────────────────

# Final feature list for ML model
FEATURE_COLS = [
    # Kinematics
    "linear_velocity", "r_squared", "trend_direction",
    "acceleration", "initial_velocity", "linear_residual", "quad_residual",
    # Momentum
    "momentum_3d", "momentum_5d", "momentum_10d", "pct_change_1d",
    # Rolling stats
    "rolling_mean_5", "rolling_mean_10", "rolling_std_5", "rolling_std_10",
    # Derived force
    "price_vs_mean5", "price_vs_mean10", "z_score_10",
    # Volatility (grouped — 5 clean features)
    "vol_yang_zhang", "vol_gjr_garch", "vol_har_rv",
    "vol_lpv_ensemble", "vol_super_hybrid",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Full feature pipeline: kinematics + momentum + volatility.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV data with columns: Open, High, Low, Close, Volume.
        At least 30 rows recommended.

    Returns
    -------
    pd.DataFrame with all feature columns, NaN rows dropped.
    """
    out = compute_kinematic_features(df)
    out = compute_momentum_features(out)
    out = compute_volatility_features(out)
    return out


def get_feature_matrix(df: pd.DataFrame) -> tuple:
    """Build features and return (X, y) ready for training.

    X = feature matrix (FEATURE_COLS)
    y = next-day return (%) — what the model predicts

    Parameters
    ----------
    df : pd.DataFrame with OHLCV columns.

    Returns
    -------
    (X: pd.DataFrame, y: pd.Series) with aligned indices, NaN dropped.
    """
    featured = build_features(df)

    # Target: next-day % return
    featured["target"] = featured["Close"].pct_change().shift(-1) * 100

    clean = featured.dropna(subset=FEATURE_COLS + ["target"])
    X = clean[FEATURE_COLS]
    y = clean["target"]

    return X, y


def build_forecast(df: pd.DataFrame, n_days: int = 10) -> pd.DataFrame:
    """Generate kinematic extrapolation forecasts.

    Uses both linear and quadratic fits to project price forward.

    Parameters
    ----------
    df : pd.DataFrame with 'Close' column.
    n_days : int, number of days to forecast.

    Returns
    -------
    pd.DataFrame with columns: day, linear_pred, kinematic_pred, avg_pred
    """
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
