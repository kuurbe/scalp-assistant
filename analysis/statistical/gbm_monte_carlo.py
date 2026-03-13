"""
Geometric Brownian Motion (GBM) Monte Carlo simulation module.

Simulates intraday price paths under GBM dynamics to estimate the
probability of hitting a target price versus a stop-loss price within
a single trading session (390 one-minute steps).
"""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_TRADING_DAYS = 252
_DEFAULT_MINUTES_PER_DAY = 390
_MIN_OBS = 20  # Minimum daily prices for parameter estimation


# ---------------------------------------------------------------------------
# Public API -- parameter estimation
# ---------------------------------------------------------------------------

def estimate_params(
    prices: pd.Series,
    trading_days: int = _DEFAULT_TRADING_DAYS,
    minutes_per_day: int = _DEFAULT_MINUTES_PER_DAY,
) -> tuple[float, float]:
    """Estimate annualised drift (mu) and volatility (sigma) from daily prices,
    then convert to per-minute scale for use with the GBM simulator.

    Parameters
    ----------
    prices : pd.Series
        Daily closing prices (oldest-first).
    trading_days : int
        Trading days per year (252 for stocks, 365 for crypto, 260 for forex).
    minutes_per_day : int
        Trading minutes per day (390 for stocks, 1440 for crypto/forex).

    Returns
    -------
    tuple[float, float]
        (mu_minute, sigma_minute) -- drift and volatility per one-minute step.

    Raises
    ------
    ValueError
        If fewer than ``_MIN_OBS`` valid prices are provided.
    """
    prices = prices.astype(float).dropna()
    if len(prices) < _MIN_OBS:
        raise ValueError(
            f"Need at least {_MIN_OBS} data points; got {len(prices)}."
        )

    log_returns = np.log(prices / prices.shift(1)).dropna()

    # Annualise daily statistics
    mu_daily = float(log_returns.mean())
    sigma_daily = float(log_returns.std())

    mu_annual = mu_daily * trading_days
    sigma_annual = sigma_daily * np.sqrt(trading_days)

    # Convert to per-minute scale
    minutes_per_year = trading_days * minutes_per_day
    mu_minute = mu_annual / minutes_per_year
    sigma_minute = sigma_annual / np.sqrt(minutes_per_year)

    return mu_minute, sigma_minute


# ---------------------------------------------------------------------------
# Public API -- simulation
# ---------------------------------------------------------------------------

def run_gbm_simulation(
    S0: float,
    mu: float,
    sigma: float,
    stop_price: float,
    target_price: float,
    n_steps: int = 390,
    n_sims: int = 1000,
) -> dict:
    """Run a Monte Carlo GBM simulation and compute outcome probabilities.

    The GBM discrete-time update is:

        S[t+1] = S[t] * exp( (mu - 0.5*sigma^2)*dt + sigma*sqrt(dt)*Z )

    where ``dt = 1/390`` (one trading minute) and ``Z ~ N(0,1)``.

    For every simulated path the function checks whether the stop price or the
    target price is hit first (whichever comes earlier in time).

    Parameters
    ----------
    S0 : float
        Starting price.
    mu : float
        Drift per minute (use ``estimate_params`` to obtain).
    sigma : float
        Volatility per minute.
    stop_price : float
        Stop-loss level.
    target_price : float
        Take-profit level.
    n_steps : int
        Number of time steps per simulation (default 390 = one trading day).
    n_sims : int
        Number of Monte Carlo paths (default 1000).

    Returns
    -------
    dict
        p_hit_target      : float  -- probability of hitting target first.
        p_hit_stop         : float  -- probability of hitting stop first.
        p_neither          : float  -- probability of neither being hit.
        expected_return_pct: float  -- mean % return across all paths.
        median_final_price : float  -- median terminal price.
    """
    _default = {
        "p_hit_target": 0.0,
        "p_hit_stop": 0.0,
        "p_neither": 1.0,
        "expected_return_pct": 0.0,
        "median_final_price": S0,
    }

    try:
        if S0 <= 0 or sigma <= 0 or n_steps < 1 or n_sims < 1:
            return _default

        dt = 1.0 / n_steps if n_steps > 0 else 1.0 / _DEFAULT_MINUTES_PER_DAY

        # Pre-compute drift and diffusion terms
        drift = (mu - 0.5 * sigma ** 2) * dt
        diffusion = sigma * np.sqrt(dt)

        # Generate all random increments at once: (n_sims, n_steps)
        Z = np.random.standard_normal((n_sims, n_steps))
        log_increments = drift + diffusion * Z

        # Build cumulative log-price paths
        log_paths = np.cumsum(log_increments, axis=1)
        # Prepend zero column for S0
        log_paths = np.hstack([np.zeros((n_sims, 1)), log_paths])
        price_paths = S0 * np.exp(log_paths)  # shape: (n_sims, n_steps+1)

        # Determine long or short bias to know direction
        going_long = target_price > stop_price

        hit_target_count = 0
        hit_stop_count = 0
        neither_count = 0
        final_prices = price_paths[:, -1]

        for i in range(n_sims):
            path = price_paths[i]

            if going_long:
                target_hits = np.where(path >= target_price)[0]
                stop_hits = np.where(path <= stop_price)[0]
            else:
                # Short trade: target below current, stop above current
                target_hits = np.where(path <= target_price)[0]
                stop_hits = np.where(path >= stop_price)[0]

            first_target = target_hits[0] if len(target_hits) > 0 else n_steps + 1
            first_stop = stop_hits[0] if len(stop_hits) > 0 else n_steps + 1

            if first_target <= first_stop and first_target <= n_steps:
                hit_target_count += 1
            elif first_stop < first_target and first_stop <= n_steps:
                hit_stop_count += 1
            else:
                neither_count += 1

        p_hit_target = hit_target_count / n_sims
        p_hit_stop = hit_stop_count / n_sims
        p_neither = neither_count / n_sims

        expected_return_pct = float(np.mean((final_prices - S0) / S0) * 100.0)
        median_final_price = float(np.median(final_prices))

        return {
            "p_hit_target": round(p_hit_target, 4),
            "p_hit_stop": round(p_hit_stop, 4),
            "p_neither": round(p_neither, 4),
            "expected_return_pct": round(expected_return_pct, 4),
            "median_final_price": round(median_final_price, 4),
        }

    except Exception:
        return _default


