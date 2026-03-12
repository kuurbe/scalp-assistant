"""
Notification configuration — channel enablement, quiet hours, cooldowns.
Controls when and how notifications are dispatched.
"""
import datetime
import logging
import os

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  Channel definitions
# ─────────────────────────────────────────────────────────────
NOTIFICATION_CHANNELS = {
    "telegram": {
        "env_vars": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
        "label": "Telegram",
    },
    "discord": {
        "env_vars": ["DISCORD_WEBHOOK_URL"],
        "label": "Discord",
    },
    "macos": {
        "env_vars": [],  # always available on macOS
        "label": "macOS Notification",
    },
    "email": {
        "env_vars": ["ALERT_EMAIL", "ALERT_EMAIL_PASSWORD"],
        "label": "Email (SMTP)",
    },
}

# ─────────────────────────────────────────────────────────────
#  Cooldown tracking: {ticker: last_notify_datetime}
# ─────────────────────────────────────────────────────────────
_cooldown_tracker: dict[str, datetime.datetime] = {}

# Urgency priority order (for minimum urgency filtering)
_URGENCY_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


# ─────────────────────────────────────────────────────────────
#  Channel enablement
# ─────────────────────────────────────────────────────────────
def is_channel_enabled(channel: str) -> bool:
    """
    Check if a notification channel is enabled by verifying
    that all required environment variables are set.

    Args:
        channel: One of "telegram", "discord", "macos", "email"

    Returns:
        True if the channel is configured and ready to use.
    """
    try:
        ch = NOTIFICATION_CHANNELS.get(channel)
        if ch is None:
            logger.debug("Unknown notification channel: %s", channel)
            return False

        required_vars = ch.get("env_vars", [])
        if not required_vars:
            # No env vars required (e.g., macOS notifications)
            # Only enable macOS on darwin
            if channel == "macos":
                import platform
                return platform.system() == "Darwin"
            return True

        # All required env vars must be non-empty
        for var in required_vars:
            val = os.environ.get(var, "").strip()
            if not val:
                return False

        return True
    except Exception:
        logger.debug("Error checking channel %s", channel, exc_info=True)
        return False


def get_enabled_channels() -> list:
    """Return list of enabled channel names."""
    try:
        return [ch for ch in NOTIFICATION_CHANNELS if is_channel_enabled(ch)]
    except Exception:
        logger.debug("Error getting enabled channels", exc_info=True)
        return []


# ─────────────────────────────────────────────────────────────
#  Should-notify logic
# ─────────────────────────────────────────────────────────────
def should_notify(urgency: str, ticker: str = None) -> bool:
    """
    Determine whether a notification should be sent, considering:
      - Quiet hours (default 10pm - 7am from settings.NOTIFY_QUIET_HOURS)
      - Cooldown per ticker (settings.NOTIFY_COOLDOWN_SECONDS)
      - Minimum urgency level (HIGH always passes)

    Args:
        urgency: "HIGH", "MEDIUM", or "LOW"
        ticker: Optional ticker symbol for cooldown tracking

    Returns:
        True if the notification should be dispatched.
    """
    try:
        urgency = (urgency or "MEDIUM").upper()

        # 1. Quiet hours check (HIGH urgency bypasses quiet hours)
        if urgency != "HIGH" and _is_quiet_hours():
            logger.debug("Suppressed notification during quiet hours (urgency=%s)", urgency)
            return False

        # 2. Minimum urgency check
        min_score = getattr(settings, "NOTIFY_MIN_SCORE", 55)
        # LOW urgency only fires if min_score is very lenient (< 40)
        if urgency == "LOW" and min_score >= 40:
            logger.debug("Suppressed LOW urgency notification (min_score=%s)", min_score)
            return False

        # 3. Per-ticker cooldown
        if ticker:
            if not _check_cooldown(ticker):
                logger.debug("Suppressed notification for %s (cooldown active)", ticker)
                return False

        return True

    except Exception:
        logger.debug("Error in should_notify", exc_info=True)
        # Default to allowing notifications on error
        return True


def record_notification(ticker: str) -> None:
    """Record that a notification was sent for a ticker (update cooldown)."""
    try:
        if ticker:
            _cooldown_tracker[ticker.upper()] = datetime.datetime.now()
    except Exception:
        logger.debug("Error recording notification for %s", ticker, exc_info=True)


def clear_cooldowns() -> None:
    """Clear all cooldown tracking (useful for testing or reset)."""
    _cooldown_tracker.clear()


# ─────────────────────────────────────────────────────────────
#  Private helpers
# ─────────────────────────────────────────────────────────────

def _is_quiet_hours() -> bool:
    """Check if current time falls within quiet hours."""
    try:
        quiet = getattr(settings, "NOTIFY_QUIET_HOURS", (22, 7))
        if not quiet or len(quiet) != 2:
            return False

        start_hour, end_hour = quiet
        current_hour = datetime.datetime.now().hour

        # Handle overnight range (e.g., 22 to 7)
        if start_hour > end_hour:
            # Quiet from start_hour to midnight, and midnight to end_hour
            return current_hour >= start_hour or current_hour < end_hour
        else:
            # Simple range (e.g., 1 to 5)
            return start_hour <= current_hour < end_hour

    except Exception:
        logger.debug("Error checking quiet hours", exc_info=True)
        return False


def _check_cooldown(ticker: str) -> bool:
    """
    Check if enough time has passed since the last notification for this ticker.

    Returns:
        True if notification is allowed (cooldown expired or no prior notification).
    """
    try:
        ticker = ticker.upper()
        last_time = _cooldown_tracker.get(ticker)
        if last_time is None:
            return True

        cooldown_secs = getattr(settings, "NOTIFY_COOLDOWN_SECONDS", 600)
        elapsed = (datetime.datetime.now() - last_time).total_seconds()

        return elapsed >= cooldown_secs

    except Exception:
        logger.debug("Error checking cooldown for %s", ticker, exc_info=True)
        return True
