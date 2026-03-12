"""
Achievement system for Scalp Assistant — gamified prediction tracking.
Defines achievements, checks earned status, persists to disk.
"""
import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
ACHIEVEMENTS_FILE = os.path.join(LOGS_DIR, "achievements.json")

# ─────────────────────────────────────────────────────────────
#  ACHIEVEMENT DEFINITIONS
# ─────────────────────────────────────────────────────────────

ACHIEVEMENTS = {
    # ── Hot streak (consecutive correct predictions) ──
    "hot_streak_3": {
        "name": "On Fire",
        "description": "3 consecutive correct predictions",
        "tier": "BRONZE",
        "check": lambda data: data.get("current_streak", 0) >= 3,
    },
    "hot_streak_5": {
        "name": "Hot Hand",
        "description": "5 consecutive correct predictions",
        "tier": "SILVER",
        "check": lambda data: data.get("current_streak", 0) >= 5,
    },
    "hot_streak_10": {
        "name": "Untouchable",
        "description": "10 consecutive correct predictions",
        "tier": "GOLD",
        "check": lambda data: data.get("current_streak", 0) >= 10,
    },
    # ── Accuracy milestones ──
    "accuracy_60": {
        "name": "Sharp Shooter",
        "description": "60% overall prediction accuracy",
        "tier": "BRONZE",
        "check": lambda data: data.get("overall_win_rate", 0) >= 60.0,
    },
    "accuracy_65": {
        "name": "Precision Trader",
        "description": "65% overall prediction accuracy",
        "tier": "SILVER",
        "check": lambda data: data.get("overall_win_rate", 0) >= 65.0,
    },
    "accuracy_70": {
        "name": "Oracle",
        "description": "70% overall prediction accuracy",
        "tier": "GOLD",
        "check": lambda data: data.get("overall_win_rate", 0) >= 70.0,
    },
    # ── Volume milestones (total predictions made) ──
    "total_100": {
        "name": "Centurion",
        "description": "100 total predictions made",
        "tier": "BRONZE",
        "check": lambda data: data.get("total_predictions", 0) >= 100,
    },
    "total_500": {
        "name": "Veteran",
        "description": "500 total predictions made",
        "tier": "SILVER",
        "check": lambda data: data.get("total_predictions", 0) >= 500,
    },
    "total_1000": {
        "name": "Market Marathon",
        "description": "1000 total predictions made",
        "tier": "GOLD",
        "check": lambda data: data.get("total_predictions", 0) >= 1000,
    },
    # ── Special achievements ──
    "multi_asset": {
        "name": "Diversified Alpha",
        "description": "Profitable predictions in 3+ asset classes",
        "tier": "SILVER",
        "check": lambda data: len(data.get("profitable_asset_classes", [])) >= 3,
    },
    "perfect_day": {
        "name": "Perfect Day",
        "description": "All predictions correct in a single day",
        "tier": "GOLD",
        "check": lambda data: data.get("had_perfect_day", False),
    },
    "big_winner": {
        "name": "Whale Trade",
        "description": "Single prediction achieved 3x+ R:R",
        "tier": "PLATINUM",
        "check": lambda data: data.get("max_rr_achieved", 0) >= 3.0,
    },
}


# ─────────────────────────────────────────────────────────────
#  PERSISTENCE
# ─────────────────────────────────────────────────────────────

def load_achievements() -> list[dict]:
    """
    Load earned achievements from logs/achievements.json.

    Returns:
        List of dicts, each with:
            achievement_id (str), name (str), tier (str),
            earned_at (str ISO timestamp)
    """
    if not os.path.exists(ACHIEVEMENTS_FILE):
        return []
    try:
        with open(ACHIEVEMENTS_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error("Failed to load achievements: %s", e)
        return []


def save_achievement(achievement: dict) -> None:
    """
    Append a newly earned achievement to logs/achievements.json.

    Args:
        achievement: Dict with achievement_id, name, tier, earned_at.
    """
    os.makedirs(LOGS_DIR, exist_ok=True)
    existing = load_achievements()

    # Prevent duplicates
    earned_ids = {a["achievement_id"] for a in existing}
    if achievement.get("achievement_id") in earned_ids:
        return

    existing.append(achievement)
    try:
        with open(ACHIEVEMENTS_FILE, "w") as f:
            json.dump(existing, f, indent=2)
        logger.info(
            "Achievement unlocked: %s (%s)",
            achievement.get("name"),
            achievement.get("tier"),
        )
    except Exception as e:
        logger.error("Failed to save achievement: %s", e)


# ─────────────────────────────────────────────────────────────
#  CHECKING & QUERYING
# ─────────────────────────────────────────────────────────────

def check_achievements(prediction_data: dict) -> list[dict]:
    """
    Check all achievements against current prediction data and return
    any newly earned achievements.

    Args:
        prediction_data: Dict containing stats used by check functions:
            - current_streak (int): Current consecutive correct predictions
            - overall_win_rate (float): Win rate as percentage (0-100)
            - total_predictions (int): Total evaluated predictions
            - profitable_asset_classes (list[str]): Asset classes with >50% win rate
            - had_perfect_day (bool): Whether any single day had 100% accuracy
            - max_rr_achieved (float): Best risk-reward ratio achieved

    Returns:
        List of newly earned achievement dicts (achievement_id, name,
        description, tier, earned_at).
    """
    already_earned = {a["achievement_id"] for a in load_achievements()}
    newly_earned = []

    for ach_id, ach_def in ACHIEVEMENTS.items():
        if ach_id in already_earned:
            continue

        try:
            if ach_def["check"](prediction_data):
                new_ach = {
                    "achievement_id": ach_id,
                    "name": ach_def["name"],
                    "description": ach_def["description"],
                    "tier": ach_def["tier"],
                    "earned_at": datetime.now().isoformat(),
                }
                save_achievement(new_ach)
                newly_earned.append(new_ach)
        except Exception as e:
            logger.debug("Error checking achievement %s: %s", ach_id, e)

    return newly_earned


def get_all_achievements() -> list[dict]:
    """
    Return every defined achievement with its earned status.

    Returns:
        List of dicts, each containing:
            achievement_id, name, description, tier,
            earned (bool), earned_at (str | None)
    """
    earned_map = {a["achievement_id"]: a for a in load_achievements()}

    result = []
    for ach_id, ach_def in ACHIEVEMENTS.items():
        earned_info = earned_map.get(ach_id)
        result.append({
            "achievement_id": ach_id,
            "name": ach_def["name"],
            "description": ach_def["description"],
            "tier": ach_def["tier"],
            "earned": earned_info is not None,
            "earned_at": earned_info["earned_at"] if earned_info else None,
        })

    return result
