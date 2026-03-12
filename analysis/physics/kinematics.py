"""
Kinematics module -- Newton's laws applied to price movement.

Computes price velocity, acceleration, and jerk (first three finite
differences of the price series) and classifies the current market phase.
"""

import numpy as np
import pandas as pd

from config.settings import SPARK_ACCEL_THRESHOLD, KINEMATICS_SMOOTH_WINDOW


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _smooth(series: pd.Series, window: int) -> pd.Series:
    """Simple moving-average smoother that preserves index alignment."""
    if window <= 1:
        return series
    return series.rolling(window=window, min_periods=1).mean()


def _rolling_zscore(series: pd.Series, window: int = 30) -> pd.Series:
    """Z-score normalised over a rolling window."""
    roll_mean = series.rolling(window=window, min_periods=2).mean()
    roll_std = series.rolling(window=window, min_periods=2).std()
    # Avoid division by zero -- fill with 0.0 where std is zero/NaN
    roll_std = roll_std.replace(0.0, np.nan)
    return ((series - roll_mean) / roll_std).fillna(0.0)


def _classify_phase(vel: float, accel: float, jerk_z: float) -> str:
    """Determine the kinematic phase of the latest bar.

    Phases
    ------
    IGNITION  : jerk_z > 2 AND accel > 0 AND vel > 0
    CRUISE    : accel approximately zero (|accel_z| < 0.5), vel > 0
    DECEL     : accel < 0, vel > 0
    REVERSAL  : vel < 0
    """
    if vel < 0:
        return "REVERSAL"
    if jerk_z > 2.0 and accel > 0 and vel > 0:
        return "IGNITION"
    if accel < 0 and vel > 0:
        return "DECEL"
    # Default: vel >= 0 and none of the above
    return "CRUISE"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_kinematics(
    prices: pd.Series,
    smooth_window: int = KINEMATICS_SMOOTH_WINDOW,
) -> pd.DataFrame:
    """Compute price velocity, acceleration, and jerk with z-score variants.

    Parameters
    ----------
    prices : pd.Series
        Raw price series (close prices, ordered oldest-first).
    smooth_window : int
        Window length for smoothing finite differences.

    Returns
    -------
    pd.DataFrame
        Columns: velocity, acceleration, jerk,
                 velocity_z, accel_z, jerk_z, phase
    """
    try:
        prices = prices.astype(float).dropna()
        if len(prices) < 3:
            # Need at least 3 points for velocity -> acceleration
            return pd.DataFrame(
                columns=[
                    "velocity", "acceleration", "jerk",
                    "velocity_z", "accel_z", "jerk_z", "phase",
                ],
                index=prices.index,
            )

        velocity = _smooth(prices.diff(), smooth_window)
        acceleration = _smooth(velocity.diff(), smooth_window)
        jerk = _smooth(acceleration.diff(), smooth_window)

        velocity_z = _rolling_zscore(velocity)
        accel_z = _rolling_zscore(acceleration)
        jerk_z = _rolling_zscore(jerk)

        # Classify each bar's phase
        phases = []
        for i in range(len(prices)):
            v = velocity.iloc[i] if not np.isnan(velocity.iloc[i]) else 0.0
            a = acceleration.iloc[i] if not np.isnan(acceleration.iloc[i]) else 0.0
            jz = jerk_z.iloc[i] if not np.isnan(jerk_z.iloc[i]) else 0.0
            phases.append(_classify_phase(v, a, jz))

        return pd.DataFrame(
            {
                "velocity": velocity,
                "acceleration": acceleration,
                "jerk": jerk,
                "velocity_z": velocity_z,
                "accel_z": accel_z,
                "jerk_z": jerk_z,
                "phase": phases,
            },
            index=prices.index,
        )
    except Exception:
        return pd.DataFrame(
            columns=[
                "velocity", "acceleration", "jerk",
                "velocity_z", "accel_z", "jerk_z", "phase",
            ],
        )


