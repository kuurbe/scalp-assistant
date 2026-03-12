"""
Push notification system — dispatches alerts to Telegram, Discord, macOS, and email.
All functions fail silently (log at debug level) to avoid crashing the scanner.
"""
import logging
import os
import smtplib
import subprocess
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from signals.notification_config import (
    is_channel_enabled,
    should_notify,
    record_notification,
)
from signals.event_cards import format_event_card_text

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  Channel: Telegram
# ─────────────────────────────────────────────────────────────
def send_telegram(message: str, bot_token: str = None, chat_id: str = None) -> bool:
    """
    Send a message via Telegram Bot API.

    Args:
        message: Text to send
        bot_token: Telegram bot token (falls back to TELEGRAM_BOT_TOKEN env var)
        chat_id: Telegram chat ID (falls back to TELEGRAM_CHAT_ID env var)

    Returns:
        True if sent successfully, False otherwise.
    """
    try:
        import requests

        token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        cid = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

        if not token or not cid:
            logger.debug("Telegram not configured (missing bot_token or chat_id)")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": cid,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.debug("Telegram message sent successfully")
            return True
        else:
            logger.debug("Telegram API error: %s %s", resp.status_code, resp.text[:200])
            return False

    except Exception:
        logger.debug("Failed to send Telegram message", exc_info=True)
        return False


# ─────────────────────────────────────────────────────────────
#  Channel: Discord
# ─────────────────────────────────────────────────────────────
def send_discord(message: str, webhook_url: str = None) -> bool:
    """
    Send a message via Discord webhook.

    Args:
        message: Text to send
        webhook_url: Discord webhook URL (falls back to DISCORD_WEBHOOK_URL env var)

    Returns:
        True if sent successfully, False otherwise.
    """
    try:
        import requests

        url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", "")

        if not url:
            logger.debug("Discord not configured (missing webhook_url)")
            return False

        payload = {
            "content": message[:2000],  # Discord max message length
        }

        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            logger.debug("Discord message sent successfully")
            return True
        else:
            logger.debug("Discord webhook error: %s %s", resp.status_code, resp.text[:200])
            return False

    except Exception:
        logger.debug("Failed to send Discord message", exc_info=True)
        return False


# ─────────────────────────────────────────────────────────────
#  Channel: macOS native notification
# ─────────────────────────────────────────────────────────────
def send_macos_notification(title: str, message: str) -> bool:
    """
    Send a native macOS notification via osascript.

    Args:
        title: Notification title
        message: Notification body text

    Returns:
        True if sent successfully, False otherwise.
    """
    try:
        import platform
        if platform.system() != "Darwin":
            logger.debug("macOS notifications only available on Darwin")
            return False

        # Escape double quotes for AppleScript
        safe_title = (title or "Scalp Assistant").replace('"', '\\"')
        safe_msg = (message or "").replace('"', '\\"')

        # Truncate long messages for notification center
        if len(safe_msg) > 256:
            safe_msg = safe_msg[:253] + "..."

        script = (
            f'display notification "{safe_msg}" '
            f'with title "{safe_title}" '
            f'sound name "Glass"'
        )

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            logger.debug("macOS notification sent successfully")
            return True
        else:
            logger.debug("osascript error: %s", result.stderr[:200])
            return False

    except Exception:
        logger.debug("Failed to send macOS notification", exc_info=True)
        return False


