"""
Chat Recommendation Journal — tracks every play recommended via chat (not auto-scanner).

Separate from scan_history.csv which logs auto-scanner picks. This journal
captures the plays I personally recommend through conversation, with full
context (confidence score, rationale, expected outcome) so I can learn what
works over time.

Schema:
    timestamp        — ISO datetime when recommended
    ticker           — symbol (stock or crypto)
    asset_class      — stocks | etfs | crypto | options
    direction        — CALL | PUT | LONG | SHORT
    strike           — option strike (blank for stocks)
    expiry           — option expiry (blank for stocks)
    entry_price      — underlying price at recommendation
    contract_cost    — option premium per contract (blank for stocks)
    quantity         — contracts/shares recommended
    total_cost       — total dollars at risk
    stop_price       — exit on breach
    target_1         — first scale-out
    target_2         — full exit
    confidence       — 0-100 confidence score
    rationale        — why this play (1-line summary)
    catalysts        — pipe-separated triggers (e.g. "RSI_OVERSOLD|VWAP_RECLAIM|VIX_CRUSH")
    market_regime    — RISK_ON | RISK_OFF | NEUTRAL | CHOP
    setup_type       — IV_CRUSH_PUT | VWAP_RECLAIM_CALL | etc
    horizon_hours    — expected hold time
    outcome          — WIN | LOSS | EXPIRED | (blank if open)
    exit_price       — actual exit
    pnl_pct          — realized P&L %
    pnl_dollars      — realized P&L $
    notes            — post-mortem
"""
from __future__ import annotations
import os
import csv
import datetime
import logging
from typing import Optional

logger = logging.getLogger(__name__)

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
JOURNAL_FILE = os.path.join(LOGS_DIR, "chat_recommendations.csv")

FIELDS = [
    "timestamp", "ticker", "asset_class", "direction",
    "strike", "expiry", "entry_price", "contract_cost", "quantity", "total_cost",
    "stop_price", "target_1", "target_2",
    "confidence", "rationale", "catalysts", "market_regime", "setup_type",
    "horizon_hours",
    "outcome", "exit_price", "pnl_pct", "pnl_dollars", "notes",
]


def _ensure_file():
    os.makedirs(LOGS_DIR, exist_ok=True)
    if not os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()


