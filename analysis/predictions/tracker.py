"""
Prediction tracker: auto-evaluation and accuracy reporting.
Reads the predictions CSV, evaluates stale predictions against actual prices,
and computes accuracy metrics across multiple dimensions.
"""
import os
import datetime
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

from analysis.predictions.predictor import PREDICTIONS_CSV, PREDICTION_COLUMNS


def _load_predictions() -> pd.DataFrame:
    """Load the predictions CSV into a DataFrame. Returns empty DF on failure."""
    try:
        if not os.path.isfile(PREDICTIONS_CSV):
            return pd.DataFrame(columns=PREDICTION_COLUMNS)
        df = pd.read_csv(PREDICTIONS_CSV)
        return df
    except Exception as e:
        print(f"[Tracker] Failed to load predictions: {e}")
        return pd.DataFrame(columns=PREDICTION_COLUMNS)


def _save_predictions(df: pd.DataFrame) -> bool:
    """Overwrite the predictions CSV with the updated DataFrame."""
    try:
        log_dir = os.path.dirname(PREDICTIONS_CSV)
        os.makedirs(log_dir, exist_ok=True)
        df.to_csv(PREDICTIONS_CSV, index=False)
        return True
    except Exception as e:
        print(f"[Tracker] Failed to save predictions: {e}")
        return False


def _fetch_current_price(ticker: str) -> float:
    """Fetch the latest price for a ticker via yfinance. Returns 0.0 on failure."""
    if yf is None:
        print("[Tracker] yfinance not installed, cannot fetch prices.")
        return 0.0
    try:
        data = yf.Ticker(ticker).history(period="1d", interval="1m")
        if data is not None and not data.empty:
            return float(data["Close"].iloc[-1])
        # Fallback: try daily data
        data = yf.Ticker(ticker).history(period="5d")
        if data is not None and not data.empty:
            return float(data["Close"].iloc[-1])
        return 0.0
    except Exception as e:
        print(f"[Tracker] Price fetch failed for {ticker}: {e}")
        return 0.0


def auto_evaluate_picks(horizon_hours: float = 6.5) -> dict:
    """
    Evaluate predictions whose horizon window has elapsed.

    Reads predictions.csv, finds rows where:
      - result is empty (unevaluated)
      - timestamp + horizon_hours <= now
    For each, fetches the current price and determines if the directional
    call was correct.

    Parameters
    ----------
    horizon_hours : float
        Number of hours after prediction to wait before evaluating.
        Defaults to 6.5 (one trading day for intraday).

    Returns
    -------
    dict
        Summary with keys: evaluated (int), wins (int), losses (int), errors (int).
    """
    summary = {"evaluated": 0, "wins": 0, "losses": 0, "errors": 0}

    try:
        df = _load_predictions()
        if df.empty:
            return summary

        now = datetime.datetime.now()
        updated = False

        for idx, row in df.iterrows():
            # Skip already-evaluated rows
            if pd.notna(row.get("result")) and str(row.get("result")).strip() != "":
                continue

            # Parse prediction timestamp
            try:
                pred_time = datetime.datetime.fromisoformat(str(row["timestamp"]))
            except (ValueError, TypeError):
                continue

            # Use per-row horizon if available, otherwise use the function arg
            row_horizon = row.get("horizon_hours")
            try:
                effective_horizon = float(row_horizon) if pd.notna(row_horizon) else horizon_hours
            except (ValueError, TypeError):
                effective_horizon = horizon_hours

            # Only evaluate if enough time has passed
            if now < pred_time + datetime.timedelta(hours=effective_horizon):
                continue

            # Fetch actual price
            ticker = str(row.get("ticker", ""))
            if not ticker:
                continue

            actual_price = _fetch_current_price(ticker)
            if actual_price <= 0:
                summary["errors"] += 1
                continue

            # Determine win/loss
            try:
                entry_price = float(row["entry_price"])
                direction = str(row["direction"]).upper()
            except (ValueError, TypeError, KeyError):
                summary["errors"] += 1
                continue

            if entry_price <= 0:
                summary["errors"] += 1
                continue

            if direction == "LONG":
                is_win = actual_price > entry_price
            elif direction == "SHORT":
                is_win = actual_price < entry_price
            else:
                summary["errors"] += 1
                continue

            result = "WIN" if is_win else "LOSS"

            # Update the row
            df.at[idx, "eval_timestamp"] = now.isoformat()
            df.at[idx, "actual_price"] = actual_price
            df.at[idx, "result"] = result
            updated = True

            summary["evaluated"] += 1
            if is_win:
                summary["wins"] += 1
            else:
                summary["losses"] += 1

        if updated:
            _save_predictions(df)

        return summary

    except Exception as e:
        print(f"[Tracker] auto_evaluate_picks error: {e}")
        return summary