# ---------------------------------------------------------------------------
# Public API -- scoring
# ---------------------------------------------------------------------------

def run_daily_gbm(
    S0: float,
    mu_annual: float,
    sigma_annual: float,
    n_days: int = 14,
    n_sims: int = 1000,
    strike: float = None,
) -> dict:
    """Run multi-day GBM Monte Carlo for options probability.

    Uses daily steps (Δt = 1/365) with annualized drift and volatility.
    Returns P(ITM), confidence cones, and percentile bands.

    The GBM daily step:
        S_{t+1} = S_t * exp((μ - σ²/2)Δt + σ√Δt * Z)

    P(ITM) = (1/N) * Σ 𝟙[S_T >= K]  (for calls)

    Percentile bands at each step t:
        Band_p = Percentile_p(S_t^(1), ..., S_t^(N))
    """
    _default = {
        "p_itm": 0.0,
        "expected_price": S0,
        "median_price": S0,
        "percentiles": {},
        "cone": [],
    }

    try:
        if S0 <= 0 or sigma_annual <= 0 or n_days < 1:
            return _default

        dt = 1.0 / 365.0  # daily step

        # Per-step drift and diffusion (annualized params)
        drift = (mu_annual - 0.5 * sigma_annual**2) * dt
        diffusion = sigma_annual * np.sqrt(dt)

        # Generate all random draws: (n_sims, n_days)
        Z = np.random.standard_normal((n_sims, n_days))
        log_increments = drift + diffusion * Z

        # Build cumulative paths
        log_paths = np.cumsum(log_increments, axis=1)
        log_paths = np.hstack([np.zeros((n_sims, 1)), log_paths])
        price_paths = S0 * np.exp(log_paths)  # shape: (n_sims, n_days+1)

        final_prices = price_paths[:, -1]

        # P(ITM) — fraction finishing above strike
        if strike and strike > 0:
            p_itm = float(np.mean(final_prices >= strike))
        else:
            p_itm = 0.0

        # Percentile bands at each time step (confidence cones)
        cone = []
        for t in range(n_days + 1):
            step_prices = price_paths[:, t]
            cone.append({
                "day": t,
                "p5": round(float(np.percentile(step_prices, 5)), 2),
                "p25": round(float(np.percentile(step_prices, 25)), 2),
                "p50": round(float(np.percentile(step_prices, 50)), 2),
                "p75": round(float(np.percentile(step_prices, 75)), 2),
                "p95": round(float(np.percentile(step_prices, 95)), 2),
            })

        # Terminal distribution percentiles
        percentiles = {
            "p5": round(float(np.percentile(final_prices, 5)), 2),
            "p25": round(float(np.percentile(final_prices, 25)), 2),
            "p50": round(float(np.percentile(final_prices, 50)), 2),
            "p75": round(float(np.percentile(final_prices, 75)), 2),
            "p95": round(float(np.percentile(final_prices, 95)), 2),
        }

        return {
            "p_itm": round(p_itm, 4),
            "expected_price": round(float(np.mean(final_prices)), 2),
            "median_price": round(float(np.median(final_prices)), 2),
            "percentiles": percentiles,
            "cone": cone,
        }

    except Exception:
        return _default


def get_gbm_score(
    prices: pd.Series,
    stop_price: float,
    target_price: float,
    trading_days: int = _DEFAULT_TRADING_DAYS,
    minutes_per_day: int = _DEFAULT_MINUTES_PER_DAY,
) -> float:
    """Return a 0-100 score based on Monte Carlo target-hit probability.

    Higher ``p_hit_target`` yields a higher score.  The mapping is roughly
    linear: ``score = p_hit_target * 100``, clamped to [0, 100].

    Parameters
    ----------
    prices : pd.Series
        Daily closing prices for parameter estimation.
    stop_price : float
        Stop-loss price level.
    target_price : float
        Take-profit price level.
    trading_days : int
        Trading days per year (252 stocks, 365 crypto, 260 forex).
    minutes_per_day : int
        Trading minutes per day (390 stocks, 1440 crypto/forex).

    Returns
    -------
    float
        Score in the range 0-100.
    """
    try:
        prices = prices.astype(float).dropna()
        if len(prices) < _MIN_OBS:
            return 50.0

        mu_min, sigma_min = estimate_params(prices, trading_days, minutes_per_day)
        S0 = float(prices.iloc[-1])

        sim_result = run_gbm_simulation(
            S0=S0,
            mu=mu_min,
            sigma=sigma_min,
            stop_price=stop_price,
            target_price=target_price,
            n_steps=minutes_per_day,
            n_sims=1000,
        )

        score = sim_result["p_hit_target"] * 100.0
        return round(min(max(score, 0.0), 100.0), 2)

    except Exception:
        return 50.0
