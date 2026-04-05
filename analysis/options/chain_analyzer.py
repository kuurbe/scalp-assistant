"""
Options Chain Analyzer — real chain data for scalp strike selection.

Fetches live options chains from yfinance, extracts real IV/bid/ask/volume/OI,
computes IV rank, and selects optimal scalp strikes with liquidity filtering.

Replaces ATR-estimated IV with actual market implied volatility.
"""
from __future__ import annotations

import datetime
import logging
import numpy as np

from config import settings
from data.cache import cached

logger = logging.getLogger(__name__)


# ── Chain Fetching ──────────────────────────────────────────────────────

@cached(ttl=300)
def get_scalp_chain(ticker: str, price: float, direction: str = "call") -> dict:
    """Fetch options chain filtered to scalp-relevant strikes.

    Returns real IV, bid/ask, volume, OI for ATM ±5 strikes.
    Direction: "call" or "put".
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        expirations = t.options
        if not expirations:
            return {}

        # Pick expiry: 0DTE if today is an expiry, else nearest
        today = datetime.date.today().isoformat()
        expiry = expirations[0]
        is_0dte = expiry == today

        chain = t.option_chain(expiry)
        df = chain.calls if direction.lower() == "call" else chain.puts

        if df is None or df.empty:
            return {}

        # Filter to ATM ±5 strikes
        strikes = df["strike"].values
        atm_idx = int(np.argmin(np.abs(strikes - price)))
        lo = max(0, atm_idx - 5)
        hi = min(len(strikes), atm_idx + 6)
        df_filtered = df.iloc[lo:hi].copy()

        # Build strike data
        strike_data = []
        for _, row in df_filtered.iterrows():
            bid = float(row.get("bid", 0) or 0)
            ask = float(row.get("ask", 0) or 0)
            mid = (bid + ask) / 2 if (bid + ask) > 0 else float(row.get("lastPrice", 0) or 0)
            spread = (ask - bid) / mid if mid > 0 else 999
            iv = float(row.get("impliedVolatility", 0) or 0)

            strike_data.append({
                "strike": float(row["strike"]),
                "bid": bid,
                "ask": ask,
                "mid": round(mid, 2),
                "spread_pct": round(spread, 4),
                "iv": round(iv, 4),
                "volume": int(row.get("volume", 0) or 0),
                "open_interest": int(row.get("openInterest", 0) or 0),
                "last_price": float(row.get("lastPrice", 0) or 0),
                "in_the_money": bool(row.get("inTheMoney", False)),
            })

        # ATM IV (closest strike to current price)
        atm_strike_data = strike_data[atm_idx - lo] if (atm_idx - lo) < len(strike_data) else {}
        atm_iv = atm_strike_data.get("iv", 0.30) if atm_strike_data else 0.30

        return {
            "ticker": ticker,
            "expiry": expiry,
            "is_0dte": is_0dte,
            "direction": direction.lower(),
            "price": price,
            "atm_iv": atm_iv,
            "atm_strike": atm_strike_data.get("strike", round(price)),
            "strikes": strike_data,
            "dte_days": _days_to_expiry(expiry),
        }

    except Exception as e:
        logger.debug("get_scalp_chain(%s) failed: %s", ticker, e)
        return {}


@cached(ttl=300)
def get_multi_expiry_chain(ticker: str) -> list:
    """Fetch chains for up to 3 nearest expirations (0DTE + weekly + next weekly)."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        expirations = t.options
        if not expirations:
            return []

        results = []
        for exp in expirations[:3]:
            chain = t.option_chain(exp)
            results.append({
                "expiry": exp,
                "dte_days": _days_to_expiry(exp),
                "call_count": len(chain.calls) if chain.calls is not None else 0,
                "put_count": len(chain.puts) if chain.puts is not None else 0,
            })
        return results

    except Exception as e:
        logger.debug("get_multi_expiry_chain(%s) failed: %s", ticker, e)
        return []


# ── IV Rank / Percentile ───────────────────────────────────────────────