def compute_prediction_accuracy() -> dict:
    """
    Compute accuracy metrics across multiple dimensions.

    Returns
    -------
    dict
        {
            overall_win_rate: float (0-100),
            wins: int,
            losses: int,
            total: int,
            accuracy_by_score_range: {range_label: win_rate},
            accuracy_by_regime: {regime: win_rate},
            accuracy_by_asset_class: {asset_class: win_rate},
            rolling_30d_accuracy: [{date: str, win_rate: float}],
        }
    """
    default = {
        "overall_win_rate": 0.0,
        "wins": 0,
        "losses": 0,
        "total": 0,
        "accuracy_by_score_range": {},
        "accuracy_by_regime": {},
        "accuracy_by_asset_class": {},
        "rolling_30d_accuracy": [],
    }

    try:
        df = _load_predictions()
        if df.empty:
            return default

        # Filter to evaluated rows only
        evaluated = df[df["result"].isin(["WIN", "LOSS"])].copy()
        if evaluated.empty:
            return default

        total = len(evaluated)
        wins = int((evaluated["result"] == "WIN").sum())
        losses = total - wins
        overall = round((wins / total) * 100, 1) if total > 0 else 0.0

        # --- Accuracy by confidence score range ---
        score_ranges = [
            ("40-55", 40, 55),
            ("55-65", 55, 65),
            ("65-75", 65, 75),
            ("75-85", 75, 85),
            ("85-100", 85, 100),
        ]
        accuracy_by_score = {}
        for label, lo, hi in score_ranges:
            try:
                mask = (evaluated["confidence"].astype(float) >= lo) & (evaluated["confidence"].astype(float) < hi)
                subset = evaluated[mask]
                if len(subset) > 0:
                    wr = round((subset["result"] == "WIN").sum() / len(subset) * 100, 1)
                    accuracy_by_score[label] = wr
            except Exception:
                continue

        # --- Accuracy by regime ---
        accuracy_by_regime = {}
        try:
            for regime, group in evaluated.groupby("regime"):
                if len(group) > 0:
                    wr = round((group["result"] == "WIN").sum() / len(group) * 100, 1)
                    accuracy_by_regime[str(regime)] = wr
        except Exception:
            pass

        # --- Accuracy by asset class ---
        accuracy_by_asset_class = {}
        try:
            for ac, group in evaluated.groupby("asset_class"):
                if len(group) > 0:
                    wr = round((group["result"] == "WIN").sum() / len(group) * 100, 1)
                    accuracy_by_asset_class[str(ac)] = wr
        except Exception:
            pass

        # --- Rolling 30-day accuracy ---
        rolling_30d = []
        try:
            evaluated["_date"] = pd.to_datetime(evaluated["timestamp"]).dt.date
            date_groups = evaluated.sort_values("_date").groupby("_date")

            # Build daily win counts, then compute 30-day rolling
            daily_wins = []
            daily_totals = []
            dates = []
            for d, grp in date_groups:
                dates.append(d)
                daily_wins.append(int((grp["result"] == "WIN").sum()))
                daily_totals.append(len(grp))

            if dates:
                daily_df = pd.DataFrame({
                    "date": dates,
                    "wins": daily_wins,
                    "total": daily_totals,
                })
                daily_df = daily_df.sort_values("date").reset_index(drop=True)
                daily_df["cum_wins"] = daily_df["wins"].rolling(window=30, min_periods=1).sum()
                daily_df["cum_total"] = daily_df["total"].rolling(window=30, min_periods=1).sum()
                daily_df["win_rate"] = (daily_df["cum_wins"] / daily_df["cum_total"] * 100).round(1)

                rolling_30d = [
                    {"date": str(row["date"]), "win_rate": float(row["win_rate"])}
                    for _, row in daily_df.iterrows()
                ]
        except Exception:
            pass

        return {
            "overall_win_rate": overall,
            "wins": wins,
            "losses": losses,
            "total": total,
            "accuracy_by_score_range": accuracy_by_score,
            "accuracy_by_regime": accuracy_by_regime,
            "accuracy_by_asset_class": accuracy_by_asset_class,
            "rolling_30d_accuracy": rolling_30d,
        }

    except Exception as e:
        print(f"[Tracker] compute_prediction_accuracy error: {e}")
        return default


def get_prediction_summary() -> str:
    """
    Return a human-readable summary of prediction performance.

    Returns
    -------
    str
        Multi-line summary string.
    """
    try:
        stats = compute_prediction_accuracy()

        if stats["total"] == 0:
            return "No evaluated predictions yet. Predictions are evaluated after their horizon window elapses."

        lines = []
        lines.append("=== Prediction Accuracy Report ===")
        lines.append(f"Overall: {stats['overall_win_rate']}% win rate  ({stats['wins']}W / {stats['losses']}L, {stats['total']} total)")
        lines.append("")

        # By score range
        if stats["accuracy_by_score_range"]:
            lines.append("By Confidence Score:")
            for rng, wr in stats["accuracy_by_score_range"].items():
                lines.append(f"  {rng}: {wr}%")
            lines.append("")

        # By regime
        if stats["accuracy_by_regime"]:
            lines.append("By Market Regime:")
            for regime, wr in stats["accuracy_by_regime"].items():
                lines.append(f"  {regime}: {wr}%")
            lines.append("")

        # By asset class
        if stats["accuracy_by_asset_class"]:
            lines.append("By Asset Class:")
            for ac, wr in stats["accuracy_by_asset_class"].items():
                lines.append(f"  {ac}: {wr}%")
            lines.append("")

        # Rolling 30d (show last 5 data points)
        if stats["rolling_30d_accuracy"]:
            recent = stats["rolling_30d_accuracy"][-5:]
            lines.append("Rolling 30-Day Accuracy (recent):")
            for entry in recent:
                lines.append(f"  {entry['date']}: {entry['win_rate']}%")

        return "\n".join(lines)

    except Exception as e:
        return f"Error generating prediction summary: {e}"
