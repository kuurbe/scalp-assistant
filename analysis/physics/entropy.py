"""
Shannon entropy predictability filter.

Discretises return distributions and measures their Shannon entropy to
assess how predictable (low entropy) or chaotic (high entropy) a price
series is.  The normalised entropy score is used as a gate: only trade
when the market shows exploitable structure.
"""

import numpy as np
import pandas as pd

from config.settings import ENTROPY_MAX_CHAOS


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_entropy(returns: pd.Series, bins: int = 10) -> float:
    """Compute normalised Shannon entropy of a return distribution.

    Parameters
    ----------
    returns : pd.Series
        Log-return series (or simple returns).
    bins : int
        Number of equal-width histogram bins for discretisation.

    Returns
    -------
    float
        Normalised entropy in [0, 1].
        0 = perfectly predictable (all mass in one bin).
        1 = maximum chaos (uniform distribution across bins).
    """
    try:
        returns = returns.astype(float).dropna()
        if len(returns) < 10 or bins < 2:
            return 1.0  # Assume maximum uncertainty with insufficient data

        # Histogram counts
        counts, _ = np.histogram(returns.values, bins=bins)
        # Convert to probabilities, ignoring empty bins
        total = counts.sum()
        if total == 0:
            return 1.0

        probs = counts / total
        # Remove zero-probability bins to avoid log(0)
        probs = probs[probs > 0]

        # Shannon entropy: H = -sum(p * log2(p))
        H = -np.sum(probs * np.log2(probs))

        # Normalise by maximum possible entropy: log2(bins)
        H_max = np.log2(bins)
        if H_max == 0:
            return 1.0

        normalised = H / H_max
        return float(np.clip(normalised, 0.0, 1.0))
    except Exception:
        return 1.0


def entropy_filter(prices: pd.Series, max_entropy: float = ENTROPY_MAX_CHAOS) -> bool:
    """Determine whether a price series is tradeable based on entropy.

    The filter computes log returns internally and checks whether the
    normalised entropy falls below the chaos threshold.

    Parameters
    ----------
    prices : pd.Series
        Close prices ordered oldest-first.
    max_entropy : float
        Maximum normalised entropy allowed.  Default from config.

    Returns
    -------
    bool
        True if tradeable (entropy < max_entropy), False otherwise.
    """
    try:
        prices = prices.astype(float).dropna()
        if len(prices) < 20:
            return False  # Not enough data to assess

        log_returns = np.log(prices / prices.shift(1)).dropna()
        if len(log_returns) < 10:
            return False

        H_norm = compute_entropy(log_returns, bins=10)
        return H_norm < max_entropy
    except Exception:
        return False


def get_predictability_score(prices: pd.Series) -> float:
    """Return a 0-100 predictability score.

    Score = (1 - normalised_entropy) * 100.
    Higher values indicate more structure / less randomness.

    Parameters
    ----------
    prices : pd.Series
        Close prices ordered oldest-first.

    Returns
    -------
    float
        Score in [0, 100].
    """
    try:
        prices = prices.astype(float).dropna()
        if len(prices) < 20:
            return 0.0

        log_returns = np.log(prices / prices.shift(1)).dropna()
        if len(log_returns) < 10:
            return 0.0

        H_norm = compute_entropy(log_returns, bins=10)
        score = (1.0 - H_norm) * 100.0
        return float(np.clip(score, 0.0, 100.0))
    except Exception:
        return 0.0