@cached(ttl=600)
def compute_iv_rank(ticker: str, current_iv: float) -> dict:
    """Compute IV rank and percentile vs 30-day historical volatility.

    IV Rank = (current_iv - 30d_low) / (30d_high - 30d_low) * 100
    Also returns historical volatility for comparison.
    """
    try:
        import yfinance as yf

        df = yf.download(ticker, period="60d", progress=False)
        if df is None or len(df) < 20:
            return {"iv_rank": 50.0, "iv_percentile": 50.0, "hv_30d": current_iv, "iv_vs_hv": 1.0}

        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)

        close = df["Close"].astype(float)

        # Historical volatility: 30-day annualized std of log returns
        log_ret = np.log(close / close.shift(1)).dropna()
        hv_30d = float(log_ret.tail(30).std() * np.sqrt(252))

        # Rolling 30-day HV to find range
        rolling_hv = log_ret.rolling(20).std() * np.sqrt(252)
        rolling_hv = rolling_hv.dropna()

        if len(rolling_hv) < 5:
            return {"iv_rank": 50.0, "iv_percentile": 50.0, "hv_30d": hv_30d, "iv_vs_hv": 1.0}

        hv_low = float(rolling_hv.min())
        hv_high = float(rolling_hv.max())

        # IV Rank: where current IV sits in the HV range
        iv_range = hv_high - hv_low
        iv_rank = ((current_iv - hv_low) / iv_range * 100) if iv_range > 0.001 else 50.0
        iv_rank = max(0.0, min(100.0, iv_rank))

        # IV Percentile: % of days HV was below current IV
        iv_pctl = float((rolling_hv < current_iv).mean() * 100)

        # IV vs HV ratio
        iv_vs_hv = current_iv / hv_30d if hv_30d > 0.001 else 1.0

        return {
            "iv_rank": round(iv_rank, 1),
            "iv_percentile": round(iv_pctl, 1),
            "hv_30d": round(hv_30d, 4),
            "iv_vs_hv": round(iv_vs_hv, 2),
        }

    except Exception as e:
        logger.debug("compute_iv_rank(%s) failed: %s", ticker, e)
        return {"iv_rank": 50.0, "iv_percentile": 50.0, "hv_30d": 0.30, "iv_vs_hv": 1.0}


# ── Strike Selection ───────────────────────────────────────────────────

def select_optimal_strike(chain_data: dict, price: float, direction: str = "call",
                          dte: float = 1.0) -> dict:
    """Select the best scalp strike from real chain data.

    Filters by:
    - Volume > OPT_SCALP_MIN_VOLUME
    - OI > OPT_SCALP_MIN_OI
    - Spread < OPT_SCALP_MAX_SPREAD_PCT
    - Delta between OPT_SCALP_MIN_DELTA and OPT_SCALP_MAX_DELTA
    - Premium <= OPT_SCALP_PREMIUM_MAX

    Returns the best strike (ATM or 1-strike OTM) with all real data,
    or empty dict if no strike passes filters.
    """
    from analysis.options_math import compute_full_greeks

    strikes = chain_data.get("strikes", [])
    if not strikes:
        return {}

    min_vol = getattr(settings, "OPT_SCALP_MIN_VOLUME", 50)
    min_oi = getattr(settings, "OPT_SCALP_MIN_OI", 100)
    max_spread = getattr(settings, "OPT_SCALP_MAX_SPREAD_PCT", 0.10)
    min_delta = getattr(settings, "OPT_SCALP_MIN_DELTA", 0.30)
    max_delta = getattr(settings, "OPT_SCALP_MAX_DELTA", 0.65)
    max_premium = getattr(settings, "OPT_SCALP_PREMIUM_MAX", 500)

    candidates = []
    for s in strikes:
        # Liquidity filters
        if s["volume"] < min_vol:
            continue
        if s["open_interest"] < min_oi:
            continue
        if s["spread_pct"] > max_spread:
            continue
        if s["mid"] * 100 > max_premium:
            continue

        # Compute real Greeks using chain IV
        iv = s["iv"] if s["iv"] > 0.01 else chain_data.get("atm_iv", 0.30)
        greeks = compute_full_greeks(
            price, s["strike"], max(dte, 0.001), iv,
            direction=direction.lower(),
        )

        delta = abs(greeks.get("delta", 0))
        if delta < min_delta or delta > max_delta:
            continue

        # Score: prefer ATM (higher delta) with tight spread and good volume
        dist_from_atm = abs(s["strike"] - price) / price
        score = delta * 40 + (1 - s["spread_pct"]) * 30 + min(s["volume"] / 1000, 1) * 20 - dist_from_atm * 100

        candidates.append({
            "strike": s["strike"],
            "bid": s["bid"],
            "ask": s["ask"],
            "mid": s["mid"],
            "spread_pct": s["spread_pct"],
            "iv": iv,
            "volume": s["volume"],
            "open_interest": s["open_interest"],
            "delta": round(greeks.get("delta", 0), 4),
            "gamma": round(greeks.get("gamma", 0), 4),
            "theta": round(greeks.get("theta", 0), 4),
            "vega": round(greeks.get("vega", 0), 4),
            "premium_est": round(greeks.get("premium_est", s["mid"]), 2),
            "score": round(score, 2),
        })

    if not candidates:
        return {}

    # Return highest scored candidate
    candidates.sort(key=lambda x: -x["score"])
    best = candidates[0]
    best["direction"] = direction.lower()
    best["expiry"] = chain_data.get("expiry", "")
    best["is_0dte"] = chain_data.get("is_0dte", False)
    best["dte_days"] = chain_data.get("dte_days", 1.0)
    return best


# ── Helpers ────────────────────────────────────────────────────────────

def _days_to_expiry(expiry_str: str) -> float:
    """Convert expiry date string to fractional days."""
    try:
        exp_date = datetime.datetime.strptime(expiry_str, "%Y-%m-%d").date()
        today = datetime.date.today()
        delta = (exp_date - today).days
        return max(delta, 0.01)  # min 0.01 to avoid div-by-zero
    except Exception:
        return 1.0
