"""
Position sizing calculator — ATR-based risk management.
Every alert includes recommended position size and risk parameters.
"""
import logging
from config import settings

logger = logging.getLogger(__name__)

DEFAULT_ACCOUNT = getattr(settings, "DEFAULT_ACCOUNT_SIZE", 10000)
DEFAULT_RISK_PCT = getattr(settings, "DEFAULT_RISK_PCT", 1.0)


def compute_position_size(
    entry_price: float,
    stop_price: float,
    account_size: float = None,
    risk_pct: float = None,
) -> dict:
    """
    Compute position size based on account risk and stop distance.

    Formula: shares = (account * risk%) / |entry - stop|
    """
    try:
        acct = account_size or DEFAULT_ACCOUNT
        risk = risk_pct or DEFAULT_RISK_PCT

        if entry_price <= 0 or stop_price <= 0:
            return {"shares": 0, "position_value": 0, "risk_amount": 0, "risk_pct": risk}

        stop_distance = abs(entry_price - stop_price)
        if stop_distance < 0.01:
            return {"shares": 0, "position_value": 0, "risk_amount": 0, "risk_pct": risk}

        risk_amount = acct * (risk / 100.0)
        shares = int(risk_amount / stop_distance)
        position_value = shares * entry_price

        # Cap at 20% of account
        max_position = acct * 0.20
        if position_value > max_position:
            shares = int(max_position / entry_price)
            position_value = shares * entry_price

        return {
            "shares": shares,
            "position_value": round(position_value, 2),
            "risk_amount": round(risk_amount, 2),
            "risk_pct": risk,
            "stop_distance": round(stop_distance, 2),
        }
    except Exception:
        logger.debug("Position sizing failed", exc_info=True)
        return {"shares": 0, "position_value": 0, "risk_amount": 0, "risk_pct": DEFAULT_RISK_PCT}


def format_position_line(entry_price: float, stop_price: float) -> str:
    """Return a formatted position sizing line for Telegram alerts."""
    pos = compute_position_size(entry_price, stop_price)
    if pos["shares"] <= 0:
        return ""
    return (
        f"   📐 Size: {pos['shares']} shares (${pos['position_value']:,.0f}) "
        f"| Risk: ${pos['risk_amount']:.0f} ({pos['risk_pct']:.0f}%)"
    )
