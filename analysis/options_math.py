"""
Black-Scholes options probability calculator.
Computes P(ITM), Delta, and optimal strike selection for trade alerts.
"""
import math
import datetime
import logging

logger = logging.getLogger(__name__)

# Risk-free rate (approximate US 10Y yield)
RISK_FREE_RATE = 0.043


def _norm_cdf(x: float) -> float:
    """Standard normal CDF — no scipy dependency."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_prob(
    price: float,
    strike: float,
    days_to_expiry: int,
    iv: float = 0.30,
    risk_free: float = RISK_FREE_RATE,
    direction: str = "CALL",
) -> dict:
    """
    Calculate Black-Scholes probability metrics for an option.

    Args:
        price:          Current stock price (S)
        strike:         Option strike price (K)
        days_to_expiry: Days until expiration
        iv:             Implied volatility (decimal, e.g. 0.30 = 30%)
        risk_free:      Risk-free rate (decimal)
        direction:      "CALL" or "PUT"

    Returns:
        dict with: d1, d2, prob_itm, delta, iv, days_to_expiry
    """
    try:
        if price <= 0 or strike <= 0 or days_to_expiry <= 0 or iv <= 0:
            return {"prob_itm": 0, "delta": 0, "d1": 0, "d2": 0,
                    "iv": iv, "days_to_expiry": days_to_expiry}

        S = price
        K = strike
        T = days_to_expiry / 365.0
        r = risk_free
        sigma = iv

        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if direction == "CALL":
            prob_itm = _norm_cdf(d2)
            delta = _norm_cdf(d1)
        else:  # PUT
            prob_itm = _norm_cdf(-d2)
            delta = _norm_cdf(d1) - 1.0  # negative for puts

        return {
            "prob_itm": round(prob_itm * 100, 1),
            "delta": round(abs(delta), 3),
            "d1": round(d1, 4),
            "d2": round(d2, 4),
            "iv": iv,
            "days_to_expiry": days_to_expiry,
        }

    except Exception as e:
        logger.debug("Black-Scholes calc error: %s", e)
        return {"prob_itm": 0, "delta": 0, "d1": 0, "d2": 0,
                "iv": iv, "days_to_expiry": days_to_expiry}


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def compute_full_greeks(
    price: float,
    strike: float,
    days_to_expiry: float,
    iv: float = 0.30,
    risk_free: float = RISK_FREE_RATE,
    direction: str = "call",
) -> dict:
    """Compute Delta, Gamma, Theta, Vega for an option.

    Returns dict with: delta, gamma, theta (per day), vega (per 1% IV change),
    premium_est (rough BS premium estimate).
    """
    try:
        S = price
        K = strike
        T = max(days_to_expiry / 365.0, 0.0001)
        r = risk_free
        sigma = max(iv, 0.01)
        sqrt_T = math.sqrt(T)

        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T

        nd1 = _norm_pdf(d1)
        Nd1 = _norm_cdf(d1)
        Nd2 = _norm_cdf(d2)

        # Gamma (same for calls and puts)
        gamma = nd1 / (S * sigma * sqrt_T)

        # Vega (per 1% IV change)
        vega = S * nd1 * sqrt_T / 100.0

        is_call = direction.lower() in ("call", "long")
        if is_call:
            delta = Nd1
            theta = (-(S * nd1 * sigma) / (2 * sqrt_T)
                     - r * K * math.exp(-r * T) * Nd2) / 365.0
            premium = S * Nd1 - K * math.exp(-r * T) * Nd2
        else:
            delta = Nd1 - 1.0
            theta = (-(S * nd1 * sigma) / (2 * sqrt_T)
                     + r * K * math.exp(-r * T) * _norm_cdf(-d2)) / 365.0
            premium = K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)

        # Theta per hour (for 0DTE scalps)
        theta_hourly = theta * 365 / (252 * 6.5)  # daily → hourly trading rate

        return {
            "delta": round(delta, 3),
            "gamma": round(gamma, 4),
            "theta": round(theta, 3),
            "theta_hourly": round(theta_hourly, 4),
            "vega": round(vega, 3),
            "premium_est": round(max(premium, 0.01), 2),
            "d1": round(d1, 4),
            "d2": round(d2, 4),
        }
    except Exception as e:
        logger.debug("Full Greeks calc error: %s", e)
        return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0, "premium_est": 0}


def select_scalp_strike(
    price: float,
    atr: float,
    direction: str = "call",
    days_to_expiry: float = 1.0,
    iv: float = 0.30,
) -> dict:
    """Select optimal strike for scalp options.

    0DTE: ATM (max gamma exposure).
    Weekly: ATM to 1% OTM.
    Returns dict with: strike, delta, gamma, expected_move.
    """
    is_call = direction.lower() in ("call", "long")
    is_0dte = days_to_expiry < 1.0

    if is_0dte:
        # ATM for 0DTE — max gamma
        strike = round(price)
    else:
        # Slightly OTM for weekly
        offset = price * 0.01  # 1% OTM
        strike = round(price + offset if is_call else price - offset)

    greeks = compute_full_greeks(price, strike, days_to_expiry, iv, direction=direction)
    return {
        "strike": strike,
        "delta": greeks.get("delta", 0.5),
        "gamma": greeks.get("gamma", 0),
        "theta_daily": greeks.get("theta", 0),
        "vega": greeks.get("vega", 0),
        "premium_est": greeks.get("premium_est", 0),
    }


# ── 0DTE Enhancements ──────────────────────────────────────────────────

TRADING_HOURS_PER_DAY = 6.5  # market hours
TRADING_DAYS_PER_YEAR = 252


def theta_per_hour(
    price: float, strike: float, hours_to_expiry: float,
    iv: float = 0.30, risk_free: float = RISK_FREE_RATE, direction: str = "call",
) -> float:
    """Theta in dollars per hour for 0DTE options.

    For intraday scalps, daily theta is misleading — this gives the actual
    hourly decay rate which accelerates dramatically as expiry approaches.
    """
    try:
        if hours_to_expiry <= 0:
            return 0.0
        # Convert hours to fractional years
        T = hours_to_expiry / (TRADING_DAYS_PER_YEAR * TRADING_HOURS_PER_DAY)
        greeks = compute_full_greeks(price, strike, T * 365, iv, risk_free, direction)
        # Daily theta → hourly: divide by trading hours in a day
        return round(greeks.get("theta", 0) * 365 / (TRADING_DAYS_PER_YEAR * TRADING_HOURS_PER_DAY), 4)
    except Exception:
        return 0.0


def gamma_ramp_factor(hours_to_expiry: float) -> float:
    """How much gamma has expanded vs a 1-day baseline.

    For ATM options, gamma ∝ 1/√T. As T→0, gamma → ∞.
    Returns ratio vs 1-day (6.5 hours) baseline.
    Factor > 2.0 = "gamma ramp zone" (last ~2 hours of 0DTE).
    """
    try:
        if hours_to_expiry <= 0:
            return 10.0  # near-infinite gamma at expiry
        baseline_hours = TRADING_HOURS_PER_DAY  # 1 trading day
        return round(math.sqrt(baseline_hours / hours_to_expiry), 2)
    except Exception:
        return 1.0


def option_value_at_target(
    price: float, strike: float, new_price: float,
    hours_elapsed: float, iv: float, iv_change: float = 0.0,
    direction: str = "call", current_dte_hours: float = 6.5,
) -> dict:
    """Estimate option value at a target price after time + IV change.

    Uses second-order Taylor expansion:
    new_premium ≈ old_premium + δ(dS) + ½γ(dS)² + θ(dt) + ν(dIV)

    Args:
        price: current underlying price
        strike: option strike
        new_price: target underlying price
        hours_elapsed: how many hours until reaching target
        iv: current implied volatility
        iv_change: change in IV (e.g., -0.05 for 5% IV crush)
        direction: "call" or "put"
        current_dte_hours: hours remaining until expiry at entry

    Returns dict with: old_premium, new_premium, profit, profit_pct, greeks_used
    """
    try:
        # Current option value and Greeks
        T_now = current_dte_hours / (TRADING_DAYS_PER_YEAR * TRADING_HOURS_PER_DAY) * 365
        greeks = compute_full_greeks(price, strike, T_now, iv, direction=direction)

        old_premium = greeks.get("premium_est", 0)
        delta = greeks.get("delta", 0)
        gamma = greeks.get("gamma", 0)
        theta_daily = greeks.get("theta", 0)
        vega = greeks.get("vega", 0)

        dS = new_price - price
        dt_days = hours_elapsed / TRADING_HOURS_PER_DAY  # convert hours to trading days
        dIV = iv_change  # in decimal (e.g., -0.05)

        # Taylor expansion
        delta_pnl = delta * dS
        gamma_pnl = 0.5 * gamma * dS ** 2
        theta_pnl = theta_daily * dt_days  # theta is per day already
        vega_pnl = vega * (dIV * 100)  # vega is per 1% IV

        new_premium = max(old_premium + delta_pnl + gamma_pnl + theta_pnl + vega_pnl, 0.01)
        profit = new_premium - old_premium
        profit_pct = (profit / old_premium * 100) if old_premium > 0 else 0

        return {
            "old_premium": round(old_premium, 2),
            "new_premium": round(new_premium, 2),
            "profit": round(profit, 2),
            "profit_pct": round(profit_pct, 1),
            "delta_pnl": round(delta_pnl, 2),
            "gamma_pnl": round(gamma_pnl, 2),
            "theta_pnl": round(theta_pnl, 2),
            "vega_pnl": round(vega_pnl, 2),
        }
    except Exception as e:
        logger.debug("option_value_at_target error: %s", e)
        return {"old_premium": 0, "new_premium": 0, "profit": 0, "profit_pct": 0}


# ── IV Estimation ──────────────────────────────────────────────────────

def estimate_iv_from_atr(price: float, atr: float) -> float:
    """
    Estimate implied volatility from ATR when real IV isn't available.
    ATR ≈ price × σ × √(1/252) × 1.25  (empirical scaling factor)
    So σ ≈ (ATR / price) × √252 / 1.25
    """
    try:
        if price <= 0 or atr <= 0:
            return 0.30  # default
        daily_vol = atr / price
        annualized = daily_vol * math.sqrt(252) / 1.25
        # Clamp to reasonable range
        return max(0.10, min(2.0, annualized))
    except Exception:
        return 0.30


def compute_option_probabilities(pick) -> dict:
    """
    Compute Black-Scholes metrics for a ScoredTicker's option play.

    Uses ATR-estimated IV when real IV isn't available.
    Returns dict with safe_strike and agg_strike probability data.
    """
    try:
        price = pick.price
        safe_strike = pick.option_safe_strike
        agg_strike = pick.option_agg_strike
        direction = pick.option_direction or "CALL"
        atr = getattr(pick, "atr", 0)

        # Estimate IV from ATR
        iv = estimate_iv_from_atr(price, atr)

        # Parse expiry to get days
        exp_str = pick.option_exp_short or pick.option_exp_long or ""
        days_to_expiry = _parse_days_to_expiry(exp_str)

        result = {"iv_est": round(iv * 100, 1)}

        # Safe strike probability (Black-Scholes)
        if safe_strike > 0:
            safe = black_scholes_prob(price, safe_strike, days_to_expiry, iv, direction=direction)
            result["safe_prob_itm"] = safe["prob_itm"]
            result["safe_delta"] = safe["delta"]

        # Aggressive strike probability
        if agg_strike > 0:
            agg = black_scholes_prob(price, agg_strike, days_to_expiry, iv, direction=direction)
            result["agg_prob_itm"] = agg["prob_itm"]
            result["agg_delta"] = agg["delta"]

        # Monte Carlo GBM P(ITM) for cross-validation
        try:
            from analysis.statistical.gbm_monte_carlo import run_daily_gbm
            # Estimate annualized drift from pct_change
            pct = getattr(pick, "pct_change", 0)
            mu_annual = (pct / 100) * 252  # rough annualized from today's move
            mc = run_daily_gbm(
                S0=price,
                mu_annual=mu_annual,
                sigma_annual=iv,
                n_days=days_to_expiry,
                n_sims=1000,
                strike=safe_strike if direction == "CALL" else None,
            )
            result["mc_prob_itm"] = round(mc["p_itm"] * 100, 1)
            result["mc_median_price"] = mc["median_price"]
            result["mc_cone"] = mc.get("cone", [])
        except Exception:
            pass

        return result

    except Exception as e:
        logger.debug("Option probability calc error: %s", e)
        return {}


def _parse_days_to_expiry(exp_str: str) -> int:
    """Parse 'Mar 21' style expiry to days from today."""
    try:
        if not exp_str or exp_str == "N/A":
            return 7  # default 1 week

        today = datetime.date.today()
        year = today.year

        # Try parsing "Mar 21" format
        exp_date = datetime.datetime.strptime(f"{exp_str} {year}", "%b %d %Y").date()

        # If parsed date is in the past, try next year
        if exp_date < today:
            exp_date = datetime.datetime.strptime(f"{exp_str} {year + 1}", "%b %d %Y").date()

        days = (exp_date - today).days
        return max(1, days)

    except Exception:
        return 7  # default