# ─────────────────────────────────────────────────────────────
#  Channel: Email (SMTP)
# ─────────────────────────────────────────────────────────────
def send_email(
    subject: str,
    body: str,
    to_email: str = None,
    from_email: str = None,
    password: str = None,
) -> bool:
    """
    Send an email via SMTP (defaults to Gmail SMTP).

    Args:
        subject: Email subject line
        body: Email body text
        to_email: Recipient address (falls back to ALERT_EMAIL env var)
        from_email: Sender address (falls back to ALERT_EMAIL env var)
        password: SMTP password (falls back to ALERT_EMAIL_PASSWORD env var)

    Returns:
        True if sent successfully, False otherwise.
    """
    try:
        to_addr = to_email or os.environ.get("ALERT_EMAIL", "")
        from_addr = from_email or os.environ.get("ALERT_EMAIL", "")
        pwd = password or os.environ.get("ALERT_EMAIL_PASSWORD", "")

        if not to_addr or not from_addr or not pwd:
            logger.debug("Email not configured (missing ALERT_EMAIL or ALERT_EMAIL_PASSWORD)")
            return False

        msg = MIMEMultipart()
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg["Subject"] = subject or "Scalp Assistant Alert"
        msg.attach(MIMEText(body or "", "plain"))

        # Use Gmail SMTP by default; detect from address domain
        smtp_host = "smtp.gmail.com"
        smtp_port = 587
        if "@outlook." in from_addr or "@hotmail." in from_addr:
            smtp_host = "smtp-mail.outlook.com"
        elif "@yahoo." in from_addr:
            smtp_host = "smtp.mail.yahoo.com"

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(from_addr, pwd)
            server.send_message(msg)

        logger.debug("Email sent successfully to %s", to_addr)
        return True

    except Exception:
        logger.debug("Failed to send email", exc_info=True)
        return False


# ─────────────────────────────────────────────────────────────
#  Dispatcher: send to all enabled channels
# ─────────────────────────────────────────────────────────────
def notify(title: str, message: str, urgency: str = "MEDIUM") -> dict:
    """
    Dispatch a notification to all configured and enabled channels.

    Args:
        title: Notification title / headline
        message: Full notification body text
        urgency: "HIGH", "MEDIUM", or "LOW" — controls quiet-hours bypass

    Returns:
        dict of {channel_name: bool} indicating success/failure per channel.
    """
    results = {}

    try:
        # Build the full text for text-based channels
        full_text = f"{title}\n\n{message}" if title and message else (title or message or "")

        # Telegram
        if is_channel_enabled("telegram"):
            results["telegram"] = send_telegram(full_text)

        # Discord
        if is_channel_enabled("discord"):
            results["discord"] = send_discord(full_text)

        # macOS
        if is_channel_enabled("macos"):
            results["macos"] = send_macos_notification(title, message)

        # Email
        if is_channel_enabled("email"):
            results["email"] = send_email(
                subject=f"[Scalp Assistant] {title}",
                body=message,
            )

        if not results:
            logger.debug("No notification channels enabled")

    except Exception:
        logger.debug("Error in notify dispatcher", exc_info=True)

    return results


# ─────────────────────────────────────────────────────────────
#  Event card dispatcher
# ─────────────────────────────────────────────────────────────
def notify_event_card(card: dict) -> dict:
    """
    Format an event card and send it via the notify() dispatcher.
    Respects quiet hours, cooldowns, and urgency filtering.

    Args:
        card: Event card dict from event_cards.generate_event_card()

    Returns:
        dict of {channel_name: bool} or empty dict if suppressed.
    """
    try:
        urgency = card.get("urgency", "MEDIUM")
        tickers = card.get("tickers", [])
        primary_ticker = tickers[0] if tickers else None

        # Check should_notify for the primary ticker
        if not should_notify(urgency, ticker=primary_ticker):
            logger.debug(
                "Event card suppressed: %s for %s (urgency=%s)",
                card.get("event_type", "?"),
                primary_ticker or "N/A",
                urgency,
            )
            return {}

        # Format the card text
        title = f"[{card.get('event_type', 'EVENT')}] {card.get('title', 'Alert')}"
        body = format_event_card_text(card)

        results = notify(title, body, urgency=urgency)

        # Record cooldown for each ticker
        for ticker in tickers:
            record_notification(ticker)

        return results

    except Exception:
        logger.debug("Error in notify_event_card", exc_info=True)
        return {}
