"""
Alert formatting, deduplication, and logging.
"""
import datetime
import json
import os
from config import settings

# In-memory alert dedup tracker
_recent_alerts: dict[str, datetime.datetime] = {}

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "live_alerts.log")


def should_alert(ticker: str, signal_type: str) -> bool:
    """Check if an alert should fire (respects cooldown)."""
    key = f"{ticker}:{signal_type}"
    now = datetime.datetime.now()
    last = _recent_alerts.get(key)
    if last and (now - last).total_seconds() < settings.ALERT_COOLDOWN_SECONDS:
        return False
    return True


def fire_alert(ticker: str, signal_type: str, data: dict) -> dict:
    """
    Record and format an alert.
    Returns the formatted alert dict.
    """
    key = f"{ticker}:{signal_type}"
    _recent_alerts[key] = datetime.datetime.now()

    alert = {
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
        "ticker": ticker,
        "type": signal_type,
        "confidence": data.get("confidence", 0),
        "price": data.get("price_at_spark", data.get("price", 0)),
        "explanation": data.get("explanation", []),
    }

    # Log to file
    _log_alert(alert)

    return alert


def _log_alert(alert: dict):
    """Append alert to log file."""
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(alert) + "\n")
    except Exception:
        pass


def format_alert_line(alert: dict) -> str:
    """Format alert as a single terminal line."""
    emoji = {"SPARK": "⚡", "DIP": "📉", "CATALYST": "📰", "LEVEL_TEST": "📊"}.get(alert["type"], "🔔")
    reasons = " | ".join(alert.get("explanation", [])[:3])
    return f"{alert['time']} {emoji} {alert['type']} {alert['ticker']} ${alert.get('price', 0):.2f} — {reasons}"
