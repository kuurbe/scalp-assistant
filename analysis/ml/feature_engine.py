"""
ML Feature Engine — Saty-Framework Feature Pipeline.

Generates features per ticker from raw OHLCV data based on Saty indicator concepts:
  - ATR Levels: volatility-normalized price positioning
  - EMA Ribbon: 5-EMA trend system (8, 13, 21, 48, 200) with crossover signals
  - Phase Oscillator: ATR/EMA-based Wyckoff phase zones + compression detection
  - Volume Stack: Buy/sell volume proxy from candle structure
  - Cross-asset context: VIX, TLT (fetched once, cached)
  - Momentum/regime: returns + z-score

Includes trend validation via ADF stationarity tests.
"""

import numpy as np
import pandas as pd
from scipy import stats


# ── 1. ATR FEATURES ───────────────────────────────────────────────────────

def compute_atr_features(df: pd.DataFrame) -> pd.DataFrame:
    """ATR-based features: volatility level, price vs pivot, target distance."""
    out = df.copy()
    n = len(out)

    if n < 15:
        for col in _ATR_COLS:
            out[col] = 0.0
        return out

    high = out["High"].astype(float)
    low = out["Low"].astype(float)
    close = out["Close"].astype(float)
    prev_close = close.shift(1)

    # True Range → ATR(14) via Wilder's smoothing
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()

    out["atr_14"] = atr

    # ATR as % of price (volatility-normalized — scale-invariant)
    out["atr_pct"] = (atr / close.replace(0, np.nan)).fillna(0) * 100

    # Price vs central pivot (prior close) in ATR units
    pivot = prev_close
    out["price_vs_pivot"] = ((close - pivot) / atr.replace(0, np.nan)).fillna(0)

    # Distance to 1x ATR extension (how far from a full-ATR move)
    out["atr_target_dist"] = ((close - pivot).abs() / atr.replace(0, np.nan)).fillna(0)

    return out


_ATR_COLS = ["atr_14", "atr_pct", "price_vs_pivot", "atr_target_dist"]


# ── 2. EMA RIBBON FEATURES ───────────────────────────────────────────────

def compute_ema_ribbon(df: pd.DataFrame) -> pd.DataFrame:
    """5-EMA ribbon (8, 13, 21, 48, 200) with crossover and slope signals."""
    out = df.copy()
    close = out["Close"].astype(float)

    if len(close) < 30:
        for col in _EMA_COLS:
            out[col] = 0.0
        return out

    ema8 = close.ewm(span=8, adjust=False).mean()
    ema13 = close.ewm(span=13, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema48 = close.ewm(span=48, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()

    # Get ATR for normalization (use atr_14 if already computed, else compute)
    if "atr_14" in out.columns:
        atr = out["atr_14"]
    else:
        high = out["High"].astype(float)
        low = out["Low"].astype(float)
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low, (high - prev_close).abs(), (low - prev_close).abs()
        ], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()

    safe_atr = atr.replace(0, np.nan)

    # Ribbon spread: (EMA8 - EMA200) / ATR — overall trend strength
    out["ema_ribbon_spread"] = ((ema8 - ema200) / safe_atr).fillna(0)

    # EMA 8/13 cross: fast trend direction (+1 bull, -1 bear)
    out["ema_8_13_cross"] = np.sign(ema8 - ema13).fillna(0)

    # EMA 13/48 cross: conviction arrow proxy
    out["ema_13_48_cross"] = np.sign(ema13 - ema48).fillna(0)

    # EMA21 slope: 5-bar rate of change of EMA21 (trend speed)
    out["ema_slope_21"] = (ema21.diff(5) / safe_atr).fillna(0)

    # Price vs EMA21 in ATR units (pullback/extension)
    out["price_vs_ema21"] = ((close - ema21) / safe_atr).fillna(0)

    return out


_EMA_COLS = [
    "ema_ribbon_spread", "ema_8_13_cross", "ema_13_48_cross",
    "ema_slope_21", "price_vs_ema21",
]


# ── 3. PHASE OSCILLATOR FEATURES ─────────────────────────────────────────

def compute_phase_oscillator(df: pd.DataFrame) -> pd.DataFrame:
    """ATR/EMA-based phase oscillator with Fibonacci zones and compression.

    Based on Saty Phase Oscillator concept: (Close - EMA21) / ATR creates
    an uncapped oscillator that maps to Wyckoff-style market phases.

    Zones (Fibonacci-based):
      +100  Extreme
      +61.8 Distribution
      +23.6 Launch
        0   Zero-line (momentum shift)
      -23.6 Launch
      -61.8 Accumulation
      -100  Extreme
    """
    out = df.copy()
    close = out["Close"].astype(float)

    if len(close) < 25:
        for col in _PHASE_COLS:
            out[col] = 0.0
        return out

    ema21 = close.ewm(span=21, adjust=False).mean()

    # Get ATR
    if "atr_14" in out.columns:
        atr = out["atr_14"]
    else:
        high = out["High"].astype(float)
        low = out["Low"].astype(float)
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low, (high - prev_close).abs(), (low - prev_close).abs()
        ], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()

    safe_atr = atr.replace(0, np.nan)

    # Core oscillator: (Close - EMA21) / ATR, scaled to ~±100 range
    # Multiply by 100 to put in Saty-like range
    raw_osc = ((close - ema21) / safe_atr).fillna(0) * 100

    out["phase_osc"] = raw_osc

    # Discretized zone based on Fibonacci levels
    # -2: Extreme down (<-100), -1: Accumulation (<-61.8), 0: Neutral/Launch (±23.6)
    # +1: Distribution (>+61.8), +2: Extreme up (>+100)
    conditions = [
        raw_osc <= -100,
        raw_osc <= -61.8,
        raw_osc <= -23.6,
        raw_osc <= 23.6,
        raw_osc <= 61.8,
        raw_osc <= 100,
        raw_osc > 100,
    ]
    choices = [-2, -1, 0, 0, 0, 1, 2]
    # More granular: accumulation, neutral, distribution mapping
    zone = np.select(
        [raw_osc <= -100, raw_osc <= -61.8, raw_osc <= 23.6,
         raw_osc <= 61.8, raw_osc <= 100, raw_osc > 100],
        [-2, -1, 0, 1, 1, 2],
        default=0,
    )
    out["phase_zone"] = zone

    # Compass: 3-bar EMA of oscillator (short-term momentum direction)
    out["phase_momentum"] = raw_osc.ewm(span=3, adjust=False).mean().fillna(0)

    # Compression: Bollinger Band width of oscillator (squeeze detection)
    osc_std = raw_osc.rolling(20, min_periods=5).std().fillna(0)
    osc_mean = raw_osc.rolling(20, min_periods=5).mean().fillna(0)
    # BB width = (upper - lower) / middle; use std-based proxy
    out["phase_compression"] = osc_std

    return out


