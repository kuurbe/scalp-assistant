"""
GARCH(1,1) volatility forecasting module.

Uses the ``arch`` library to fit a GARCH(1,1) model on log-return data,
forecast conditional volatility over a given horizon, and classify the
current volatility regime.
"""

import numpy as np
import pandas as pd

from arch import arch_model


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_OBS = 30            # Minimum data points required for model fitting
_TRADING_DAYS = 252      # Used for annualisation of daily volatility
_LOW_VOL_CEILING = 20.0  # Annualised % boundary: below = LOW_VOL
_HIGH_VOL_FLOOR = 40.0   # Annualised % boundary: above = HIGH_VOL

_DEFAULT_RESULT = {
    "current_vol": 30.0,
    "forecast_vol": [],
    "alpha": 0.0,
    "beta": 0.0,
    "persistence": 0.0,
    "vol_regime": "NORMAL",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _classify_regime(annualised_vol: float) -> str:
    """Map an annualised volatility reading to a regime label."""
    if annualised_vol < _LOW_VOL_CEILING:
        return "LOW_VOL"
    elif annualised_vol > _HIGH_VOL_FLOOR:
        return "HIGH_VOL"
    return "NORMAL"


def _annualise_daily_vol(daily_vol: float) -> float:
    """Convert a daily standard deviation (in %) to annualised terms."""
    return daily_vol * np.sqrt(_TRADING_DAYS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fit_garch(prices: pd.Series, horizon: int = 5) -> dict:
    """Fit a GARCH(1,1) model and produce volatility forecasts.

    Parameters
    ----------
    prices : pd.Series
        Price series (close prices, oldest-first).  Must contain at least
        ``_MIN_OBS`` non-NaN values.
    horizon : int
        Number of forward periods (days) to forecast volatility.

    Returns
    -------
    dict
        current_vol     : float  -- latest annualised conditional volatility (%).
        forecast_vol    : list[float] -- annualised vol forecasts for each
                          horizon step (%).
        alpha           : float  -- fitted ARCH (alpha[1]) parameter.
        beta            : float  -- fitted GARCH (beta[1]) parameter.
        persistence     : float  -- alpha + beta.
        vol_regime      : str    -- "LOW_VOL", "NORMAL", or "HIGH_VOL".
    """
    try:
        prices = prices.astype(float).dropna()
        if len(prices) < _MIN_OBS:
            return {**_DEFAULT_RESULT, "forecast_vol": [30.0] * horizon}

        # Log returns scaled to percent
        log_returns = np.log(prices / prices.shift(1)).dropna() * 100.0
        if len(log_returns) < _MIN_OBS:
            return {**_DEFAULT_RESULT, "forecast_vol": [30.0] * horizon}

        # Fit GARCH(1,1) with a constant mean
        model = arch_model(
            log_returns,
            vol="GARCH",
            p=1,
            q=1,
            mean="Constant",
            rescale=False,
        )
        result = model.fit(disp="off", show_warning=False)

        # Extract parameters
        alpha = float(result.params.get("alpha[1]", 0.0))
        beta = float(result.params.get("beta[1]", 0.0))
        persistence = alpha + beta

        # Current conditional volatility (last observation, daily %)
        cond_vol_daily = float(np.sqrt(result.conditional_volatility.iloc[-1] ** 2))
        current_vol = _annualise_daily_vol(cond_vol_daily)

        # Forecast
        forecast = result.forecast(horizon=horizon, reindex=False)
        # forecast.variance contains h-step-ahead variance forecasts
        variance_forecasts = forecast.variance.iloc[-1].values
        forecast_vol = [
            _annualise_daily_vol(np.sqrt(float(v))) for v in variance_forecasts
        ]

        vol_regime = _classify_regime(current_vol)

        return {
            "current_vol": round(current_vol, 4),
            "forecast_vol": [round(v, 4) for v in forecast_vol],
            "alpha": round(alpha, 6),
            "beta": round(beta, 6),
            "persistence": round(persistence, 6),
            "vol_regime": vol_regime,
        }

    except Exception:
        return {**_DEFAULT_RESULT, "forecast_vol": [30.0] * horizon}


def get_garch_score(prices: pd.Series) -> float:
    """Return a 0-100 score reflecting breakout potential based on vol regime.

    Methodology
    -----------
    Volatility expanding from a compressed state signals a potential breakout.
    We compare the current conditional vol to a rolling 30-day percentile of
    historical realised vol.  A high percentile reading coming out of a low-vol
    regime yields the highest score.

    Score mapping (approximate):
        - Very compressed vol now starting to expand  ->  80-100
        - Moderate vol expansion                      ->  50-79
        - Flat / no expansion                         ->  20-49
        - Vol contracting                             ->  0-19
    """
    try:
        prices = prices.astype(float).dropna()
        if len(prices) < _MIN_OBS:
            return 50.0

        garch_result = fit_garch(prices, horizon=1)
        current_vol = garch_result["current_vol"]

        # Compute 30-day rolling realised vol (annualised) for percentile
        log_returns = np.log(prices / prices.shift(1)).dropna()
        rolling_vol = log_returns.rolling(window=30, min_periods=10).std() * np.sqrt(_TRADING_DAYS) * 100.0
        rolling_vol = rolling_vol.dropna()

        if len(rolling_vol) < 5:
            return 50.0

        # Percentile rank of current conditional vol versus the rolling series
        percentile = float((rolling_vol < current_vol).sum()) / len(rolling_vol) * 100.0

        # Detect expansion: current vol > recent average vol
        recent_avg_vol = float(rolling_vol.iloc[-30:].mean()) if len(rolling_vol) >= 30 else float(rolling_vol.mean())
        expansion_ratio = current_vol / max(recent_avg_vol, 1e-8)

        # Score logic:
        # - High percentile (vol high relative to history) AND expanding -> high score
        # - Low percentile (compressed) -> moderate baseline, waiting for expansion
        if expansion_ratio > 1.2 and percentile > 60:
            # Vol is expanding out of a relatively elevated state
            base = 70.0
            bonus = min((expansion_ratio - 1.0) * 50.0, 30.0)
            score = base + bonus
        elif expansion_ratio > 1.05:
            # Mild expansion
            score = 40.0 + percentile * 0.4
        elif expansion_ratio < 0.85:
            # Vol contracting
            score = max(0.0, 20.0 * expansion_ratio)
        else:
            # Flat vol
            score = 20.0 + percentile * 0.3

        return round(min(max(score, 0.0), 100.0), 2)

    except Exception:
        return 50.0
