"""
Final weighted aggregate scorer.
Combines physics, technical, catalyst, and statistical sub-scores.
Outputs a ScoredTicker with all context needed for display and trading.
"""
import datetime
from dataclasses import dataclass, field
from config import settings


@dataclass
class ScoredTicker:
    ticker: str
    composite_score: float = 0
    direction: str = "LONG"
    entry_price: float = 0
    stop_price: float = 0
    target_price: float = 0
    aggressive_target: float = 0
    risk_reward: float = 0
    # Sub-scores
    physics_score: float = 0
    technical_score: float = 0
    catalyst_score: float = 0
    statistical_score: float = 0
    social_score: float = 0
    # Social intel context
    political_exposure: str = ""
    war_exposure: str = ""
    influencer_signal: str = ""
    social_narrative: str = ""
    # Context
    regime: str = "UNKNOWN"
    kinematic_phase: str = "UNKNOWN"
    hurst: float = 0.5
    entropy: float = 0.5
    confidence_tier: str = "C"
    # Narrative
    why_moving: str = ""
    where_headed: str = ""
    catalyst_summary: str = ""
    # Market data
    price: float = 0
    pct_change: float = 0
    rel_volume: float = 0
    rsi: float = 50
    atr: float = 0
    # Option play
    option_direction: str = ""
    option_safe_strike: float = 0
    option_agg_strike: float = 0
    option_exp_short: str = ""
    option_exp_long: str = ""
    option_budget: str = ""
    # Levels
    nearest_support: float = 0
    nearest_resistance: float = 0
    # Asset class
    asset_class: str = "stocks"
    # Timestamps
    scan_time: str = ""


def score_ticker(
    ticker: str,
    physics_score: float = 0,
    technical_score: float = 0,
    catalyst_score: float = 0,
    statistical_score: float = 0,
    social_score: float = 0,
    macro_regime: str = "NEUTRAL",
    regime_info: dict = None,
    kinematic_phase: str = "UNKNOWN",
    price_data: dict = None,
    levels_data: dict = None,
    targets_data: dict = None,
    catalyst_info: dict = None,
    sentiment_info: dict = None,
    social_info: dict = None,
    asset_class: str = "stocks",
) -> ScoredTicker:
    """
    Compute the final composite score and build a ScoredTicker.
    """
    # Weighted composite (now includes social)
    social_weight = getattr(settings, "WEIGHT_SOCIAL", 0.15)
    raw = (
        settings.WEIGHT_PHYSICS * physics_score +
        settings.WEIGHT_TECHNICAL * technical_score +
        settings.WEIGHT_CATALYST * catalyst_score +
        settings.WEIGHT_STATISTICAL * statistical_score +
        social_weight * social_score
    )

    # Macro multiplier
    macro_mult = {"RISK_ON": 1.15, "RISK_OFF": 0.75, "NEUTRAL": 1.0}.get(macro_regime, 1.0)
    composite = max(0, min(100, raw * macro_mult))

    # Determine direction
    if regime_info and regime_info.get("preferred_strategy") == "MEAN_REVERSION":
        # For mean reversion, direction depends on current position vs mean
        direction = "LONG"  # default to long for dip buying
    else:
        pct = price_data.get("pct_change", 0) if price_data else 0
        direction = "LONG" if pct >= 0 else "SHORT"

    # Confidence tier
    if composite >= 75:
        tier = "A"
    elif composite >= 55:
        tier = "B"
    else:
        tier = "C"

    # Build narratives
    why = catalyst_info.get("summary", "No catalyst detected") if catalyst_info else "No catalyst detected"
    where = targets_data.get("where_headed", "") if targets_data else ""

    # Option play (skip for crypto/forex — no options on Robinhood)
    price = price_data.get("price", 0) if price_data else 0
    asset_cfg = settings.ASSET_CLASS_CONFIG.get(asset_class, {})
    has_options = asset_cfg.get("has_options", True)
    option = _compute_option_play(price, direction) if has_options else {
        "dir": "CALL" if direction == "LONG" else "PUT",
        "safe": 0, "agg": 0, "exp_short": "N/A", "exp_long": "N/A", "budget": "N/A",
    }

    ri = regime_info or {}
    si = social_info or {}

    return ScoredTicker(
        ticker=ticker,
        composite_score=round(composite, 1),
        direction=direction,
        entry_price=price,
        stop_price=targets_data.get("stop_price", 0) if targets_data else 0,
        target_price=targets_data.get("conservative_target", 0) if targets_data else 0,
        aggressive_target=targets_data.get("aggressive_target", 0) if targets_data else 0,
        risk_reward=targets_data.get("risk_reward", 0) if targets_data else 0,
        physics_score=round(physics_score, 1),
        technical_score=round(technical_score, 1),
        catalyst_score=round(catalyst_score, 1),
        statistical_score=round(statistical_score, 1),
        social_score=round(social_score, 1),
        political_exposure=si.get("political_exposure", ""),
        war_exposure=si.get("war_exposure", ""),
        influencer_signal=si.get("influencer_signal", ""),
        social_narrative=si.get("social_narrative", ""),
        regime=ri.get("regime", "UNKNOWN"),
        kinematic_phase=kinematic_phase,
        hurst=ri.get("hurst", 0.5),
        entropy=ri.get("entropy", 0.5),
        confidence_tier=tier,
        why_moving=why,
        where_headed=where,
        catalyst_summary=catalyst_info.get("summary", "") if catalyst_info else "",
        price=price,
        pct_change=price_data.get("pct_change", 0) if price_data else 0,
        rel_volume=price_data.get("rel_volume", 0) if price_data else 0,
        rsi=price_data.get("rsi", 50) if price_data else 50,
        atr=price_data.get("atr", 0) if price_data else 0,
        option_direction=option["dir"],
        option_safe_strike=option["safe"],
        option_agg_strike=option["agg"],
        option_exp_short=option["exp_short"],
        option_exp_long=option["exp_long"],
        option_budget=option["budget"],
        nearest_support=levels_data.get("nearest_support", 0) if levels_data else 0,
        nearest_resistance=levels_data.get("nearest_resistance", 0) if levels_data else 0,
        asset_class=asset_class,
        scan_time=datetime.datetime.now().strftime("%I:%M %p"),
    )


def _compute_option_play(price: float, direction: str) -> dict:
    """Generate option strike/expiry recommendations."""
    if price <= 0:
        return {"dir": "CALL", "safe": 0, "agg": 0, "exp_short": "", "exp_long": "", "budget": "$0"}

    today = datetime.date.today()
    is_bull = direction == "LONG"
    opt_dir = "CALL" if is_bull else "PUT"
    safe = round(price * (1.02 if is_bull else 0.98))
    agg = round(price * (1.05 if is_bull else 0.95))

    days_to_friday = (4 - today.weekday()) % 7 or 7
    exp_short = (today + datetime.timedelta(days=days_to_friday)).strftime("%b %d")
    exp_long = (today + datetime.timedelta(days=days_to_friday + 7)).strftime("%b %d")

    if price < 15:
        budget = "$20-$60"
    elif price < 50:
        budget = "$40-$100"
    elif price < 150:
        budget = "$80-$180"
    else:
        budget = "$100-$300"

    return {"dir": opt_dir, "safe": safe, "agg": agg,
            "exp_short": exp_short, "exp_long": exp_long, "budget": budget}
