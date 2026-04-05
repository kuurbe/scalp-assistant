"""
CSV-based performance logging and win rate tracking.
"""
from __future__ import annotations
import os
import datetime
import logging

import pandas as pd

logger = logging.getLogger(__name__)

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
HISTORY_FILE = os.path.join(LOGS_DIR, "scan_history.csv")
PICKS_FILE = os.path.join(LOGS_DIR, "scalp_picks_today.csv")


def log_picks(scored_tickers: list, max_rows: int = 20):
    """Save today's picks to CSV and append to history."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    today = str(datetime.date.today())

    rows = []
    for i, pick in enumerate(scored_tickers[:max_rows]):
        rows.append({
            "date": today,
            "rank": i + 1,
            "ticker": pick.ticker,
            "price": pick.price,
            "pct_change": pick.pct_change,
            "rel_volume": pick.rel_volume,
            "rsi": pick.rsi,
            "composite_score": pick.composite_score,
            "physics_score": pick.physics_score,
            "technical_score": pick.technical_score,
            "catalyst_score": pick.catalyst_score,
            "statistical_score": pick.statistical_score,
            "regime": pick.regime,
            "kinematic_phase": pick.kinematic_phase,
            "direction": pick.direction,
            "entry_price": pick.entry_price,
            "stop_price": pick.stop_price,
            "target_price": pick.target_price,
            "risk_reward": pick.risk_reward,
            "option_direction": pick.option_direction,
            "option_safe_strike": pick.option_safe_strike,
            "option_exp_long": pick.option_exp_long,
            "catalyst_summary": pick.catalyst_summary,
            "why_moving": pick.why_moving,
            "confidence_tier": pick.confidence_tier,
            "outcome": "",  # filled manually later
            "pnl_pct": "",
        })

    df_today = pd.DataFrame(rows)

    # Save today's picks
    df_today.to_csv(PICKS_FILE, index=False)

    # Append to history (deduplicate by date+ticker)
    if os.path.exists(HISTORY_FILE):
        try:
            df_old = pd.read_csv(HISTORY_FILE)
            df_combined = pd.concat([df_old, df_today]).drop_duplicates(
                subset=["date", "ticker"], keep="last"
            ).reset_index(drop=True)
        except Exception:
            df_combined = df_today
    else:
        df_combined = df_today

    df_combined.to_csv(HISTORY_FILE, index=False)
    return PICKS_FILE, HISTORY_FILE


def calculate_win_rate() -> dict:
    """
    Calculate historical win rate from filled outcomes.
    Returns: {total, wins, losses, win_rate, avg_score_winners, avg_score_losers}
    """
    if not os.path.exists(HISTORY_FILE):
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0}

    try:
        df = pd.read_csv(HISTORY_FILE)
        filled = df[df["outcome"].isin(["WIN", "LOSS"])]
        if len(filled) == 0:
            return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0}

        wins = len(filled[filled["outcome"] == "WIN"])
        losses = len(filled[filled["outcome"] == "LOSS"])
        total = wins + losses

        avg_w = filled[filled["outcome"] == "WIN"]["composite_score"].mean() if wins > 0 else 0
        avg_l = filled[filled["outcome"] == "LOSS"]["composite_score"].mean() if losses > 0 else 0

        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            "avg_score_winners": round(avg_w, 1),
            "avg_score_losers": round(avg_l, 1),
        }
    except Exception:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0}


# ─────────────────────────────────────────────────────────────
#  AUTO-EVALUATION
# ─────────────────────────────────────────────────────────────

def auto_evaluate_picks(horizon_hours: float = 6.5) -> dict:
    """
    Read scan_history.csv, find un-evaluated rows whose entry time
    is older than `horizon_hours`, fetch the actual price via yfinance,
    and mark direction_correct = WIN / LOSS.

    Args:
        horizon_hours: How many hours after entry to check the outcome.
                       Defaults to 6.5 (one full trading day).

    Returns:
        Dict with: evaluated (int), wins (int), losses (int), errors (int).
    """
    if not os.path.exists(HISTORY_FILE):
        return {"evaluated": 0, "wins": 0, "losses": 0, "errors": 0}

    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed — cannot auto-evaluate picks")
        return {"evaluated": 0, "wins": 0, "losses": 0, "errors": 0}

    try:
        df = pd.read_csv(HISTORY_FILE)
    except Exception as e:
        logger.error("Failed to read history file: %s", e)
        return {"evaluated": 0, "wins": 0, "losses": 0, "errors": 0}

    # Identify un-evaluated rows (outcome is empty or NaN)
    mask_unevaluated = df["outcome"].isna() | (df["outcome"] == "")

    # Only evaluate rows old enough (date + horizon has passed)
    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(hours=horizon_hours)

    stats = {"evaluated": 0, "wins": 0, "losses": 0, "errors": 0}

    for idx in df[mask_unevaluated].index:
        try:
            row_date = pd.to_datetime(df.at[idx, "date"])
            # Assume entry was at market open (9:30 ET) on that date
            entry_time = row_date.replace(hour=9, minute=30)
            if entry_time > cutoff:
                continue  # Not old enough to evaluate yet

            ticker = df.at[idx, "ticker"]
            entry_price = float(df.at[idx, "entry_price"])
            direction = str(df.at[idx, "direction"]).upper()

            if not ticker or pd.isna(entry_price) or not direction:
                continue

            # Fetch current / recent price
            try:
                ticker_data = yf.Ticker(ticker)
                hist = ticker_data.history(period="5d", interval="1h")
                if hist.empty:
                    stats["errors"] += 1
                    continue
                current_price = float(hist["Close"].iloc[-1])
            except Exception:
                stats["errors"] += 1
                continue

            # Determine if direction was correct
            price_change = current_price - entry_price
            if direction in ("LONG", "BULLISH", "CALL", "UP"):
                is_correct = price_change > 0
            elif direction in ("SHORT", "BEARISH", "PUT", "DOWN"):
                is_correct = price_change < 0
            else:
                stats["errors"] += 1
                continue

            outcome = "WIN" if is_correct else "LOSS"
            pnl_pct = round((price_change / entry_price) * 100, 2)
            if direction in ("SHORT", "BEARISH", "PUT", "DOWN"):
                pnl_pct = -pnl_pct  # Flip for short positions

            df.at[idx, "outcome"] = outcome
            df.at[idx, "pnl_pct"] = pnl_pct

            stats["evaluated"] += 1
            if is_correct:
                stats["wins"] += 1
            else:
                stats["losses"] += 1

        except Exception as e:
            logger.debug("Error evaluating row %d: %s", idx, e)
            stats["errors"] += 1

    # Persist updated results
    if stats["evaluated"] > 0:
        try:
            df.to_csv(HISTORY_FILE, index=False)
            logger.info(
                "Auto-evaluated %d picks: %d wins, %d losses",
                stats["evaluated"], stats["wins"], stats["losses"],
            )
        except Exception as e:
            logger.error("Failed to save evaluated results: %s", e)

    return stats


# ─────────────────────────────────────────────────────────────
#  PREDICTION ACCURACY BREAKDOWN
# ─────────────────────────────────────────────────────────────

def compute_prediction_accuracy() -> dict:
    """
    Compute detailed prediction accuracy from evaluated history.

    Returns:
        Dict with:
            overall_win_rate (float): Percentage 0-100
            total_evaluated (int): Total picks with WIN/LOSS outcome
            current_streak (int): Current consecutive correct predictions
            max_streak (int): Best ever consecutive correct predictions
            by_score_range (dict): Win rate bucketed by composite_score ranges
            by_regime (dict): Win rate grouped by market regime
            by_asset_class (dict): Win rate grouped by inferred asset class
            had_perfect_day (bool): Whether any day had 100% accuracy
            max_rr_achieved (float): Best risk-reward ratio achieved
            profitable_asset_classes (list[str]): Asset classes with >50% win rate
    """
    from config import settings

    default = {
        "overall_win_rate": 0.0,
        "total_evaluated": 0,
        "current_streak": 0,
        "max_streak": 0,
        "by_score_range": {},
        "by_regime": {},
        "by_asset_class": {},
        "had_perfect_day": False,
        "max_rr_achieved": 0.0,
        "profitable_asset_classes": [],
    }

    if not os.path.exists(HISTORY_FILE):
        return default

    try:
        df = pd.read_csv(HISTORY_FILE)
        filled = df[df["outcome"].isin(["WIN", "LOSS"])].copy()
        if len(filled) == 0:
            return default
    except Exception:
        return default

    # ── Overall win rate ──
    total = len(filled)
    wins = len(filled[filled["outcome"] == "WIN"])
    overall_win_rate = round(wins / total * 100, 1) if total > 0 else 0.0

    # ── Streak calculation (chronological order) ──
    filled_sorted = filled.sort_values("date").reset_index(drop=True)
    current_streak = 0
    max_streak = 0
    streak = 0
    for outcome in filled_sorted["outcome"]:
        if outcome == "WIN":
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    current_streak = streak  # Streak at end is the current one

    # ── Win rate by composite score range ──
    score_ranges = {
        "40-50": (40, 50),
        "50-60": (50, 60),
        "60-70": (60, 70),
        "70-80": (70, 80),
        "80-90": (80, 90),
        "90-100": (90, 100),
    }
    by_score_range = {}
    if "composite_score" in filled.columns:
        for label, (lo, hi) in score_ranges.items():
            bucket = filled[
                (filled["composite_score"] >= lo) & (filled["composite_score"] < hi)
            ]
            if len(bucket) > 0:
                bucket_wins = len(bucket[bucket["outcome"] == "WIN"])
                by_score_range[label] = {
                    "total": len(bucket),
                    "wins": bucket_wins,
                    "win_rate": round(bucket_wins / len(bucket) * 100, 1),
                }

    # ── Win rate by regime ──
    by_regime = {}
    if "regime" in filled.columns:
        for regime, group in filled.groupby("regime"):
            if pd.isna(regime) or str(regime).strip() == "":
                continue
            regime_wins = len(group[group["outcome"] == "WIN"])
            by_regime[str(regime)] = {
                "total": len(group),
                "wins": regime_wins,
                "win_rate": round(regime_wins / len(group) * 100, 1),
            }

    # ── Win rate by asset class ──
    # Infer asset class from ticker using settings universes
    def _classify_ticker(ticker: str) -> str:
        t = str(ticker).upper()
        if t in [s.upper() for s in settings.CRYPTO_UNIVERSE]:
            return "crypto"
        if t in [s.upper() for s in settings.FOREX_UNIVERSE]:
            return "forex"
        if t in [s.upper() for s in settings.COMMODITY_UNIVERSE]:
            return "commodities"
        if t in [s.upper() for s in settings.ETF_UNIVERSE]:
            return "etfs"
        return "stocks"

    by_asset_class = {}
    profitable_asset_classes = []
    if "ticker" in filled.columns:
        filled["_asset_class"] = filled["ticker"].apply(_classify_ticker)
        for ac, group in filled.groupby("_asset_class"):
            ac_wins = len(group[group["outcome"] == "WIN"])
            wr = round(ac_wins / len(group) * 100, 1) if len(group) > 0 else 0.0
            by_asset_class[str(ac)] = {
                "total": len(group),
                "wins": ac_wins,
                "win_rate": wr,
            }
            if wr > 50.0:
                profitable_asset_classes.append(str(ac))

    # ── Perfect day check ──
    had_perfect_day = False
    if "date" in filled.columns:
        for date_val, day_group in filled.groupby("date"):
            if len(day_group) >= 2 and all(day_group["outcome"] == "WIN"):
                had_perfect_day = True
                break

    # ── Max R:R achieved ──
    max_rr_achieved = 0.0
    if "pnl_pct" in filled.columns and "risk_reward" in filled.columns:
        winners = filled[filled["outcome"] == "WIN"]
        if len(winners) > 0:
            try:
                # Actual R:R = pnl / expected_risk_per_unit
                # Approximate from pnl_pct and planned risk_reward
                pnl_vals = pd.to_numeric(winners["pnl_pct"], errors="coerce")
                rr_vals = pd.to_numeric(winners["risk_reward"], errors="coerce")
                valid = pnl_vals.notna() & rr_vals.notna() & (rr_vals > 0)
                if valid.any():
                    # Actual achieved RR relative to stop distance
                    achieved_rr = pnl_vals[valid] / (pnl_vals[valid] / rr_vals[valid])
                    # Simpler: just use the raw risk_reward if pnl was positive
                    max_rr_achieved = float(rr_vals[valid].max())
                    # Also check if any pnl exceeded 3x the planned risk
                    for i in winners.index:
                        try:
                            pnl = float(winners.at[i, "pnl_pct"])
                            entry = float(winners.at[i, "entry_price"])
                            stop = float(winners.at[i, "stop_price"])
                            if entry and stop and entry != stop:
                                risk_pct = abs(entry - stop) / entry * 100
                                if risk_pct > 0:
                                    actual_rr = abs(pnl) / risk_pct
                                    max_rr_achieved = max(max_rr_achieved, actual_rr)
                        except (ValueError, TypeError):
                            continue
            except Exception:
                pass

    return {
        "overall_win_rate": overall_win_rate,
        "total_evaluated": total,
        "current_streak": current_streak,
        "max_streak": max_streak,
        "by_score_range": by_score_range,
        "by_regime": by_regime,
        "by_asset_class": by_asset_class,
        "had_perfect_day": had_perfect_day,
        "max_rr_achieved": round(max_rr_achieved, 2),
        "profitable_asset_classes": profitable_asset_classes,
    }


# ─────────────────────────────────────────────────────────────
#  ACHIEVEMENT TRIGGER CHECK
# ─────────────────────────────────────────────────────────────

def check_achievement_triggers(accuracy_data: dict | None = None) -> list[dict]:
    """
    Check whether any new achievements should be awarded based on
    current prediction accuracy data.

    Args:
        accuracy_data: Output from compute_prediction_accuracy().
                       If None, will compute fresh.

    Returns:
        List of newly earned achievement dicts from the achievements module.
    """
    from output.achievements import check_achievements

    if accuracy_data is None:
        accuracy_data = compute_prediction_accuracy()

    # Build the prediction_data dict that check_achievements expects
    prediction_data = {
        "current_streak": accuracy_data.get("current_streak", 0),
        "overall_win_rate": accuracy_data.get("overall_win_rate", 0.0),
        "total_predictions": accuracy_data.get("total_evaluated", 0),
        "profitable_asset_classes": accuracy_data.get("profitable_asset_classes", []),
        "had_perfect_day": accuracy_data.get("had_perfect_day", False),
        "max_rr_achieved": accuracy_data.get("max_rr_achieved", 0.0),
    }

    newly_earned = check_achievements(prediction_data)

    if newly_earned:
        logger.info(
            "New achievements unlocked: %s",
            ", ".join(a["name"] for a in newly_earned),
        )

    return newly_earned
