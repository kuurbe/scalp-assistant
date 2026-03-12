"""
Prediction generation and logging.
Takes ScoredTicker objects and produces formal prediction records,
then persists them to CSV for tracking and evaluation.
"""
import os
import datetime
import pandas as pd
from config import settings


# CSV columns for the predictions log
PREDICTION_COLUMNS = [
    "prediction_id", "ticker", "direction", "confidence", "entry_price",
    "conservative_target", "aggressive_target", "stop_price", "risk_reward",
    "timeframe", "asset_class", "regime", "kinematic_phase", "timestamp",
    "horizon_hours", "eval_timestamp", "actual_price", "result",
]

PREDICTIONS_CSV = os.path.join(os.path.dirname(__file__), "..", "..", "logs", "predictions.csv")
PREDICTIONS_CSV = os.path.normpath(PREDICTIONS_CSV)


def _get_horizon_hours(horizon: str) -> float:
    """Look up the horizon duration in hours from settings."""
    try:
        return settings.PREDICTION_HORIZONS.get(horizon, {}).get("hours", 6.5)
    except Exception:
        return 6.5


def generate_prediction(scored_ticker, horizon: str = "intraday") -> dict:
    """
    Convert a ScoredTicker into a formal prediction dictionary.

    Parameters
    ----------
    scored_ticker : ScoredTicker
        A scored ticker object from analysis.scoring.composite_scorer.
    horizon : str
        One of 'intraday', 'swing_2d', 'swing_5d'.

    Returns
    -------
    dict
        Prediction record with all fields needed for logging and evaluation.
    """
    try:
        now = datetime.datetime.now()
        horizon_hours = _get_horizon_hours(horizon)

        prediction = {
            "prediction_id": f"{scored_ticker.ticker}_{now.strftime('%Y%m%d_%H%M%S')}",
            "ticker": scored_ticker.ticker,
            "direction": scored_ticker.direction,
            "confidence": scored_ticker.composite_score,
            "entry_price": scored_ticker.entry_price,
            "conservative_target": scored_ticker.target_price,
            "aggressive_target": scored_ticker.aggressive_target,
            "stop_price": scored_ticker.stop_price,
            "risk_reward": scored_ticker.risk_reward,
            "timeframe": horizon,
            "asset_class": scored_ticker.asset_class,
            "regime": scored_ticker.regime,
            "kinematic_phase": scored_ticker.kinematic_phase,
            "timestamp": now.isoformat(),
            "horizon_hours": horizon_hours,
            # Evaluation fields -- filled in later by tracker
            "eval_timestamp": "",
            "actual_price": "",
            "result": "",
        }
        return prediction

    except Exception as e:
        # Return a minimal safe prediction so callers never crash
        return {
            "prediction_id": f"ERROR_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "ticker": getattr(scored_ticker, "ticker", "UNKNOWN"),
            "direction": "LONG",
            "confidence": 0,
            "entry_price": 0,
            "conservative_target": 0,
            "aggressive_target": 0,
            "stop_price": 0,
            "risk_reward": 0,
            "timeframe": horizon,
            "asset_class": "stocks",
            "regime": "UNKNOWN",
            "kinematic_phase": "UNKNOWN",
            "timestamp": datetime.datetime.now().isoformat(),
            "horizon_hours": 6.5,
            "eval_timestamp": "",
            "actual_price": "",
            "result": "",
        }


def log_prediction(prediction: dict) -> bool:
    """
    Append a single prediction dict to the predictions CSV.

    Parameters
    ----------
    prediction : dict
        A prediction record (from generate_prediction).

    Returns
    -------
    bool
        True if logged successfully, False otherwise.
    """
    try:
        # Ensure the logs directory exists
        log_dir = os.path.dirname(PREDICTIONS_CSV)
        os.makedirs(log_dir, exist_ok=True)

        # If the file does not exist yet, create it with headers
        file_exists = os.path.isfile(PREDICTIONS_CSV)

        row = pd.DataFrame([prediction], columns=PREDICTION_COLUMNS)

        row.to_csv(
            PREDICTIONS_CSV,
            mode="a",
            header=not file_exists,
            index=False,
        )
        return True

    except Exception as e:
        print(f"[Predictor] Failed to log prediction: {e}")
        return False


def generate_and_log_predictions(scored_tickers: list, horizon: str = "intraday") -> list:
    """
    Generate predictions for a list of ScoredTicker objects and log them all.

    Parameters
    ----------
    scored_tickers : list
        List of ScoredTicker objects.
    horizon : str
        Prediction horizon key.

    Returns
    -------
    list
        List of prediction dicts that were generated (and attempted to log).
    """
    predictions = []
    for st in scored_tickers:
        try:
            pred = generate_prediction(st, horizon=horizon)
            log_prediction(pred)
            predictions.append(pred)
        except Exception as e:
            print(f"[Predictor] Error processing {getattr(st, 'ticker', '?')}: {e}")
            continue
    return predictions
