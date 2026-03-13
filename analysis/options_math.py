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