def log_recommendation(
    ticker: str,
    direction: str,
    entry_price: float,
    confidence: int,
    rationale: str,
    *,
    asset_class: str = "stocks",
    strike: Optional[float] = None,
    expiry: Optional[str] = None,
    contract_cost: Optional[float] = None,
    quantity: int = 1,
    stop_price: Optional[float] = None,
    target_1: Optional[float] = None,
    target_2: Optional[float] = None,
    catalysts: Optional[list] = None,
    market_regime: str = "",
    setup_type: str = "",
    horizon_hours: float = 6.5,
) -> dict:
    """Log a play recommendation. Returns the row dict written."""
    _ensure_file()

    total_cost = 0.0
    if contract_cost is not None:
        total_cost = contract_cost * 100 * quantity  # options contracts = 100 shares
    elif entry_price > 0:
        total_cost = entry_price * quantity

    row = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "ticker": ticker.upper(),
        "asset_class": asset_class,
        "direction": direction.upper(),
        "strike": strike if strike is not None else "",
        "expiry": expiry or "",
        "entry_price": round(entry_price, 4),
        "contract_cost": round(contract_cost, 2) if contract_cost is not None else "",
        "quantity": quantity,
        "total_cost": round(total_cost, 2),
        "stop_price": round(stop_price, 4) if stop_price is not None else "",
        "target_1": round(target_1, 4) if target_1 is not None else "",
        "target_2": round(target_2, 4) if target_2 is not None else "",
        "confidence": int(confidence),
        "rationale": rationale[:200],
        "catalysts": "|".join(catalysts) if catalysts else "",
        "market_regime": market_regime,
        "setup_type": setup_type,
        "horizon_hours": horizon_hours,
        "outcome": "",
        "exit_price": "",
        "pnl_pct": "",
        "pnl_dollars": "",
        "notes": "",
    }

    with open(JOURNAL_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writerow(row)

    logger.info("Logged recommendation: %s %s @ %s (conf=%d)",
                ticker, direction, entry_price, confidence)
    return row


def evaluate_open_recommendations(force: bool = False) -> dict:
    """Walk open recs, mark WIN/LOSS via current price.

    For options: WIN if underlying hit target_1 before stop, LOSS if hit stop first.
    For stocks: same logic.

    Returns: {evaluated, wins, losses, errors, still_open}
    """
    import pandas as pd
    try:
        import yfinance as yf
    except ImportError:
        return {"evaluated": 0, "wins": 0, "losses": 0, "errors": 0, "still_open": 0}

    if not os.path.exists(JOURNAL_FILE):
        return {"evaluated": 0, "wins": 0, "losses": 0, "errors": 0, "still_open": 0}

    df = pd.read_csv(JOURNAL_FILE)
    if len(df) == 0:
        return {"evaluated": 0, "wins": 0, "losses": 0, "errors": 0, "still_open": 0}

    stats = {"evaluated": 0, "wins": 0, "losses": 0, "errors": 0, "still_open": 0}
    now = datetime.datetime.now()

    for idx in df.index:
        outcome_val = df.at[idx, "outcome"]
        # Skip already-evaluated rows
        if pd.notna(outcome_val) and str(outcome_val).strip() in ("WIN", "LOSS", "EXPIRED"):
            continue

        try:
            ts = pd.to_datetime(df.at[idx, "timestamp"])
            horizon = float(df.at[idx, "horizon_hours"] or 6.5)
            elapsed = (now - ts.to_pydatetime()).total_seconds() / 3600

            # Check if expired (option) or past horizon (stock)
            expiry_str = str(df.at[idx, "expiry"])
            is_expired = False
            if expiry_str and expiry_str != "nan" and expiry_str != "":
                try:
                    exp_date = pd.to_datetime(expiry_str).date()
                    if exp_date < now.date():
                        is_expired = True
                except Exception:
                    pass

            if not force and elapsed < horizon and not is_expired:
                stats["still_open"] += 1
                continue

            ticker = df.at[idx, "ticker"]
            entry = float(df.at[idx, "entry_price"])
            direction = str(df.at[idx, "direction"]).upper()
            stop_price = df.at[idx, "stop_price"]
            target_1 = df.at[idx, "target_1"]

            # Fetch high/low between entry timestamp and now
            tk = yf.Ticker(ticker)
            start_date = ts.date()
            end_date = (now + datetime.timedelta(days=1)).date()
            try:
                hist = tk.history(start=start_date, end=end_date, interval="1h")
            except Exception:
                hist = None
            if hist is None or hist.empty:
                # Fallback: 10-day daily bars then filter to >= entry timestamp
                try:
                    hist = tk.history(period="10d")
                    # Strip timezone to compare with naive ts
                    if hasattr(hist.index, "tz") and hist.index.tz is not None:
                        hist.index = hist.index.tz_localize(None)
                    hist = hist[hist.index >= pd.Timestamp(ts).tz_localize(None) if hasattr(ts, 'tz') and ts.tz else hist.index >= pd.Timestamp(ts)]
                except Exception:
                    hist = None
            else:
                # Filter intraday bars to bars at or after entry timestamp
                try:
                    if hasattr(hist.index, "tz") and hist.index.tz is not None:
                        hist.index = hist.index.tz_localize(None)
                    ts_naive = pd.Timestamp(ts).tz_localize(None) if hasattr(ts, 'tz') and ts.tz else pd.Timestamp(ts)
                    hist = hist[hist.index >= ts_naive]
                except Exception:
                    pass
            if hist is None or hist.empty:
                stats["errors"] += 1
                continue

            high = float(hist["High"].max())
            low = float(hist["Low"].min())
            current = float(hist["Close"].iloc[-1])

            # Determine outcome based on direction
            outcome = "OPEN"
            exit_price = current

            if direction in ("CALL", "LONG", "BULLISH"):
                hit_target = target_1 != "" and pd.notna(target_1) and high >= float(target_1)
                hit_stop = stop_price != "" and pd.notna(stop_price) and low <= float(stop_price)
                if hit_target and not hit_stop:
                    outcome = "WIN"
                    exit_price = float(target_1)
                elif hit_stop and not hit_target:
                    outcome = "LOSS"
                    exit_price = float(stop_price)
                elif hit_target and hit_stop:
                    # Both hit — assume stop first (conservative)
                    outcome = "LOSS"
                    exit_price = float(stop_price)
                elif is_expired:
                    outcome = "WIN" if current > entry else "LOSS"
            elif direction in ("PUT", "SHORT", "BEARISH"):
                hit_target = target_1 != "" and pd.notna(target_1) and low <= float(target_1)
                hit_stop = stop_price != "" and pd.notna(stop_price) and high >= float(stop_price)
                if hit_target and not hit_stop:
                    outcome = "WIN"
                    exit_price = float(target_1)
                elif hit_stop and not hit_target:
                    outcome = "LOSS"
                    exit_price = float(stop_price)
                elif hit_target and hit_stop:
                    outcome = "LOSS"
                    exit_price = float(stop_price)
                elif is_expired:
                    outcome = "WIN" if current < entry else "LOSS"

            if outcome == "OPEN":
                stats["still_open"] += 1
                continue

            # Compute P&L
            pnl_pct = (exit_price - entry) / entry * 100
            if direction in ("PUT", "SHORT", "BEARISH"):
                pnl_pct = -pnl_pct

            df.at[idx, "outcome"] = outcome
            df.at[idx, "exit_price"] = round(exit_price, 4)
            df.at[idx, "pnl_pct"] = round(pnl_pct, 2)

            # Approximate dollar P&L using delta=0.5 for options
            try:
                total_cost = float(df.at[idx, "total_cost"] or 0)
                if df.at[idx, "contract_cost"] != "" and pd.notna(df.at[idx, "contract_cost"]):
                    # Rough: option moves ~50% of underlying move at ATM
                    pnl_dollars = total_cost * (pnl_pct / 100) * 5  # crude leverage estimate
                else:
                    pnl_dollars = total_cost * pnl_pct / 100
                df.at[idx, "pnl_dollars"] = round(pnl_dollars, 2)
            except Exception:
                pass

            stats["evaluated"] += 1
            if outcome == "WIN":
                stats["wins"] += 1
            elif outcome == "LOSS":
                stats["losses"] += 1

        except Exception as e:
            logger.debug("Error evaluating row %d: %s", idx, e)
            stats["errors"] += 1

    if stats["evaluated"] > 0:
        df.to_csv(JOURNAL_FILE, index=False)

    return stats


def get_journal_stats() -> dict:
    """Compute lifetime stats from the chat recommendation journal."""
    import pandas as pd

    if not os.path.exists(JOURNAL_FILE):
        return {"total": 0, "evaluated": 0, "wins": 0, "losses": 0, "win_rate": 0.0}

    df = pd.read_csv(JOURNAL_FILE)
    total = len(df)
    evaluated = df[df["outcome"].isin(["WIN", "LOSS"])]
    wins = len(evaluated[evaluated["outcome"] == "WIN"])
    losses = len(evaluated[evaluated["outcome"] == "LOSS"])
    win_rate = round(wins / max(len(evaluated), 1) * 100, 1)

    stats = {
        "total": total,
        "evaluated": len(evaluated),
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "still_open": total - len(evaluated),
    }

    # Win rate by confidence bucket
    if "confidence" in df.columns and len(evaluated) > 0:
        buckets = {"high (80+)": (80, 101), "med (60-80)": (60, 80), "low (<60)": (0, 60)}
        by_conf = {}
        for label, (lo, hi) in buckets.items():
            sub = evaluated[(evaluated["confidence"] >= lo) & (evaluated["confidence"] < hi)]
            if len(sub) > 0:
                w = len(sub[sub["outcome"] == "WIN"])
                by_conf[label] = {"n": len(sub), "wins": w, "win_rate": round(w/len(sub)*100, 1)}
        stats["by_confidence"] = by_conf

    # Win rate by setup
    if "setup_type" in df.columns and len(evaluated) > 0:
        by_setup = {}
        for setup, group in evaluated.groupby("setup_type"):
            if not setup or str(setup) == "nan":
                continue
            w = len(group[group["outcome"] == "WIN"])
            by_setup[str(setup)] = {"n": len(group), "wins": w, "win_rate": round(w/len(group)*100, 1)}
        stats["by_setup"] = by_setup

    # Total realized P&L
    if "pnl_dollars" in df.columns:
        try:
            stats["total_pnl_dollars"] = round(
                pd.to_numeric(evaluated["pnl_dollars"], errors="coerce").sum(), 2
            )
        except Exception:
            stats["total_pnl_dollars"] = 0.0

    return stats