def get_kinematic_score(prices: pd.Series) -> float:
    """Return a 0-100 score based on the latest bar's kinematic phase.

    Score bands
    -----------
    IGNITION  : 80-100
    CRUISE    : 50-70
    DECEL     : 20-40
    REVERSAL  : 0-20
    """
    try:
        df = compute_kinematics(prices)
        if df.empty:
            return 0.0

        latest = df.iloc[-1]
        phase = latest["phase"]

        # Use accel_z magnitude within each band for finer granularity
        accel_z = abs(float(latest["accel_z"])) if not np.isnan(latest["accel_z"]) else 0.0
        # Clamp accel_z contribution to [0, 1] range
        accel_frac = min(accel_z / 4.0, 1.0)

        if phase == "IGNITION":
            return 80.0 + accel_frac * 20.0
        elif phase == "CRUISE":
            return 50.0 + accel_frac * 20.0
        elif phase == "DECEL":
            return 20.0 + accel_frac * 20.0
        else:  # REVERSAL
            return 0.0 + accel_frac * 20.0
    except Exception:
        return 0.0


def is_spark(prices: pd.Series) -> bool:
    """Return True if the latest bar is in IGNITION with extreme acceleration.

    Criteria
    --------
    1. Phase == IGNITION
    2. accel_z > SPARK_ACCEL_THRESHOLD (from config)
    """
    try:
        df = compute_kinematics(prices)
        if df.empty:
            return False

        latest = df.iloc[-1]
        return (
            latest["phase"] == "IGNITION"
            and float(latest["accel_z"]) > SPARK_ACCEL_THRESHOLD
        )
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Kinetic Energy + Momentum Physics
# ---------------------------------------------------------------------------

def compute_kinetic_energy(prices: pd.Series, volumes: pd.Series = None, decay_bars: int = 20) -> dict:
    """
    Compute physics-based kinetic energy with half-life decay.
    KE = 0.5 * mass * velocity^2
    Mass = volume (or 1.0 if no volume)
    Velocity = 5-bar rate of change
    Apply exponential decay so old signals fade.
    """
    try:
        prices = prices.astype(float).dropna()
        if len(prices) < 10:
            return {"kinetic_energy": 0.0, "momentum": 0.0, "energy_score": 0.0}

        velocity = prices.pct_change(periods=5) * 100
        acceleration = velocity.diff()

        if volumes is not None and len(volumes) == len(prices):
            mass = volumes.rolling(10).mean().fillna(volumes.mean())
        else:
            mass = pd.Series(1.0, index=prices.index)

        # KE = 0.5 * m * v^2
        ke = 0.5 * mass * (velocity ** 2)

        # Exponential half-life decay
        n = len(ke)
        decay = np.exp(-np.log(2) * np.arange(n)[::-1] / decay_bars)
        ke_decayed = ke * decay

        # Momentum p = m * v
        momentum = mass * velocity

        # Normalize to 0-100 score
        ke_latest = float(ke_decayed.iloc[-1]) if not np.isnan(ke_decayed.iloc[-1]) else 0.0
        ke_mean = float(ke_decayed.mean()) if not np.isnan(ke_decayed.mean()) else 1.0

        # Score: how much current KE exceeds average (volume-boosted)
        vol_boost = 1.0
        if volumes is not None and len(volumes) > 1:
            vol_ratio = float(volumes.iloc[-1] / volumes.mean()) if volumes.mean() > 0 else 1.0
            vol_boost = min(max(vol_ratio, 0.5), 3.0)

        raw_score = (ke_latest / max(ke_mean, 1e-10)) * vol_boost * 25
        energy_score = float(np.clip(raw_score, 0, 100))

        return {
            "kinetic_energy": round(ke_latest, 4),
            "momentum": round(float(momentum.iloc[-1]) if not np.isnan(momentum.iloc[-1]) else 0.0, 4),
            "energy_score": round(energy_score, 1),
            "acceleration": round(float(acceleration.iloc[-1]) if not np.isnan(acceleration.iloc[-1]) else 0.0, 4),
        }
    except Exception:
        return {"kinetic_energy": 0.0, "momentum": 0.0, "energy_score": 0.0, "acceleration": 0.0}
