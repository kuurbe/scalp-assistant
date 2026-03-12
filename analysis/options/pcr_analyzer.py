"""
Put/Call Ratio analyzer using existing yfinance options data.
No new API required — uses yfinance options chain.
"""
import logging
import yfinance as yf
from data.cache import cached

logger = logging.getLogger(__name__)


@cached(ttl=300)
def get_pcr(symbol: str) -> dict:
    """Calculate put/call ratio from nearest-expiry options chain.

    Returns:
        {"pcr": 0.85, "put_oi": 12000, "call_oi": 14100,
         "put_volume": 3500, "call_volume": 4200, "expiry": "2024-03-15"}
    """
    try:
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            return {}

        exp = expirations[0]
        chain = ticker.option_chain(exp)
        calls = chain.calls
        puts = chain.puts

        call_oi = int(calls["openInterest"].sum()) if "openInterest" in calls.columns else 0
        put_oi = int(puts["openInterest"].sum()) if "openInterest" in puts.columns else 0
        call_vol = int(calls["volume"].fillna(0).sum()) if "volume" in calls.columns else 0
        put_vol = int(puts["volume"].fillna(0).sum()) if "volume" in puts.columns else 0

        pcr = round(put_oi / call_oi, 3) if call_oi > 0 else 0.0

        return {
            "pcr": pcr,
            "put_oi": put_oi,
            "call_oi": call_oi,
            "put_volume": put_vol,
            "call_volume": call_vol,
            "expiry": exp,
        }
    except Exception as e:
        logger.debug("PCR fetch failed for %s: %s", symbol, e)
        return {}


@cached(ttl=300)
def get_max_pain(symbol: str) -> dict:
    """Calculate max pain strike price for nearest expiry.

    Returns:
        {"max_pain": 185.0, "expiry": "2024-03-15"}
    """
    try:
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            return {}

        exp = expirations[0]
        chain = ticker.option_chain(exp)
        calls = chain.calls
        puts = chain.puts

        strikes = sorted(set(calls["strike"].tolist()) & set(puts["strike"].tolist()))
        if not strikes:
            return {}

        min_pain = float("inf")
        max_pain_strike = strikes[0]

        for strike in strikes:
            call_pain = calls[calls["strike"] >= strike]["openInterest"].fillna(0).sum() * 100
            put_pain = puts[puts["strike"] <= strike]["openInterest"].fillna(0).sum() * 100
            total = 0
            for s in strikes:
                if s > strike:
                    total += (s - strike) * calls[calls["strike"] == s]["openInterest"].fillna(0).sum() * 100
                elif s < strike:
                    total += (strike - s) * puts[puts["strike"] == s]["openInterest"].fillna(0).sum() * 100

            if total < min_pain:
                min_pain = total
                max_pain_strike = strike

        return {"max_pain": max_pain_strike, "expiry": exp}
    except Exception as e:
        logger.debug("Max pain failed for %s: %s", symbol, e)
        return {}


def classify_options_sentiment(pcr: float) -> str:
    """Classify options sentiment from put/call ratio.

    < 0.7 = BULLISH (more calls than puts)
    0.7-1.0 = NEUTRAL
    > 1.0 = BEARISH (more puts than calls)
    """
    if pcr < 0.7:
        return "BULLISH"
    if pcr <= 1.0:
        return "NEUTRAL"
    return "BEARISH"
