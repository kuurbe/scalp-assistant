"""
P&L Scenario Engine — dollar-amount projections for options scalps.

Computes option value at stop, target 1, target 2 prices, models
time decay over hold periods, and estimates IV crush impact.
Outputs plain English summaries for Telegram alerts.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def compute_scenarios(
    entry_price: float,
    strike: float,
    direction: str,
    iv: float,
    dte_hours: float,
    bid: float,
    ask: float,
    stop_price: float,
    target_1: float,
    target_2: float,
    hold_minutes: float = 30.0,
) -> dict:
    """Compute full P&L scenario table for an options scalp.

    Args:
        entry_price: current underlying price
        strike: option strike price
        direction: "call" or "put"
        iv: implied volatility (decimal)
        dte_hours: hours to expiration
        bid/ask: option bid and ask prices
        stop_price: underlying stop price
        target_1: underlying first target (50% scale)
        target_2: underlying second target (full exit)
        hold_minutes: expected hold time in minutes

    Returns dict with entry cost, P&L at each level, time decay, IV crush, breakeven.
    """
    from analysis.options_math import option_value_at_target, theta_per_hour, gamma_ramp_factor

    try:
        entry_cost = (bid + ask) / 2 if (bid + ask) > 0 else ask or bid or 0
        if entry_cost <= 0:
            return {}

        spread = ask - bid
        hold_hours = hold_minutes / 60.0

        # P&L at Target 1 (50% scale-out)
        t1 = option_value_at_target(
            entry_price, strike, target_1, hold_hours, iv,
            direction=direction, current_dte_hours=dte_hours,
        )

        # P&L at Target 2 (full exit)
        t2 = option_value_at_target(
            entry_price, strike, target_2, hold_hours * 1.5, iv,
            direction=direction, current_dte_hours=dte_hours,
        )

        # P&L at Stop
        stop = option_value_at_target(
            entry_price, strike, stop_price, hold_hours * 0.5, iv,
            direction=direction, current_dte_hours=dte_hours,
        )

        # Time decay scenarios
        th = theta_per_hour(entry_price, strike, dte_hours, iv, direction=direction)
        time_decay = {
            "30min": round(th * 0.5, 2),
            "1hr": round(th, 2),
            "2hr": round(th * 2, 2),
        }

        # IV crush scenario (IV drops 5%)
        iv_crush = option_value_at_target(
            entry_price, strike, entry_price, 0.5, iv,
            iv_change=-0.05, direction=direction, current_dte_hours=dte_hours,
        )

        # Gamma ramp
        gamma_factor = gamma_ramp_factor(dte_hours)

        # Breakeven: stock move needed to cover spread + 30min theta
        theta_30min = abs(th * 0.5)
        breakeven_cost = spread + theta_30min
        from analysis.options_math import compute_full_greeks
        greeks = compute_full_greeks(
            entry_price, strike, max(dte_hours / (252 * 6.5) * 365, 0.01),
            iv, direction=direction,
        )
        delta = abs(greeks.get("delta", 0.5))
        breakeven_move = breakeven_cost / delta if delta > 0.01 else 999

        return {
            "entry_cost": round(entry_cost, 2),
            "entry_cost_100": round(entry_cost * 100, 0),  # per contract (100 shares)
            "spread": round(spread, 2),
            "at_target_1": {
                "option_value": round(t1.get("new_premium", 0), 2),
                "profit_pct": round(t1.get("profit_pct", 0), 1),
                "profit_dollars": round(t1.get("profit", 0) * 100, 0),
                "underlying_price": target_1,
            },
            "at_target_2": {
                "option_value": round(t2.get("new_premium", 0), 2),
                "profit_pct": round(t2.get("profit_pct", 0), 1),
                "profit_dollars": round(t2.get("profit", 0) * 100, 0),
                "underlying_price": target_2,
            },
            "at_stop": {
                "option_value": round(stop.get("new_premium", 0), 2),
                "loss_pct": round(stop.get("profit_pct", 0), 1),
                "loss_dollars": round(stop.get("profit", 0) * 100, 0),
                "underlying_price": stop_price,
            },
            "time_decay": time_decay,
            "iv_crush_5pct": round(iv_crush.get("profit", 0) * 100, 0),
            "breakeven_move": round(breakeven_move, 2),
            "gamma_ramp_factor": gamma_factor,
            "gamma_warning": gamma_factor >= 2.0,
            "greeks": {
                "delta": greeks.get("delta", 0),
                "gamma": greeks.get("gamma", 0),
                "theta_hourly": round(th, 4),
                "vega": greeks.get("vega", 0),
            },
        }

    except Exception as e:
        logger.debug("compute_scenarios error: %s", e)
        return {}


def format_scenario_plain_english(
    scenarios: dict, ticker: str, strike: float, direction: str, expiry: str = "",
) -> str:
    """Convert P&L scenarios to plain English for Telegram alerts.

    No jargon — just dollar amounts and what happens at each price.
    """
    if not scenarios:
        return ""

    dir_word = "Call" if direction.lower() == "call" else "Put"
    dte_label = "expiring today" if "0dte" in expiry.lower() or expiry == "" else f"exp {expiry}"
    cost = scenarios.get("entry_cost", 0)
    cost_100 = scenarios.get("entry_cost_100", 0)

    lines = [
        f"Buy {ticker} ${strike:.0f} {dir_word} {dte_label} at ~${cost:.2f}",
        f"Cost: ${cost_100:.0f} per contract",
    ]

    # Target 1
    t1 = scenarios.get("at_target_1", {})
    if t1:
        lines.append(
            f"\nIf {ticker} hits ${t1['underlying_price']:.2f} → "
            f"option worth ~${t1['option_value']:.2f} "
            f"({t1['profit_pct']:+.0f}%, {'+' if t1['profit_dollars'] >= 0 else ''}${t1['profit_dollars']:.0f}/contract)"
        )

    # Target 2
    t2 = scenarios.get("at_target_2", {})
    if t2:
        lines.append(
            f"If {ticker} hits ${t2['underlying_price']:.2f} → "
            f"option worth ~${t2['option_value']:.2f} "
            f"({t2['profit_pct']:+.0f}%, {'+' if t2['profit_dollars'] >= 0 else ''}${t2['profit_dollars']:.0f}/contract)"
        )

    # Stop
    st = scenarios.get("at_stop", {})
    if st:
        lines.append(
            f"Stop: {ticker} below ${st['underlying_price']:.2f} → "
            f"option worth ~${st['option_value']:.2f} "
            f"({st['loss_pct']:+.0f}%)"
        )

    # Time decay
    td = scenarios.get("time_decay", {})
    if td:
        hr_cost = abs(td.get("1hr", 0))
        if hr_cost > 0.01:
            lines.append(f"\nTime decay: ~${hr_cost:.2f}/hr per contract")

    # IV crush warning
    iv_crush = scenarios.get("iv_crush_5pct", 0)
    if iv_crush < -10:
        lines.append(f"IV crush risk: ${abs(iv_crush):.0f}/contract if volatility drops 5%")

    # Gamma warning
    if scenarios.get("gamma_warning"):
        lines.append("⚡ Gamma zone — moves fast both ways, size small")

    # Spread
    spread = scenarios.get("spread", 0)
    if spread > 0:
        spread_label = "tight" if spread < 0.10 else "okay" if spread < 0.25 else "wide — careful"
        lines.append(f"Spread: ${spread:.2f} ({spread_label})")

    return "\n".join(lines)