_PHASE_COLS = ["phase_osc", "phase_zone", "phase_momentum", "phase_compression"]


# ── 4. VOLUME STACK FEATURES ─────────────────────────────────────────────

def compute_volume_stack(df: pd.DataFrame) -> pd.DataFrame:
    """Buy/sell volume proxy from candle structure + relative volume.

    Buy % = (Close - Low) / (High - Low) — price closed near high = buying
    Sell % = (High - Close) / (High - Low) — price closed near low = selling
    Volume bias = buy% - sell% — net directional bias
    """
    out = df.copy()
    high = out["High"].astype(float)
    low = out["Low"].astype(float)
    close = out["Close"].astype(float)

    candle_range = (high - low).replace(0, np.nan)

    out["buy_volume_pct"] = ((close - low) / candle_range).fillna(0.5)
    out["sell_volume_pct"] = ((high - close) / candle_range).fillna(0.5)
    out["volume_bias"] = out["buy_volume_pct"] - out["sell_volume_pct"]

    # Relative volume (vs 20-day mean)
    if "Volume" in out.columns:
        vol = out["Volume"].astype(float)
        avg_vol = vol.rolling(20, min_periods=5).mean()
        out["rel_volume"] = (vol / avg_vol.replace(0, np.nan)).fillna(1.0)
    else:
        out["rel_volume"] = 1.0

    return out


_VOLUME_COLS = ["buy_volume_pct", "sell_volume_pct", "volume_bias", "rel_volume"]


# ── 5. CROSS-ASSET FEATURES ──────────────────────────────────────────────

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
        out["vix_level"] = vix_data["Close"].reindex(out.index).ffill().fillna(20.0).values
        out["vix_change_1d"] = pd.Series(out["vix_level"]).pct_change().fillna(0).values * 100
    else:
        out["vix_level"] = 20.0
        out["vix_change_1d"] = 0.0

    if tlt_data is not None and len(tlt_data) >= n:
        tlt_close = tlt_data["Close"].reindex(out.index).ffill()
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


_CROSS_COLS = ["vix_level", "vix_change_1d", "tlt_ret_1d"]


# ── 6. MOMENTUM / REGIME FEATURES ────────────────────────────────────────

def compute_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """Simplified momentum: 5d/20d returns + z-score."""
    out = df.copy()
    c = out["Close"]

    out["ret_5d"] = c.pct_change(5) * 100
    out["ret_20d"] = c.pct_change(20) * 100

    # Z-score (mean reversion signal)
    mean_20 = c.rolling(20).mean()
    std_20 = c.rolling(20).std().replace(0, np.nan)
    out["z_score_20"] = ((c - mean_20) / std_20).fillna(0)

    return out


_MOMENTUM_COLS = ["ret_5d", "ret_20d", "z_score_20"]


# ── 7. MASTER FEATURE BUILDER ────────────────────────────────────────────

# Final feature list — Saty-framework aligned
FEATURE_COLS = [
    # ATR Levels
    "atr_14", "atr_pct", "price_vs_pivot", "atr_target_dist",
    # EMA Ribbon (8, 13, 21, 48, 200)
    "ema_ribbon_spread", "ema_8_13_cross", "ema_13_48_cross",
    "ema_slope_21", "price_vs_ema21",
    # Phase Oscillator (Wyckoff zones)
    "phase_osc", "phase_zone", "phase_momentum", "phase_compression",
    # Volume Stack
    "buy_volume_pct", "sell_volume_pct", "volume_bias", "rel_volume",
    # Cross-asset context
    "vix_level", "vix_change_1d", "tlt_ret_1d",
    # Momentum / regime
    "ret_5d", "ret_20d", "z_score_20",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Full Saty-framework feature pipeline."""
    out = compute_atr_features(df)
    out = compute_ema_ribbon(out)
    out = compute_phase_oscillator(out)
    out = compute_volume_stack(out)
    out = compute_cross_asset_features(out)
    out = compute_momentum_features(out)
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
    """Generate kinematic extrapolation forecasts (linear + quadratic)."""
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


# ── 8. TREND VALIDATION ──────────────────────────────────────────────────

def validate_trends(df: pd.DataFrame) -> dict:
    """Run ADF stationarity tests on key features.

    Returns dict of {feature: {adf_stat, p_value, is_spurious}}.
    If p_value > 0.05, the feature is non-stationary (potential spurious trend).
    """
    results = {}
    trend_cols = ["ret_20d", "z_score_20", "phase_osc"]

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
