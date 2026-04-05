"""
Insider & congressional trading fetcher.
Uses existing Finnhub API key for insider transactions.
"""
from __future__ import annotations
import os
import logging
import requests
from data.cache import cached

logger = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _get_finnhub_key() -> str | None:
    from config.settings import get_secret
    return get_secret("FINNHUB_API_KEY") or get_secret("FINNHUB_KEY")


@cached(ttl=900)
def get_insider_transactions(symbol: str) -> list[dict]:
    """Fetch recent insider transactions for a symbol.

    Returns:
        [{"name": "John Doe", "share": 50000, "change": 50000,
          "transaction_type": "P-Purchase", "filing_date": "2024-03-10"}, ...]
    """
    key = _get_finnhub_key()
    if not key:
        return []

    try:
        resp = requests.get(
            f"{FINNHUB_BASE}/stock/insider-transactions",
            params={"symbol": symbol, "token": key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("Insider fetch failed for %s: %s", symbol, e)
        return []

    txns = []
    for t in data.get("data", [])[:20]:
        txns.append({
            "name": t.get("name", ""),
            "share": t.get("share", 0),
            "change": t.get("change", 0),
            "transaction_type": t.get("transactionType", ""),
            "filing_date": t.get("filingDate", ""),
            "transaction_code": t.get("transactionCode", ""),
        })
    return txns


@cached(ttl=900)
def get_insider_summary(symbol: str) -> dict:
    """Summarize insider activity for a symbol.

    Returns:
        {"net_insider_buys": 3, "total_bought": 150000, "total_sold": 50000,
         "sentiment": "BULLISH", "recent_buyers": ["CEO", "CFO"]}
    """
    txns = get_insider_transactions(symbol)
    if not txns:
        return {"net_insider_buys": 0, "sentiment": "NEUTRAL"}

    buys = [t for t in txns if t.get("transaction_code") in ("P", "A")]
    sells = [t for t in txns if t.get("transaction_code") in ("S", "F")]

    total_bought = sum(abs(t.get("change", 0)) for t in buys)
    total_sold = sum(abs(t.get("change", 0)) for t in sells)

    net = len(buys) - len(sells)
    if net >= 2:
        sentiment = "BULLISH"
    elif net <= -2:
        sentiment = "BEARISH"
    else:
        sentiment = "NEUTRAL"

    buyers = list({t.get("name", "")[:30] for t in buys[:5]})

    return {
        "net_insider_buys": net,
        "total_bought": total_bought,
        "total_sold": total_sold,
        "sentiment": sentiment,
        "recent_buyers": buyers,
    }
